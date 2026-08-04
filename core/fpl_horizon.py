"""Multi-gameweek fixture aggregation — the planning window behind the horizon.

WHY THIS EXISTS. `evmax.fpl_articles.ticker` answers "who scores most this
Saturday". That is the right question for a knockout tournament and the wrong
one for a 38-week league, because FPL's transfer rules make a squad sticky:
one free transfer a gameweek (bankable to 5, any extra costing -4 points), a
50% sell-on fee, and no wildcard at all in GW1 (its windows are GW2-19 and
GW20-38). A manager's opening squad is roughly 90% of their GW5 squad and
cannot be cheaply undone. Our own output shows the failure: the GW1 ticker
ranks Arsenal the best clean-sheet buy on the strength of COV at home, and
their next six are COV(2) AVL(4) CHE(4) SUN(3) BHA(3) LEE(2) -- correct for
Saturday, and it walks a reader into Villa away and Chelsea.

WHY IT IS NEWLY POSSIBLE. Odds reach a week or two out at most, so a six-week
view used to be unbuildable: five of the six gameweeks had no prices. Phase 5's
`core.fpl_ratings` produces lambdas for ANY fixture whether the bookmakers have
priced it or not, and Phase 5 Task 1 carried FPL's own FDR through
`fpl_api.parse_fixtures` for all 380 fixtures. Both halves of a horizon row are
therefore available for every gameweek of the season.

DECAY. A fixture five weeks out is worth less to a decision made today -- team
news, form and injuries all move first -- so each gameweek is weighted
`decay ** offset` (`config.FPL_HORIZON_DECAY`). `decay=1.0` counts every
gameweek equally; `decay=0.0` collapses the window onto the current gameweek and
reproduces the single-gameweek numbers EXACTLY. That last property is the
calibration anchor: it lets a horizon regression be told apart from a ratings
regression, and it is a test.

WHAT IS NOT DECAYED. The fixture count. A blank three weeks out is still a
blank and a double is still a double -- those are facts about the calendar, not
forecasts, and discounting them would hide the very thing a horizon is for.

Conventions follow `ticker()` deliberately -- per-CLUB aggregation (gameweeks
have blanks and doubles, so per-fixture rows cannot express them), clean sheets
SUMMED rather than "at least one" (a defender is paid per clean sheet kept), and
the same `market` / `model` / `mixed` provenance vocabulary. Provenance degrades
across a window rather than inheriting the near gameweek's label: a six-week
aggregate that is priced only in week one is `mixed`, never `market`.
"""

from __future__ import annotations

import math

import config

from . import fixtures

SEASON_GAMEWEEKS = 38


def window(gameweek: int, length: int | None = None) -> list[int]:
    """The planning window starting at `gameweek`, clamped to the season's end.

    Late in the season the window is simply shorter -- GW36 with a six-week
    horizon has three gameweeks left, not six, and inventing gameweeks 39-41 to
    keep the length constant would dilute every aggregate that consumed it.
    """
    if length is None:
        length = config.FPL_HORIZON_LENGTH
    return [gw for gw in range(gameweek, gameweek + length)
            if gw <= SEASON_GAMEWEEKS]


def match_projection(lam_home: float, lam_away: float) -> dict:
    """The match layer for one fixture, analytically — no simulation.

    Under the independent-Poisson scoring model the whole engine already assumes
    (`core.engine_events` draws each side's goals as `_poisson(lam, rng)`), two
    of the four quantities the horizon needs have closed forms:

      * expected goals ARE the lambdas — the mean of Poisson(λ) is λ;
      * a clean sheet is P(opponent scores 0) = exp(-opponent λ).

    The brevity is the point, not an oversight. Simulating five further
    gameweeks to recover two numbers that are exactly `exp(-λ)` would multiply
    the build cost by six for a planning aid, and would add Monte-Carlo noise to
    figures that have none. `TestProjectionAgreesWithTheSimulation` pins this
    against `build_artifact`'s simulated summary for the SAME fixture, so the
    six-week view and the one-week view cannot drift apart.

    RELATIONSHIP TO evmax/articles.py. This is the same maths as that module's
    no-sample fallback (`p_cs_home = math.exp(-lam_a)` / `p_cs_away =
    math.exp(-lam_h)`, articles.py ~line 705). It is DUPLICATED here rather than
    extracted, deliberately:

      * The only thing worth sharing would be those two `exp` calls. The
        substantial part of articles.py's fallback -- `_poisson_prob` and the
        `_outcome_probs_from_lambdas` grid -- computes 1X2 probabilities and a
        top scoreline, which the horizon does not want and never calls. No third
        Poisson GRID is created here; there are still exactly two, in
        articles.py and in the engine's sampler.
      * `evmax/articles.py` is a frozen dependency of the World Cup track
        record, pinned output-for-output by tests/test_site_render.py and
        tests/test_site_build.py. Refactoring its internals to share two
        one-line expressions puts published, graded claims at risk for no
        readability gain.

    If articles.py's fallback ever grows past those two lines, or the horizon
    ever needs 1X2, extract `_outcome_probs_from_lambdas` into a shared
    `core.poisson` at that point and have all three call it.

    A zero lambda gives a certain clean sheet (`exp(0) == 1.0`), which is the
    right answer for a side projected to score nothing rather than an edge case
    to guard.
    """
    return {
        "p_cs_home": math.exp(-lam_away),   # home keeps it clean iff AWAY scores 0
        "p_cs_away": math.exp(-lam_home),
        "exp_home_goals": lam_home,
        "exp_away_goals": lam_away,
    }


def horizon_matches(gameweek: int, length: int | None = None) -> list:
    """Match dicts for every FPL fixture in the window, shaped for `club_horizon`.

    The output keys are deliberately those of `games.fpl.model.match_summaries`,
    so the current gameweek's SIMULATED summaries and the later gameweeks'
    PROJECTED ones are interchangeable in the aggregate — the caller does not
    have to know which rows came from where.

    `stage=fixtures.FPL_STAGE`, never a bare `by_round`: the shared SCHEDULE
    holds both competitions and buckets on `fantasy_round` alone, so an
    unnarrowed call over a six-gameweek window would sweep two dozen World Cup
    ties into the Premier League fixture run.

    Every fixture yields a row whether the bookmakers have priced it or not --
    `Fixture.lambdas()` falls back to `core.ratings.match_lambdas`, and Phase 5
    registered club-differentiated Premier League ratings, which is exactly what
    makes gameweeks two through six projectable at all. `market` records which
    of the two it was, so `club_horizon` can degrade the aggregate's provenance
    instead of presenting a uniform confidence it does not have.

    A gameweek with no registered fixtures simply contributes nothing; that is a
    blank as far as the aggregate is concerned, and the caller's `clubs` list is
    what keeps a wholly-blank club on the grid.
    """
    out = []
    for gw in window(gameweek, length):
        for f in fixtures.by_round(gw, stage=fixtures.FPL_STAGE):
            lam_home, lam_away = f.lambdas()
            row = {
                "match_id": f.match_id,
                "fantasy_round": gw,
                "home": f.home,
                "away": f.away,
                "kickoff": f.kickoff.isoformat(),
            }
            row.update(match_projection(lam_home, lam_away))
            # FPL's own FDR, carried for display only -- never an input to the
            # lambdas above. getattr guards a test double built without them.
            row["home_difficulty"] = getattr(f, "home_difficulty", None)
            row["away_difficulty"] = getattr(f, "away_difficulty", None)
            row["market"] = f.lam_home is not None and f.lam_away is not None
            out.append(row)
    return out


def club_horizon(matches: list, clubs: list, window: list,
                 decay: float | None = None) -> dict:
    """One row per club: the window's fixtures aggregated, plus per-gameweek cells.

    `matches` are match-summary dicts (see `games.fpl.model.match_summaries`)
    carrying `fantasy_round`, `home`/`away`, `p_cs_home`/`p_cs_away`,
    `exp_home_goals`/`exp_away_goals`, `home_difficulty`/`away_difficulty` and
    `market`. Anything outside `window` is ignored; the caller may pass the whole
    380-fixture season.

    `clubs` is the full league list, so a club blank for the ENTIRE window still
    gets a row -- as in `ticker()`, a blank is the most actionable thing to
    report and dropping the club would hide it. A club that appears in `matches`
    but not in `clubs` is taken anyway rather than silently dropping a real
    fixture on a stale club list.

    Forecast quantities (clean sheets, goals for/against, mean difficulty) are
    weighted `decay ** offset`, where offset is the gameweek's position in the
    window. `fixtures` is NOT weighted -- it is a count of the calendar.

    `difficulty` is the WEIGHTED mean of the club's own side's FDR, so that
    `decay=0.0` reproduces the current gameweek's figure exactly like every
    other quantity here. It is None when the club has no fixture carrying any
    weight (a club blank in the window, or -- at `decay=0.0` -- blank in the
    current gameweek), never 0.0, which would read as "easiest possible fixture".

    `by_gameweek` maps every gameweek in the window to a LIST of cells, so the
    grid can tell a blank (empty list) from a double (two cells) from missing
    data (absent key -- which never happens here). Cells within a gameweek keep
    the fixture feed's order.

    Returns a dict keyed by club name; `matches` is never mutated.
    """
    if decay is None:
        decay = config.FPL_HORIZON_DECAY

    # Position in the window, not `gw - window[0]`: the offset is what the decay
    # is raised to, and it is defined by the window we were handed.
    offsets = {gw: i for i, gw in enumerate(window)}

    def _blank_row(club):
        return {"name": club, "fixtures": 0,
                "exp_clean_sheets": 0.0, "exp_goals_for": 0.0,
                "exp_goals_against": 0.0,
                "difficulty_sum": 0.0, "difficulty_weight": 0.0,
                "market": 0, "model": 0,
                "by_gameweek": {gw: [] for gw in window}}

    agg: dict = {c: _blank_row(c) for c in clubs}

    for m in matches:
        offset = offsets.get(m.get("fantasy_round"))
        if offset is None:
            continue
        # 0.0 ** 0 == 1.0, which is exactly what the calibration anchor needs:
        # the current gameweek keeps full weight and every later one drops out.
        weight = decay ** offset
        gw = m["fantasy_round"]
        for team, opponent, venue, p_cs, gf, ga, difficulty in (
            (m["home"], m["away"], "H", m.get("p_cs_home", 0.0),
             m.get("exp_home_goals", 0.0), m.get("exp_away_goals", 0.0),
             m.get("home_difficulty")),
            (m["away"], m["home"], "A", m.get("p_cs_away", 0.0),
             m.get("exp_away_goals", 0.0), m.get("exp_home_goals", 0.0),
             m.get("away_difficulty")),
        ):
            row = agg.setdefault(team, _blank_row(team))
            row["fixtures"] += 1
            row["exp_clean_sheets"] += weight * p_cs
            row["exp_goals_for"] += weight * gf
            row["exp_goals_against"] += weight * ga
            row["market" if m.get("market") else "model"] += 1
            # Each club takes its OWN side's FDR. A missing value is skipped
            # rather than counted as 0 -- see ticker().
            if difficulty is not None:
                row["difficulty_sum"] += weight * difficulty
                row["difficulty_weight"] += weight
            row["by_gameweek"][gw].append({
                "opponent": opponent, "venue": venue, "difficulty": difficulty})

    out = {}
    for club, row in agg.items():
        if not row["fixtures"]:
            basis = "—"
        elif row["market"] and row["model"]:
            basis = "mixed"
        elif row["market"]:
            basis = "market"
        else:
            basis = "model"
        difficulty = (round(row["difficulty_sum"] / row["difficulty_weight"], 2)
                      if row["difficulty_weight"] else None)
        out[club] = {
            "name": row["name"],
            "fixtures": row["fixtures"],
            "exp_clean_sheets": round(row["exp_clean_sheets"], 3),
            "exp_goals_for": round(row["exp_goals_for"], 2),
            "exp_goals_against": round(row["exp_goals_against"], 2),
            "difficulty": difficulty,
            "basis": basis,
            "by_gameweek": row["by_gameweek"],
        }
    return out
