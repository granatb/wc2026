# Strategy, evidence and delivery — 7 September 2026

Keep the market-informed model, run an independent statistical challenger, and earn the right to blend them. Odds are a useful estimate of team strength; they do not solve minutes, player roles, scoring details or squad decisions. There is no demonstrated predictive edge yet. FC27/game ratings are excluded from this FPL research programme.

## What the record actually says

Frozen squads replay to GW1 44–53, GW2 93–84 and GW3 37–59: model-assisted squad 174, consensus 196. These totals remain unchanged after repairing grading; reconstructing squads from today's state would have changed them. GW1's historical “Sangaré”, NFO, is explicitly mapped to Ibrahim Sangaré (FPL ID 488). Previous accuracy receipts are preserved under `evmax/assets/accuracy/revisions/`.

The corrected GW3 all-source common intersection has 343 players: evmax MAE 1.891 / RMSE 2.791; Fantasy Football IQ 1.786 / 2.629. The common 60+ minute subset has 192 players: 2.468 / 3.477 versus 2.371 / 3.245. These are different populations from the earlier reported 585-player pairwise comparison. Original coverage is retained separately. Neither comparison supports claiming we lead. GW3's late Git receipt and the old horizon-vintage limitation remain historical limitations; code cannot retrospectively establish publication timing.

World Cup Round 3 is restored. The already published Round 4 retrospective report is retained as an explicitly retrospective receipt; routine builds no longer rerun it with today's engine.

## A real odds-free experiment

Source: [Vaastav's public FPL historical data](https://github.com/vaastav/Fantasy-Premier-League). Downloaded the 2023/24 and 2024/25 `gws/merged_gw.csv` files. Local raw inputs are gitignored under `data/research/`; the committed result records SHA-256 checksums. Do not relicense raw third-party data as evmax's model output.

Training: 2023/24 only. Held out: 2024/25 only. Fixed ridge penalty 100, with no holdout tuning. Nine features: intercept, lagged four-gameweek points/minutes/xG/xA, season-to-date points per gameweek, and position indicators. Doubles aggregate before feature calculation; blank weeks inside a known history count as zero. Neither current-season data, FC27 ratings, future points, injuries, odds, prices nor ownership enters the model. Match timestamps enforce separation between training and holdout seasons.

| Held-out population | Model | MAE | RMSE |
|---|---|---:|---:|
| All 22,425 eligible recorded player-gameweeks | Ridge | 1.096 | 2.064 |
| Same | Last four GW average | 1.101 | 2.203 |
| Same | Season points/GW | 1.109 | 2.108 |
| 5,454 player-gameweeks with prior four-GW average minutes ≥60 | Ridge | 2.302 | 3.107 |
| Same | Last four GW average | 2.530 | 3.410 |
| Same | Season points/GW | 2.264 | 3.158 |

The 95% gameweek-block bootstrap interval for ridge minus last-four MSE is approximately [-0.672, -0.508]. This is an improvement over that baseline in this held-out season. It is **not** an odds comparison, a production forecast record, a prospective validation, or a demonstrated captain/transfer advantage. The frequent-player cohort also shows why one metric is insufficient: ridge improves RMSE but loses MAE to season points/GW. Historical extracts can contain later corrections; scoring rules differ from 2026/27; players without six prior recorded gameweeks are excluded.

Reproduce:

```sh
python3 scripts/evaluate_challenger.py --train data/research/fpl-2023-24.csv --test data/research/fpl-2024-25.csv --out docs/research/2026-09-07-challenger-results.json
```

The same training season contains 1,071 FPL assists and 1,246 goals across 380 fixtures. The FPL event model uses 0.85955 as its starting assisted-event probability. Allocation still has an unmodelled-player sink; this is not a claim that its final aggregate assist rate is calibrated.

## Data priorities

1. **Minutes and availability first.** Capture official fixtures, squad membership, starts/substitute appearances, minutes, injuries, suspensions and manager press conferences. Keep `observed_at`, source URL, player ID, applicable GW, expiry and confidence. A club transfer resets confidence in the old role. Never treat an LLM's interpretation as a new fact. Official bootstrap/fixture writes now retain timestamped, hashed observations.
2. **Player performance second.** Add lagged non-penalty xG, xA, shots, box touches, set-piece/penalty roles, defensive actions and saves with source coverage audits. Player and team rates need shrinkage, recency weighting and league/club context. Missing coverage must not mean zero performance.
3. **Market context alongside those inputs.** Keep de-vigged 1X2 and totals, source timestamps, bookmaker spread and movement. Add reliable player goals/assists props only where coverage and acquisition terms permit. Separate early-week and deadline forecasts. Do not compare closing odds with earlier model snapshots as if they had the same information.
4. **Buy only after an ablation earns it.** Trial event data or lineup providers on a fixed sample, then measure incremental calibration and decision value. More scraped pages are not automatically more signal. [FPL Review describes a hybrid approach](https://docs.fplreview.com/getting-started/about-fplreview/); [OpenFPL](https://arxiv.org/html/2508.09992v1) supports testing public-data challengers, not assuming they will win here.

## Model promotion rules

Freeze four variants at the same cutoff: naive baseline; corrected market-informed model; odds-free challenger; a blend whose weights were fitted only on earlier folds. Separate automatic predictions from sourced human overrides. Use expanding chronological folds and a final untouched season, then prospective gameweeks. Primary mean forecast loss: MSE/RMSE; also MAE, bias, minutes calibration, distribution calibration and errors by position, minutes risk, promoted/transferred players and forecast horizon. Bootstrap by gameweek; do not treat every player as independent.

Grade captain decisions and transfers on legal squads, accounting for price, hits and available options. Current transfer utility now optimizes each week's legal XI plus captain mean. Autosubs, vice-captain fallback, future free-transfer option value, chip strategy and correlated squad simulations remain further work. Do not market the current utility as a complete FPL solver.

The corrected event model has bounded simultaneous lineups, exposure intervals, MID clean sheets, exact conceded thresholds, no self-assists, save rates, shrunk DefCon, residual BPS and fitted Dixon-Coles scorelines. Its lineup marginals, cameo proxy, partial-squad sink, own goals, penalty events, goalkeeper substitutions and red-card timing remain limitations. BPS residuals approximate unobserved contributions; the [2026/27 official BPS changes](https://www.premierleague.com/en/news/4679946/whats-new-in-202627-fantasy-changes-to-bonus-points-system) make cross-season calibration necessary.

## Website direction

The useful promise is “make your next FPL decision with an explanation you can check.” Prioritize one workflow: enter squad → compare hold versus feasible moves → select captain → save the decision → review it after the deadline. Each recommendation should show expected gain after hits, downside, minutes sensitivity, the most important source-backed reason, input age and what new information would change the call. Publish only appropriately supported probabilities; simulation count is not model confidence.

Keep historical pages as evidence. Full new forecasts, player cards, ordered squads, IDs, inputs, model fingerprint and prose are archived before the deadline; legacy missing boards are labelled unavailable. Checksums detect alteration but are not independent timestamps. A public Git/deployment receipt before the deadline remains operationally necessary.

Measure product success separately: completed squad analyses, saved decisions, return visits around the next deadline, and readers revisiting their scorecard. First establish a denominator and baseline, then set targets. Use a small opted-in test group to find confusing recommendations before adding more article types, paid plans or expensive feeds. Avoid claiming retention improvements without actual measurements.

## Remaining work requiring new evidence

The offline challenger is evaluated, not integrated into live forecasts. A trained minutes model, optimized blend, realistic joint lineups, full autosub/chip solver, multi-season robustness and prospective performance cannot be honestly marked complete by writing scaffolding. The next promotion requires fresh inputs and dated forecasts. Today's GW4 smoke simulation used cached odds from 1 September, so its output is a **test artifact**, not a current recommendation. No production deployment was performed during this remediation.


Follow-up implementation adds the four-arm virtual experiment ledger, portfolio
continuity, shared decision policy and public registration/standings page. All
four providers still require integration; no prospective weeks are enrolled.
See `experiments/fpl-2026-27/README.md` for the executable workflow.

Validation: 1,305 Python tests and 3 MCP regressions passed; MCP dependency audit
reported zero vulnerabilities. The historical preview passed the deployment
evidence validator. See the fix plan for exact scope and retained limitations.
