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
