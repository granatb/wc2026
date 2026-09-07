# Minutes candidate and historical-population correction

## Outcome

The new fitted minutes-transition model is a research candidate. It does not
replace production minutes assumptions or change the four-arm decision policy.
Its probability scores and minutes RMSE improve over the last-four baseline;
its minutes MAE worsens and cold-start improvement is negligible.

| Heldout population | N | Transition Brier | Last-four Brier | Transition minutes MAE | Last-four minutes MAE | Transition minutes RMSE | Last-four minutes RMSE |
|---|---:|---:|---:|---:|---:|---:|---:|
| All single-fixture player-GWs | 26,555 | 0.3026 | 0.3198 | 15.50 | 13.56 | 23.98 | 25.14 |
| Cold start | 782 | 0.5713 | 0.5731 | 33.02 | 33.09 | 37.54 | 37.54 |
| One to four prior fixtures | 3,109 | 0.2932 | 0.3246 | 13.68 | 11.22 | 21.99 | 23.30 |
| Prior average under 30 minutes | 16,389 | 0.2282 | 0.2356 | 8.98 | 7.03 | 17.42 | 18.38 |
| Prior average at least 60 minutes | 6,412 | 0.3309 | 0.3503 | 22.77 | 18.14 | 29.18 | 30.57 |

Rows are historical player-gameweeks, not independent observations. The JSON
report includes equal-gameweek paired differences with exploratory three-week
block intervals and probability calibration bins for every class/cohort. These
intervals are descriptive and unadjusted for multiple comparisons.

## Model and evaluation

Training uses 2023/24 only; 2024/25 is held out. Three outcomes are no appearance,
1–59 played minutes and 60+ played minutes. They are **not starting probabilities**.
The model fits position-specific transitions conditioned on the last observed
role and a binned last-four-fixture minutes average. Cell estimates shrink toward
training position priors with fixed strength 20. Predicted minutes use training
class-conditional means. No parameter was tuned to the heldout season.

Baselines estimate class probabilities from smoothed recent/season role counts;
their minutes forecasts use the raw recent/season minutes mean where history
exists. Cold starts use training-derived positional information. Five-bin
calibration tables expose average probabilities against observed frequencies;
good aggregate Brier scores alone do not establish calibration for every group.

Only earlier gameweeks played before the target GW's first kickoff enter history.
Within-GW results are never used. Actual historical deadline and final-result
publication timestamps are unavailable, so this remains a retrospective study,
not a reconstruction of independently timestamped operational forecasts. Targets
exclude double-gameweek rows and the dataset lacks explicit blank-week targets.
Injuries, lineup news, club changes and cross-season ID joins are absent.

## Assistant Manager contamination corrected

The 2024/25 CSV contains 322 raw Assistant Manager rows (position `AM`). Those
were previously included by the ridge evaluator with all position indicators
zero, effectively treating managers like forwards. Both evaluators now restrict
the population to GK, DEF, MID and FWD. The unchanged 2023/24 training data contain
no AM rows, so the ridge coefficients do not change.

- Early ridge: heldout N **26,427 → 26,135**, RMSE **2.0934 → 1.9902**;
  corrected last-four baseline RMSE **2.1432**.
- Six-prior-GW ridge: N **22,425 → 22,233**, RMSE **2.0641 → 2.0027**;
  corrected last-four baseline RMSE **2.1500**.

These changes correct the evaluation population, not the forecasts. The original
`2026-09-07-challenger-results.json` remains as the original research receipt;
`2026-09-07-challenger-players-only.json` is the corrected evaluation. The candidate
statistical model artifact was regenerated with its matching feature-code hash
and corrected evaluation. No frozen experimental week or historical site forecast
was replaced.

## Reproduce and next decision

```sh
python3 scripts/evaluate_minutes.py --train data/research/fpl-2023-24.csv --test data/research/fpl-2024-25.csv --out docs/research/2026-09-07-minutes-results.json
```

Before production integration, evaluate genuine historical availability inputs,
full blanks/doubles handling, a production-heuristic baseline reconstructed from
appropriate prior-season data, and another untouched chronological fold. Measure
changes to point forecasts and squad decisions, not just minutes errors. Until
then, the current four providers continue using their existing minutes behavior.
