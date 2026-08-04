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

    THE SWEEP IS LOAD-BEARING FOR LEGALITY, NOT JUST FOR POINTS -- read this before
    changing it. In the World Cup builder the sweep is a pure optimisation: every
    formation builds, and the sweep only picks the highest-scoring one. Here it is
    also the error-recovery mechanism. _squad_for_formation RAISES when a position
    cannot be filled under the cap, and which formations raise depends on the pool:
    if one club owns most of the cheap defenders, the 3-DEF formations exhaust that
    club on the bench and then cannot field a keeper, while the 5-DEF ones survive.
    The `except ValueError: continue` below is what turns those raises into a
    rescued build.

    So: do NOT short-circuit the sweep (e.g. break on the first formation that
    builds, or skip formations to save time). That converts a pool this function
    currently handles into a hard "no legal FPL squad" failure. The covering test is
    test_club_cap_holds_when_one_club_dominates_the_pool, where only 4- and 5-DEF
    formations build at all.

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


# Goal-environment thresholds on a fixture's combined expected goals. Carried
# over from the World Cup ticker: the question ("is this a game to target
# attackers in?") and the scale (goals per match) are the same in both games.
ENV_BLOWOUT_MIN = 3.0
ENV_AVOID_MAX = 2.1


def _env_for(exp_total: float, fixture_count: int) -> str:
    """The club's gameweek label: blank / double / blowout / avoid / balanced.

    Fixture count outranks the goal environment deliberately. The thresholds are
    per-MATCH, so a double's combined exp_total cannot be compared against them —
    two dull fixtures sum to a "blowout" that is nothing of the kind. Nor is a
    blended label the answer: a double's two fixtures often sit at opposite ends
    (a home game against the bottom club, an away trip to the leaders), and one
    averaged tag would describe neither. "Double" is also the more actionable
    fact of the two, and per-match goals stay recoverable from the exported
    exp_goals_for/against and fixtures columns.
    """
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

    Per CLUB, not per fixture, because FPL gameweeks have blanks and doubles.
    `clubs` is the full league list, so a club with no fixture this gameweek still
    gets a row — a blank is the most actionable thing a ticker can tell a manager,
    and dropping the club would hide it.

    exp_clean_sheets SUMS across a double rather than computing "at least one
    clean sheet". A defender is paid per clean sheet kept, so two fixtures at 45%
    are worth 0.9 clean sheets of points, not the 70% chance of keeping at least
    one. The summed figure is the one that maps to points; it can exceed 1.0 and
    that is correct.

    `basis` is the confidence label: "market" when every one of the club's
    fixtures is odds-derived, "model" when none is, "mixed" for a double with one
    of each. Mixed reports as mixed rather than rounding up to market — the
    combined number is only as good as its weaker half, and the site's whole
    positioning is that it says which is which.

    Sorted by exp_clean_sheets desc, tie-broken on club name so the order is
    deterministic: every blank club ties at 0.0, and dict insertion order would
    otherwise leak the fixture feed's ordering into the published table.
    """
    def _blank_row(club):
        return {"name": club, "fixtures": 0, "opponents": [],
                "exp_clean_sheets": 0.0, "exp_goals_for": 0.0,
                "exp_goals_against": 0.0, "exp_total": 0.0,
                "market": 0, "model": 0, "kickoff": None,
                "difficulty_sum": 0.0, "difficulty_n": 0}

    agg: dict = {c: _blank_row(c) for c in clubs}

    for m in matches:
        for team, opponent, venue, p_cs, gf, ga, difficulty in (
            (m["home"], m["away"], "H", m.get("p_cs_home", 0.0),
             m.get("exp_home_goals", 0.0), m.get("exp_away_goals", 0.0),
             m.get("home_difficulty")),
            (m["away"], m["home"], "A", m.get("p_cs_away", 0.0),
             m.get("exp_away_goals", 0.0), m.get("exp_home_goals", 0.0),
             m.get("away_difficulty")),
        ):
            # A club in the fixture list but not in `clubs` is taken anyway rather
            # than silently dropping a real fixture on a stale club list.
            row = agg.setdefault(team, _blank_row(team))
            row["fixtures"] += 1
            row["opponents"].append((m["kickoff"], f"{opponent} ({venue})"))
            row["exp_clean_sheets"] += p_cs
            row["exp_goals_for"] += gf
            row["exp_goals_against"] += ga
            row["exp_total"] += m.get("exp_total", gf + ga)
            row["market" if m.get("market") else "model"] += 1
            if row["kickoff"] is None or m["kickoff"] < row["kickoff"]:
                row["kickoff"] = m["kickoff"]
            # FPL's own FDR: each club takes its OWN side's number (home clubs
            # get home_difficulty, away clubs get away_difficulty). Missing
            # values (cached artifacts written before this carried difficulty,
            # or a fixture the feed didn't rate) are skipped rather than
            # counted as 0 -- zero would read as "easiest possible fixture".
            if difficulty is not None:
                row["difficulty_sum"] += difficulty
                row["difficulty_n"] += 1

    out = []
    for row in agg.values():
        ordered = [label for _ko, label in sorted(row["opponents"])]
        opponents = ", ".join(ordered) if ordered else "—"
        if not row["fixtures"]:
            basis = "—"
        elif row["market"] and row["model"]:
            basis = "mixed"
        elif row["market"]:
            basis = "market"
        else:
            basis = "model"
        difficulty = (round(row["difficulty_sum"] / row["difficulty_n"], 1)
                      if row["difficulty_n"] else None)
        out.append({
            "name": row["name"],
            # `team` is what the shared table renderer prints in its second
            # column; the ticker's subject IS a club, so the opponent list is the
            # useful thing to put there.
            "team": opponents,
            "position": "—",
            "opponents": opponents,
            "fixtures": row["fixtures"],
            "exp_clean_sheets": round(row["exp_clean_sheets"], 3),
            "exp_goals_for": round(row["exp_goals_for"], 2),
            "exp_goals_against": round(row["exp_goals_against"], 2),
            "env": _env_for(row["exp_total"], row["fixtures"]),
            "basis": basis,
            "difficulty": difficulty,
            "kickoff": row["kickoff"],
        })

    out.sort(key=lambda r: (-r["exp_clean_sheets"], r["name"]))
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


# The em dash a blank gameweek's cell carries. A blank and an empty cell are
# different facts and the grid must not render them the same way.
BLANK_CELL_LABEL = "—"


def _run_cell(fixtures_in_gw: list) -> dict:
    """One grid cell: the club's fixture(s) in one gameweek.

    difficulty is None for a blank rather than 0 -- zero would colour as the
    easiest fixture on the board, which is the exact opposite of what a blank
    means. For a double it is the MEAN of the two fixtures' FDR, rounded to an
    integer so the cell still lands on one of the five colour bands; the two
    opponents are both named in the label, so the reader is never left with only
    the average.
    """
    if not fixtures_in_gw:
        return {"label": BLANK_CELL_LABEL, "difficulty": None,
                "blank": True, "double": False}
    labels = [f"{f.get('opponent', '?')} ({f.get('venue', '?')})"
              for f in fixtures_in_gw]
    known = [f["difficulty"] for f in fixtures_in_gw
             if f.get("difficulty") is not None]
    return {
        "label": " + ".join(labels),
        "difficulty": round(sum(known) / len(known)) if known else None,
        "blank": False,
        "double": len(fixtures_in_gw) > 1,
    }


def fixture_runs(horizon: dict, window: list) -> list:
    """One row per club for the fixture-run grid: the summary plus a cell per week.

    `horizon` is games.fpl.model.build_artifact's "horizon" key (see
    core.fpl_horizon.club_horizon); `window` is the gameweeks it was built over,
    in order.

    RANKED ON EXPECTED CLEAN SHEETS, NOT ON FDR -- this is the finding the whole
    article rests on, so it is worth stating plainly. Measured over the live
    six-week window, FDR's middle 50% of clubs sit inside a 4% band (3.00, 3.01,
    3.01, 3.03, 3.03, 3.03, 3.06 ...) while expected clean sheets spread the same
    clubs over an 18% band. Sorting on FDR would order a dozen clubs on rounding
    noise. FDR stays as the human-readable label on each cell -- it is what every
    other fixture ticker prints and readers know it -- and the clean-sheet
    aggregate does the ranking.

    Tie-broken on club name, like ticker(): clubs blank for the entire window all
    tie at 0.0, and a published table must not reshuffle between builds because a
    dict's insertion order moved.

    `cells` is one entry per gameweek IN WINDOW ORDER, not in the horizon dict's
    key order -- the grid's columns are a timeline and a run read out of sequence
    is worse than no run at all. `gameweeks` rides along because the renderer
    needs the column headers and cannot infer them from a club that blanks
    throughout.
    """
    window = list(window)
    out = []
    for club, row in (horizon or {}).items():
        by_gw = row.get("by_gameweek") or {}
        entry = {
            "name": row.get("name", club),
            "fixtures": row.get("fixtures", 0),
            "exp_clean_sheets": row.get("exp_clean_sheets", 0.0),
            "exp_goals_for": row.get("exp_goals_for", 0.0),
            "exp_goals_against": row.get("exp_goals_against", 0.0),
            "difficulty": row.get("difficulty"),
            "basis": row.get("basis", "—"),
            "gameweeks": list(window),
            "cells": [_run_cell(by_gw.get(gw) or []) for gw in window],
        }
        out.append(entry)

    out.sort(key=lambda r: (-(r["exp_clean_sheets"] or 0.0), r["name"]))
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out
