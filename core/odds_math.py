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


def devig_proportional(decimal_odds: list[float]) -> list[float]:
    """Proportional de-vig: normalise implied probabilities to sum to 1.

    The mainstream default, but per Strumbelj (2014) and Hegarty & Whelan (2025) it is
    the worst mainstream method — it understates favourites (favourite-longshot bias)
    because it spreads the whole overround evenly instead of weighting it towards the
    longshots where bookmaker margin is actually concentrated.
    """
    raw = implied_probs(decimal_odds)
    s = sum(raw)
    return [r / s for r in raw]


# Back-compat alias: existing call sites (core/espn.py, core/odds.py, tests) call
# odds_math.devig(...) directly. Keep it bit-identical to devig_proportional.
devig = devig_proportional


def solve_shin_z(implied: list[float], *, lo: float = 0.0, hi: float = 0.5,
                 iters: int = 100, tol: float = 1e-12) -> float:
    """Solve for Shin's insider-trading fraction z in (0, 1).

    Shin (1992/93): a fraction z of the betting population are informed insiders; the
    bookmaker sets prices to survive against them. Fair probabilities satisfy
        p_i = (sqrt(z^2 + 4(1-z) * imp_i^2 / B) - z) / (2(1-z))
    for booksum B = sum(imp_i), and z is the unique root making sum(p_i) = 1.
    z = 0 recovers proportional normalisation (no informed-trading correction).
    Bisection on the monotonic residual sum(p_i(z)) - 1.
    """
    def probs_for_z(z: float) -> list[float]:
        return _shin_probs(implied, z)

    def residual(z: float) -> float:
        return sum(probs_for_z(z)) - 1.0

    b = sum(implied)
    if b <= 1.0 + 1e-12:
        return 0.0  # no overround (or underround) — nothing for z to correct.

    r_lo, r_hi = residual(lo), residual(hi)
    # residual(0) > 0 whenever there's overround (booksum > 1); residual should fall
    # as z grows. If hi isn't enough to flip the sign, widen once — pathological/very
    # high-margin inputs — then fall back to the boundary that minimises |residual|.
    if r_lo * r_hi > 0:
        hi = 0.9
        r_hi = residual(hi)
        if r_lo * r_hi > 0:
            return lo if abs(r_lo) < abs(r_hi) else hi
    for _ in range(iters):
        mid = (lo + hi) / 2.0
        r_mid = residual(mid)
        if abs(r_mid) < tol:
            return mid
        if (r_lo < 0) != (r_mid < 0):
            hi = mid
        else:
            lo, r_lo = mid, r_mid
    return (lo + hi) / 2.0


def _shin_probs(implied: list[float], z: float) -> list[float]:
    b = sum(implied)
    if z <= 0.0:
        return [i / b for i in implied]
    if z >= 1.0:
        z = 1.0 - 1e-9
    out = []
    for i in implied:
        i = min(max(i, 0.0), 1.0)
        inner = z * z + 4.0 * (1.0 - z) * (i * i) / b
        inner = max(inner, 0.0)
        p = (math.sqrt(inner) - z) / (2.0 * (1.0 - z))
        out.append(max(p, 0.0))
    return out


def devig_shin(implied: list[float]) -> list[float]:
    """Shin's method: de-vig by solving for the insider-trading fraction z, then
    reading off fair probabilities. Corrects the favourite-longshot bias that
    proportional normalisation leaves in place — favourites get MORE probability,
    longshots get less, relative to plain normalisation, for the same market."""
    z = solve_shin_z(implied)
    p = _shin_probs(implied, z)
    s = sum(p)
    if s <= 0:
        # Degenerate input (all-zero implied probs) — fall back to proportional.
        return devig_proportional_probs(implied)
    return [x / s for x in p]


def devig_proportional_probs(implied: list[float]) -> list[float]:
    """Proportional normalisation applied directly to already-implied probabilities
    (as opposed to devig_proportional, which takes decimal odds)."""
    s = sum(implied)
    return [i / s for i in implied]


def solve_power_k(implied: list[float], *, lo: float = 0.05, hi: float = 4.0,
                  iters: int = 100, tol: float = 1e-12) -> float:
    """Solve for the power-method exponent k such that sum(imp_i^k) = 1.

    The power method treats the whole market as scaled by a single exponent: fair
    p_i = imp_i^k / sum(imp_j^k). Choosing k so that sum(imp_i^k) = 1 makes the
    normalising denominator equal to 1, i.e. p_i = imp_i^k directly. sum(imp_i^k) is
    strictly decreasing in k for imp_i in (0,1), so a market with overround (booksum
    > 1 at k=1) needs k > 1 to shrink every probability just enough to remove the
    margin (bisection on the residual).
    """
    def total(k: float) -> float:
        return sum(i ** k for i in implied)

    b = total(1.0)
    if abs(b - 1.0) < 1e-12:
        return 1.0  # no overround — k=1 is already exact.

    r_lo, r_hi = total(lo) - 1.0, total(hi) - 1.0
    if r_lo * r_hi > 0:
        # Shouldn't happen for a normal overround market; fall back to the closer end.
        return lo if abs(r_lo) < abs(r_hi) else hi
    for _ in range(iters):
        mid = (lo + hi) / 2.0
        r_mid = total(mid) - 1.0
        if abs(r_mid) < tol:
            return mid
        if (r_lo < 0) != (r_mid < 0):
            hi = mid
        else:
            lo, r_lo = mid, r_mid
    return (lo + hi) / 2.0


def devig_power(implied: list[float]) -> list[float]:
    """Power method: fair p_i = imp_i^k, with k solved so sum(imp_i^k) = 1.

    Like Shin, this concentrates the correction on the longshots (imp_i^k for k<1
    shrinks small probabilities proportionally more than large ones), giving
    favourites more probability than plain proportional normalisation."""
    k = solve_power_k(implied)
    p = [i ** k for i in implied]
    s = sum(p)
    if s <= 0:
        return devig_proportional_probs(implied)
    return [x / s for x in p]


# Dispatch table for config.DEVIG_METHOD. All three take DECIMAL ODDS (not implied
# probabilities) so they're drop-in interchangeable at the 1X2-to-lambda call site.
def devig_by_method(decimal_odds: list[float], method: str = "proportional") -> list[float]:
    """De-vig decimal odds using the named method: proportional | shin | power."""
    if method == "proportional":
        return devig_proportional(decimal_odds)
    implied = implied_probs(decimal_odds)
    if method == "shin":
        return devig_shin(implied)
    if method == "power":
        return devig_power(implied)
    raise ValueError(f"unknown DEVIG_METHOD: {method!r} (expected proportional|shin|power)")


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
