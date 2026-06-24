"""Målspillet — EV-optimal scorelines under 1+1+1 scoring, plus Chance Bamse.

Uses an analytic Dixon-Coles joint scoreline grid (market-consistent, capturing draw
inflation) rather than Monte-Carlo. DC params (lam_home, lam_away, rho) come from the
cached ESPN odds when available, else fall back to the ratings priors with rho=0.
"""

from __future__ import annotations

from core import fixtures, odds_math, espn


def match_dc_params(f) -> tuple[float, float, float]:
    """(lam_home, lam_away, rho) for a fixture — cached market odds, else priors."""
    cached = espn.load_match_odds(f.match_id)
    if cached and cached.get("lam_home") is not None:
        return cached["lam_home"], cached["lam_away"], cached.get("rho", 0.0)
    lh, la = f.lambdas()
    return lh, la, 0.0


def _marginals(grid: dict):
    mh: dict[int, float] = {}
    ma: dict[int, float] = {}
    for (h, a), p in grid.items():
        mh[h] = mh.get(h, 0.0) + p
        ma[a] = ma.get(a, 0.0) + p
    return mh, ma


def optimal_pick(grid: dict) -> tuple[int, int, float]:
    """Scoreline maximising expected Målspillet points: P(home=h)+P(away=a)+P(outcome)."""
    mh, ma = _marginals(grid)
    pH, pD, pA = odds_math.outcome_from_matrix(grid)
    oc = {"H": pH, "D": pD, "A": pA}
    best = (0, 0, -1.0)
    for hg in range(7):
        for ag in range(7):
            res = "H" if hg > ag else "A" if ag > hg else "D"
            ev = mh.get(hg, 0.0) + ma.get(ag, 0.0) + oc[res]
            if ev > best[2]:
                best = (hg, ag, ev)
    return best


def run(state: dict, fantasy_round: int, sims: int = 100_000) -> None:
    fx = sorted(fixtures.by_round(fantasy_round), key=lambda f: f.kickoff)
    if not fx:
        print(f"  [malspillet] no fixtures for round {fantasy_round} — run with --refresh "
              "(ESPN) to populate the schedule.")
        return

    print(f"\n=== Målspillet — round {fantasy_round} order book ===")
    locked = {p["match_id"] for p in state.get("predictions", [])
              if p.get("locked") and not p.get("_example")}

    rows = []
    for f in fx:
        lh, la, rho = match_dc_params(f)
        grid = odds_math.score_matrix_dc(lh, la, rho)
        hg, ag, ev = optimal_pick(grid)
        pH, pD, pA = odds_math.outcome_from_matrix(grid)
        rows.append((f, hg, ag, ev))
        src = "odds" if espn.load_match_odds(f.match_id) else "priors"
        print(f"\n  {f.match_id} {f.home} v {f.away}  "
              f"(KO {f.kickoff:%m-%d %H:%M}, {src}, rho={rho:+.3f})")
        print(f"    submit {hg}-{ag}   E[pts]={ev:.3f}   "
              f"(H {pH:.0%} / D {pD:.0%} / A {pA:.0%})")

    print("\n  Chance Bamse:")
    if fixtures.is_single_match_round(fantasy_round):
        f = fx[0]
        print(f"    auto-assigned to {f.match_id} (single-match round). "
              f"Locks at KO {f.kickoff:%m-%d %H:%M}.")
    elif state.get("bamse_locked"):
        print(f"    already locked to {state.get('bamse_match_id')}.")
    else:
        unlocked = [r for r in rows if r[0].match_id not in locked]
        if unlocked:
            best = max(unlocked, key=lambda r: r[3])
            f = best[0]
            print(f"    assign to {f.match_id} {f.home} v {f.away} "
                  f"(highest E[pts]={best[3]:.3f}, doubled={2*best[3]:.3f}). "
                  f"Locks at KO {f.kickoff:%m-%d %H:%M}.")
        else:
            print("    all matches locked — no Bamse choice available.")
