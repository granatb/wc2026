# FPL port — design

**Date:** 2026-07-28
**Deadline:** GW1 lock, `2026-08-21T17:30:00Z` (24 days out)
**Vault MOC:** `~/personal/vault/10 Projects/FPL Adaptation/FPL Adaptation.md`

## 1. Goal

Port the wc2026 engine to Fantasy Premier League. The **public evmax site is the
deliverable**; the private order book (`games/fpl/`) is the instrument the owner uses to
validate the model by playing the game himself and grading it against reality.

Six articles ship for GW1. The engine's Monte-Carlo substrate is reused unchanged; the
player-rate layer inverts from market-derived to xG-derived.

## 2. Decisions

| # | Decision |
|---|---|
| D1 | **Approach A** — new `games/fpl/` module + narrow generalisation of `core/`. Rejected: a full league-adapter refactor (too risky in 24 days, breaks the WC track-record grading) and a forked repo (divergent copies of the engine, contradicts one-engine-many-games). |
| D2 | Public site is the deliverable; the order book is a validation instrument, not a product surface. Consequence: no full 38-GW transfer-path optimiser. |
| D3 | Sequencing: **incremental sim caching ships before GW1; the templating refactor is deferred to the September international break** (GW5→GW6, 18 Sep → 10 Oct). Rationale: GW1 is the year's largest FPL search peak and the refactor adds no reader-visible feature. Deferral is cheap because the article set will change after contact with real FPL queries. |
| D4 | GW1 content set = 5 core ports + **DefCon leaders** as the differentiator. |
| D5 | URL namespace `/fpl/gw{N}/`. The WC tree at `/round/N/` is untouched and stays live forever (§5.6 commitment). |
| D6 | Derived-only rule (§4.1) **permits FPL's own public fields** — price, ownership, availability. Owner ruling 07-28: "we permit whatever makes it better." The rule was written for bookmaker data; FPL price/ownership is the game's own published data and the efficiency article is inherently price-denominated. Never naming upstream *odds* sources still stands. |
| D7 | **No Reddit read path.** Reddit is unreachable from this toolchain (UA-blocked on direct fetch, refused by WebFetch/WebSearch, blocked by browser policy). Replaced by a per-GW web-search research pass over FPL portals, reusing the `research/rounds/` + `core/research.py` convention from the WC. §8's "never covert automation" rule governs posting and remains fully intact. |

## 3. What the research established

Verified 2026-07-28 against `bootstrap-static` and the official rules page. Full verbatim
capture lands in `games/fpl/rules.md`.

### Scoring (official)

| Action | Points |
|---|---|
| Playing up to 60 min / 60+ min | 1 / 2 |
| Goal — GK / DEF / MID / FWD | **10** / 6 / 5 / 4 |
| Assist | 3 |
| Clean sheet — GK,DEF / MID | 4 / 1 |
| **Every 3 shot saves (GK)** | **1** |
| DefCon — DEF ≥10 CBIT / MID+FWD ≥12 CBIRT | 2 (capped) |
| Penalty save / miss | 5 / −2 |
| Bonus | 1–3 |
| **Every 2 goals conceded (GK, DEF)** | **−1** |
| Yellow / red / own goal | −1 / −3 / −2 |

Both divisors are confirmed from the official page, not inferred. `game_config.scoring`
carries unit values only (`saves: 1`, `goals_conceded: -1`) and would mislead if read
literally.

### Rules mechanics

- Squad 15, XI 11, max 3 per club, £100.0m (`squad_total_spend` 1000, currency ×10)
- Chips: two sets — wildcard/freehit GW2–19 and GW20–38; bench boost/triple captain GW1–19 and GW20–38
- Bank up to 5 free transfers (`max_extra_free_transfers` 4); 50% sell-on fee
- **No manager element type** → the Assistant Manager chip is gone
- BPS reworked for 2026/27: the −1 for *being* tackled is removed (a successful tackle still earns +2), CBI drops to 1 BPS per 3, GK saves 2 each +1 inside box +1 big chance, penalty save 7

### Data availability

- **ESPN `eng.1` works** — moneyline + draw + totals already live for GW1, plus a `Team Clean Sheet` market that prices clean sheets better than deriving them from λ.
- **Zero player-level props.** All 172 prop markets on a sampled GW1 fixture are match-level; no athlete refs at all. The WC's player-differentiation path (`espn.load_player_rates`) will be empty at build time. Re-test nearer a deadline, but do not design around it.
- **FPL's API compensates.** 105 fields per player, and bootstrap already carries *last season's* totals and per-90 rates — so there is no cold start for established players. Also `penalties_order`, set-piece order, `status` / `chance_of_playing_next_round`, injury news, ownership, and `ep_next` (FPL's own projection — a public benchmark to grade against).
- All 380 fixtures are currently 10-per-GW with **no blanks or doubles**; those emerge in-season from cup progression, so the handling must be correct before any live data exhibits it.

### Season context affecting priors

Salah has left the league entirely (absent from the API — several press summaries still
price him, which is a live example of why the feed is authoritative and article-derived
data is not). Eight new managers, three British-record transfers, COV/HUL/IPS promoted.
Last-season per-90 rates are weaker priors than in a normal season.

## 4. Architecture

### New files

| File | Purpose |
|---|---|
| `core/fpl_api.py` | Network + pure parsers for `bootstrap-static`, `fixtures`, `element-summary`. Caches to `data/fpl/`. Mirrors `core/espn.py`: network isolated, `parse_*` pure and fixture-tested. |
| `core/fpl_priors.py` | The single place FPL data becomes `ratings.PlayerPrior`. Owns the minutes model and per-90 rate derivation. |
| `games/fpl/model.py` | Scoring + order book. Mirrors `games/fifa/model.py`. |
| `games/fpl/rules.md` | Scoring + BPS tables verbatim, **with provenance per row** — API, official page, or assumption. |
| `games/fpl/state.json` | Owner's squad snapshot. |
| `core/simcache.py` | Sim-artifact cache (§6). |

### Changed, surgically

- `core/engine_events.py` — three additions, detailed in §4.1. Larger than first estimated: the original plan of "one priors parameter" cannot support §7.2's threshold scoring or §7.3's bonus model.
- `core/espn.py` — parameterise the league slug (`fifa.world` → configurable); replace the hand-maintained `ROUND_DATES` with a per-league date resolver, since FPL dates come from its own fixtures feed.
- `core/fixtures.py` — gameweek semantics (§5).
- `core/ratings.py` — `PlayerPrior` gains `defcon_per90` and `saves_per90`, defaults 0, non-breaking.
- `config.py` — `GAMES["fpl"]` entry plus FPL dials (prior-shrinkage rate, DefCon calibration).
- `manage.py` — add `fpl` to `GAMES`, add its refresh path.

### Untouched

`core/odds_math.py`, `core/blend.py`, `core/research.py`, and every WC game model. This is
deliberate: the `/track-record/` page keeps grading WC history off unchanged code, and the
existing suite passing is the regression gate.

### 4.1 The `engine_events` extension

Discovered while reading the sim loop for the implementation plan. All three changes are
additive and leave WC behaviour byte-identical; the guiding principle is **the engine samples
raw events, games apply their own rules to them.**

**(a) Priors provider.** A `priors` parameter defaulting to `ratings.players_for_team`.
`simulate_round` currently calls it at line 240, *inside* the per-sim loop — resolve once
outside and pass the resolved squads down.

**(b) Four additive `PlayerSample` fields.** Each exists because a WC-shaped field cannot be
remapped to FPL's rule:

| Field | Why |
|---|---|
| `conceded` | `conc_beyond` stores `max(0, ga − 1)` — FIFA's rule. FPL needs `floor(ga / 2)`, not derivable from it. Store the raw count; let each game map it. |
| `played_60` | FPL pays 1 point under 60 minutes and 2 at 60+. Minutes are sampled per sim (line 254) but only the total is kept, so `P(60+)` is unrecoverable. |
| `save_samples` | `E[floor(saves/3)] ≠ floor(E[saves]/3)`. GK only, so the memory cost is ~20 players. |
| `defcon_samples` | DefCon is a threshold crossing, not a rate. A mean count cannot yield `P(count ≥ 10)`. Only populated when `defcon_per90 > 0`. |

**(c) A per-match per-sim hook.** `per_match_hook(match_id, rows)` called once per match per
sim, where `rows` is a list of cheap tuples — `(name, position, goals, assists, minutes,
clean_sheet, conceded, saves, yellow, red)` — for all players on both sides.

This exists solely because bonus is a **rank-within-match** quantity (§7.3). It depends on
all 22 players' events within a single sim of a single match, which no per-player accumulator
can reconstruct. The alternatives were rejected: computing bonus post-hoc from marginals
destroys the rank correlation that is the entire point, and giving the FPL model its own sim
loop duplicates the engine.

The engine stays game-agnostic — it passes raw events to a callback and knows nothing about
BPS. `None` by default, so WC runs are unaffected.

**Performance note.** The hook fires `sims × matches` times (500k at 50k sims over 10
fixtures), each call sorting 22 rows. If this proves slow, bonus tolerates a lower sim count
than the rest of the model — it is a small share of total points and does not need 50k
precision. A `config.BONUS_SIMS` dial is the mitigation; measure before reaching for it.

### Module boundaries

- `fpl_api` — "give me the raw FPL feed, cached." Knows nothing of priors or scoring.
- `fpl_priors` — "give me `PlayerPrior`s for gameweek N." Knows FPL field names and the minutes model. Knows nothing of scoring or the site.
- `games/fpl/model` — "map simulated events to FPL points, emit an order book." Knows the scoring table. Never touches HTTP.

## 5. Gameweek semantics

`Fixture` already carries `fantasy_round`, `stage` and `kickoff`. FPL reuses them:
`fantasy_round` = GW id, `stage` = `"GW"`, `neutral=False` always (home advantage is real,
unlike WC neutral venues). Two behaviour changes:

1. **Blanks and doubles.** A team can appear 0 or 2 times in a gameweek. `fixtures_for_team`
   already returns a list, but callers indexing `kos[0]` break on both cases — two exist in
   `games/fifa/model.py` (lines 147, 160) and the FPL model must not repeat the pattern.
2. **`round_lock_time` becomes the FPL deadline, not first kickoff.** For GW1 the deadline
   is 17:30 UTC and first kickoff is later that evening. The frozen-at-lock rule (07-04
   decision) depends on using the deadline.

**Deadlines are read from the API in UTC.** The official rules page renders them in the
viewer's local timezone — it showed GW1 as "Fri 21 Aug 19:30" (CEST) against the API's
`17:30Z`. Never scrape deadlines.

## 6. Sim caching

Cache key = hash over everything determining sim output:

- the odds cache for that GW's fixtures
- the priors snapshot
- research entries for that GW
- sim-affecting config (`GOAL_CONCENTRATION`, `PEN_TAKER_GOAL_BONUS`, `DEFAULT_SIMS`, seed, de-vig method)
- **a fingerprint of the model source** — `core/engine_events.py`, `core/fpl_priors.py`, `games/fpl/model.py`

The source fingerprint is load-bearing. Without it, editing a scoring constant silently
reuses stale sims and publishes a number that was never recomputed.

Stored artifact is a compact summary, not 50k raw samples: mean events, goal-sample
quantiles, the bonus distribution, DefCon probabilities. That set is sufficient for all six
articles. Old gameweeks are never rebuilt — `_refresh_old_round_dynamic_bits` already owns
the archive-refresh path. Tests reuse the memoised-sim mechanism that took the suite from
530s to 67s (07-06).

## 7. The model

### 7.1 Priors and minutes — `core/fpl_priors.py`

- `goal_share` ← `expected_goals_per_90` normalised within club; `assist_share` ← `expected_assists_per_90`
- Rate blends last season's per-90 with this season's as minutes accumulate, shrinking toward the prior early. The shrinkage rate is a `config.py` dial, set faster than a normal season would warrant because of this year's churn.
- `start_prob` ← starts-per-team-match in-season, `starts_per_90` before that, then **hard-gated by `status` and `chance_of_playing_next_round`** (`i`/`s`/`u` → 0; `d` → scaled). This is STRATEGY.md §9's top-priority weakness and FPL supplies the data directly.
- `exp_minutes` ← `minutes / starts`, clamped.
- `pen_taker` ← `penalties_order == 1`
- New: `defcon_per90` (CBIT for DEF, CBIRT for MID/FWD), `saves_per90`

**Cold-start fallback.** Promoted-club players and summer signings have empty or non-PL
`history_past`. Fall back to a position-and-price prior — FPL's price is itself a forecast,
so a £7.5m midfielder carries information. `ep_next` is a second fallback. Players hitting
a fallback are flagged in preflight.

Position mapping: FPL `element_type` 1–4 → `GKP`/`DEF`/`MID`/`FWD`; the repo's internal
vocabulary uses `GK`, so map at the `fpl_priors` boundary.

### 7.2 Direct scoring — `games/fpl/model.py`

Mirrors `expected_points()` in the FIFA model. Two places the WC's shortcuts do not survive:

- **The divisors are integer thresholds on counts, not linear rates.**
  `E[floor(saves/3)] ≠ floor(E[saves]/3)`. The FIFA model takes the linear shortcut
  (`SAVE_PTS = 1/3` × mean saves), a small bias there. With a GK goal at 10 and clean sheet
  at 4, goalkeepers carry more weight in FPL — so points come from the per-sim counts in
  `save_samples` and `conceded` (§4.1b), never from means.
- **DefCon is a threshold, so it is a probability.** `P(CBIT ≥ 10)` / `P(CBIRT ≥ 12)`
  computed from `defcon_samples` (§4.1b), paying exactly 2, capped. `2 × rate/threshold` is
  wrong in both tails. This is the differentiator article's engine.
- **Appearance points** use `played_60` for the 2-point tier and `played` for the 1-point
  tier, rather than the FIFA model's blanket "treat appearance as 60+" simplification.

### 7.3 Bonus points

The BPS table has 30+ components — crosses, dribbles, pass-completion tiers, fouls won,
errors leading to an attempt. **We have none of that data and no route to it.**
Reconstructing BPS from components is not possible.

Instead, bonus is a **rank-within-match** problem, computed in the `per_match_hook` of §4.1c.
Per sim, per match: each player's BPS =
a baseline per-90 rate (from FPL's own `bps` history) × minutes, plus event-driven deltas
for the components we *do* sample — non-penalty goal (FWD +24, MID +18, GK/DEF +12),
penalty goal +12, assist +9, GK/DEF clean sheet +12, conceding −4, yellow −3, red −9, own
goal −6, penalty save +7, and +2 per save. Rank all 22, award 3/2/1.

Only the base +2 per save is modelled. The +1 increments for a save inside the box and for
a save from a big chance need shot-location data we do not have; they are absorbed into the
baseline per-90 BPS rate rather than applied per event.

This yields a calibrated bonus *distribution* without inventing dribble counts. It is new
machinery, not a port, and it earns its cost: bonus is a meaningful slice of any high
scorer's total and the BPS rework is one of the season's real changes.

**Not modelled:** own goals, penalty misses and saves as sampled events (rare — flat EV
from season rates), goalline clearances, errors leading to goals.

### 7.4 Calibration posture

There is **zero realized FPL data until GW1 completes**, so GW1 projections ship
uncalibrated and are labelled as such on the site. The backtest harness grades from GW1
forward; constants get recalibrated the way the MID tackles/chances credit was on 07-06,
including publishing the miss.

## 8. Site

### The six GW1 articles

| Article | Engine output |
|---|---|
| Captains | 2× xP, kickoff-ordered chain |
| Draft XI / wildcard | Budget knapsack — £100.0m, max 3/club, legal formation. `optimize_holdet.py`'s formation sweep (a52c054) is the precedent. |
| Fixture ticker | Per-club clean-sheet probability, expected goals for/against |
| Defenders | DEF/GK xP with CS, DefCon and bonus split out |
| Efficiency | xP per £m |
| **DefCon leaders** | `P(CBIT ≥ 10)` / `P(CBIRT ≥ 12)` |

Dropped from the WC set: `blowout-transfers` and anything keyed on `p_advance` — knockout-specific, no FPL analogue.

**Ticker confidence labelling.** ESPN prices fixtures only a week or two out, so a
multi-GW ticker is market-derived for the near gameweek and priors-derived beyond it. Each
column states which, per the transparency positioning. Silent uniformity would be a
misrepresentation.

CLI: `python3 -m evmax.build --gw N`; `python manage.py fpl --gw N --refresh`.

### Per-GW research pass

Replacing the Reddit path (D7): a web-search pass over FPL portals (Fantasy Football Scout,
RotoWire, premierleague.com, club press conferences) before each gameweek, reusing the WC's
`research/rounds/` digest convention and writing actionable flags into `research/players/*.md`
with the frontmatter `core/research.py` already reads (`status`, `start_prob_override`,
`lambda_multiplier`, `sources`, `updated`).

It serves two purposes: topic selection for the articles, and injury/rotation flags feeding
the engine's research overlay at the game's `research_weight`. This is the FPL analogue of
the R3/R4 news passes and is part of the recurring per-gameweek routine, not a one-off.

### Order book

`games/fpl/model.py` is in GW1 scope, not deferred. The owner validates the model by playing
the game and grading the order book against realized points — that feedback loop is the only
source of calibration evidence before the backtest harness has history to work with (§7.4).

## 9. Failure modes

Extend the existing `_preflight` (which already warns loudly on unpriced fixtures,
e16d241, and expired risk flags) to warn when:

- a gameweek has fixtures with no odds
- a player fell back to the price prior for lack of PL history
- `status` / `chance_of_playing` data looks stale
- the sim cache missed unexpectedly

## 10. Testing

- `fpl_api` parse tests against saved bootstrap/fixtures JSON, offline, following the `espn.py` fixture convention
- `fpl_priors` — cold-start fallbacks, `status` gating, position mapping
- `games/fpl/model` — each scoring row hand-computed; **both divisors**; the DefCon threshold probability; bonus rank-within-match
- **Synthetic blank/double fixtures** — live data won't exhibit these for months
- Deadlines come from the API in UTC
- The existing suite stays green — the regression gate proving WC track-record grading is intact

## 11. Implementation phasing

This spec is larger than one sitting. Four phases, each independently verifiable, in
dependency order:

| Phase | Contents | Done when |
|---|---|---|
| 1 — Data | `core/fpl_api.py`, `core/fpl_priors.py`, gameweek semantics in `fixtures.py`, league param in `espn.py`, new `PlayerPrior` fields | GW1 priors build offline from cached bootstrap; parse + gating + synthetic blank/double tests green |
| 2 — Model | `games/fpl/model.py`, `rules.md`, DefCon threshold, bonus rank-within-match, `priors` injection into `engine_events` | Order book runs for GW1; every scoring row hand-verified; existing suite still green |
| 3 — Caching | `core/simcache.py` | A second build reuses the cache; changing a scoring constant invalidates it |
| 4 — Site | Six articles, `/fpl/gw{N}/`, preflight extensions | Full GW1 build into `dist/` |

Phases 1 and 2 are the beachhead — nothing else has value without them. Phase 3 is
independent of 1–2 and can move in parallel if convenient. Phase 4 depends on all three.

## 12. Out of scope

Templating refactor (September). Transfers, chip-timing and `ep_next`-comparison articles
(post-GW1). Full 38-GW transfer-path optimiser. Holdet sibling. Reddit read path (D7).
