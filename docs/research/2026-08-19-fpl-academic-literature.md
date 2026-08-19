# FPL & fantasy-football optimization: annotated literature survey

*2026-08-19. Survey of academic and quasi-academic research relevant to our engine
(market odds → de-vig → Dixon-Coles scoreline distributions → per-player event
simulation → FPL scoring → expected-points order books).*

Scope note: the academic FPL literature is thin and skews toward point-prediction ML;
the serious optimization work lives half in theses and half in open-source community
tooling (which is often more advanced than the papers). The rank-vs-points theory is
best developed in the US daily-fantasy (DFS) literature and transfers well.

---

## Theme 1 — Scoreline & team-level prediction (our simulation backbone)

### Dixon & Coles (1997), "Modelling Association Football Scores and Inefficiencies in the Football Betting Market"

- **Citation:** Dixon, M.J. & Coles, S.G. (1997). *JRSS Series C (Applied Statistics)*, 46(2), 265–280. [Publisher](https://rss.onlinelibrary.wiley.com/doi/abs/10.1111/1467-9876.00065)
- **Summary:** The founding paper of the scoreline-modelling literature. Independent
  Poisson goals with team-specific attack/defence parameters and home advantage,
  plus two crucial fixes: (a) a low-score dependence correction (the τ adjustment
  inflating 0-0/1-1 and deflating 1-0/0-1 relative to independence), and (b)
  exponential time-decay downweighting of older matches in the pseudo-likelihood, so
  team strengths track form. Fitted to English league/cup data 1992–95, then used to
  attack bookmaker odds 1995–96.
- **Method:** Poisson regression, maximum pseudo-likelihood with time decay,
  value-betting rule (bet when model probability / bookmaker probability > threshold).
- **Headline result:** Positive returns as the basis of a betting strategy against
  mid-90s bookmakers — i.e. the model found real inefficiencies then (markets are
  far sharper now).
- **Transferable: yes — already core.** We use D-C structurally, but the two details
  worth auditing in our engine: (1) since we calibrate to de-vigged odds per match
  rather than fitting from historical results, the *time-decay* machinery is
  irrelevant for us, but the *low-score τ correction* still matters — a plain
  independent-Poisson grid fitted to the 1X2/OU odds systematically misallocates
  mass between 0-0/1-1 and 1-0/0-1, which directly hits clean-sheet and defender EP;
  (2) fit τ to markets that pin down the draw (correct-score odds where available).

### Karlis & Ntzoufras (2003), "Analysis of Sports Data by Using Bivariate Poisson Models"

- **Citation:** Karlis, D. & Ntzoufras, I. (2003). *JRSS Series D (The Statistician)*, 52(3), 381–393. [PDF](http://www2.stat-athens.aueb.gr/~jbn/papers2/08_Karlis_Ntzoufras_2003_RSSD.pdf)
- **Summary:** Replaces the independence assumption with a bivariate Poisson
  (shared latent component λ₃ creating positive correlation between the two teams'
  goal counts) and, importantly, a *diagonal-inflated* variant that adds extra mass
  on draws. Shows both improve fit and, especially, draw prediction, which
  independent Poisson chronically underestimates.
- **Method:** Bivariate Poisson via trivariate reduction, EM estimation,
  diagonal inflation for draws; applied to Italian Serie A.
- **Headline result:** Better model fit and materially better draw-count prediction
  than independent Poisson; λ₃ is usually small but non-zero.
- **Transferable: partially.** Same practical implication as the D-C τ: the
  dependence structure matters for scoreline-conditional quantities (clean sheets,
  "both teams to score" consistency). If our de-vig pipeline consumes BTTS or
  correct-score markets, a diagonal-inflated bivariate Poisson is a strictly richer
  family for reconciling them than independent Poisson + τ. If we only consume 1X2 +
  totals, τ-corrected D-C is sufficient and simpler.

### Successors worth knowing (brief)

- **Rue & Salvesen (2000)** — Bayesian dynamic generalized linear model with
  time-varying team strengths (precursor to Kalman-style strength tracking).
  *Transferable: no* — odds calibration supersedes strength estimation for us.
- **Boshnakov, Kharrat & McHale (2017)**, "A Bivariate Weibull Count Model for
  Forecasting Association Football Scores" ([PDF](https://blogs.salford.ac.uk/business-school/wp-content/uploads/sites/7/2016/09/paper.pdf)) — inter-arrival goal times
  are not exponential; Weibull count models give heavier/lighter tails than Poisson
  and beat it in forecasting tests. *Transferable: partially* — relevant only if we
  ever simulate in-match goal *timing* (minutes-based events, red-card windows);
  for full-match score distributions calibrated to odds it adds little.
- **Extension survey:** the D-C family still underpins modern open tooling (e.g.
  the [regista](https://torvaney.github.io/regista/reference/dixoncoles.html) R
  package and the Turing Institute's AIrsenal team model below).

### Odds vs. stats models — published backtests

- **Citation (a):** Forrest, Goddard & Simmons (2005), "Odds-setters as forecasters:
  the case of English football" / and "The value of statistical forecasts in the UK
  association football betting market" ([ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S016920700400010X)), *Int. J. Forecasting*.
- **Citation (b):** Spann & Skiera (2009), "Sports forecasting: a comparison of the
  forecast accuracy of prediction markets, betting odds and tipsters"
  ([Academia](https://www.academia.edu/2549746/Sports_forecasting_a_comparison_of_the_forecast_accuracy_of_prediction_markets_betting_odds_and_tipsters)).
- **Citation (c):** Wilkens (2026), "Can simple models predict football — and beat
  the odds? Lessons from the German Bundesliga", *J. Sports Analytics* / SAGE
  ([journal](https://journals.sagepub.com/doi/10.1177/22150218261416681)).
- **Citation (d):** Wunderlich & Memmert (2018), "The Betting Odds Rating System:
  Using soccer forecasts to forecast soccer" ([PLOS One](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0198668)).
- **Summary:** The through-line of two decades of backtests: bookmaker odds are the
  best single forecaster of match outcomes, and their edge over pure stats models
  *grew* over time as odds-setting professionalized (Forrest et al. tracked this
  across seasons). Prediction markets ≈ odds > tipsters (Spann & Skiera). Odds known
  before the match carry more predictive information about future results than the
  actual realized result does (Wunderlich & Memmert — the basis of odds-derived
  team ratings). The nuance from recent work (Wilkens 2026): odds are the best
  *calibrated*, but xG-based models capture some signal not fully priced in, and
  simulated betting showed ~10–15% ROI in a Bundesliga backtest window — evidence
  that a stats overlay on top of odds can add value at the margin, though such ROI
  claims rarely survive out-of-sample.
- **Headline result:** Odds-first is the empirically correct architecture; stats
  models earn their keep only as *overlays* on markets, not replacements.
- **Transferable: yes — validation of our core design.** Our
  odds → de-vig → D-C pipeline sits on the right side of this literature. The
  actionable nuance: keep an xG/stats-based residual check against the odds-implied
  team goal rates, both as a sanity monitor and as a tie-breaker where markets are
  stale (early lines, low-liquidity WC group games).

---

## Theme 2 — Player expected-points prediction

### Matthews, Ramchurn & Chalkiadakis (AAAI 2012), "Competing with Humans at Fantasy Football: Team Formation in Large Partially-Observable Domains"

- **Citation:** Matthews, T., Ramchurn, S.D. & Chalkiadakis, G. (2012). *Proc. AAAI-26*, Toronto. [PDF](https://eprints.soton.ac.uk/340382/1/fantasyFootball2012cr.pdf), [Semantic Scholar](https://www.semanticscholar.org/paper/5aaaa7c18b7703021ed959dbe4dba15b35fd0d8a)
- **Summary:** Still the canonical academic FPL paper. Frames a full FPL season as a
  belief-state Markov decision process: beliefs over each player's latent abilities
  (appearance probability, scoring rates per point category) updated Bayesianly from
  observed performances; the weekly squad/transfer decision handled by decomposing
  the exponential action space. They combine Bayesian Q-learning for the sequential
  transfer policy with knapsack-style combinatorial optimization for team formation,
  using domain structure (points decompose per player; budget/formation constraints
  are linear) to stay tractable.
- **Method:** Bayesian RL (belief-state MDP), Bayesian Q-learning over transfer
  actions, LP/knapsack team formation, player ability priors from historical data.
- **Headline result:** Ranked around the **top percentile against ~2.5M human
  players** in the 2010/11 season, without information human managers had (news,
  injuries). Follow-up deployment as "**Squadguru**"
  ([Southampton ECS](https://ecs.soton.ac.uk/news/4915), [BBC](https://feeds.bbci.co.uk/news/technology-40905913)) reportedly held top-1%
  form across later seasons and beat BBC pundit predictions two seasons running; the
  group's later work (Beal et al., e.g. [Optimising Game Tactics for Football, AAMAS 2020](https://dl.acm.org/doi/10.5555/3398761.3398783)) moved to real-football tactics.
- **Transferable: partially.** The Bayesian-RL machinery itself is superseded by our
  odds-based inputs (their belief updating is doing, badly, what the market does
  well). What transfers: (1) the *decomposition* insight — sequential transfer policy
  and within-week team formation are separable layers, each tractable; (2) the
  framing of squad value as expected points under uncertainty rather than point
  estimates; (3) proof that top-1% is achievable with EV-maximization alone, no
  rank-gaming needed — relevant to how much complexity we spend on rank objectives.

### Groos (2025), "OpenFPL: An open-source forecasting method rivaling state-of-the-art Fantasy Premier League services"

- **Citation:** Groos, D. (2025). arXiv:2508.09992. [arXiv](https://arxiv.org/abs/2508.09992)
- **Summary:** The most useful recent benchmark paper. Builds *position-specific
  ensemble models* (Random Forest + XGBoost with hyperparameter search) on public
  FPL + Understat data (2020/21–2023/24), prospectively tested on 2024/25, and —
  crucially — benchmarks head-to-head against the commercial FPL Review "Massive
  Data" model with error split by return category (Zeros / Blanks / Tickers /
  Haulers).
- **Method:** Position-specific supervised ensembles; public features (form, minutes,
  Understat xG/xA, fixture context); evaluation by RMSE/MAE per return category over
  1/2/3-GW horizons.
- **Headline result:** Both OpenFPL and FPL Review beat naive baselines by 5–34%
  RMSE. FPL Review wins on low-return categories (predicting zeros/blanks — i.e.
  minutes); **OpenFPL wins on high-return players (>2 pts), the ones that decide
  rank**. Shorter horizons help most on Zeros (15–25% RMSE improvement 1-GW vs
  3-GW), i.e. the horizon-decay is mostly a *minutes-information* effect.
- **Transferable: yes.** Three direct adoptions: (1) their return-category evaluation
  protocol is exactly the right backtest harness for our EP order books (RMSE on
  haulers matters more than aggregate RMSE); (2) position-specific residual models
  layered on our odds-driven baseline could capture what odds don't price (set-piece
  duty, BPS propensity, team style); (3) their finding that horizon degradation is
  minutes-driven argues for investing in the minutes model, not the goals model.

### Bonello, Beel, Lawless & Debattista (2019), "Multi-stream Data Analytics for Enhanced Performance Prediction in Fantasy Football"

- **Citation:** Bonello, N., Beel, J., Lawless, S. & Debattista, J. (2019). *27th AIAI Irish Conf. on AI and Cognitive Science*. arXiv:1912.07441. [arXiv](https://arxiv.org/pdf/1912.07441)
- **Summary:** Tests whether fusing heterogeneous signals — historical player stats,
  fixture difficulty, **betting-market data**, social-media sentiment, expert
  articles — beats purely statistical prediction for FPL.
- **Method:** Multi-source feature engineering into a supervised predictive model;
  evaluated by simulating a full FPL 2018/19 season.
- **Headline result:** The fused model outperformed conventional statistical
  predictors by **~300 points over the season (~11 pts/GW)**, landing around rank
  30,000 of 6.5M (top 0.5%).
- **Transferable: partially.** Direct evidence that *betting-market features beat
  stats-only features* for FPL specifically — external validation of our
  architecture. The sentiment/news streams are the interesting marginal idea: they
  proxy team-news/minutes information that neither odds nor historical stats carry.
  We'd adopt the *category* (a minutes/news signal), not their pipeline.

### ML point-prediction cluster (representative entries)

- **Citations:** "Using ML Models to Predict Points in Fantasy Premier League"
  (IEEE, 2022, [IEEE Xplore](https://ieeexplore.ieee.org/document/9909447/));
  CNN-vs-LSTM comparison ([ResearchGate](https://www.researchgate.net/publication/391850138_PREDICTING_FANTASY_PREMIER_LEAGUE_POINTS_USING_CONVOLUTIONAL_NEURAL_NETWORK_AND_LONG_SHORT_TERM_MEMORY));
  "Deep Learning and Transfer Learning Architectures for EPL Player Performance
  Forecasting" (arXiv:2405.02412, [arXiv](https://arxiv.org/pdf/2405.02412));
  transformer + news-sentiment variant ([ResearchGate](https://www.researchgate.net/publication/391452336));
  Gupta (2019), "Time Series Modeling for Dream Team in Fantasy Premier League",
  arXiv:1909.12938 ([arXiv](https://arxiv.org/abs/1909.12938)) — ARIMA+RNN ensemble
  feeding an LP team selector.
- **Summary:** A large, mostly low-quality cluster: linear regression, tree
  ensembles (RF/XGBoost/LightGBM), LSTMs/CNNs on per-player point histories, usually
  evaluated on aggregate RMSE against weak baselines, usually ignoring minutes as a
  separate problem, and almost never benchmarked against odds-implied projections.
  Consistent findings across the cluster: tree ensembles ≈ small neural nets ≫
  raw-form heuristics; the features that matter are **minutes/starts, ICT-style
  involvement indices, xG/xA, home/away, fixture strength, and recent form** — with
  fixture strength being precisely the thing market odds measure better than any of
  their proxies.
- **Headline result:** Nothing in this cluster demonstrably beats a good
  odds-anchored baseline; LSTM-vs-CNN style deltas are noise-level.
- **Transferable: no (mostly).** Useful only as a feature-importance census and as a
  reminder to always benchmark against the odds baseline before believing an ML win.

### FPL Review, "Ultimate Truth: How FPL Models Perform Relative to a 'Perfect' Model"

- **Citation:** FPL Review blog / docs (quasi-academic). [Article](https://fplreview.com/ultimate-truth-how-fpl-models-perform-relative-to-a-perfect-model/)
- **Summary:** The most honest calibration exercise in the community: estimates the
  irreducible error of FPL point prediction by constructing a "perfect" model that
  knows true underlying rates, then measuring how far real models sit from that
  ceiling.
- **Method:** Simulation-based noise floor estimation; comparison of live models'
  RMSE/MAE against it.
- **Headline result:** Perfect-model ceiling ≈ **RMSE 2.81 / MAE 1.96** per
  player-GW; good commercial/ML models (e.g. [FPL Pulse](https://www.fplpulse.com/blog/fpl-predicted-points-model)) already sit at ~2.79/1.95
  on starters — i.e. per-player point prediction is near saturation, and remaining
  edge lives in *minutes*, *joint distributions*, and *decision layers*, not in
  shaving mean-EP error.
- **Transferable: yes.** Adopt the noise-floor framing for our backtests: report our
  EP error relative to a simulated perfect-model floor (which our Monte Carlo engine
  can produce natively), so we know when a "model improvement" is fitting noise.

### Notelid & Östlund (2025), "Enhancing Fantasy Premier League Strategies through Machine Learning and Large Language Models"

- **Citation:** Notelid, E. & Östlund, T. (2025). MSc thesis, Uppsala University
  (supervisor: David Sumpter). [PDF](https://uu.diva-portal.org/smash/get/diva2:1972615/FULLTEXT02.pdf)
- **Summary:** Predicts FPL scoring components with linear/logistic regression and
  XGBoost, runs a GW1–21 simulation of 2024/25 with weekly lineup/substitution
  optimization, then wraps predictions in an LLM explanation layer for user-facing
  recommendations.
- **Method:** Component-wise supervised models → weekly optimizer → LLM explainer;
  user-trust evaluation of explanations.
- **Headline result:** Best variant (linear models) scored 1293 points over GW1–21,
  ≈ top 12% of managers; notably **linear ≈ XGBoost**, reinforcing the saturation
  point above.
- **Transferable: partially.** Modelling *scoring components separately* (goals,
  assists, CS, bonus) rather than total points is the right decomposition and is
  exactly what our event simulation does; the LLM-explanation layer is a product
  idea, not an engine idea.

---

## Theme 3 — Squad selection & transfer-plan optimization (MILP)

### Kristiansen, Gupta & Eilertsen (2018), "Developing a Forecast-Based Optimization Model for Fantasy Premier League" (NTNU)

- **Citation:** Kristiansen, B.K., Gupta, A. & Eilertsen, W. (2018). MSc thesis, NTNU. [NTNU Open](https://ntnuopen.ntnu.no/ntnu-xmlui/handle/11250/2577003)
- **Summary:** The earliest serious multi-period treatment: a MILP over the season
  with squad, budget, formation, 3-per-club, transfer and chip constraints, solved
  with a **rolling-horizon heuristic** (optimize a window, commit the first GW,
  roll forward) fed by point forecasts (recency-weighted averages; multivariate
  regression). Also tests **risk-handling constraints** and looks for a
  portfolio-style risk/reward trade-off.
- **Method:** MILP + rolling horizon; forecast variants; risk constraints
  (variance-limiting) tested on 2017/18.
- **Headline result:** Rolling-horizon MILP with even crude forecasts comfortably
  beats average human performance; risk constraints showed a measurable
  risk/reward trade-off analogous to portfolio optimization.
- **Transferable: yes.** This is the academic template for the decision layer our
  engine currently lacks: our per-GW EP order books are exactly the objective
  coefficients a rolling-horizon MILP needs.

### Çay / sertalpbilal, "FPL Optimization Tools" + open-fpl-solver (2020–, ongoing)

- **Citation:** Çay, S.B. (sertalpbilal). [FPL-Optimization-Tools](https://github.com/sertalpbilal/FPL-Optimization-Tools/blob/main/src/multi_period.py); tutorial repo [open-fpl-solver](https://github.com/solioanalytics/open-fpl-solver); blog [alpscode — Hindsight Optimization](https://alpscode.com/blog/hindsight-optimization/). Quasi-academic (Çay is an operations-research PhD; the repo is the de-facto community standard, used with FPL Review / Mikkel Tokvam projections).
- **Summary:** The most complete public formulation of FPL as a **multi-period
  MILP**: binary variables per (player, GW, state ∈ {squad, lineup, captain, vice,
  bench-order}), transfer in/out variables linking weeks, exact free-transfer
  rollover logic (including post-wildcard/free-hit FT accrual), chips as binary
  activation variables (WC/FH/BB/TC) with at-most-once constraints, budget flow with
  purchase/sale price asymmetry, and a **time-decay factor on future-GW objective
  terms** to discount forecast uncertainty. Solved with HiGHS/CBC via sasoptpy.
  The "hindsight optimization" blog solves the season with perfect information to
  establish the attainable ceiling — the same role as FPL Review's Ultimate Truth
  but for the *decision* layer.
- **Method:** Deterministic MILP, rolling horizon (typically 5–8 GW window),
  scenario/sensitivity analysis by re-solving over projection perturbations;
  optional "no-transfer EV" comparisons to price a free transfer (~1.5–2 pts is the
  community consensus that falls out of these solves).
- **Headline result:** Deterministic MILP over decent projections + decay is the
  strongest known practical baseline; every top solver-assisted FPL account uses a
  variant of this stack.
- **Transferable: yes — highest-priority adoption.** Our engine produces better
  inputs (full distributions, not just means) than this stack usually gets; wiring
  our EP means into this exact formulation is the shortest path to a decision layer,
  and our simulation lets us go beyond it (see Theme 5) by re-solving across Monte
  Carlo scenario draws instead of using a scalar decay factor.

### Alan Turing Institute, "AIrsenal" (2019–)

- **Citation:** [github.com/alan-turing-institute/AIrsenal](https://github.com/alan-turing-institute/AIrsenal)
- **Summary:** End-to-end open pipeline: Bayesian team-strength model in the
  Dixon-Coles family (their `bpl` library, Stan/numpyro), player-level conditional
  models (probability of goal/assist given team goals, minutes model), expected
  points per player per GW, then transfer-strategy search over the next few GWs
  (tree search over transfer options rather than MILP), including chip decisions.
- **Method:** Bayesian hierarchical team model → conditional player event model →
  EV → look-ahead transfer search.
- **Headline result:** Runs publicly every season; performance is respectable-but-
  not-elite (typically well above average, below top solver+commercial-projection
  stacks) — mainly limited by its projections, not its search.
- **Transferable: partially.** Its *player-conditional-on-team* decomposition
  (P(player scores | team scores k goals)) is structurally identical to our
  per-player event simulation, and their open code is a useful cross-check for our
  conditional rates. The transfer search is weaker than the MILP approach above.

### Letchford et al. (2025), "A data-driven framework for team selection in Fantasy Premier League"

- **Citation:** arXiv:2505.02170 (2025). [arXiv](https://arxiv.org/abs/2505.02170)
- **Summary:** Recent academic entry formulating squad, bench, and captain choice
  under budget/formation/club-quota constraints as deterministic **and robust**
  mixed-integer programs; objective parameterized by a hybrid of realized points and
  regression predictions; benchmarks cost estimators including recency-weighted
  averages, exponential smoothing, ARIMA, and Monte Carlo simulation across 1–3 GW
  horizons.
- **Method:** Deterministic + robust-optimization MILP variants; comparison of
  forecast feeders.
- **Headline result:** Robust variants hedge low-probability busts at modest EV
  cost; conclusions stable across 1–3 GW horizons; the paper's own framing —
  literature is heavy on prediction, light on selection modelling — matches this
  survey's finding.
- **Transferable: partially.** The robust-MIP idea (optimize against an uncertainty
  set rather than the mean) is a cheap risk-control lever, but with a full Monte
  Carlo engine we can do strictly better via scenario-based/CVaR objectives, so this
  is a fallback formulation, not a target.

---

## Theme 4 — Sequential decisions: transfers, captaincy, chip timing

### Finding: there is no rigorous academic treatment of FPL chip timing

Searches for dynamic-programming or RL treatments of wildcard/bench-boost/triple-
captain/free-hit timing return only community strategy content (e.g.
[Fantasy Football Fix's chip EV analysis](https://www.fantasyfootballfix.com/blog-index/fpl-chip-strategy/) — average gain from good chip timing ≈ **+49 pts/season**,
best case +73). The academic-adjacent state of the art is:

- **Matthews et al. (2012)** (above) — the only formal sequential-decision framing
  of a full FPL season (belief-state MDP), but chips barely feature (the 2010/11
  ruleset had only the wildcard).
- **NTNU thesis (2018)** — chips as binary variables inside the rolling-horizon
  MILP; timing emerges from the optimization rather than being reasoned about.
- **sertalpbilal's MILP** — the most complete chip logic anywhere (WC/FH/BB/TC
  binaries, FT interaction), but still deterministic: chip EV is whatever the
  point-forecast window says, with no option-value/regret treatment.
- **Verdict for our engine: yes — open territory.** A Monte Carlo engine is the
  right tool for the unsolved part: chip timing is an *optimal-stopping* problem
  (hold an option, exercise on a high-EV double gameweek), and simulated
  distributions of future chip EV windows let us price the option properly
  (value of waiting = E[max over remaining windows] vs. exercise now), which no
  published work does. Captaincy per-GW is trivial under EV (argmax EP) but
  non-trivial under rank objectives — see Theme 5.

---

## Theme 5 — Rank-vs-points objectives, variance, and opponent fields

### Hunter, Vielma & Zaman (2016/2019), "Picking Winners in Daily Fantasy Sports Using Integer Programming"

- **Citation:** Hunter, D.S., Vielma, J.P. & Zaman, T. arXiv:1604.01455; MIT Sloan. [arXiv](https://arxiv.org/abs/1604.01455), [PDF](https://juan-pablo-vielma.github.io/publications/Picking-Winners.pdf)
- **Summary:** The founding paper of rank-aware fantasy optimization. In top-heavy
  DFS contests, maximizing mean points is wrong; you maximize P(some entry exceeds
  the winning threshold). They show this is well-approximated by constructing a
  *portfolio of lineups*, each with **maximal mean subject to a minimum-variance
  constraint and maximum-correlation constraints against previously built lineups**
  — i.e. deliberately variance-seeking and mutually diversified. Key empirical
  input: fantasy points of same-team players are strongly positively correlated, so
  "stacking" teammates raises lineup variance cheaply.
- **Method:** Sequential integer programming with mean/variance/correlation
  constraints; order-statistics argument for why max-of-N diversified lineups
  approximates threshold-crossing probability.
- **Headline result:** Real-money DraftKings hockey/baseball entries repeatedly
  placed in the top 10 of large contests.
- **Transferable: yes — directly.** Substitute "lineups" with our decision
  candidates: (1) **captaincy** is a pure variance instrument (doubling one player's
  score) — under a rank objective the right captain maximizes P(beating the field),
  not EP; (2) *stacking* logic maps to our engine natively because our simulations
  already carry the intra-team correlations (D-C scoreline → shared team-goal
  events) that Hunter et al. had to estimate; (3) for cup/head-to-head/mini-league
  contexts, solve max-P(rank threshold) over our simulated joint draws instead of
  max-EV.

### Haugh & Singal (2021), "How to Play Fantasy Sports Strategically (and Win)"

- **Citation:** Haugh, M.B. & Singal, R. (2021). *Management Science*, 67(1), 72–92. [INFORMS](https://pubsonline.informs.org/doi/10.1287/mnsc.2019.3528), [PDF](http://www.columbia.edu/~mh2078/DFS_Revision_1_May2019.pdf)
- **Summary:** The rigorous successor to Picking Winners. Models the *opponent
  field* explicitly: opponents' lineup selections follow a **Dirichlet-multinomial
  generating process estimated via Dirichlet regression** on ownership data; the
  optimal portfolio problem for double-up and top-heavy payoffs then becomes a
  mean-variance-like problem of *outperforming a stochastic benchmark* (the field's
  order statistics), which they solve with binary quadratic programs. Shows the
  value of modelling opponents grows with contest size and payoff top-heaviness.
- **Method:** Dirichlet-multinomial opponent model + moment-based
  order-statistic approximation + sequential BQP portfolio construction; live
  testing on DraftKings NFL contests.
- **Headline result:** Strategic (opponent-aware) portfolios significantly
  outperform opponent-oblivious mean-maximizing portfolios in top-heavy contests;
  framework recovers "be contrarian in big fields, be conventional in cash games"
  as a theorem rather than folklore.
- **Transferable: yes — the theory behind 'effective ownership'.** FPL's community
  EO concept ([Fantasy Football Scout explainer](https://www.fantasyfootballscout.co.uk/2021/03/24/what-is-effective-ownership-and-why-is-it-so-widely-talked-about-in-fpl/)) is exactly Haugh–Singal's stochastic
  benchmark in disguise: a player at 60% EO is 60% "already in the benchmark", so
  owning him hedges rank while a differential moves it. Because FPL publishes
  ownership and captaincy percentages, we can build the field benchmark *directly
  from data* (no Dirichlet regression needed for the top-line version): simulate the
  field's score per our Monte Carlo draw as Σ EOᵢ × simulated-pointsᵢ and optimize
  rank-based objectives (P(green arrow), P(top-10k)) against it.

### NTNU risk constraints (2018) & robust MILP (2025) — see Theme 3

Both find a real risk/reward frontier in FPL selection, mirroring the DFS result:
risk-averse solutions for protecting rank, variance-seeking for chasing it.
**Transferable: yes** — but scenario-based objectives over our simulation draws
dominate both formulations.

---

## Theme 6 — Bonus points (BPS)

### Finding: essentially no academic literature

No paper models the Bonus Point System explicitly. What exists:

- **Rules + mechanism:** BPS is a *deterministic function of Opta event counts*
  ([Premier League explainer](https://www.premierleague.com/en/news/106533)); the 3/2/1 bonus goes to the top-3 BPS scores
  in each match, with tie-sharing rules.
- **Empirical importance:** community analysis ([Fantasy Football Pundit](https://www.fantasyfootballpundit.com/importance-of-bonus-points-fpl/)) shows bonus
  contributes a meaningful share of premium players' totals and is systematically
  skewed (goalscoring defenders and CS+goal midfielders over-collect).
- **Academic models:** OpenFPL and the ML cluster predict *total* points, absorbing
  bonus implicitly; Notelid & Östlund model scoring components but treat bonus
  crudely; commercial models (FPL Review) model bonus internally but unpublished.
- **Transferable: yes — a genuine edge for our architecture.** Because BPS is
  deterministic given events, an event-level Monte Carlo engine can compute bonus
  *exactly per simulation draw*: extend the per-player event simulation to the BPS
  event vocabulary (or a reduced version: goals, assists, CS, cards, saves + a
  calibrated baseline BPS-per-90 by player), apply the BPS formula, take the top-3
  within each simulated match. This captures the crucial *competition* structure
  (your striker's expected bonus depends on who else hauls in the same match) that
  every regression-based model smears out. Nobody has published this; the commercial
  models' unpublished versions are the only competition.

---

## Top 5 adoptable ideas (ranked by expected impact for a Monte-Carlo odds-based engine)

1. **Bolt a rolling-horizon multi-period MILP decision layer onto our EP order
   books** (sertalpbilal's formulation + NTNU's rolling-horizon evidence). Exact FT
   rollover, chips as binaries, price-change-aware budget flow, decay-weighted
   future GWs. Our simulation already produces the objective coefficients; this is
   the shortest path from "projections" to "decisions", and it's the layer where
   the community demonstrably wins. Upgrade path unique to us: replace the scalar
   decay factor with re-solves across Monte Carlo scenario draws (stochastic
   program via scenario sampling).

2. **Rank-based objectives computed on our joint simulation draws** (Hunter–Vielma
   variance/correlation portfolios + Haugh–Singal stochastic-benchmark opponent
   model). Build the field benchmark from published FPL ownership/captaincy (EO),
   score it inside each Monte Carlo draw, and optimize P(beat benchmark) /
   P(top-k) instead of EV where the contest is top-heavy — captaincy and
   differential choice fall out correctly, including "stacking" attackers with
   their own team's clean-sheet assets, whose correlations our D-C engine already
   carries.

3. **Simulate BPS/bonus inside the event simulation** (literature gap — Theme 6).
   Bonus is deterministic given events and competitive within a match; per-draw BPS
   computation with top-3 allocation captures effects (bonus cannibalization
   between teammates, defender-goal bonus skew) that no published regression model
   does. Likely worth 0.2–0.5 EP accuracy on exactly the premium players where
   accuracy matters most.

4. **Adopt the OpenFPL/Ultimate-Truth evaluation harness**: backtest EP by return
   category (Zeros/Blanks/Tickers/Haulers) at 1/2/3-GW horizons against (a) a
   de-vigged-odds-only baseline and (b) a simulated perfect-model noise floor.
   This tells us where remaining edge lives (the literature says: minutes, not
   goal rates) and prevents fitting noise — per-player EP is near its accuracy
   ceiling (~RMSE 2.8), so unbenchmarked "model improvements" are usually fake.

5. **Keep odds-first, add a position-specific stats overlay and a minutes/news
   signal** (Forrest et al., Wunderlich–Memmert, Wilkens; Bonello et al.; OpenFPL).
   The backtest literature is unambiguous that odds beat stats models, validating
   our core pipeline; the marginal value sits in (a) low-score dependence — verify
   our de-vig → D-C step preserves the τ/diagonal-inflation draw correction
   (Dixon–Coles 1997; Karlis–Ntzoufras 2003), since it directly moves clean-sheet
   EP, and (b) player-level residual models for what odds don't price: set-piece
   duty, BPS propensity, and above all appearance probability, the single largest
   error source in every published evaluation.

---

## Quick-reference source list

- Matthews, Ramchurn & Chalkiadakis (2012) — [paper](https://eprints.soton.ac.uk/340382/1/fantasyFootball2012cr.pdf), [Squadguru follow-up](https://ecs.soton.ac.uk/news/4915), [BBC coverage](https://feeds.bbci.co.uk/news/technology-40905913)
- Dixon & Coles (1997) — [JRSS-C](https://rss.onlinelibrary.wiley.com/doi/abs/10.1111/1467-9876.00065)
- Karlis & Ntzoufras (2003) — [PDF](http://www2.stat-athens.aueb.gr/~jbn/papers2/08_Karlis_Ntzoufras_2003_RSSD.pdf)
- Boshnakov, Kharrat & McHale (2017) — [PDF](https://blogs.salford.ac.uk/business-school/wp-content/uploads/sites/7/2016/09/paper.pdf)
- Forrest, Goddard & Simmons (2005) — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S016920700400010X)
- Spann & Skiera (2009) — [Academia](https://www.academia.edu/2549746/Sports_forecasting_a_comparison_of_the_forecast_accuracy_of_prediction_markets_betting_odds_and_tipsters)
- Wunderlich & Memmert (2018) — [PLOS One](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0198668)
- Wilkens (2026) — [SAGE](https://journals.sagepub.com/doi/10.1177/22150218261416681)
- Groos (2025), OpenFPL — [arXiv:2508.09992](https://arxiv.org/abs/2508.09992)
- Bonello et al. (2019) — [arXiv:1912.07441](https://arxiv.org/pdf/1912.07441)
- Gupta (2019) — [arXiv:1909.12938](https://arxiv.org/abs/1909.12938)
- IEEE ML-for-FPL (2022) — [IEEE Xplore](https://ieeexplore.ieee.org/document/9909447/)
- Deep/transfer learning for EPL forecasting — [arXiv:2405.02412](https://arxiv.org/pdf/2405.02412)
- Notelid & Östlund (2025), Uppsala thesis — [PDF](https://uu.diva-portal.org/smash/get/diva2:1972615/FULLTEXT02.pdf)
- Kristiansen, Gupta & Eilertsen (2018), NTNU — [NTNU Open](https://ntnuopen.ntnu.no/ntnu-xmlui/handle/11250/2577003)
- Çay, FPL Optimization Tools — [GitHub](https://github.com/sertalpbilal/FPL-Optimization-Tools/blob/main/src/multi_period.py), [open-fpl-solver](https://github.com/solioanalytics/open-fpl-solver), [hindsight optimization](https://alpscode.com/blog/hindsight-optimization/)
- AIrsenal — [GitHub](https://github.com/alan-turing-institute/AIrsenal)
- Data-driven FPL selection (2025) — [arXiv:2505.02170](https://arxiv.org/abs/2505.02170)
- Hunter, Vielma & Zaman — [arXiv:1604.01455](https://arxiv.org/abs/1604.01455)
- Haugh & Singal (2021) — [Management Science](https://pubsonline.informs.org/doi/10.1287/mnsc.2019.3528)
- FPL Review, Ultimate Truth — [article](https://fplreview.com/ultimate-truth-how-fpl-models-perform-relative-to-a-perfect-model/)
- FPL Pulse model notes — [blog](https://www.fplpulse.com/blog/fpl-predicted-points-model)
- BPS mechanics — [Premier League](https://www.premierleague.com/en/news/106533); bonus importance — [Fantasy Football Pundit](https://www.fantasyfootballpundit.com/importance-of-bonus-points-fpl/)
- Chip-timing EV (community) — [Fantasy Football Fix](https://www.fantasyfootballfix.com/blog-index/fpl-chip-strategy/)
- Effective ownership — [Fantasy Football Scout](https://www.fantasyfootballscout.co.uk/2021/03/24/what-is-effective-ownership-and-why-is-it-so-widely-talked-about-in-fpl/)
