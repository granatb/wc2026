# Changelog

Engine / model / app changes, newest first. Verification: `python3 -m unittest discover -s tests`
(44 tests). App: `streamlit run app.py`.

## 2026-06-24 — R3 prep

- **R3 news research pass** — 23-team parallel web-research workflow (qualification/rotation,
  injuries, pens, differentials). Full findings saved under
  [research/rounds/](research/rounds/README.md) (digest + raw JSON, 154 sources). Actionable
  flags written to `research/players/*.md` as `round: 3`. Headline: Germany/England/Argentina/
  Mexico/USA rotating (qualified → resting); Raphinha OUT; safe blowouts to target =
  Morocco / Ivory Coast / Senegal / Belgium / Netherlands.
- **YOLO anti-chalk dial** — `config.YOLO_FADE` (ownership-leverage tilt; default 0.5).
- Confirmed chip plan (FIFA): Maximum Captain in R3 (chaotic slate); save Wildcard +
  Qualification + Mystery for R32.

## 2026-06-22 — Pre-R3 hardening

### Scoring fidelity (confirmed from in-app tables)
- **FIFA** (`games/fifa/model.py`) — corrected to the official 2026 "How to score" table:
  goals **GK 9 / DEF 7 / MID 6 / FWD 5**, clean sheet GK/DEF **5** (MID 1), red **−2**,
  conceded **−1 per goal after the first** (GK/DEF), GK **+1/3 saves**, FWD **+1/2 SoT**,
  MID **+1/3 tackles & +1/2 chances**, assist +3, appearance +1/+2, scouting **+2 when
  pts > 4 and < 5% owned**. Removed two wrong guesses: **no Player-of-the-Match** and
  **no DEF tackle/CBI points** in this game. See `games/fifa/rules.md`.
  - Scouting bonus is now a proper EV (`scouting_ev` = +2 × P(match pts > 4)), not a flat +2.
  - MID tackles/chances are **role-shaped** by the player's goal/assist share (attacking
    mids tackle less / create more; defensive mids the reverse), total ~calibrated.
- **Holdet** (`games/holdet_common.py`) — kr table verified exact against the in-app
  Pointsystem. Enabled the two dormant terms: **hat-trick** (P(goals≥3)) and **MOTM**
  (the engine never actually sampled MOTM before — fixed). Added **decisive scoring**
  (scoring til sejr +40k / uafgjort +20k): one winning/equalising goal per match credited
  to a scorer. Still unmodeled (rare): own goal, missed pen, pen save, shootout.

### Engine (`core/engine_events.py`)
- **MOTM now sampled** (one per match, contribution + result-weighted) — was hardcoded 0,
  silently breaking MOTM in both games.
- **Goals conceded** tracked (`conc_beyond`) for the GK/DEF −1-per-extra-goal rule.
- **Decisive-goal** tracking (`decisive_win` / `decisive_draw`).
- **Goal concentration dial** `config.GOAL_CONCENTRATION` (γ): sharpens the within-team
  goal split toward higher-share players while preserving team totals. Tuned to **1.2**
  (1.6 over-inflated elite strikers once true scoring values were in).
- **Penalty uplift** `config.PEN_TAKER_GOAL_BONUS` (0.10) applied to marked pen-takers.
- `goal_share` / `assist_share` carried into `event_means` (role signal for downstream scoring).

### Full-board evaluation (`core/ratings.py`)
- The engine scored only 84 hand-set players; `players.json` has ~1530. For the knapsack
  this was crippling (cheap value picks invisible). Now `players_for_team` **derives a
  prior** (goal/assist share + start-prob) for any player from **position + price** (quality
  vs the position's median), **budget-normalised per team** so derived players fill only the
  residual share hand-set priors leave — stars are NOT diluted (Oyarzabal R2 ceiling held
  ~350k). Capped at `_DERIVE_CAP` (16) players/team. Result: **84 → ~750 scored** (~13s @10k sims).
- **Deduped 4 phantom priors** (same real player entered under two name variants:
  Oyarzabal, Musiala, Wirtz, Rangel) by canonical identity.
- **Pen-takers derived** for teams with none marked (top attacker) — now 48/48 teams covered.
- **Team-name normalisation** USA→United States, Côte d'Ivoire→Ivory Coast (in
  `build_players.py` + a one-time `players.json` remap) — those 59 players were invisible.
- `clear_prior_cache()` called on player re-sync.

### Data integrity (`core/espn.py`, `manage.py`)
- **Closing-odds preservation**: `save_match_odds` no longer overwrites a good pre-match line
  with the empty fallback when ESPN drops odds at kickoff. It merges, keeps the last-seen
  ("closing") lambdas (flagged `odds_status: "closing"`, stamped `odds_captured_at`), and
  still updates the actual result. `manage.refresh` feeds the preserved line back into the
  schedule. This was actively destroying data (e.g. Spain's R2 odds → priors, halving
  Oyarzabal's ceiling). Regression test in `tests/test_espn.py`.
- **Player props fetched** for R3 (735 market goal-rates) — who-scores is now book-anchored
  (~70% market for FIFA at w=0.30). `manage.refresh --props`.

### Research layer (`core/research.py`)
- **Round-scoped notes**: a `round:` frontmatter field; `load_entries(kind, fantasy_round)`
  drops notes pinned to a different round, so R3 rotation flags no longer leak into the
  R2 (or knockout) sim. R3 rotation notes tagged `round: 3`, Montes suspension `round: 2`.

### App / UX (`app.py`)
- Dashboard cards: **EV / Ceiling read as a vertical grid** (Round → so-far → actual),
  captain demoted to a caption, **green/red colored delta** vs the played-EV base.
- **FIFA ceiling** added (goal-variance, mirrors Holdet) — FIFA cards now show a Ceiling column.
- **Fixture-coverage panel** ("are we in the blowouts?"): the round's fixtures ranked by the
  favourite's xG with our exposure count, red-flagging any uncovered λ≥2.0 blowout.

### Findings / lessons (saved to memory)
- Engine ran ~2.3 pts under Rotowire on FIFA before the scoring fix; after correct values +
  γ=1.2, R2 mean ratio ~0.85–0.90, rank-corr ~0.6.
- **Målspillet: no blanket X-0** — use the per-match Dixon-Coles pick (X-1 when the underdog's
  xG ≈ 1). A blanket X-0 rec cost ~2 pts in R2 (Germany, Netherlands).
- **Blowout coverage > over-concentration** — R2 had 0 France (λ3.25, the biggest fixture) but
  11 Spain slots. Cover the top-λ fixtures before deepening an already-covered team.

### Deferred (intentionally)
- **Backtest** — closing odds + results are being captured; tool to grade the model is on hold
  until a few more rounds bank data.
- **Workers research pass** — fan-out agents to verify the R3 shortlist (starting / on pens /
  fit). Best run once R2 concludes and R3 squads are chosen, so it targets real candidates.

### Known caveats
- Derived start-probs are price-rank proxies (the workers pass refines the ones that matter).
- Tackle/chance/MOTM/decisive rates and the derived-prior budget (1.10) / cap (16) are
  reasonable but uncalibrated (needs the backtest).
- ~790 deep-bench players (beyond the per-team cap) remain unscored — unpickable depth.
- A few players fall back to prior where prop name-resolution misses.
- Knockout rounds (R4+) untested.
