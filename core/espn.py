"""ESPN hidden-API client (free, no key).

Two endpoints:
  scoreboard  site.api.espn.com/.../soccer/fifa.world/scoreboard?dates=YYYYMMDD
              -> schedule (teams, kickoff) + embedded match odds (1X2 + totals).
  propBets    sports.core.api.espn.com/.../events/{id}/competitions/{id}/odds/{prov}/propBets
              -> player goalscorer markets; athlete is a $ref to resolve to a name.

Network lives here; the parse_* / derive_* functions are pure and unit-tested. Match
odds are turned into Dixon-Coles (lh, la, rho) via core.odds_math. Player goalscorer
odds become relative goal weights for the engine's market_rates path.

ESPN odds are a single book (DraftKings, provider id 100) and the schema is
undocumented — extraction is deliberately tolerant.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

import config

from . import odds_math

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_HERE, "data")
ODDS_CACHE = os.path.join(DATA_DIR, "odds")

SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
CORE = "https://sports.core.api.espn.com/v2/sports/soccer/leagues/fifa.world"
DRAFTKINGS = 100

# Which fantasy round maps to which calendar dates (WC2026). Refresh queries these and
# stamps the round, so we don't depend on ESPN's round labels (which don't split group
# matchdays). Edit if the schedule shifts.
ROUND_DATES = {
    1: ("20260611", "20260617"),
    2: ("20260618", "20260624"),
    3: ("20260624", "20260627"),
    4: ("20260628", "20260703"),   # R32
    5: ("20260704", "20260707"),   # R16
    6: ("20260709", "20260711"),   # QF
    7: ("20260714", "20260715"),   # SF
    8: ("20260718", "20260719"),   # Final (+ bronze)
}


def _get_json(url: str, params: dict | None = None) -> object:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --- network ---------------------------------------------------------------

def fetch_scoreboard(date_yyyymmdd: str) -> dict:
    return _get_json(SCOREBOARD, {"dates": date_yyyymmdd})


def fetch_propbets(event_id: str, provider: int = DRAFTKINGS) -> dict:
    """All prop-bet pages for an event (the feed paginates at ~1000 items)."""
    base = f"{CORE}/events/{event_id}/competitions/{event_id}/odds/{provider}/propBets"
    first = _get_json(base, {"lang": "en", "region": "us", "limit": 1000})
    items = list(first.get("items", []))
    for pg in range(2, (first.get("pageCount") or 1) + 1):
        nxt = _get_json(base, {"lang": "en", "region": "us", "limit": 1000, "page": pg})
        items.extend(nxt.get("items", []))
    first["items"] = items
    return first


_ATHLETES_PATH = os.path.join(DATA_DIR, "athletes.json")
_athlete_cache: dict | None = None


def fetch_athlete_name(ref_url: str) -> str | None:
    """Resolve an athlete $ref to a display name, memoised to data/athletes.json so
    repeat refreshes don't re-hit the network for the same players."""
    global _athlete_cache
    if _athlete_cache is None:
        _athlete_cache = {}
        if os.path.exists(_ATHLETES_PATH):
            with open(_ATHLETES_PATH, encoding="utf-8") as fh:
                _athlete_cache = json.load(fh)
    if ref_url in _athlete_cache:
        return _athlete_cache[ref_url]
    try:
        data = _get_json(ref_url)
        name = data.get("displayName") or data.get("fullName")
    except Exception:
        name = None
    _athlete_cache[ref_url] = name
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_ATHLETES_PATH, "w", encoding="utf-8") as fh:
        json.dump(_athlete_cache, fh)
    return name


# --- pure parsing ----------------------------------------------------------

def _parse_american(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return odds_math.american_to_decimal(float(val))
    t = str(val).strip().upper().replace("+", "")
    if t in ("EVEN", "EV"):
        return 2.0
    try:
        return odds_math.american_to_decimal(float(t))
    except ValueError:
        return None


def _price_decimal(node: dict | None) -> float | None:
    """Decimal price from an ESPN odds node. Handles the live shapes:
    {moneyLine: 255}; {close/open: {odds: '+390'}} (moneyline/total);
    {current/open: {over: {decimal: 16.0, american: '+1500'}}} (props)."""
    if not isinstance(node, dict):
        return None
    if node.get("moneyLine") is not None:
        return odds_math.american_to_decimal(float(node["moneyLine"]))
    for state in ("close", "current", "open"):
        sub = node.get(state)
        if isinstance(sub, dict):
            leaf = sub.get("over") if isinstance(sub.get("over"), dict) else sub
            if leaf.get("decimal"):
                return float(leaf["decimal"])
            if leaf.get("odds") is not None:
                d = _parse_american(leaf["odds"])
                if d:
                    return d
    if node.get("decimal"):
        return float(node["decimal"])
    if node.get("odds") is not None:
        return _parse_american(node["odds"])
    return None


def parse_scoreboard(raw: dict, fantasy_round: int) -> list:
    """Scoreboard JSON -> list of match dicts with schedule + 1X2 + totals.

    Only events whose home/away/draw prices are all present are returned with odds;
    others come back with h2h=None (engine falls back to priors)."""
    out = []
    for ev in raw.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        comps = comp.get("competitors", [])
        home = next((c for c in comps if c.get("homeAway") == "home"), {})
        away = next((c for c in comps if c.get("homeAway") == "away"), {})
        ht = home.get("team", {}).get("displayName")
        at = away.get("team", {}).get("displayName")
        if not ht or not at:
            continue
        rec = {
            "match_id": str(ev.get("id")),
            "home": ht, "away": at,
            "kickoff_utc": ev.get("date"),
            "stage": (comp.get("status", {}).get("type", {}).get("name")
                      or ev.get("season", {}).get("slug") or "GROUP"),
            "fantasy_round": fantasy_round,
        }
        odds_list = comp.get("odds") or []
        if odds_list and odds_list[0]:
            o = odds_list[0]
            ml = o.get("moneyline") or {}
            rec["h2h"] = {
                "home": _price_decimal(ml.get("home")),
                "draw": _price_decimal(o.get("drawOdds")),
                "away": _price_decimal(ml.get("away")),
            }
            tot = o.get("total") or {}
            rec["totals"] = {
                "line": o.get("overUnder"),
                "over": _price_decimal(tot.get("over")),
                "under": _price_decimal(tot.get("under")),
            }
        else:
            rec["h2h"] = None
            rec["totals"] = None
        out.append(rec)
    return out


GROUP_STAGE_RANGE = ("20260611", "20260627")  # full WC2026 group stage


def assign_group_matchdays(rows: list) -> list:
    """Tag each group match with fantasy_round = its matchday (1/2/3).

    A team plays once per matchday; in a group, a match is the k-th game for *both*
    its teams. So ordering each team's matches by kickoff and taking the position is
    robust to timezone/date-boundary issues (chronological order is timezone-invariant).
    Requires the full group stage so every team has its 3 matches.
    """
    from collections import defaultdict
    by_team: dict[str, list] = defaultdict(list)
    for r in rows:
        by_team[r["home"]].append(r)
        by_team[r["away"]].append(r)
    position: dict[str, list] = defaultdict(list)
    for _team, matches in by_team.items():
        for i, r in enumerate(sorted(matches, key=lambda r: r.get("kickoff_utc") or "")):
            position[r["match_id"]].append(i + 1)
    for r in rows:
        pos = position.get(r["match_id"], [1])
        r["fantasy_round"] = min(pos)  # both teams agree; min guards partial data
    return rows


def first_match_per_team(rows: list) -> list:
    """Keep each team's earliest match in the window — its matchday for this round.

    WC group matchdays overlap in the calendar, so a fixed date window can catch a
    team's next matchday too. Greedily keeping the first appearance of each team
    yields exactly one match per team (the round's matchday) and drops the bleed.
    """
    kept, used = [], set()
    for r in sorted(rows, key=lambda r: r.get("kickoff_utc") or ""):
        if r["home"] in used or r["away"] in used:
            continue
        kept.append(r)
        used.add(r["home"])
        used.add(r["away"])
    return kept


def derive_match(rec: dict) -> dict:
    """Add Dixon-Coles (lam_home, lam_away, rho) from a parsed match's 1X2 + totals."""
    h = rec.get("h2h")
    if not h or not all(h.get(k) for k in ("home", "draw", "away")):
        return {}
    method = getattr(config, "DEVIG_METHOD", "proportional")
    pH, pD, pA = odds_math.devig_by_method([h["home"], h["draw"], h["away"]], method)
    p_over = line = None
    tot = rec.get("totals") or {}
    if tot.get("over") and tot.get("under") and tot.get("line"):
        ov, un = odds_math.devig_by_method([tot["over"], tot["under"]], method)
        p_over, line = ov, tot["line"]
    lh, la, rho = odds_math.solve_dc(pH, pD, pA, p_over=p_over, line=line or 2.5)
    return {"lam_home": round(lh, 3), "lam_away": round(la, 3), "rho": round(rho, 4),
            "p1x2": {"home": pH, "draw": pD, "away": pA}}


def parse_propbets(raw: dict) -> dict:
    """propBets JSON -> {type_name_lower: [(athlete_ref, decimal_odds)]}."""
    out: dict[str, list] = {}
    for item in raw.get("items", []):
        tname = (item.get("type", {}).get("name") or "").strip().lower()
        ref = item.get("athlete", {}).get("$ref")
        dec = _price_decimal(item)
        if not tname or not ref or dec is None:
            continue
        out.setdefault(tname, []).append((ref, dec))
    return out


def save_match_odds(match_id: str, data: dict) -> dict:
    """Persist a match record, PRESERVING the last-seen ("closing") odds.

    ESPN drops live odds once a match kicks off, so a later refresh returns no odds for
    it. We must NOT overwrite a good pre-match line with that empty fallback — that line
    is the ground truth needed to backtest and calibrate. So we merge over any previous
    record: when the new pull has no odds we keep the prior lambdas (and flag them as
    closing), while still updating status/score. `odds_captured_at` stamps when the line
    was last live. Returns the merged record written.
    """
    from datetime import datetime, timezone
    os.makedirs(ODDS_CACHE, exist_ok=True)
    prev = load_match_odds(match_id) or {}
    merged = {**prev, **data}
    if data.get("lam_home") is not None:
        merged["odds_captured_at"] = datetime.now(timezone.utc).isoformat()
        merged.pop("odds_status", None)
    elif prev.get("lam_home") is not None:
        # odds vanished from ESPN -> freeze the closing line; keep refreshing status/score
        merged["lam_home"], merged["lam_away"] = prev["lam_home"], prev["lam_away"]
        merged["rho"] = prev.get("rho", 0.0)
        merged["odds_captured_at"] = prev.get("odds_captured_at")
        merged["odds_status"] = "closing"
    path = os.path.join(ODDS_CACHE, f"{match_id}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2)
    return merged


def load_match_odds(match_id: str) -> dict | None:
    path = os.path.join(ODDS_CACHE, f"{match_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_player_rates(fantasy_round: int, rates: dict) -> str:
    os.makedirs(ODDS_CACHE, exist_ok=True)
    path = os.path.join(ODDS_CACHE, f"player_rates_r{fantasy_round}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rates, fh, indent=2)
    return path


def load_player_rates(fantasy_round: int) -> dict:
    path = os.path.join(ODDS_CACHE, f"player_rates_r{fantasy_round}.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def goal_weights(parsed: dict, athlete_names: dict) -> dict:
    """Per-player goal weight from goalscorer props.

    Prefers an 'anytime' market (-> absolute goal rate); falls back to 'first
    goalscorer' (-> relative weight). athlete_names maps ref_url -> player name.
    Weights are de-margined implied probabilities (shrunk).
    """
    pick = None
    for key in parsed:
        if "anytime" in key:
            pick, mode = key, "anytime"
            break
    if pick is None:
        for key in parsed:
            if "first" in key:
                pick, mode = key, "first"
                break
    if pick is None:
        return {}
    rates: dict[str, float] = {}
    for ref, decimal in parsed[pick]:
        name = athlete_names.get(ref)
        if not name:
            continue
        import config
        prob = (1.0 / decimal) * config.SCORER_MARGIN_SHRINK  # de-margin (2-way prop)
        rates[name] = odds_math.scorer_prob_to_goal_rate(prob) if mode == "anytime" else prob
    return rates
