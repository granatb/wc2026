#!/usr/bin/env python3
"""Write the gameweek's growth report: is the ratchet working?

docs/STRATEGY.md §1 treats the site as an event ratchet -- peaks with quiet
valleys between them, each peak meant to leave residue that raises the floor for
the next one. So this report is peak-over-peak, not week-over-week-in-a-vacuum:
each run snapshots its metrics into evmax/assets/growth/ (committed) and compares
against the highest gameweek below this one.

Usage:
    python3 scripts/growth_report.py --gw 1
    python3 scripts/growth_report.py --gw 2 --since 2026-08-08 --until 2026-08-12

The window defaults to "since the previous snapshot was written" through today,
which is the span the last report did not cover.

EVERY SOURCE DEGRADES ON ITS OWN. The three planned sources have three unrelated
auth stories and will essentially never all be configured at once, so an
unconfigured or failing source costs you its own section and nothing else. A run
with zero credentials present still writes a readable document -- one that names
the environment variable each missing source needs, because a report that
silently omits a source is worse than one that says it is switched off.

Nothing here runs in a reader's browser: sources are server-side or API-side
only, keeping /privacy/'s "no cookies, no analytics or trackers, no third-party
requests" true. See core/growth/__init__.py.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

# Allow running as `python3 scripts/growth_report.py` from anywhere: put the repo
# root (which holds core/ and evmax/) on the path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.growth import cloudflare, snapshot  # noqa: E402

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(_HERE, "data", "growth")

# Days of window to assume on the very first run, when no previous snapshot
# exists to measure from.
FIRST_RUN_WINDOW_DAYS = 7

TOP_N = 15

# Sources that exist. Each one satisfies the configured()/fetch() contract in
# core/growth/__init__.py. Adding a source here is all it takes to get it a
# section, a configured/not line, and its metrics into the snapshot.
SOURCES = [
    {
        "key": "cloudflare",
        "title": "Traffic (Cloudflare edge)",
        "module": cloudflare,
        "env": [cloudflare.TOKEN_ENV, cloudflare.ZONE_ENV],
    },
]

# Named so the report is honest about its own coverage: these are planned but
# unbuilt, and a blank space would read as "measured, nothing found".
PLANNED = [
    ("Search position", "Bing Webmaster API key"),
    ("Indexing coverage", "Google Search Console OAuth"),
    ("IndexNow acceptance", "submission log + Bing API key"),
    ("LLM citations", "manual prompt panel"),
    ("Reddit outcomes", "per-post karma and referral join"),
]


def default_window(gameweek: int, snapshot_dir: str | None = None) -> tuple[str, str]:
    """(since, until) as YYYY-MM-DD: from the previous snapshot through today."""
    today = dt.date.today()
    prev = snapshot.previous(gameweek, directory=snapshot_dir)
    since = None
    if prev:
        written = str(prev.get("written_at") or "")[:10]
        try:
            since = dt.date.fromisoformat(written)
        except ValueError:
            since = None
    if since is None:
        since = today - dt.timedelta(days=FIRST_RUN_WINDOW_DAYS)
    return since.isoformat(), today.isoformat()


def gather(since: str, until: str) -> dict:
    """Pull every source. A source that returns None is recorded, not raised.

    Nothing in here may propagate an exception: `fetch` swallows its own network
    and credential failures by contract, and the belt-and-braces `except` is
    here because one source's surprise must not cost the other sections.
    """
    results = {}
    for source in SOURCES:
        module = source["module"]
        configured = False
        payload = None
        why = None
        try:
            configured = bool(module.configured())
            payload = module.fetch(since, until)
            if payload is None:
                why = getattr(module, "last_error", lambda: None)()
        except Exception as exc:  # noqa: BLE001 - diagnostics must not die here
            payload, why = None, "%s: %s" % (type(exc).__name__, exc)
        results[source["key"]] = {"configured": configured, "data": payload,
                                  "why": why}
    return results


def metrics(results: dict) -> dict:
    """The flat numbers that get snapshotted and compared peak-over-peak.

    A source that produced nothing contributes NO key -- deliberately, not a
    zero. A fabricated zero would become next week's baseline and manufacture a
    growth figure out of an outage.
    """
    out: dict = {}
    cf = results.get("cloudflare", {}).get("data")
    if cf:
        out["cloudflare_requests"] = cf["total"]
        out["cloudflare_paths"] = len(cf["by_path"])
        out["cloudflare_referrers"] = len(cf["by_referrer"])
    return out


# --- rendering ---------------------------------------------------------------

def _table(counts: dict, header: str, limit: int = TOP_N) -> list[str]:
    lines = ["| %s | requests |" % header, "| --- | ---: |"]
    for name, count in list(counts.items())[:limit]:
        lines.append("| `%s` | %d |" % (name, count))
    if len(counts) > limit:
        lines.append("| _... %d more_ | |" % (len(counts) - limit))
    return lines


def render_cloudflare(result: dict, env: list[str]) -> list[str]:
    data = result.get("data")
    if data is None:
        return _unavailable(result, env)
    lines = ["**%d requests** across %d paths and %d referrer hosts."
             % (data["total"], len(data["by_path"]), len(data["by_referrer"])),
             ""]
    lines += _table(data["by_path"], "path")
    lines += ["", "Where they came from:", ""]
    lines += _table(data["by_referrer"], "referrer host")
    lines += ["", "_`direct` means the request arrived without a referrer host "
              "(typed, bookmarked, or a client that strips it)._"]
    return lines


def _unavailable(result: dict, env: list[str]) -> list[str]:
    """The line a switched-off source gets: what is missing, and how to fix it."""
    if not result.get("configured"):
        missing = ", ".join(env)
        return ["_Not configured — set %s to enable this section._" % missing]
    return ["_Unavailable — %s_" % (result.get("why") or "the source returned "
                                    "nothing for this window.")]


def render_delta(current: dict, previous: dict | None) -> list[str]:
    changes = snapshot.delta(current, previous)
    if changes is None:
        return ["_No previous peak — this is the first snapshot, so there is "
                "nothing to compare against yet. The next gameweek's report will "
                "measure against this one._"]
    label = "gameweek %s" % previous.get("gameweek")
    if not changes:
        return ["_A snapshot for %s exists, but it shares no comparable metric "
                "with this run — every source that would have produced one was "
                "unavailable in one of the two windows._" % label]
    lines = ["Against **%s** (written %s):" % (label, previous.get("written_at", "?")),
             "",
             "| metric | previous | now | change |",
             "| --- | ---: | ---: | ---: |"]
    for key, change in changes.items():
        pct = "n/a" if change["pct"] is None else "%+.1f%%" % change["pct"]
        lines.append("| %s | %s | %s | %+d (%s) |"
                     % (key, change["previous"], change["current"],
                        change["delta"], pct))
    lines += ["", "_A percentage of `n/a` means the baseline was zero: growth "
              "from nothing has no percentage._"]
    return lines


def render(gameweek: int, since: str, until: str, results: dict,
           current: dict, previous: dict | None) -> str:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = ["# Growth report — gameweek %d" % gameweek,
             "",
             "- Window: **%s → %s**" % (since, until),
             "- Generated: %s" % now,
             "",
             "Peak-over-peak by design (docs/STRATEGY.md §1): the question is "
             "whether this peak raised the floor, not how it compares to the "
             "valley behind it.",
             "",
             "## Peak over peak",
             ""]
    lines += render_delta(current, previous)

    for source in SOURCES:
        result = results.get(source["key"], {})
        lines += ["", "## %s" % source["title"], ""]
        if source["key"] == "cloudflare":
            lines += render_cloudflare(result, source["env"])
        else:  # pragma: no cover - no second source yet
            lines += _unavailable(result, source["env"])

    lines += ["", "## Source status", "",
              "| source | status | environment |",
              "| --- | --- | --- |"]
    for source in SOURCES:
        result = results.get(source["key"], {})
        if result.get("data") is not None:
            status = "ok"
        elif result.get("configured"):
            status = "configured, but no data (%s)" % (result.get("why") or "unknown")
        else:
            status = "not configured"
        lines.append("| %s | %s | `%s` |"
                     % (source["title"], status, "`, `".join(source["env"])))
    for title, need in PLANNED:
        lines.append("| %s | not implemented yet | %s |" % (title, need))

    lines += ["", "_Every source here is server-side or API-side only. Nothing "
              "runs in a reader's browser, so /privacy/'s promise of no cookies, "
              "no analytics and no third-party requests holds._", ""]
    return "\n".join(lines)


# --- cli ---------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Write the gameweek's growth report (peak over peak).",
        epilog="Runs to completion with no credentials configured; each "
               "switched-off source names the variable that would enable it.")
    ap.add_argument("--gw", type=int, required=True,
                    help="gameweek this report is labelled with")
    ap.add_argument("--since", help="window start, YYYY-MM-DD "
                                    "(default: the previous snapshot's date)")
    ap.add_argument("--until", help="window end, YYYY-MM-DD (default: today)")
    ap.add_argument("--snapshot-dir", default=None,
                    help=f"override the snapshot root (default {snapshot.SNAPSHOT_DIR})")
    ap.add_argument("--out-dir", default=REPORT_DIR,
                    help=f"where the markdown lands (default {REPORT_DIR})")
    ap.add_argument("--no-snapshot", action="store_true",
                    help="write the report but do not record a snapshot")
    args = ap.parse_args(argv)

    default_since, default_until = default_window(args.gw, args.snapshot_dir)
    since = args.since or default_since
    until = args.until or default_until

    results = gather(since, until)
    current = metrics(results)
    previous = snapshot.previous(args.gw, directory=args.snapshot_dir)

    text = render(args.gw, since, until, results, current, previous)

    os.makedirs(args.out_dir, exist_ok=True)
    path = os.path.join(args.out_dir,
                        "gw%d-%s.md" % (args.gw, dt.date.today().isoformat()))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)

    if not args.no_snapshot:
        # Written even when every source was dark: it keeps the ratchet's chain
        # of gameweeks intact and dates the next run's default window. It carries
        # no fabricated zeros -- see metrics().
        snapshot.write(args.gw, current, directory=args.snapshot_dir)

    for source in SOURCES:
        result = results.get(source["key"], {})
        if result.get("data") is None and not result.get("configured"):
            print("  %s: not configured — set %s"
                  % (source["title"], " and ".join(source["env"])))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
