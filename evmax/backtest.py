"""Grade evmax's own PUBLISHED predictions against realized official FIFA fantasy
points. This is the site's credibility layer (/track-record/): honest, misses
included, everything computed deterministically from frozen point-in-time snapshots.

Public API
----------
load_snapshots(assets_dir=None) -> {round_no: {slug: envelope_dict}}
realized_points(round_no) -> {"points": {name: pts}, "matched": int, "total": int}
grade_round(round_no, snapshots, realized) -> {slug: grade_dict, ...}
round_status(round_no) -> "final" | "pending" | "no_snapshot"
retrospective_round(fantasy_round) -> {"round", "status", "kind", "grades", "note"}
build_track_record() -> {"rounds": [...], "summary": {...}}

No network I/O: realized_points reads the FIFA fantasy feed via core.fifa_api,
which is a local on-disk cache (data/fifa/*.json), populated by fifa_api.refresh().
retrospective_round reruns the simulation engine, but only against on-disk
caches (data/odds, data/schedule.json, research/) — still no live network I/O.
"""
from __future__ import annotations

import glob
import json
import os
import re

from core import engine_events, espn, fifa_api, fixtures, research

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "assets", "projections")

# Articles that carry a ranked player list we can grade entry-by-entry. 'matches'
# is fixture 1X2 grading, deferred to v2 — see grade_round().
_GRADEABLE_LIST_ARTICLES = {
    "captains", "best-xi", "differentials", "risky", "defenders", "efficiency",
    "best-value-xi", "high-ceiling-xi", "blowout-transfers", "transfers",
}

_FINAL_STATUSES_PREFIXES = ("STATUS_FULL_TIME", "STATUS_FINAL")

# Owner decision 2026-07-04: hide Round 3 from the public track record for now.
# Snapshots are kept untouched on disk at evmax/assets/projections/round-3/ —
# nothing is deleted. Flip this set (remove 3, or empty it) to re-enable.
EXCLUDED_DISPLAY_ROUNDS = {3}

# Rounds that were NEVER PUBLISHED on the site (no frozen pre-lock snapshot)
# but are reconstructed after the fact, purely for context. These are graded
# and shown in the rounds list, explicitly labeled "retrospective", but are
# always excluded from the published-record summary aggregates — mixing them
# in would overclaim a track record we don't actually have for that round.
# See retrospective_round().
RETROSPECTIVE_ROUNDS = {4}

# Articles graded for a retrospective round. Kept deliberately narrow (vs. the
# full published article set) to avoid overclaiming from a reconstruction.
_RETROSPECTIVE_ARTICLES = ("captains", "best-xi")


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


def live_xi_progress(round_no: int, snapshots: dict | None = None,
                     realized: dict | None = None,
                     finished_teams: set | None = None):
    """Mid-round progress of the round's PUBLISHED XI (the frozen wildcard
    snapshot): realized official points so far vs what those same
    already-played players were projected for, and their combined ceiling.

    This is a live element by design — the published articles stay frozen at
    lock, but the owner explicitly wants "expected vs realised" reality
    panels (matches scoreboard, track record, and this XI strip) to update as
    games finish. Sums cover ONLY the XI players whose team's fixture is
    final, so expected/ceiling stay comparable to realized (no credit for
    games not yet played). No captain doubling: the published wildcard XI is
    graded as a flat XI total (same basis as its xi_xpoints meta).

    Returns {played, total, realized, expected, ceiling} or None when there is
    no snapshot for the round or nothing has finished yet.

    snapshots/realized/finished_teams are injectable for tests; production
    callers pass nothing and get the cached feeds.
    """
    snapshots = load_snapshots() if snapshots is None else snapshots
    env = (snapshots.get(round_no) or {}).get("wildcard") \
        or (snapshots.get(round_no) or {}).get("best-xi")
    if not env:
        return None
    entries = env.get("entries", [])
    xi = [e for e in entries if e.get("role") == "XI"] or entries[:11]
    if not xi:
        return None
    if finished_teams is None:
        finished_teams = {t for f in fixtures.by_round(round_no)
                          if _is_final_status(f.stage) for t in (f.home, f.away)}
    played = [e for e in xi if e.get("team") in finished_teams]
    if not played:
        return None
    if realized is None:
        realized = realized_points(round_no)["points"]
    return {
        "played": len(played),
        "total": len(xi),
        # so-far: only the already-played XI players, so the three numbers
        # stay comparable to each other
        "realized": round(sum(realized.get(e["name"], 0.0) for e in played), 1),
        "expected": round(sum(e.get("x_points") or 0.0 for e in played), 1),
        "ceiling": round(sum(e.get("ceiling") or 0.0 for e in played), 1),
        # full-round target: all 11, what the XI is aiming for by round end
        "expected_total": round(sum(e.get("x_points") or 0.0 for e in xi), 1),
        "ceiling_total": round(sum(e.get("ceiling") or 0.0 for e in xi), 1),
    }


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


def grade_entries_map(entries_by_slug: dict, realized: dict) -> dict:
    """{slug: grade_dict} for an in-memory {slug: entries_list} map.

    Shared per-list grading logic factored out of grade_round() so it can be
    reused both for published snapshots (loaded from disk) and for
    retrospective reconstructions (held only in memory — never written as a
    published snapshot). 'matches' is fixture 1X2 grading, deferred — marked
    not_graded here, same as grade_round().
    """
    grades: dict[str, dict] = {}
    for slug, entries in entries_by_slug.items():
        if slug == "matches":
            grades[slug] = {"slug": slug, "graded": False,
                            "reason": "fixture grading not implemented in v1"}
            continue
        grades[slug] = _grade_list_article(slug, entries, realized)
    return grades


def grade_round(round_no: int, snapshots: dict, realized: dict) -> dict:
    """{slug: grade_dict} for every article published in this round's snapshot.

    'matches' is fixture 1X2 grading, deferred — marked not_graded here.
    Every other article gets the shared list-grading treatment; captains and
    best-xi get extra slug-specific fields (see _grade_list_article).
    """
    round_snaps = snapshots.get(round_no, {})
    entries_by_slug = {slug: env.get("entries", []) for slug, env in round_snaps.items()}
    return grade_entries_map(entries_by_slug, realized)


# ---------------------------------------------------------------------------
# Retrospective backtests (rounds never published on the site)
# ---------------------------------------------------------------------------

_RETROSPECTIVE_NOTE = (
    "Reconstructed after the fact from frozen closing odds (research overlay "
    "off, fixed seed). NOT published predictions.")


def _kickoffs_for_round(fantasy_round: int) -> dict:
    """team -> earliest ISO-8601 kickoff string for the round. Same pattern as
    evmax.build._kickoffs_for_round, duplicated here (rather than imported) to
    avoid a circular import (evmax.build already imports evmax.backtest)."""
    out = {}
    for f in fixtures.by_round(fantasy_round):
        for team in (f.home, f.away):
            iso = f.kickoff.isoformat()
            if team not in out or iso < out[team]:
                out[team] = iso
    return out


# _retrospective_entries is a ~1-minute 50k-sim rerun whose inputs (frozen
# closing odds on disk) and seed are fixed -- the output is deterministic per
# round. Memoize per process: a build calls it once anyway, but the test
# suite was recomputing the identical result for every track-record test
# (7 tests x ~58s was most of the suite's runtime).
_RETRO_ENTRIES_CACHE: dict[int, dict] = {}


def _retrospective_entries(fantasy_round: int) -> dict:
    """Rerun the engine reproducibly from on-disk caches and build the narrow
    {slug: entries} set graded for a retrospective round (captains, best-xi).

    research_weight=0.0 is deliberate: current research/ notes for an already-
    finished round are written post-hoc (with the result known), so overlaying
    them here would leak hindsight into a "prediction". Pure odds only.
    """
    cached = _RETRO_ENTRIES_CACHE.get(fantasy_round)
    if cached is not None:
        return cached

    from evmax import articles

    players, _match_samples = engine_events.simulate_round(
        fantasy_round, sims=50_000,
        market_rates=espn.load_player_rates(fantasy_round),
        research=research.load_entries("players", fantasy_round),
        research_weight=0.0)
    means = engine_events.event_means(players)
    samples = {name: ps.goal_samples for name, ps in players.items()}
    meta = articles.load_player_meta()
    kickoffs = _kickoffs_for_round(fantasy_round)
    rows = articles.build_rows(means, samples, meta, kickoffs)

    out = {
        "captains": articles.rank_captains(rows)[:20],
        "best-xi": articles.select_xi(rows, "x_points"),
    }
    _RETRO_ENTRIES_CACHE[fantasy_round] = out
    return out


def retrospective_round(fantasy_round: int) -> dict:
    """Grade a round that was NEVER PUBLISHED, by reconstructing it after the
    fact from frozen closing odds. Structurally and visually distinct from
    published rounds ("kind": "retrospective") — see render.py's badge/note
    handling. Grading uses the same per-list metrics as published rounds
    (grade_entries_map / _grade_list_article), just on in-memory entries.
    """
    status = round_status_ignoring_snapshot(fantasy_round)
    round_entry = {
        "round": fantasy_round,
        "status": status,
        "kind": "retrospective",
        "generated_at": None,
        "note": _RETROSPECTIVE_NOTE,
    }
    if status != "final":
        round_entry["grades"] = {}
        round_entry["misses"] = []
        return round_entry

    entries_by_slug = _retrospective_entries(fantasy_round)
    realized = realized_points_for_entries(fantasy_round, entries_by_slug)
    grades = grade_entries_map(entries_by_slug, realized)
    round_entry["grades"] = grades
    round_entry["coverage"] = {"matched": realized["matched"], "total": realized["total"]}
    round_entry["misses"] = _misses_for_round(fantasy_round, grades)
    return round_entry


def round_status_ignoring_snapshot(round_no: int) -> str:
    """Like round_status(), but for rounds with no published snapshot at all
    (retrospective rounds) — gated purely on fixture completeness."""
    fx = fixtures.by_round(round_no)
    if not fx:
        return "pending"
    if all(_is_final_status(f.stage) for f in fx):
        return "final"
    return "pending"


def realized_points_for_entries(round_no: int, entries_by_slug: dict) -> dict:
    """Same contract as realized_points(), but sources the player-name universe
    from an in-memory {slug: entries} map instead of on-disk snapshots — needed
    for retrospective rounds, which have no snapshot to read names from."""
    names: set[str] = set()
    for entries in entries_by_slug.values():
        for e in entries:
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
            continue
        points[name] = pts

    return {
        "points": points,
        "matched": len(points),
        "total": len(names),
        "unmatched": unmatched,
    }


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
    """Build the public track record.

    Three kinds of round can appear in the output:
      - published, excluded (EXCLUDED_DISPLAY_ROUNDS): skipped entirely — not
        in the rounds list, not in summary aggregates. Data/snapshots on disk
        are untouched; this is a display-only filter.
      - published (everything else with a snapshot): graded normally,
        "kind": "published", counted in summary aggregates.
      - retrospective (RETROSPECTIVE_ROUNDS): never had a published snapshot;
        reconstructed after the fact via retrospective_round(). Shown in the
        rounds list (interleaved newest-first like any other round) but
        ALWAYS excluded from summary aggregates — mixing a reconstruction
        into the published-record stats would overclaim a track record we
        don't actually have for that round.
    """
    snapshots = load_snapshots(assets_dir)
    rounds_out = []

    all_captain_mae: list[float] = []
    all_spearman: list[float] = []
    captain_regrets: list[dict] = []

    for round_no in sorted(snapshots):
        if round_no in EXCLUDED_DISPLAY_ROUNDS:
            continue

        status = round_status(round_no)
        round_entry = {
            "round": round_no,
            "status": status,
            "kind": "published",
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

    # Retrospective rounds: never published, so they have no on-disk snapshot
    # and are never in `snapshots` above — add them explicitly. Deliberately
    # NOT folded into all_captain_mae / all_spearman / captain_regrets.
    for round_no in sorted(RETROSPECTIVE_ROUNDS):
        if round_no in EXCLUDED_DISPLAY_ROUNDS:
            continue
        rounds_out.append(retrospective_round(round_no))

    rounds_out.sort(key=lambda r: r["round"], reverse=True)

    summary = {
        "rounds_graded": sum(1 for r in rounds_out
                             if r["status"] == "final" and r.get("kind") == "published"),
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
