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


def build_rows(means: dict, samples: dict, meta: dict, kickoffs: dict) -> list:
    """Enrich the engine's per-player means with metadata into ranked-ready rows.

    means:    name -> event-means dict (from engine_events.event_means)
    samples:  name -> goal_samples list (from PlayerSample.goal_samples)
    meta:     name -> {team, position, price, ownership_pct} (load_player_meta)
    kickoffs: team -> ISO-8601 kickoff string for the round
    Players missing metadata or a position are skipped.
    """
    rows = []
    for name, ev in means.items():
        m = meta.get(name)
        if not m or not m.get("position"):
            continue
        xp = fifa_model.expected_points(ev)
        ceiling = fifa_model.ceiling_points(ev, samples.get(name, []))
        price = m.get("price")
        rows.append({
            "name": name,
            "team": m.get("team"),
            "position": m["position"],
            "x_points": round(xp, 2),
            "captain_ev": round(2 * xp, 2),
            "ceiling": round(ceiling, 2),
            "price": price,
            "ownership_pct": m.get("ownership_pct"),
            "value": xp / price if price else None,
            "kickoff": kickoffs.get(m.get("team")),
        })
    return rows


def select_xi(rows: list, key: str) -> list:
    """Greedy formation-constrained XI maximizing `key` (e.g. 'x_points' or 'ceiling').
    Fills position minimums first, then the remaining slots by best `key` within maxima."""
    pools = {pos: sorted([r for r in rows if r["position"] == pos and r.get(key) is not None],
                         key=lambda r: r[key], reverse=True)
             for pos in POS_MIN}
    chosen, counts = [], {}
    for pos in POS_MIN:
        take = pools[pos][:POS_MIN[pos]]
        chosen += take
        counts[pos] = len(take)
    leftovers = []
    for pos in POS_MIN:
        leftovers += pools[pos][POS_MIN[pos]:]
    leftovers.sort(key=lambda r: r[key], reverse=True)
    for r in leftovers:
        if len(chosen) >= XI_SIZE:
            break
        pos = r["position"]
        if counts.get(pos, 0) < POS_MAX[pos]:
            chosen.append(r)
            counts[pos] = counts.get(pos, 0) + 1
    chosen.sort(key=lambda r: r[key], reverse=True)
    return chosen


def _ranked(rows, key, reverse=True):
    out = [dict(r) for r in sorted(rows, key=lambda r: r[key], reverse=reverse)]
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


def rank_captains(rows: list) -> list:
    return _ranked(rows, "captain_ev")


def rank_value(rows: list) -> list:
    return _ranked([r for r in rows if r.get("value") is not None], "value")


def differentials(rows: list, max_ownership: float = DIFF_MAX_OWNERSHIP,
                  min_xpts: float = DIFF_MIN_XPTS) -> list:
    pool = [r for r in rows
            if r.get("ownership_pct") is not None
            and r["ownership_pct"] < max_ownership
            and r["x_points"] >= min_xpts]
    return _ranked(pool, "x_points")


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


def blowout_teams(fantasy_round: int, top_n: int = BLOWOUT_FIXTURES) -> set:
    """Teams playing in the round's highest combined-lambda (most lopsided/high-scoring)
    fixtures. Uses core.fixtures lambdas (odds-derived where present)."""
    fx = fixtures.by_round(fantasy_round)
    scored = []
    for f in fx:
        lh, la = f.lambdas()
        scored.append((lh + la, f))
    scored.sort(key=lambda t: t[0], reverse=True)
    teams = set()
    for _total, f in scored[:top_n]:
        teams.add(f.home)
        teams.add(f.away)
    return teams


def blowout_transfers(rows: list, teams: set) -> list:
    """Attackers (FWD/MID) from the blowout fixtures, ranked by x_points."""
    pool = [r for r in rows if r["team"] in teams and r["position"] in ("FWD", "MID")]
    return _ranked(pool, "x_points")
