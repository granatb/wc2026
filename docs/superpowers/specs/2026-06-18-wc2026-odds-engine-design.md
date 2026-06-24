# wc2026 — Odds-driven engine + research layer + chat interface

**Date:** 2026-06-18
**Status:** Approved (design)
**Supersedes:** the estimate-only Layer-1 engine in the initial scaffold.

## 1. Purpose

Upgrade the five-game wc2026 decision engine from hand-estimated team lambdas to
**market-derived** probabilities (bookmaker odds, including deep player-prop markets),
overlaid with **expert/research knowledge** via a tunable per-game blend. Keep one
shared Monte Carlo substrate; keep the games thin. Drive it chat-first.

## 2. Core design decision: odds × expert blend

Two kinds of non-market input, handled differently:

- **Hard facts** — ruled out, suspended, confirmed benched. These are **absolute**:
  they override the market unconditionally (a player who is out has rate `0`,
  `start_prob = 0`), regardless of any weight.
- **Soft reads** — form, matchup, motivation, dead-rubber rotation risk, contrarian
  ceiling. These are scaled by a per-game **`research_weight w ∈ [0,1]`**:
  - Match goals:   `λ_eff = λ_odds × (1 + w·(lambda_multiplier − 1))`
  - Player rates:  `rate_eff = (1 − w)·rate_odds + w·rate_expert`
  - Start prob:    blended the same way unless a hard status flag pins it.

`w = 0` ⇒ pure odds. `w = 1` ⇒ full expert overlay.

### Default weights (per game)

| Game | `w` | Posture |
|---|---|---|
| Målspillet | 0.05 | Odds-only; also cross-check the correct-score market. |
| GOLD (Alwaysss 2nd) | 0.10 | Near-pure odds, chalk EV-max. |
| FREE (Always 2nd) | 0.25 | Odds-driven discipline — only 3 transfers. |
| FIFA (Granat65) | 0.30 | Balanced. |
| YOLO (Always 2nd 2) | 0.50 | Heaviest expert overlay **and** a ceiling (high-percentile) objective. |

Rejected alternatives: pure hard-override (too blunt for variance plays); full
Bayesian prior-update (more principled but heavier to reason about round-to-round).
The weighted blend + absolute-hard-facts split captures most of the benefit with a
dial the operator can feel.

## 3. Data sources

### 3.1 The Odds API (`core/odds.py`)
- Sport key: `soccer_fifa_world_cup`. Auth via `ODDS_API_KEY` env var.
- Markets pulled per match: `h2h` (1X2), `totals` (O/U lines), and player props where
  offered (`player_goal_scorer_anytime`, `player_shots_on_target`, `player_assists`,
  team `clean_sheet`), plus `correct_score` for Målspillet cross-check.
- **De-vig**: decimal odds → implied prob → normalise out the overround (proportional
  method; document the choice).
- **Lambda solver**: find `(λ_home, λ_away)` for an independent/bivariate Poisson whose
  implied 1X2 and expected total best match the de-vigged market (numeric solve /
  least-squares over the small goal grid).
- **Player rates from props**: `P(anytime scorer)` → goal rate `λ_p = −ln(1 − p)`;
  SoT and assist props → per-90 rates. These seed per-player Poisson directly.
- **Caching**: raw responses and derived quantities written to `data/odds/<match_id>.json`
  with a fetch timestamp; the engine reads cache and only re-fetches on demand (respect
  free-tier rate limits, keep runs reproducible).

### 3.2 Fixtures / lineups (`core/schedule_api.py`)
- api-football (API-Sports). Auth via `API_FOOTBALL_KEY`.
- Pulls the schedule (teams, kickoff datetimes UTC, stage), and where available
  predicted/confirmed lineups + recent minutes. Writes `data/schedule.json`; `fixtures.py`
  loads from it (no hardcoded fixtures).

## 4. Research / memory layer

- Directory: `research/teams/`, `research/players/`, `research/matches/`.
- One markdown file per entity. YAML frontmatter holds machine-readable fields; the body
  holds cited prose (web articles, analyses, Reddit threads).

```yaml
---
entity: player            # player | team | match
name: Erling Haaland
status: nailed            # nailed | rotation_risk | doubtful | out | suspended
start_prob_override: null # absolute override when not null
lambda_multiplier: 1.0    # soft team/player attack adjustment (1.0 = neutral)
sources:
  - https://...
updated: 2026-06-18
---
Prose: why. Citations inline.
```

- `core/research.py` loads these, separates **hard** (`status ∈ {out, suspended}` or a
  non-null `start_prob_override`) from **soft** (`lambda_multiplier`, soft status), and
  applies them per the blend rules in §2 using the active game's `w`.
- Populated by the operator (Claude) via web + Reddit research at decision time; persists
  as a versioned memory layer in the repo.

## 5. Engine changes (`core/engine_events.py`)

- Per match, draw `(home_goals, away_goals)` from blended `(λ_home, λ_away)` — preserves
  the correlated team-goal backbone for clean sheets, scorelines, results, Målspillet.
- Player goals: where market player-rates exist, draw each player's goals from his own
  blended rate and reconcile to the team total; where they don't, fall back to the
  goal-share multinomial distribution of the team total (current behaviour).
- Everything else (assists, SoT, CS, cards, minutes, MOTM, saves) unchanged in shape,
  fed by blended rates where props exist.
- Output API (`simulate_round`, `PlayerSample`, `MatchSample`) is unchanged so the game
  models keep working.

## 6. Game model changes

- **Config**: each game's `state.json` gains a `research_weight` (defaults per §2) so the
  blend is per-game and editable.
- **YOLO** (`holdet_yolo/model.py`): objective becomes a **high-percentile** of the
  growth distribution (e.g. P85–P90 from `PlayerSample.goal_samples` / per-sim growth),
  not the mean — actively rewards ceiling/variance. Captain chosen on ceiling.
- **GOLD/FREE/FIFA/Målspillet**: unchanged logic, now fed by blended market numbers.
- **Målspillet**: primary scoreline still from the joint Poisson of blended λ; additionally
  cross-checked against the `correct_score` market when present.

## 7. Interface (chat-first)

Repo stays a deterministic library + CLI (`manage.py`). Claude is the operator. Per round:

1. Refresh odds (`odds.py`) + schedule (`schedule_api.py`).
2. Web/Reddit research → update `research/*.md`.
3. Run each game's model (`manage.py <game> --round N`).
4. Translate order books into plain-language decisions + rationale.
5. Operator executes in each app; Claude writes the result back into `state.json`.

No standalone REPL (YAGNI).

## 8. Secrets & config

- `ODDS_API_KEY`, `API_FOOTBALL_KEY` read from environment / `.env` (gitignored if/when a
  repo is initialised). Never written to state or committed. A `.env.example` documents
  the required vars.

## 9. File-level impact

New: `core/odds.py`, `core/schedule_api.py`, `core/research.py`, `core/blend.py`
(blend math, isolated + unit-tested), `research/` tree, `data/` cache dir, `.env.example`,
`tests/` for the offline-testable math.
Modified: `core/engine_events.py`, `core/fixtures.py` (load from `data/schedule.json`),
`core/ratings.py` (priors become the expert fallback, not the primary source), all five
`games/*/model.py` + `state.json` (add `research_weight`; YOLO objective), `manage.py`
(refresh hooks), `README.md`.

## 10. Testing

- Pure-math units are network-free and TDD'd: de-vig, λ-solver round-trips (recover λ from
  odds generated by a known λ), player-prop→rate conversion, blend formulas (w=0 ⇒ odds,
  w=1 ⇒ expert, hard-facts absolute), YOLO percentile objective.
- API clients tested against cached/fixture JSON, not the live network.

## 11. Out of scope (for now)

Standalone chat REPL; auto-execution into the fantasy apps; non-WC competitions;
historical backtesting harness (candidate for a later spec).
