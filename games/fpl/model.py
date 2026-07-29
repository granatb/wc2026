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
