#!/usr/bin/env python3
"""Daily FPL price-change watch — what moved overnight, and does it touch us.

WHY THIS IS SEPARATE FROM core.fpl_diff. The Thursday runbook's feed diff
already reports price moves, but it runs once a week and it ROTATES
data/fpl/feed_snapshot.json as it goes. That snapshot's timestamp is what the
publish gate compares research notes against ("a note clears a red flag only if
it is dated on/after the snapshot"), so running the feed diff daily would push
that date forward every morning and silently invalidate every note written the
day before. This watcher therefore keeps its OWN snapshot file and never
touches the feed one.

Prices move nightly, around 01:30 UK. Between Thursdays we were blind to them:
Watkins fell 8.0 -> 7.9 during GW1 week and the first anyone noticed was the
owner spotting it in the app.

    python3 scripts/price_watch.py              # diff against the last watch
    python3 scripts/price_watch.py --no-store   # look without rotating

Exit status is 0 whether or not anything moved; a price change is news, not a
failure. It is nonzero only when the feed could not be read.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from core import fpl_api                     # noqa: E402
from games.fpl import state as fpl_state     # noqa: E402

WATCH_CACHE = "price_watch"
STATE_FILES = ("state.json", "state_consensus.json")


def prices(bootstrap: dict) -> dict:
    """{element id as str: {name, team, price}} — everything the watch needs."""
    teams = fpl_api.parse_teams(bootstrap)
    return {str(e["id"]): {"name": e["web_name"],
                           "team": teams.get(e["team"], "???"),
                           "price": e["now_cost"] / 10.0}
            for e in bootstrap.get("elements", [])}


def changes(old: dict, new: dict) -> list:
    """Price moves between two snapshots, biggest fall first.

    A fall is listed before a rise of the same size: a fall costs real money on
    a player we own (FPL pays the current price when it is below what we paid),
    while a rise on a player we do not own only costs an opportunity.
    """
    out = []
    for pid, now in new.items():
        was = old.get(pid)
        if was is None or was.get("price") is None:
            continue
        delta = round(now["price"] - was["price"], 1)
        if delta:
            out.append({"id": pid, "name": now["name"], "team": now["team"],
                        "old": was["price"], "new": now["price"],
                        "delta": delta})
    out.sort(key=lambda r: (r["delta"], r["name"]))
    return out


def squad_names(root: str = HERE) -> dict:
    """{player name: [squad names holding them]} across both published states."""
    held: dict = {}
    for fname in STATE_FILES:
        path = os.path.join(root, "games", "fpl", fname)
        try:
            with open(path, encoding="utf-8") as fh:
                st = json.load(fh)
        except (OSError, ValueError):
            continue
        for entry in st.get("squad", []):
            held.setdefault(entry["name"], []).append(
                st.get("team_name", fname))
    return held


def report(rows: list, held: dict) -> str:
    if not rows:
        return "price watch: nothing moved since the last check."
    ours = [r for r in rows if r["name"] in held]
    lines = [f"price watch: {len(rows)} move(s), {len(ours)} in our squads"]
    if ours:
        lines.append("\nOURS:")
        for r in ours:
            who = ", ".join(held[r["name"]])
            lines.append(f"  {r['delta']:+.1f}  {r['name']} ({r['team']}) "
                         f"{r['old']:.1f} -> {r['new']:.1f}   [{who}]")
    rest = [r for r in rows if r["name"] not in held]
    if rest:
        lines.append("\nEVERYONE ELSE:")
        for r in rest:
            lines.append(f"  {r['delta']:+.1f}  {r['name']} ({r['team']}) "
                         f"{r['old']:.1f} -> {r['new']:.1f}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-store", action="store_true",
                    help="report without rotating the watch snapshot")
    ap.add_argument("--cached", action="store_true",
                    help="use the on-disk bootstrap instead of fetching")
    args = ap.parse_args(argv)

    boot = (fpl_api.read_cache("bootstrap") if args.cached
            else fpl_api.fetch_bootstrap())
    if not boot:
        print("price watch: could not read the FPL bootstrap", file=sys.stderr)
        return 1

    now = prices(boot)
    old = fpl_api.read_cache(WATCH_CACHE)
    if not old:
        print(f"price watch: FIRST RUN — recording {len(now)} prices, "
              f"nothing to compare against yet.")
        fpl_api.write_cache(WATCH_CACHE, now)
        return 0

    print(report(changes(old, now), squad_names()))
    if not args.no_store:
        fpl_api.write_cache(WATCH_CACHE, now)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
