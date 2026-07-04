#!/usr/bin/env python3
"""Rate a fantasy team for Reddit rate-my-team threads.

Runs the poster's players through the engine and prints a paste-ready reply:
per-player xPts, captain check, injury flags, and the total vs our optimal.

Usage:
  python3 scripts/rate_team.py --round 5 "Messi (C), Mbappe, Cunha, Saibari, ..."
  echo "Messi (C)\nMbappe\n..." | python3 scripts/rate_team.py --round 5
Names are matched case/diacritic-insensitively against the player DB (aliases incl.).
"""
from __future__ import annotations

import argparse
import os
import sys
import unicodedata

# Allow running as `python3 scripts/rate_team.py` from anywhere: put the repo
# root (which holds core/ and evmax/) on the path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import engine_events, espn, research
from evmax import articles


def _norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return "".join(ch for ch in s.lower() if ch.isalnum())


def build_rows(rnd: int, sims: int) -> list:
    players, _ = engine_events.simulate_round(
        rnd, sims=sims,
        market_rates=espn.load_player_rates(rnd),
        research=research.load_entries("players", rnd),
        research_weight=0.30)
    means = engine_events.event_means(players)
    samples = {n: ps.goal_samples for n, ps in players.items()}
    meta = articles.load_player_meta()
    from evmax.build import _kickoffs_for_round
    return articles.build_rows(means, samples, meta, _kickoffs_for_round(rnd))


def match(rows: list, wanted: str):
    nw = _norm(wanted)
    exact = [r for r in rows if _norm(r["name"]) == nw]
    if exact:
        return exact[0], None
    part = [r for r in rows if nw in _norm(r["name"]) or _norm(r["name"]) in nw]
    if len(part) == 1:
        return part[0], None
    if len(part) > 1:
        part.sort(key=lambda r: -r["x_points"])
        return part[0], f"(matched '{part[0]['name']}'; also: {', '.join(p['name'] for p in part[1:3])})"
    return None, None


def flags_for(name: str, rnd: int, notes: dict) -> str:
    e = notes.get(name)
    if e and e.status in ("out", "suspended"):
        return f"🚫 {e.status.upper()}"
    if e and e.status == "doubtful":
        return "⚠ doubtful"
    return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("players", nargs="?", help="comma-separated names, (C) marks captain")
    ap.add_argument("--round", type=int, default=5)
    ap.add_argument("--sims", type=int, default=8000)
    a = ap.parse_args()

    raw = a.players if a.players else sys.stdin.read()
    names = [t.strip() for t in raw.replace("\n", ",").split(",") if t.strip()]
    cap_name = None
    cleaned = []
    for n in names:
        if "(c)" in n.lower():
            n = n.lower().replace("(c)", "").strip()
            cap_name = n
        cleaned.append(n)

    print(f"[engine] simulating round {a.round} ({a.sims} sims)…", file=sys.stderr)
    rows = build_rows(a.round, a.sims)
    notes = research.load_entries("players", a.round)

    lines, total, missing = [], 0.0, []
    matched_rows = []
    cap_row = None
    for n in cleaned:
        r, note = match(rows, n)
        if r is None:
            missing.append(n)
            continue
        matched_rows.append(r)
        is_cap = cap_name and _norm(cap_name) in _norm(r["name"])
        if is_cap:
            cap_row = r
        fl = flags_for(r["name"], a.round, notes)
        capmark = " **(C)**" if is_cap else ""
        extras = " ".join(x for x in (fl, note or "") if x)
        lines.append(f"- {r['name']}{capmark} — **{r['x_points']:.1f} xPts**"
                     + (f"  {extras}" if extras else ""))
        total += r["x_points"] * (2 if is_cap else 1)

    best_cap = max(matched_rows, key=lambda r: r["captain_ev"], default=None)

    print(f"\nRan your team through my Monte-Carlo model ({a.sims:,} sims on de-vigged market odds, Round {a.round}):\n")
    print("\n".join(lines))
    print(f"\n**Projected total: {total:.1f} pts** (captain doubled)")
    if cap_row is not None and best_cap is not None:
        if _norm(cap_row["name"]) == _norm(best_cap["name"]):
            print(f"\nCaptain check: **{cap_row['name']} ✔** — top captain EV in your squad "
                  f"({cap_row['captain_ev']:.1f}).")
        else:
            print(f"\nCaptain check: model prefers **{best_cap['name']}** "
                  f"({best_cap['captain_ev']:.1f} cEV vs {cap_row['name']} {cap_row['captain_ev']:.1f}).")
    elif best_cap is not None:
        print(f"\nBest captain in your squad by my sims: **{best_cap['name']}** ({best_cap['captain_ev']:.1f} cEV).")
    if missing:
        print(f"\n(couldn't match: {', '.join(missing)})")
    print("\n*(my own model — de-vigged odds → Dixon-Coles → Monte-Carlo, scored on official fantasy rules; graded publicly each round)*")


if __name__ == "__main__":
    main()
