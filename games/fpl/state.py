"""Loader + validator for the two published FPL squad states.

The site fields two real teams under real rules (owner decisions 2026-08-19):
`games/fpl/state.json` (strategy "model" — pure engine EV over the discounted
horizon) and `games/fpl/state_consensus.json` (strategy "consensus" — the
best-follower squad tallied from the expert research corpus). Both are frozen
published claims once a gameweek locks, so an illegal or misspelled state must
kill the build, never degrade it.

Pure: no I/O beyond `load_state`'s file read, no HTTP, no simulation. Prices
come from the FPL bootstrap at load time and are never stored in the state
files — the bootstrap is the single source of truth for what a player costs,
and a stored price silently goes stale.

State shape (see the two JSON files):
    team_name      display name ("The Model XI" / "The Consensus XI")
    strategy       "model" | "consensus"
    free_transfers banked FTs going into the next gameweek
    chips_used     chip names already burned this season
    source_count   (consensus only, optional) how many expert sources the
                   mention-tally ran across this gameweek — the prose quotes
                   it, so it lives in the state as part of the published claim
                   rather than hardcoded in a template
    squad          exactly 15 of {name, position, is_starter, bench_order,
                   is_captain, is_vice} — `name` is the player's exact FPL
                   web_name, diacritics intact ("Sánchez", "Groß", "João Pedro")
"""

from __future__ import annotations

import json

# FPL squad rules (2026/27 official, games/fpl/rules.md). Deliberately local
# constants rather than an import from evmax.articles: games/ must not depend
# on the site layer, and these are the game's rules, not the site's.
SQUAD_QUOTA = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
XI_MIN = {"GK": 1, "DEF": 3, "MID": 2, "FWD": 1}
XI_MAX = {"GK": 1, "DEF": 5, "MID": 5, "FWD": 3}
SQUAD_BUDGET = 100.0
MAX_PER_CLUB = 3
STRATEGIES = ("model", "consensus")
BENCH_SIZE = 4

_ENTRY_KEYS = ("name", "position", "is_starter", "bench_order",
               "is_captain", "is_vice")


def load_state(path: str) -> dict:
    """Read a raw state file. No validation — see validate_state / load_squad."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_squad(path: str, players: list) -> dict:
    """Load + validate + enrich in one step. Raises ValueError on any problem."""
    return validate_state(load_state(path), players)


def _resolve(entry: dict, by_name: dict) -> dict:
    """The bootstrap player this squad entry names, or raise.

    Names are exact web_names (diacritics intact) — "Sánchez" is a different
    string from "Sanchez" and MUST stay one, because the artifact rows and the
    public feeds key on the web_name too. Two real players can share a
    web_name; the entry's position disambiguates, and a still-ambiguous name
    is an error rather than a guess — this file is a published claim.
    """
    name = entry["name"]
    candidates = by_name.get(name)
    if not candidates:
        raise ValueError(f"squad name {name!r} does not resolve against the FPL "
                         f"bootstrap — names must be exact web_names, "
                         f"diacritics included")
    matches = [p for p in candidates if p["position"] == entry["position"]]
    if not matches:
        have = ", ".join(sorted({p["position"] for p in candidates}))
        raise ValueError(f"squad entry {name!r} says position "
                         f"{entry['position']!r} but the bootstrap has {name!r} "
                         f"as {have}")
    if len(matches) > 1:
        teams = ", ".join(sorted(p["team"] for p in matches))
        raise ValueError(f"squad name {name!r} ({entry['position']}) is "
                         f"ambiguous in the bootstrap ({teams}) — cannot "
                         f"publish a squad whose players are guesses")
    return matches[0]


def validate_state(state: dict, players: list) -> dict:
    """Validate a squad state against the FPL bootstrap and enrich it.

    players: core.fpl_api.parse_players output (dicts with name/team/position/
    price at minimum). Returns a new state dict whose squad entries additionally
    carry `team` and `price` from the bootstrap, plus a top-level `total_cost`.

    Raises ValueError naming the first problem found. Checks, in order:
    schema shape, name resolution (exact web_names), position quota, club cap,
    budget, XI size + formation legality, captain/vice, bench order.
    """
    # --- Schema shape --------------------------------------------------------
    strategy = state.get("strategy")
    if strategy not in STRATEGIES:
        raise ValueError(f"strategy must be one of {STRATEGIES}, got {strategy!r}")
    team_name = state.get("team_name")
    if not team_name or not isinstance(team_name, str):
        raise ValueError("team_name must be a non-empty string")
    if "source_count" in state:
        sc = state["source_count"]
        if not isinstance(sc, int) or isinstance(sc, bool) or sc < 1:
            raise ValueError(f"source_count must be a positive integer when "
                             f"present, got {sc!r}")
    squad = state.get("squad")
    if not isinstance(squad, list) or len(squad) != 15:
        n = len(squad) if isinstance(squad, list) else "no"
        raise ValueError(f"squad must hold exactly 15 entries, got {n}")
    for entry in squad:
        missing = [k for k in _ENTRY_KEYS if k not in entry]
        if missing:
            raise ValueError(f"squad entry {entry.get('name', '?')!r} is missing "
                             f"key(s): {', '.join(missing)}")
    names = [e["name"] for e in squad]
    if len(set(names)) != 15:
        dupes = sorted({n for n in names if names.count(n) > 1})
        raise ValueError(f"duplicate squad name(s): {', '.join(dupes)}")

    # --- Name resolution + enrichment ---------------------------------------
    by_name: dict = {}
    for p in players:
        by_name.setdefault(p["name"], []).append(p)
    enriched = []
    for entry in squad:
        player = _resolve(entry, by_name)
        e = dict(entry)
        e["team"] = player["team"]
        e["price"] = player["price"]
        enriched.append(e)

    # --- Squad-level legality ------------------------------------------------
    for pos, need in SQUAD_QUOTA.items():
        have = sum(1 for e in enriched if e["position"] == pos)
        if have != need:
            raise ValueError(f"position quota violated at {pos}: need {need}, "
                             f"have {have}")
    clubs: dict = {}
    for e in enriched:
        clubs[e["team"]] = clubs.get(e["team"], 0) + 1
    over = {t: c for t, c in clubs.items() if c > MAX_PER_CLUB}
    if over:
        raise ValueError(f"club cap of {MAX_PER_CLUB} violated: {over}")
    total_cost = round(sum(e["price"] for e in enriched), 1)
    if total_cost > SQUAD_BUDGET:
        raise ValueError(f"squad costs {total_cost}m — over the "
                         f"{SQUAD_BUDGET}m budget")

    # --- XI legality -----------------------------------------------------------
    xi = [e for e in enriched if e["is_starter"]]
    bench = [e for e in enriched if not e["is_starter"]]
    if len(xi) != 11:
        raise ValueError(f"exactly 11 starters required, got {len(xi)}")
    for pos in SQUAD_QUOTA:
        n = sum(1 for e in xi if e["position"] == pos)
        if not (XI_MIN[pos] <= n <= XI_MAX[pos]):
            raise ValueError(f"illegal XI formation at {pos}: {n} "
                             f"(legal range {XI_MIN[pos]}-{XI_MAX[pos]})")

    # --- Captaincy ------------------------------------------------------------
    captains = [e for e in enriched if e["is_captain"]]
    vices = [e for e in enriched if e["is_vice"]]
    if len(captains) != 1:
        raise ValueError(f"exactly 1 captain required, got {len(captains)}")
    if len(vices) != 1:
        raise ValueError(f"exactly 1 vice-captain required, got {len(vices)}")
    if captains[0]["name"] == vices[0]["name"]:
        raise ValueError(f"captain and vice must differ, both are "
                         f"{captains[0]['name']!r}")
    for role, e in (("captain", captains[0]), ("vice-captain", vices[0])):
        if not e["is_starter"]:
            raise ValueError(f"the {role} ({e['name']!r}) must be a starter")

    # --- Bench order -----------------------------------------------------------
    for e in xi:
        if e["bench_order"] is not None:
            raise ValueError(f"starter {e['name']!r} carries bench_order "
                             f"{e['bench_order']!r} — starters must be null")
    orders = sorted(e["bench_order"] for e in bench
                    if isinstance(e["bench_order"], int))
    if orders != list(range(1, BENCH_SIZE + 1)):
        raise ValueError(f"bench_order must be exactly 1-{BENCH_SIZE}, "
                         f"got {[e['bench_order'] for e in bench]}")
    first = next(e for e in bench if e["bench_order"] == 1)
    if first["position"] != "GK":
        raise ValueError(f"bench_order 1 must be the backup GK, got "
                         f"{first['name']!r} ({first['position']})")

    out = dict(state)
    out["squad"] = enriched
    out["total_cost"] = total_cost
    out["free_transfers"] = state.get("free_transfers", 1)
    out["chips_used"] = list(state.get("chips_used", []))
    return out
