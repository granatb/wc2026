#!/usr/bin/env python3
"""wc2026 CLI dispatcher.

Loads a game's rules + state, runs its model against the shared Monte Carlo engine,
and prints the order book for the open window.

    python manage.py holdet_gold --round 2
    python manage.py malspillet  --round 1 --sims 200000
    python manage.py fifa        --round 1
    python manage.py all         --round 2

Run from inside the wc2026/ directory (so `core` and `games` import cleanly).
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys

GAMES = ["fpl", "fifa", "holdet_gold", "holdet_yolo", "holdet_free", "malspillet"]

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import config


def load_state(game: str) -> dict:
    path = os.path.join(HERE, "games", game, "state.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def refresh(fantasy_round: int, with_props: bool = False) -> None:
    """Pull schedule + match odds from ESPN (free, no key) into data/.

    Player props (anytime-goal) are opt-in via with_props: they require resolving
    ~1000+ athlete names and only matter once player priors are populated.
    """
    from core import espn, schedule_api, fixtures

    if fantasy_round <= 3:
        # Group rounds: fetch the whole group stage and tag each match by matchday
        # (chronological per team) — timezone-proof, no date-boundary bleed.
        start, end = espn.GROUP_STAGE_RANGE
        print(f"Refreshing ESPN group stage ({start}-{end}); tagging matchdays...")
        rows = espn.parse_scoreboard(espn.fetch_scoreboard(f"{start}-{end}"), fantasy_round)
        rows = espn.assign_group_matchdays(rows)
        rows = [r for r in rows if r["fantasy_round"] == fantasy_round]
    elif fantasy_round in espn.ROUND_DATES:
        # Knockouts: teams play once per round; a date window is unambiguous.
        start, end = espn.ROUND_DATES[fantasy_round]
        print(f"Refreshing ESPN scoreboard for round {fantasy_round} ({start}-{end})...")
        rows = espn.parse_scoreboard(espn.fetch_scoreboard(f"{start}-{end}"), fantasy_round)
        rows = espn.first_match_per_team(rows)
    else:
        print(f"  no window for round {fantasy_round}; edit espn.ROUND_DATES.")
        return
    print(f"  {len(rows)} matches (one per team).")

    # Match odds -> Dixon-Coles, cache per match + assemble schedule entries.
    schedule_entries, priced = [], 0
    for rec in rows:
        derived = espn.derive_match(rec)
        merged = espn.save_match_odds(rec["match_id"], {**rec, **derived})
        if merged.get("lam_home") is not None:  # fresh OR preserved closing line
            priced += 1
        schedule_entries.append({
            "match_id": rec["match_id"], "home": rec["home"], "away": rec["away"],
            "kickoff_utc": rec["kickoff_utc"], "stage": rec["stage"],
            "fantasy_round": fantasy_round,
            "lam_home": merged.get("lam_home"), "lam_away": merged.get("lam_away"),
        })
    print(f"  priced {priced}/{len(rows)} (rest fall back to priors).")

    # Merge into schedule.json (replace just this round) and reload fixtures.
    existing = []
    if os.path.exists(schedule_api.SCHEDULE_PATH):
        with open(schedule_api.SCHEDULE_PATH, encoding="utf-8") as fh:
            existing = [e for e in json.load(fh) if e.get("fantasy_round") != fantasy_round]
    schedule_api.write_schedule(existing + schedule_entries)
    fixtures.SCHEDULE = fixtures.load_from_json()

    if not with_props:
        print("  (player props skipped — pass --props to fetch anytime-goal odds.)")
        return

    # Player goalscorer props -> per-player goal weights for market_rates.
    print("Refreshing ESPN player props (athlete names cached to data/athletes.json)...")
    rates = {}
    for rec in rows:
        try:
            parsed = espn.parse_propbets(espn.fetch_propbets(rec["match_id"]))
            pref = next((k for k in parsed if "anytime" in k),
                        next((k for k in parsed if "first" in k), None))
            if not pref:
                continue
            names = {ref: espn.fetch_athlete_name(ref) for ref, _ in parsed[pref]}
            rates.update(espn.goal_weights(parsed, names))
        except Exception as e:  # undocumented API — keep going on per-match failures
            print(f"  props skip {rec['match_id']}: {e}")
    espn.save_player_rates(fantasy_round, rates)
    print(f"  cached goal rates for {len(rates)} players.")


def run_game(game: str, fantasy_round: int, sims: int, no_cache: bool = False) -> None:
    state = load_state(game)
    # Inject the tunables from config.py (the single control panel) so state.json
    # only ever holds squad data, never behaviour.
    state["research_weight"] = config.weight(game)
    state["ceiling_percentile"] = config.CEILING_PERCENTILE
    # Only games with a sim cache (currently just fpl) look at this; the rest
    # ignore it, same as they already ignore other games' tunables.
    state["no_cache"] = no_cache
    model = importlib.import_module(f"games.{game}.model")
    model.run(state, fantasy_round, sims=sims or config.DEFAULT_SIMS)


def main() -> None:
    ap = argparse.ArgumentParser(description="wc2026 fantasy decision engine")
    ap.add_argument("game", choices=GAMES + ["all", "config"],
                    help="game to run, 'all', or 'config' to view the control panel")
    ap.add_argument("--round", type=int, default=None, dest="fantasy_round",
                    help="fantasy round / matchday to run")
    ap.add_argument("--sims", type=int, default=None, help="Monte Carlo iterations")
    ap.add_argument("--live", action="store_true",
                    help="(fifa) emphasise live captain-chain / sub output")
    ap.add_argument("--refresh", action="store_true",
                    help="pull fresh schedule + match odds into data/ cache before running")
    ap.add_argument("--props", action="store_true",
                    help="also fetch ESPN anytime-goal player props (slower; with --refresh)")
    ap.add_argument("--no-cache", action="store_true", dest="no_cache",
                    help="(fpl) skip the sim cache and force a fresh simulation")
    args = ap.parse_args()

    if args.game == "config":
        print(config.summary())
        return

    if args.fantasy_round is None:
        ap.error("--round is required when running a game")

    if args.refresh:
        try:
            refresh(args.fantasy_round, with_props=args.props)
        except Exception as e:
            print(f"Refresh failed ({type(e).__name__}: {e}).\n"
                  "Running off cached data in data/ instead.")

    targets = GAMES if args.game == "all" else [args.game]
    for g in targets:
        run_game(g, args.fantasy_round, args.sims, no_cache=args.no_cache)


if __name__ == "__main__":
    main()
