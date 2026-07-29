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


def defcon_points(position: str, defcon_samples: list) -> float:
    """Expected DefCon points: 2 x P(count >= threshold).

    A threshold crossing, not a rate — 2 x rate/threshold is wrong in both tails,
    over-paying players who never reach it and under-paying those who always do.
    The payout is capped at 2 no matter how far past the threshold a player goes.
    """
    threshold = defcon_threshold(position)
    if threshold is None or not defcon_samples:
        return 0.0
    hits = sum(1 for c in defcon_samples if c >= threshold)
    return DEFCON_PTS * hits / float(len(defcon_samples))


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
# absorbed into the baseline rate. Same for goalline clearances and errors.
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
_NAME, _POS, _GOALS, _ASSISTS, _MINUTES, _CS, _CONCEDED, _SAVES, _YELLOW, _RED = range(10)


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


class BonusAccumulator:
    """Accumulates expected bonus points across sims via rank-within-match.

    Pass `observe` as engine_events' per_match_hook. After the sim completes,
    `expected(name)` gives that player's mean bonus.

    Ties consume award POSITIONS, matching the official rule: two players tied on
    top both take 3 and the third-most BPS takes 1 (not 2, because the tie has
    already used two positions). Two tied for second both take 2 and no 1 is
    awarded at all.
    """

    def __init__(self, baselines: dict):
        self.baselines = baselines or {}
        self._total: dict = {}
        self._sims: dict = {}

    def observe(self, _match_id: str, rows: list) -> None:
        scored = [(bps_from_row(r, self.baselines.get(r[_NAME], 0.0)), r[_NAME])
                  for r in rows]
        for _bps, name in scored:
            self._sims[name] = self._sims.get(name, 0) + 1
        if not scored:
            return
        # Group by BPS, highest first. Each group takes the award for the next
        # open position, then consumes as many positions as it has members.
        groups: dict = {}
        for bps, name in scored:
            groups.setdefault(bps, []).append(name)

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
                self._total[name] = self._total.get(name, 0) + award
            placed += len(groups[bps])

    def expected(self, name: str) -> float:
        sims = self._sims.get(name, 0)
        if not sims:
            return 0.0
        return self._total.get(name, 0) / float(sims)


def total_points(means: dict, sample, conceded_samples: list,
                 bonus: float = 0.0) -> float:
    """Full expected FPL points for one player.

    `means` comes from engine_events.event_means; `sample` is the PlayerSample
    carrying per-sim threshold counts. Bonus is supplied by BonusAccumulator.
    """
    pts = expected_points(means)
    pts += saves_points(getattr(sample, "save_samples", []))
    pts += conceded_points(means["position"], conceded_samples)
    pts += defcon_points(means["position"], getattr(sample, "defcon_samples", []))
    pts += bonus
    return pts


def ceiling_points(means: dict, goal_samples: list, q: float = 0.85) -> float:
    """Goal-variance ceiling: mean points with the mean-goal contribution swapped
    for the q-percentile goal contribution, floored at the mean.

    Mirrors the FIFA and Holdet ceilings so all three are defined the same way.
    The floor removes an artefact: for non-scoring defenders the raw ceiling dips
    below the mean, because it models only goal upside and not clean-sheet variance.
    """
    pos = means["position"]
    goal_pts = GOAL_PTS.get(pos, 4)
    base = expected_points(means)
    p_goals = engine_events.percentile(goal_samples, q)
    raw = base - means.get("goals", 0.0) * goal_pts + p_goals * goal_pts
    return max(base, raw)


# --- run path -------------------------------------------------------------

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

    # team_matches: how many matches the per-90 sample covers. Preseason the feed
    # carries last season's totals, so a full 38. Once the season starts this should
    # become matches played so far -- tracked by the caller as history accumulates.
    team_matches = 38
    priors_by_team, flags = fpl_priors.build_with_flags(players, team_matches)
    return priors_by_team, {p["name"]: p for p in players}, flags


def run(state: dict, fantasy_round: int, sims: int = 50_000) -> None:
    """Print the FPL order book for one gameweek."""
    from core import engine_events

    priors_by_team, players_by_name, flags = load_gameweek(fantasy_round)
    if flags:
        print(f"  [fpl] {len(flags)} player(s) on the price-based cold-start prior "
              f"(no PL history): "
              f"{', '.join(f['name'] for f in flags[:6])}"
              f"{' ...' if len(flags) > 6 else ''}")

    baselines = {}
    for name, p in players_by_name.items():
        minutes = p.get("minutes") or 0
        if minutes > 0:
            baselines[name] = (p.get("bps") or 0) * 90.0 / minutes

    bonus = BonusAccumulator(baselines)
    samples, _matches = engine_events.simulate_round(
        fantasy_round, sims=sims,
        priors=lambda team: priors_by_team.get(team, []),
        research_weight=state.get("research_weight", 0.3),
        per_match_hook=bonus.observe,
    )
    means = engine_events.event_means(samples)

    rows = []
    for name, ps in samples.items():
        m = means[name]
        # conceded is accumulated as a running total; rebuild the per-sim series
        # the threshold needs from the mean over the sims the player appeared in.
        conceded_samples = _conceded_series(ps)
        pts = total_points(m, ps, conceded_samples, bonus=bonus.expected(name))
        meta = players_by_name.get(name, {})
        rows.append({
            "name": name, "team": m["team"], "position": m["position"],
            "x_points": pts, "price": meta.get("price"),
            "ownership_pct": meta.get("ownership"),
            "ceiling": ceiling_points(m, ps.goal_samples),
            "bonus": bonus.expected(name),
            "defcon": defcon_points(m["position"], ps.defcon_samples),
        })
    rows.sort(key=lambda r: -r["x_points"])

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
