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


def _f(value, default: float = 0.0) -> float:
    """FPL returns several numeric fields as strings ('25.50'). Coerce safely."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_players(raw: dict) -> list[dict]:
    """Flatten `elements` into the fields the prior builder needs.

    NOTE on preseason: bootstrap's per-player totals carry LAST season's numbers
    until the new season starts, so xg_per90/minutes/starts are populated on day
    one. Players with minutes == 0 have no Premier League history at all (promoted
    clubs, foreign signings) and are handled by the cold-start fallback in
    core/fpl_priors.
    """
    teams = parse_teams(raw)
    out = []
    for e in raw.get("elements", []):
        out.append({
            "id": e["id"],
            "name": e["web_name"],
            "full_name": f"{e.get('first_name', '')} {e.get('second_name', '')}".strip(),
            "team": teams.get(e["team"], "???"),
            "position": POSITIONS.get(e["element_type"], "MID"),
            "price": e["now_cost"] / 10.0,
            "ownership": _f(e.get("selected_by_percent")),
            "status": e.get("status", "a"),
            "chance_of_playing": e.get("chance_of_playing_next_round"),
            "news": e.get("news", ""),
            "minutes": e.get("minutes", 0),
            "starts": e.get("starts", 0),
            "xg_per90": _f(e.get("expected_goals_per_90")),
            "xa_per90": _f(e.get("expected_assists_per_90")),
            "saves_per90": _f(e.get("saves_per_90")),
            "defcon_per90": _f(e.get("defensive_contribution_per_90")),
            "bps": e.get("bps", 0),
            "ep_next": _f(e.get("ep_next")),
            "pen_taker": e.get("penalties_order") == 1,
        })
    return out


def parse_scoring(raw: dict) -> dict:
    """The scoring table from game_config, with GKP keys remapped to GK.

    WARNING: this block carries UNIT values only. `saves: 1` means one point per
    THREE saves and `goals_conceded: -1` means minus one per TWO conceded. The
    divisors are not in the feed — they are pinned in games/fpl/model.py from the
    official rules page. Reading this block literally mis-prices every goalkeeper.
    """
    sc = dict(raw.get("game_config", {}).get("scoring", {}))
    for key, value in list(sc.items()):
        if isinstance(value, dict) and "GKP" in value:
            remapped = {("GK" if k == "GKP" else k): v for k, v in value.items()}
            sc[key] = remapped
    return sc


def parse_squad_rules(raw: dict) -> dict:
    r = raw.get("game_config", {}).get("rules", {}) or raw.get("game_settings", {})
    multiplier = r.get("ui_currency_multiplier", 10)
    return {
        "squad_size": r.get("squad_squadsize", 15),
        "squad_play": r.get("squad_squadplay", 11),
        "team_limit": r.get("squad_team_limit", 3),
        "budget": r.get("squad_total_spend", 1000) / multiplier,
        "max_extra_free_transfers": r.get("max_extra_free_transfers", 4),
        "sell_on_fee": r.get("transfers_sell_on_fee", 0.5),
    }


def parse_fixtures(raw: list, teams: dict[int, str]) -> list[dict]:
    """Flatten the fixtures feed into schedule rows.

    Fixtures with `event: None` are not yet assigned to a gameweek (postponed or
    awaiting a cup outcome) and are skipped — they are the mechanism by which
    blanks and doubles appear later in the season.
    """
    out = []
    for f in raw:
        gw = f.get("event")
        if gw is None:
            continue
        out.append({
            "match_id": str(f["id"]),
            "home": teams.get(f["team_h"], "???"),
            "away": teams.get(f["team_a"], "???"),
            "kickoff_utc": f.get("kickoff_time"),
            "fantasy_round": gw,
            "stage": "GW",
        })
    return out


def write_cache(name: str, payload) -> str:
    """Persist a raw payload under data/fpl/ so models can run offline."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    return path


def read_cache(name: str):
    path = os.path.join(DATA_DIR, f"{name}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def refresh(write: bool = True) -> tuple[dict, list]:
    """Fetch bootstrap + fixtures and cache them. Returns the raw payloads."""
    boot, fx = fetch_bootstrap(), fetch_fixtures()
    if write:
        write_cache("bootstrap", boot)
        write_cache("fixtures", fx)
    return boot, fx
