"""Pure odds math — no network. De-vig, lambda solving, prop->rate.

These functions take already-fetched decimal odds (see core/odds.py for fetching)
and turn them into the quantities the engine needs:
  - devig: strip the bookmaker overround from a set of mutually-exclusive outcomes.
  - solve_lambdas: recover (lambda_home, lambda_away) of an independent Poisson whose
    implied 1X2 best matches the de-vigged market.
  - scorer_prob_to_goal_rate: turn an anytime-goalscorer probability into a Poisson rate.
"""

from __future__ import annotations

import math


def implied_probs(decimal_odds: list[float]) -> list[float]:
    return [1.0 / o for o in decimal_odds]


def devig(decimal_odds: list[float]) -> list[float]:
    """Proportional de-vig: normalise implied probabilities to sum to 1."""
    raw = implied_probs(decimal_odds)
    s = sum(raw)
    return [r / s for r in raw]


def _pois(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def poisson_1x2(lh: float, la: float, max_goals: int = 8) -> tuple[float, float, float]:
    """1X2 probabilities for an independent Poisson scoreline model."""
    pH = pD = pA = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = _pois(h, lh) * _pois(a, la)
            if h > a:
                pH += p
            elif h == a:
                pD += p
            else:
                pA += p
    return pH, pD, pA


def solve_lambdas(pH: float, pD: float, pA: float, *, lo: float = 0.2, hi: float = 3.5,
                  steps: int = 34, refine: int = 3) -> tuple[float, float]:
    """Coarse-to-fine search for (lh, la) minimising squared 1X2 error vs the market."""
    best, lh0, la0 = 1e9, 1.2, 1.2
    span = (lo, hi, lo, hi)
    for _ in range(refine):
        lo_h, hi_h, lo_a, hi_a = span
        gh = [lo_h + (hi_h - lo_h) * i / steps for i in range(steps + 1)]
        ga = [lo_a + (hi_a - lo_a) * i / steps for i in range(steps + 1)]
        for lh in gh:
            for la in ga:
                qH, qD, qA = poisson_1x2(lh, la)
                err = (qH - pH) ** 2 + (qD - pD) ** 2 + (qA - pA) ** 2
                if err < best:
                    best, lh0, la0 = err, lh, la
        d = (hi_h - lo_h) / steps
        span = (lh0 - d, lh0 + d, la0 - d, la0 + d)
    return lh0, la0


def scorer_prob_to_goal_rate(p_anytime: float) -> float:
    """Anytime-scorer probability -> Poisson goal rate. P(>=1) = 1 - e^-lambda."""
    if p_anytime <= 0:
        return 0.0
    if p_anytime >= 1:
        p_anytime = 0.999
    return -math.log(1 - p_anytime)


def american_to_decimal(american: float) -> float:
    """American odds -> decimal. +160 -> 2.6, -125 -> 1.8."""
    if american > 0:
        return american / 100.0 + 1.0
    return 100.0 / abs(american) + 1.0


# --- Dixon-Coles scoreline model -------------------------------------------
# Independent Poisson underweights low-score draws (0-0, 1-1) and the 1-0/0-1
# cells. Dixon-Coles applies a small dependence correction `rho` to exactly those
# four cells, giving a market-consistent joint scoreline distribution — what
# Målspillet needs and what a correct-score market would have provided.

def dc_tau(x: int, y: int, lh: float, la: float, rho: float) -> float:
    """Dixon-Coles low-score adjustment for cell (x, y)."""
    if x == 0 and y == 0:
        return 1.0 - lh * la * rho
    if x == 0 and y == 1:
        return 1.0 + lh * rho
    if x == 1 and y == 0:
        return 1.0 + la * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def score_matrix_dc(lh: float, la: float, rho: float = 0.0,
                    max_goals: int = 10) -> dict:
    """Normalised joint scoreline distribution {(h, a): prob} under Dixon-Coles.
    rho = 0 reduces to independent Poisson."""
    grid: dict = {}
    total = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = max(0.0, dc_tau(h, a, lh, la, rho)) * _pois(h, lh) * _pois(a, la)
            grid[(h, a)] = p
            total += p
    if total > 0:
        for k in grid:
            grid[k] /= total
    return grid


def outcome_from_matrix(grid: dict) -> tuple[float, float, float]:
    """(pH, pD, pA) from a scoreline grid."""
    pH = pD = pA = 0.0
    for (h, a), p in grid.items():
        if h > a:
            pH += p
        elif h == a:
            pD += p
        else:
            pA += p
    return pH, pD, pA


def prob_over(grid: dict, line: float) -> float:
    """P(total goals > line) from a scoreline grid (e.g. line=2.5)."""
    return sum(p for (h, a), p in grid.items() if (h + a) > line)


def solve_dc(pH: float, pD: float, pA: float, *, p_over: float | None = None,
             line: float = 2.5, lo: float = 0.2, hi: float = 3.5, steps: int = 24,
             refine: int = 3, rho_lo: float = -0.15, rho_hi: float = 0.15,
             rho_steps: int = 12) -> tuple[float, float, float]:
    """Fit (lh, la, rho) so the DC joint matches the de-vigged 1X2 (and totals if
    given). 1X2 alone underdetermines 3 params, so pass p_over for the 3rd target."""
    best = (1e9, 1.2, 1.2, 0.0)
    span = (lo, hi, lo, hi)
    for _ in range(refine):
        lo_h, hi_h, lo_a, hi_a = span
        gh = [lo_h + (hi_h - lo_h) * i / steps for i in range(steps + 1)]
        ga = [lo_a + (hi_a - lo_a) * i / steps for i in range(steps + 1)]
        grho = [rho_lo + (rho_hi - rho_lo) * j / rho_steps for j in range(rho_steps + 1)]
        for lh in gh:
            for la in ga:
                for rho in grho:
                    grid = score_matrix_dc(lh, la, rho)
                    qH, qD, qA = outcome_from_matrix(grid)
                    err = (qH - pH) ** 2 + (qD - pD) ** 2 + (qA - pA) ** 2
                    if p_over is not None:
                        err += (prob_over(grid, line) - p_over) ** 2
                    if err < best[0]:
                        best = (err, lh, la, rho)
        _, lh0, la0, _rho0 = best
        d = (hi_h - lo_h) / steps
        span = (lh0 - d, lh0 + d, la0 - d, la0 + d)
    return best[1], best[2], best[3]
