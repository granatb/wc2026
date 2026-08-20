"""Ranking and squad selection for the FPL articles.

Pure: no I/O, no HTTP, no simulation. Input is the enriched order-book rows from
games.fpl.model.build_artifact; output is ranked entry lists the site renders.

Separate from evmax/articles.py on purpose. That module is a frozen dependency of
the World Cup track record — /track-record/ grades published WC predictions off
snapshots built with it, and the existing suite passing is the regression gate for
this whole port (spec §4 "Untouched"). FPL-specific rules (goalkeepers belong in
the defenders article; DefCon exists at all; a three-per-club squad cap) go here.

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


def captains(rows: list, top: int = 20) -> list:
    """The top `top` captain candidates by captain EV, annotated with their
    kickoff order.

    kickoff_order exists because the captain and the VICE are two different
    decisions. The captain is picked against the deadline; the vice matters only
    if the captain does not play, so a manager wants to know whether their vice
    kicks off before or after their captain. 1 is the earliest kickoff among the
    PUBLISHED candidates.

    It is a dense rank over the DISTINCT kickoff instants of the published top
    slice, not an enumeration of players: two candidates in the same match share
    an instant and therefore share an order — an enumeration would hand them
    orders like 57 vs 337 and let the prose claim one of them "kicks off later"
    when neither does. Ranking the published slice (rather than all ~560 rows)
    keeps 1 meaning "first kickoff a reader of this article can act on".

    A row with no kickoff (a blank gameweek for that club) takes the rank after
    every real instant rather than raising — `None` is not comparable to a
    string, so it needs the explicit fallback.
    """
    ranked = _ranked(rows, "captain_ev")[:top]
    instants = sorted({r["kickoff"] for r in ranked
                       if r.get("kickoff") is not None})
    order = {ko: i for i, ko in enumerate(instants, 1)}
    for r in ranked:
        r["kickoff_order"] = order.get(r.get("kickoff"), len(instants) + 1)
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
    """
    ranked = _ranked([r for r in rows if r.get("value") is not None], "value")
    for r in ranked:
        r["tier"] = price_tier(r.get("price"))
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

    Still a greedy heuristic, not an exact solver — same as the World Cup builder,
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
    """One greedy build with the XI formation fixed. See fpl_squad's docstring."""

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

    bench_quota = {pos: SQUAD_QUOTA[pos] - xi_counts.get(pos, 0)
                   for pos in SQUAD_QUOTA}
    bench_quota["GK"] = 1                      # 2 keepers, exactly 1 starts
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
        need = xi_counts.get(pos, 1 if pos == "GK" else 0)
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
        was_bench = bench_flags[_key(squad[i])]
        squad[i] = dict(repl)
        bench_flags[_key(repl)] = was_bench

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
        squad[i] = dict(repl)
        bench_flags[_key(repl)] = False

    # --- Finalize.
    xi = sorted([r for r in squad if not bench_flags[_key(r)]],
                key=lambda r: -r["x_points"])
    bench = sorted([r for r in squad if bench_flags[_key(r)]],
                   key=lambda r: -r["x_points"])

    # Legality gate. The construction above should be safe by design; this raises
    # rather than ever publishing an illegal lineup — the World Cup site shipped a
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


def squad_article(state: dict, rows: list) -> tuple:
    """Join a validated squad state (games.fpl.state) to the artifact rows.

    Returns (entries, meta) — the same two-part shape fpl_squad returns, so the
    renderer, the pitch SVG and the JSON envelope need no new handling. Works
    identically for both published states; nothing here branches on strategy.

      entries: 15 row copies in STATE order — the XI first (rank 1-11, role
               "XI"), then the bench in bench_order (rank 12-15, role "Bench")
               — each carrying is_captain / is_vice / bench_order. State order,
               not x_points order: this is OUR pick, and the page presents the
               team as fielded, not as a leaderboard.
      meta:    team_name, strategy, formation (derived from the XI),
               xi_xpoints (XI sum), projected_total (XI sum + the captain's
               x_points AGAIN — the armband doubles him), captain, vice,
               total_cost, free_transfers, chips_used, and source_count when
               the state carries one (the consensus corpus size).

    source_count is ALSO stamped on every entry: the prose templates receive
    entries only, and "N expert sources" must derive from the state rather
    than sit hardcoded in a template (review 2026-08-19, finding 5). A state
    without one (the model squad) stamps nothing — a null key would be noise
    in its published JSON.

    Raises ValueError when a state name has no artifact row. A published squad
    whose player the model never simulated is a build-stopping data problem
    (name drift, stale bootstrap) — skipping him would publish a 14-man team
    with a quietly wrong total.
    """
    by_name = {r["name"]: r for r in rows}
    source_count = state.get("source_count")
    xi_state = [e for e in state["squad"] if e["is_starter"]]
    bench_state = sorted((e for e in state["squad"] if not e["is_starter"]),
                         key=lambda e: e["bench_order"])
    entries = []
    for rank, s in enumerate(xi_state + bench_state, 1):
        row = by_name.get(s["name"])
        if row is None:
            raise ValueError(
                f"squad player {s['name']!r} ({state.get('team_name', '?')}) "
                f"has no row in the gameweek artifact — the state file and the "
                f"simulated player pool have drifted")
        e = dict(row)
        e["rank"] = rank
        e["role"] = "XI" if s["is_starter"] else "Bench"
        e["is_captain"] = s["is_captain"]
        e["is_vice"] = s["is_vice"]
        e["bench_order"] = s["bench_order"]
        if source_count is not None:
            e["source_count"] = source_count
        entries.append(e)

    xi = entries[:11]
    captain = next(e for e in xi if e["is_captain"])
    vice = next(e for e in xi if e["is_vice"])
    xi_xpoints = round(sum(e["x_points"] for e in xi), 2)
    meta = {
        "team_name": state["team_name"],
        "strategy": state["strategy"],
        "formation": formation_of(xi),
        "xi_xpoints": xi_xpoints,
        "projected_total": round(xi_xpoints + captain["x_points"], 2),
        "captain": captain["name"],
        "vice": vice["name"],
        "total_cost": state.get("total_cost"),
        "free_transfers": state.get("free_transfers"),
        "chips_used": list(state.get("chips_used", [])),
    }
    if source_count is not None:
        meta["source_count"] = source_count
    return entries, meta


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


# Goal-environment thresholds on a fixture's combined expected goals. Carried
# over from the World Cup ticker: the question ("is this a game to target
# attackers in?") and the scale (goals per match) are the same in both games.
ENV_BLOWOUT_MIN = 3.0
ENV_AVOID_MAX = 2.1


def _env_for(exp_total: float, fixture_count: int) -> str:
    if fixture_count == 0:
        return "blank"
    if fixture_count > 1:
        return "double"
    if exp_total >= ENV_BLOWOUT_MIN:
        return "blowout"
    if exp_total <= ENV_AVOID_MAX:
        return "avoid"
    return "balanced"


def ticker(matches: list, clubs: list) -> list:
    """One row per club: expected clean sheets, goals for/against, provenance.

    Per CLUB, not per fixture, because FPL gameweeks have blanks and doubles
    (spec §5.1). `clubs` is the full league list, so a club with no fixture this
    gameweek still gets a row — a blank is the most actionable thing a ticker can
    tell a manager, and dropping the club would hide it.

    exp_clean_sheets SUMS across a double rather than computing "at least one
    clean sheet". A defender is paid per clean sheet kept, so two fixtures at 45%
    are worth 0.9 clean sheets of points, not the 70% chance of keeping at least
    one. The summed figure is the one that maps to points; it can exceed 1.0 and
    that is correct.

    `basis` is spec §8's confidence label: "market" when every one of the club's
    fixtures is odds-derived, "model" when none is, "mixed" for a double with one
    of each. Mixed reports as mixed rather than rounding up to market — the
    combined number is only as good as its weaker half, and the site's whole
    positioning is that it says which is which.
    """
    def _blank_row(name):
        return {"name": name, "fixtures": 0, "opponents": [],
                "exp_clean_sheets": 0.0, "exp_goals_for": 0.0,
                "exp_goals_against": 0.0, "exp_total": 0.0,
                "market": 0, "model": 0, "kickoff": None}

    agg: dict = {c: _blank_row(c) for c in clubs}

    for m in matches:
        for team, opponent, venue, p_cs, gf, ga in (
            (m["home"], m["away"], "H", m.get("p_cs_home", 0.0),
             m.get("exp_home_goals", 0.0), m.get("exp_away_goals", 0.0)),
            (m["away"], m["home"], "A", m.get("p_cs_away", 0.0),
             m.get("exp_away_goals", 0.0), m.get("exp_home_goals", 0.0)),
        ):
            row = agg.get(team)
            if row is None:
                # A club in the fixture list but not in `clubs` — take it anyway
                # rather than silently dropping a real fixture.
                row = agg[team] = _blank_row(team)
            row["fixtures"] += 1
            row["opponents"].append((m["kickoff"], f"{opponent} ({venue})"))
            row["exp_clean_sheets"] += p_cs
            row["exp_goals_for"] += gf
            row["exp_goals_against"] += ga
            row["exp_total"] += m.get("exp_total", gf + ga)
            row["market" if m.get("market") else "model"] += 1
            if row["kickoff"] is None or m["kickoff"] < row["kickoff"]:
                row["kickoff"] = m["kickoff"]

    out = []
    for row in agg.values():
        ordered = [label for _ko, label in sorted(row["opponents"])]
        if row["market"] and row["model"]:
            basis = "mixed"
        elif row["market"]:
            basis = "market"
        else:
            basis = "model"
        out.append({
            "name": row["name"],
            # `team` is what the shared table renderer prints in its second
            # column; the ticker's subject IS a club, so the opponent list is the
            # useful thing to put there.
            "team": ", ".join(ordered) if ordered else "—",
            "position": "—",
            "opponents": ", ".join(ordered) if ordered else "—",
            "fixtures": row["fixtures"],
            "exp_clean_sheets": round(row["exp_clean_sheets"], 3),
            "exp_goals_for": round(row["exp_goals_for"], 2),
            "exp_goals_against": round(row["exp_goals_against"], 2),
            "env": _env_for(row["exp_total"], row["fixtures"]),
            "basis": basis if row["fixtures"] else "—",
            "kickoff": row["kickoff"],
        })

    out.sort(key=lambda r: (-r["exp_clean_sheets"], r["name"]))
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out
