"""Our own team strength table, fitted from accumulated market odds (spec D6).

Replaces the static FDR mapping as the source of FUTURE-gameweek lambdas once
enough real market data exists. The model is multiplicative, the same form as
core.ratings.match_lambdas:

    lam_home = BASE_GOALS * HOME_ADV * att_home * def_away
    lam_away = BASE_GOALS * att_away * def_home

Every PRICED match in the data/fpl/odds_gw{N}.json caches whose entry carries
no `source` field (i.e. real de-vigged market lambdas — the FDR priors are
stamped `source: "fdr_prior..."`) is an observation of the two teams' att/def
terms. The fit solves them in log space by iterative averaging: fix defences,
solve each team's attack as the weighted mean of

    log(lam) - log(BASE_GOALS) - (log(HOME_ADV) if at home) - log(def_opp)

then fix attacks and solve defences the same way; ten alternations is plenty
at 20 teams x a season of matches. Observations are recency-weighted
0.85^(current_gw - gw), and every fitted term is shrunk toward the pre-season
prior:

    final_log = (n_eff * fitted_log + K_SHRINK * prior_log) / (n_eff + K_SHRINK)

with n_eff the sum of that team's observation weights — one week of data
mostly believes the prior; six weeks mostly believe the market.

THE PRIOR is the FDR-calibrated table expressed as att/def multipliers.
Derivation (documented per the plan; exactness matters less than the
shrinkage direction): the GW1 calibration fitted market lambdas from the
opponent's FDR as  log(lam) = 1.056 - 0.242*FDR + 0.075*home  (mean abs error
22% on the 10 GW1 fixtures — docs/research/2026-08-19-squad-provenance.html).
Dropping the home term, exp(1.056 - 0.242*FDR) is what an average side scores
against an FDR-`d` opponent, so that opponent's DEFENCE multiplier is

    def_prior = exp(1.056 - 0.242*FDR) / BASE_GOALS

(FDR 3 lands at ~1.03 — near neutral, as it should). The calibration says
nothing about the team's own attack, so the prior assumes a side is as good
going forward as it is at the back:  att_prior = 1 / def_prior , which keeps
the league-average lambda at BASE_GOALS by construction. FDR values come from
the bootstrap's per-team `strength` field.

Pure fit; the cache-reading helpers touch local files only, mirroring
core/fpl_odds.read_cached. No network anywhere in this module.
"""

from __future__ import annotations

import math

import config

from core import fpl_api, fpl_odds

BASE = config.BASE_GOALS
HOME = config.HOME_ADV

# GW1 FDR calibration constants (squad-provenance doc, 2026-08-19).
FDR_CALIB_A = 1.056
FDR_CALIB_B = 0.242

DECAY = 0.85        # recency weight per gameweek of age
K_SHRINK = 2.0      # pseudo-observations of prior
ITERATIONS = 10

MAX_GW = 38


def prior_table(fdr_by_team: dict) -> dict:
    """{team: (att, def)} from FDR values — see the module docstring."""
    out = {}
    for team, fdr in (fdr_by_team or {}).items():
        if not fdr:
            continue
        dfn = math.exp(FDR_CALIB_A - FDR_CALIB_B * float(fdr)) / BASE
        out[team] = (1.0 / dfn, dfn)
    return out


def fdr_from_bootstrap(bootstrap) -> dict:
    """{short_name: strength} — FPL's own 2-5 difficulty per club."""
    if not bootstrap:
        return {}
    return {t["short_name"]: t.get("strength")
            for t in bootstrap.get("teams", []) if t.get("short_name")}


def _is_real(entry: dict) -> bool:
    """True for a priced real-market entry (the FDR priors stamp `source`)."""
    return (entry.get("lam_home") is not None
            and entry.get("lam_away") is not None
            and not str(entry.get("source") or "").startswith("fdr_prior"))


def observations(before_gw: int = MAX_GW + 1) -> list:
    """Every real-market priced match in the odds caches for gws < before_gw.

    Strictly BEFORE the target gameweek: the table prices future fixtures
    from settled market data, and the target week's own real odds (when they
    exist) are consumed directly by the model layer, never round-tripped
    through this fit.
    """
    out = []
    for gw in range(1, min(before_gw, MAX_GW + 1)):
        cached = fpl_odds.read_cached(gw)
        if not cached:
            continue
        for entry in (cached.get("matches") or {}).values():
            if _is_real(entry):
                out.append({"gw": gw, "home": entry["home"],
                            "away": entry["away"],
                            "lam_home": entry["lam_home"],
                            "lam_away": entry["lam_away"]})
    return out


def real_gw_count(before_gw: int = MAX_GW + 1) -> int:
    """How many distinct gameweeks before `before_gw` carry real market data."""
    return len({o["gw"] for o in observations(before_gw)})


def fit(obs: list, current_gw: int, prior: dict | None = None,
        decay: float = DECAY, k: float = K_SHRINK,
        iterations: int = ITERATIONS) -> dict:
    """{team: (att, def)} from observations. Pure — see the module docstring."""
    prior = prior or {}
    teams = {o["home"] for o in obs} | {o["away"] for o in obs} | set(prior)

    def prior_logs(team):
        att, dfn = prior.get(team, (1.0, 1.0))
        return math.log(att), math.log(dfn)

    att_log = {t: prior_logs(t)[0] for t in teams}
    def_log = {t: prior_logs(t)[1] for t in teams}

    # (team, weight, log-lambda, base-log, opponent) per attacking view and
    # per defending view of every observation.
    att_views, def_views = [], []
    for o in obs:
        w = decay ** max(0, current_gw - o["gw"])
        for scorer, conceder, lam, base in (
                (o["home"], o["away"], o["lam_home"], BASE * HOME),
                (o["away"], o["home"], o["lam_away"], BASE)):
            if not lam or lam <= 0:
                continue
            att_views.append((scorer, w, math.log(lam), math.log(base),
                              conceder))
            def_views.append((conceder, w, math.log(lam), math.log(base),
                              scorer))

    for _ in range(iterations):
        for views, solve_for, other in ((att_views, att_log, def_log),
                                        (def_views, def_log, att_log)):
            sums: dict = {}
            weights: dict = {}
            for team, w, log_lam, log_base, opp in views:
                resid = log_lam - log_base - other.get(opp, 0.0)
                sums[team] = sums.get(team, 0.0) + w * resid
                weights[team] = weights.get(team, 0.0) + w
            for team in teams:
                n_eff = weights.get(team, 0.0)
                if n_eff <= 0:
                    continue                      # no data: prior stands
                fitted = sums[team] / n_eff
                p_att, p_def = prior_logs(team)
                p = p_att if solve_for is att_log else p_def
                solve_for[team] = (n_eff * fitted + k * p) / (n_eff + k)

    return {t: (math.exp(att_log[t]), math.exp(def_log[t])) for t in teams}


def table(gw: int, bootstrap=None) -> dict:
    """The strength table for pricing gameweek `gw`, from all real market
    data before it, shrunk toward the FDR prior (bootstrap `strength`)."""
    boot = bootstrap if bootstrap is not None else fpl_api.read_cache(
        "bootstrap")
    return fit(observations(before_gw=gw), current_gw=gw,
               prior=prior_table(fdr_from_bootstrap(boot)))


def future_lambdas(home: str, away: str, strength: dict) -> tuple:
    """(lam_home, lam_away) for a future fixture off a fitted table.

    Unknown teams (a promoted club before its first priced match, a test
    fixture) price at league average rather than raising — the multiplicative
    form makes (1.0, 1.0) the natural identity.
    """
    att_h, def_h = strength.get(home, (1.0, 1.0))
    att_a, def_a = strength.get(away, (1.0, 1.0))
    return BASE * HOME * att_h * def_a, BASE * att_a * def_h
