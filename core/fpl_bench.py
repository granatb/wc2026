"""The open benchmark — same-sample accuracy across public FPL predictors.

Owner asked for this roughly five times before it existed ("where is this
table with us comparing to other websites and their predictions?"), and the
2026-08-26 feasibility study had already decided its shape; Phase 2 shipped
the feature-comparison page and this fell out of the plan. The decisions that
survive from that study:

  - v1 columns are CLEAN SOURCES ONLY: evmax, Fantasy Football IQ (whose
    payload embeds "free to use in articles, videos, tools and research —
    attribution required"), FPL's own ep_next, and two naive baselines
    (season points per appearance, mean of the last four gameweeks).
  - The snapshot is taken BEFORE the deadline and committed to git — the
    commit timestamp is the proof of no lookahead, the one piece of
    infrastructure every dead benchmark before this lacked.
  - Grading is on the SAME players with the SAME error definition, published
    on two populations: everyone snapshotted, and the 60+ minute players —
    so the population effect is visible instead of hidden.
  - NOBODY's projections are republished. The snapshot file stays in the
    repo as evidence; the site publishes only derived metrics (MAE, RMSE, n),
    exactly as with bookmaker odds.

CLI:
    python3 -m core.fpl_bench --snapshot --gw 3    # Thursday, pre-deadline
    (grading runs inside scripts/grade_gw.py once the gameweek finishes)
"""
from __future__ import annotations

import json
import math
import os
import urllib.request
from datetime import datetime, timezone

from core import fpl_api, forecast_archive

FFIQ_URL = "https://fantasyfootballiq.app/data/ffiq-projections-latest.json"
FFIQ_ATTRIBUTION = "https://fantasyfootballiq.app"

BENCH_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "evmax", "assets", "bench")

# The 60+ minute grading population, following the only convention the field
# shares (Onside grades on it too).
FULL_SHIFT_MINUTES = 60


def _path(gameweek: int) -> str:
    return os.path.join(BENCH_DIR, f"gw{gameweek}.json")


def fetch_ffiq(url: str = FFIQ_URL, fetch=None) -> dict:
    """The FFIQ payload, verbatim. `fetch` injectable for tests."""
    if fetch is not None:
        return fetch(url)
    # Identify ourselves — FFIQ 403s the bare urllib agent, and a benchmark
    # that snapshots someone's data owes them an honest User-Agent anyway.
    req = urllib.request.Request(
        url, headers={"User-Agent": f"{fpl_api.USER_AGENT} "
                                    f"(evmax.ai open benchmark)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ffiq_column(payload: dict, gameweek: int) -> dict:
    """{(web_name, club): projected points} for one gameweek.

    Joined by name+club because FFIQ carries no element id; the club pin is
    what keeps a Sangaré-style collision from grading the wrong man.
    """
    out = {}
    for row in payload.get("players") or payload.get("rows") or []:
        for g in row.get("gws", []):
            if g.get("gw") == gameweek and g.get("proj") is not None:
                out[(row["web_name"], row["club"])] = float(g["proj"])
    return out


def our_column(gameweek: int) -> dict:
    """The exact archived full board; refuse an unrelated horizon vintage."""
    record = forecast_archive.load(gameweek)
    if record is None:
        raise SystemExit("bench snapshot: publish and archive the full board first")
    elements = {e["id"]: e for e in record["bootstrap"]["elements"]}
    return {(elements[r["player_id"]]["web_name"], r["team"]): float(r["x_points"])
            for r in record["rows"]}


def baseline_inputs(bootstrap: dict, form_history: dict, gameweek: int) -> dict:
    """Per-player frozen inputs the two naive baselines are computed from.

    Frozen INTO the snapshot on purpose: a baseline computed at grading time
    from a later bootstrap would quietly know the future.
    """
    teams = fpl_api.parse_teams(bootstrap)
    out = {}
    for e in bootstrap.get("elements", []):
        rows = (form_history or {}).get(str(e["id"])) \
            or (form_history or {}).get(e["id"]) or []
        rows = [r for r in rows if r.get("round", 0) < gameweek]
        played = [r["total_points"] for r in rows
                  if (r.get("minutes") or 0) > 0]
        appearances = len(played)
        out[f'{e["web_name"]}|{teams.get(e["team"], "???")}'] = {
            "player_id": e["id"],
            "season_points": sum(r.get("total_points", 0) for r in rows),
            "appearances": appearances,
            "last4": played[-4:],
            "ep_next": fpl_api._f(e.get("ep_next")) or 0.0,
        }
    return out


def take_snapshot(gameweek: int, ffiq_payload: dict = None,
                  bootstrap: dict = None, form_history: dict = None,
                  now=None) -> str:
    """Freeze every column for `gameweek` into evmax/assets/bench/gw{N}.json.

    Run BEFORE the deadline and committed; the git timestamp is the audit
    trail. Refuses to overwrite an existing snapshot — a benchmark whose
    frozen forecasts can be quietly replaced proves nothing.
    """
    path = _path(gameweek)
    if os.path.exists(path):
        raise SystemExit(f"bench snapshot for gw{gameweek} already exists "
                         f"({path}) — frozen means frozen")
    ffiq_payload = ffiq_payload or fetch_ffiq()
    bootstrap = bootstrap or fpl_api.read_cache("bootstrap")
    form_history = (form_history if form_history is not None
                    else fpl_api.read_cache(fpl_api.FORM_CACHE_NAME) or {})
    captured = forecast_archive.utc(now or datetime.now(timezone.utc))
    if captured >= forecast_archive.deadline(bootstrap, gameweek):
        raise SystemExit("benchmark snapshot: deadline passed")
    ffiq = ffiq_column(ffiq_payload, gameweek)
    ours = our_column(gameweek)
    snapshot = {
        "gameweek": gameweek,
        "taken_at": (now or datetime.now(timezone.utc)).isoformat(),
        "sources": {
            "evmax": "this repo, full pre-deadline forecast archive",
            "ffiq": {"url": FFIQ_URL,
                     "attribution": FFIQ_ATTRIBUTION,
                     "license": (ffiq_payload.get("license") or ""),
                     "generated_at": ffiq_payload.get("generated_at")},
            "ep_next": "official bootstrap-static at snapshot time",
            "baselines": "season pts/appearance and last-4 mean, inputs frozen here",
        },
        "evmax": {f"{n}|{c}": v for (n, c), v in ours.items()},
        "ffiq": {f"{n}|{c}": v for (n, c), v in ffiq.items()},
        "baseline_inputs": baseline_inputs(bootstrap, form_history, gameweek),
    }
    os.makedirs(BENCH_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return path


def load_snapshot(gameweek: int):
    try:
        with open(_path(gameweek), encoding="utf-8") as fh:
            return json.load(fh)
    except OSError:
        return None


def _errors(pred: dict, realized: dict) -> list:
    return [pred[k] - realized[k] for k in pred if k in realized]


def _mae(errs: list):
    return round(sum(abs(e) for e in errs) / len(errs), 3) if errs else None


def _rmse(errs: list):
    return (round(math.sqrt(sum(e * e for e in errs) / len(errs)), 3)
            if errs else None)


def grade_snapshot(snapshot: dict, realized_by_key: dict,
                   minutes_by_key: dict) -> dict:
    """Same-sample scores for every column in the snapshot.

    realized_by_key / minutes_by_key: {"web_name|CLUB": value} for the
    finished gameweek. Every nonempty source uses the common intersection across sources.
    Original coverage is reported separately; the 60+ group is selected after
    outcomes and is descriptive, not a pre-deadline selection rule.
    """
    inputs = snapshot.get("baseline_inputs") or {}
    columns = {
        "evmax": dict(snapshot.get("evmax") or {}),
        "ffiq": dict(snapshot.get("ffiq") or {}),
        "ep_next": {k: v["ep_next"] for k, v in inputs.items()},
        "baseline_ppg": {
            k: (v["season_points"] / v["appearances"])
            for k, v in inputs.items() if v["appearances"] > 0},
        "baseline_form4": {
            k: (sum(v["last4"]) / len(v["last4"]))
            for k, v in inputs.items() if v["last4"]},
    }
    # Every ranked score uses the same players, including the naive baselines.
    populated = [set(c) for c in columns.values() if c]
    common = set(realized_by_key).intersection(*populated) if populated else set()
    out = {}
    for source, original in columns.items():
        pred = {k: v for k, v in original.items() if k in common}
        full = {k: v for k, v in pred.items()
                if (minutes_by_key.get(k) or 0) >= FULL_SHIFT_MINUTES}
        errs_all = _errors(pred, realized_by_key)
        errs_60 = _errors(full, realized_by_key)
        out[source] = {
            "mae_all": _mae(errs_all), "n_all": len(errs_all),
            "rmse_all": _rmse(errs_all),
            "coverage_all": len(_errors(original, realized_by_key)),
            "population": "common_intersection",
            "mae_60plus": _mae(errs_60), "rmse_60plus": _rmse(errs_60),
            "n_60plus": len(errs_60),
        }
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--gw", type=int, required=True)
    args = ap.parse_args(argv)
    if args.snapshot:
        path = take_snapshot(args.gw)
        snap = load_snapshot(args.gw)
        print(f"bench: frozen gw{args.gw} → {path}")
        print(f"  evmax {len(snap['evmax'])} players · "
              f"ffiq {len(snap['ffiq'])} players · "
              f"baseline inputs {len(snap['baseline_inputs'])}")
        print("  COMMIT THIS FILE NOW — the git timestamp is the proof.")
        return 0
    ap.error("nothing to do — pass --snapshot")


if __name__ == "__main__":
    raise SystemExit(main())


# =============================================================================
# Squads: other sites' published teams, graded on official points
# =============================================================================
# The owner's actual question (2026-09-03): "I thought some sides will have
# their teams and models and recommend stuff and we could compare to them."
# A per-player error table is the analyst's view; the reader's view is the
# duel extended to other sites — whose recommended XI scored what. Sources are
# captured pre-deadline exactly as ours are, and graded the way FPL grades a
# team: XI points with the captain doubled. No autosubs unless a bench and its
# order were published (the two v1 sources publish a bench without a formal
# order, so v1 grades the XI as named — stated on the page).

SQUADS_SOURCES = {
    "ffs_scout_picks": {"label": "Fantasy Football Scout — Scout Picks",
                        "home": "https://www.fantasyfootballscout.co.uk"},
    "ffiq_ai_squad": {"label": "Fantasy Football IQ — IQ AI's squad",
                      "home": "https://fantasyfootballiq.app"},
}


def _squads_path(gameweek: int) -> str:
    return os.path.join(BENCH_DIR, f"squads_gw{gameweek}.json")


def load_squads(gameweek: int):
    try:
        with open(_squads_path(gameweek), encoding="utf-8") as fh:
            return json.load(fh)
    except OSError:
        return None


def freeze_squads(gameweek: int, squads: dict, now=None) -> str:
    """Freeze other sites' published XIs for `gameweek`.

    squads: {source_key: {"url", "published_at", "label"?, "xi": [[web_name,
    club], ...], "captain": web_name, "vice": web_name|None, "bench":
    [[web_name, club], ...], "status": "early"|"final"}}. A source may be
    re-frozen with a later 'final' version ONLY while the gameweek is still
    open — the file records both, and grading uses the latest one taken before
    the deadline.
    """
    path = _squads_path(gameweek)
    existing = load_squads(gameweek) or {"gameweek": gameweek, "versions": []}
    existing["versions"].append({
        "taken_at": (now or datetime.now(timezone.utc)).isoformat(),
        "squads": squads,
    })
    os.makedirs(BENCH_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(existing, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return path


def latest_squads(frozen: dict, deadline_iso: str = None) -> dict:
    """The newest frozen version taken before the deadline (or the newest)."""
    versions = frozen.get("versions") or []
    if deadline_iso:
        lock = forecast_archive.utc(deadline_iso)
        versions = [v for v in versions if forecast_archive.utc(v["taken_at"]) < lock]
    versions = sorted(versions, key=lambda v: forecast_archive.utc(v["taken_at"]))
    return versions[-1]["squads"] if versions else {}


def grade_squads(squads: dict, realized_by_key: dict) -> dict:
    """{source: {"points", "captain", "captain_points", "missing": [...]}}.

    XI points summed on official realized points, captain doubled. A player
    the join cannot find is listed under `missing` and scores 0, so a broken
    name never silently inflates or deflates a total.
    """
    out = {}
    for source, sq in squads.items():
        total, missing = 0, []
        for name, club in sq.get("xi", []):
            key = f"{name}|{club}"
            if key not in realized_by_key:
                missing.append(key); continue
            pts = realized_by_key[key]
            if name == sq.get("captain"):
                pts *= 2
            total += pts
        cap_key = next((f"{n}|{c}" for n, c in sq.get("xi", [])
                        if n == sq.get("captain")), None)
        out[source] = {
            "points": total,
            "captain": sq.get("captain"),
            "captain_points": realized_by_key.get(cap_key) if cap_key else None,
            "missing": missing,
            "status": sq.get("status"),
            "url": sq.get("url"),
        }
    return out
