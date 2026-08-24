# wc2026

Local decision engine for 5 fantasy competitions over the 2026 FIFA World Cup.

> Recent engine/model/app changes are logged in [CHANGELOG.md](CHANGELOG.md).

All five games share **one** Monte Carlo substrate (`core/engine_events.py`) fed by
**market-derived** probabilities from the **free ESPN hidden API** (`core/espn.py` —
schedule + 1X2/totals + anytime-goal props, no key), with a **research/expert overlay**
(`core/research.py`) blended per-game by a tunable weight. Match odds become
Dixon-Coles scoreline distributions; each game is a thin layer that maps simulated
events onto its own rules and emits an **order book**.

Data source: **ESPN** (free, no key, single book = DraftKings). `core/odds.py`
(The Odds API) + `core/schedule_api.py` (api-football) remain as documented,
key-based alternatives but are not the default.

## Layout

```
wc2026/
  core/
    blend.py           # odds x expert blend math (the per-game `w` dial)
    odds_math.py       # de-vig, lambda-solver, Dixon-Coles, prop->rate (pure, tested)
    espn.py            # ESPN hidden-API client: scoreboard + props -> data/ (DEFAULT)
    odds.py            # The Odds API client (alternative, key-based)
    schedule_api.py    # api-football client (alternative, key-based)
    fixtures.py        # schedule + per-match lambdas (loads data/schedule.json)
    ratings.py         # priors = the EXPERT FALLBACK when no market rate
    research.py        # markdown memory layer -> overrides via blend rules
    engine_events.py   # Layer-1 Monte Carlo (shared by ALL games)
  games/
    fifa/ holdet_gold/ holdet_yolo/ holdet_free/ malspillet/
      rules.md state.json model.py
    holdet_common.py   # shared kr scoring + trade rule (no per-script copies)
  research/{teams,players,matches}/   # research notes (frontmatter + prose)
  data/                # cache: odds/, schedule.json (gitignored)
  manage.py            # CLI dispatcher + --refresh
  docs/superpowers/    # design spec + implementation plan
```

## Setup

No keys needed for the default ESPN path. (`.env.example` documents `ODDS_API_KEY` /
`API_FOOTBALL_KEY` only if you switch to the alternative providers.)

## Usage

```bash
python manage.py all --round 2 --refresh         # ESPN: schedule + match odds, run every game
python manage.py malspillet --round 2 --refresh  # Dixon-Coles scorelines from live odds
python manage.py holdet_gold --round 2           # run off cached data (no fetch)
python manage.py fifa --round 2 --refresh --props # also fetch anytime-goal player props (slower)
```

`--refresh` pulls the round's ESPN scoreboard → schedule + Dixon-Coles match odds into
`data/`. `--props` additionally fetches anytime-goal player odds (resolves ~1000 athlete
names, cached to `data/athletes.json`; only matters once player priors are populated).
Without `--refresh`, models run off whatever is cached (reproducible, offline). Knockout
matches have no odds until teams are set — those fall back to `ratings.py` priors.

### Site build (evmax)

```bash
python3 -m evmax.build --round 8 --no-llm   # World Cup round into dist/round/8/
python3 -m evmax.build --gw 1 --no-llm      # FPL gameweek into dist/fpl/gw1/
```

`--gw` builds the eight FPL articles (our-squad, captains, consensus-squad,
wildcard, ticker, defenders, efficiency, defcon) plus the JSON/markdown twins and
agent files. `/` serves the current FPL gameweek; the World Cup tree under
`/round/N/` stays live and untouched (its landing is at `/round/8/`). Drop
`--no-llm` to enable the LLM prose tier (needs `ANTHROPIC_API_KEY`); either way
the hand-written templates and any cached prose in `data/articles/` keep the
pages publishable. `--no-cache` (FPL only) forces a fresh simulation past the
sim cache.

### In-gameweek routine (the FPL live duel)

While a gameweek runs, refresh live points + rebuild + deploy after each match
day (manual for now; a cron wrapper can come later):

```bash
python3 -m evmax.build --gw 2 --live && scripts/deploy.sh
```

`--live` fetches the official live feed (`event/{gw}/live/` +
`fixtures/?event={gw}`) into `data/fpl/live_gw{N}.json` (always overwritten — a
convenience, not a record) and renders the reality layer: the landing duel strip
gains each squad's realized total ("44 so far · 1 to play") next to the frozen
projections, and both squad pages get a realized table above the frozen prose,
stamped with the fetch time. Article bodies (HTML/JSON/md) stay frozen — the
freeze is test-enforced. Without the flag the layer is automatic mid-gameweek
from the cached payload only (no network); `--no-live` forces it off. A squad
name the season has renamed is bridged by the state file's `aliases` map
(validated); an unresolved name kills the build rather than publishing a
14-man total.

Before the GW2 deadline (one-off): rebuild the consensus squad from actual
ownership — its declared Wildcard, retiring the GW1 expert mention-tally:

```bash
python3 -c "from core import fpl_api; fpl_api.refresh()"   # current ownership first
python3 -m evmax.build --gw 2 --reset-consensus    # rewrites games/fpl/state_consensus.json
# review the diff, then build + deploy as usual
```

### Weekly runbooks (FPL — the credibility engine)

The weekly routine is fully documented, command by command, in
[docs/runbooks/thursday-pre-deadline.md](docs/runbooks/thursday-pre-deadline.md)
(refresh → feed diff → red-flag research → notes → re-sim → transfers → the
publish gate → build --live → deploy → post drafts → owner summary) and
[docs/runbooks/monday-post-gw.md](docs/runbooks/monday-post-gw.md) (grade the
gameweek → duel + vs-average scoreboard → scorecard draft → transfer preview →
season-learnings entry). Sessions are manual by owner decision; each runbook
ends with the parked schedule-it-later incantations. The standing pieces:

```bash
python3 -m core.fpl_diff                            # feed churn since last week
python3 manage.py fpl --round 2 --transfers         # weekly swap table, both squads
python3 scripts/grade_gw.py --gw 1 --refresh        # bank the accuracy JSON post-GW
```

The build itself enforces the knowledge layer: every published player gets a
dossier (status, minutes source, club/name drift, transfer-out spikes) and a
red dossier **aborts the build** unless a sourced, dated research note under
`research/players/` overrides it. Mistakes and their structural fixes are
logged append-only in
[docs/research/season-learnings.md](docs/research/season-learnings.md).

## Dashboard (Streamlit)

A local web UI over the engine — squads + EVs + captain per game, the Målspillet board,
a probe-a-change EV tool, and the schedule with scraped odds + the "why" behind each
number. Editable values save back to `state.json`.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Sidebar: pick the round, sim count, refresh ESPN odds, and navigate. The engine
(`core/`, `games/`) stays pure stdlib; only the dashboard needs `streamlit`.

## The odds × expert blend

**All tunables live in one place — [`config.py`](config.py).** View it any time with
`python manage.py config`. `state.json` files hold only squad snapshots; behaviour
(blend weights, objective, sims, margins, priors) is in `config.py`.

Numbers are market-derived, then nudged by research scaled by a per-game weight `w`.
Hard facts (out/suspended) are absolute and ignore `w`; soft reads (form, rotation,
ceiling) scale with it.

| Game | `w` | Posture |
|---|---|---|
| Målspillet | 0.05 | odds-only |
| GOLD (Alwaysss 2nd) | 0.10 | near-pure odds, chalk EV-max |
| FREE (Always 2nd) | 0.25 | odds-driven discipline (3 transfers total) |
| FIFA (Granat65) | 0.30 | balanced |
| YOLO (Always 2nd 2) | 0.50 | heaviest overlay + **ceiling** (P85) objective |

## Data flow

```
The Odds API ─┐                          research/*.md ─┐
              ├─> odds_math ─> lambdas ──┐               ├─> blend (per-game w)
api-football ─┘   (de-vig, solve)        ├──> engine_events ──> per-player samples
                  player props ──────────┘        │              + scoreline dist
                                                   v
                       fifa / holdet_* / malspillet models ──> order book
```

## Research layer

One markdown file per entity under `research/`, with frontmatter the loader reads:

```yaml
---
entity: player
name: Erling Haaland
status: nailed            # nailed|rotation_risk|doubtful|out|suspended
start_prob_override: null # absolute when set
lambda_multiplier: 1.0    # soft nudge, scaled by w
sources: [https://...]
updated: 2026-06-18
---
reasoning + citations
```

## Interface

Chat-first: you ask, Claude refreshes odds, updates research notes, runs the models, and
translates each order book into plain decisions; you execute in the apps and Claude writes
the result back to `state.json`. The repo stays a deterministic CLI underneath.

## Tests

```bash
python -m unittest discover -s tests -t .
```

Pure-math + loader logic is unit-tested offline; API clients are tested against fixture
JSON (no live network).
