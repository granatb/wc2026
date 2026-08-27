"""Turn FPL API data into engine priors.

This is the ONLY place FPL's field names become `ratings.PlayerPrior`. It owns:
  - the minutes model (start probability + expected minutes)
  - per-90 rate derivation (xG/xA -> goal/assist share, DefCon, saves)
  - the cold-start fallback for players with no Premier League history

It knows nothing about scoring (that is games/fpl/model.py) and nothing about HTTP
(that is core/fpl_api.py).

Why xG-derived rather than market-derived: ESPN carries no player-level props for
eng.1 (verified 2026-07-28), so the World Cup's anytime-goalscorer path is empty at
build time. FPL's own feed ships last season's per-90 rates instead, which slot into
the engine's existing `prior_share` blend slot. If props ever appear, the engine's
`market_rate` path lights up with no change here.
"""

from __future__ import annotations

import contextlib
import json
import os

import collections

import config

from . import ratings

# FPL status codes: a=available, d=doubtful, i=injured, s=suspended, u=unavailable.
_CANNOT_PLAY = {"i", "s", "u"}


def availability_factor(player: dict) -> float:
    """Multiplier on start probability from FPL's own availability fields.

    Hard-gates unavailable players to zero. Scales the doubtful. A `chance_of_playing`
    of 0 gates regardless of status, because FPL sometimes leaves status at 'a' while
    the percentage has already dropped to 0.
    """
    chance = player.get("chance_of_playing")
    if chance is not None:
        return max(0.0, min(1.0, chance / 100.0))
    if player.get("status") in _CANNOT_PLAY:
        return 0.0
    if player.get("status") == "d":
        return 0.5   # doubtful with no published percentage
    return 1.0


# Fallback expected minutes when a player has no history to measure.
_DEFAULT_EXP_MINUTES = 70.0
PRESEASON_MATCHES = 38       # the snapshot's sample size
_DEFAULT_START_PROB = 0.25   # unknown player: assume a squad role, not a starter


def minutes_model(player: dict, team_matches: int) -> tuple[float, float]:
    """(start_prob, exp_minutes) for one player, blending history with this season.

    start_rate is the observed start rate, then multiplied by FPL's availability
    signal. exp_minutes is minutes-per-start, which separates a 90-minute nailed
    starter from one who is routinely withdrawn, and drops toward a cameo figure
    for players who mostly come off the bench.

    `team_matches` is how many matches THIS SEASON's sample covers — 1 after
    gameweek 1, not 38.

    THE BUG THIS EXISTS TO PREVENT (2026-08-27): the live feed's `starts` and
    `minutes` reset at the season rollover. Dividing this season's 1 start by a
    hardcoded 38 collapsed every player to a ~2.6% start probability, so the only
    players left standing in the order book were the ones carrying a research
    note — the model was silently ranking by "who did Claude write about", not by
    football. The preseason snapshot (38 games) is blended in by minutes exactly
    as the scoring rates are, so August leans on last season and the live sample
    takes over as it grows.
    """
    live_starts = player.get("starts") or 0
    live_minutes = player.get("minutes") or 0
    gate = availability_factor(player)

    hist = preseason_rates().get(str(player.get("id"))) or {}
    hist_starts = hist.get("starts") or 0
    hist_minutes = hist.get("minutes") or 0
    hist_matches = PRESEASON_MATCHES if hist_minutes else 0

    if (team_matches <= 0 or (live_starts == 0 and live_minutes == 0)) and not hist_minutes:
        return _DEFAULT_START_PROB * gate, _DEFAULT_EXP_MINUTES

    # Starts over matches, with the prior as pseudo-matches. Without it a player
    # who started the season's only fixture reads as a 100% nailed starter --
    # which is how a 5.5m promoted forward outranked the entire league.
    live_matches = max(0, team_matches)
    start_rate = shrink(PRIOR_START_RATE, PRIOR_MATCHES, [
        (hist_rate_of(hist_starts, hist_matches), hist_matches),
        (live_rate_of(live_starts, live_matches), live_matches),
    ])

    total_starts = hist_starts + live_starts
    total_minutes = hist_minutes + live_minutes
    total_matches = hist_matches + max(0, team_matches)
    if total_starts > 0:
        exp_minutes = min(90.0, total_minutes / float(total_starts))
    elif total_matches > 0:
        # Never started in either sample: a substitute. Spread the minutes over
        # the appearances we can infer, floored so the sim still gives him time.
        exp_minutes = max(15.0, min(59.0, total_minutes / float(total_matches)))
    else:
        exp_minutes = _DEFAULT_EXP_MINUTES

    return min(1.0, start_rate) * gate, exp_minutes


def needs_cold_start(player: dict) -> bool:
    """True when a player has no Premier League minutes to derive rates from."""
    return (player.get("minutes") or 0) <= 0


def _price_scaled(player: dict, table: dict) -> float:
    pos = player.get("position", "MID")
    base = table.get(pos, 0.0)
    if base <= 0.0:
        return 0.0
    median = config.FPL_MEDIAN_PRICE.get(pos, 5.0)
    quality = min(3.0, max(0.3, (player.get("price") or median) / median))
    return base * quality


def price_prior_xg(player: dict) -> float:
    """Cold-start non-penalty xG/90 from price and position."""
    return _price_scaled(player, config.FPL_COLD_START_XG90)


def price_prior_xa(player: dict) -> float:
    """Cold-start xA/90 from price and position."""
    return _price_scaled(player, config.FPL_COLD_START_XA90)


_PRESEASON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "evmax", "assets", "preseason_rates.json")
_preseason_cache: dict = {}


def preseason_rates() -> dict:
    """{element_id: {rate fields, minutes}} as the feed carried them pre-GW1.

    Once the season starts, bootstrap-static's per-90 fields describe the CURRENT
    season only — a one- or two-game sample. Read literally that is noise: after
    gameweek 1 it projected De Cuyper at 11.97 xPts off a single goal while
    B.Fernandes, on 3,065 minutes of elite history, fell to 5.83. This snapshot is
    the season's only surviving record of the 38-game sample, so it is committed
    and never regenerated.
    """
    if not _preseason_cache:
        try:
            with open(_PRESEASON_PATH, encoding="utf-8") as fh:
                _preseason_cache.update(json.load(fh).get("rates") or {})
        except (OSError, ValueError):
            _preseason_cache["_missing"] = True
    return _preseason_cache


@contextlib.contextmanager
def preseason_rates_override(rates: dict):
    """Swap the preseason snapshot for the duration of a block.

    Tests build synthetic players, and a synthetic id collides with a real one:
    a fixture player carrying `id: 1` silently inherited a real footballer's
    38-game career and every minutes assertion moved. Anything asserting on
    history must state the history it wants.
    """
    global _preseason_cache
    saved = _preseason_cache
    _preseason_cache = dict(rates) or {"_missing": True}
    try:
        yield
    finally:
        _preseason_cache = saved


def blend_rate(hist_value, hist_minutes, live_value, live_minutes) -> float:
    """Minutes-weighted blend of last season's rate and this season's.

    Early in a season the live sample is tiny and the history should dominate;
    by the run-in the live sample is the truth. Weighting by minutes does that
    automatically with no schedule to tune: at GW2 a 90-minute sample carries
    90/3155 of the weight, and it crosses over naturally as the season runs.
    """
    hm = max(0.0, float(hist_minutes or 0))
    lm = max(0.0, float(live_minutes or 0))
    hv, lv = float(hist_value or 0.0), float(live_value or 0.0)
    if hm + lm <= 0:
        return lv
    return (hv * hm + lv * lm) / (hm + lm)


# How much evidence the price-based prior is worth. A player's price is the
# market's own estimate of him and it is never worthless, so it is carried as a
# pseudo-sample that real minutes progressively outvote rather than as a
# fallback that switches off the moment a single match exists.
#
# THE BUG THIS EXISTS TO PREVENT (2026-08-27): Emersonn, promoted with Ipswich
# and therefore carrying no Premier League history at all, played 65 minutes of
# gameweek 1 and posted 1.14 xG/90 in them — a higher rate than Haaland has ever
# sustained. Read literally, that one substitute appearance made him the best
# forward in the game and the transfer optimizer wanted him over every
# alternative. Five matches of prior is enough that a single hot cameo cannot do
# that, and little enough that a genuinely good player escapes it within a month.
PRIOR_MINUTES = 450.0        # five matches
PRIOR_MATCHES = 3.0          # for the start rate, whose denominator is matches
PRIOR_START_RATE = 0.35      # a squad player, before we know anything else


def hist_rate_of(starts, matches) -> float:
    return min(1.0, (starts or 0) / float(matches)) if matches else 0.0


def live_rate_of(starts, matches) -> float:
    return min(1.0, (starts or 0) / float(matches)) if matches else 0.0


def shrink(prior: float, prior_weight: float, observations: list) -> float:
    """Weighted mean of `prior` and (value, weight) observations."""
    num = prior * prior_weight
    den = prior_weight
    for value, weight in observations:
        w = max(0.0, float(weight or 0.0))
        num += float(value or 0.0) * w
        den += w
    return num / den if den > 0 else prior


def _rates(player: dict) -> tuple[float, float]:
    """(xg_per90, xa_per90) — the price prior, history and the live season,
    weighted by the minutes behind each.

    The price prior is always in the mix (see PRIOR_MINUTES) rather than being a
    fallback that switches off as soon as one match exists, because one match is
    not evidence of a rate.
    """
    hist = preseason_rates().get(str(player.get("id"))) or {}
    hist_minutes = hist.get("minutes") or 0
    live_minutes = player.get("minutes") or 0
    xg = shrink(price_prior_xg(player), PRIOR_MINUTES, [
        (hist.get("expected_goals_per_90"), hist_minutes),
        (player.get("xg_per90"), live_minutes),
    ])
    xa = shrink(price_prior_xa(player), PRIOR_MINUTES, [
        (hist.get("expected_assists_per_90"), hist_minutes),
        (player.get("xa_per90"), live_minutes),
    ])
    return xg, xa


def _disambiguate_names(players: list[dict]) -> None:
    """Give every player a `name` that is unique across the whole pool, in place.

    FPL's `web_name` collides across clubs -- 14 collisions in the real GW1 pool,
    the worst being Cole Palmer (CHE, MID) and Alex Palmer (IPS, GK) both keying
    the shared engine's per-player accumulator as "Palmer". The engine keys
    strictly by name (core/engine_events.simulate_round), so uniqueness has to be
    established here, at the FPL boundary, before names ever reach it.

    Escalates only as far as needed so the common case (a unique web_name) is left
    completely untouched:

      1. web_name, if it is unique in the pool
      2. otherwise full_name, if THAT disambiguates
      3. otherwise f"{web_name} ({team})" -- guaranteed unique, because a single
         club cannot field two players sharing a web_name.

    Mutates the player dicts' "name" key in place (rather than returning a
    separate mapping) so that every existing caller keying off `p["name"]` --
    `games/fpl/model.py`'s `players_by_name = {p["name"]: p for p in players}`
    chief among them -- keeps working unmodified as long as it reads `name` AFTER
    this runs, which it already does.
    """
    web_counts = collections.Counter(p["name"] for p in players)
    colliding = [p for p in players if web_counts[p["name"]] > 1]
    if not colliding:
        return

    full_counts = collections.Counter(p.get("full_name") or p["name"] for p in players)
    for p in colliding:
        full = p.get("full_name") or p["name"]
        if full_counts[full] == 1:
            p["name"] = full
        else:
            p["name"] = f"{p['name']} ({p['team']})"


def shrink_defcon_rate(position: str, observed: float, minutes: float) -> float:
    """Empirical-Bayes shrinkage of a raw per-90 DefCon rate toward its position
    prior, in units of 90-minute appearances (defect D).

    `defensive_contribution * 90 / minutes` from a handful of minutes is noise,
    not signal -- a 1-minute cameo with a single alert action prints a 90.0
    per-90 rate. Blending it with `config.FPL_DEFCON_PRIOR` in proportion to how
    much of it is actually measured (`config.FPL_DEFCON_SHRINKAGE_K` pseudo-
    appearances of prior) degrades gracefully as the sample grows, rather than a
    hard minutes cutoff that would zero out real players returning from injury or
    arriving from abroad. See config.py for the K derivation and the measured
    priors.

    Goalkeepers are hard-gated to 0.0 no matter what `observed` says: they do not
    accrue CBIT/CBIRT actions and are not DefCon-eligible at all.
    """
    if position == "GK":
        return 0.0
    prior = config.FPL_DEFCON_PRIOR.get(position, 0.0)
    appearances = max(0.0, minutes) / 90.0
    k = config.FPL_DEFCON_SHRINKAGE_K
    return (observed * appearances + prior * k) / (appearances + k)


def _defcon_rate(player: dict, backfill: dict | None) -> float:
    """The DefCon per-90 rate to carry onto this player's prior.

    Bootstrap's own `defcon_per90` wins whenever it is non-zero -- in-season,
    live data always beats last season's history. Only when bootstrap has
    nothing (preseason, when bootstrap-static zeroes the field for everyone) do
    we fall back to `backfill`, the core.fpl_api.fetch_defcon_backfill mapping of
    element id -> {"defcon_per90", "minutes"}. A player missing from `backfill`
    (no backfill supplied, or the id wasn't in it) safely falls through to 0.0.

    The backfilled rate is shrunk toward the position prior before it reaches the
    prior (see shrink_defcon_rate) -- raw per-90 rates from the tiny samples
    common in the backfill (61 of 400 real players under 200 minutes) are noise
    that would otherwise dominate the DefCon ranking. Goalkeepers are gated to
    0.0 up front, regardless of what `player["defcon_per90"]` or `backfill` say --
    they are not DefCon-eligible.
    """
    if player.get("position") == "GK":
        return 0.0
    live = player.get("defcon_per90") or 0.0
    if live:
        return live
    if not backfill:
        return 0.0
    entry = backfill.get(player.get("id"))
    if not entry:
        return 0.0
    observed = entry.get("defcon_per90") or 0.0
    minutes = entry.get("minutes") or 0
    return shrink_defcon_rate(player.get("position", "MID"), observed, minutes)


def build_with_flags(players: list[dict], team_matches: int,
                     defcon_backfill: dict[int, dict] | None = None
                     ) -> tuple[dict[str, list], list[dict]]:
    """Build priors grouped by club, plus a list of cold-start flags for preflight.

    Shares are normalised WITHIN a club: the engine allocates a team's simulated
    goals among its own players, so what matters is a player's share of his club's
    attacking output, not an absolute rate. Shares need not sum to 1 — the engine
    treats the remainder as unmodelled teammates.

    `defcon_backfill` is optional -- see `_defcon_rate` for the precedence rule
    (live bootstrap data always wins over it). Existing callers that don't pass it
    are unaffected: they get bootstrap's own defcon_per90 (0.0 preseason) exactly
    as before.

    Mutates `players` to disambiguate colliding names before anything else reads
    them -- see `_disambiguate_names`.
    """
    _disambiguate_names(players)

    by_team: dict[str, list] = {}
    flags: list[dict] = []

    grouped: dict[str, list] = {}
    for p in players:
        grouped.setdefault(p["team"], []).append(p)

    for team, squad in grouped.items():
        weighted = []
        for p in squad:
            start_prob, exp_minutes = minutes_model(p, team_matches)
            xg90, xa90 = _rates(p)
            # A genuine cold start now means no history ANYWHERE — a player
            # with a preseason sample blends (see _rates) and must not be
            # reported as priced off his cost alone, or the operator warning
            # cries wolf about 300 players who are fine.
            if (not (preseason_rates().get(str(p.get("id"))) or {}).get("minutes")
                    and needs_cold_start(p)):
                flags.append({"name": p["name"], "team": team,
                              "reason": "no_pl_history"})
            weighted.append((p, start_prob, exp_minutes, xg90, xa90))

        # Normalise to shares of the club's expected output, weighting each player's
        # rate by how much of the pitch time he is expected to occupy.
        goal_mass = sum(sp * xg for _p, sp, _m, xg, _xa in weighted) or 1.0
        assist_mass = sum(sp * xa for _p, sp, _m, _xg, xa in weighted) or 1.0

        priors = []
        for p, start_prob, exp_minutes, xg90, xa90 in weighted:
            priors.append(ratings.PlayerPrior(
                name=p["name"], team=team, position=p["position"],
                start_prob=start_prob, exp_minutes=exp_minutes,
                goal_share=(xg90 / goal_mass) if xg90 else 0.0,
                assist_share=(xa90 / assist_mass) if xa90 else 0.0,
                sot_per90=0.0,          # FPL does not score shots on target
                pen_taker=bool(p.get("pen_taker")),
                defcon_per90=_defcon_rate(p, defcon_backfill),
                saves_per90=p.get("saves_per90") or 0.0,
            ))
        by_team[team] = priors

    return by_team, flags


def build(players: list[dict], team_matches: int,
         defcon_backfill: dict[int, dict] | None = None) -> dict[str, list]:
    """build_with_flags without the flags, for callers that don't need preflight."""
    by_team, _flags = build_with_flags(players, team_matches, defcon_backfill)
    return by_team
