"""The Odds API client + local cache.

Thin layer: HTTP + JSON normalisation + cache I/O. All probability/lambda math lives
in core/odds_math.py so it stays unit-testable without a network.

Endpoints (The Odds API v4):
  GET /v4/sports/{sport}/odds?markets=h2h,totals          -> match markets
  GET /v4/sports/{sport}/events/{id}/odds?markets=...      -> player props per event

Auth: ODDS_API_KEY env var (only required when fetching; cache reads need no key).
Cache: data/odds/<match_id>.json, with a `fetched_utc` stamp for reproducibility.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from . import odds_math

BASE_URL = "https://api.the-odds-api.com/v4"
SPORT = "soccer_fifa_world_cup"

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_HERE, "data", "odds")

# Anytime-scorer markets are two-way per player (not mutually exclusive across
# players), so we can't normalise to 1. Apply a crude margin shrink instead.
SCORER_MARGIN_SHRINK = 0.95


def _api_key() -> str:
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        raise RuntimeError("ODDS_API_KEY not set — needed to fetch (cache reads do not).")
    return key


def _http_get_json(path: str, params: dict) -> object:
    params = {**params, "apiKey": _api_key(), "oddsFormat": "decimal"}
    url = f"{BASE_URL}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_events(regions: str = "eu", markets: str = "h2h,totals") -> list:
    return _http_get_json(f"/sports/{SPORT}/odds", {"regions": regions, "markets": markets})


def fetch_player_props(event_id: str, regions: str = "eu",
                       market: str = "player_goal_scorer_anytime") -> dict:
    return _http_get_json(f"/sports/{SPORT}/events/{event_id}/odds",
                          {"regions": regions, "markets": market})


# --- normalisation (pure; takes raw JSON) ----------------------------------

def _consensus(bookmakers: list, market_key: str) -> dict:
    """Mean decimal odds per outcome name across all books offering the market."""
    acc: dict[str, list[float]] = {}
    for bk in bookmakers:
        for m in bk.get("markets", []):
            if m.get("key") != market_key:
                continue
            for o in m.get("outcomes", []):
                key = o.get("name")
                acc.setdefault(key, []).append(o["price"])
    return {k: sum(v) / len(v) for k, v in acc.items() if v}


def _totals_consensus(bookmakers: list) -> dict | None:
    """Mean Over/Under decimal at the most common totals line."""
    by_point: dict[float, dict[str, list[float]]] = {}
    for bk in bookmakers:
        for m in bk.get("markets", []):
            if m.get("key") != "totals":
                continue
            for o in m.get("outcomes", []):
                pt = o.get("point")
                by_point.setdefault(pt, {}).setdefault(o["name"], []).append(o["price"])
    if not by_point:
        return None
    line = max(by_point, key=lambda p: sum(len(v) for v in by_point[p].values()))
    side = by_point[line]
    out = {"line": line}
    for name in ("Over", "Under"):
        if name in side:
            out[name.lower()] = sum(side[name]) / len(side[name])
    return out if "over" in out and "under" in out else None


def normalize_event(raw: dict) -> dict:
    """Reduce a raw Odds-API event to the fields the engine needs."""
    bks = raw.get("bookmakers", [])
    h2h = _consensus(bks, "h2h")
    home, away = raw["home_team"], raw["away_team"]
    return {
        "match_id": raw["id"],
        "home": home,
        "away": away,
        "kickoff_utc": raw.get("commence_time"),
        "h2h": {
            "home": h2h.get(home),
            "draw": h2h.get("Draw"),
            "away": h2h.get(away),
        },
        "totals": _totals_consensus(bks),
    }


def derive_match(norm: dict) -> dict:
    """Turn normalised odds into (lam_home, lam_away) + de-vigged 1X2."""
    h = norm["h2h"]
    pH, pD, pA = odds_math.devig([h["home"], h["draw"], h["away"]])
    lh, la = odds_math.solve_lambdas(pH, pD, pA)
    return {"lam_home": round(lh, 3), "lam_away": round(la, 3),
            "p1x2": {"home": pH, "draw": pD, "away": pA}}


def player_goal_rates(props_raw: dict) -> dict:
    """Map anytime-scorer event JSON -> {player_name: goal_rate}."""
    rates: dict[str, float] = {}
    for bk in props_raw.get("bookmakers", []):
        for m in bk.get("markets", []):
            if m.get("key") != "player_goal_scorer_anytime":
                continue
            for o in m.get("outcomes", []):
                name = o.get("description") or o.get("name")
                p = (1.0 / o["price"]) * SCORER_MARGIN_SHRINK
                rates.setdefault(name, []).append(p)
    return {n: odds_math.scorer_prob_to_goal_rate(sum(ps) / len(ps))
            for n, ps in rates.items()}


# --- cache ------------------------------------------------------------------

def save_match(match_id: str, data: dict, fetched_utc: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{match_id}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({**data, "fetched_utc": fetched_utc}, fh, indent=2)
    return path


def load_cached(match_id: str) -> dict | None:
    path = os.path.join(CACHE_DIR, f"{match_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
