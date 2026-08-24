"""FPL feed diff — the churn detector the Thursday runbook starts with.

Compares the current bootstrap against the last stored snapshot summary
(data/fpl/feed_snapshot.json) and reports every kind of churn that burned the
site in GW1: renames (the wrong-Sangaré failure), club moves (Konsa), new and
removed players, status transitions, price moves, and transfer-out spikes (the
Watkins exodus — 50k managers selling while we held).

Pure diff logic, offline-tested; network lives only in `main()` via an
injectable fetch, mirroring core/fpl_api.py's split. The snapshot is a compact
projection keyed by element id (as a string, so it JSON round-trips):

    {"taken_at": iso, "<id>": {web_name, team_short, status, price,
                               selected_pct, tin, tout}, ...}

CLI:
    python3 -m core.fpl_diff
fetches the live bootstrap, diffs it against the stored snapshot, prints the
human report grouped by category (loudly announcing a FIRST RUN when no
snapshot exists yet), then stores the new snapshot for next time.
"""

from __future__ import annotations

from datetime import datetime, timezone

from core import fpl_api

SNAPSHOT_CACHE = "feed_snapshot"

# Transfer-out z-score threshold. Calibrated on the GW1 shape: one player with
# 50k transfers out among ~500 players around 2k sits near z=20; the everyday
# churn of the population stays well under 3.
OUTFLOW_Z_THRESHOLD = 3.0


def snapshot(bootstrap: dict, now=None) -> dict:
    """The compact per-player projection of one bootstrap payload.

    Deliberately does NOT carry the news string: news is free text that changes
    wording without changing meaning, and the report tells the operator to
    check the feed for it instead of diffing prose.
    """
    teams = fpl_api.parse_teams(bootstrap)
    snap = {"taken_at": (now or datetime.now(timezone.utc)).isoformat()}
    for e in bootstrap.get("elements", []):
        snap[str(e["id"])] = {
            "web_name": e["web_name"],
            "team_short": teams.get(e["team"], "???"),
            "status": e.get("status", "a"),
            "price": e["now_cost"] / 10.0,
            "selected_pct": fpl_api._f(e.get("selected_by_percent")),
            "tin": e.get("transfers_in_event", 0) or 0,
            "tout": e.get("transfers_out_event", 0) or 0,
        }
    return snap


def _players(snap: dict) -> dict:
    return {pid: p for pid, p in snap.items() if pid != "taken_at"}


def outflow_spikes(snap: dict, threshold: float = OUTFLOW_Z_THRESHOLD) -> list:
    """Players whose transfers-out z-score crosses `threshold`.

    The z-score is computed over every player with tout > 0 — including the
    zeros would shrink the mean toward nothing and flag ordinary churn. Public
    on purpose: the publish gate (games/fpl/dossier via evmax/fpl_build) reads
    the same spike list off the CURRENT snapshot, so the diff report and the
    gate can never disagree about who is being sold.
    """
    players = _players(snap)
    touts = [p["tout"] for p in players.values() if p["tout"] > 0]
    if len(touts) < 2:
        return []
    mean = sum(touts) / len(touts)
    std = (sum((t - mean) ** 2 for t in touts) / len(touts)) ** 0.5
    if std == 0:
        return []
    out = []
    for pid, p in players.items():
        if p["tout"] <= 0:
            continue
        z = (p["tout"] - mean) / std
        if z >= threshold:
            out.append({"id": pid, "name": p["web_name"],
                        "team": p["team_short"], "tout": p["tout"],
                        "z": round(z, 2)})
    out.sort(key=lambda r: -r["z"])
    return out


def diff(old: dict | None, new: dict) -> dict:
    """Categorised churn between two snapshots.

    `old` may be None (no stored snapshot yet) — that returns
    {"first_run": True} so the caller can be loud about it rather than
    printing a misleading all-quiet report.
    """
    if old is None:
        return {"first_run": True}

    old_p, new_p = _players(old), _players(new)
    renamed, moved, status_changed, price_changed = [], [], [], []
    for pid in sorted(set(old_p) & set(new_p), key=int):
        o, n = old_p[pid], new_p[pid]
        if o["web_name"] != n["web_name"]:
            renamed.append({"id": pid, "old": o["web_name"],
                            "new": n["web_name"], "team": n["team_short"]})
        if o["team_short"] != n["team_short"]:
            moved.append({"id": pid, "name": n["web_name"],
                          "old": o["team_short"], "new": n["team_short"]})
        if o["status"] != n["status"]:
            status_changed.append({"id": pid, "name": n["web_name"],
                                   "team": n["team_short"],
                                   "old": o["status"], "new": n["status"]})
        if o["price"] != n["price"]:
            price_changed.append({"id": pid, "name": n["web_name"],
                                  "team": n["team_short"],
                                  "old": o["price"], "new": n["price"]})

    arrived = [{"id": pid, "name": new_p[pid]["web_name"],
                "team": new_p[pid]["team_short"], "price": new_p[pid]["price"]}
               for pid in sorted(set(new_p) - set(old_p), key=int)]
    departed = [{"id": pid, "name": old_p[pid]["web_name"],
                 "team": old_p[pid]["team_short"]}
                for pid in sorted(set(old_p) - set(new_p), key=int)]

    return {
        "renamed": renamed,
        "moved": moved,
        "status_changed": status_changed,
        "arrived": arrived,
        "departed": departed,
        "price_changed": price_changed,
        "outflow_spikes": outflow_spikes(new),
    }


def store(snap: dict) -> str:
    return fpl_api.write_cache(SNAPSHOT_CACHE, snap)


def load_previous():
    """The stored snapshot from the last run, or None on a first run."""
    return fpl_api.read_cache(SNAPSHOT_CACHE)


def report(d: dict, since: str | None = None) -> str:
    """The human report the Thursday runbook opens with."""
    if d.get("first_run"):
        return ("=" * 60 + "\n"
                "FIRST RUN — snapshot stored, no diff.\n"
                "Every category below starts reporting on the next run.\n"
                + "=" * 60)

    lines = ["FPL feed diff" + (f" (since {since})" if since else "")]

    def section(title, rows, fmt):
        lines.append(f"\n{title} ({len(rows)})")
        if not rows:
            lines.append("  — none")
        for r in rows:
            lines.append(f"  {fmt(r)}")

    section("RENAMED — update aliases in the state files", d["renamed"],
            lambda r: f"{r['old']} → {r['new']} ({r['team']}, id {r['id']})")
    section("MOVED CLUB — re-check any note or squad claim", d["moved"],
            lambda r: f"{r['name']}: {r['old']} → {r['new']} (id {r['id']})")
    section("STATUS CHANGED — check feed for the news string",
            d["status_changed"],
            lambda r: f"{r['name']} ({r['team']}): "
                      f"{r['old']} → {r['new']} — check feed")
    section("ARRIVED — new players the capture has never seen", d["arrived"],
            lambda r: f"{r['name']} ({r['team']}, {r['price']}m, id {r['id']})")
    section("DEPARTED — gone from the feed entirely", d["departed"],
            lambda r: f"{r['name']} ({r['team']}, id {r['id']})")
    section("PRICE CHANGED", d["price_changed"],
            lambda r: f"{r['name']} ({r['team']}): "
                      f"{r['old']}m → {r['new']}m")
    section("OUTFLOW SPIKES — the crowd is selling; find out why",
            d["outflow_spikes"],
            lambda r: f"{r['name']} ({r['team']}): {r['tout']:,} out, "
                      f"z={r['z']}")
    return "\n".join(lines)


def main(fetch=None) -> int:
    """Fetch → diff against the stored snapshot → print → rotate the snapshot."""
    fetch = fetch or fpl_api.fetch_bootstrap
    boot = fetch()
    new = snapshot(boot)
    old = load_previous()
    print(report(diff(old, new),
                 since=(old or {}).get("taken_at")))
    store(new)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
