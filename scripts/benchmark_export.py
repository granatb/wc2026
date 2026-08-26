#!/usr/bin/env python3
"""Export one gameweek's frozen projections as a benchmark submission file.

Phase 2B / spec P4: the artifact for a third-party expected-points benchmark
(Onside's Open xPts Benchmark and anything shaped like it). Third-party
grading beats self-grading, so we make submitting mechanical.

    python3 scripts/benchmark_export.py --gw 2
    -> evmax/assets/benchmark/gw2-evmax.csv

    player_id,player_name,gameweek,predicted_points

THE SOURCE IS THE FROZEN SNAPSHOT, NEVER A RERUN. Rows come out of the
committed point-in-time envelopes under evmax/assets/projections/fpl-gw{N}/ —
the exact numbers published before that deadline. A gameweek with no snapshot
exports NOTHING and says so: re-simulating a finished gameweek would produce a
number we never published, which is precisely the failure mode a public
benchmark exists to catch. That refusal is a feature, not an error to work
around.

player_id is the official FPL element id, joined by name through the same
disambiguation the projections were built with. A name that will not join gets
an EMPTY id rather than a guessed one — a wrong id in a benchmark submission
grades someone else's player as ours.
"""

from __future__ import annotations

import argparse
import csv
import glob
import io
import json
import os
import sys

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

SNAPSHOT_ROOT = os.path.join(_HERE, "evmax", "assets", "projections")
BENCHMARK_DIR = os.path.join(_HERE, "evmax", "assets", "benchmark")

CSV_COLUMNS = ("player_id", "player_name", "gameweek", "predicted_points")


def snapshot_dir(gameweek: int, snapshot_root: str = None) -> str:
    return os.path.join(snapshot_root or SNAPSHOT_ROOT, f"fpl-gw{gameweek}")


def collect_rows(gameweek: int, snapshot_root: str = None) -> list:
    """[{name, x_points}] — every player the site published a number about
    that gameweek, deduplicated by name, ordered by projection descending.

    The graded universe is the union of every committed envelope's entries,
    matching scripts/grade_gw.py's `assemble` so the submission covers exactly
    the players our own accuracy page grades.
    """
    snap = snapshot_dir(gameweek, snapshot_root)
    paths = sorted(glob.glob(os.path.join(snap, "*.json")))
    if not paths:
        raise SystemExit(
            f"benchmark_export: no frozen snapshot for gameweek {gameweek} "
            f"under {snap}/ — nothing was published before that deadline, so "
            f"there is no submission to make. The submission file must come "
            f"from the projections as published; a finished gameweek is never "
            f"re-simulated to fill this in.")
    rows, seen = [], set()
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                envelope = json.load(fh)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"benchmark_export: {path} is unreadable ({exc}) "
                             f"— the snapshot is the published claim and must "
                             f"not be exported partially.")
        for entry in envelope.get("entries", []):
            name = entry.get("name")
            if name is None or name in seen or entry.get("x_points") is None:
                continue
            seen.add(name)
            rows.append({"name": name, "x_points": entry["x_points"]})
    if not rows:
        raise SystemExit(
            f"benchmark_export: the gameweek {gameweek} snapshot carries no "
            f"projected players — nothing to submit.")
    rows.sort(key=lambda r: (-r["x_points"], r["name"]))
    return rows


def element_ids(gameweek: int) -> dict:
    """{disambiguated name: FPL element id} from the bootstrap cache.

    Same join grade_gw.py makes: the priors' disambiguation is what the
    projection rows were named with, so the two sides agree on 'Cole Palmer'.
    An empty dict (no cache) is survivable — every id column comes out blank
    and the operator is told.
    """
    from core import fpl_api, fpl_priors

    boot = fpl_api.read_cache("bootstrap")
    if boot is None:
        return {}
    players = fpl_api.parse_players(boot)
    fpl_priors._disambiguate_names(players)
    return {p["name"]: p["id"] for p in players}


def to_csv(rows: list, gameweek: int, ids: dict) -> str:
    """RFC4180 CSV in the common submission shape."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        pid = ids.get(row["name"])
        writer.writerow(["" if pid is None else pid, row["name"], gameweek,
                         row["x_points"]])
    return buf.getvalue()


def export(gameweek: int, snapshot_root: str = None, out_dir: str = None,
           ids: dict = None) -> str:
    """Write evmax/assets/benchmark/gw{N}-evmax.csv; return its path.

    collect_rows runs FIRST so a gameweek with no snapshot never even creates
    the output directory — a stale or empty submission file on disk is worse
    than none.
    """
    rows = collect_rows(gameweek, snapshot_root)
    ids = element_ids(gameweek) if ids is None else ids
    target_dir = out_dir or BENCHMARK_DIR
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, f"gw{gameweek}-evmax.csv")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(to_csv(rows, gameweek, ids))
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Export a gameweek's frozen projections as a benchmark "
                    "submission CSV")
    ap.add_argument("--gw", type=int, required=True,
                    help="gameweek to export (must have a frozen snapshot)")
    ap.add_argument("--out", default=None,
                    help="output directory (default evmax/assets/benchmark)")
    args = ap.parse_args(argv)

    rows = collect_rows(args.gw)
    ids = element_ids(args.gw)
    matched = sum(1 for r in rows if ids.get(r["name"]) is not None)
    path = export(args.gw, out_dir=args.out, ids=ids)
    print(f"Benchmark submission → {path} ({len(rows)} players, "
          f"{matched} with an FPL element id)")
    if matched < len(rows):
        print(f"  !!! {len(rows) - matched} player(s) exported with an EMPTY "
              f"player_id — the bootstrap cache could not match the name. "
              f"Refresh with `python3 manage.py fpl --round {args.gw} "
              f"--refresh` and re-export before submitting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
