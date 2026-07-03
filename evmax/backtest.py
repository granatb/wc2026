"""Grade evmax's own PUBLISHED predictions against realized official FIFA fantasy
points. This is the site's credibility layer (/track-record/): honest, misses
included, everything computed deterministically from frozen point-in-time snapshots.

Public API
----------
load_snapshots(assets_dir=None) -> {round_no: {slug: envelope_dict}}
realized_points(round_no) -> {"points": {name: pts}, "matched": int, "total": int}
grade_round(round_no, snapshots, realized) -> {slug: grade_dict, ...}
round_status(round_no) -> "final" | "pending" | "no_snapshot"
build_track_record() -> {"rounds": [...], "summary": {...}}

No network I/O: realized_points reads the FIFA fantasy feed via core.fifa_api,
which is a local on-disk cache (data/fifa/*.json), populated by fifa_api.refresh().
"""
from __future__ import annotations

import glob
import json
import os
import re

from core import fifa_api, fixtures

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "assets", "projections")

# Articles that carry a ranked player list we can grade entry-by-entry. 'matches'
# is fixture 1X2 grading, deferred to v2 — see grade_round().
_GRADEABLE_LIST_ARTICLES = {
    "captains", "best-xi", "differentials", "risky", "defenders", "efficiency",
    "best-value-xi", "high-ceiling-xi", "blowout-transfers", "transfers",
}

_FINAL_STATUSES_PREFIXES = ("STATUS_FULL_TIME", "STATUS_FINAL")


# ---------------------------------------------------------------------------
# Loading snapshots
# ---------------------------------------------------------------------------

def load_snapshots(assets_dir: str | None = None) -> dict:
    """{round_no: {slug: envelope_dict}} from evmax/assets/projections/round-*/.

    Envelope dicts are exactly what was published (article_json() output) —
    the frozen ground truth of what evmax claimed, at lock time.
    """
    base = assets_dir or _ASSETS_DIR
    out: dict[int, dict] = {}
    if not os.path.isdir(base):
        return out
    for round_dir in sorted(glob.glob(os.path.join(base, "round-*"))):
        m = re.search(r"round-(\d+)$", round_dir)
        if not m:
            continue
        round_no = int(m.group(1))
        slugs: dict[str, dict] = {}
        for path in sorted(glob.glob(os.path.join(round_dir, "*.json"))):
            slug = os.path.splitext(os.path.basename(path))[0]
            with open(path, encoding="utf-8") as fh:
                slugs[slug] = json.load(fh)
        if slugs:
            out[round_no] = slugs
    return out


# ---------------------------------------------------------------------------
# Realized points (official FIFA fantasy feed, cached)
# ---------------------------------------------------------------------------

def _round_points_for_record(rec: dict, round_no: int):
    """Defensively pull roundPoints[str(round_no)] — the feed serializes an
    all-zero/empty round as `[]` (an empty list) instead of `{}`, so a plain
    dict.get() blows up unless we guard the type first."""
    stats = rec.get("stats") or {}
    rp = stats.get("roundPoints")
    if not isinstance(rp, dict):
        return None
    return rp.get(str(round_no))


def realized_points(round_no: int) -> dict:
    """canonical-name -> official FIFA fantasy points for `round_no`.

    Reads every published snapshot for the round to know which names need
    resolving, matches each to the FIFA feed via fifa_api.lookup (which uses
    core.players.name_match under the hood), and reports match coverage so a
    silently-broken feed or matcher is visible rather than swallowed.

    Returns {"points": {name: pts}, "matched": int, "total": int, "unmatched": [names]}
    """
    snapshots = load_snapshots()
    names: set[str] = set()
    for env in snapshots.get(round_no, {}).values():
        for e in env.get("entries", []):
            if "name" in e:
                names.add(e["name"])

    points: dict[str, float] = {}
    unmatched: list[str] = []
    for name in sorted(names):
        rec = fifa_api.lookup(name)
        if rec is None:
            unmatched.append(name)
            continue
        pts = _round_points_for_record(rec, round_no)
        if pts is None:
            # Matched the player, but the feed has no entry for this round yet
            # (DNP / not yet posted) — not a matching failure, just no data.
            continue
        points[name] = pts

    return {
        "points": points,
        "matched": len(points),
        "total": len(names),
        "unmatched": unmatched,
    }


# ---------------------------------------------------------------------------
# Round completeness gate
# ---------------------------------------------------------------------------

def _is_final_status(stage: str) -> bool:
    return any(stage.startswith(p) for p in _FINAL_STATUSES_PREFIXES)


def round_status(round_no: int) -> str:
    """'final' | 'pending' | 'no_snapshot'.

    A round is gradeable ('final') only once every one of its scheduled matches
    has reached a final match status (STATUS_FULL_TIME / STATUS_FINAL_*) — the
    completeness gate from data/schedule.json's `stage` field.
    """
    snapshots = load_snapshots()
    if round_no not in snapshots:
        return "no_snapshot"
    fx = fixtures.by_round(round_no)
    if not fx:
        return "pending"
    if all(_is_final_status(f.stage) for f in fx):
        return "final"
    return "pending"


# ---------------------------------------------------------------------------
# Statistics (stdlib only)
# ---------------------------------------------------------------------------

def _mae(pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    return sum(abs(a - b) for a, b in pairs) / len(pairs)


def _rank_average(values: list[float]) -> list[float]:
    """Fractional (average) ranks for `values`, ties sharing the mean rank.
    Rank 1 = largest value (descending — matches 'best pick ranked #1')."""
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=True)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation between two equal-length sequences, hand-rolled
    (stdlib only). Ties handled by average rank. None if fewer than 2 points or
    either sequence has zero variance (undefined correlation)."""
    n = len(xs)
    if n != len(ys) or n < 2:
        return None
    rx = _rank_average(xs)
    ry = _rank_average(ys)
    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n
    num = sum((a - mean_rx) * (b - mean_ry) for a, b in zip(rx, ry))
    den_x = sum((a - mean_rx) ** 2 for a in rx) ** 0.5
    den_y = sum((b - mean_ry) ** 2 for b in ry) ** 0.5
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

def _grade_list_article(slug: str, entries: list, realized: dict) -> dict:
    points = realized["points"]
    matched_rows = [(e, points[e["name"]]) for e in entries
                    if e.get("name") in points]
    total = len(entries)
    matched = len(matched_rows)

    if not matched_rows:
        return {"slug": slug, "graded": False, "matched": matched, "total": total,
                "reason": "no matched entries"}

    mae = _mae([(e.get("x_points", 0.0), realized_pts) for e, realized_pts in matched_rows])
    xs = [e.get("x_points", 0.0) for e, _ in matched_rows]
    ys = [realized_pts for _, realized_pts in matched_rows]
    rho = spearman(xs, ys)

    top_entry, top_realized = matched_rows[0]
    top_pick = {"name": top_entry["name"], "projected": top_entry.get("x_points"),
                "realized": top_realized}

    best_entry, best_realized = max(matched_rows, key=lambda t: t[1])
    best_in_list = {"name": best_entry["name"], "realized": best_realized}

    grade = {
        "slug": slug,
        "graded": True,
        "matched": matched,
        "total": total,
        "mae": round(mae, 3) if mae is not None else None,
        "spearman": round(rho, 3) if rho is not None else None,
        "top_pick": top_pick,
        "best_in_list": best_in_list,
    }

    if slug == "captains":
        grade["captain_regret"] = round(best_in_list["realized"] - top_pick["realized"], 3)

    if slug == "best-xi":
        grade["xi_projected_total"] = round(
            sum(e.get("x_points", 0.0) for e, _ in matched_rows), 3)
        grade["xi_realized_total"] = round(
            sum(r for _, r in matched_rows), 3)

    return grade


def grade_round(round_no: int, snapshots: dict, realized: dict) -> dict:
    """{slug: grade_dict} for every article published in this round's snapshot.

    'matches' is fixture 1X2 grading, deferred — marked not_graded here.
    Every other article gets the shared list-grading treatment; captains and
    best-xi get extra slug-specific fields (see _grade_list_article).
    """
    round_snaps = snapshots.get(round_no, {})
    grades: dict[str, dict] = {}
    for slug, env in round_snaps.items():
        if slug == "matches":
            grades[slug] = {"slug": slug, "graded": False,
                            "reason": "fixture grading not implemented in v1"}
            continue
        entries = env.get("entries", [])
        grades[slug] = _grade_list_article(slug, entries, realized)
    return grades


# ---------------------------------------------------------------------------
# Misses (honest, computed — not hand-written)
# ---------------------------------------------------------------------------

_BAD_CAPTAIN_THRESHOLD = 2.0


def _misses_for_round(round_no: int, grades: dict) -> list[str]:
    misses: list[str] = []
    for slug, g in sorted(grades.items()):
        if not g.get("graded"):
            continue
        top_pick = g.get("top_pick")
        if slug == "captains" and top_pick and top_pick.get("realized") is not None \
                and top_pick["realized"] <= _BAD_CAPTAIN_THRESHOLD:
            misses.append(
                f"Round {round_no} captains: top pick {top_pick['name']} scored only "
                f"{top_pick['realized']:.1f} pts (projected {top_pick['projected']:.1f}).")
        rho = g.get("spearman")
        if rho is not None and rho < 0:
            misses.append(
                f"Round {round_no} {slug}: our ranking was negatively correlated with "
                f"reality (Spearman {rho:.2f}).")
        regret = g.get("captain_regret")
        if regret is not None and regret > 0:
            misses.append(
                f"Round {round_no} captains: left {regret:.1f} pts on the table — "
                f"{g['best_in_list']['name']} ({g['best_in_list']['realized']:.1f} pts) "
                f"outscored our top pick {top_pick['name']} ({top_pick['realized']:.1f} pts).")
    return misses


# ---------------------------------------------------------------------------
# Top-level report
# ---------------------------------------------------------------------------

def build_track_record(assets_dir: str | None = None) -> dict:
    snapshots = load_snapshots(assets_dir)
    rounds_out = []

    all_captain_mae: list[float] = []
    all_spearman: list[float] = []
    captain_regrets: list[dict] = []

    for round_no in sorted(snapshots):
        status = round_status(round_no)
        round_entry = {
            "round": round_no,
            "status": status,
            "generated_at": _generated_at(snapshots[round_no]),
        }
        if status == "final":
            realized = realized_points(round_no)
            grades = grade_round(round_no, snapshots, realized)
            round_entry["grades"] = grades
            round_entry["coverage"] = {"matched": realized["matched"],
                                       "total": realized["total"]}
            round_entry["misses"] = _misses_for_round(round_no, grades)

            cap = grades.get("captains")
            if cap and cap.get("graded"):
                if cap.get("mae") is not None:
                    all_captain_mae.append(cap["mae"])
                if cap.get("spearman") is not None:
                    all_spearman.append(cap["spearman"])
                if cap.get("captain_regret") is not None:
                    captain_regrets.append({"round": round_no,
                                            "regret": cap["captain_regret"]})
            for g in grades.values():
                if g is cap or not g.get("graded"):
                    continue
                if g.get("spearman") is not None:
                    all_spearman.append(g["spearman"])
        else:
            round_entry["grades"] = {}
            round_entry["misses"] = []

        rounds_out.append(round_entry)

    rounds_out.sort(key=lambda r: r["round"], reverse=True)

    summary = {
        "rounds_graded": sum(1 for r in rounds_out if r["status"] == "final"),
        "mean_captain_mae": round(sum(all_captain_mae) / len(all_captain_mae), 3)
                           if all_captain_mae else None,
        "mean_spearman": round(sum(all_spearman) / len(all_spearman), 3)
                        if all_spearman else None,
        "captain_regrets": captain_regrets,
    }

    return {"rounds": rounds_out, "summary": summary}


def _generated_at(round_slugs: dict) -> str | None:
    for env in round_slugs.values():
        if "generated_at" in env:
            return env["generated_at"]
    return None
