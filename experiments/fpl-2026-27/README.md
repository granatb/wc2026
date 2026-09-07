# Prospective season experiment

Four virtual approaches are registered in `protocol.json`: market, statistical,
hybrid and consensus. All four providers now run through `scripts/fpl_providers.py`.
No weeks have been enrolled; draft forecasts are not frozen performance records.
The two existing published teams retain their separate history.

All four start with the same affordable 15-player seed. The shared policy chooses
a legal XI, captain and vice; subsequent weeks consider at most one transfer with
positive expected gain after hits. Purchases, selling profits, bank and free
transfers carry forward. Chips are disabled. This is a controlled one-week policy,
not a full season optimizer. Human deviations require dated reasons and sources.

## Inputs and operation

Run commands from the repository root. Refresh bootstrap and fixtures using the
existing FPL cache writer so their matching `.meta.json` receipts exist. Each
provider supplies `market.json`, `statistical.json`, `hybrid.json` or
`consensus.json` in a board directory. Each file contains:

- `model_version`, `generated_at`, `trained_through` (UTC timestamps). The external
  consensus may explicitly declare `trained_through: null, training_disclosed: false`;
  its training date must not be invented from our internal model's cutoff.
- `source_artifact_id`: SHA-256 identifying retained source evidence.
- `bootstrap_sha256` and `fixtures_sha256`, calculated with
  `core.forecast_archive.digest`; fixture context is filtered to the target GW.
- `predictions`: one `{ "player_id": 123, "x_points": 4.2 }` row for **every** player in
  the frozen bootstrap, with finite numbers and unique IDs.
- Optional `interventions`, each containing `reason`, `source`, `recorded_at`.

All boards must use the same context and generate within the registered
30-minute window before capture. Training cutoffs must precede generation.
Do not relabel old forecasts with a fresh timestamp. Source digests identify
evidence; operators must retain that evidence and verify provider provenance.
Fresh observations and provider timestamps are separately limited to 24 hours.

## Provider workflow

The normal weekly entry point is now `scripts/fpl_season.py`:

```sh
python3 scripts/fpl_season.py status --gw 4
python3 scripts/fpl_season.py rehearse --gw 4
python3 scripts/fpl_season.py run --gw 4
python3 scripts/fpl_season.py grade --gw 4
```

`status` is read-only and labels its cached input. `rehearse` refreshes inputs and
builds all four forecasts and squads without enrolling them; `--context PATH`
allows an offline rehearsal from retained, still-fresh inputs. It returns the exact
run manifest path. `run` checks a fresh official deadline, then refreshes, builds,
backs up and freezes together **only within the final 24 hours**. Outside that
window it returns `rehearsal_only`; missed deadlines and history gaps fail. It
never schedules itself or submits changes to an official FPL account.

To freeze a reviewed run still inside its 30-minute forecast window:

```sh
python3 scripts/fpl_season.py freeze --run-file /path/from/rehearsal/run.json
python3 scripts/fpl_season.py verify-backup --backup /path/to/backup.json
```

The CLI holds a POSIX file lock around mutations. Repeating the same freeze returns
the original receipt, including after the deadline; a different run cannot replace
it. Before enrollment, a self-contained forecast/source/run bundle is written under
`data/experiments/season-2026-27/backups/`; the source is also retained beside the
records in an ignored `sources/` directory. These are local recovery copies, not
off-device backups. Copy backups to durable private storage. `verify-backup` checks
their internal identities; recovery must preserve the original forecast hash and
be checked against an independently published receipt, never recapture past data.

`grade` fetches official outcomes and refuses unfinished, duplicate or missing
results. Raw outcomes are retained under the ledger's `results/` directory before
the derived grade is written. Every report recalculates scores against that evidence.
Repeated fetches of identical outcomes do not create revisions; changed official
outcomes preserve the previous grade and its original result receipt.

The public API includes forecast commitment receipts, without raw external provider
payloads. Publish those receipts before the deadline; a local timestamp or hash
alone is not independent proof. Deployment validation checks that the experiment
summary matches the retained evidence.

The lower-level provider commands remain available for diagnosis:

```sh
python3 scripts/fpl_providers.py train
python3 scripts/fpl_providers.py refresh --gw 4 --context data/experiments/gw4-context.json
python3 scripts/fpl_providers.py build --context data/experiments/gw4-context.json --out data/experiments/gw4 --sims 5000
python3 scripts/fpl_experiment.py prepare --gw 4 --boards data/experiments/gw4 --out data/experiments/gw4/submissions.json
```

### Learning from the season

The primary score remains RMSE over the complete common player population. Two
secondary populations are selected entirely from the frozen forecast: players
averaging at least 60 minutes per completed prior gameweek, and the union of all
four squads. The first is a gameweek average (doubles can influence it), not a
per-match minutes measure. Empty cohorts report unavailable scores rather than
zero error. Every arm uses exactly the same cohort IDs.

Paired comparisons subtract one arm's weekly MSE from another's and weight each
eligible gameweek equally. The public page shows all-player comparisons; the API
also includes both secondary cohorts, sample sizes, MAE and bias. Captain bonus
points and transfer hits remain separate season totals in the API.

Exploratory intervals resample consecutive three-gameweek blocks with a fixed
seed and 2,000 draws. Intervals are suppressed until 12 eligible consecutive weeks
exist with unchanged model versions. These are prespecified operational choices,
not a power calculation. Dependence beyond three weeks, nonstationarity and
multiple comparisons can still make intervals misleading. They do not establish
an edge or automatically select a model for next season. Mixed-version season
averages describe the deployed approach, not one unchanged model.
Model fingerprints distinguish code and fitted-parameter changes from normal
weekly inputs, even if a readable version label was not changed. Undisclosed
external model revisions suppress intervals for those pairs. Old draft boards
without fingerprints must be regenerated before source-verified enrollment.

The block-resampling method follows the general idea of resampling dependent
observations in blocks: [Künsch (1989)](https://doi.org/10.1214/aos/1176347265).
Our particular block length, sample threshold and application to football are
not validated by that paper. No historical or synthetic example is added to the
prospective public results.

Training uses the already downloaded 2023/24 CSV; 2024/25 is evaluation only. Run
training once for this version, not weekly. Refresh fetches public official data,
completed gameweek outcomes, ESPN match odds and FFIQ forecasts. It requires no paid
API key. Build performs no network fetches and writes all boards plus a hashed
source bundle before the shared policy prepares squads.

The market arm uses the corrected engine and official statistical priors with no
editorial overrides. Every target fixture requires actual market prices; fallback
team ratings are refused. The statistical arm uses the identical training/inference
feature transform on prior gameweeks only, plus official availability gates. Its
new version supports early-season history; it is distinct from the original
six-prior-GW research experiment. Positional training means handle true cold starts;
blanks are zero and doubles scale approximately by future match count.

The hybrid is a **prespecified 50/50 average**, not a fitted or optimized blend.
We lack matching historical market predictions to tune it honestly. The reference
uses the mean of official FPL `ep_next` and FFIQ where covered, official alone
otherwise. Coverage and missing IDs are retained. FFIQ IDs are used with club checks;
name-and-club joins must be unambiguous when IDs are absent. Attribution:
[Fantasy Football IQ](https://fantasyfootballiq.app). External training/data lineage
is unknown. Internal market/statistical models do not consume FC27 ratings.

Generated boards carry `provider_version`. Prepare and freeze require the referenced
source file in `sources/` beside the boards/submissions (or `--sources PATH`). They
verify the source hash and bind predictions, context, version and clock to it.
Retain this directory for the season; `data/` is intentionally ignored by Git.
Raw external projections are not added to the public website. Back up private source
bundles separately; publish only authorized evidence/receipts and derived results.

```sh
python3 scripts/fpl_experiment.py prepare --gw 4 --boards /path/to/boards --out /tmp/submissions.json
python3 scripts/fpl_experiment.py freeze --gw 4 --submissions /tmp/submissions.json
python3 scripts/fpl_experiment.py grade --gw 4 --results /path/to/final-results.json
python3 scripts/fpl_experiment.py report
```

`prepare` creates a reviewable draft. `freeze` must finish before the deadline;
it writes an exclusive, hashed weekly record. Publish its digest through an
independent pre-deadline receipt: a local hash alone does not prove capture time.
Result input contains `gameweek`, `fetched_at`, the matching final `fixtures`, and
official `live.elements` with minutes and points for every forecast player.
Corrections preserve previous grade receipts. Missing outcomes or changed fixture
membership require investigation rather than partial grading.

The site publishes the derived report at `/fpl/experiments/` and
`/api/fpl/experiments.json`. Forecast errors use identical populations and equal
gameweek weighting; squad results include official substitutions and transfer
hits. Model versions and human interventions remain visible. No automatic winner
is selected from a few gameweeks. Rules cannot change within a frozen history;
a changed protocol requires a separately identified experiment.

## Activation and remaining limitations

The 7 September live-data run produced four complete 654-player boards and a valid
common-seed squad draft. These are working drafts, not enrolled GW4 forecasts.
Refresh and regenerate near the 12 September 12:30 UTC deadline, then freeze and
publish an independent receipt before that deadline. Do not freeze an old draft
after its 30-minute window. No scheduler or official FPL account is operated here.
The weekly workflow's freeze window opens on 11 September at 12:30 UTC.

Heldout early-ridge RMSE is 2.093 versus 2.231 for last-four mean on 26,427 rows;
MAE is 1.100 versus 1.104. This population differs from the original research model,
excludes zero-history cases and does not test the new availability gate. No market
comparison, cold-start validation or prospective improvement is established.
Opponent-aware statistics, trained minutes, optimized blends and full multiweek
transfer/chip planning remain future work. Do not enroll placeholders or backfill
past weeks. Update a model under an explicit new version rather than retuning silently.
