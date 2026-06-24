"""Pure ranking/selection logic for the evmax static site (no I/O except load_player_meta)."""

import json
import os

from core import fixtures
from games.fifa import model as fifa_model

POS_MIN = {"GK": 1, "DEF": 3, "MID": 2, "FWD": 1}
POS_MAX = {"GK": 1, "DEF": 5, "MID": 5, "FWD": 3}
XI_SIZE = 11
DIFF_MAX_OWNERSHIP = 10.0   # percent — "differential" cutoff
DIFF_MIN_XPTS = 4.0         # only surface differentials worth owning
BLOWOUT_FIXTURES = 2        # how many top-lambda fixtures count as "blowouts"
ARTICLES = ["best-xi", "captains", "high-ceiling-xi", "differentials",
            "best-value-xi", "blowout-transfers"]
ARTICLE_TITLES = {
    "best-xi": "Best World Cup Fantasy XI",
    "captains": "Best captain picks",
    "high-ceiling-xi": "High-ceiling / differential XI",
    "differentials": "Best differentials (low-owned)",
    "best-value-xi": "Best value XI",
    "blowout-transfers": "Best transfers for the blowout fixtures",
}

_PLAYERS_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "players.json")


def load_player_meta(path: str = _PLAYERS_JSON) -> dict:
    """name (and aliases) -> {team, position, price, ownership_pct} from data/players.json."""
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    out = {}
    for p in raw.get("players", []):
        meta = {
            "team": p.get("team"),
            "position": p.get("fifa_pos"),
            "price": p.get("fifa_price"),
            "ownership_pct": p.get("ownership"),
        }
        out[p["name"]] = meta
        for alias in p.get("aliases", []):
            out.setdefault(alias, meta)
    return out
