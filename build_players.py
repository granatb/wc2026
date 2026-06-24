"""Rebuild data/players.json from the FIFA + Holdet public APIs (replaces screenshots).

Spine = the Holdet player universe (tournament 504): name, team, holdet position, holdet
price (kr), holdet ownership. FIFA players (play.fifa.com) matched by surname +
first-initial + position add the FIFA position, price and ownership. `aliases` carry the
short names our game state files / ratings use, so core.players.resolve keeps working.
status comes from research notes. Per-round growth/points are fetched live, not stored.

Run:  python build_players.py     · or call build() from the app's Sync button.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core import holdet_api, fifa_api, players as pdb, ratings, research


def _surname(n):
    return pdb._parts(n)[1]


def build(refresh: bool = True) -> int:
    if refresh:
        holdet_api.refresh(rounds=(1, 2, 3))
        fifa_api.refresh()
    hold = holdet_api.players(1)
    fifa = fifa_api.players()

    fidx = defaultdict(list)
    for p in fifa:
        full = (p.get("firstName", "") + " " + p.get("lastName", "")).strip()
        for nm in (full, p.get("knownName"), p.get("lastName")):
            if nm:
                fidx[_surname(nm)].append((nm, p))

    def best_fifa(name, pos):
        scored = []
        for nm, p in fidx.get(_surname(name), []):
            fa, sa = pdb._parts(nm)
            fb, sb = pdb._parts(name)
            if sa != sb:
                continue
            s = 2 if (fa and fb and fa == fb) else 1
            if pos and p.get("position") == pos:
                s += 0.5
            scored.append((s, p))
        return max(scored, key=lambda x: x[0])[1] if scored else None

    ours = set(ratings.PLAYER_PRIORS)
    for g in ("fifa", "holdet_gold", "holdet_yolo", "holdet_free"):
        ours |= {p["name"] for p in json.load(
            open(f"{ROOT}/games/{g}/state.json", encoding="utf-8")).get("squad", [])}
    entries = research.load_entries("players")

    # Holdet uses a few team names that differ from the ESPN/fixtures convention the
    # engine + odds are keyed on. Normalise so every player joins its fixture/odds.
    espn_team = {"USA": "United States", "Côte d'Ivoire": "Ivory Coast",
                 "Cote d'Ivoire": "Ivory Coast"}
    recs = []
    for hp in hold:
        name = hp["name"]
        if not name or name == "?":
            continue
        fp = best_fifa(name, hp["pos"])
        aliases = sorted({n for n in ours if n != name and pdb.name_match(n, name)})
        status = next((e.status for rn, e in entries.items()
                       if pdb.name_match(rn, name) and e.status), None)
        recs.append({
            "name": name, "aliases": aliases, "team": espn_team.get(hp["team"], hp["team"]),
            "fifa_pos": (fp.get("position") if fp else None) or hp["pos"],
            "holdet_pos": hp["pos"],
            "fifa_price": fp.get("price") if fp else None,
            "holdet_price": hp["price"],
            "ownership": fp.get("percentSelected") if fp else None,
            "holdet_ownership": round(hp["ownership"] * 100, 1) if hp["ownership"] is not None else None,
            "status": status,
        })
    recs.sort(key=lambda r: r["name"])
    pdb.save(recs)
    return len(recs)


if __name__ == "__main__":
    n = build()
    print(f"wrote {n} players from FIFA + Holdet APIs")
