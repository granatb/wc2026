# FPL Phase 4c — the live duel (points so far) + consensus reset machinery

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans, task-by-task.
> Branch `fpl-live-duel` off main. Suite: `python3 -m unittest discover -s tests -t .`
> (747 green at start), green at every commit. Stage by explicit path only. Do not push,
> do not merge, do not deploy.

**Goal (owner, 2026-08-24):** the WC-style "so far" reality layer for FPL — the landing
duel strip and both squad pages show each squad's REALIZED points during/after a
gameweek, next to the frozen projections. Plus the machinery to rebuild the consensus
squad from actual ownership at GW2 (its Wildcard).

**Owner decisions embedded here, do not re-litigate:**
1. Articles stay frozen (standing 07-04 rule). The live layer is the landing strip and
   a small panel on the two squad pages — the WC "Our XI so far" pattern (07-06).
2. From GW2 the Consensus XI = the actual most-owned legal template (real ownership
   data exists post-deadline; the GW1 expert-tally method is retired with a method
   note). The squad declares its first Wildcard to do the full rebuild under real
   rules. GW1 is still graded as published.

## Context

- Live data: `https://fantasy.premierleague.com/api/event/{gw}/live/` (per-element
  stats incl. total_points, minutes) + `/api/fixtures/?event={gw}` (`finished`,
  `finished_provisional`, kickoff) + bootstrap for id→name/team. All free, no auth.
- Scoring semantics already prototyped this week (see git log context): a starter with
  0 minutes whose club's match is `finished or finished_provisional` gets the first
  same-role-compatible bench player IN BENCH ORDER who played (GK↔GK only; outfield
  must keep ≥3 DEF, ≥2 MID, ≥1 FWD legal); captain doubles, falls to vice if the
  captain has 0 minutes and his club is done; pending players are "to play".
- **Names shift under the season** (live example: our cached "Sangaré" is now
  "I.Sangaré" after "M.Sangaré" joined BRE mid-window; Konsa moved AVL→ARS). Every
  live join must resolve names defensively and FAIL LOUDLY listing unresolved names.
- The GW1 states in games/fpl/*.json use capture-time web_names. Do NOT rewrite the
  state files in this phase; instead the live joiner accepts a per-state
  `name_aliases` map (state file may carry `"aliases": {"Sangaré": "I.Sangaré"}`) —
  add that key to state.json/state_consensus.json for the known rename, validated.

## Tasks

- [ ] **1. `core/fpl_live.py`** — network + pure split, mirroring fpl_api/espn:
  `fetch_live(gw)`, `fetch_event_fixtures(gw)` (cache to data/fpl/live_gw{N}.json,
  refresh always overwrites — this cache is a convenience, not a record), and PURE
  `grade_squad(state, live_stats, fixtures, bootstrap)` returning per-player rows
  {name, club, points, multiplier, status: played|pending|blank|autosub_in, note} plus
  {total_so_far, players_pending, autosubs_applied, captain_effective}. Full offline
  test suite with synthetic payloads: autosub chain incl. formation legality, GK-only
  swap, captain→vice fallback, pending players, unresolved-name failure, alias lookup.
  Reference truth for GW1: Model squad = 42 shown + Watkins→Calvert-Lewin autosub
  (published bench order N.Williams first would give 44; the PUBLISHED state is the
  truth for the site: expect 44 from grade_squad on the published state once AVL and
  NFO are finished; write the test from synthetic data, not this note).

- [ ] **2. Landing strip + squad-page panels.** `fpl_build` gains `--live` (default
  on when bootstrap says the gw `is_current` and any fixture has started): the duel
  strip shows "so far" totals next to projections ("Model 44 · Consensus 42, 1 to
  play"), each squad page gets a compact realized table (player, pts, status) above
  the frozen prose with a "live, updates on rebuild" timestamp label. Article
  HTML/JSON/md bodies stay FROZEN — assert byte-identical article files in a test
  when --live only changes landing + the panel block. WC pages byte-identical as
  always.

- [ ] **3. Consensus reset command.** `python3 -m evmax.build --gw N --reset-consensus`
  (or a small scripts/ entry): builds the most-owned legal 15 from live bootstrap
  ownership (top selected_by_percent per position, greedy legalize under budget/quotas/
  club cap; captain = highest-owned premium, vice next), writes state_consensus.json
  with `chips_used: ["wildcard"]` and strategy note, validates via games/fpl/state.py.
  DO NOT run it against the real feed in this phase — implement + test with synthetic
  bootstrap payloads only; the owner triggers it before the GW2 deadline.

- [ ] **4. Ops note + CHANGELOG.** README gains the in-gameweek routine: rebuild with
  --live + deploy after each match day (cron later). CHANGELOG entry. Suite count
  updated.

## Out of scope
Deploying, running the consensus reset for real, rewriting GW1 states' names, cron
automation, EO columns, transfer recommendations.
