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

import config
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


# ---------------------------------------------------------------------------
# Chip legality
# ---------------------------------------------------------------------------
# The chip a manager cannot play is the one the article must not be named after.
# FPL publishes the windows in bootstrap-static's `chips` list -- for 2026/27 the
# wildcard and the free hit run GW2-19 and GW20-38, while bench boost and triple
# captain are legal from GW1. So in GW1 there is no rebuild available at all: the
# fifteen are simply the season-opening squad, and the manager is stuck with them
# at one free transfer a week.
#
# DERIVED FROM THE FEED, NEVER FROM `gameweek == 1`. The same rule governs the
# second-half wildcard, and a hard-coded 1 would be wrong at GW20 -- where the
# chip IS available again and the "wildcard squad" framing becomes correct once
# more. It would also silently mislead in any season where FPL moves the windows.


def chip_available(chip_name: str, gameweek: int, chips: list | None) -> bool:
    """Whether `chip_name` can legally be played in `gameweek`.

    `chips` is bootstrap-static's `chips` list: dicts carrying `name`,
    `start_event` and `stop_event`. A chip appears once per window, so the
    wildcard has two entries and is available if EITHER covers the gameweek.

    ABSENT DATA IS NOT PERMISSION. No chips list, an empty one, an unknown chip
    name or an entry with no window all return False. The failure mode this
    guards is asymmetric: telling a reader to play a chip they do not have is a
    published error, while declining to mention one they do have is a missed
    sentence.
    """
    for chip in chips or []:
        if chip.get("name") != chip_name:
            continue
        start, stop = chip.get("start_event"), chip.get("stop_event")
        if start is None or stop is None:
            continue
        if start <= gameweek <= stop:
            return True
    return False


# Both under 34 characters: the <title> becomes "{title} — Gameweek N | evmax"
# and Bing errors past about 65.
SQUAD_TITLE_WILDCARD = "Draft squad & wildcard XI"
SQUAD_TITLE_OPENER = "Season-opener squad & XI"


def squad_title(gameweek: int, chips: list | None) -> str:
    """The squad article's title for this gameweek.

    The numbers in the article are the same either way -- what changes is what
    the reader can DO with them. Where the wildcard is playable the piece is a
    rebuild plan and "wildcard XI" is the honest name. Where it is not, the
    fifteen are the season-opening squad and naming them after a chip the reader
    cannot use is simply wrong.
    """
    if chip_available("wildcard", gameweek, chips):
        return SQUAD_TITLE_WILDCARD
    return SQUAD_TITLE_OPENER


def _club_counts(squad: list) -> dict:
    counts: dict = {}
    for r in squad:
        counts[r["team"]] = counts.get(r["team"], 0) + 1
    return counts


def _key(r: dict) -> tuple:
    """Identity for squad membership. Name alone collides across test fixtures and,
    in principle, across two real players sharing a web_name."""
    return (r["name"], r["team"], r["position"], r["price"])


# ---------------------------------------------------------------------------
# The squad objective
# ---------------------------------------------------------------------------
# The scratch column the sweep ranks on. Every optimisation decision below reads
# this key rather than x_points; the two are equal, exactly, whenever no horizon
# is supplied. It is stripped from the returned entries -- x_points stays the
# published number, because it is the one the article's table and prose quote.
_SCORE_KEY = "_objective"

# WHICH HORIZON AGGREGATE SCALES WHICH POSITION.
#
# A player's x_points already prices THIS gameweek's fixture. To project the same
# player across the window we need a per-club multiplier, and it has to be the
# aggregate that actually pays that position:
#
#   GK, DEF -> exp_clean_sheets. FPL pays a keeper or a defender 4 points a clean
#             sheet, and it is the single largest line in their scoring. Scaling
#             them on their club's goals FOR would reward a leaky front-runner.
#   MID, FWD -> exp_goals_for. Attacking returns are what a midfielder or a
#             striker is bought for. Scaling a striker on his club's CLEAN SHEETS
#             would be plainly wrong -- it is the number the plan singled out --
#             and would rate a 0-0 specialist as a good place to buy a forward.
#
# A midfielder's 1-point clean sheet is deliberately ignored. It is worth a
# quarter of a defender's, it is dominated by goal and assist involvement at
# every price point, and blending it in would blur the one distinction this table
# exists to make.
_HORIZON_METRIC = {
    "GK": "exp_clean_sheets",
    "DEF": "exp_clean_sheets",
    "MID": "exp_goals_for",
    "FWD": "exp_goals_for",
}


def _horizon_strengths(horizon: dict) -> dict:
    """Per metric, each club's window aggregate divided by the league mean.

    1.0 is a league-average run; 1.3 is a run 30% better than the field's.

    WHY THE LEAGUE MEAN AND NOT THE CLUB'S CURRENT GAMEWEEK. The ratio of the
    horizon aggregate to the club's own current-gameweek value is the more
    natural construction, and it is not computable from what this function is
    handed. `core.fpl_horizon.club_horizon` returns aggregates that are ALREADY
    decay-weighted SUMS over the window -- the per-gameweek terms have been added
    up and cannot be unpicked -- and `by_gameweek` carries only opponent labels
    and FDR, no lambdas, so the current gameweek's clean-sheet or goal figure
    cannot be recovered from it either. Re-deriving it would mean re-simulating
    inside a squad builder that is documented as pure.

    The league mean is the reference that IS available, and for this problem it
    is the right one: fpl_squad chooses BETWEEN clubs, so what it needs of each
    club is its run relative to the field. Normalising on the mean is also what
    makes 1.0 mean "average", which is the anchor the decay blend below needs.

    The fixture count is deliberately not divided out. A club with a double
    inside the window has a genuinely larger aggregate and should scale up; a
    club with a blank should scale down. That is the calendar, not a forecast,
    and `core.fpl_horizon` makes the same choice for the same reason.

    Clubs with no fixture in the window are excluded from the MEAN (they would
    drag it toward zero and inflate everyone else) but still get their own
    strength, which is 0.0 -- correctly, since they have no fixtures to earn from.
    """
    out: dict = {}
    for metric in set(_HORIZON_METRIC.values()):
        values = {club: float(row.get(metric) or 0.0)
                  for club, row in (horizon or {}).items()}
        playing = [v for club, v in values.items()
                   if (horizon[club].get("fixtures") or 0) > 0]
        mean = sum(playing) / len(playing) if playing else 0.0
        # A league that projects zero of this metric has nothing to rank on;
        # a flat 1.0 leaves the single-gameweek objective untouched.
        out[metric] = ({club: v / mean for club, v in values.items()} if mean > 0
                       else {club: 1.0 for club in values})
    return out


def _objective_scorer(horizon: dict | None, decay: float | None):
    """(scorer, label) — the per-player objective and the name meta reports.

    `decay` is HOW FAR toward the horizon view the objective is tilted, not the
    per-gameweek decay: that one lives in `core.fpl_horizon.club_horizon` and is
    already baked into the aggregates we are handed here. The two share
    `config.FPL_HORIZON_DECAY` as their default because they are the same
    judgement about how much the future is worth to a decision made today,
    applied at the two points where it bites.

        score = x_points * (1 + decay * (club_strength - 1))

    decay=0.0 collapses the multiplier to exactly 1.0 for every club and
    reproduces the single-gameweek squad bit for bit -- the calibration anchor,
    and the thing that lets a future squad regression be told apart from a
    ratings or horizon regression. decay=1.0 scales each player fully by his
    club's run relative to the league.

    A club absent from the horizon scores 1.0, neutral: a stale club list must
    cost that club nothing, and it must certainly not crash a build.

    KNOWN OVERLAP, stated rather than hidden: the current gameweek is itself the
    highest-weighted member of the window, so its fixture is counted once inside
    x_points and again inside the multiplier. The effect is to weight the nearest
    and most certain fixture a little more heavily than the decay alone implies,
    which is the direction we would err in anyway.
    """
    if not horizon:
        return (lambda r: r["x_points"]), "single_gameweek"
    if decay is None:
        decay = config.FPL_HORIZON_DECAY
    if not decay:
        return (lambda r: r["x_points"]), "single_gameweek"

    strengths = _horizon_strengths(horizon)

    def score(r):
        metric = _HORIZON_METRIC.get(r.get("position"))
        strength = strengths.get(metric, {}).get(r.get("team"), 1.0)
        return r["x_points"] * (1.0 + decay * (strength - 1.0))

    return score, "horizon"


def fpl_squad(rows: list, budget: float = SQUAD_BUDGET,
              max_per_club: int = MAX_PER_CLUB,
              horizon: dict | None = None,
              decay: float | None = None) -> tuple:
    """A legal 15-man FPL squad: quota, budget, formation and club cap.

    Returns (entries, meta) with the same shape articles.wildcard_squad returns, so
    the renderer and the pitch SVG need no FPL-specific handling:
      entries: 15 row copies, each with role ("XI"/"Bench") and a 1-based rank
               (1-11 XI by x_points desc, 12-15 bench).
      meta:    {"total_cost", "xi_xpoints", "xi_objective", "objective",
                "formation", "budget", "left_over"}

    THE OBJECTIVE. With `horizon` left at None this maximises x_points for the one
    gameweek, exactly as it always has. That is the wrong objective for FPL and it
    is kept only as the calibration anchor: one free transfer a gameweek (bankable
    to five, extras at -4) makes a squad sticky, so a manager's opening fifteen is
    roughly 90% of their GW5 fifteen and cannot be cheaply undone. A squad
    optimised for one Saturday is a mistake paid off over a month.

    Pass `horizon` -- `games.fpl.model.build_artifact`'s "horizon" key, i.e.
    `core.fpl_horizon.club_horizon`'s output -- and each player is instead scored
    on his club's whole fixture run, position by position (see _objective_scorer
    and _HORIZON_METRIC for which aggregate scales whom, and why). `decay` sets
    how far the objective tilts toward that view; `decay=0.0` reproduces the
    single-gameweek squad exactly, and None takes config.FPL_HORIZON_DECAY.

    Only the OBJECTIVE changes. Every legality rule -- quota, budget, formation
    limits, the three-per-club cap -- is untouched and still enforced on every
    selection and every swap, and the formation sweep below still runs in full.

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

    # Score once, here, rather than inside the sweep: the objective is a property
    # of the player, not of the formation being tried, and every one of the eight
    # formation builds below must rank on the same numbers.
    score, objective = _objective_scorer(horizon, decay)
    pool = [dict(r, **{_SCORE_KEY: score(r)}) for r in pool]

    best = None
    last_err = None
    for xi_counts in legal_xi_formations():
        try:
            entries, meta = _squad_for_formation(pool, xi_counts, budget,
                                                 max_per_club)
        except ValueError as e:
            last_err = e
            continue
        # Ranked on the objective, not on xi_xpoints: the sweep must pick the
        # formation that is best under the view the caller asked for, or the
        # horizon would decide the players and the single gameweek the shape.
        key = (meta["xi_objective"], -meta["total_cost"])
        if best is None or key > best[0]:
            best = (key, entries, meta)
    if best is None:
        raise ValueError(f"no legal FPL squad in any formation: {last_err}")
    best[2]["objective"] = objective
    return best[1], best[2]


def _squad_for_formation(pool: list, xi_counts: dict, budget: float,
                         cap: int) -> tuple:
    """One greedy build with the XI formation fixed. See fpl_squad's docstring.

    `cap` is threaded as a parameter and closed over by club_ok rather than read
    from the module global, so a caller-supplied max_per_club is honoured
    throughout and no global state is mutated.

    Every row in `pool` carries `_SCORE_KEY`, and EVERY optimisation decision here
    reads it: which players the XI takes, which way the two budget repairs trade,
    and the order the entries come out in. x_points is still reported in the meta
    and still rides on each entry, but it no longer decides anything -- that is
    what makes the single-gameweek and horizon objectives one code path rather
    than two, and it is why decay=0.0 reproduces the old squad exactly instead of
    approximately.
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
                            key=lambda r: (r["price"], -r[_SCORE_KEY]))
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
                            key=lambda r: -r[_SCORE_KEY])
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
            cheaper.sort(key=lambda r: (r["price"], -r[_SCORE_KEY]))
            repl = cheaper[0]
            saved = slot["price"] - repl["price"]
            ratio = ((slot[_SCORE_KEY] - repl[_SCORE_KEY]) / saved
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
                      and r[_SCORE_KEY] > slot[_SCORE_KEY]
                      and club_ok(squad, r, replacing=slot)]
            if not better:
                continue
            better.sort(key=lambda r: -r[_SCORE_KEY])
            repl = better[0]
            spent = repl["price"] - slot["price"]
            ratio = ((repl[_SCORE_KEY] - slot[_SCORE_KEY]) / spent
                     if spent > 0 else float("inf"))
            if ratio > best_ratio:
                best_ratio, best_swap = ratio, (i, repl)
        if best_swap is None:
            break
        i, repl = best_swap
        replace(i, repl, False)

    # --- Finalize.
    xi = sorted([r for r in squad if not bench_flags[_key(r)]],
                key=lambda r: -r[_SCORE_KEY])
    bench = sorted([r for r in squad if bench_flags[_key(r)]],
                   key=lambda r: -r[_SCORE_KEY])

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

    # _SCORE_KEY is popped rather than published: it is a scratch column of the
    # search, it is denominated in nothing a reader recognises (x_points scaled
    # by a club multiplier), and these entries go straight into the public JSON
    # feed. x_points survives on every entry as the number the table quotes.
    entries = []
    for i, r in enumerate(xi, 1):
        e = dict(r)
        e.pop(_SCORE_KEY, None)
        e["role"], e["rank"] = "XI", i
        entries.append(e)
    for i, r in enumerate(bench, len(xi) + 1):
        e = dict(r)
        e.pop(_SCORE_KEY, None)
        e["role"], e["rank"] = "Bench", i
        entries.append(e)

    cost = total_cost(squad)
    meta = {
        "total_cost": cost,
        # Both totals ride, and they are different questions. xi_xpoints is what
        # this XI projects THIS Saturday -- the number the prose and the pitch
        # quote. xi_objective is what the sweep actually maximised, and the two
        # are equal only under the single-gameweek objective.
        "xi_xpoints": round(sum(r["x_points"] for r in xi), 2),
        "xi_objective": round(sum(r[_SCORE_KEY] for r in xi), 2),
        "formation": formation_of(xi),
        "budget": budget,
        "left_over": round(budget - cost, 2),
    }
    return entries, meta


# ---------------------------------------------------------------------------
# The transfer plan
# ---------------------------------------------------------------------------
# FPL's transfer rules, from bootstrap-static's game_config.rules (captured in
# games/fpl/rules.md):
#
#   * ONE FREE TRANSFER a gameweek, bankable to a maximum of five
#     (`max_extra_free_transfers = 4` -- four banked on top of this week's one);
#   * every transfer beyond the free ones costs 4 POINTS, and no more than 20 can
#     be made in a single gameweek at all (`transfers_cap = 20`);
#   * a 50% SELL-ON FEE on realised price rises (`transfers_sell_on_fee = 0.5`),
#     so churn costs money on top of the points.
#
# HIT_COST is the whole argument of this article, and it is named here rather
# than written as a bare 4 at the comparison site because it is a rule of the
# game, not a tuning constant: if FPL ever changes the price of a hit, this is
# the one place that should have to change.
#
# THE BAR IS CLEARED OVER THE WINDOW, NOT OVER ONE GAMEWEEK. A transfer buys you
# a player for the whole run, so the four points it costs are repaid over the
# whole run too. A move worth +2 this week and +1 a week for five more weeks
# clears the bar; a move worth +3 this week and nothing after it does not.
HIT_COST = 4


def _replacement_levels(projections: list) -> dict:
    """Median WINDOW projection per position — the baseline a target is judged against.

    THE SHAPE IS evmax.articles._replacement_level's, deliberately: median value
    at the same position, subtracted to give a value-over-replacement figure. That
    is the right baseline here for the same reason it is there — no squad state is
    available (games/fpl/state.json is the owner's private order book and is not a
    site input), so the public article cannot know what the reader already owns,
    and the median incumbent at the position is the honest stand-in for whoever
    would be sold.

    That module's function is NOT called, and not because of the frozen-dependency
    rule alone. It medians `x_points` — one gameweek — and the number subtracted
    from a window projection has to be denominated in window points too, or the
    difference is not points at all and comparing it to HIT_COST is meaningless.
    Feeding it window projections would also mean writing them into `x_points`,
    which is the published single-gameweek column.

    Positions are taken from POS_MIN, which includes GK: a keeper is a transfer a
    reader makes, and dropping the position would silently exclude every one.
    """
    from statistics import median
    out = {}
    for pos in POS_MIN:
        vals = [p for p, r in projections if r.get("position") == pos]
        out[pos] = round(median(vals), 3) if vals else 0.0
    return out


def transfer_plan(rows: list, horizon: dict, top_n: int = 20,
                  window: list | None = None, decay: float | None = None,
                  max_per_club: int = MAX_PER_CLUB) -> list:
    """Transfer targets ranked on projected gain over replacement across the window.

    Each entry carries the row's usual fields plus:
      horizon_gain -- points over a replacement-level player at the SAME position,
                      summed across the planning window.
      replacement  -- the baseline that was subtracted, so a reader can reconstruct
                      the projection and disagree with the baseline rather than
                      with an opaque score.
      worth_a_hit  -- whether horizon_gain clears HIT_COST. This is the article's
                      one recommendation and it is computed, not asserted.
      fixtures / difficulty / run / gameweeks -- the club's window at a glance, so
                      the prose can say WHEN a run turns and not only who to buy.

    THE PROJECTION. Task 4's `_objective_scorer` supplies the per-gameweek rate,
    tilted toward the club's run by `decay` (see _HORIZON_METRIC for which horizon
    aggregate scales which position, and why a striker is not scaled on clean
    sheets). That rate is then carried across the window:

        window_rate = per_gameweek_rate * len(window)
        projection  = window_rate * (fixtures / len(window))

    which is just `rate * fixtures`, written in two steps because that is the
    derivation and the second step is the one with a caveat on it.

    BLANKS ARE DISCOUNTED LINEARLY, AND THAT IS AN APPROXIMATION. Five fixtures in
    a six-week window is a blank, and a blank is a gameweek of zero however good
    the club's rate is, so the target is worth proportionally less than the rate
    suggests. What the linear factor does NOT model is WHICH gameweek blanks: a
    blank in the next gameweek is worse than one five weeks out (it is certain,
    and the reader may still wildcard or transfer around a distant one), and a
    blank the week a rival club doubles is worse again. Modelling that needs the
    per-gameweek decay weights, which `core.fpl_horizon` has already summed away
    by the time we are handed these aggregates.

    A related, deliberate double-count: the horizon aggregates are sums that do
    not divide out the fixture count, so a blanked club already scores a little
    lower through its strength multiplier before this factor is applied. The
    effect is to weight blanks slightly more heavily than once, which is the
    direction to err in -- a blank is the most actionable fact on the page.

    THE WHOLE LEAGUE IS RANKED FIRST; top_n SLICES AT THE END. The replacement
    level is medianed over every priced player rather than over an already-good
    subset -- a median of the top 20 would be a "replacement level" no reader
    could ever replace anything with -- and the club cap below needs the full
    ordering to pick from.

    AT MOST `max_per_club` TARGETS FROM ONE CLUB, and this is a rule of the game
    rather than editorial taste. An FPL squad may hold three players from a club
    and no more, so a list that opens with five players from the same good run is
    advice the reader cannot take: two of those moves are illegal once the first
    three are made. Without the cap a single kind fixture run also crowds the page
    off -- on the test fixture the top 20 contained not one player from the club
    with the worst run, which is a list that has stopped being a comparison. The
    cap is applied to the RANKED list, so what each club contributes is its best
    three and not an arbitrary three, and `rank` is assigned afterwards: it is a
    position in the published plan, not in the league.

    NO AFFORDABILITY FILTER, and this was considered. The obvious candidate is a
    price ceiling on targets nobody could fit, but FPL's most expensive player
    costs about 15% of the 100.0m budget, so there is no target that is
    unaffordable in principle -- only ones that are unaffordable in a particular
    squad, and we do not know the reader's squad. A filter would therefore be
    guessing, and it would hide the exact premium the article exists to argue
    about. Price rides on every entry and the reader can apply their own.

    Rows with no price are dropped: a transfer is a purchase, and a target with no
    price is one the reader cannot make.
    """
    n = max(1, len(window) if window is not None else config.FPL_HORIZON_LENGTH)
    gameweeks = list(window) if window is not None else []
    score, _label = _objective_scorer(horizon or {}, decay)

    scored = []
    for r in rows:
        if r.get("price") is None:
            continue
        club = (horizon or {}).get(r.get("team")) or {}
        # A club absent from the horizon is assumed to play every gameweek in the
        # window. It already scores a neutral 1.0 strength (see _objective_scorer);
        # assuming a blank as well would invent a fact from a stale club list.
        fixtures = club.get("fixtures")
        fixtures = n if fixtures is None else fixtures
        projection = score(r) * n * (fixtures / n)
        scored.append((projection, r, club, fixtures))

    if not scored:
        return []

    replacement = _replacement_levels([(p, r) for p, r, _c, _f in scored])

    out = []
    for projection, r, club, fixtures in scored:
        base = replacement.get(r.get("position"), 0.0)
        gain = round(projection - base, 2)
        by_gw = club.get("by_gameweek") or {}
        run_gws = gameweeks or sorted(by_gw)
        entry = dict(r)
        entry["horizon_gain"] = gain
        entry["replacement"] = base
        # Compared on the ROUNDED gain, so the published number and the published
        # verdict can never disagree -- a 3.999 printed as 4.00 and flagged "no"
        # is the kind of thing that reads as a bug in the article.
        entry["worth_a_hit"] = gain >= HIT_COST
        entry["fixtures"] = fixtures
        entry["difficulty"] = club.get("difficulty")
        entry["gameweeks"] = list(run_gws)
        # The club's FDR week by week -- None where it blanks. Enough for the
        # prose to say when a run turns without duplicating the runs grid.
        entry["run"] = [_run_cell(by_gw.get(gw) or [])["difficulty"]
                        for gw in run_gws]
        out.append(entry)

    # Rank the whole league, then take each club's best `max_per_club` in that
    # order, then re-rank so the published positions run 1..n with no holes.
    ordered = _ranked(out, "horizon_gain")
    per_club: dict = {}
    kept = []
    for e in ordered:
        club = e.get("team")
        if per_club.get(club, 0) >= max_per_club:
            continue
        per_club[club] = per_club.get(club, 0) + 1
        kept.append(e)
        if len(kept) >= top_n:
            break
    for i, e in enumerate(kept, 1):
        e["rank"] = i
    return kept


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
