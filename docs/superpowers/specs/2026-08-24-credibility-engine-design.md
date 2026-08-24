# The Credibility Engine — design

Owner-approved 2026-08-24 after the GW1 retro. Goal hierarchy (owner): **C → B** —
the model must genuinely, visibly beat the crowd (C); credibility built that way is
what makes the site win (B). The owner's rank is not the optimization target.

## The problem this fixes

Every credibility dent in GW1 was a knowledge-layer failure, not an engine failure:
the double-Spurs-keeper squad advice, the wrong Sangaré (expert meant a player who
joined the league after our capture), holding Watkins into a 0-minute blank while
50k managers sold him, Isak and Maguire minutes mispriced until Reddit corrected us.
"Validate every published player" existed as intent with no enforcement, so under
deadline pressure it silently didn't happen. Intent becomes a mechanical gate.

**Owner delegation (supersedes the WC-era "Bartek writes the notes" rule):** the
system flags, Claude researches the web and adjudicates, notes are written by Claude
with sources, Bartek gets a five-line summary. His notes still always win when he
writes them.

## Decisions

| # | Decision |
|---|---|
| D1 | Publish gate: a build cannot freeze/publish a squad containing a red-flagged player without an overriding sourced research note. Refusal, not warning. |
| D2 | Validation is automated + Claude-run. Deterministic flags in code; judgment via Claude web research in the manual sessions. |
| D3 | Sessions are MANUAL for now ("run Thursday" / "run Monday"), fully documented as runbooks incl. a "schedule this later" section. Owner parked cron. |
| D4 | Reddit sensor: Claude cannot fetch Reddit directly (toolchain-blocked; covert scraping banned by standing policy). Inputs: owner pastes/screenshots, or Claude reads via the owner's logged-in Chrome (claude-in-chrome) during sessions. The Thursday session drafts a "poke holes" shortlist comment for the owner to post. |
| D5 | The public headline metric each week is **points vs the average manager** (and the duel). Beating the crowd must be legible to Reddit at a glance. |
| D6 | Engine adopts the community-validated fixes: joint captaincy objective, bench-spend cap, XI minutes floor, own strength table replacing FDR. |
| D7 | No display ads (off-ladder, breaks the published no-ads promise). Monetization rung 1 = newsletter activation (owner action, Buttondown). |
| D8 | Consensus squad = the real most-owned template from GW2 (Wildcard reset, machinery already merged in phase 4c); it doubles as the owner's "squad A" benchmark. |

## Components

### 1. `core/fpl_diff.py` — the feed diff
Compares the current bootstrap against the last committed snapshot summary
(`data/fpl/feed_snapshot.json`, regenerated each run; a compact projection: per
player id → {web_name, team, status, price, selected, transfers_in/out_event}).
Reports: club changes, renames, new players, removed players, status transitions,
price moves, transfer-flow outliers (out-flow z-score over the player population).
Pure diff logic, offline-tested; a CLI entry (`python3 -m core.fpl_diff --gw N`)
prints the human report the runbooks start with. Would have caught: M.Sangaré's
arrival + rename, Konsa's move, the Watkins exodus.

### 2. Player dossiers + the publish gate (preflight extension)
For every player in any published squad, preflight assembles a dossier:
status, start-prob source (proxy | note | realized starts), start-prob value,
club-changed-since-capture, name drift (alias in use), transfer-flow flag,
news string. Red conditions (any one): status ≠ 'a'; start prob < 0.75 and source
is proxy; club changed; out-flow z-score above threshold; unresolved name.
Green publishes silently. **Red without an overriding note (a research note whose
`sources:` is non-empty and whose date ≥ the flag's trigger) aborts the freeze/build
with a per-player explanation.** Runbook step: Claude researches each red, writes
the note (or changes the squad), re-runs.

### 3. `core/fpl_strength.py` — our own strength table (replaces FDR)
Per-team attack/defence multipliers updated weekly: solve each finished/priced GW's
market lambdas into team terms, combine across weeks with recency weighting and
shrinkage toward the pre-season prior (the FDR-calibrated table is the GW1 prior).
Future-GW lambdas come from this table instead of the FDR mapping as soon as ≥2
gameweeks of market data exist; the per-GW odds cache keeps overriding for the
current priced week. Published as its own site table when stable (differentiation
content). Validation: backtest vs realized goals per week; report in the Monday
runbook.

### 4. Optimizer v2 (`evmax/fpl_articles.py` / squad building)
- Objective = XI xPts + best captain's xPts (joint), over the discounted horizon.
- Bench budget cap: total bench cost ≤ 18.5 (doctrine band), bench players must
  project to start (the existing playing-bench rule stays).
- XI minutes floor: start prob ≥ 0.75 unless a sourced note overrides — aligned
  with the gate so the optimizer cannot propose what the gate would refuse.
- Still the greedy+repair heuristic; exact MILP stays on the roadmap.

### 5. Transfer optimizer v1
Given a squad state + free-transfer count: evaluate every legal single swap (and
flagged-player forced-sale candidates first) on discounted-horizon delta net of
hits (threshold: gain > 4 over the holding horizon per doctrine); output top-5 with
per-swap reasoning rows. Drives the weekly transfer for both squads and the
`transfers` content beat. GW2's first user: the Watkins decision.

### 6. Accuracy grading (backtest v1)
After each GW: per-player |projection − realized| for our xPts and FPL's own
`ep_next` (captured pre-deadline into the frozen snapshots from now on), plus
squad-level projected vs realized. Cumulative accuracy table published on the site
(the accuracy league). This is the C-metric made public.

### 7. Runbooks (docs/runbooks/)
- `thursday-pre-deadline.md`: refresh → diff report → red-flag research (Claude,
  web + owner's Chrome for Reddit) → notes → re-sim → optimize squads + transfer →
  gate check → build --live → deploy → draft posts (shortlist comment + any article
  tweaks) → five-line owner summary. Includes the newsletter-blurb step.
- `monday-post-gw.md`: final grading → duel + vs-average update → accuracy table →
  scorecard post draft → transfer shortlist preview → season-learnings entry.
- Both end with "to schedule this later": the exact `/schedule` (scheduled cloud
  agent) or local cron incantation, parked until the owner opts in.

### 8. `docs/research/season-learnings.md`
Append-only log: mistake → root cause → structural fix → status. Seeded with GW1's
five (keeper pair, Sangaré, Watkins, Isak, Maguire + the bench-order mismatch).

## Non-goals (now)
Scheduled/cron sessions (parked, D3). Exact MILP. EO/rank-aware objective for the
model squad (the duel needs it pure). MCP server + public dataset (next phase, after
the competitor research lands). Reddit automation of any kind. Display ads (D7).

## GW2 operational sequence (after implementation lands, before Friday deadline)
1. Bootstrap refresh → diff report (expect the Sangaré/Konsa churn to appear).
2. `--reset-consensus` (Wildcard rebuild to real template) → review → commit.
3. Fix Model-state web_names via aliases where drifted.
4. Thursday runbook end-to-end: research, notes, sims on fresh GW2 odds, transfer
   optimizer (Watkins), gate, build, deploy, posts. Bench order in the owner's real
   FPL app aligned to the published state.

## Success criteria
- A GW1-style knowledge failure (transferred/blanking/benched published player)
  is impossible without a dated, sourced note consciously overriding a red flag.
- Weekly public scoreboard: both squads' totals vs the average manager + duel state,
  cumulative; accuracy league vs ep_next live by ~GW4.
- The Thursday runbook runs end-to-end in one session with zero owner input.
