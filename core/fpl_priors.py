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
_DEFAULT_START_PROB = 0.25   # unknown player: assume a squad role, not a starter


def minutes_model(player: dict, team_matches: int) -> tuple[float, float]:
    """(start_prob, exp_minutes) for one player.

    start_prob is the observed start rate over `team_matches`, then multiplied by
    FPL's availability signal. exp_minutes is minutes-per-start, which separates a
    90-minute nailed starter from a player who starts but is routinely withdrawn,
    and drops toward a cameo figure for players who mostly come off the bench.

    `team_matches` is how many matches the sample covers — 38 for a full prior
    season, or matches played so far once the new season is under way.
    """
    starts = player.get("starts") or 0
    minutes = player.get("minutes") or 0
    gate = availability_factor(player)

    if team_matches <= 0 or (starts == 0 and minutes == 0):
        return _DEFAULT_START_PROB * gate, _DEFAULT_EXP_MINUTES

    start_rate = min(1.0, starts / float(team_matches))

    if starts > 0:
        exp_minutes = min(90.0, minutes / float(starts))
    else:
        # Never started in the sample: a substitute. Spread the minutes over the
        # appearances we can infer, floored so the sim still gives him some time.
        exp_minutes = max(15.0, min(59.0, minutes / float(team_matches)))

    return start_rate * gate, exp_minutes


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


def _rates(player: dict) -> tuple[float, float]:
    """(xg_per90, xa_per90), falling back to the price prior with no history."""
    if needs_cold_start(player):
        return price_prior_xg(player), price_prior_xa(player)
    return player.get("xg_per90") or 0.0, player.get("xa_per90") or 0.0


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


def build_with_flags(players: list[dict], team_matches: int
                     ) -> tuple[dict[str, list], list[dict]]:
    """Build priors grouped by club, plus a list of cold-start flags for preflight.

    Shares are normalised WITHIN a club: the engine allocates a team's simulated
    goals among its own players, so what matters is a player's share of his club's
    attacking output, not an absolute rate. Shares need not sum to 1 — the engine
    treats the remainder as unmodelled teammates.

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
            if needs_cold_start(p):
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
                defcon_per90=p.get("defcon_per90") or 0.0,
                saves_per90=p.get("saves_per90") or 0.0,
            ))
        by_team[team] = priors

    return by_team, flags


def build(players: list[dict], team_matches: int) -> dict[str, list]:
    """build_with_flags without the flags, for callers that don't need preflight."""
    by_team, _flags = build_with_flags(players, team_matches)
    return by_team
