"""api-football (API-Sports) client -> data/schedule.json.

Pulls the World Cup fixture list and normalises each match to the shape fixtures.py
consumes. Auth: API_FOOTBALL_KEY env var (header x-apisports-key). Like odds.py, the
network lives here; fixtures.py only reads the cached JSON.

World Cup league id on API-Sports is 1.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

BASE_URL = "https://v3.football.api-sports.io"
WORLD_CUP_LEAGUE = 1

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEDULE_PATH = os.path.join(_HERE, "data", "schedule.json")

# api-football "round" string -> (stage, fantasy_round). Substring-matched, order matters
# (check the longer/more specific names first).
ROUND_MAP = [
    ("Group Stage - 1", ("GROUP_MD1", 1)),
    ("Group Stage - 2", ("GROUP_MD2", 2)),
    ("Group Stage - 3", ("GROUP_MD3", 3)),
    ("Round of 32", ("R32", 4)),
    ("Round of 16", ("R16", 5)),
    ("Quarter", ("QF", 6)),
    ("Semi", ("SF", 7)),
    ("3rd Place", ("BRONZE", 8)),
    ("Final", ("FINAL", 8)),
]


def _api_key() -> str:
    key = os.environ.get("API_FOOTBALL_KEY")
    if not key:
        raise RuntimeError("API_FOOTBALL_KEY not set — needed to fetch (cache reads do not).")
    return key


def _http_get_json(path: str, params: dict) -> object:
    url = f"{BASE_URL}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"x-apisports-key": _api_key()})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_fixtures(season: int = 2026, league: int = WORLD_CUP_LEAGUE) -> dict:
    return _http_get_json("/fixtures", {"league": league, "season": season})


def map_round(round_name: str) -> tuple[str, int]:
    for needle, mapped in ROUND_MAP:
        if needle in round_name:
            return mapped
    return ("GROUP_MD1", 1)


def normalize_fixture(item: dict) -> dict:
    stage, frnd = map_round(item.get("league", {}).get("round", ""))
    return {
        "match_id": str(item["fixture"]["id"]),
        "home": item["teams"]["home"]["name"],
        "away": item["teams"]["away"]["name"],
        "kickoff_utc": item["fixture"]["date"],
        "stage": stage,
        "fantasy_round": frnd,
    }


def write_schedule(entries: list, path: str = SCHEDULE_PATH) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2)
    return path


def fetch_and_write(season: int = 2026) -> str:
    raw = fetch_fixtures(season)
    entries = [normalize_fixture(it) for it in raw.get("response", [])]
    return write_schedule(entries)
