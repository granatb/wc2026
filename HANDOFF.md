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

## Immediate next actions

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
