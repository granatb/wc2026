"""Holdet data — undocumented public JSON at api.holdet.dk (no auth).

WC2026 = tournament 504, game 735. Three GETs, joined on player→person/team IDs, give
per-player value (kr), per-round growth (værdistigning = the actual increase), totalGrowth,
ownership (popularity), position and team. Cached to data/holdet/.
"""

from __future__ import annotations

import json
import os
import urllib.request

from . import players as pdb

BASE = "https://api.holdet.dk"
TOURNAMENT = 504
GAME = 735
POS = {6: "GK", 7: "DEF", 8: "MID", 9: "FWD"}
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "data", "holdet")
_MEM: dict = {}


def _get(path: str):
    url = f"{BASE}{path}{'&' if '?' in path else '?'}appid=holdet&culture=da-DK"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def refresh(rounds=(1, 2, 3)) -> None:
    os.makedirs(CACHE, exist_ok=True)
    json.dump(_get(f"/tournaments/{TOURNAMENT}"),
              open(f"{CACHE}/tournament.json", "w", encoding="utf-8"))
    for n in rounds:
        try:
            json.dump(_get(f"/games/{GAME}/rounds/{n}/statistics"),
                      open(f"{CACHE}/stats_r{n}.json", "w", encoding="utf-8"))
        except Exception:
            pass
    _MEM.clear()


def _load(name):
    p = f"{CACHE}/{name}.json"
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def players(rnd: int = 1) -> list:
    """Joined player rows: name, team, pos, price, growth, totalGrowth, ownership."""
    key = f"players_r{rnd}"
    if key in _MEM:
        return _MEM[key]
    t = _load("tournament")
    stats = _load(f"stats_r{rnd}")
    if not t or not stats:
        return []
    person = {p["id"]: (p.get("firstname", "") + " " + p.get("lastname", "")).strip()
              for p in t["persons"]}
    team = {tm["id"]: tm["name"] for tm in t["teams"]}
    meta = {pl["id"]: (person.get(pl["person"]["id"], "?"), team.get(pl["team"]["id"], "?"),
                       POS.get(pl["position"]["id"], "?")) for pl in t["players"]}
    out = []
    for e in stats:
        nm, tm, po = meta.get(e["player"]["id"], ("?", "?", "?"))
        v = e.get("values", {})
        out.append({"holdet_id": e["player"]["id"], "name": nm, "team": tm, "pos": po,
                    "price": v.get("value"), "growth": v.get("growth"),
                    "total_growth": v.get("totalGrowth"), "ownership": v.get("popularity")})
    _MEM[key] = out
    return out


def lookup(name: str, position: str | None = None, rnd: int = 1) -> dict | None:
    hits = [p for p in players(rnd) if pdb.name_match(name, p["name"])]
    if not hits:
        return None
    if position and len(hits) > 1:
        hits.sort(key=lambda p: p["pos"] != position)
    return hits[0]


def growth(name, rnd, position=None):
    p = lookup(name, position, rnd)
    return p["growth"] if p else None
