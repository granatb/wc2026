#!/usr/bin/env python3
"""Rate a fantasy team for Reddit rate-my-team threads.

Runs the poster's players through the engine and prints a paste-ready reply:
per-player xPts, captain check, injury flags, and the total vs our optimal.

Rates the full 15, not just the XI. Tag bench players with (B) so they're
excluded from the projected total (only the XI + doubled captain scores) but
still get an xPts line -- plus a "sub chain" note when a same-position XI
starter kicks off earlier than they do. That gap is a real, common manual-sub
tactic: FIFA's automatic subs are DNP-only and only fire at round end, but
manual subs are allowed right up to the round's last kickoff, so managers
routinely start the earlier fixture and hold a stronger later-kickoff player
in reserve, swapping him in once they've seen the early starter's result.
Don't read an unflagged, strong bench player as a "wasted" pick without
checking this -- it's very often intentional.

Usage:
  python3 scripts/rate_team.py --round 5 "Messi (C), Mbappe, Cunha, Saibari, Freeman (B), ..."
  echo "Messi (C)\nMbappe\nFreeman (B)\n..." | python3 scripts/rate_team.py --round 5
Names are matched case/diacritic-insensitively against the player DB (aliases incl.).
"""
from __future__ import annotations

import argparse
import datetime as dt
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
    """Display-string wrapper around the shared articles.player_flag() taxonomy
    ("out"/"doubtful"/None) -- kept here so existing callers/tests of this CLI's
    exact glyph output ("🚫 OUT" / "⚠ doubtful") don't need to change."""
    flag = articles.player_flag(name, notes)
    if flag == "out":
        e = notes.get(name)
        return f"🚫 {e.status.upper()}"
    if flag == "doubtful":
        return "⚠ doubtful"
    return ""


def _kickoff_dt(row: dict):
    ko = row.get("kickoff")
    return dt.datetime.fromisoformat(ko) if ko else None


def chain_note(bench_row: dict, xi_rows: list) -> str:
    """A bench player is a "sub chain" option, not a wasted slot, if some XI
    starter of the same position kicks off earlier: the manager can watch that
    match, then manually swap the bench player in before his own kickoff --
    manual subs are allowed up to the round's last match (autosubs are
    DNP-only and only run at round end). Returns "" if no such starter exists
    (or kickoff data is missing), in which case a strong bench pick really is
    just sitting idle this round."""
    bench_ko = _kickoff_dt(bench_row)
    if bench_ko is None:
        return ""
    earlier = [
        r for r in xi_rows
        if r.get("position") == bench_row.get("position")
        and (ko := _kickoff_dt(r)) is not None and ko < bench_ko
    ]
    if not earlier:
        return ""
    last_ko = max(_kickoff_dt(r) for r in earlier)
    gap_h = round((bench_ko - last_ko).total_seconds() / 3600)
    names = ", ".join(r["name"] for r in earlier)
    return f"(chain option for {names} -- kicks off first, ~{gap_h}h to react)"


def captain_chain(xi_rows: list) -> list:
    """The armband can be moved mid-round just like manual subs: captain an
    early-kickoff player, and after his match either keep the double (he
    hauled) or roll the band to a later player before that one kicks off.
    Chain = highest-cEV player per kickoff slot among those who (a) play
    before the best static captain (the anchor) and (b) have a ceiling above
    the anchor's single xPts, so a haul is actually worth locking. Returns
    the kickoff-ordered chain ending at the anchor, or [] when there's no
    earlier link worth a shot (then static advice stands)."""
    scored = [r for r in xi_rows if _kickoff_dt(r) is not None]
    if not scored:
        return []
    anchor = max(scored, key=lambda r: r["captain_ev"])
    best_at = {}
    for r in scored:
        ko = _kickoff_dt(r)
        if ko >= _kickoff_dt(anchor) or r.get("ceiling", 0) <= anchor["x_points"]:
            continue
        if ko not in best_at or r["captain_ev"] > best_at[ko]["captain_ev"]:
            best_at[ko] = r
    if not best_at:
        return []
    return sorted(best_at.values(), key=_kickoff_dt) + [anchor]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("players", nargs="?", help="comma-separated names, (C) marks captain, (B) marks bench")
    ap.add_argument("--round", type=int, default=5)
    ap.add_argument("--sims", type=int, default=8000)
    a = ap.parse_args()

    raw = a.players if a.players else sys.stdin.read()
    names = [t.strip() for t in raw.replace("\n", ",").split(",") if t.strip()]
    cap_name = None
    cleaned = []
    bench_flags = []
    for n in names:
        is_bench = "(b)" in n.lower()
        if is_bench:
            n = n.lower().replace("(b)", "").strip()
        if "(c)" in n.lower():
            n = n.lower().replace("(c)", "").strip()
            cap_name = n
        cleaned.append(n)
        bench_flags.append(is_bench)

    print(f"[engine] simulating round {a.round} ({a.sims} sims)…", file=sys.stderr)
    rows = build_rows(a.round, a.sims)
    notes = research.load_entries("players", a.round)

    xi_lines, bench_lines, total, missing = [], [], 0.0, []
    xi_rows, bench_rows = [], []
    cap_row = None
    for n, is_bench in zip(cleaned, bench_flags):
        r, note = match(rows, n)
        if r is None:
            missing.append(n)
            continue
        is_cap = (not is_bench) and cap_name and _norm(cap_name) in _norm(r["name"])
        if is_cap:
            cap_row = r
        fl = flags_for(r["name"], a.round, notes)
        capmark = " **(C)**" if is_cap else ""
        if is_bench:
            bench_rows.append(r)
        else:
            xi_rows.append(r)
            total += r["x_points"] * (2 if is_cap else 1)
        extras = [x for x in (fl, note or "") if x]
        line_pos = bench_lines if is_bench else xi_lines
        line_pos.append((r, capmark, extras))

    # second pass: bench chain notes need the full XI, so compute after the loop
    for r, capmark, extras in bench_lines:
        cn = chain_note(r, xi_rows)
        if cn:
            extras.append(cn)

    def fmt(entries):
        out = []
        for r, capmark, extras in entries:
            extra_str = "  " + " ".join(extras) if extras else ""
            out.append(f"- {r['name']}{capmark} — **{r['x_points']:.1f} xPts**{extra_str}")
        return out

    best_cap = max(xi_rows, key=lambda r: r["captain_ev"], default=None)

    print(f"\nRan your team through my Monte-Carlo model ({a.sims:,} sims on de-vigged market odds, Round {a.round}):\n")
    print("Starting XI:")
    print("\n".join(fmt(xi_lines)))
    print(f"\n**Projected total: {total:.1f} pts** (XI only, captain doubled)")
    if bench_lines:
        print("\nBench:")
        print("\n".join(fmt(bench_lines)))
    if cap_row is not None and best_cap is not None:
        if _norm(cap_row["name"]) == _norm(best_cap["name"]):
            print(f"\nCaptain check: **{cap_row['name']} ✔** — top captain EV in your squad "
                  f"({cap_row['captain_ev']:.1f}).")
        else:
            print(f"\nCaptain check: model prefers **{best_cap['name']}** "
                  f"({best_cap['captain_ev']:.1f} cEV vs {cap_row['name']} {cap_row['captain_ev']:.1f}).")
    elif best_cap is not None:
        print(f"\nBest captain in your squad by my sims: **{best_cap['name']}** ({best_cap['captain_ev']:.1f} cEV).")
    chain = captain_chain(xi_rows)
    if len(chain) > 1:
        hops = " → ".join(r["name"] for r in chain)
        # keep the band only on a score that beats the best you could still
        # chain to -- otherwise roll it forward before the next link kicks off
        thrs = [max(r["x_points"] for r in chain[i + 1:]) for i in range(len(chain) - 1)]
        if len({f"{t:.0f}" for t in thrs}) == 1:
            rule = f"keep the band wherever it lands on a {thrs[0]:.0f}+ score, otherwise roll it forward"
        else:
            rule = ", ".join(
                f"roll off {chain[i]['name']} if he scores under ~{thrs[i]:.0f}"
                for i in range(len(chain) - 1))
        print(f"\nArmband chain (captain can be moved mid-round): **{hops}** — {rule}.")
    if missing:
        print(f"\n(couldn't match: {', '.join(missing)})")
    print("\n*(my own model — de-vigged odds → Dixon-Coles → Monte-Carlo, scored on official fantasy rules; graded publicly each round)*")


if __name__ == "__main__":
    main()
