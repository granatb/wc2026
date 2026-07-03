# Engine improvement roadmap — from the SOTA research program

*Synthesized 2026-06-24 from 99 methods / 9 research domains (full evidence + source URLs in [2026-06-24-engine-sota-corpus.json](2026-06-24-engine-sota-corpus.json)). Two gap domains (platform market microstructure; intra-match awards/BPS/MOTM) and an independent synthesis pass hit the session limit — re-run after reset to append.*

## The headline finding: our −2.3 xPts gap has a likely *mechanical* cause

Four independent research angles converged on the same diagnosis: **proportional de-vig + plain-Poisson inversion of 1X2 odds systematically under-recovers goal expectancy.**

- Practitioner validation (opisthokonta) measured the exact failure: plain-Poisson inversion of 1X2 under-recovers **~0.10–0.15 goals per team per match**.
- Hegarty & Whelan (Int J Forecasting 2025, 80k+ matches): 1X2 odds carry strong favourite-longshot bias, while **Asian-handicap implied probabilities are statistically unbiased** — supremacy should be read from AH, not 1X2.
- Proportional de-vig understates favourites most in lopsided fixtures — exactly the World Cup group-stage profile — and AGS player props (20–40% margins, heavy longshot skew) inflate deep options while deflating stars under proportional treatment.

Fewer team goals × understated star scoring rates → systematically low xPts, worst for favourites. This is fixable in days, not months (Phase 1, items 1–3).

## Phase 0 — Measurement first (prerequisite for everything)

No model change ships without evidence. The backtest harness must provide:

1. **Log-loss (primary) + RPS/Brier vs the de-vigged-odds baseline** — every probability we emit scored as *skill vs market*, not raw accuracy.
2. **Component-level bias decomposition** — score each simulated event stream (goals, assists, SoT, CS, minutes, saves, cards) separately vs realized (`stats_rN.json` event IDs already decoded) → tells us *which component* carries the remaining bias.
3. **PIT histograms** (Czado-Gneiting-Held for counts) on the scoreline distributions; clean-sheet reliability diagram.
4. **CLV loop:** add a second odds snapshot at kickoff−1h; score our probabilities against de-vigged *closing* odds — fast per-round ground truth that doesn't wait for outcomes.
5. **Distributional player scoring:** persist per-player sim quantiles; CRPS + pinball loss at τ=0.85 (audits the ceiling numbers we publish); benchmark against a simulated **noise ceiling** (score the engine against its own draws = the best any model could do).
6. **Leakage-free point-in-time protocol:** append-only timestamped snapshots (odds, ownership, overlay facts dated) + a replay clock → makes the hand-set blend weight `w` legitimately tunable by grid search.
7. **Small-sample honesty:** paired permutation tests + minimum-detectable-effect reporting (a ~104-match tournament can't confirm small edges — report that).
8. *(Scale option, L):* backfill the match layer over thousands of archived-odds matches (football-data CSVs, B365/PS open+close) → tight CIs for the bake-offs below.

## Phase 1 — Quick wins (S/M; order of expected evidence-per-effort)

1. **Shin de-vig bake-off** (S). Replace proportional with Shin (fixed-point on z, ~30 lines stdlib); power method for 2-way markets. Štrumbelj 2014: Shin cut forecast bias ~two-thirds vs normalization. Validate via Phase 0.1 before adopting.
2. **FLB-aware AGS prop de-vig + minutes-aware inversion** (S, high). Shin/power-with-booksum on goalscorer props, reconciled to team λ; converts to rates through expected minutes rather than flat 90. Directly raises star forwards' rates (our audited weakness).
3. **Pin λ from Asian handicap + the full totals ladder** (M, high). Replace the 2-equation 1X2+total solve with weighted least-squares over ALL cached markets (AH supremacy via Skellam inversion, O/U 1.5/2.5/3.5, BTTS, CS grid where free). With ≥4 constraints, per-match dispersion/dependence become identifiable, not just the two means.
4. **Decomposed minutes model** (M, high). Replace "starters = 60′" with P(start)/P(cameo)/P(unused) × conditional minutes distributions; beta-binomial start posteriors from cached team sheets; team-level 990-minute conservation constraint. The OpenFPL paper attributes FPL Review's remaining edge to exactly this layer.
5. **Dead-rubber rotation model** (M, high). Use our own group-stage simulation to compute each team's stakes entering MD3 → churn multiplier on P(start). (We hand-did this for R3 via research notes; make it a model.)
6. **Structured news ingestion** (M, high). Replace freeform overlay multipliers with typed entries (status, source-trust, hours-to-kickoff) → calibrated P(start) adjustments; matches our memory rule that only confirmed team news should move start probs.
7. **Scenario-matrix export** (S, high). Stop collapsing the 50k draws to means — persist per-sim player points (int16, gzip). Unlocks the entire portfolio layer (Phase 2) for free and makes captain/ceiling numbers exact per-world quantities.
8. **Joint scorer–assister assignment per simulated goal** (S). Same-play correlation baked into the sim.
9. **Recalibration layer** (M, high). Walk-forward beta/multiplicative calibration per position/component fitted on completed rounds — kills residual level bias while structural fixes land.
10. **Knockout mechanics** (M): reconcile 90′ 1X2 with to-advance odds → simulate ET/pens exposure and its minutes/points effects (needed for R32 in days).

## Phase 2 — Structural upgrades (L; rank by impact once Phase 0 measures)

- **Weibull-count marginals + Frank copula scoreline model** (Boshnakov-Kharrat-McHale) — the standout *published market-beater* among count models (positive Kelly returns on 1X2 and O/U); moves CS, ceilings, correct-score mass even with 1X2 pinned to market. penaltyblog as reference implementation for a stdlib port.
- **Minute-level match simulation** (Dixon-Robinson birth process with score-state intensity) — structural correlation: goals, minutes, subs, cards interact per-world; replaces flat per-match player sim. Gold standard (SaberSim-style).
- **Multi-book consensus** (precision-weighted logit mean) or Betfair exchange as a near-vig-free second anchor — replaces single-book dependence *and* de-risks the ESPN availability threat.
- **Outright-market ability inversion** (bookmaker-consensus school, Leitner/Zeileis) — team abilities from tournament-winner odds → future-round λ for multi-round transfer/chip planning (the R32 wildcard question needs exactly this).
- **Hierarchical shot-generation × conversion player priors** (McHale-Szczepański line) — beats naive goal rates AND bookmaker-implied probs in FPL Review's own audit; fitted offline on Understat/FBref + StatsBomb open internationals, consumed as cached JSON.
- **Opponent-field rank engine** (Haugh-Singal): projected ownership (Dirichlet-multinomial) + field simulation over the scenario matrix → optimize P(top-k), not E[points]; leverage/captaincy as explicit game theory. This is the public-content differentiator ("chase rank" articles) too.
- **In-tournament Bayesian updating with published-magnitude discipline:** Gamma-Poisson conjugate shrinkage; Ley et al. optimal half-life ≈ 3 *years* for national teams → 1–3 matches should move strength only ~5–10%; roster-adjusted λ corrections (injuries propagate to *team* strength); a hard "never update finishing skill in-tournament" rule (year-over-year correlation ≈ 0).
- **Defensive-contribution simulation** (negative-binomial counts coupled to game state) — replaces the role-shaped MID estimate; matters for FIFA + new FPL DC points.

## Phase 3 — Moonshots (XL; track, don't build yet)

- **Large Events Model (LEM):** autoregressive event-sequence simulator as the player-event engine.
- **Hybrid covariate model** (random forest + ability parameters) as an odds bias-corrector for tournament football.
- **Player-level ML scoring-rate model** replacing props as the primary source (FPL-Review-style; L/XL with data pipeline).

## Sobering evidence to respect (from the ML-benchmarks sweep)

- Model class barely matters at match level: 2023 Soccer Prediction Challenge won by a bookmaker-consensus-type model; deep learning **lost** to CatBoost+pi-ratings; top methods near-indistinguishable (RPS 0.206–0.219).
- FiveThirtyEight's SPI lost −6.2% ROI vs Pinnacle closing over 36k matches → **standalone ratings must enter as priors/blends, never replace odds-implied λ.** Our odds-anchored architecture is correct; the wins are in *extracting the odds properly* and in the *player/minutes/portfolio layers* the market doesn't price.

## Convergence map (findings ≥3 domains agree on)

| Finding | Domains agreeing |
|---|---|
| Proportional de-vig is wrong; Shin/power + AH anchoring | score-models, odds-processing, player-event-rates, ml-benchmarks, validation |
| Minutes projection is the biggest structural gap vs commercial systems | minutes, bayesian, ml-benchmarks, correlation |
| Keep and reuse the 50k draws (scenario matrix) for portfolio/rank | correlation, portfolio, validation |
| Score everything vs the odds baseline; measure before believing | validation, ml-benchmarks, score-models |
| In-tournament updates must be tiny (~5–10% after 1–3 games) | bayesian, score-models, odds-processing |

## Pending

- Re-run after limit reset: `platform-market-microstructure`, `intra-match-awards-bps-motm` gap agents + independent synthesis cross-check (workflow resume: run ID `wf_93267a43-13d`).
