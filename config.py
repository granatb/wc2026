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
    "fpl":         {"team": "Granat65",     "research_weight": 0.30, "objective": "mean"},
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

# Which ESPN soccer league the odds client reads. "fifa.world" = 2026 World Cup,
# "eng.1" = Premier League. ESPN carries match odds (1X2 + totals) for both, but
# NO player-level props for eng.1 — verified 2026-07-28, all 172 prop markets on a
# sampled GW1 fixture were match-level. FPL player differentiation therefore comes
# from core/fpl_priors (xG-derived), not from props.
ESPN_LEAGUE = "fifa.world"

# ---------------------------------------------------------------------------
# Priors — the expert fallback used when no market odds exist (e.g. knockouts
# before teams are known). Multiplicative goal model around BASE_GOALS.
# ---------------------------------------------------------------------------
BASE_GOALS = 1.35
HOME_ADV = 1.07               # host-nation home advantage multiplier


# ---------------------------------------------------------------------------
# FPL priors
# ---------------------------------------------------------------------------
# How fast in-season per-90 rates displace last season's. Higher = trust the new
# season sooner. Set deliberately high for 2026/27: eight new managers, three
# British-record transfers, Salah gone from the league and three promoted clubs
# make last season's rates weaker priors than in a normal year. This is a
# judgement call, not a measured value — revisit once GW1-5 data exists.
FPL_PRIOR_SHRINKAGE_MATCHES = 6.0

# Cold-start fallback: expected non-penalty xG per 90 for a league-median-priced
# player, by position. Scaled by price relative to the position median, because
# FPL's price is itself a forecast of output. Used only for players with no
# Premier League history (promoted clubs, foreign signings).
FPL_COLD_START_XG90 = {"GK": 0.0, "DEF": 0.05, "MID": 0.12, "FWD": 0.28}
FPL_COLD_START_XA90 = {"GK": 0.0, "DEF": 0.06, "MID": 0.14, "FWD": 0.12}
FPL_MEDIAN_PRICE = {"GK": 4.5, "DEF": 4.5, "MID": 5.5, "FWD": 6.0}

# DefCon per-90 shrinkage (defect D): a raw defensive_contribution*90/minutes rate
# from a handful of minutes is noise, not signal -- against the real 2026-07-28
# backfill, a 1-minute cameo with a single alert action prints a 90.0 per-90 rate
# and would top the DefCon leaderboard ahead of genuine defensive midfielders with
# thousands of minutes behind their number. FPL_DEFCON_PRIOR pulls every observed
# rate toward a position baseline in proportion to how little of it is actually
# measured (see core.fpl_priors.shrink_defcon_rate).
#
# Measured 2026-07-28 from the 267 backfilled players with >=900 minutes (10 full
# matches) of last-season history -- the cohort large enough that its own ranking
# is already credible without any shrinkage. Values are the MEDIAN per-90 rate per
# position, chosen over the mean because it is a few points more robust to the
# handful of genuine DefCon specialists (Anderson, Bentancur, Wieffer, ...) who
# pull the mean up without being representative of the position as a whole.
# GK is 0.0 and MUST stay 0.0: goalkeepers do not accrue CBIT/CBIRT actions and
# are not DefCon-eligible at all (games/fpl/model.DEFCON_THRESHOLD has no "GK"
# key) -- shrink_defcon_rate hard-gates GK to 0.0 regardless of this table.
# This is last season's shape, not this season's -- a judgement call to revisit
# once 2026/27 in-season minutes accrue.
FPL_DEFCON_PRIOR = {"GK": 0.0, "DEF": 7.72, "MID": 7.96, "FWD": 4.46}

# Shrinkage strength, in pseudo-appearances (90-minute equivalents):
#   shrunk = (observed*appearances + prior*K) / (appearances + K)
# K is the appearance count at which the estimate is a 50/50 blend of a player's
# own sample and the position prior. K=3 (270 minutes, three full matches):
#   - a 1-minute cameo (0.01 appearances) lands essentially on the prior
#     (K completely dominates the tiny numerator/denominator contribution)
#   - a 3000+ minute season (33+ appearances) keeps ~92% of its own observed rate
#     (K is under a tenth of the denominator)
#   - the 200-900 minute band (2.2-10 appearances, ~72 of the 400 backfilled
#     players) sits in between: meaningfully pulled toward the prior (33%-77%
#     own weight) without being erased.
# Deliberately small and conservative rather than tuned to any downstream metric
# -- chosen from the appearance-count anchors above, not fit to the leaderboard.
FPL_DEFCON_SHRINKAGE_K = 3.0


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
