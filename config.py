"""Central control panel — the dials you tune, all in one place.

Everything tunable reads from here. `state.json` files hold only squad snapshots
(rosters, prices, ownership); this file holds *behaviour*. Edit and re-run.

See it any time with:  python manage.py config
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Per-game blend + objective
#
# research_weight (w): how much expert/research overrides the market odds.
#   w = 0.0  -> pure market odds
#   w = 1.0  -> full expert/research overlay
# Hard facts (player out/suspended) always override regardless of w.
#
# objective:
#   "mean"    -> maximise expected value (chalk)
#   "ceiling" -> maximise the high-percentile upside (variance / anti-chalk)
#   "odds"    -> pure market scoreline math (Målspillet)
# ---------------------------------------------------------------------------
GAMES = {
    "fifa":        {"team": "Granat65",     "research_weight": 0.30, "objective": "mean"},
    "holdet_gold": {"team": "Alwaysss 2nd", "research_weight": 0.10, "objective": "mean"},
    "holdet_yolo": {"team": "Always 2nd 2", "research_weight": 0.50, "objective": "ceiling"},
    "holdet_free": {"team": "Always 2nd",   "research_weight": 0.25, "objective": "mean"},
    "malspillet":  {"team": None,           "research_weight": 0.05, "objective": "odds"},
}

# Quantile used by the "ceiling" objective (YOLO). 0.85 = 85th-percentile upside.
CEILING_PERCENTILE = 0.85

# YOLO anti-chalk dial. The YOLO ranking score = ceiling × (1 − YOLO_FADE × ownership),
# so a low-owned boom (which leapfrogs the field that doesn't own it) outranks an equal
# chalk boom. 0.0 = pure ceiling (no fade), 1.0 = full leverage. Uses Holdet popularity.
YOLO_FADE = 0.5

# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------
DEFAULT_SIMS = 50_000

# Goal-allocation concentration (the differentiation dial). Sharpens how a team's
# goals/assists split among its players WITHOUT changing the team total — levels are
# preserved, only the spread widens:
#   1.0 -> raw goal_share weights (flattest; our XI compresses to a narrow band)
#   >1  -> concentrate onto higher-share players (stars pull ahead, role players drop)
# Acts on overall goal/assist share, NOT penalty duty, so it differentiates by attacking
# quality generally rather than singling out set-piece takers.
# 1.2: once the FIFA scoring values were corrected (goals 9/7/6/5), correct scoring did
# most of the differentiation by itself (rank-corr 0.54 at γ=1.0). Concentration past ~1.2
# barely lifts ranking but inflates elite strikers (Kane 1.2x->1.4x vs Rotowire), so keep
# it as a light nudge only.
GOAL_CONCENTRATION = 1.2

# Penalty takers get a modest goal-share uplift so their EV reflects spot-kick duty.
# Deliberately small — a pen is roughly one extra share point, a nudge UP, not a term
# that dominates the projection. Who takes pens is marked in core/ratings.PEN_TAKERS.
PEN_TAKER_GOAL_BONUS = 0.10

# ---------------------------------------------------------------------------
# Odds / market
# ---------------------------------------------------------------------------
DATA_SOURCE = "espn"          # "espn" (free, default) | "odds_api" (key-based alt)
USE_DIXON_COLES = True        # Målspillet: market-consistent scoreline correlation
SCORER_MARGIN_SHRINK = 0.92   # de-margin factor for 2-way player props (anytime goal)

# De-vig method for turning 1X2 decimal odds into fair probabilities (consumed at the
# 1X2-to-lambda step in core/espn.py derive_match, via core.odds_math.devig_by_method).
#   proportional -> normalise implied probs to sum to 1 (mainstream default, but per
#                   Strumbelj 2014 / Hegarty & Whelan 2025 the worst mainstream method:
#                   it understates favourites — the favourite-longshot bias).
#   shin         -> Shin's method; solves for an insider-trading fraction z, corrects FLB.
#   power        -> power method; solves p_i = imp_i^k normalised, also corrects FLB.
# Default stays "proportional" until scripts/devig_bakeoff.py shows a challenger wins
# on realized results with n>=40 matches (see bake-off script + commit history).
DEVIG_METHOD = "proportional"

# ---------------------------------------------------------------------------
# Priors — the expert fallback used when no market odds exist (e.g. knockouts
# before teams are known). Multiplicative goal model around BASE_GOALS.
# ---------------------------------------------------------------------------
BASE_GOALS = 1.35
HOME_ADV = 1.07               # host-nation home advantage multiplier


def game(name: str) -> dict:
    return GAMES[name]


def weight(name: str) -> float:
    return GAMES.get(name, {}).get("research_weight", 0.0)


def summary() -> str:
    """Human-readable dump for `manage.py config`."""
    lines = ["wc2026 config", "=" * 52, "", "Per-game blend (research_weight w):"]
    lines.append(f"  {'game':<13}{'team':<16}{'w':>6}  objective")
    for name, g in GAMES.items():
        lines.append(f"  {name:<13}{str(g['team']):<16}{g['research_weight']:>6.2f}  {g['objective']}")
    lines += [
        "",
        f"ceiling percentile : {CEILING_PERCENTILE}",
        f"default sims       : {DEFAULT_SIMS:,}",
        f"data source        : {DATA_SOURCE}",
        f"dixon-coles        : {USE_DIXON_COLES}",
        f"devig method       : {DEVIG_METHOD}",
        f"prop margin shrink : {SCORER_MARGIN_SHRINK}",
        f"base goals / home  : {BASE_GOALS} / {HOME_ADV}",
        "",
        "w=0 pure odds · w=1 full expert overlay · hard facts (out/susp) always override.",
    ]
    return "\n".join(lines)
