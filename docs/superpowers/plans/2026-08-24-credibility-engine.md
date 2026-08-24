# Credibility Engine Implementation Plan (Phase 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a GW1-class knowledge failure mechanically impossible to publish (feed
diff → player dossiers → a publish gate that refuses reds without sourced notes), and
land the community-validated engine fixes (joint captaincy objective, bench cap,
minutes floor, own strength table, transfer optimizer, accuracy grading, runbooks).

**Architecture:** Deterministic code layer only — the Claude/web-research layer lives
in runbooks, not code. New pure modules mirror the repo's network/pure split
(`core/fpl_api.py` conventions). The gate lives in `evmax/fpl_build.py` preflight.
Optimizer changes stay inside the greedy+repair heuristic.

**Tech Stack:** Python 3.9 stdlib only, `unittest`, offline synthetic-payload tests.
Suite is 832 green at start; green at every commit. `from __future__ import
annotations` in every new module. Never touch `core/engine_events.py`; WC pages stay
byte-identical (existing suites are the gate). Frozen GW1 artifacts and
`evmax/assets/projections/` untouched.

**Spec:** `docs/superpowers/specs/2026-08-24-credibility-engine-design.md` — read it
first; decisions D1–D8 govern any judgment call.

---

### Task 1: `core/fpl_diff.py` — feed snapshot + diff

**Files:**
- Create: `core/fpl_diff.py`
- Test: `tests/test_fpl_diff.py`

Semantics: `snapshot(bootstrap) -> dict` produces a compact projection keyed by
element id: `{web_name, team_short, status, price, selected_pct, tin, tout}` plus
`{"taken_at": iso}`. `diff(old, new) -> dict` returns lists: `renamed`
(id present in both, web_name changed — carries old/new), `moved` (team changed),
`status_changed` (carries old/new status + news is NOT in the snapshot; the report
prints "check feed"), `arrived` (id only in new), `departed` (id only in old),
`price_changed`, `outflow_spikes` (tout z-score over all players with tout>0,
threshold 3.0 — must catch a Watkins-shaped 50k-out among ~500 players). Persist via
`fpl_api.write_cache("feed_snapshot", snap)`; `load_previous()` reads it. CLI:
`python3 -m core.fpl_diff` fetches bootstrap via `fpl_api.fetch_bootstrap()`, diffs
against the stored snapshot, prints a human report grouped by category (loud "FIRST
RUN — snapshot stored, no diff" when none exists), then stores the new snapshot.

- [ ] Step 1: Write failing tests: rename detection (Sangaré→I.Sangaré shape), club
  move (Konsa AVL→ARS shape), arrival (M.Sangaré), outflow spike (one player with
  tout=50_000 among 400 players tout≈2_000, z>3), first-run behavior
  (`diff(None, new)` returns `{"first_run": True}`), snapshot round-trips through a
  temp `fpl_api.DATA_DIR` (patch it like tests/test_fpl_odds.py does).
- [ ] Step 2: Run `python3 -m unittest tests.test_fpl_diff -v` — expect failures
  (module missing).
- [ ] Step 3: Implement; pure functions take dicts, no network outside `main()`.
- [ ] Step 4: Suite green (`python3 -m unittest tests.test_fpl_diff` then full suite).
- [ ] Step 5: Commit `feat(fpl): feed diff — the churn detector (renames, moves, outflow spikes)`.

### Task 2: Player dossiers + the publish gate

**Files:**
- Create: `games/fpl/dossier.py`
- Modify: `evmax/fpl_build.py` (preflight)
- Test: `tests/test_fpl_dossier.py`, extend `tests/test_fpl_site.py`

`games/fpl/dossier.py`: pure. `build_dossier(entry, prior, bootstrap_player,
research_note) -> dict` with fields `{name, status, start_prob, start_source
('note'|'proxy'|'history'), club_changed, name_drift, outflow_flag, red: bool,
reasons: [str]}`. Red iff any of: `status != 'a'`; `start_prob < 0.75 and
start_source == 'proxy'`; `club_changed`; `outflow_flag`; unresolved name.
`gate(dossiers, notes) -> (ok, failures)`: a red passes ONLY if a note exists for
that player with non-empty `sources` and `updated >=` the snapshot date; otherwise
the failure carries the player name + reasons verbatim.

Wire into `fpl_build` preflight for BOTH squad states: on gate failure the build
aborts (SystemExit) printing every failing dossier — matching the existing preflight
abort style. `--force-publish` is deliberately NOT added (D1: refusal, not warning).

- [ ] Step 1: Failing tests: green player passes; red-status player without note
  aborts listing his name; same player + sourced dated note passes; note with empty
  sources does NOT override; proxy start 0.6 red vs note-sourced 0.6 green; club
  change red. Build-level test (synthetic states à la tests/test_fpl_live_build.py):
  a build whose consensus squad contains a status='i' player exits with the gate
  message.
- [ ] Step 2: Run to verify failure.
- [ ] Step 3: Implement dossier.py, then the preflight wiring.
- [ ] Step 4: Full suite green — the existing e2e builds must still pass, which
  proves the current GW1 states gate green (Watkins is status 'a' with a note-less
  proxy 0.87 ≥ 0.75: green; if any current player gates red, write the missing
  sourced note under research/players/ as part of this task rather than weakening
  the rule).
- [ ] Step 5: Commit `feat(fpl): player dossiers + the publish gate — reds cannot ship without a sourced note`.

### Task 3: Optimizer v2 — joint captaincy, bench cap, minutes floor

**Files:**
- Modify: `evmax/fpl_articles.py` (the squad builder used for the model squad +
  wildcard article; keep `articles.wildcard_squad` (WC) untouched)
- Test: extend `tests/test_fpl_articles.py`

Changes to the FPL squad builder: (a) objective becomes
`sum(xi.x_points) + max(xi.x_points)` (the doubled captain's second helping) — the
formation sweep and repair loops compare on this; (b) hard constraint: XI members
need `start_prob >= 0.75` unless a research note overrides (the builder receives a
`notes` set of names; entries carry `start_prob` — thread it into the rows the
builder consumes); (c) bench total cost ≤ 18.5 while keeping the playing-bench rule.
Expose `objective(xi_rows) -> float` as a pure function so the test pins it.

- [ ] Step 1: Failing tests: objective counts the best player twice (hand-built rows:
  XI of 10×4.0 + 1×8.0 → objective 56.0); a 0.6-start 9.0-xPts player is excluded
  from the XI without a note but included with one; bench cost ≤ 18.5 on a synthetic
  pool that would previously buy a 20.5 bench; a Haaland-priced row (15.5, top xPts)
  now enters when the doubling justifies him on a pool built to make that true — and
  the same pool without doubling excludes him (this pins that the objective actually
  changed behavior).
- [ ] Step 2: Run to verify failure.
- [ ] Step 3: Implement minimally inside the existing greedy structure.
- [ ] Step 4: Full suite green. NOTE: squad-page/duel tests pin projected totals from
  the STATE files, not the optimizer — they must be unaffected. If any FPL article
  test pinned old optimizer output, update that test with a comment citing this plan.
- [ ] Step 5: Commit `feat(fpl): optimizer v2 — captaincy in the objective, 18.5 bench cap, 0.75 minutes floor`.

### Task 4: `core/fpl_strength.py` — our own strength table

**Files:**
- Create: `core/fpl_strength.py`
- Modify: `games/fpl/model.py` (future-GW lambda source), the FDR-prior generation
  path stays as the zero-data fallback
- Test: `tests/test_fpl_strength.py`

Model: multiplicative, same form as `ratings.match_lambdas`. For every PRICED match
in `data/fpl/odds_gw{N}.json` files whose entries carry `source != 'fdr_prior...'`
(i.e., real market lambdas), we observe `lam_home = BASE * HOME * att_h * def_a` and
`lam_away = BASE * att_a * def_h`. Fit per-team `att`, `def` in log space by
iterative averaging (alternate: fix defences, solve attacks as the mean of
`log(lam) - log(BASE·HOME?) - log(def_opp)`, then vice versa; 10 iterations is
plenty at this scale), with recency weights `0.85^(current_gw - gw)` and shrinkage:
`final = (n_eff * fitted + k * prior) / (n_eff + k)` with `k = 2.0`, prior = the
FDR-calibrated table expressed as att/def multipliers (derive once from the GW1-fit
constants: `att_prior = exp(1.056 - 0.242*FDR_avg)/BASE`-style — document the exact
derivation in the module docstring; exactness of the prior matters less than the
shrinkage direction). `table(gw) -> {team: (att, def)}`;
`future_lambdas(home, away) -> (lh, la)`. `games/fpl/model.py`: when building a
FUTURE gameweek's odds cache is absent or fdr-sourced AND ≥2 gameweeks of real
market data exist, use `fpl_strength.future_lambdas` and stamp
`source: "strength_table_v1"`; else the existing FDR fallback. Current-GW real odds
always win.

- [ ] Step 1: Failing tests: synthetic two-GW odds set where one team's matches carry
  λ≈2.5 both weeks → its att multiplier > 1.3; shrinkage pulls a one-observation
  team toward prior (fit with k=2 sits between prior and observation); recency
  weight prefers the later GW when observations conflict; `future_lambdas` is
  symmetric-consistent (recomputing the training match reproduces its λ within 15%);
  with <2 real GWs the model layer keeps the FDR source (integration test on the
  cache-writing path with synthetic caches in a temp DATA_DIR).
- [ ] Step 2: Run to verify failure.
- [ ] Step 3: Implement.
- [ ] Step 4: Full suite green — GW1 build byte-stability: with only GW1 real odds
  (<2 GWs), nothing changes; assert the existing e2e build output ignores the new
  module (the freeze survives).
- [ ] Step 5: Commit `feat(fpl): own strength table from accumulated market odds, FDR demoted to zero-data fallback`.

### Task 5: Transfer optimizer v1

**Files:**
- Create: `games/fpl/transfers.py`
- Modify: `manage.py` (a `fpl_transfers` entry or flag), nothing in evmax
- Test: `tests/test_fpl_transfers.py`

`recommend(state, rows_by_gw, free_transfers, bank) -> list[dict]`: every legal
single swap (same position, budget-feasible using selling price = bank + price of
outgoing, club cap respected, minutes floor respected) scored by
`delta = sum_gw disc[gw] * (xpts_in[gw] - xpts_out[gw])` over the horizon rows
provided; players whose dossier is red (pass a `flagged: set[str]`) are forced to
the top as sale candidates regardless of delta sign. Output top-5 dicts
`{out, in, delta, hit_adjusted_delta, reasons}` where a second transfer this week
would subtract 4.0 (`hit_adjusted_delta` only differs when `free_transfers == 0`).
No I/O in the module; `manage.py fpl --transfers` (or equivalent) loads states +
the horizon matrix and prints the table for both squads.

- [ ] Step 1: Failing tests: budget feasibility (can't buy above bank+sale), club
  cap enforced post-swap, flagged player surfaces first even with negative delta
  swaps only, delta math over a hand-built 3-GW horizon, hit adjustment at 0 FTs.
- [ ] Step 2: Run to verify failure.
- [ ] Step 3: Implement.
- [ ] Step 4: Full suite green.
- [ ] Step 5: Commit `feat(fpl): transfer optimizer v1 — single swaps on horizon delta, flagged players forced to the block`.

### Task 6: Accuracy grading v1

**Files:**
- Create: `games/fpl/grading.py`, `scripts/grade_gw.py`
- Modify: `evmax/fpl_build.py` (freeze `ep_next` into snapshots from now on: add the
  bootstrap's `ep_next` per player to the row projection written into
  `evmax/assets/projections/fpl-gw{N}/` for FUTURE gameweeks only — GW1's committed
  snapshots are frozen history, do not regenerate them)
- Test: `tests/test_fpl_grading.py`

`grading.grade(snapshot_rows, live_stats) -> dict`: per-player absolute error for
our `x_points` and (when present) `ep_next` vs realized `total_points`, aggregated
to `{n, mae_ours, mae_ep_next, beat_ep_next: bool}` plus the squad-level
`{projected, realized}` for both squad snapshots. `scripts/grade_gw.py --gw N`
loads the committed snapshot + `core.fpl_live` data and writes
`evmax/assets/accuracy/gw{N}.json` (committed, like projections) and prints the
Monday-report table. Site surface: NOT this phase (runbook prints it; a page comes
with the next site phase).

- [ ] Step 1: Failing tests: MAE math on hand-built rows; ep_next missing → mae_ep_next
  None and beat_ep_next None; squad projected-vs-realized pulled from the squad
  snapshot's meta; writer creates the accuracy JSON in a temp dir.
- [ ] Step 2: Run to verify failure.
- [ ] Step 3: Implement.
- [ ] Step 4: Full suite green.
- [ ] Step 5: Commit `feat(fpl): accuracy grading v1 — our projections vs ep_next vs reality, banked per GW`.

### Task 7: Runbooks, learnings log, docs

**Files:**
- Create: `docs/runbooks/thursday-pre-deadline.md`, `docs/runbooks/monday-post-gw.md`,
  `docs/research/season-learnings.md`
- Modify: `README.md`, `CHANGELOG.md`

Thursday runbook (numbered, exact commands): bootstrap refresh one-liner →
`python3 -m core.fpl_diff` → "research every red + every published player" (the
Claude step: what to search, where notes go, note format with sources) →
`manage.py fpl --round N --refresh` → optimizer/transfer commands → gate expectation
("the build REFUSES reds; that is the system working") → `--live` build + deploy →
post drafts checklist (shortlist comment, owner posts) → the five-line owner summary
template. Monday runbook: `grade_gw` → duel/scorecard numbers → transfer preview →
season-learnings entry format. Both end with a "schedule this later" section (the
`/schedule` slash-command route and a plain `launchd`/cron line, marked PARKED by
owner decision D3). Seed season-learnings.md with GW1's six entries (keeper pair,
wrong Sangaré, Watkins hold, Isak proxy, Maguire proxy, bench-order mismatch) in
mistake→root cause→structural fix→status form, each fix cross-referencing the task
in this plan that closes it. CHANGELOG entry; README points at the runbooks; suite
count updated.

- [ ] Step 1: Write all files.
- [ ] Step 2: Full suite green (docs only — but run it anyway before the commit).
- [ ] Step 3: Commit `docs: the credibility-engine runbooks + the season learnings log`.

---

## Self-review notes (done at write time)
- Spec D1–D8 → tasks: D1/D2→T2, D6→T3+T4, transfer/Watkins→T5, C-metric→T6,
  D3/D4→T7, D8 machinery already merged (phase 4c), D5 lives in runbook outputs
  until the next site phase, D7 is an owner action (no task).
- GW1 freeze protected explicitly in T4 step 4 and T6 (no snapshot regeneration).
- Type consistency: dossier dict feeds both the gate (T2) and transfers' `flagged`
  set (T5) by name; builder consumes `start_prob` + `notes` names (T3).

### Task 8: IndexNow — tell the engines on every deploy

**Files:**
- Create: `scripts/indexnow_ping.py`
- Modify: `evmax/build.py` (`write_site_chrome` also writes the IndexNow key file)
- Test: `tests/test_indexnow.py`

IndexNow (indexnow.org) is keyless-account instant indexing for Bing/Yandex/Seznam
(Bing powers Copilot + Perplexity grounding): host `{key}.txt` at the site root
containing the key, then POST to `https://api.indexnow.org/indexnow` with
`{host, key, urlList}`. Google does NOT consume IndexNow — Google needs the
one-time GSC setup (owner action, via his browser; documented in the Thursday
runbook's "first-time setup" appendix).

Semantics: a fixed key committed as a constant (generate one 32-hex string ONCE and
hard-code it — it is not a secret, it merely proves site ownership by being served);
`write_site_chrome` writes `{key}.txt`; `scripts/indexnow_ping.py --out dist`
parses `dist/sitemap.xml`, POSTs the full URL list (≤10k allowed), prints the HTTP
status, exits 0 on 200/202 and nonzero otherwise — and NEVER raises on network
failure (a failed ping must not break a deploy; print and exit 1). Runbooks gain
the ping right after the deploy step.

- [ ] Step 1: Failing tests: key file written by site chrome (temp dir); ping
  payload built from a synthetic sitemap (urlList matches loc entries, host/key
  correct) with the HTTP call injected; network-failure path exits 1 without
  traceback.
- [ ] Step 2: Run to verify failure.
- [ ] Step 3: Implement (stdlib urllib, injectable opener).
- [ ] Step 4: Full suite green; WC byte-identity unaffected except the new root
  key file (existing chrome test extended, not weakened).
- [ ] Step 5: Commit `feat(growth): IndexNow key + post-deploy ping — Bing-facing surface stops waiting to be found`.
