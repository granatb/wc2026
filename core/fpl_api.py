"""Fantasy Premier League official API client (free, no key).

Three endpoints:
  bootstrap-static  -> teams, gameweek events (deadlines), all players with last
                       season's totals and per-90 rates, plus the scoring config.
  fixtures          -> all 380 fixtures with gameweek assignment and kickoff.
  element-summary/N -> one player's per-fixture history + past seasons.

Network lives in the fetch_* functions; every parse_* is pure and unit-tested
against saved payloads in tests/fixtures/. Mirrors core/espn.py's split.

Deadlines are ALWAYS read from here in UTC. The official rules page renders them
in the viewer's local timezone and must never be scraped.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone

BASE = "https://fantasy.premierleague.com/api"
BOOTSTRAP = f"{BASE}/bootstrap-static/"
FIXTURES = f"{BASE}/fixtures/"
ELEMENT_SUMMARY = f"{BASE}/element-summary/{{element_id}}/"

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_HERE, "data", "fpl")

USER_AGENT = "wc2026-engine/1.0"

# FPL element_type -> this repo's internal position vocabulary.
# FPL says GKP; the repo says GK. Map here, once, at the boundary.
POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def _get_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --- network ---------------------------------------------------------------

def fetch_bootstrap() -> dict:
    return _get_json(BOOTSTRAP)


def fetch_fixtures() -> list:
    return _get_json(FIXTURES)


def fetch_element_summary(element_id: int) -> dict:
    return _get_json(ELEMENT_SUMMARY.format(element_id=element_id))


# --- pure parsers ------------------------------------------------------------

def _parse_utc(s: str) -> datetime:
    """Parse an FPL ISO-8601 timestamp to a UTC-aware datetime (py3.9-safe)."""
    s = s.replace("Z", "+00:00")
    d = datetime.fromisoformat(s)
    return d.astimezone(timezone.utc) if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_teams(raw: dict) -> dict[int, str]:
    """{team_id: short_name}, e.g. {14: 'LIV'}."""
    return {t["id"]: t["short_name"] for t in raw.get("teams", [])}


def parse_events(raw: dict) -> dict[int, dict]:
    """{gw_id: {id, name, deadline (UTC-aware), finished}}."""
    out = {}
    for e in raw.get("events", []):
        out[e["id"]] = {
            "id": e["id"],
            "name": e.get("name", f"Gameweek {e['id']}"),
            "deadline": _parse_utc(e["deadline_time"]),
            "finished": bool(e.get("finished")),
        }
    return out
