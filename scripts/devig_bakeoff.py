#!/usr/bin/env python3
"""De-vig method bake-off: proportional vs Shin vs power, scored against realized
World Cup results on cached data only (no network).

Background: proportional normalisation ("de-vig by dividing by the booksum") is,
per Strumbelj (2014) and Hegarty & Whelan (2025), the worst mainstream de-vig method
— it understates favourites (the favourite-longshot bias). Shin's method (solves for
an insider-trading fraction z) and the power method (probs = raw^k, normalised) are
the leading challengers, and both give favourites MORE fair probability than
proportional for the same market.

For every match in fantasy rounds 1-4 (4 = R32, only once final) that has BOTH:
  (a) cached RAW 1X2 decimal odds in data/odds/<match_id>.json, and
  (b) a realized 90-minute result (regular time; matches decided in ET/pens are
      excluded — see EXCLUDED_ET below and the note in the report),
this script de-vigs with all three methods and scores each one's H/D/A probability
vector against the actual outcome with log loss (primary) and Brier score
(secondary). It also reports the mean favourite-probability shift (Shin vs
proportional) to size the favourite-longshot-bias correction.

Decision rule (see config.DEVIG_METHOD): flip the default away from "proportional"
ONLY if a challenger beats it on mean log loss with n>=40 matches. If n<40, this
script does NOT flip anything — it only reports.

Usage: python3 scripts/devig_bakeoff.py
"""

from __future__ import annotations

import json
import math
import os
import sys
from collections import defaultdict

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _HERE)

from core import fifa_api, odds_math  # noqa: E402

DATA_DIR = os.path.join(_HERE, "data")
ODDS_DIR = os.path.join(DATA_DIR, "odds")
SCHEDULE_PATH = os.path.join(DATA_DIR, "schedule.json")

METHODS = ("proportional", "shin", "power")
MIN_N_TO_FLIP = 40


def _log_loss(probs: tuple, outcome_idx: int, eps: float = 1e-12) -> float:
    p = max(min(probs[outcome_idx], 1 - eps), eps)
    return -math.log(p)


def _brier(probs: tuple, outcome_idx: int) -> float:
    return sum((p - (1.0 if i == outcome_idx else 0.0)) ** 2 for i, p in enumerate(probs))


def _outcome_idx(hs: int, aws: int) -> int:
    if hs > aws:
        return 0  # home
    if hs == aws:
        return 1  # draw
    return 2  # away


def load_schedule() -> list:
    with open(SCHEDULE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def load_raw_odds(match_id: str) -> dict | None:
    path = os.path.join(ODDS_DIR, f"{match_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def eligible_matches(max_round: int = 4) -> tuple[list, dict]:
    """Matches with BOTH cached raw 1X2 decimal odds AND a realized 90' result.

    Returns (rows, exclusions) where exclusions counts why matches were dropped, so
    the report can show the data-gap honestly instead of silently under-counting.
    """
    schedule = load_schedule()
    rows = []
    exclusions = defaultdict(int)
    seen_ids = set()
    for m in schedule:
        rnd = m.get("fantasy_round")
        if rnd is None or rnd > max_round:
            continue
        mid = m["match_id"]
        if mid in seen_ids:
            continue
        seen_ids.add(mid)

        cached = load_raw_odds(mid)
        if not cached:
            exclusions["no_cached_odds_file"] += 1
            continue
        h2h = cached.get("h2h")
        if not h2h or not all(h2h.get(k) for k in ("home", "draw", "away")):
            exclusions["no_raw_h2h_odds"] += 1
            continue

        home, away = m["home"], m["away"]
        hs, aws, status = fifa_api.actual_score(home, away)
        if hs is None or aws is None or status != "complete":
            exclusions["not_final"] += 1
            continue
        if fifa_api.went_to_et(home, away):
            # 90' Målspillet-style result unavailable/ambiguous for ET/pens games —
            # exclude rather than risk grading against an after-ET score.
            exclusions["excluded_et_or_pens"] += 1
            continue

        rows.append({
            "match_id": mid, "round": rnd, "home": home, "away": away,
            "decimal_odds": [h2h["home"], h2h["draw"], h2h["away"]],
            "hs": hs, "as": aws,
        })
    return rows, exclusions


def run_bakeoff(rows: list) -> dict:
    """Per-method: list of (log_loss, brier, favourite_prob) per match, by round."""
    results = {m: defaultdict(list) for m in METHODS}
    fav_shift = []  # (shin_fav_prob - proportional_fav_prob) per match
    for r in rows:
        odds = r["decimal_odds"]
        outcome = _outcome_idx(r["hs"], r["as"])
        probs_by_method = {m: odds_math.devig_by_method(odds, m) for m in METHODS}
        for m in METHODS:
            probs = probs_by_method[m]
            results[m]["log_loss"].append(_log_loss(probs, outcome))
            results[m]["brier"].append(_brier(probs, outcome))
            results[m]["round"].append(r["round"])
        prop_probs = probs_by_method["proportional"]
        shin_probs = probs_by_method["shin"]
        fav_i = max(range(3), key=lambda i: prop_probs[i])
        fav_shift.append(shin_probs[fav_i] - prop_probs[fav_i])
    return {"results": results, "fav_shift": fav_shift}


def _mean(xs: list) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def print_report(rows: list, exclusions: dict, bakeoff: dict) -> str:
    lines = []
    lines.append("=" * 66)
    lines.append("De-vig bake-off: proportional vs Shin vs power (cached data only)")
    lines.append("=" * 66)
    lines.append("")
    lines.append(f"Eligible matches (raw 1X2 odds cached + realized 90' result): {len(rows)}")
    if exclusions:
        lines.append("Excluded:")
        for reason, n in sorted(exclusions.items()):
            lines.append(f"  {reason:<24} {n}")
    lines.append("")

    results = bakeoff["results"]
    n = len(rows)
    lines.append(f"{'method':<14}{'n':>5}{'mean log loss':>16}{'mean brier':>14}")
    for m in METHODS:
        ll = _mean(results[m]["log_loss"])
        br = _mean(results[m]["brier"])
        lines.append(f"{m:<14}{n:>5}{ll:>16.4f}{br:>14.4f}" if n else
                      f"{m:<14}{n:>5}{'n/a':>16}{'n/a':>14}")
    lines.append("")

    if n:
        lines.append("Per-round breakdown (mean log loss):")
        by_round = defaultdict(set)
        for r in rows:
            by_round[r["round"]].add(r["match_id"])
        rounds_present = sorted(by_round)
        header = "  " + "".join(f"R{rd:<9}" for rd in rounds_present)
        lines.append(header)
        for m in METHODS:
            per_round_ll = defaultdict(list)
            for ll, rd in zip(results[m]["log_loss"], results[m]["round"]):
                per_round_ll[rd].append(ll)
            row = "  ".join(f"{_mean(per_round_ll[rd]):>8.4f}" if per_round_ll[rd] else "     n/a"
                            for rd in rounds_present)
            lines.append(f"  {m:<10}{row}")
        lines.append("")

        fav_shift = bakeoff["fav_shift"]
        lines.append(f"Mean favourite-probability shift (Shin - proportional): "
                     f"{_mean(fav_shift):+.4f} over n={len(fav_shift)}")
        lines.append("(Positive = Shin gives the favourite MORE probability than "
                     "proportional, the FLB correction.)")
    lines.append("")

    lines.append("-" * 66)
    lines.append("Decision")
    lines.append("-" * 66)
    if n < MIN_N_TO_FLIP:
        lines.append(
            f"n={n} < {MIN_N_TO_FLIP} required to flip the default -> "
            f"config.DEVIG_METHOD stays \"proportional\". NOT FLIPPED."
        )
        if n == 0:
            lines.append("")
            lines.append(
                "ROOT CAUSE: data/odds/<id>.json caches only retain the LATEST refresh's "
                "fields. core/espn.py derive_match() computes de-vigged p1x2/lambdas from "
                "raw h2h decimal odds but only persists the derived fields — the raw h2h "
                "block itself is dropped once ESPN stops serving live odds for a kicked-off "
                "match (save_match_odds merges {**prev, **data} and does not protect h2h "
                "from being overwritten to None, unlike lam_home/lam_away/rho which ARE "
                "explicitly preserved). data/ is gitignored with no other history, so raw "
                "1X2 odds for already-played rounds 1-3 matches are unrecoverable. The only "
                "matches with full raw h2h cached are R4/R5 fixtures still STATUS_SCHEDULED "
                "(no result yet). This bake-off will start producing real numbers once "
                "core/espn.py is fixed to also preserve h2h under the same rule as the "
                "lambdas, AND enough rounds complete with the fix live."
            )
    else:
        best = min(METHODS, key=lambda m: _mean(results[m]["log_loss"]))
        prop_ll = _mean(results["proportional"]["log_loss"])
        best_ll = _mean(results[best]["log_loss"])
        if best != "proportional" and best_ll < prop_ll:
            lines.append(
                f"n={n} >= {MIN_N_TO_FLIP}. \"{best}\" beats proportional on mean log loss "
                f"({best_ll:.4f} < {prop_ll:.4f}) -> FLIP config.DEVIG_METHOD to \"{best}\"."
            )
        else:
            lines.append(
                f"n={n} >= {MIN_N_TO_FLIP} but no challenger beats proportional on mean "
                f"log loss -> config.DEVIG_METHOD stays \"proportional\". NOT FLIPPED."
            )
    report = "\n".join(lines)
    print(report)
    return report


def main() -> None:
    rows, exclusions = eligible_matches(max_round=4)
    bakeoff = run_bakeoff(rows)
    print_report(rows, exclusions, bakeoff)


if __name__ == "__main__":
    main()
