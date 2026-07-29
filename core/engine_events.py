"""Layer-1 Monte Carlo: the shared substrate for ALL five games.

For each match we draw a *correlated* set of per-player events from one underlying
pair of team-goal / opponent-goal draws, so that everything downstream (a striker's
goals, a defender's clean sheet, the exact scoreline) is consistent within a single
simulated universe. The same simulation batch can therefore feed:

  - FIFA / Holdet  (per-player goals, assists, SoT, CS, cards, minutes, MOTM)
  - Malspillet     (the literal (home_goals, away_goals) scoreline)

Design:
  * Per match, draw home_goals ~ Poisson(lam_home), away_goals ~ Poisson(lam_away).
    These shared team-goal totals are the correlation backbone -- a player's goal
    sample is conditioned on his team's total, and a defender's clean sheet is
    exactly "opponent total == 0" in the SAME draw.
  * Distribute each team's goals to its on-pitch players via goal_share priors
    (multinomial). Assists likewise, excluding the scorer where possible.
  * Minutes, cards, saves, MOTM drawn per-player.

Pure-Python + `random` so the scaffold runs with no third-party deps. Swap in numpy
later for speed if needed; the public API (`simulate_round`, `PlayerSample`) stays.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field

from . import fixtures, ratings


def _poisson(lam: float, rng: random.Random) -> int:
    """Knuth's Poisson sampler (fine for the small lambdas in football)."""
    if lam <= 0:
        return 0
    L = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= L:
            return k - 1


@dataclass
class PlayerSample:
    """One player's accumulated events across N sims (stored as running totals so a
    game can read means directly, plus per-sim arrays where distribution matters)."""

    name: str
    team: str
    position: str
    sims: int = 0
    goals: float = 0.0
    assists: float = 0.0
    sot: float = 0.0
    minutes: float = 0.0
    played: float = 0.0          # times appeared (minutes > 0)
    clean_sheet: float = 0.0
    conc_beyond: float = 0.0     # goals conceded beyond the first (DEF/GK), for -pts
    decisive_win: float = 0.0    # scored the winning goal (Holdet "scoring til sejr")
    decisive_draw: float = 0.0   # scored the equalising goal (Holdet "scoring til uafgjort")
    yellow: float = 0.0
    red: float = 0.0
    motm: float = 0.0
    saves: float = 0.0           # GK only
    goal_share: float = 0.0      # carried prior (role signal for downstream scoring)
    assist_share: float = 0.0
    # Per-sim goal tallies, for games that need the full distribution (e.g. captaincy
    # variance, hat-trick bonuses). Kept compact.
    goal_samples: list[int] = field(default_factory=list)
    # --- fields added for FPL. The engine samples RAW events; each game applies its
    # own rules to them. Zero/empty for World Cup games, which don't read them.
    conceded: float = 0.0            # raw goals conceded while on the pitch (GK/DEF).
                                     # conc_beyond is FIFA's max(0, ga-1); FPL needs
                                     # floor(ga/2), which that cannot express.
    played_60: float = 0.0           # times the player reached 60 minutes. FPL pays 1
                                     # point under 60 and 2 at 60+.
    save_samples: list[int] = field(default_factory=list)    # GK only.
                                     # E[floor(saves/3)] != floor(E[saves]/3).
    defcon_samples: list[int] = field(default_factory=list)  # DefCon is a threshold
                                     # crossing, so a mean count cannot give P(>= 10).

    def mean(self, attr: str) -> float:
        return getattr(self, attr) / self.sims if self.sims else 0.0


@dataclass
class MatchSample:
    """Distribution of scorelines for one match (for malspillet) plus team totals."""

    match_id: str
    home: str
    away: str
    sims: int = 0
    # scoreline counts: {(home_goals, away_goals): count}
    scorelines: dict = field(default_factory=lambda: defaultdict(int))

    def prob(self, hg: int, ag: int) -> float:
        return self.scorelines.get((hg, ag), 0) / self.sims if self.sims else 0.0

    def marginal_home(self) -> dict:
        d = defaultdict(int)
        for (hg, _ag), c in self.scorelines.items():
            d[hg] += c
        return {k: v / self.sims for k, v in d.items()}

    def marginal_away(self) -> dict:
        d = defaultdict(int)
        for (_hg, ag), c in self.scorelines.items():
            d[ag] += c
        return {k: v / self.sims for k, v in d.items()}

    def outcome_probs(self) -> dict:
        d = {"H": 0, "D": 0, "A": 0}
        for (hg, ag), c in self.scorelines.items():
            d["H" if hg > ag else "A" if ag > hg else "D"] += c
        return {k: v / self.sims for k, v in d.items()}


def _distribute(total_goals: int, players: list[ratings.PlayerPrior],
                on_pitch: dict[str, bool], rng: random.Random,
                weight_of: dict[str, float], gamma: float = 1.0) -> dict[str, int]:
    """Multinomial allocation of `total_goals` among on-pitch players by weight.

    Weights are shares of the team's goals. We only hold priors for *our* squad
    players, not the full national team, so the remaining share (1 - sum of known
    weights) is an "unmodeled teammates" sink: goals landing there are uncredited.
    Without it, a handful of known players would absorb 100% of the team's goals.

    `gamma` (>1) sharpens the split toward higher-share players while preserving the
    known players' *collective* mass (so team-level goals — and the leak — are
    unchanged; only the within-team distribution concentrates). gamma=1.0 = raw shares.
    """
    out: dict[str, int] = defaultdict(int)
    pool = [p for p in players if on_pitch.get(p.name)]
    weights = [max(weight_of.get(p.name, 0.0), 1e-6) for p in pool]
    wsum = sum(weights)
    if total_goals == 0 or not pool or wsum <= 0:
        return out
    if gamma != 1.0 and len(pool) > 1:
        sharp = [w ** gamma for w in weights]
        ssum = sum(sharp)
        if ssum > 0:
            weights = [s * (wsum / ssum) for s in sharp]  # renormalise to same wsum
    denom = max(wsum, 1.0)  # leak to unmodeled teammates when known shares < 1
    for _ in range(total_goals):
        r = rng.random() * denom
        acc = 0.0
        for p, w in zip(pool, weights):
            acc += w
            if r <= acc:
                out[p.name] += 1
                break
        # r beyond wsum -> goal to an unmodeled teammate, uncredited
    return out


def effective_goal_weight(prior_share: float | None, market_rate: float | None,
                          entry, w: float, base_start: float = 0.8) -> tuple[float, float]:
    """Combine market goal rate, prior share (expert fallback) and a research entry
    into one (goal_weight, start_prob), per the blend rules.

    - market present + prior present: linear blend (w=0 -> market, w=1 -> prior).
    - only one present: use it.
    - research entry then applies hard facts (absolute) + a soft lambda multiplier.
    Goal weight is a *relative* multinomial weight, not an absolute rate.
    """
    from . import blend
    if market_rate is not None and prior_share is not None:
        weight = blend.blend_rate(market_rate, expert=prior_share, w=w)
    elif market_rate is not None:
        weight = market_rate
    else:
        weight = prior_share or 0.0
    start = base_start
    if entry is not None:
        weight, start = entry.adjust(weight, start, w)
    return max(weight, 0.0), start


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile (q in [0,1]). Used for YOLO ceiling objective."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    idx = q * (len(s) - 1)
    lo = int(idx)
    frac = idx - lo
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + frac * (s[hi] - s[lo])


def simulate_round(fantasy_round: int, sims: int = 50_000, seed: int = 12345,
                   market_rates: dict | None = None, research: dict | None = None,
                   research_weight: float = 0.0, concentration: float | None = None,
                   priors=None):
    """Run the shared Monte Carlo for every fixture in a round.

    market_rates:    optional {player_name: goal_rate} from bookmaker player props.
    research:        optional {player_name: ResearchEntry} overrides.
    research_weight: the game's `w` dial (0 = pure odds, 1 = full expert overlay).
    concentration:   goal-split sharpening γ; None -> config.GOAL_CONCENTRATION.
    priors:          optional callable(team) -> [PlayerPrior]. Defaults to
                     ratings.players_for_team. FPL injects xG-derived priors here;
                     the World Cup uses the registry. Resolved ONCE per team below,
                     never inside the sim loop.

    Returns (player_samples, match_samples).
    """
    import config
    gamma = config.GOAL_CONCENTRATION if concentration is None else concentration
    rng = random.Random(seed)
    fx = fixtures.by_round(fantasy_round)
    market_rates = market_rates or {}
    research = research or {}
    prior_of = priors or ratings.players_for_team

    player_samples: dict[str, PlayerSample] = {}
    match_samples: dict[str, MatchSample] = {}
    eff_weight: dict[str, float] = {}     # multinomial goal weight per player
    eff_start: dict[str, float] = {}      # blended start probability
    assist_weight: dict[str, float] = {}
    squads: dict[str, list] = {}   # team -> resolved priors, looked up once

    # Pre-index priors per team + precompute blended per-player params once.
    for f in fx:
        match_samples[f.match_id] = MatchSample(f.match_id, f.home, f.away)
        for team in (f.home, f.away):
            if team not in squads:
                squads[team] = prior_of(team)
            for p in squads[team]:
                ps0 = player_samples.setdefault(
                    p.name, PlayerSample(p.name, p.team, p.position))
                ps0.goal_share, ps0.assist_share = p.goal_share, p.assist_share
                w_goal, w_start = effective_goal_weight(
                    p.goal_share, market_rates.get(p.name), research.get(p.name),
                    research_weight, base_start=p.start_prob)
                if getattr(p, "pen_taker", False):
                    w_goal += config.PEN_TAKER_GOAL_BONUS  # modest spot-kick uplift
                eff_weight[p.name] = w_goal
                eff_start[p.name] = w_start
                assist_weight[p.name] = p.assist_share

    for _ in range(sims):
        for f in fx:
            lam_h, lam_a = f.lambdas()
            hg = _poisson(lam_h, rng)
            ag = _poisson(lam_a, rng)
            ms = match_samples[f.match_id]
            ms.sims += 1
            ms.scorelines[(hg, ag)] += 1

            motm_pool: list[tuple[str, float]] = []  # one MOTM per match across both teams
            for team, gf, ga in ((f.home, hg, ag), (f.away, ag, hg)):
                squad = squads.get(team, ())
                if not squad:
                    continue
                # Who is on the pitch this sim (blended start probabilities).
                on_pitch = {p.name: rng.random() < eff_start[p.name] for p in squad}
                goals = _distribute(gf, squad, on_pitch, rng, eff_weight, gamma)
                assists = _distribute(gf, squad, on_pitch, rng, assist_weight, gamma)
                clean = (ga == 0)
                won, drew = gf > ga, gf == ga
                for p in squad:
                    ps = player_samples[p.name]
                    ps.sims += 1
                    if not on_pitch[p.name]:
                        continue
                    mins = min(90, max(0, rng.gauss(p.exp_minutes, 12)))
                    ps.minutes += mins
                    ps.played += 1
                    if mins >= 60:
                        ps.played_60 += 1
                    g = goals.get(p.name, 0)
                    a = assists.get(p.name, 0)
                    ps.goals += g
                    ps.assists += a
                    ps.goal_samples.append(g)
                    ps.sot += _poisson(p.sot_per90 * mins / 90, rng) + g  # goals are SoT
                    if p.position in ("DEF", "GK"):
                        ps.conceded += ga
                        if mins >= 60:
                            if clean:
                                ps.clean_sheet += 1
                            ps.conc_beyond += max(0, ga - 1)  # -pts per goal after the first
                    if p.position == "GK":
                        s = _poisson(max(0.0, ga + 1.5), rng)
                        ps.saves += s
                        ps.save_samples.append(s)
                    if p.defcon_per90 > 0:
                        ps.defcon_samples.append(
                            _poisson(p.defcon_per90 * mins / 90.0, rng))
                    # Discipline.
                    if rng.random() < 0.12:
                        ps.yellow += 1
                    if rng.random() < 0.012:
                        ps.red += 1
                    # MOTM candidacy: contributions + result bias (one winner per match).
                    motm_pool.append((p.name, 1.0 + 3.0 * g + 1.5 * a
                                      + (1.2 if won else 0.4 if drew else 0.0)))
                # Decisive goal (Holdet): one winning/equalising goal per match, credited
                # to a scorer weighted by goals scored this sim.
                if gf > 0 and (won or drew):
                    scorers = [(nm, c) for nm, c in goals.items() if c > 0 and on_pitch.get(nm)]
                    if scorers:
                        rr, ac = rng.random() * sum(c for _, c in scorers), 0.0
                        for nm, c in scorers:
                            ac += c
                            if rr <= ac:
                                if won:
                                    player_samples[nm].decisive_win += 1
                                else:
                                    player_samples[nm].decisive_draw += 1
                                break
            if motm_pool:  # award exactly one MOTM this sim, weighted
                r, acc = rng.random() * sum(wt for _, wt in motm_pool), 0.0
                for nm, wt in motm_pool:
                    acc += wt
                    if r <= acc:
                        player_samples[nm].motm += 1
                        break

    return player_samples, match_samples


def event_means(player_samples: dict[str, PlayerSample]) -> dict[str, dict]:
    """Convenience: collapse to per-player mean events for table-style scoring."""
    out = {}
    for name, ps in player_samples.items():
        out[name] = {
            "team": ps.team, "position": ps.position,
            "goals": ps.mean("goals"), "assists": ps.mean("assists"),
            "sot": ps.mean("sot"), "minutes": ps.mean("minutes"),
            "played": ps.mean("played"), "clean_sheet": ps.mean("clean_sheet"),
            "conc_beyond": ps.mean("conc_beyond"),
            "conceded": ps.mean("conceded"),
            "played_60": ps.mean("played_60"),
            "decisive_win": ps.mean("decisive_win"),
            "decisive_draw": ps.mean("decisive_draw"),
            "yellow": ps.mean("yellow"), "red": ps.mean("red"),
            "motm": ps.mean("motm"), "saves": ps.mean("saves"),
            "goal_share": ps.goal_share, "assist_share": ps.assist_share,
        }
    return out
