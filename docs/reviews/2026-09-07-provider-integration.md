# Experimental provider integration

The four-arm ledger now has working forecast providers and a repeatable
train → refresh → build → prepare workflow. A fresh GW4 run covered all 654
official players in every arm and produced a legal common-seed draft. FFIQ
matched all 654 IDs; no official-only fallback was needed in this run.

The market model chose Szoboszlai as captain; statistical, hybrid and external
reference chose B. Fernandes. These are draft decisions, not recommendations
backed by a demonstrated edge. No experimental week has been frozen or graded.

## Methodology decisions

- Keep the corrected market engine, but disable editorial overlays in this
  experiment. Require actual fresh match odds for every fixture.
- Fit a distinct early-season ridge model on 2023/24 with one or more prior
  recorded gameweeks. Share the exact feature transform between historical
  training and live inference. Never reuse IDs across seasons to join players.
- Evaluate on 2024/25 without fitting weights to that season: 26,427 rows,
  RMSE 2.09335 versus last-four baseline 2.23101; MAE 1.10013 versus 1.10431.
  This is a different population from the earlier six-week challenger evaluation.
- Use a prespecified 50/50 market/statistical blend. Historical market vintages
  are absent, so there is no honest basis for calling this blend optimized.
- Define the reference as FPL `ep_next` plus attributed FFIQ projections. Missing
  FFIQ players retain official points, with IDs and coverage disclosed. External
  training lineage is unknown; no training date is fabricated.

Internal models exclude FC27 ratings. The statistical availability gate and
double-gameweek scaling are explicit prospective approximations, not benefits
measured by the heldout experiment. Cold-start positional means still need
validation. No model has demonstrated an edge over the corrected market model.

## Integrity and operations

Source bundles bind all raw inputs, fitted model, code fingerprints, predictions,
versions and forecast clocks. Prepare/freeze verify the board against its bundle.
Official history must reconcile to current player totals, be final, and contain
every prior gameweek without gaps after registration. Stale source timestamps,
wrong fixture populations, ambiguous external identities and nonfinite inputs
are rejected. Raw external forecasts remain in ignored local data storage.

The live-data rehearsal is stored in `data/experiments/gw4/`; the reusable command
sequence and retention requirements are in `experiments/fpl-2026-27/README.md`.
The fitted statistical model is stored as a candidate artifact, not a claim
that its historical score will transfer to 2026/27 rules.

Refresh and regenerate near GW4's official deadline (12 September, 12:30 UTC),
then freeze and publish an independent receipt before the deadline. A current
draft does not authorize pretending that a later forecast existed earlier.
No automation was scheduled, and no new website deployment was performed in this
provider-integration step.

Validation: the full 1,311-test suite passed after provider integration; all seven
provider regressions passed after adding the explicit unknown-training test.
The historical site preview built and passed publication validation. The final
live-data build and source-verified squad preparation both succeeded.
