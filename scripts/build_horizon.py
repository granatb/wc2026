#!/usr/bin/env python3
"""Regenerate the horizon matrix the transfer optimizer reads.

WHY THIS FILE EXISTS (2026-08-27): three modules read
data/fpl/xpts_gw*.json -- the transfer optimizer, the player cards' six-week
strip, and the build's horizon lookup -- and NOTHING wrote it. It had been
produced by hand in an earlier session. By GW2 Thursday it was two days old,
predating that morning's odds, that week's research notes and a fix to the
minutes model, and the transfer table it produced was quietly wrong: the
forced Watkins sale did not appear in it at all. A file that three consumers
trust and no command regenerates will always drift.

It simulates each gameweek across the priced horizon exactly the way the
weekly build does -- same load_gameweek, same build_artifact, same cache --
so the matrix and the published order book cannot disagree.

    python3 scripts/build_horizon.py --from 2 --to 7
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from games.fpl import model as fpl_model   # noqa: E402


def build(first: int, last: int, sims: int, use_cache: bool = True) -> dict:
    """{name: {team, position, price, own, gw: {gw: xpts}}} over [first, last]."""
    matrix: dict = {}
    covered = []
    for gw in range(first, last + 1):
        try:
            priors_by_team, players_by_name, _cold = fpl_model.load_gameweek(gw)
        except SystemExit as exc:          # unpriced gameweek: stop, don't guess
            print(f"  gw{gw}: {exc} — horizon ends at gw{gw - 1}")
            break
        rows = fpl_model.build_rows(priors_by_team, players_by_name, gw, sims,
                                    use_cache=use_cache)
        for row in rows:
            entry = matrix.setdefault(row["name"], {
                "team": row.get("team"),
                "position": row.get("position"),
                "price": row.get("price"),
                "own": row.get("own"),
                "gw": {},
            })
            entry["gw"][str(gw)] = round(row["x_points"], 2)
        covered.append(gw)
        print(f"  gw{gw}: {len(rows)} players")
    if not covered:
        raise SystemExit("no gameweek in the range could be priced — refresh "
                         "odds first")
    return matrix, covered


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="first", type=int, required=True)
    ap.add_argument("--to", dest="last", type=int, required=True)
    ap.add_argument("--sims", type=int, default=50_000)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    matrix, covered = build(args.first, args.last, args.sims,
                            use_cache=not args.no_cache)
    out = os.path.join(HERE, "data", "fpl",
                       f"xpts_gw{covered[0]}_{covered[-1]}.json")
    # One live matrix at a time. The readers do sorted(glob("xpts_gw*.json"))[-1],
    # which is lexicographic and not numeric -- xpts_gw10_15 sorts BEFORE
    # xpts_gw2_7 -- so leaving siblings in place means the transfer table picks
    # its inputs by string luck. Retire the others by renaming: data/fpl is
    # gitignored, so a delete here is unrecoverable, and an old matrix is the
    # record of what we projected when a squad was picked.
    data_dir = os.path.join(HERE, "data", "fpl")
    for name in os.listdir(data_dir):
        path = os.path.join(data_dir, name)
        if name.startswith("xpts_gw") and name.endswith(".json") and path != out:
            os.rename(path, os.path.join(data_dir, "_retired_" + name))
            print(f"  retired stale matrix {name} → _retired_{name}")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(matrix, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print(f"horizon gw{covered[0]}-{covered[-1]} → {out} "
          f"({len(matrix)} players)")


if __name__ == "__main__":
    main()
