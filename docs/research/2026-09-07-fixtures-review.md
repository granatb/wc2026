# Fixture-aware challenger — 7 September 2026

Decision: retain a research candidate. Fixture features produce a small improvement
in two later seasons, but this is not yet a validated replacement for the live
statistical provider. No odds or FC27 ratings are used.

## Experiment and results

Fit 2023/24 once, fixed ridge penalty 100, no holdout search. Compare two
per-fixture regressions: lagged player features alone and those same features plus
home/away and own/opponent goals scored/conceded rates. Team rates have five
pseudo-matches at 1.4 goals per match; fixture features interact with prior minutes.
The ablation isolates fixture information from the change to per-fixture modeling.
It is not a comparison with the production gameweek ridge.

2024/25 has been reused for earlier research and is therefore a development
comparison. The unchanged specification was then tested on 2025/26. No model
parameters were changed after either result. The later loader initially rejected
duplicates; ten fully identical source rows were removed before evaluation.
Conflicting duplicates remain fatal. The development report was regenerated only
to record the final loader implementation hash; its results did not change.

| Evaluation | Player-GWs | Fixture RMSE | Ablation RMSE | Fixture MAE | Ablation MAE |
|---|---:|---:|---:|---:|---:|
| 2024/25 development | 26,135 | 1.9634 | 1.9710 | 1.0294 | 1.0354 |
| 2025/26 validation | 28,497 | 1.9688 | 1.9768 | 1.0081 | 1.0181 |

The later-season RMSE reduction is about 0.4%. Prior-60-minute players improve
from 3.1668 to 3.1444 RMSE (6,502 rows); doubles from 2.7873 to 2.7693 (408 rows).
All-player bias worsens from -0.0582 to -0.0783, so calibration is not uniformly
better. Row-weighted headline errors and equal-gameweek paired differences have
different denominators and must not be conflated.

Equal-gameweek fixture-minus-ablation MSE is -0.0301 in development with a
three-week moving-block 95% interval [-0.0539, 0.0003], and -0.0320 in validation
with [-0.0556, -0.0053]. These deterministic, unadjusted exploratory intervals
are not a promotion rule or evidence of an edge over markets. GW2–38 are covered;
GW1/cold starts are excluded by the requirement for one prior fixture.

## Time integrity and population limits

- Freeze player and team history for the entire target gameweek. Each double leg
  has separate home/opponent context; its first result never enters the second.
- Require a lower historical GW and kickoff plus three hours before the cutoff.
  The cutoff is a proxy: first target-GW kickoff minus two hours. This guards
  against postponed lower-GW results and unfinished matches, but does not prove
  actual publication or ingestion times.
- Reconstruct teams and final scores once per fixture; reject conflicting or
  one-sided fixture metadata. Exact duplicate player-fixture rows are discarded.
- Never use target results, ownership, price, xP, future form or final league
  standings as model features. Target row club, position and retrospective fixture
  assignment still lack archived pre-deadline evidence.
- Blank inference sums an explicitly empty fixture list to zero. Historical CSVs
  omit player blank rows and registration snapshots: no measured blank cohort is
  claimed and missing player records are not synthesized as zero outcomes.
- Cold starts, injury/availability and transfers with missing histories are not
  validated. Scoring rules changed across these seasons. Gains cannot establish
  squad value, transfer profitability or market-beating performance.

## Next promotion requirements

1. Retain current-season per-fixture player histories and team fixture inputs with
   retrieval receipts. The existing provider stores aggregated gameweek history;
   splitting a historical double by assumption would invalidate this transform.
2. Build a live adapter sharing this transform, with explicit cold-start and
   availability policies; compare it to production on identical eligible inputs.
3. Shadow forecasts before deadlines and retain results before replacing an arm.
   Any production promotion must change model identity and preserve old records.

The four-arm season protocol and live provider are unchanged. The first freeze
window remains 11 September 12:30 UTC to 12 September 12:30 UTC. This batch does not
create a scheduler or freeze forecasts early.

## Reproduce and sources

Historical CSVs: [Vaastav FPL data](https://github.com/vaastav/Fantasy-Premier-League/tree/master/data).
Raw third-party data remains ignored; report source hashes identify the downloaded
files. Repository software licensing does not transfer ownership of FPL data.

```sh
python3 scripts/evaluate_fixtures.py --train data/research/fpl-2023-24.csv --test data/research/fpl-2024-25.csv --out docs/research/2026-09-07-fixtures-development.json
python3 scripts/evaluate_fixtures.py --train data/research/fpl-2023-24.csv --test data/research/fpl-2025-26.csv --out docs/research/2026-09-07-fixtures-validation.json
python3 -m unittest tests.test_fixture_challenger
```

Both JSON reports retain coefficients, configuration, cohorts, source hashes and
implementation identity. Source snapshots and local hashes are reproducibility
evidence, not independent proof of when this experiment was specified.

Verification: 1,336 tests passed, including eight fixture-specific regression tests.
The existing four-provider GW4 rehearsal covered all 654 players without changing
its forecasts or freezing a record. Public page/API rendering and cross-fold
coefficient/implementation equality were checked.
