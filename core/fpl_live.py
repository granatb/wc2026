"""Live FPL gameweek data + realized squad grading (the "so far" layer).

Two endpoints on top of core/fpl_api's three:
  event/{gw}/live/     -> per-element realized stats (minutes, total_points, ...)
  fixtures/?event={gw} -> the gameweek's fixtures with finished flags

Network lives in the fetch_* functions; grade_squad and every helper below it
are pure and unit-tested against synthetic payloads in tests/test_fpl_live.py.
Mirrors core/fpl_api.py's split. The cache (data/fpl/live_gw{N}.json) is a
convenience for offline rebuilds, not a record: refresh_live always overwrites
it, and nothing published is derived from a stale copy without saying so (the
site labels the panel with the fetch timestamp).

Name drift: the GW1 state files carry capture-time web_names, and web_names
shift under a live season ("Sangaré" became "I.Sangaré" when a second Sangaré
joined the league). Every live join therefore resolves names defensively via
the state's optional "aliases" map ({old_state_name: current_web_name},
validated by games/fpl/state.py) and FAILS LOUDLY listing every name it could
not resolve — a silent skip would publish a 14-man total as if it were real.
"""

from __future__ import annotations

from datetime import datetime, timezone

from core import fpl_api

LIVE_URL = f"{fpl_api.BASE}/event/{{gw}}/live/"
EVENT_FIXTURES_URL = f"{fpl_api.BASE}/fixtures/?event={{gw}}"

# FPL XI formation limits (2026/27 official, games/fpl/rules.md) — the legality
# gate an autosub must pass. Deliberately local constants, same reasoning as
# games/fpl/state.py: these are the game's rules, pinned where they are used.
XI_MIN = {"GK": 1, "DEF": 3, "MID": 2, "FWD": 1}
XI_MAX = {"GK": 1, "DEF": 5, "MID": 5, "FWD": 3}


def cache_name(gameweek: int) -> str:
    return f"live_gw{gameweek}"


# --- network -----------------------------------------------------------------

def fetch_live(gameweek: int) -> dict:
    return fpl_api._get_json(LIVE_URL.format(gw=gameweek))


def fetch_event_fixtures(gameweek: int) -> list:
    return fpl_api._get_json(EVENT_FIXTURES_URL.format(gw=gameweek))


def refresh_live(gameweek: int, fetch_live_fn=None, fetch_fixtures_fn=None,
                 now=None) -> dict:
    """Fetch both live feeds and OVERWRITE data/fpl/live_gw{N}.json.

    Unlike the bootstrap cache (a build input worth preserving), this cache is
    only ever a snapshot of "now" — keeping an old copy would mean quietly
    grading against stale minutes. The payload carries fetched_at so every
    surface built from it can label its own freshness.
    """
    fetch_live_fn = fetch_live_fn or fetch_live
    fetch_fixtures_fn = fetch_fixtures_fn or fetch_event_fixtures
    payload = {
        "gameweek": gameweek,
        "fetched_at": (now or datetime.now(timezone.utc)).isoformat(),
        "live": fetch_live_fn(gameweek),
        "fixtures": fetch_fixtures_fn(gameweek),
    }
    fpl_api.write_cache(cache_name(gameweek), payload)
    return payload


def read_live_cache(gameweek: int):
    """The cached refresh_live payload, or None if this gameweek never fetched."""
    return fpl_api.read_cache(cache_name(gameweek))


# --- pure helpers --------------------------------------------------------------

def any_fixture_started(fixtures: list, now=None) -> bool:
    """True once any of the gameweek's fixtures has kicked off.

    Trusts the feed's own flags first (started/finished) and falls back to
    comparing kickoff_time against `now` — the bootstrap-adjacent fixtures
    cache carries a `started` flag but the plan's minimal synthetic shape (and
    a mid-refresh feed) may not.
    """
    now = now or datetime.now(timezone.utc)
    for f in fixtures or []:
        if f.get("started") or f.get("finished") or f.get("finished_provisional"):
            return True
        ko = f.get("kickoff_time")
        if ko and fpl_api._parse_utc(ko) <= now:
            return True
    return False


def resolve_squad(state: dict, bootstrap: dict) -> dict:
    """{state squad name: bootstrap element} for all 15, or raise listing EVERY
    failure.

    Resolution order per entry: exact web_name first, then the state's
    "aliases" map ({state_name: current_web_name}) — the shim for players
    renamed after the state was published. Position disambiguates shared
    web_names, exactly like games/fpl/state._resolve; anything still missing
    or ambiguous is collected and reported in ONE error, so a three-name drift
    costs one build failure to diagnose, not three.
    """
    by_name: dict = {}
    for el in bootstrap.get("elements", []):
        by_name.setdefault(el["web_name"], []).append(el)
    aliases = state.get("aliases") or {}

    resolved, problems = {}, []
    for entry in state["squad"]:
        name = entry["name"]
        looked_up = name
        candidates = by_name.get(name)
        if not candidates and name in aliases:
            looked_up = aliases[name]
            candidates = by_name.get(looked_up)
        if not candidates:
            tried = (f"{name!r} (alias {looked_up!r} tried too)"
                     if looked_up != name else f"{name!r}")
            problems.append(f"{tried} is not in the bootstrap")
            continue
        matches = [el for el in candidates
                   if fpl_api.POSITIONS.get(el["element_type"]) == entry["position"]]
        if not matches:
            problems.append(f"{name!r} resolves, but not as a {entry['position']}")
        elif len(matches) > 1:
            problems.append(f"{name!r} ({entry['position']}) is ambiguous "
                            f"({len(matches)} bootstrap candidates)")
        else:
            resolved[name] = matches[0]
    if problems:
        raise ValueError(
            "live join failed — state name(s) do not resolve against the "
            "bootstrap (fix the state or add to its \"aliases\" map): "
            + "; ".join(problems))
    return resolved


def grade_squad(state: dict, live_stats: dict, fixtures: list,
                bootstrap: dict) -> dict:
    """Realized points so far for one published squad state. Pure.

    state:      a games/fpl state dict (raw load_state output or the validated
                copy — extra enrichment keys are ignored). Assumed legal.
    live_stats: the event live payload, {"elements": [{"id", "stats": {...}}]}.
    fixtures:   the gameweek's fixtures, [{"team_h", "team_a", "finished",
                "finished_provisional", "kickoff_time"}].
    bootstrap:  the raw bootstrap payload (elements + teams), for the name and
                club join.

    Scoring semantics (prototyped 2026-08 against the real GW1 feed):
      - a starter with 0 minutes whose club has nothing left to play (every
        fixture finished or finished_provisional; a blank club counts as done)
        is auto-subbed: the first bench player IN BENCH ORDER who actually
        PLAYED and whose entry keeps the XI formation legal (>=3 DEF, >=2 MID,
        >=1 FWD, and no position over its max). GK swaps GK-only, ever.
      - the armband doubles the captain; if the captain has 0 minutes and his
        club is done it falls to the vice, and if the vice is in the same state
        nobody doubles.
      - a player whose club still has an unfinished fixture and who has not
        appeared is "pending" — counted to play, not written off.
      - autosubs and the armband are PROVISIONAL mid-gameweek by construction:
        a still-pending bench player is skipped rather than waited for, and the
        next rebuild self-corrects. The official reconciliation happens once at
        gameweek end, same as FPL's own.

    Returns {"rows": [...], "total_so_far", "players_pending",
    "autosubs_applied", "captain_effective"} where each row is {name, club,
    points, multiplier, status: played|pending|blank|autosub_in, note} — rows
    in presentation order (XI in state order, then bench in bench order),
    points always the RAW total and multiplier the armband/autosub weight, so
    total_so_far == sum(points * multiplier) is checkable from the rows alone.
    """
    teams = {t["id"]: t.get("short_name", "???")
             for t in bootstrap.get("teams", [])}
    resolved = resolve_squad(state, bootstrap)
    stats = {e["id"]: (e.get("stats") or {})
             for e in (live_stats or {}).get("elements", [])}

    club_fixtures: dict = {}
    for f in fixtures or []:
        for tid in (f.get("team_h"), f.get("team_a")):
            club_fixtures.setdefault(tid, []).append(f)

    xi = [e for e in state["squad"] if e["is_starter"]]
    bench = sorted((e for e in state["squad"] if not e["is_starter"]),
                   key=lambda e: e["bench_order"])

    info = {}
    for entry in xi + bench:
        el = resolved[entry["name"]]
        st = stats.get(el["id"], {})
        fx = club_fixtures.get(el["team"], [])
        info[entry["name"]] = {
            "club": teams.get(el["team"], "???"),
            "minutes": st.get("minutes", 0) or 0,
            "points": st.get("total_points", 0) or 0,
            "has_fixture": bool(fx),
            # A blank club is "done": nothing left to play, so its players are
            # write-offs this gameweek and autosub-eligible, same as a DNP.
            "done": all(f.get("finished") or f.get("finished_provisional")
                        for f in fx),
        }

    def dnp(name):
        return info[name]["minutes"] == 0 and info[name]["done"]

    # --- Autosubs -------------------------------------------------------------
    replaced: dict = {}          # out (starter) name -> in (bench) name
    counts = {pos: sum(1 for e in xi if e["position"] == pos) for pos in XI_MIN}

    gk = next((e for e in xi if e["position"] == "GK"), None)
    bench_gk = next((e for e in bench if e["position"] == "GK"), None)
    if gk and bench_gk and dnp(gk["name"]) \
            and info[bench_gk["name"]]["minutes"] > 0:
        replaced[gk["name"]] = bench_gk["name"]

    used = set(replaced.values())
    for cand in bench:
        if cand["position"] == "GK" or cand["name"] in used:
            continue
        if info[cand["name"]]["minutes"] <= 0:
            continue                       # pending or blank — skipped, not waited for
        for starter in xi:
            if starter["position"] == "GK" or starter["name"] in replaced \
                    or not dnp(starter["name"]):
                continue
            trial = dict(counts)
            trial[starter["position"]] -= 1
            trial[cand["position"]] += 1
            if all(XI_MIN[p] <= trial[p] <= XI_MAX[p] for p in XI_MIN):
                counts = trial
                replaced[starter["name"]] = cand["name"]
                used.add(cand["name"])
                break

    # --- Armband ----------------------------------------------------------------
    captain = next(e for e in xi if e["is_captain"])
    vice = next(e for e in xi if e["is_vice"])
    if not dnp(captain["name"]):
        captain_effective = captain["name"]
    elif not dnp(vice["name"]):
        captain_effective = vice["name"]
    else:
        captain_effective = None

    # --- Rows ------------------------------------------------------------------
    in_for = {v: k for k, v in replaced.items()}
    rows = []
    for entry in xi + bench:
        name = entry["name"]
        i = info[name]
        note = ""
        if entry["is_starter"]:
            if name in replaced:
                status, multiplier = "blank", 0
                note = f"0 minutes — {replaced[name]} comes in"
            elif i["minutes"] > 0:
                status, multiplier = "played", 1
            elif not i["done"]:
                status, multiplier, note = "pending", 1, "to play"
            else:
                status, multiplier = "blank", 0
                note = ("no fixture this gameweek" if not i["has_fixture"]
                        else "0 minutes")
        else:
            if name in in_for:
                status, multiplier = "autosub_in", 1
                note = f"in for {in_for[name]}"
            elif i["minutes"] > 0:
                status, multiplier = "played", 0
            elif not i["done"]:
                status, multiplier, note = "pending", 0, "to play"
            else:
                status, multiplier = "blank", 0
                note = "no fixture this gameweek" if not i["has_fixture"] else ""
        if captain_effective == name:
            multiplier *= 2
            if name != captain["name"]:
                note = (note + " · " if note else "") + "inherits the armband"
        elif name == captain["name"] and captain_effective != name:
            extra = (f"armband passes to {captain_effective}"
                     if captain_effective else "armband lost — vice blanked too")
            note = (note + " · " if note else "") + extra
        rows.append({"name": name, "club": i["club"], "points": i["points"],
                     "multiplier": multiplier, "status": status, "note": note})

    return {
        "rows": rows,
        "total_so_far": sum(r["points"] * r["multiplier"] for r in rows),
        "players_pending": sum(1 for r in rows
                               if r["status"] == "pending" and r["multiplier"] > 0),
        "autosubs_applied": [{"out": o, "in": n} for o, n in replaced.items()],
        "captain_effective": captain_effective,
    }
