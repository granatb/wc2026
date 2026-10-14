# Resume here

This is the handoff for the ongoing evmax/FPL improvement work. Read this file,
then [the prioritized plan](docs/reviews/2026-09-07-fix-plan.md) and
[the season operations guide](experiments/fpl-2026-27/README.md).
The repository also contains older World Cup tooling; the current work is FPL.

## Verified checkpoint — 7 September 2026

- Canonical checkout: `/Users/bartlomiej.granat/personal/projects/wc2026`.
  Remote: `https://github.com/granatb/wc2026.git`, branch `main`.
- Last verified code batch: `7210df5`, pushed and deployed to `https://evmax.ai`.
  Public page/API were checked against repository output.
- 1,360 Python tests passed. All 654 market forecast values matched the baseline
  before joint retention was added; the four-provider rehearsal also passed.
- No experimental GW is frozen or graded. No scheduler or official FPL account
  is operated. Rehearsals and simulated expectations are not prospective results.
- Four-arm controlled policy stays `single_swap_xi_mean_v1`. Research candidates
  and the scenario optimizer have not replaced it.

This is a dated checkpoint, not a claim about future repository or season state.
Inspect current Git history, records, official deadlines and input freshness
before acting. Do not assume GW4 is still the next gameweek when returning later.

## Owner decisions after the checkpoint

- **2026-09-08 — player cards are always visible.** A locked gameweek's build
  renders *preview cards* for the next open gameweek (fresh simulation on
  today's inputs, labelled with simulation date and deadline, JSON under
  `/api/fpl/preview/`, replaced and deleted by Thursday's real build). The
  landing carries no archive banner. The locked gameweek's own forecast
  surfaces stay frozen/unavailable as before. See `evmax/fpl_build.py`
  (`_preview_gameweek`, `_preview_payloads`), `tests/test_preview_cards.py`
  and `docs/runbooks/monday-post-gw.md`.

- **2026-10-07 — the private `data/` directory is gone.** It was not in the
  2026-10-02 Mac migration backup. Caches are refetched; the experiment
  contexts, research CSV snapshots and cached article prose are not
  recoverable. `dist/` is a mirror of the live site taken on 2026-10-07; never
  deploy from an empty `dist/`, the build does not regenerate past gameweeks.
- **2026-10-07 — unenrolled experiment weeks become dated gap records**
  (`fpl_season.py gap`). GW5 is recorded as a gap; GW4 is graded. The chain
  continues from GW6.

## Immediate next actions

### Website release prepared; environment blocks shipping — 14 October 2026

The user now explicitly authorizes publication, commit, push and deployment;
this supersedes the earlier local-only scope below. Actual transfers remain
the user's Friday action. [Release status and exact commands](docs/reviews/2026-10-14-provisional-release-status.md).

The cumulative production export is built and validated: final GW6 41/71 versus
field average 58; provisional GW7 667-player projections, article/expert updates,
joint transfer comparisons and captain reasoning. Receipt `553cfb64…` accepts
held website rosters only; account submission is unverified. New GW7 forecast
artifact is `91272d7db80451db2ddac544b124f2e3aba423f43b66a0e105877e15edd41b10`.
1,430 tests pass (five existing skips), GW1–7 content/evidence validation passes,
and all 372 protected pre-existing files retain their hashes.

Deployment stopped at `scripts/deploy.sh: line 16: npx: command not found`.
Bundled Node also cannot read the system OpenSSL configuration (`Operation not
permitted`). The previous Git write denial was respected; no permissions or
security settings changed. No commit, push, deployment or live verification
completed. Branch remains `chore/gw6-thursday`, HEAD `0ddb44b`, ahead five.
Run `bash scripts/ship_gw7_provisional.sh` from an ordinary authorized Mac
terminal to finish the exact prepared release, then record its real identities.

### Provisional GW7 research — 14 October 2026

- [Conditional recommendation and complete portfolio comparisons](docs/reviews/2026-10-14-gw7-provisional-recommendation.md)
  use the user-confirmed **three free transfers**. Actual account roster, bank,
  displayed sale prices, chips and any already-made GW7 moves remain unverified.
  Website Model/Consensus states are separate and unchanged; Consensus bank is missing.
- Conditional Model shortlist: Bruno → Saka first; Evanilson → Gonzalo if injury
  cover is adequate, or Szoboszlai → Tavernier if recovery remains unclear;
  Shaw → De Cuyper is an optional third move after workload/fitness checks.
  Holding/using 1/2/3 FTs leaves 4/3/2/1 next week; FT option value is unpriced.
- Research evidence is private at `data/reviews/gw7/2026-10-14-provisional/`:
  official capture 14:05 UTC, 436/436 fresh player histories, isolated 10,000-draw
  simulations GW7–11 and full joint portfolio comparisons. GW7 odds are market;
  GW8 is 4 market/6 strength fallback, GW9–11 all strength fallback.
  No model retuning. All 372 protected pre-existing hashes match after simulation;
  61 focused tests passed on Python 3.12 with networking blocked.
- `research/experts/gw7.json` is explicitly provisional, derived-only research.
  Final Scout selections/captain metrics and Friday press conferences remain open.
  Wednesday/Thursday European workload matters; GW7 is not the immediate first
  round after the international break. Deadline **17 October, 10:00 UTC**.
- No production build, accepted publication decision, account action, push or
  deployment. The rehearsal excludes stale editorial/World Cup round-seven
  research; that namespace collision remains an unmodified follow-up risk.
- **Reconnection verification completed:** independent recomputation passes for
  65 saved portfolio records, all 15 sale values, 88 news sensitivities, 44 recovery
  records and 18 price sensitivities, including the £0.3m-short Haaland/Saka route.
  Joint XI/captain utility, budgets, position/club limits, bench and FT accounting
  agree. All 372 protected hashes still match; six-source expert JSON validates.
  See private `verification-resumed.json` and `expert-validation-resumed.log`.
  Simulations and the full search were not rerun. Saka captain is conditional on
  the proposed roster lacking Haaland; the base board still ranks Haaland 8.63
  above Saka 7.02, and a legal Haaland acquisition was evaluated.
- Git is `chore/gw6-thursday` at `0ddb44b`, ahead five of the locally recorded
  upstream (no fetch). GW7 report/expert JSON are untracked; these HANDOFF/plan
  edits are unstaged; private evidence is ignored. No GW7 artifact is committed.
  Verification needed no permission change or Git write. Actual account inputs
  and final pre-deadline news remain the outstanding decision gates.

### Final GW6 reconciliation — 14 October 2026

Latest local checkpoint supersedes the provisional finality blocker below.
Official capture at **11:35:28–11:35:37 UTC** returned HTTP 200 / `Age: 0`:
all ten GW6 fixtures final, event `finished=true`, `data_checked=true`, final
field average **58**. The existing guard passed without changing any flags.

- `evmax/assets/accuracy/gw6.json` is now banked through the existing grading
  command using retained official inputs. Frozen artifact remains
  `a8a8df5f59f3f68008f2c761d90a01536efd257dd02311182ccb720efddedebf`.
  Results payload digest:
  `2a87accc591ed2b1071e81ab9beda6c12602bd23a4e6f44f871efdc08be2f4bc`.
- Website Model **41**, Consensus **71**, including autosubs, versus field
  average **58**. Published-XI-only lines are **39/63**; these exclude autosubs.
  Actual user-account results, transfers, hits and chips remain unverified.
- Full frozen board: 667 players, MAE **1.103** versus archived official
  `ep_next` **1.176**. Single-week results do not establish model superiority.
  No missing four-arm or external GW6 benchmark was manufactured.
- Raw official snapshots, headers, receipts, replay and preservation evidence
  are private at `data/reviews/gw6/2026-10-14-final/`. Prior evidence and all
  forecast/live caches remain unchanged. All **353** protected pre-existing
  files retain their hashes. This local evidence is not an off-device backup.
- **59 focused tests pass on Python 3.12**, network blocked. System Python
  3.9.6 fails the retained GW4 exact-float replay on last-digit reduction
  differences; no historical receipt or model code was changed to accommodate it.
  The new GW6 banked player metrics also match Python 3.12 replay exactly.
- [Final review and GW7 checklist](docs/reviews/2026-10-12-gw6-provisional-review.md)
  are current. Verified next deadline: **17 October 2026, 10:00 UTC**.
  Confirm actual portfolio and finances, refresh GW7 news/history/horizon,
  then review and accept the exact dry-build publication proposal. No GW7
  acceptance, squad decision, account action or prospective comparator freeze
  has been performed here.

Current delivery is local evidence, documentation and commit only. No push,
deployment or public build is authorized. Publication remains a separate decision.
Do not use the historical operational permissions below to publish this batch.

### Local code checkpoint, 9 October 2026, before publication authorization

- Branch `chore/gw6-thursday`, starting from `6346666`, with a clean checkout
  before this batch. `chore/gw5-catchup` points to `9215110`; `main` points to
  `46fa54a`. No remote refresh was performed.
- Player research can bind to an FPL `player_id`. The Palmer note binds to 154,
  which the cached bootstrap identifies as Cole Palmer. The simulation,
  dossier and gate use that identity. Alex Palmer (301) receives no override.
  Existing notes without an ID retain exact-name lookup.
- Transfer recommendations use market price and `bought_at` to calculate sale
  proceeds in integer tenths. The experiment ledger uses the same half-profit
  calculation. Cached squad probes give Tarkowski 6.1 from market 6.2 / paid
  6.0, and Raya 6.0 from market 6.1 / paid 6.0.
- Verification: 214 focused tests passed. Full discovery ran 1,407 tests with
  socket connections and DNS blocked: OK, five historical-cache tests skipped.
  The normal runner also emits existing unclosed-file ResourceWarnings.
  Synthetic simulations and cached read-only probes are development evidence.
- Instruction for that local batch: final squad decisions await the 9 October afternoon
  announcements. Branch evidence in `research/experts/gw6.json` lists the Friday
  Scout selections as pending; `research/players/fpl-palmer.md` names Friday's
  press conference as a condition for revision. Git does not record the exact
  afternoon instruction.
- This batch is local only. Squad files, accounts, frozen forecasts and published
  output are untouched. No push, deployment, PR or issue is authorized for this
  batch. Refresh open-week inputs and regenerate the working horizon after the
  announcements before making final decisions. Existing saved horizons were not
  regenerated by this code fix.

### GW6 published checkpoint, 9 October 2026

The subsequent user request authorized a final FPL pass and website publication.
It includes local commits, a normal push and the established Cloudflare route.
Fantasy-account actions and final owner squad selections remain outside this task.
Both squad state files retain the exact bytes from `dd87a3e`.

- Refreshed official bootstrap/fixtures and GW6–10 odds at 14:08 UTC. There are
  667 players. GW6 locks at **10 October 2026, 10:00 UTC**. Form and DefCon
  histories are current through GW5. GW6–7 use market prices. GW8–10 use
  `strength_table_v1` estimates because market prices are unavailable.
- Chelsea's 9 October report confirms Palmer and João Pedro available. Both
  use a provisional 0.75 start assumption. Liverpool rules Isak and Gakpo out
  for GW6. City confirms Haaland fit. These reports promise no starting XI.
- ID-bound research reaches card flags/provenance and optimizer vouching. The
  published start probability is the same effective probability used in the
  simulation. Forecast model version is `2026-10-09.1`. Scoring and the
  controlled experiment policy are unchanged.
- Rebuilt the GW6–10 working horizon at 50,000 simulations per week. The
  existing single-swap policy offers Sánchez → Leno (+0.59) as a reserve-keeper
  repair and Palmer → Saka (+13.03) as its strongest model-squad value option.
  Those are independent discounted legal-XI-plus-captain deltas, with no
  autosub/vice option value. Their gains cannot be added together.
- Saka leads GW6 at 7.96 xPts. Among the registered model squad, Fernandes has
  7.16 versus Palmer's 5.22. Three private 10,000-simulation minutes/start
  sensitivity scenarios retain Saka first. Palmer spans 3.27–6.32 and João
  Pedro 2.52–4.92. These are uncalibrated model assumptions and synthetic
  sensitivity results, with no demonstrated prospective superiority.
- Published expert content includes the current PL Scout Selection and a
  verified subset of FFS Scout Squad nominations. It exposes pending sources
  and owner-review options. Final FFS Scout Picks, FFIQ's squad and All About
  FPL selections remain unverified. Dated September source rows retain their
  dates. Consensus swap analysis assumes 0.0 bank and does not reset that team.
- Dry and production builds passed both squad dossier gates. Production holds
  667 player pages and nine standard articles, plus the expert page. All 119
  pre-existing evidence files retain their SHA256 hashes. No old forecast or
  evaluation baseline was overwritten. Two new GW6 captures retain both build
  vintages. The latest artifact is
  `a8a8df5f59f3f68008f2c761d90a01536efd257dd02311182ccb720efddedebf`, captured
  at 14:27:19 UTC, before the official deadline.
- Full offline discovery: 1,409 tests, OK, five historical-cache skips. After
  the forecast-version metadata change, 257 focused tests passed. The final
  cumulative site evidence validator passed.
- Limits: 134 players use price-based cold-start priors. Future weeks carry
  current feed availability, with no injury-recovery forecast. No new
  four-arm enrollment or external-projection benchmark was frozen. Raw
  third-party projections must stay private. Final squad/account action and
  those research workflows remain separate from website publication.
- Private working evidence and the input/site backups are at
  `/tmp/wc2026-gw6-final-20261009-1404/`. Temporary local files are not a durable
  off-device backup.

- Code/publication commit `63b03beae663eaa60b21dd35939fc64670e272ae` is pushed
  to `main` and `chore/gw6-thursday`. GitHub CI completed successfully:
  https://github.com/granatb/wc2026/actions/runs/37944652543.
- Cloudflare production deployment `e11d2ccd-e221-449a-b59a-9a888acb759c`
  identifies source `63b03be` on `main`:
  https://e11d2ccd.evmax.pages.dev. The established deploy script passed the
  site validator and IndexNow returned HTTP 200 for 746 URLs.
- At 2026-10-09T14:31:40.873400+00:00, all 15 checked production
  responses returned HTTP 200 and matched `dist/` byte for byte: landing,
  latest feed, GW6 expert page/API, captain/squad APIs, full dataset, the five
  Palmer/João Pedro/Isak/Gakpo cards, experiment page/API and GW1 captains.
  The experiment API also equals `evmax.experiments.report()`. This is HTTP
  publication verification. No browser surface was available for visual review.
- A subsequent documentation-only commit records these completed checks.
  It changes no published bytes and needs no rebuild or redeployment.

### Locked-GW6 copy correction, 10 October 2026

The user authorized publication of the QA corrections after GW6's deadline.
This is a dated presentation correction. The eligible forecast remains artifact
`a8a8df5f59f3f68008f2c761d90a01536efd257dd02311182ccb720efddedebf`, captured
9 October at 14:27:19 UTC under model `2026-10-09.1`.

- Squad prose names the registered captain Palmer (10.44 captain EV) and vice
  Szoboszlai (9.36), and identifies Fernandes (14.31) as the highest projection
  in that registered XI. The generator does not infer rank from an armband.
- Raw FPL availability has an explicit forecast-capture label. Palmer and João
  Pedro cards show the archived 9 October Chelsea source and its availability
  clarification. Playing availability and the provisional 0.75 start assumption
  are separate concepts. The club report promises neither a start nor 90 minutes.
- The adjacent captain article explains automatic vice captaincy independent of
  kickoff order, under https://www.premierleague.com/en/news/4661029. Projection
  ranking and all numeric rows are unchanged.
- `evmax/assets/corrections/fpl-gw6.json` binds the dated correction to that
  artifact. Club sources and source dates must match its archived research.
  HTML and Markdown carry a 10 October copy-correction notice. Original archive
  prose remains intact. The locked player index reads archived injury flags.
- The production rebuild ran with socket/DNS access blocked and both data reload
  and simulation calls forbidden. No new forecast, outcome input, account action
  or squad decision enters this correction. No model-version bump is needed.
- Verification: 1,415 offline tests, OK, five missing-history skips. The focused
  suite passed 310 tests. The site evidence validator passed. All 137 protected
  files retain their hashes, including forecasts, evaluation baselines, experiment
  records and both squad states. Every existing public API byte is preserved
  except the dated clarification field on player 154 and 165 JSON responses.
- Evidence and the prior site backup are at
  `/tmp/wc2026-gw6-qa-20261010/`. Those temporary files are not a durable backup.
  Code commit `a3929502112e872eeefc93cb939f78d588b822b7` is pushed to `main`
  and `chore/gw6-thursday`. Its CI passed:
  https://github.com/granatb/wc2026/actions/runs/38085885606.
- Cloudflare production deployment `47abb0ba-f163-445f-92fc-84072f8a7c03`
  identifies source `a392950` on `main`:
  https://47abb0ba.evmax.pages.dev. IndexNow accepted 746 URLs with HTTP 200.
- At 2026-10-10T21:01:06.970403+00:00, all 22 checked live responses
  returned HTTP 200 and matched the validated export byte for byte. Checks
  include the corrected squad/captain HTML and Markdown, both full player pages,
  the card APIs, frozen player index and dataset, experiment page/API, latest
  feed and a historical captain API. The experiment API equals the retained
  report. These are HTTP checks, with no claim of browser-rendered QA.
- A subsequent documentation-only commit records the verified delivery. It
  changes no website bytes and needs no redeployment.

### Provisional GW6 review, 12 October 2026

Current authorization is local draft/review work. No push, publication or
account action is authorized for this review. Official snapshots at 11:00:34
UTC show Coventry v Newcastle still scheduled for 12 October at 19:00 UTC.
Nine matches are provisionally finished. GW6 `finished` and `data_checked`
remain false. The final-grading gate rejects this snapshot.

The [local retrospective draft](docs/reviews/2026-10-12-gw6-provisional-review.md)
reconciles provisional registered-squad scores: Model 41, Consensus 71.
These are website squad scores, with autosubs, and no verified user-account
reconciliation. The draft separates failed captain rankings, the Szoboszlai
appearance miss, publication inconsistencies and the unconfirmed timing of
his injury warning. It also identifies the consensus ownership-template
method being described incorrectly as an expert mention tally. No code or
methodology is changed in this review.

Timestamped official data, raw-byte hashes, the reproducible analysis and
outputs are retained privately in
`data/reviews/gw6/2026-10-12-provisional/`. The draft includes the GW7 checklist
and verified deadline of 17 October at 10:00 UTC. Before any final report:
refresh after the last game, require final fixtures/data checks, grade the
existing artifact, reconcile official autosubs/captain fallback and the final
field average, then obtain the parent's publication decision. Do not silently
promote today's partial metrics or create a retrospective benchmark freeze.

### All-played GW6 review, 13 October 2026

The Mac tools are functional. Local review scope remains in force: no push,
publication, account access or transfers. The 12 October draft is updated at
its existing path, [GW6 review](docs/reviews/2026-10-12-gw6-provisional-review.md).

Coventry v Newcastle finished 4–1. Official club reports confirm full time.
FPL captures at 08:48 and 08:50 UTC, including cache-busting requests with
`Age: 0`, still report all ten fixtures provisionally finished and zero final.
GW6 `finished` and `data_checked` remain false. This is the precise blocker
for final grading. Do not set those flags manually or bypass the guard.

Registered website totals remain Model 41 and Consensus 71, including autosubs.
FPL's displayed average is 55, still provisional. The user account is unverified.
The all-played draft now covers all 667 forecast rows. Source snapshots,
receipts, hashes and analysis are private at
`data/reviews/gw6/2026-10-13-all-played-provisional/`. The prior snapshot is
retained. No pre-deadline artifact, note, roster or forecast cache is changed.

Next: obtain final FPL flags, recapture actuals, grade the existing artifact,
reconcile the final field average, and get the parent's publication decision.
The GW7 reset checklist remains ready on the verified 17 October 10:00 UTC
deadline. No actual squad decision or model change is made by this review.

1. Inspect `git status --short`, `git log -8 --oneline`, and the records directory.
   Preserve unrelated user changes. Read the plan before selecting another feature.
2. Check current season status. At this checkpoint GW4's freeze window is
   **11 September 12:30 UTC to 12 September 12:30 UTC**. The guarded `run` command
   refreshes, rehearses and freezes only in that window. A missed deadline must
   not be repaired by manufacturing an earlier forecast.
3. Freeze the complete four-arm comparison and publish its receipt before the
   deadline; arrange a private durable backup of its source bundle. Local hashes
   alone do not independently prove publication time.
4. Run the separate fixture shadow workflow if enrolling that comparison too.
   It is not automatically included by `fpl_season.py run`.
5. Once results are final, grade retained forecasts, then evaluate calibration.
   Other remaining work is ordered in the plan: minutes validation, transfer
   option value/multiweek moves, blends, product workflow and optional dependencies.

```sh
python3 scripts/fpl_season.py status --gw 4
# Status can use cached bootstrap. `run` fetches the official current deadline.
python3 scripts/fpl_season.py run --gw 4
python3 scripts/fpl_season.py grade --gw 4
```

These examples refer to GW4 at this checkpoint. Read command help and the
operations guide; do not blindly execute a grade or reuse old context later.

## Research and implementation map

| Area | Start here | Current conclusion |
|---|---|---|
| Four providers | `games/fpl/forecast_providers.py` | Market, statistical, fixed 50/50 hybrid, official/FFIQ reference |
| Weekly operations | `games/fpl/season_ops.py`, `scripts/fpl_season.py` | Guarded freezes, portfolios, retained sources, replayed grades |
| Minutes candidate | `docs/research/2026-09-07-minutes-review.md` | Mixed metrics; not promoted |
| Fixture candidate | `docs/research/2026-09-07-fixtures-review.md` | Small historical improvement; no prospective edge |
| Live fixture shadow | `docs/research/2026-09-07-fixture-shadow.md` | 654-player rehearsal; separate collect/build/freeze/grade commands |
| Scenario optimizer | `docs/research/2026-09-07-lineup-decisions.md` | All 3,300 legal XI/bench combinations, conditional captain/vice value |
| Actual engine draws | `docs/research/2026-09-07-joint-lineup.md` | Retained joint samples and offline replay; audit difference -0.018 points, within simulation noise |
| Public experiment page | `evmax/experiments.py` | Derived results and dated research summaries; no invented standings |

## Evidence and portability

Code, reports and the plan are in Git. **Private evidence is not all in Git.**
On this computer another agent using this checkout can read the existing data.
A fresh clone on another computer also needs a private copy of:

- `data/experiments/` — contexts, histories, draft/frozen backups, joint samples;
- `data/research/` — exact historical CSV snapshots used by the reports;
- `experiments/**/records/sources/` — retained forecast sources when present;
- other required caches under `data/` for offline builds.

Copying the complete `data/` directory is the simplest way to preserve this
checkpoint. Do not commit raw external projections or credentials. A new machine
also needs its own Git/Cloudflare authentication. `dist/` is ignored and may hold
cumulative historical site exports; rebuilding only one GW in an empty `dist/`
may not satisfy the full publication validator. Follow the publication checks.

Without the private files, a fresh clone can continue development and refresh
new inputs, but cannot honestly reproduce every historical research run or recover
missing pre-deadline evidence. Never relabel newly fetched data as an old snapshot.

## Delivery and safety conventions

The user repeatedly requested completed batches be committed, pushed and deployed,
and dislikes uncommitted finished work. Existing authorization for this project
includes that delivery workflow; still respect the current session's permissions.
Deploy when published output changes; documentation-only handoffs need no redeploy.
Do not send messages to other people or purchase services without authorization.

Keep frozen forecasts immutable, version changed models/policies, retain grading
corrections, and distinguish simulation precision from real-world performance.
No FC27 ratings enter the controlled FPL providers. Do not optimize blend weights
without matching forecast vintages or promote a model on reused holdout results.

```sh
python3 -m unittest discover -s tests
python3 -m evmax.build --gw 3 --out dist --no-llm --no-live
python3 scripts/validate_site.py --out dist
git diff --check
# Review changes, commit explicit files, push origin main, then:
scripts/deploy.sh
```

GW3 is the last published-build example at this checkpoint, not a permanent target.
For code changes run relevant regressions and the full suite. For deployment,
verify the production experiment page and API against `evmax.experiments.report()`;
use a cache-busting query if the domain briefly serves the prior deployment.
Update this handoff and the priority plan after substantive future checkpoints.


## Local audit fixes — 13 October 2026

Current scope is local diagnosis and bounded fixes on `chore/gw6-thursday`;
no push, deployment, account access or transfers. Historical permissions above
are not authorization to publish this batch.

- See `docs/reviews/2026-10-13-independent-fpl-audit.md` for ranked findings and contrary evidence;
  `docs/reviews/2026-10-13-fpl-audit-fixes.md` for delivered fixes, tests and the GW7 operator procedure.
- New final grades require matching event `finished` and `data_checked` flags
  plus retained event evidence. The 12:01 UTC GW6 capture still fails finality;
  published roster totals remain provisional, not verified user-account totals.
- Start values are now labeled as input priors before lineup constraints.
  Sampling and point forecasts are unchanged. Comparator copy identifies the
  held ownership template and shared model; historical corrections are dated.
- GW7+ production builds require an explicitly reviewed immutable publication
  decision. A dry build writes `fpl-decision-gw7.json`; acceptance is a separate
  operator CLI step. No real GW7 decision has been accepted. Account submission
  stays unverified and separate. Changed forecasts or squads require review again.
- All 1,430 tests pass (five existing skips), GW1–6 local site validation passes,
  independent review is resolved, and all 335 protected files match their original
  hashes. No forecasting retuning, history overwrite or dependency installation.
