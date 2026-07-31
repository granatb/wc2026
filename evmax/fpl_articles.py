"""Ranking and squad selection for the FPL articles.

Pure: no I/O, no HTTP, no simulation. Input is the enriched order-book rows from
games.fpl.model.build_artifact; output is ranked entry lists the site renders.

Separate from evmax/articles.py on purpose. That module is a frozen dependency of
the World Cup track record — /track-record/ grades published WC predictions off
snapshots built with it, and the existing suite passing is the regression gate for
this whole port. FPL-specific rules (goalkeepers belong in the defenders article;
DefCon exists at all; a three-per-club squad cap) go here.

Reused from articles.py where the rule is genuinely identical, not merely similar:
XI formation limits and price tiers.
"""

from __future__ import annotations

from evmax.articles import (POS_MAX, POS_MIN, SQUAD_QUOTA, XI_SIZE,
                            formation_of, legal_xi_formations, price_tier)
from games.fpl.model import DEFCON_THRESHOLD

# FPL squad rules (2026/27 official, games/fpl/rules.md).
SQUAD_BUDGET = 100.0
MAX_PER_CLUB = 3
# Positions the defenders article covers. FPL pays goalkeepers a 4-point clean
# sheet and a 10-point goal, so they belong with defenders rather than in an
# article of their own — the reader's decision is "which end of the pitch do I
# spend on", and one article answers it.
DEFENSIVE_POSITIONS = ("DEF", "GK")


def _ranked(rows: list, key: str, reverse: bool = True) -> list:
    out = [dict(r) for r in sorted(rows, key=lambda r: r[key], reverse=reverse)]
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


def captains(rows: list) -> list:
    """Captain candidates by captain EV, annotated with their kickoff order.

    kickoff_order exists because the captain and the VICE are two different
    decisions. The captain is picked against the deadline; the vice matters only
    if the captain does not play, so a manager wants to know whether their vice
    kicks off before or after their captain. 1 is the earliest kickoff among the
    candidates.

    A row with no kickoff (a blank gameweek for that club) sorts last rather than
    raising — None is not comparable to a string, so it needs an explicit key.
    """
    ranked = _ranked(rows, "captain_ev")
    by_kickoff = sorted(ranked, key=lambda r: (r.get("kickoff") is None,
                                               r.get("kickoff") or ""))
    order = {id(r): i for i, r in enumerate(by_kickoff, 1)}
    for r in ranked:
        r["kickoff_order"] = order[id(r)]
    return ranked


def defenders(rows: list) -> list:
    """Defenders and goalkeepers by expected points.

    The rows carry cs_points, defcon and bonus as separate columns, so the article
    can show a reader WHERE a defender's points come from — a 6.0 built on clean
    sheets is a different bet from a 6.0 built on DefCon.
    """
    return _ranked([r for r in rows if r.get("position") in DEFENSIVE_POSITIONS],
                   "x_points")


def efficiency(rows: list) -> list:
    """Points per million, tagged with a price tier.

    Rows with no price are dropped: value is undefined without one, and a null in
    the primary sort column would order arbitrarily.

    price_tier's thresholds (5.5 / 8.0) are imported from articles.py rather than
    redefined: they happen to be exactly FPL's own vernacular for enabler /
    mid-price / premium, and the live price range (4.0-15.5) sits across them
    correctly.
    """
    ranked = _ranked([r for r in rows if r.get("value") is not None], "value")
    for r in ranked:
        r["tier"] = price_tier(r.get("price"))
    return ranked


def defcon_leaders(rows: list) -> list:
    """Players by P(defensive contribution >= their position's threshold).

    Ranked on the PROBABILITY, not the points: the points column is exactly
    2 x the probability, so the ordering is identical, but the probability is the
    number the article is about — "Gabriel hits 10 CBIT in 71% of simulations" is
    the claim, and "1.42 DefCon points" is its consequence.

    Goalkeepers are excluded because they are not DefCon-eligible at all, and
    players projecting exactly zero are excluded because they pad the list with
    names that cannot earn the points.
    """
    pool = [r for r in rows
            if DEFCON_THRESHOLD.get(r.get("position")) is not None
            and (r.get("p_defcon") or 0.0) > 0.0]
    ranked = _ranked(pool, "p_defcon")
    for r in ranked:
        r["defcon_threshold"] = DEFCON_THRESHOLD[r["position"]]
    return ranked


def _club_counts(squad: list) -> dict:
    counts: dict = {}
    for r in squad:
        counts[r["team"]] = counts.get(r["team"], 0) + 1
    return counts


def _key(r: dict) -> tuple:
    """Identity for squad membership. Name alone collides across test fixtures and,
    in principle, across two real players sharing a web_name."""
    return (r["name"], r["team"], r["position"], r["price"])


def fpl_squad(rows: list, budget: float = SQUAD_BUDGET,
              max_per_club: int = MAX_PER_CLUB) -> tuple:
    """A legal 15-man FPL squad: quota, budget, formation and club cap.

    Returns (entries, meta) with the same shape articles.wildcard_squad returns, so
    the renderer and the pitch SVG need no FPL-specific handling:
      entries: 15 row copies, each with role ("XI"/"Bench") and a 1-based rank
               (1-11 XI by x_points desc, 12-15 bench).
      meta:    {"total_cost", "xi_xpoints", "formation", "budget", "left_over"}

    Method: sweep every legal XI formation, greedily build the cheapest legal bench
    and the best XI for each, repair over budget by the smallest xPts-lost-per-pound,
    then spend what is left on the best xPts-gained-per-pound XI upgrade. Best
    xi_xpoints wins.

    The club cap is checked on every selection AND every swap, not once at the end.
    Checking at the end would mean rejecting an otherwise-optimal squad with no way
    to repair it; checking inline means the search only ever walks legal states.

    The cap also makes the formation sweep do real work beyond xPts: a formation
    whose greedy build cannot fill a position under the cap raises and is skipped,
    so the sweep is what rescues pools dominated by one club.

    Still a greedy heuristic, not an exact solver -- same as the World Cup builder,
    and the same caveat applies: it will not always find the true optimum.

    Raises ValueError if no legal squad exists in any formation.
    """
    pool = [r for r in rows if r.get("price") is not None and r.get("team")]
    for pos, need in SQUAD_QUOTA.items():
        have = sum(1 for r in pool if r.get("position") == pos)
        if have < need:
            raise ValueError(
                f"insufficient {pos} pool for an FPL squad: need {need}, have {have}")

    best = None
    last_err = None
    for xi_counts in legal_xi_formations():
        try:
            entries, meta = _squad_for_formation(pool, xi_counts, budget,
                                                 max_per_club)
        except ValueError as e:
            last_err = e
            continue
        key = (meta["xi_xpoints"], -meta["total_cost"])
        if best is None or key > best[0]:
            best = (key, entries, meta)
    if best is None:
        raise ValueError(f"no legal FPL squad in any formation: {last_err}")
    return best[1], best[2]


def _squad_for_formation(pool: list, xi_counts: dict, budget: float,
                         cap: int) -> tuple:
    """One greedy build with the XI formation fixed. See fpl_squad's docstring.

    `cap` is threaded as a parameter and closed over by club_ok rather than read
    from the module global, so a caller-supplied max_per_club is honoured
    throughout and no global state is mutated.
    """
    # legal_xi_formations() returns DEF/MID/FWD only -- the GK is implicit, since
    # every legal XI fields exactly one. Normalise it here so both the XI need and
    # the bench quota below are derived from one table rather than hardcoded.
    xi_full = dict(xi_counts)
    xi_full["GK"] = XI_SIZE - sum(xi_counts.values())

    def club_ok(squad, candidate, replacing=None):
        counts = _club_counts(squad)
        if replacing is not None:
            counts[replacing["team"]] = counts.get(replacing["team"], 0) - 1
        return counts.get(candidate["team"], 0) < cap

    # --- Bench: the cheapest legal filler at each position the XI does not field.
    # Philosophy carried over from the World Cup builder: spend nothing on the
    # bench, spend everything on the XI.
    squad: list = []
    bench_flags: dict = {}

    def take(candidate, is_bench):
        squad.append(dict(candidate))
        bench_flags[_key(candidate)] = is_bench

    def replace(i, repl, is_bench):
        """Swap squad[i] for repl, moving the bench flag with the slot.

        The outgoing key is popped rather than left behind: a stale entry is
        harmless while every live member's key is unique, but the invariant is
        cheaper to keep than to reason about.
        """
        bench_flags.pop(_key(squad[i]), None)
        squad[i] = dict(repl)
        bench_flags[_key(repl)] = is_bench

    bench_quota = {pos: SQUAD_QUOTA[pos] - xi_full.get(pos, 0)
                   for pos in SQUAD_QUOTA}
    for pos in ("GK", "DEF", "MID", "FWD"):
        need = bench_quota[pos]
        candidates = sorted([r for r in pool if r["position"] == pos],
                            key=lambda r: (r["price"], -r["x_points"]))
        taken = 0
        for c in candidates:
            if taken >= need:
                break
            if _key(c) in bench_flags or not club_ok(squad, c):
                continue
            take(c, True)
            taken += 1
        if taken < need:
            raise ValueError(f"cannot fill the {pos} bench under the club cap")

    # --- XI: the best x_points players completing each position's quota.
    for pos in ("GK", "DEF", "MID", "FWD"):
        need = xi_full.get(pos, 0)
        candidates = sorted([r for r in pool if r["position"] == pos],
                            key=lambda r: -r["x_points"])
        taken = 0
        for c in candidates:
            if taken >= need:
                break
            if _key(c) in bench_flags or not club_ok(squad, c):
                continue
            take(c, False)
            taken += 1
        if taken < need:
            raise ValueError(f"cannot fill the {pos} XI slots under the club cap")

    def total_cost(sq):
        return round(sum(r["price"] for r in sq), 2)

    def in_squad(sq):
        return {_key(r) for r in sq}

    # --- Repair 3a: downgrade until legal on budget, smallest xPts loss per pound.
    guard = 0
    while total_cost(squad) > budget and guard < len(squad) * len(pool):
        guard += 1
        best_swap, best_ratio = None, None
        members = in_squad(squad)
        for i, slot in enumerate(squad):
            cheaper = [r for r in pool
                       if r["position"] == slot["position"]
                       and _key(r) not in members
                       and r["price"] < slot["price"]
                       and club_ok(squad, r, replacing=slot)]
            if not cheaper:
                continue
            cheaper.sort(key=lambda r: (r["price"], -r["x_points"]))
            repl = cheaper[0]
            saved = slot["price"] - repl["price"]
            ratio = ((slot["x_points"] - repl["x_points"]) / saved
                     if saved > 0 else float("inf"))
            if best_ratio is None or ratio < best_ratio:
                best_ratio, best_swap = ratio, (i, repl)
        if best_swap is None:
            break
        i, repl = best_swap
        replace(i, repl, bench_flags[_key(squad[i])])

    if total_cost(squad) > budget:
        raise ValueError(
            f"no legal 15-man squad fits within budget {budget}m "
            f"(cheapest assembled squad costs {total_cost(squad)}m)")

    # --- Repair 3b: spend what is left on the best XI upgrade per pound.
    guard = 0
    while guard < len(squad) * len(pool):
        guard += 1
        left_over = round(budget - total_cost(squad), 2)
        if left_over <= 0:
            break
        best_swap, best_ratio = None, 0.0
        members = in_squad(squad)
        for i, slot in enumerate(squad):
            if bench_flags[_key(slot)]:
                continue           # the bench stays cheap by design
            better = [r for r in pool
                      if r["position"] == slot["position"]
                      and _key(r) not in members
                      and r["price"] <= left_over + slot["price"]
                      and r["x_points"] > slot["x_points"]
                      and club_ok(squad, r, replacing=slot)]
            if not better:
                continue
            better.sort(key=lambda r: -r["x_points"])
            repl = better[0]
            spent = repl["price"] - slot["price"]
            ratio = ((repl["x_points"] - slot["x_points"]) / spent
                     if spent > 0 else float("inf"))
            if ratio > best_ratio:
                best_ratio, best_swap = ratio, (i, repl)
        if best_swap is None:
            break
        i, repl = best_swap
        replace(i, repl, False)

    # --- Finalize.
    xi = sorted([r for r in squad if not bench_flags[_key(r)]],
                key=lambda r: -r["x_points"])
    bench = sorted([r for r in squad if bench_flags[_key(r)]],
                   key=lambda r: -r["x_points"])

    # Legality gate. The construction above should be safe by design; this raises
    # rather than ever publishing an illegal lineup -- the World Cup site shipped a
    # 2-5-3 once because only the pool, not the XI's slots, was guarded.
    counts = {pos: sum(1 for r in xi if r["position"] == pos) for pos in POS_MIN}
    for pos, need in POS_MIN.items():
        if not (need <= counts.get(pos, 0) <= POS_MAX[pos]):
            raise ValueError(
                f"FPL XI violates formation limits at {pos}: {counts.get(pos, 0)} "
                f"(legal range {need}-{POS_MAX[pos]}); formation {formation_of(xi)}")
    clubs = _club_counts(squad)
    over = {t: c for t, c in clubs.items() if c > cap}
    if over:
        raise ValueError(f"FPL squad violates the {cap}-per-club cap: {over}")

    entries = []
    for i, r in enumerate(xi, 1):
        e = dict(r)
        e["role"], e["rank"] = "XI", i
        entries.append(e)
    for i, r in enumerate(bench, len(xi) + 1):
        e = dict(r)
        e["role"], e["rank"] = "Bench", i
        entries.append(e)

    cost = total_cost(squad)
    meta = {
        "total_cost": cost,
        "xi_xpoints": round(sum(r["x_points"] for r in xi), 2),
        "formation": formation_of(xi),
        "budget": budget,
        "left_over": round(budget - cost, 2),
    }
    return entries, meta
