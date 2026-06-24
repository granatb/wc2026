"""Odds × expert blend math — the per-game `w` dial.

w = 0  -> pure odds (ignore soft research)
w = 1  -> full expert overlay
Hard facts (out / suspended, or an absolute start_prob override) ignore w entirely.

Soft research enters as a `lambda_multiplier` (team/player attack nudge) for goal
rates and as blended start probabilities; this module holds only the math so it can
be unit-tested in isolation. See docs/superpowers/specs/2026-06-18-*.
"""

from __future__ import annotations

HARD_OUT_STATUSES = {"out", "suspended"}


def blend_lambda(lam_odds: float, *, multiplier: float, w: float) -> float:
    """Blend a market goal rate with a soft expert multiplier.

    multiplier = 1.0 is neutral. At w=0 returns lam_odds; at w=1 applies the full
    multiplier.
    """
    return lam_odds * (1 + w * (multiplier - 1))


def blend_rate(rate_odds: float, *, expert: float, w: float) -> float:
    """Linear blend between a market rate and an expert estimate."""
    return (1 - w) * rate_odds + w * expert


def apply_status(status: str | None, *, base_rate: float, base_start: float,
                 w: float) -> tuple[float, float]:
    """Apply a hard status flag. Soft statuses pass through unchanged (they are
    expressed via multipliers, not here). Returns (rate, start_prob)."""
    if status in HARD_OUT_STATUSES:
        return 0.0, 0.0
    return base_rate, base_start
