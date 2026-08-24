"""Accuracy grading v1 — our projections vs FPL's own ep_next vs reality.

The C-metric made mechanical (spec §6): after each gameweek, per-player
absolute error of our frozen x_points and (when the snapshot carries it)
FPL's own pre-deadline `ep_next` against realized total_points, plus each
published squad's projected-vs-realized line. scripts/grade_gw.py drives it
and banks the result to evmax/assets/accuracy/gw{N}.json (committed, like
the projections snapshots); a site surface comes with the next site phase —
until then the Monday runbook prints format_report's table.

Everything here is data-in/data-out except write_accuracy, the one deliberate
file writer (mirroring core/fpl_api.write_cache's precedent) so the banked
JSON has exactly one producer.

ep_next enters the snapshots via stamp_ep_next, which evmax/fpl_build applies
to the point-in-time projection archive for FUTURE gameweeks only — the
committed GW1 snapshots are frozen history and predate the capture, so their
grading reports mae_ep_next as None ("no benchmark"), never a fabricated 0.
"""

from __future__ import annotations

import json
import os


def grade(snapshot_rows: list, realized_points: dict) -> dict:
    """Per-player |projection - realized| aggregated over one gameweek.

    snapshot_rows:   entries out of the committed projection envelopes —
                     dicts carrying name, x_points and optionally ep_next.
    realized_points: {name: realized total_points}, names matching the rows'
                     (the caller joins the live feed through the same
                     disambiguation the rows were built with).

    Players absent from realized_points are SKIPPED, not zeroed: a missing
    join (rename mid-week) must not masquerade as a 0-point blank.

    Returns {n, mae_ours, mae_ep_next, beat_ep_next, players}; mae_ep_next
    and beat_ep_next are None when no graded row carries ep_next.
    """
    players = []
    err_ours_total = 0.0
    err_ep_total, ep_n = 0.0, 0
    for row in snapshot_rows:
        name = row["name"]
        if name not in realized_points:
            continue
        realized = realized_points[name]
        err_ours = abs(row["x_points"] - realized)
        err_ours_total += err_ours
        line = {"name": name, "x_points": row["x_points"],
                "realized": realized, "err_ours": round(err_ours, 2)}
        ep = row.get("ep_next")
        if ep is not None:
            err_ep = abs(ep - realized)
            err_ep_total += err_ep
            ep_n += 1
            line["ep_next"] = ep
            line["err_ep_next"] = round(err_ep, 2)
        players.append(line)

    n = len(players)
    mae_ours = round(err_ours_total / n, 3) if n else None
    mae_ep = round(err_ep_total / ep_n, 3) if ep_n else None
    return {
        "n": n,
        "mae_ours": mae_ours,
        "mae_ep_next": mae_ep,
        "beat_ep_next": (mae_ours < mae_ep) if (mae_ours is not None
                                                and mae_ep is not None)
        else None,
        "players": sorted(players, key=lambda p: -p["err_ours"]),
    }


def squad_line(envelope: dict, realized_points: dict) -> dict:
    """{projected, realized} for one squad snapshot.

    projected is the FROZEN projected_total out of the committed envelope's
    squad meta — the published claim, never a rerun. realized is the XI's
    realized points with the captain doubled; v1 deliberately does not
    re-derive autosubs (the live duel panel shows FPL's official total — this
    line grades the projection against the team as published).
    """
    realized = 0
    for e in envelope.get("entries", []):
        if e.get("role") != "XI":
            continue
        pts = realized_points.get(e["name"], 0)
        realized += pts * (2 if e.get("is_captain") else 1)
    return {"projected": (envelope.get("squad") or {}).get("projected_total"),
            "realized": realized}


def stamp_ep_next(envelope: dict, ep_by_name: dict) -> dict:
    """A deep copy of an article envelope with ep_next stamped per entry.

    Applied by evmax/fpl_build to the projection SNAPSHOT copy only — the
    public /api JSON stays exactly as rendered. Entries whose player has no
    ep_next in the feed stay unstamped rather than carrying null noise.
    """
    out = json.loads(json.dumps(envelope))
    for entry in out.get("entries", []):
        ep = ep_by_name.get(entry.get("name"))
        if ep is not None:
            entry["ep_next"] = ep
    return out


def write_accuracy(gameweek: int, payload: dict, out_dir: str) -> str:
    """Bank one gameweek's accuracy JSON: {out_dir}/gw{N}.json."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"gw{gameweek}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path


def format_report(payload: dict) -> str:
    """The Monday-report table the runbook prints."""
    gw = payload.get("gameweek")
    lines = [f"=== Accuracy — gameweek {gw} "
             f"({payload.get('n', 0)} graded players) ==="]
    mae_ours = payload.get("mae_ours")
    mae_ep = payload.get("mae_ep_next")
    if mae_ep is None:
        lines.append(f"  MAE ours {mae_ours} — no ep_next benchmark in this "
                     f"gameweek's snapshots (pre-capture history)")
    else:
        verdict = ("we beat ep_next" if payload.get("beat_ep_next")
                   else "ep_next beat us")
        lines.append(f"  MAE ours {mae_ours} vs ep_next {mae_ep} — {verdict}")
    for slug, line in (payload.get("squads") or {}).items():
        lines.append(f"  {slug}: projected {line.get('projected')} → "
                     f"realized {line.get('realized')}")
    players = payload.get("players") or []
    if players:
        lines.append(f"\n  {'player':<22} {'ours':>6} {'ep':>6} "
                     f"{'real':>5} {'|err|':>6}")
        for p in players[:15]:
            ep = p.get("ep_next")
            lines.append(f"  {p['name']:<22} {p['x_points']:>6.2f} "
                         f"{(f'{ep:.2f}' if ep is not None else '—'):>6} "
                         f"{p['realized']:>5} {p['err_ours']:>6.2f}")
    return "\n".join(lines)
