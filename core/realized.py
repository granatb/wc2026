"""Realized minutes + attacking output from cached Holdet stats (data/holdet/stats_rN.json).

Turns each player's per-round events into a start-probability and an attacking profile, so
priors reflect WHO ACTUALLY PLAYS and PRODUCES rather than inferring ability from price.
The price->quality prior was structurally blind to cheap boomers (R3 backtest 2026-06-28:
Nicolas Pepe ranked #614, Pape Gueye #128, both ~0% owned, both boomed).

Event type IDs decoded empirically from the cached stats + known players (kr-table cross-check):
  224/562 = started, 225/226 = subbed on/off, 342 = did not play,
  218 = goal (Dembélé=3 hat-trick -> +602k; total 71 ≈ R3 goal count),
  220 = assist (~53 ≈ assist count), 513 = MOTM (24 = 1/match),
  558 = shot on target, 559 = GK save.
Further ids decoded 2026-07-06 by regressing official FIFA fantasy roundPoints residuals
(after goals/assists/CS/appearance) on event counts across R1-R5 (n=2706 player-rounds):
  222 = yellow card (coef -1.04 vs FIFA's -1), 219/223 = red card / own goal (both ~-2.4
  vs FIFA's -2; which is which is unresolved — both score -2), 465 = penalty save (+2.8
  vs FIFA's +3, n=4). 556/557 track shot/duel-like volume (no FIFA point value); 348,
  520, 560, 561, 618 remain undecoded.

Knockout caveat: matchday 3 (R3) was full of dead-rubber rotation (e.g. Argentina rested
Romero/Enzo/de Paul -> DNP), so the competitive rounds R1/R2 are weighted ALONGSIDE R3 for
the start probability rather than trusting R3 alone.
"""

from __future__ import annotations

import json
import os
import unicodedata

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "holdet")

STARTED = {224, 562}
SUBBED = {225, 226}
DNP = {342}
GOAL, ASSIST, SOT = 218, 220, 558
_ROUND_W = {1: 0.30, 2: 0.40, 3: 0.30}   # per-matchday weight for the start prob

_CACHE: dict = {}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return "".join(c for c in s if c.isalpha() or c == " ").strip()


def _load_tournament():
    t = json.load(open(os.path.join(_DIR, "tournament.json"), encoding="utf-8"))
    persons = {p["id"]: f'{p.get("firstname","")} {p.get("lastname","")}'.strip()
               for p in t["persons"]}
    teams = {tm["id"]: tm["name"] for tm in t["teams"]}
    pl = {p["id"]: p for p in t["players"]}
    return persons, teams, pl


def load(rounds=(1, 2, 3)) -> dict:
    """-> {(norm_name, team): {start_prob, starts, subs, dnp, apps, goals, assists, sot}}"""
    key = tuple(rounds)
    if key in _CACHE:
        return _CACHE[key]
    try:
        persons, teams, pl = _load_tournament()
    except FileNotFoundError:
        _CACHE[key] = {}
        return {}
    prof: dict = {}
    for r in rounds:
        path = os.path.join(_DIR, f"stats_r{r}.json")
        if not os.path.exists(path):
            continue
        for e in json.load(open(path, encoding="utf-8")):
            pp = pl.get(e["player"]["id"])
            if not pp:
                continue
            nm = _norm(persons.get(pp["person"]["id"], ""))
            tm = teams.get(pp["team"]["id"], "?")
            if not nm:
                continue
            ids: dict = {}
            for ev in e.get("events", {}).get("round", []):
                ids[ev["type"]["id"]] = ids.get(ev["type"]["id"], 0) + ev.get("amount", 0)
            started = any(i in ids for i in STARTED)
            subbed = (not started) and any(i in ids for i in SUBBED)
            d = prof.setdefault((nm, tm), {"_play": {}, "starts": 0, "subs": 0, "dnp": 0,
                                           "apps": 0, "goals": 0.0, "assists": 0.0, "sot": 0.0})
            d["_play"][r] = 1.0 if started else (0.5 if subbed else 0.0)
            d["starts"] += int(started)
            d["subs"] += int(subbed)
            d["dnp"] += int(not started and not subbed)
            d["apps"] += int(started or subbed)
            d["goals"] += ids.get(GOAL, 0)
            d["assists"] += ids.get(ASSIST, 0)
            d["sot"] += ids.get(SOT, 0)
    for d in prof.values():
        num = sum(_ROUND_W.get(r, 0.3) * p for r, p in d["_play"].items())
        den = sum(_ROUND_W.get(r, 0.3) for r in d["_play"])
        d["start_prob"] = max(0.05, min(0.95, num / den)) if den else None
        d.pop("_play", None)
    _CACHE[key] = prof
    return prof


def profile(name: str, team: str | None = None) -> dict | None:
    """Realized profile for a player; team disambiguates common surnames."""
    p = load()
    n = _norm(name)
    if team and (n, team) in p:
        return p[(n, team)]
    for (nm, tm), d in p.items():
        if nm == n and (team is None or tm == team):
            return d
    return None


def clear_cache() -> None:
    _CACHE.clear()
