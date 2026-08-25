#!/usr/bin/env python3
"""Grade one finished gameweek: our frozen projections vs ep_next vs reality.

The Monday runbook's first command (spec §6, the C-metric made public). Loads
the committed projection snapshots (evmax/assets/projections/fpl-gw{N}/), the
live payload (data/fpl/live_gw{N}.json — refreshed with --refresh once the
gameweek is done), joins realized total_points onto every player the site
published a claim about, and banks the result to
evmax/assets/accuracy/gw{N}.json (committed, exactly like the projections it
grades). A site surface for the accuracy league comes with the next site
phase; until then this prints the Monday-report table.

Usage:
    python3 scripts/grade_gw.py --gw 1
    python3 scripts/grade_gw.py --gw 2 --refresh   # fetch final live stats

The graded universe is the union of every committed envelope's entries for
that gameweek — every player we published a number about — deduplicated by
name; the squad-level projected-vs-realized lines come from the two squad
envelopes' own meta. GW1's snapshots predate the ep_next capture, so its
report says "no ep_next benchmark" rather than inventing one.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from core import fpl_api, fpl_live, fpl_priors           # noqa: E402
from games.fpl import grading                            # noqa: E402

SQUAD_SLUGS = ("our-squad", "consensus-squad")


def load_snapshots(gameweek: int) -> dict:
    """{slug: envelope} for every committed projection snapshot of this GW."""
    snap_dir = os.path.join(_HERE, "evmax", "assets", "projections",
                            f"fpl-gw{gameweek}")
    out = {}
    for path in sorted(glob.glob(os.path.join(snap_dir, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            out[os.path.splitext(os.path.basename(path))[0]] = json.load(fh)
    if not out:
        raise SystemExit(
            f"grade_gw: no committed snapshots under "
            f"evmax/assets/projections/fpl-gw{gameweek}/ — nothing was "
            f"published for that gameweek, so there is nothing to grade.")
    return out


def realized_points(gameweek: int, refresh: bool) -> dict:
    """{disambiguated player name: realized total_points} for the gameweek.

    Joins the live per-element stats onto names through the SAME
    disambiguation the projection rows were built with
    (core.fpl_priors._disambiguate_names), so 'Cole Palmer' grades as
    'Cole Palmer' on both sides.
    """
    payload = None
    if refresh:
        payload = fpl_live.refresh_live(gameweek)
    if payload is None:
        payload = fpl_live.read_live_cache(gameweek)
    if payload is None:
        raise SystemExit(
            f"grade_gw: no live payload for gameweek {gameweek} — fetch the "
            f"final stats with\n    python3 scripts/grade_gw.py "
            f"--gw {gameweek} --refresh")
    boot = fpl_api.read_cache("bootstrap")
    if boot is None:
        raise SystemExit(
            "grade_gw: data/fpl/bootstrap.json is missing — refresh with\n"
            f"    python3 manage.py fpl --round {gameweek} --refresh")
    players = fpl_api.parse_players(boot)
    fpl_priors._disambiguate_names(players)
    stats = {e["id"]: (e.get("stats") or {})
             for e in (payload.get("live") or {}).get("elements", [])}
    return {p["name"]: stats[p["id"]].get("total_points", 0)
            for p in players if p["id"] in stats}


def assemble(gameweek: int, envelopes: dict, realized: dict) -> dict:
    """The accuracy payload: player grading + the two squad lines."""
    rows, seen = [], set()
    for envelope in envelopes.values():
        for entry in envelope.get("entries", []):
            name = entry.get("name")
            if name is None or name in seen or "x_points" not in entry:
                continue
            seen.add(name)
            rows.append(entry)
    payload = {"gameweek": gameweek}
    payload.update(grading.grade(rows, realized))
    payload["squads"] = {
        slug: grading.squad_line(envelopes[slug], realized)
        for slug in SQUAD_SLUGS if slug in envelopes
    }
    return payload


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Grade a finished FPL gameweek's published projections")
    ap.add_argument("--gw", type=int, required=True, help="gameweek to grade")
    ap.add_argument("--refresh", action="store_true",
                    help="fetch the final live stats before grading")
    ap.add_argument("--out", default=os.path.join(_HERE, "evmax", "assets",
                                                  "accuracy"),
                    help="directory the accuracy JSON is banked to")
    args = ap.parse_args(argv)

    envelopes = load_snapshots(args.gw)
    realized = realized_points(args.gw, refresh=args.refresh)
    payload = assemble(args.gw, envelopes, realized)
    # Official FPL scoring (autosubs + captain fallback) alongside the
    # as-published grading line — readers compare official totals.
    try:
        from core import fpl_live
        from games.fpl import state as fpl_state
        lp = fpl_live.read_live_cache(args.gw)
        if lp:
            boot = fpl_api.read_cache("bootstrap")
            for slug, path in (("our-squad", "games/fpl/state.json"),
                               ("consensus-squad", "games/fpl/state_consensus.json")):
                st = fpl_state.load_state(path)
                g = fpl_live.grade_squad(st, lp["live"], lp["fixtures"], boot)
                if g["players_pending"] == 0:
                    payload["squads"][slug]["realized_official"] = g["total_so_far"]
                    payload["squads"][slug]["autosubs"] = g["autosubs_applied"]
    except Exception as exc:  # official line is additive; grading must still bank
        print(f"  (official-scoring line unavailable: {exc})")
    path = grading.write_accuracy(args.gw, payload, out_dir=args.out)
    print(grading.format_report(payload))
    print(f"\nbanked → {os.path.relpath(path, _HERE)} (commit it with the "
          f"Monday scorecard)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
