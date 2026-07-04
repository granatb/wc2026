"""FIFA World Cup Fantasy — undocumented public JSON feed (no auth, ~15s live).

play.fifa.com/json/fantasy/{players,rounds,squads_fifa}.json. Gives per-player price,
ownership, points-per-round, total points, and live match status. Cached to data/fifa/.
Names are matched to our canonical players via core.players.name_match (+ team to break
common-surname ties like Camilo vs Ruben Vargas).
"""

from __future__ import annotations

import json
import os
import urllib.request

from . import players as pdb

BASE = "https://play.fifa.com/json/fantasy"
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "data", "fifa")
_FILES = ("players", "rounds", "squads_fifa")


def _get(name: str):
    with urllib.request.urlopen(f"{BASE}/{name}.json", timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


_MEM: dict = {}


def refresh() -> None:
    os.makedirs(CACHE, exist_ok=True)
    for n in _FILES:
        json.dump(_get(n), open(f"{CACHE}/{n}.json", "w", encoding="utf-8"))
    _MEM.clear()


def _load(name: str):
    p = f"{CACHE}/{name}.json"
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def players() -> list:
    if "players" not in _MEM:
        _MEM["players"] = _load("players") or []
    return _MEM["players"]


def fixtures() -> list:
    """Flat list of all matches across rounds: date, status, teams, score."""
    if "fixtures" not in _MEM:
        out = []
        for rd in (_load("rounds") or []):
            for m in rd.get("tournaments", []):
                out.append({"round": rd.get("id"), "date": m.get("date"),
                            "status": m.get("status"), "home": m.get("homeSquadName"),
                            "away": m.get("awaySquadName"), "hs": m.get("homeScore"),
                            "as": m.get("awayScore"), "period": m.get("period"),
                            "extraMinutes": m.get("extraMinutes") or 0})
        _MEM["fixtures"] = out
    return _MEM["fixtures"]


# Country spellings differ between feeds (ESPN ↔ FIFA). Normalise the known variants.
import unicodedata as _ud

_COUNTRY_ALIAS = {
    "south korea": "korea republic",
    "united states": "usa", "usmnt": "usa",
    "ivory coast": "cote d ivoire",
    "czech republic": "czechia",
}


def _ckey(name: str) -> str:
    s = "".join(c for c in _ud.normalize("NFD", name or "")
                if _ud.category(c) != "Mn").lower()
    s = " ".join("".join(ch if ch.isalpha() or ch == " " else " " for ch in s).split())
    return _COUNTRY_ALIAS.get(s, s)


def same_team(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return _ckey(a) == _ckey(b) or pdb.name_match(a, b)


def actual_score(home: str, away: str):
    """(home_goals, away_goals, status) for a fixture, matched by team names.

    WARNING: in knockouts the feed's score INCLUDES extra-time goals (penalties are
    separate). Målspillet scores the 90-minute result, so use went_to_et() to detect
    ET games and avoid grading a 90-min bet against an after-ET score.
    """
    for m in fixtures():
        if same_team(home, m.get("home")) and same_team(away, m.get("away")):
            return m.get("hs"), m.get("as"), m.get("status")
    return None, None, None


_ET_PERIODS = {"extra_time", "after_extra_time", "penalties", "penalty_shootout",
               "extra_first_half", "extra_second_half"}


def went_to_et(home: str, away: str) -> bool:
    """True if this knockout went beyond 90' — meaning actual_score() is NOT the
    90-minute (regulation) score Målspillet grades against."""
    for m in fixtures():
        if same_team(home, m.get("home")) and same_team(away, m.get("away")):
            return (m.get("extraMinutes") or 0) > 0 or \
                   str(m.get("period") or "").lower() in _ET_PERIODS
    return False


def team_match_status(team: str, rnd: int):
    """Status of `team`'s match in a round ('complete'/'playing'/'scheduled'/None)."""
    for m in fixtures():
        if m["round"] == rnd and (same_team(team, m.get("home")) or
                                  same_team(team, m.get("away"))):
            return m["status"]
    return None


def _names(p: dict):
    full = f"{p.get('firstName', '')} {p.get('lastName', '')}".strip()
    return [n for n in (full, p.get("knownName"), p.get("lastName")) if n]


def _score(name: str, p: dict) -> int:
    """Match strength: 2 = surname + first-initial both present & equal, 1 = surname
    only (one side has no first name), 0 = no match. Distinguishes Ruben vs Camilo Vargas."""
    fn, sn = pdb._parts(name)
    best = 0
    for cand in _names(p):
        fc, sc = pdb._parts(cand)
        if sc != sn:
            continue
        best = max(best, 2 if (fn and fc and fn == fc) else 1)
    return best


def lookup(name: str, position: str | None = None) -> dict | None:
    """Best FIFA-API player for our name, ranked by name-match strength then position."""
    hits = [(p, _score(name, p)) for p in players()]
    hits = [(p, s) for p, s in hits if s > 0]
    if not hits:
        return None
    if position:
        hits.sort(key=lambda ps: (-ps[1], ps[0].get("position") != position))
    else:
        hits.sort(key=lambda ps: -ps[1])
    return hits[0][0]


def round_points(name, rnd, position=None):
    p = lookup(name, position)
    return p.get("stats", {}).get("roundPoints", {}).get(str(rnd)) if p else None


def total_points(name, position=None):
    p = lookup(name, position)
    return p.get("stats", {}).get("totalPoints") if p else None


def match_status(name, position=None):
    """('status', 'matchStatus') e.g. ('playing','start')."""
    p = lookup(name, position)
    return (p.get("status"), p.get("matchStatus")) if p else (None, None)


def price_ownership(name, position=None):
    p = lookup(name, position)
    return (p.get("price"), p.get("percentSelected")) if p else (None, None)
