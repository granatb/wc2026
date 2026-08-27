"""Fantasy Premier League model.

Maps the shared engine's simulated events onto the official 2026/27 FPL points
scale and emits the order book.

Every constant here cites a row in games/fpl/rules.md, which is a verbatim capture
of the official rules page. The two DIVISORS are the trap: bootstrap-static's
game_config.scoring reports `saves: 1` and `goals_conceded: -1` as unit values,
but the real rules are one point per THREE saves and minus one per TWO conceded.
Reading the feed literally mis-prices every goalkeeper.

Threshold scoring is computed from PER-SIM COUNTS, never from means, because
E[floor(x/n)] != floor(E[x]/n).
"""

from __future__ import annotations

from core import engine_events

# --- confirmed scoring values (games/fpl/rules.md) -------------------------
GOAL_PTS = {"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}
ASSIST_PTS = 3
CS_PTS = {"GK": 4, "DEF": 4, "MID": 1, "FWD": 0}
APPEARANCE_60 = 2          # 60 minutes or more, excluding stoppage time
APPEARANCE_SHORT = 1       # up to 60 minutes
YELLOW_PTS = -1
RED_PTS = -3
OWN_GOAL_PTS = -2
PEN_MISS_PTS = -2
PEN_SAVE_PTS = 5

# Divisors — from the official rules page ONLY, not from the API feed.
SAVES_PER_POINT = 3        # "For every 3 shot saves by a goalkeeper: 1"
CONCEDED_PER_MINUS = 2     # "For every 2 goals conceded by a goalkeeper or defender: -1"

# Defensive contribution: a threshold crossing worth exactly 2, capped.
# Defenders count CBIT; midfielders and forwards count CBIRT (recoveries included).
# Goalkeepers are not eligible.
DEFCON_PTS = 2
DEFCON_THRESHOLD = {"DEF": 10, "MID": 12, "FWD": 12}

# Positions that suffer the goals-conceded penalty.
_CONCEDE_POSITIONS = ("GK", "DEF")


def expected_points(ev: dict) -> float:
    """Expected FPL points from mean events, EXCLUDING the threshold components.

    Saves, goals conceded, DefCon and bonus are threshold or rank quantities and
    must be computed from per-sim samples — see saves_points, conceded_points,
    defcon_points and the bonus accumulator. Keeping them out of here makes it
    impossible to double-count them by accident.
    """
    pos = ev["position"]
    pts = 0.0
    # Appearance: the 60+ tier and the short tier are mutually exclusive.
    played, played_60 = ev.get("played", 0.0), ev.get("played_60", 0.0)
    pts += played_60 * APPEARANCE_60
    pts += max(0.0, played - played_60) * APPEARANCE_SHORT
    pts += ev.get("goals", 0.0) * GOAL_PTS.get(pos, 4)
    pts += ev.get("assists", 0.0) * ASSIST_PTS
    pts += ev.get("clean_sheet", 0.0) * CS_PTS.get(pos, 0)
    pts += ev.get("yellow", 0.0) * YELLOW_PTS
    pts += ev.get("red", 0.0) * RED_PTS
    return pts


def saves_points(save_samples: list) -> float:
    """Expected points from saves: mean of floor(saves / 3) over the sims.

    NOT floor(mean_saves / 3) — a keeper averaging 3.0 saves does not reliably
    bank the point, because the sims below 3 pay nothing.
    """
    if not save_samples:
        return 0.0
    return sum(s // SAVES_PER_POINT for s in save_samples) / float(len(save_samples))


def conceded_points(position: str, conceded_samples: list) -> float:
    """Expected points from goals conceded: mean of -floor(conceded / 2).

    Only goalkeepers and defenders are charged.
    """
    if position not in _CONCEDE_POSITIONS or not conceded_samples:
        return 0.0
    total = sum(c // CONCEDED_PER_MINUS for c in conceded_samples)
    return -total / float(len(conceded_samples))


def defcon_threshold(position: str) -> int | None:
    """The DefCon action count a position must reach, or None if not eligible."""
    return DEFCON_THRESHOLD.get(position)


def defcon_probability(position: str, defcon_samples: list) -> float:
    """P(defensive-contribution count >= this position's threshold).

    Conditional on having played, like save_samples and defcon_samples generally
    (they only accumulate on sims where the player was on the pitch). Callers
    scale by appearance_probability to make it unconditional.
    """
    threshold = defcon_threshold(position)
    if threshold is None or not defcon_samples:
        return 0.0
    hits = sum(1 for c in defcon_samples if c >= threshold)
    return hits / float(len(defcon_samples))


def defcon_points(position: str, defcon_samples: list) -> float:
    """Expected DefCon points: 2 x P(count >= threshold).

    A threshold crossing, not a rate — 2 x rate/threshold is wrong in both tails,
    over-paying players who never reach it and under-paying those who always do.
    The payout is capped at 2 no matter how far past the threshold a player goes.
    """
    return DEFCON_PTS * defcon_probability(position, defcon_samples)


# --- Bonus points ---------------------------------------------------------
# The official BPS table has 30+ components: successful crosses, dribbles,
# pass-completion tiers, fouls won, errors leading to an attempt. We have NO data
# for most of them, so reconstructing BPS from components is impossible.
#
# Instead: a per-90 baseline from each player's own realized BPS history carries
# everything we cannot see, and the components we DO sample are applied as exact
# deltas from the table. Rank all players in the match, award 3/2/1.
#
# Deliberately NOT applied per event: the +1 for a save inside the box and the +1
# for a save from a big chance both need shot-location data we lack, so they are
# absorbed into the baseline rate. Same for goalline clearances and errors. Also
# NOT applied: the rules page pays a goal scored direct from a penalty a flat 12
# BPS for any position, separate from the position-scaled non-penalty rows below
# (GK/DEF 12, MID 18, FWD 24) -- the engine does not distinguish penalty from
# open-play goals, so bps_from_row always uses the position-scaled value and a
# forward's penalty is over-credited (24 instead of 12). Deferred, not fixed,
# until the engine can tell the two apart.
BPS_PLAY_60 = 6
BPS_PLAY_SHORT = 3
BPS_GOAL = {"GK": 12, "DEF": 12, "MID": 18, "FWD": 24}
BPS_ASSIST = 9
BPS_CLEAN_SHEET = {"GK": 12, "DEF": 12, "MID": 0, "FWD": 0}
BPS_SAVE = 2
BPS_CONCEDED = -4          # per goal, goalkeepers and defenders only
BPS_YELLOW = -3
BPS_RED = -9

# Row layout produced by engine_events' per_match_hook.
(_NAME, _POS, _GOALS, _ASSISTS, _MINUTES, _CS, _CONCEDED, _SAVES, _YELLOW, _RED,
 _DEFCON) = range(11)


def bps_from_row(row: tuple, baseline: float) -> int:
    """BPS for one player in one simulated match.

    `baseline` is the player's realized BPS per 90, prorated by minutes played. It
    stands in for every component we cannot sample.
    """
    pos = row[_POS]
    bps = BPS_PLAY_60 if row[_MINUTES] >= 60 else BPS_PLAY_SHORT
    bps += row[_GOALS] * BPS_GOAL.get(pos, 18)
    bps += row[_ASSISTS] * BPS_ASSIST
    if row[_CS]:
        bps += BPS_CLEAN_SHEET.get(pos, 0)
    bps += row[_SAVES] * BPS_SAVE
    if pos in _CONCEDE_POSITIONS:
        bps += row[_CONCEDED] * BPS_CONCEDED
    bps += row[_YELLOW] * BPS_YELLOW
    bps += row[_RED] * BPS_RED
    bps += int(round(baseline * row[_MINUTES] / 90.0))
    return bps


def _bonus_awards(rows: list, baselines: dict) -> dict:
    """{name: bonus points} for the players in ONE match in ONE sim, via BPS rank.

    Extracted out of BonusAccumulator so the tie-handling logic backs both the
    cross-sim bonus average (BonusAccumulator, below) and the per-sim points
    total (SimPointsAccumulator) from a single place — bonus must not be
    reimplemented twice, only consumed twice.

    Ties consume award POSITIONS, matching the official rule: two players tied on
    top both take 3 and the third-most BPS takes 1 (not 2, because the tie has
    already used two positions). Two tied for second both take 2 and no 1 is
    awarded at all.
    """
    scored = [(bps_from_row(r, baselines.get(r[_NAME], 0.0)), r[_NAME])
              for r in rows]
    if not scored:
        return {}
    # Group by BPS, highest first. Each group takes the award for the next
    # open position, then consumes as many positions as it has members.
    groups: dict = {}
    for bps, name in scored:
        groups.setdefault(bps, []).append(name)

    awards: dict = {}
    placed = 0
    for bps in sorted(groups, reverse=True):
        if placed == 0:
            award = 3
        elif placed == 1:
            award = 2
        elif placed == 2:
            award = 1
        else:
            break
        for name in groups[bps]:
            awards[name] = award
        placed += len(groups[bps])
    return awards


class BonusAccumulator:
    """Accumulates expected bonus points across sims via rank-within-match.

    Pass `observe` as engine_events' per_match_hook. After the sim completes,
    `expected(name)` gives that player's mean bonus.
    """

    def __init__(self, baselines: dict):
        self.baselines = baselines or {}
        self._total: dict = {}
        self._sims: dict = {}

    def observe(self, _match_id: str, rows: list, _sim_index: int | None = None) -> None:
        for r in rows:
            name = r[_NAME]
            self._sims[name] = self._sims.get(name, 0) + 1
        for name, award in _bonus_awards(rows, self.baselines).items():
            self._total[name] = self._total.get(name, 0) + award

    def expected(self, name: str) -> float:
        """Mean bonus per MATCH APPEARANCE, not per sim.

        Double gameweeks: the Phase 3 plan left open whether total_points'
        played/sims scaling reconstructs the SUM across a two-fixture week.
        Settled 2026-08-19 against SimPointsAccumulator.mean() on a synthetic
        double (tests/test_fpl_model.TestDoubleGameweekTotalPoints), and the
        answer is NO: ps.sims counts once per MATCH appearance (twice per
        outer sim for a doubled player), so played/sims stays ~1.0 and the
        whole assembled total — this bonus term included — comes out as a
        per-MATCH average, exactly half the gameweek total. The order book's
        x_points therefore comes from SimPointsAccumulator.mean(), which sums
        a player's matches within each sim; total_points remains correct for
        any single-fixture player.
        """
        sims = self._sims.get(name, 0)
        if not sims:
            return 0.0
        return self._total.get(name, 0) / float(sims)


def _row_points(row: tuple, bonus_award: int) -> float:
    """Total FPL points for ONE player in ONE simulated match, bonus included.

    This is the per-match building block SimPointsAccumulator sums across a
    sim's matches (for double gameweeks). It mirrors expected_points +
    saves_points + conceded_points + defcon_points, but evaluated directly on a
    single sim's row rather than on a mean or a threshold series, because that
    is exactly what a per-sim points DISTRIBUTION (as opposed to an expectation)
    needs.
    """
    pos = row[_POS]
    pts = APPEARANCE_60 if row[_MINUTES] >= 60 else APPEARANCE_SHORT
    pts += row[_GOALS] * GOAL_PTS.get(pos, 4)
    pts += row[_ASSISTS] * ASSIST_PTS
    if row[_CS]:
        pts += CS_PTS.get(pos, 0)
    pts += row[_YELLOW] * YELLOW_PTS
    pts += row[_RED] * RED_PTS
    pts += row[_SAVES] // SAVES_PER_POINT
    if pos in _CONCEDE_POSITIONS:
        pts -= row[_CONCEDED] // CONCEDED_PER_MINUS
    threshold = DEFCON_THRESHOLD.get(pos)
    if threshold is not None and row[_DEFCON] >= threshold:
        pts += DEFCON_PTS
    pts += bonus_award
    return pts


def _tail_mean(values: list, q: float = 0.85) -> float:
    """Mean of the top (1 - q) fraction of an already zero-padded `values` list.

    Pulled out as a standalone, list-in/float-out function (mirroring
    engine_events.percentile) so the statistic itself -- given a known
    distribution -- can be unit-tested directly, independent of the per-sim
    scoring machinery that builds the distribution in the first place.

    Tail size floors at 1 element so a single-sim (or otherwise tiny) input
    never produces an empty slice.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    n = max(1, round((1 - q) * len(ordered)))
    tail = ordered[-n:]
    return sum(tail) / len(tail)


class SimPointsAccumulator:
    """Per-sim, per-player TOTAL FPL points, summed across matches within a sim.

    Pass `observe` as (one leg of) engine_events' per_match_hook. Unlike
    BonusAccumulator, this needs the sim boundary: a double-gameweek player's
    points for one sim are the sum of both his matches' points in THAT sim, and
    sim_index is the only thing that tells "two matches, one sim" apart from
    "two matches, two different sims".

    Design choices:

    - Kept as a SEPARATE class from BonusAccumulator, rather than merging the
      two, so BonusAccumulator's existing cross-sim-average API (and its test
      suite) is untouched. Both classes need a match's bonus award, so the
      ranking/tie logic lives once in the module-level `_bonus_awards` and is
      called from each `observe` -- reused, not duplicated. (`_bonus_awards`
      does get *evaluated* twice per match-sim, once per accumulator, but each
      evaluation is independent bookkeeping for a different question; neither
      accumulator's own total double-counts a bonus award.)
    - `sims` (the total sim count) is a REQUIRED CONSTRUCTOR ARGUMENT rather than
      inferred from what gets observed or supplied via a later finalise() call.
      mean() and tail_mean() both need to zero-pad every player's per-sim series
      out to the true sim count, and this pipeline has no separate "finalise"
      step -- build_rows reads mean()/tail_mean() straight after
      simulate_round() returns -- so the constructor is the one place that
      value is available before it is needed, and cannot be forgotten.
    """

    def __init__(self, baselines: dict, sims: int):
        self.baselines = baselines or {}
        self.sims = sims
        self._per_sim: dict = {}  # name -> {sim_index: points accumulated that sim}

    def observe(self, _match_id: str, rows: list, sim_index: int) -> None:
        awards = _bonus_awards(rows, self.baselines)
        for row in rows:
            name = row[_NAME]
            pts = _row_points(row, awards.get(name, 0))
            bucket = self._per_sim.setdefault(name, {})
            bucket[sim_index] = bucket.get(sim_index, 0.0) + pts

    def _distribution(self, name: str) -> list:
        """Per-sim totals for `name`, zero-padded to the full `sims` length.

        Zero-padding is what makes mean()/tail_mean() UNCONDITIONAL: a sim the
        player did not feature in (no row in any match that sim) never creates
        an entry in `_per_sim`, so it must default to 0 rather than being
        excluded from the distribution -- exactly the same reasoning the old
        (now-retired) _unconditional_goal_samples used for the goal-count
        ceiling.
        """
        bucket = self._per_sim.get(name, {})
        values = [0.0] * self.sims
        for sim_index, pts in bucket.items():
            values[sim_index] = pts
        return values

    def mean(self, name: str) -> float:
        """Unconditional mean points per sim, zero-padded for non-appearances."""
        if not self.sims:
            return 0.0
        return sum(self._per_sim.get(name, {}).values()) / self.sims

    def histogram(self, name: str) -> dict:
        """{integer points: count of sims} over ALL sims — the discrete PMF.

        FPL points ARE integers (every scoring term in this module is an int
        constant or an integer-divided count), so the per-sim totals need no
        binning: the histogram is the exact distribution, not an approximation
        of it. It is stored sparse ({points: count}, only realised values) --
        ~30 keys x ~610 players is nothing next to the artifact it rides in
        (spec 2026-08-26, D2).

        Zero-padded on exactly the same convention as mean() and tail_mean():
        a sim the player did not feature in contributes a 0, so the counts
        always sum to `sims` and the histogram's own mean reconstructs
        mean(name). Reconstructability is the point -- every derived statistic
        downstream (p10/median/mode/p90/p_haul/p_blank) reads this dict rather
        than the per-sim series, so the dict must be the whole truth about the
        player's week.

        The accumulated totals are floats only because the bucket sums start
        at 0.0; round-to-int is exact for the values that can actually land
        there, and is what keys the dict on the integer scale the reader sees.
        """
        if not self.sims:
            return {}
        hist: dict = {}
        appeared = 0
        for pts in self._per_sim.get(name, {}).values():
            key = int(round(pts))
            hist[key] = hist.get(key, 0) + 1
            appeared += 1
        missing = self.sims - appeared
        if missing:
            hist[0] = hist.get(0, 0) + missing
        return hist

    def tail_mean(self, name: str, q: float = 0.85) -> float:
        """Mean of the top (1 - q) fraction of the zero-padded per-sim totals.

        Smooth in appearance probability (unlike a percentile over a discrete
        goal count) because it averages, rather than reading off, the sims in
        the tail -- see the RETIRED ceiling_points note above for the
        motivating cliff. The statistic itself lives in module-level
        `_tail_mean`; this just supplies it the zero-padded distribution.
        """
        if not self.sims:
            return 0.0
        return _tail_mean(self._distribution(name), q)


def appearance_probability(sample) -> float:
    """P(played) for one player: sample.played / sample.sims.

    `sims` is incremented for every player on every sim BEFORE the on-pitch
    guard, so it is the total sim count. `played` only grows when the player
    was actually on the pitch. Their ratio is exactly the probability this
    player appears in a given sim.

    This exists because saves_points, conceded_points, defcon_points and
    BonusAccumulator.expected are all CONDITIONAL expectations -- E[x |
    played] -- computed over lists/counters (save_samples, defcon_samples,
    sample.played itself, BonusAccumulator._sims) that only accumulate on
    sims where the player appeared. expected_points(means), by contrast, is
    UNCONDITIONAL: engine_events.event_means divides by ps.sims. Adding a
    conditional expectation straight to an unconditional one silently assumes
    P(played) == 1 for every player. Multiplying the conditional component by
    this probability converts it to E[x | played] * P(played) == E[x], the
    correct unconditional contribution -- and is a no-op for any player who
    appears in every sim, which is exactly the case every prior fixture in
    this suite tested.
    """
    sims = getattr(sample, "sims", 0)
    if not sims:
        return 0.0
    return getattr(sample, "played", 0.0) / sims


def total_points(means: dict, sample, conceded_samples: list,
                 bonus: float = 0.0) -> float:
    """Full expected FPL points for one player.

    `means` comes from engine_events.event_means; `sample` is the PlayerSample
    carrying per-sim threshold counts. Bonus is supplied by BonusAccumulator.

    saves_points, conceded_points, defcon_points and `bonus` are all
    conditional on having played (see appearance_probability's docstring for
    why), so each is scaled by P(played) before being added to the
    unconditional expected_points(means) -- otherwise a player who starts one
    game in five gets paid as if he started every game.
    """
    p_played = appearance_probability(sample)
    conditional = (
        saves_points(getattr(sample, "save_samples", []))
        + conceded_points(means["position"], conceded_samples)
        + defcon_points(means["position"], getattr(sample, "defcon_samples", []))
        + bonus
    )
    return expected_points(means) + conditional * p_played


# RETIRED 2026-07-30: ceiling_points(means, sample, conceded_samples, bonus, q) and
# its helper _unconditional_goal_samples(sample) used to swap the mean-goal
# contribution for the UNCONDITIONAL 85th percentile of a player's simulated goal
# COUNT. Measured cliff (goal_share 0.35, 40k sims):
#
#     P(play) 1.00-0.61 -> p85(goals) = 1.0, ceiling/xPts 1.84-2.72
#     P(play) 0.50-0.20 -> p85(goals) = 0.0, ceiling/xPts = 1.00 exactly
#
# A percentile over a DISCRETE count is a step function, so above ~55%
# appearance probability every player's ceiling sat in a narrow band and below
# it the ceiling collapsed onto xPts with no signal -- useless as a ranking
# column. Replaced by SimPointsAccumulator.tail_mean: the mean of simulated
# TOTAL points across the top (1-q) fraction of sims, which is smooth over
# discrete outcomes because it averages the tail rather than reading off a
# single order statistic of it. Confirmed nothing outside this module and its
# tests called either retired function before deleting them.


# --- run path -------------------------------------------------------------

def gameweek_odds(gameweek: int, rows: list, refresh: bool = False,
                  fetch=None) -> dict:
    """The odds dict for one gameweek, with the strength-table upgrade.

    Precedence (spec D6 / phase 5 task 4):
      1. This gameweek's own REAL market lines (cached or freshly fetched)
         always win — they are prices, not estimates.
      2. Entries that are absent or fdr-prior-sourced are re-priced from
         core.fpl_strength once >= 2 gameweeks of real market data exist,
         stamped `source: "strength_table_v1"`.
      3. With less accumulated data than that, the FDR-prior cache stays as
         the zero-data fallback, exactly as before this module existed.

    `fetch` is injectable for the tests (default core.fpl_odds.fetch_gw_odds,
    the only network in this path); the upgrade itself never overwrites the
    on-disk cache — the cache keeps recording what each source actually said.
    """
    from core import fpl_odds, fpl_strength

    fetch = fetch or fpl_odds.fetch_gw_odds
    odds = None if refresh else fpl_odds.read_cached(gameweek)
    if odds is None:
        try:
            odds = fetch(gameweek, rows)
        except Exception as exc:  # network down / feed shape change
            print(f"  [fpl] WARNING: odds fetch failed ({exc}) -- "
                  "running on flat prior lambdas")
            odds = {"matches": {}}

    matches = odds.get("matches") or {}

    def needs_upgrade(m):
        return (m is None or m.get("lam_home") is None
                or str(m.get("source") or "").startswith("fdr_prior"))

    if not any(needs_upgrade(matches.get(r["match_id"])) for r in rows):
        return odds                       # fully market-priced: hands off
    if fpl_strength.real_gw_count(gameweek) < 2:
        return odds                       # not enough data: FDR fallback

    strength = fpl_strength.table(gameweek)
    upgraded = dict(odds)
    upgraded["matches"] = dict(matches)
    repriced = 0
    for r in rows:
        m = matches.get(r["match_id"])
        if not needs_upgrade(m):
            continue
        lam_home, lam_away = fpl_strength.future_lambdas(r["home"], r["away"],
                                                         strength)
        upgraded["matches"][r["match_id"]] = {
            "home": r["home"], "away": r["away"],
            "lam_home": round(lam_home, 3), "lam_away": round(lam_away, 3),
            "source": "strength_table_v1",
        }
        repriced += 1
    if repriced:
        print(f"  [fpl] strength table v1 priced {repriced} fixture(s) from "
              f"accumulated market data (FDR prior superseded)")
    return upgraded


def load_gameweek(gameweek: int, refresh: bool = False):
    """Load FPL data, register the gameweek's fixtures and deadline, build priors.

    Returns (priors_by_team, players_by_name, cold_start_flags).
    """
    from core import fixtures, fpl_api, fpl_priors

    boot = fpl_api.read_cache("bootstrap")
    raw_fx = fpl_api.read_cache("fixtures")
    if refresh or boot is None or raw_fx is None:
        boot, raw_fx = fpl_api.refresh()

    teams = fpl_api.parse_teams(boot)
    events = fpl_api.parse_events(boot)
    players = fpl_api.parse_players(boot)

    # DefCon backfill: bootstrap-static zeroes defensive_contribution for every
    # player preseason, so without this the DefCon model (and the order book's
    # `dfc` column) is uniformly zero. See core.fpl_api.fetch_defcon_backfill.
    # Incrementally cached to data/fpl/ -- only the first run pays the ~400-call
    # cost; every run after that is instant.
    defcon_backfill = fpl_api.fetch_defcon_backfill(players)

    # Register this gameweek's fixtures with the shared schedule.
    rows = [r for r in fpl_api.parse_fixtures(raw_fx, teams)
            if r["fantasy_round"] == gameweek]
    existing = {f.match_id for f in fixtures.SCHEDULE}
    for r in rows:
        if r["match_id"] in existing:
            continue
        fixtures.SCHEDULE.append(fixtures.Fixture(
            match_id=r["match_id"], home=r["home"], away=r["away"],
            kickoff=fpl_api._parse_utc(r["kickoff_utc"]),
            stage="GW", fantasy_round=r["fantasy_round"], neutral=False,
        ))
    if gameweek in events:
        fixtures.set_deadline(gameweek, events[gameweek]["deadline"])

    # Market lambdas: without this every fixture simulates at league-average
    # strength (ARS v COV == NEW v LIV), so the order book carries no fixture
    # signal at all. Cached per GW; --refresh re-captures the current lines.
    # Absent/fdr-sourced entries are re-priced from the strength table once
    # >=2 real gameweeks of market data exist (see gameweek_odds).
    odds = gameweek_odds(gameweek, rows, refresh=refresh)
    priced, unpriced = 0, []
    for f in fixtures.SCHEDULE:
        if f.stage != "GW" or f.fantasy_round != gameweek:
            continue
        m = (odds.get("matches") or {}).get(f.match_id)
        if m and m.get("lam_home") is not None:
            f.lam_home, f.lam_away = m["lam_home"], m["lam_away"]
            priced += 1
        else:
            unpriced.append(f"{f.home} v {f.away}")
    if unpriced:
        print(f"  [fpl] WARNING: {len(unpriced)} fixture(s) without market "
              f"odds, on flat prior lambdas: {', '.join(unpriced)}")
    if priced:
        print(f"  [fpl] market lambdas applied to {priced} fixture(s) "
              f"(odds captured {odds.get('captured_at', 'unknown')})")

    # team_matches: how many matches THIS SEASON's live sample covers. Preseason
    # the feed carried last season's totals and 38 was right; the moment the
    # season rolled over, `starts` and `minutes` reset and 38 became a divisor
    # that crushed every start probability to a few percent (2026-08-27: zero
    # forwards cleared the 0.75 minutes floor, and the order book silently
    # ranked players by whether they had a research note). It is now the count
    # of FINISHED gameweeks, and fpl_priors blends the preseason snapshot in by
    # minutes so August still leans on last season.
    team_matches = sum(1 for e in events.values() if e.get("finished")) or 0
    priors_by_team, flags = fpl_priors.build_with_flags(
        players, team_matches, defcon_backfill=defcon_backfill)
    return priors_by_team, {p["name"]: p for p in players}, flags


# The seed engine_events.simulate_round defaults to. Kept as an explicit local
# constant (rather than relying on the default) so it can participate in the
# cache key -- a silent change to that default would otherwise change every
# player's numbers without changing the key.
_SEED = 12345

# PlayerPrior fields that feed the sim, in a fixed order so the cache key's
# projection is stable regardless of dataclass field order.
_PRIOR_FIELDS = ("start_prob", "exp_minutes", "goal_share", "assist_share",
                 "sot_per90", "pen_taker", "defcon_per90", "saves_per90")


def _priors_projection(priors_by_team: dict) -> dict:
    """{player_name: tuple of every PlayerPrior field that affects the sim}.

    Keyed by name (not team) because that is how the sim and the row output are
    keyed; a player changing team would already show up via a different squad
    list membership, and this dict does not need to duplicate that.
    """
    out = {}
    for squad in priors_by_team.values():
        for p in squad:
            out[p.name] = tuple(getattr(p, f) for f in _PRIOR_FIELDS)
    return out


def _bps_baselines(players_by_name: dict) -> dict:
    """{player_name: realized BPS per 90}, the input to BonusAccumulator.

    Prorated by minutes exactly as `run` computes it -- see the loop below. This
    lives here (not just inline in build_rows) so the exact same computation
    backs both the simulation input and the cache-key projection: baselines are
    NOT passed to cache_key as a separate argument, they are folded into the
    `priors` projection (see build_rows), because they are derived from
    players_by_name and change sim output just as much as PlayerPrior fields do.
    """
    baselines = {}
    for name, p in players_by_name.items():
        minutes = p.get("minutes") or 0
        if minutes > 0:
            baselines[name] = (p.get("bps") or 0) * 90.0 / minutes
    return baselines


def match_summaries(match_samples: dict, fx: list) -> list:
    """One JSON-safe dict per fixture: scoreline distribution, 1X2, clean sheets.

    Derived here rather than in the site layer because MatchSample objects do not
    survive a JSON round trip, and spec §6 requires the cached artifact to carry
    the per-match distribution — so the derivation must happen before the store.

    Deliberately NOT evmax.articles.match_predictions: that function emits
    p_advance_home/p_advance_away for any round >= 4 (World Cup knockout), which
    for gameweek 4 of a league season would publish a survival probability for a
    tie that does not exist.

    `market` records whether the fixture's lambdas came from the odds feed or fell
    back to ratings priors, so the ticker can label each column's provenance
    instead of presenting a uniform confidence it does not have (spec §8).
    """
    out = []
    for f in fx:
        ms = match_samples.get(f.match_id)
        if ms is not None and ms.sims > 0:
            probs = ms.outcome_probs()
            p_home = probs.get("H", 0.0)
            p_draw = probs.get("D", 0.0)
            p_away = probs.get("A", 0.0)
            best_sl = max(ms.scorelines, key=lambda k: ms.scorelines[k])
            mh, ma = ms.marginal_home(), ms.marginal_away()
            exp_h = sum(g * p for g, p in mh.items())
            exp_a = sum(g * p for g, p in ma.items())
            # A team keeps a clean sheet iff the OPPONENT scores zero.
            p_cs_home, p_cs_away = ma.get(0, 0.0), mh.get(0, 0.0)
        else:
            # No sample for this fixture (a blank, or a match the engine skipped).
            p_home = p_draw = p_away = 0.0
            best_sl = (0, 0)
            exp_h = exp_a = p_cs_home = p_cs_away = 0.0

        total_p = p_home + p_draw + p_away
        if total_p > 0:
            p_home, p_draw, p_away = (p_home / total_p, p_draw / total_p,
                                      p_away / total_p)

        out.append({
            "match_id": f.match_id,
            "home": f.home,
            "away": f.away,
            "kickoff": f.kickoff.isoformat(),
            "exp_home_goals": round(exp_h, 2),
            "exp_away_goals": round(exp_a, 2),
            "exp_total": round(exp_h + exp_a, 2),
            "top_scoreline": f"{best_sl[0]}-{best_sl[1]}",
            "p_home": round(p_home, 3),
            "p_draw": round(p_draw, 3),
            "p_away": round(p_away, 3),
            "p_cs_home": round(p_cs_home, 3),
            "p_cs_away": round(p_cs_away, 3),
            "market": f.lam_home is not None and f.lam_away is not None,
        })
    out.sort(key=lambda m: m["kickoff"])
    return out


def _kickoffs_by_team(fx: list) -> dict:
    """{team: EARLIEST kickoff ISO string} for the gameweek.

    Earliest, not only, because a double-gameweek team has two. The captains
    article orders by the first fixture — that is the one a manager's captain
    decision is locked against.
    """
    out: dict = {}
    for f in fx:
        iso = f.kickoff.isoformat()
        for team in (f.home, f.away):
            if team not in out or iso < out[team]:
                out[team] = iso
    return out


def _match_projection(fx: list) -> dict:
    """{match_id: {"lambdas", "kickoff"}} — the cache key's match layer.

    Kickoff is part of the projection because the cached artifact SERVES it:
    every row's kickoff column and every match summary carry it. A fixture
    re-slotted for TV with unchanged odds must therefore miss the cache and
    re-derive, not hit and republish the stale kickoff (review 2026-08-19,
    finding 2).
    """
    return {f.match_id: {"lambdas": f.lambdas(),
                         "kickoff": f.kickoff.isoformat()}
            for f in fx}


# --- PMF statistics ---------------------------------------------------------
# Standalone list/dict-in, number-out functions (mirroring _tail_mean) so each
# statistic can be unit-tested against a hand-built PMF with a known answer,
# independent of the simulation that normally produces one.

HAUL_THRESHOLD = 10        # "a haul" in the FPL vernacular: a double-figure week
BLANK_THRESHOLD = 2        # a blank: a bare appearance or worse


def _pmf_percentile(pmf: dict, q: float) -> int:
    """Smallest integer points value whose cumulative probability is >= q.

    The LOWER-BOUND convention (rather than interpolating between adjacent
    values) is deliberate: FPL points are integers, and "your floor is 2.4
    points" is a number no reader can ever score. Interpolation would also
    smear across the appearance cliff — the huge atom of probability sitting
    at 0 for a rotation risk is the single most important feature of these
    distributions, and a floor of "0" states it where a floor of "1.3" hides
    it.

    Empty PMF -> 0, matching mean()'s zero for a player with no mass at all.
    """
    total = sum(pmf.values())
    if not total:
        return 0
    target = q * total
    cumulative = 0
    for pts in sorted(pmf):
        cumulative += pmf[pts]
        if cumulative >= target:
            return int(pts)
    return int(max(pmf))


def _pmf_mode(pmf: dict) -> int:
    """The most likely single score. Ties break to the LOWEST value.

    Ties are common and not a rounding artefact: a rotation risk can carry
    equal mass on 0 and on a 2-point appearance. Breaking low is the
    conservative read (and makes the statistic deterministic, which the
    byte-identical rebuild contract requires — dict iteration order must
    never decide a published number).
    """
    if not pmf:
        return 0
    best = max(pmf.values())
    return int(min(pts for pts, n in pmf.items() if n == best))


def _pmf_tail_prob(pmf: dict, threshold: int) -> float:
    """P(points >= threshold) — INCLUSIVE. A 10-point week IS a haul."""
    total = sum(pmf.values())
    if not total:
        return 0.0
    return sum(n for pts, n in pmf.items() if pts >= threshold) / float(total)


def _pmf_head_prob(pmf: dict, threshold: int) -> float:
    """P(points <= threshold) — INCLUSIVE. A 2-point week IS a blank."""
    total = sum(pmf.values())
    if not total:
        return 0.0
    return sum(n for pts, n in pmf.items() if pts <= threshold) / float(total)


def distribution_stats(pmf: dict) -> dict:
    """{p10, median, p90, mode, p_haul, p_blank} for one player's PMF.

    Probabilities round to 4dp (the same "Monte-Carlo noise is not
    information" rule _derive_row applies to the points columns — at 50k sims
    the standard error on a probability is ~0.002, so a fifth decimal is
    noise); percentiles and the mode stay ints because points are ints.
    """
    return {
        "p10": _pmf_percentile(pmf, 0.10),
        "median": _pmf_percentile(pmf, 0.50),
        "p90": _pmf_percentile(pmf, 0.90),
        "mode": _pmf_mode(pmf),
        "p_haul": round(_pmf_tail_prob(pmf, HAUL_THRESHOLD), 4),
        "p_blank": round(_pmf_head_prob(pmf, BLANK_THRESHOLD), 4),
    }


def _derive_row(*, name: str, means: dict, x_points: float, ceiling: float,
                bonus: float, defcon_pts: float, p_defcon: float,
                price, ownership, kickoff, distribution: dict | None = None) -> dict:
    """One order-book row with every column the six articles consume.

    Kept as a standalone pure function (rather than an inline dict literal in
    build_rows) so the derived columns can be unit-tested against hand-computed
    inputs without running a simulation.

    UNIT WARNING — the columns mix two denominators. x_points (and therefore
    captain_ev, value and ceiling) is a per-WEEK total: SimPointsAccumulator
    sums a player's matches within each sim, so a double-gameweek player's
    figure covers both fixtures. bonus, defcon, p_defcon and cs_points are
    per-MATCH quantities: they come off event_means / per-match accumulators
    whose divisor increments once per APPEARANCE (see the RETIRED total_points
    note and TestDoubleGameweekTotalPoints), so for a doubled player they are
    single-match averages and do NOT sum to x_points. Prose that frames them
    as components of the weekly total must render only for a single-fixture
    player (evmax.writer guards this on the row's stamped fixture count).
    TODO(pre-first-DGW): rework these columns per-sim so every column shares
    the per-week denominator (review 2026-08-19, finding 7 — the minimum fix
    is this documentation plus the prose guard).

    The distribution columns land on the RIGHT side of that split.
    `distribution` and its six derived statistics — p10, median, p90, mode,
    p_haul, p_blank — all read SimPointsAccumulator.histogram, which (like
    mean/tail_mean, and unlike bonus/defcon/cs_points) sums a player's matches
    within each sim. They are per-WEEK quantities, on the same denominator as
    x_points, captain_ev, value and ceiling: a double-gameweek player's p90 is
    his best week, not his best match. Any prose framing them alongside the
    per-match columns must say which is which.

    They are also OPTIONAL — the whole distribution block is present only when
    a `distribution` is supplied. An artifact written before histograms existed
    degrades to a row without them rather than to a row that fabricates a floor
    of zero, and every consumer keys on their absence to decide whether to draw
    the chart at all.

    Rounding happens HERE and only here: these rows are what the cache stores and
    what the public JSON feed serves, and 14 significant figures of Monte-Carlo
    noise is not information.
    """
    pos = means["position"]
    row = {
        "name": name,
        "team": means["team"],
        "position": pos,
        "x_points": round(x_points, 2),
        "captain_ev": round(2 * x_points, 2),
        "ceiling": round(ceiling, 2),
        "price": price,
        "ownership_pct": ownership,
        "value": round(x_points / price, 3) if price else None,
        "bonus": round(bonus, 2),
        # Points and probability are the same quantity in two units
        # (points == 2 x probability). The DefCon article headlines the
        # probability; the tables print the points. Emitting both keeps every
        # surface reading the same number.
        "defcon": round(defcon_pts, 2),
        "p_defcon": round(p_defcon, 3),
        "cs_points": round(means.get("clean_sheet", 0.0) * CS_PTS.get(pos, 0), 2),
        "kickoff": kickoff,
    }
    if distribution is not None:
        row["distribution"] = distribution
        row.update(distribution_stats(distribution))
    return row


def _int_keyed_distributions(rows: list) -> list:
    """Restore `distribution`'s INT keys on rows that came back from the cache.

    The simcache is JSON, and JSON object keys are strings — so the histogram
    `{5: 61}` that build_artifact stored reads back as `{"5": 61}`. Every
    consumer (the derived percentiles, the card's chart, the article's
    convolution) does integer arithmetic on those keys, so the cache-hit path
    and the fresh-simulation path must hand out the SAME type or a cached
    gameweek would silently take a different code path from a freshly
    simulated one. Normalising on read (rather than making every consumer
    tolerate both) keeps that contract in one place.
    """
    out = []
    for r in rows:
        dist = r.get("distribution")
        if isinstance(dist, dict):
            r = dict(r, distribution={int(k): v for k, v in dist.items()})
        out.append(r)
    return out


def build_artifact(priors_by_team: dict, players_by_name: dict, gameweek: int,
                   sims: int, use_cache: bool = True) -> tuple:
    """Simulate (or fetch from cache); return ({"rows", "matches"}, cache_hit).

    Consults core.simcache before running the Monte Carlo: the cache key covers
    every input that determines the derived rows (see the `priors`, `research`,
    match (lambdas + kickoffs) and `config` projections below) plus a fingerprint of this file and
    the shared engine's source, so an edit to a scoring constant can never
    silently serve a stale artifact. `use_cache=False` always simulates, for an
    operator who wants to force a fresh run regardless of the cache.

    cache_hit is the second return value so the build preflight can tell an
    expected first-build miss from an unexpected one (spec §9).
    """
    import config
    from core import fixtures, research, simcache

    # GW-stage only: the shared SCHEDULE also carries World Cup fixtures whose
    # fantasy_round numbers collide with FPL gameweeks (WC round 1 == GW1).
    # The engine still simulates everything registered for the round number —
    # that is its contract and the rng stream depends on it — but the FPL
    # artifact's match layer, kickoffs and cache-key lambdas are GW business
    # only; without this filter the ticker would publish 48 national teams.
    fx = [f for f in fixtures.by_round(gameweek) if f.stage == "GW"]
    match_projection = _match_projection(fx)
    research_entries = research.load_entries("players", gameweek)
    research_projection = {
        name: (e.status, e.start_prob_override, e.lambda_multiplier)
        for name, e in research_entries.items()
    }
    priors_projection = {
        "players": _priors_projection(priors_by_team),
        # Folded in here rather than as a separate cache_key argument: BPS
        # baselines derive from players_by_name and affect BonusAccumulator's
        # output just as much as any PlayerPrior field, so they must be part of
        # whatever gets hashed as "priors" or a bps/minutes edit could silently
        # serve a stale bonus-points figure.
        "bps_baselines": _bps_baselines(players_by_name),
    }
    research_weight = config.weight("fpl")
    sim_config = {
        "GOAL_CONCENTRATION": config.GOAL_CONCENTRATION,
        "PEN_TAKER_GOAL_BONUS": config.PEN_TAKER_GOAL_BONUS,
        "DEVIG_METHOD": config.DEVIG_METHOD,
        # Not in the plan's literal list of three dials, but it plainly is one:
        # research_weight (w) is fed straight into effective_goal_weight's blend
        # and into ResearchEntry.adjust's soft lambda nudge, so retuning it in
        # config.py changes simulated output exactly like GOAL_CONCENTRATION
        # does. Leaving it out would mean a config edit could silently serve a
        # stale artifact -- the one failure mode this cache exists to prevent.
        "research_weight": research_weight,
    }

    key = simcache.cache_key(
        gameweek=gameweek, sims=sims, seed=_SEED, lambdas=match_projection,
        priors=priors_projection, research=research_projection,
        config=sim_config,
    )

    if use_cache:
        cached = simcache.load(key)
        if cached is not None:
            # .get("matches", []): artifacts written before the match layer
            # existed have no matches key. They cannot actually be served — the
            # source fingerprint covers this file, so the edit that added the
            # layer invalidated all of them — but the .get costs nothing and
            # means a hand-copied artifact degrades rather than crashing.
            return {"rows": _int_keyed_distributions(cached["rows"]),
                    "matches": cached.get("matches", [])}, True

    baselines = _bps_baselines(players_by_name)
    bonus = BonusAccumulator(baselines)
    points = SimPointsAccumulator(baselines, sims)

    def _hook(match_id: str, rows: list, sim_index: int) -> None:
        bonus.observe(match_id, rows, sim_index)
        points.observe(match_id, rows, sim_index)

    samples, match_samples = engine_events.simulate_round(
        gameweek, sims=sims, seed=_SEED,
        priors=lambda team: priors_by_team.get(team, []),
        research=research_entries,
        research_weight=research_weight,
        per_match_hook=_hook,
    )
    means = engine_events.event_means(samples)

    kickoffs = _kickoffs_by_team(fx)
    rows = []
    for name, ps in samples.items():
        m = means[name]
        player_bonus = bonus.expected(name)
        # x_points comes from the per-sim distribution, NOT the older
        # total_points assembly: for a double-gameweek player the assembly path
        # is a per-MATCH average — half the week's total (settled 2026-08-19,
        # see BonusAccumulator.expected's docstring and
        # tests/test_fpl_model.TestDoubleGameweekTotalPoints) — while
        # SimPointsAccumulator.mean sums a player's matches within each sim.
        pts = points.mean(name)
        p_played = appearance_probability(ps)
        meta = players_by_name.get(name, {})
        # Scaled by P(played): the raw threshold probability is conditional on
        # appearing, which would show a rotation player as if he started every
        # week. See appearance_probability's docstring.
        p_defcon = defcon_probability(m["position"], ps.defcon_samples) * p_played
        rows.append(_derive_row(
            name=name, means=m, x_points=pts, ceiling=points.tail_mean(name),
            bonus=player_bonus, defcon_pts=p_defcon * DEFCON_PTS,
            p_defcon=p_defcon, price=meta.get("price"),
            ownership=meta.get("ownership"),
            kickoff=kickoffs.get(m["team"]),
            # The full PMF rides INSIDE the cached artifact rather than being
            # recomputed on read: the simcache key fingerprints this file's
            # source, so adding the column invalidated every artifact written
            # before it existed — a stale hit cannot serve a row that silently
            # lacks a distribution.
            distribution=points.histogram(name)))
    rows.sort(key=lambda r: -r["x_points"])

    artifact = {"rows": rows, "matches": match_summaries(match_samples, fx)}
    if use_cache:
        simcache.store(key, artifact, meta={"gameweek": gameweek, "sims": sims})
    return artifact, False


def build_rows(priors_by_team: dict, players_by_name: dict, gameweek: int,
              sims: int, use_cache: bool = True) -> list:
    """The order-book rows alone — `run()`'s view of build_artifact.

    Kept so the CLI order book and its tests do not have to care about the match
    layer, which only the site consumes.
    """
    artifact, _hit = build_artifact(priors_by_team, players_by_name, gameweek,
                                    sims, use_cache=use_cache)
    return artifact["rows"]


def run(state: dict, fantasy_round: int, sims: int = 50_000) -> None:
    """Print the FPL order book for one gameweek."""
    priors_by_team, players_by_name, flags = load_gameweek(fantasy_round)
    if flags:
        print(f"  [fpl] {len(flags)} player(s) on the price-based cold-start prior "
              f"(no PL history): "
              f"{', '.join(f['name'] for f in flags[:6])}"
              f"{' ...' if len(flags) > 6 else ''}")

    use_cache = not state.get("no_cache", False)
    rows = build_rows(priors_by_team, players_by_name, fantasy_round, sims,
                      use_cache=use_cache)

    print(f"\n=== FPL — gameweek {fantasy_round} order book ===")
    print(f"\n{'xPts':>6} {'ceil':>6} {'bon':>5} {'dfc':>5}  "
          f"{'player':<20} {'team':<5} pos  price")
    for r in rows[:30]:
        price = f"{r['price']:.1f}" if r["price"] else "  - "
        print(f"{r['x_points']:6.2f} {r['ceiling']:6.2f} {r['bonus']:5.2f} "
              f"{r['defcon']:5.2f}  {r['name']:<20} {r['team']:<5} "
              f"{r['position']:<4} {price}")

    if state.get("squad") and not state["squad"][0].get("_example"):
        _print_squad_view(state, {r["name"]: r for r in rows})
    else:
        print("\n  [fpl] state.json not populated — add your 15 to see the squad view.")


def _conceded_series(sample) -> list:
    """Per-sim conceded counts for the -1-per-2 threshold.

    The engine accumulates `conceded` as a total rather than a list (goals conceded
    is a team-level quantity, so keeping 50k per-player copies would waste memory).
    Reconstruct a two-point series around the mean, which preserves the threshold's
    convexity better than applying the divisor to the mean alone.

    Design choice: `sample.conceded / sample.played` is deliberate, not
    `/ sample.sims`. save_samples and defcon_samples are also collected only on
    sims where the player was on the pitch (appended after the on-pitch guard),
    so they are already E[x | played] -- this series matches that convention
    exactly, and total_points scales conceded_points' result by
    appearance_probability(sample) afterward, identically to saves and DefCon.
    Centring on `conceded / sims` instead would make this series unconditional
    already, and it would then need to be the ONE component NOT scaled --
    correct in principle, but a special case that is easy to get wrong later.
    Keeping every conditional component conditional, and applying one uniform
    scaling step in total_points, is the same amount of correctness with one
    fewer way to reintroduce this bug.
    """
    if not sample.played:
        return []
    mean = sample.conceded / sample.played
    lo, hi = int(mean), int(mean) + 1
    frac = mean - lo
    return [lo] * max(1, int(round((1 - frac) * 100))) + [hi] * max(0, int(round(frac * 100)))


def _print_squad_view(state: dict, by_name: dict) -> None:
    print("\nYour squad:")
    total = 0.0
    for p in state["squad"]:
        r = by_name.get(p["name"])
        xp = r["x_points"] if r else 0.0
        tag = " (B)" if not p.get("is_starter") else ""
        if p.get("is_starter"):
            total += xp
        flag = "" if r else "  <- not modelled (name mismatch?)"
        print(f"  {xp:6.2f}  {p['name']:<20} {p.get('team', ''):<5}"
              f"{p.get('position', ''):<4}{tag}{flag}")
    print(f"\n  projected XI total: {total:.1f}")
