"""FPL gameweek match odds: ESPN eng.1 scoreboard -> Dixon-Coles lambdas.

The WC engine's market layer, pointed at the Premier League. core/espn.py owns
fetching, parsing and lambda derivation (parse_scoreboard + derive_match are
league-agnostic); this module owns only what is FPL-specific: which UTC dates a
gameweek spans, mapping ESPN team names onto FPL club short names, and the
data/fpl/odds_gw{N}.json cache.

Fixtures ESPN has not priced yet come back without lambdas -- the caller
(games/fpl/model.load_gameweek) falls back to ratings priors and must say so
loudly. A silently flat fixture list is exactly the failure mode this module
exists to remove: before it existed, every GW1 fixture simulated at the same
league-average lambdas.
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import espn, fpl_api

ESPN_LEAGUE = "eng.1"

# ESPN team displayName -> FPL short_name, the 20 clubs of 2026/27. Both sides
# read from the live feeds on 2026-08-19. Update on promotion/relegation;
# match_espn() raises on any ESPN name it does not know rather than guessing.
ESPN_TO_FPL = {
    "AFC Bournemouth": "BOU",
    "Arsenal": "ARS",
    "Aston Villa": "AVL",
    "Brentford": "BRE",
    "Brighton & Hove Albion": "BHA",
    "Chelsea": "CHE",
    "Coventry City": "COV",
    "Crystal Palace": "CRY",
    "Everton": "EVE",
    "Fulham": "FUL",
    "Hull City": "HUL",
    "Ipswich Town": "IPS",
    "Leeds United": "LEE",
    "Liverpool": "LIV",
    "Manchester City": "MCI",
    "Manchester United": "MUN",
    "Newcastle United": "NEW",
    "Nottingham Forest": "NFO",
    "Sunderland": "SUN",
    "Tottenham Hotspur": "TOT",
}


def _cache_name(gameweek: int) -> str:
    return f"odds_gw{gameweek}"


def gw_dates(fpl_rows: list) -> list:
    """Unique UTC dates (YYYYMMDD, sorted) the gameweek's kickoffs span."""
    dates = {fpl_api._parse_utc(r["kickoff_utc"]).strftime("%Y%m%d")
             for r in fpl_rows if r.get("kickoff_utc")}
    return sorted(dates)


def match_espn(espn_rows: list, fpl_rows: list) -> tuple:
    """Pair ESPN parsed rows with FPL fixture rows by (home, away) club.

    Returns ({fpl_match_id: espn_row}, [unmatched fpl rows]). Raises ValueError
    on an ESPN team name outside ESPN_TO_FPL -- an unknown club means the
    mapping is stale, and guessing would price the wrong fixture.
    """
    by_clubs = {}
    for rec in espn_rows:
        for side in ("home", "away"):
            if rec[side] not in ESPN_TO_FPL:
                raise ValueError(
                    f"unknown ESPN team {rec[side]!r} -- update "
                    "core.fpl_odds.ESPN_TO_FPL for the current season")
        by_clubs[(ESPN_TO_FPL[rec["home"]], ESPN_TO_FPL[rec["away"]])] = rec

    matched, unmatched = {}, []
    for row in fpl_rows:
        rec = by_clubs.get((row["home"], row["away"]))
        if rec is None:
            unmatched.append(row)
        else:
            matched[row["match_id"]] = rec
    return matched, unmatched


def fetch_gw_odds(gameweek: int, fpl_rows: list,
                  fetch=espn.fetch_scoreboard, write: bool = True) -> dict:
    """Fetch the GW's ESPN scoreboards, derive lambdas, key by FPL match id.

    Every matched fixture appears under "matches"; only those ESPN actually
    priced (a full 1X2) carry lam_home/lam_away/rho/p1x2.
    """
    espn_rows = []
    for date in gw_dates(fpl_rows):
        raw = fetch(date, league=ESPN_LEAGUE)
        espn_rows.extend(espn.parse_scoreboard(raw, gameweek))
    matched, unmatched = match_espn(espn_rows, fpl_rows)

    out = {
        "gameweek": gameweek,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "matches": {},
        "unmatched": [f'{r["home"]} v {r["away"]}' for r in unmatched],
    }
    for fpl_id, rec in matched.items():
        entry = {
            "home": ESPN_TO_FPL[rec["home"]],
            "away": ESPN_TO_FPL[rec["away"]],
            "espn_id": rec["match_id"],
            "h2h": rec.get("h2h"),
            "totals": rec.get("totals"),
        }
        entry.update(espn.derive_match(rec))
        out["matches"][fpl_id] = entry
    if write:
        fpl_api.write_cache(_cache_name(gameweek), out)
    return out


def read_cached(gameweek: int):
    """The cached odds payload for a gameweek, or None."""
    return fpl_api.read_cache(_cache_name(gameweek))
