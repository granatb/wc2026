# Changelog

Engine / model / app changes, newest first. Verification: `python3 -m unittest discover -s tests -t .`
(1052 tests). App: `streamlit run app.py`.

## 2026-08-26 — Phase 2B: the public dataset, the MCP server, the accuracy page

Three surfaces nobody in the FPL space currently holds, all built on numbers we
already had (spec: `docs/superpowers/specs/2026-08-26-phase2-design.md`, P2/P3/P4
and decisions D3–D6). The common thread: everything we compute becomes
independently checkable, and every reuse of it is a citation.

- **`evmax/dataset.py` — the CC BY 4.0 bulk dataset.** Pure emitters:
  `gameweek_payload` (licence/attribution/method meta plus every simulated
  player), `to_csv` (RFC 4180 — stable header, CRLF, minimal quoting, no index
  column, `None` as an empty cell and never the string "None"), `index_payload`,
  `merge_all`. `COLUMN_GLOSSARY` defines every column exactly once; `/data/` and
  `docs/DATASET.md` both render from it and a test fails if a column ever ships
  undocumented.
- **The build publishes it** (D3 — from artifacts already in memory, no new
  pipeline): `/api/fpl/dataset/gw{N}.json|.csv`, a refreshed `index.json`, and
  `all.json|.csv` rebuilt from **every `gw*.json` already on disk in `out/`**.
  Old gameweeks survive a rebuild without being re-simulated, which matters
  because re-simulating would quietly restate a frozen published claim. The
  dataset covers every simulated player, not the (cappable) page payload set;
  an unmatched name gets a null element id rather than a guess that would
  poison a downstream join.
- **`/data/`** — the human page: the terms with the exact credit line to paste,
  the column glossary, three curl examples, a card per file, a citation block,
  and schema.org `Dataset` for Google Dataset Search. Reached via the sitemap,
  `llms.txt` and `/track-record/`'s FPL block. **No nav or footer link was
  added** — that chrome is shared, and every World Cup page stays
  byte-identical; `evmax/build.py` has no reference to the dataset at all,
  pinned by a test.
- **`/fpl/accuracy/`** (P4) — the graded ledger in full: per-gameweek MAE over
  the number of players actually graded (so a good average cannot hide behind a
  tiny sample), FPL's own `ep_next` where captured, both frozen squad lines
  against realized official points, the running duel, and a link to every
  grading JSON. Per D5, GW1's `ep_next` cell reads **"captured from GW2"** — a
  bare dash in a column of numbers reads as a zero, and a zero there would claim
  FPL's own model was perfect that week. A "how to check us" block names the
  whole chain: frozen snapshot → public grading JSON → downloadable dataset →
  open code.
- **`scripts/benchmark_export.py --gw N`** — the submission artifact for a
  third-party expected-points benchmark, written from the **frozen** snapshot
  (`player_id,player_name,gameweek,predicted_points`). A gameweek with no
  snapshot exports nothing and says so; re-simulating a finished gameweek would
  produce a number we never published, which is exactly what a public benchmark
  exists to catch.
- **`mcp/` — the evmax MCP server** (D4): Node ESM, one dependency
  (`@modelcontextprotocol/sdk`), stdio, no build step, no secrets, no state.
  Tools: `list_gameweeks`, `get_projections`, `get_player`, `get_duel`,
  `get_accuracy`, `get_distribution`. Every result cites its source URL and the
  CC BY line. Two things it is careful about: **a 200 is not a success** (Pages
  serves the HTML 404 fallback with status 200, so the fetch layer checks the
  content type and treats HTML as "not published"), and the dataset is
  *preferred, not required* — where a gameweek predates a field the tools fall
  back to the always-live feeds and **say which source answered** rather than
  reporting a missing column as a zero. `node mcp/test-smoke.js` hits the live
  site and is deliberately outside the Python suite. npm publish stays an owner
  action.
- **`docs/DATASET.md`** — the schema mirror: files, cadence, JSON shape, every
  column with type and meaning, the per-week vs per-match units warning, the
  licence and the citation forms.

Suite 982 → 1052, green at every commit. World Cup pages byte-identical;
`evmax/assets/projections/` untouched.

## 2026-08-26 — Phase 2A: distributions

Everyone in this market ships a mean. A mean cannot tell a 6.0 that is six
every week from a 6.0 that is zero four times and twenty-four once, and only a
real Monte-Carlo engine can tell you which one you are buying. This phase
surfaces the shape (spec: `docs/superpowers/specs/2026-08-26-phase2-design.md`,
P1 and decisions D1/D2).

- **`SimPointsAccumulator.histogram(name)`** (`games/fpl/model.py`) — the
  discrete PMF over integer FPL points, zero-padded for non-appearances on the
  same convention as `mean()`, so the counts sum to `sims` and the histogram's
  own mean reconstructs `mean(name)`. Stored per row as `distribution` inside
  the cached artifact. The simcache is JSON and JSON keys are strings, so
  `_int_keyed_distributions` restores int keys on a cache hit — in one place,
  rather than making every consumer tolerate both types.
- **Six derived columns** (`_derive_row`): `p10` (floor), `median`, `p90`
  (ceiling), `mode` (most likely, ties breaking low so the published number is
  deterministic), `p_haul` (P ≥ 10, inclusive) and `p_blank` (P ≤ 2,
  inclusive). Percentiles use the lower-bound convention — smallest x with
  cumulative ≥ q — because points are integers and interpolation would smear
  across the appearance cliff, hiding the atom of probability at 0 that is the
  most important fact about a rotation risk. These are WEEK-level, on the same
  denominator as `x_points`, unlike the per-match bonus/defcon/cs columns.
- **The card's distribution chart** (`evmax/fpl_players._distribution_svg`):
  bars banded by outcome (muted blank / green return / dark-green haul), rules
  at floor, most likely and ceiling, drawn range clipped at the 99th percentile
  so one freak sim cannot flatten it. The SVG carries geometry only — the
  numbers are HTML above it — because text inside a scaled viewBox is a 27px
  shout on a player page and unreadable in a landing card.
- **Decision D1: distributions are FREE.** The premium slot's reserved striped
  strip is gone and its copy is your-team work only. Per-player JSON's reserved
  `distribution: null` now carries the histogram, its sim count and the six
  statistics, and still degrades to null for a pre-histogram artifact.
- **`/fpl/gw{N}/distributions/`** — the ninth article slug. `beats(a, b)` =
  P(A > B) + 0.5·P(A = B) over two PMFs; the half-credit on ties is
  load-bearing, because points are integers, ties are common, and without it
  the two directions would not sum to 1. Independence is a knowingly wrong
  approximation (two attackers in one match are not independent), so the
  template states it as a fixed sentence and the LLM prompt makes stating it a
  condition of printing the number. The engine holds the joint distribution; a
  later version should read P(A > B) off the paired per-sim totals instead.

## 2026-08-24 — FPL phase 5: the credibility engine

Every GW1 credibility dent was a knowledge failure, not an engine failure
(double-Spurs-keeper advice, the wrong Sangaré, the Watkins hold, Isak/Maguire
minutes mispriced until Reddit corrected us). This phase makes that class of
failure mechanically unpublishable and lands the community-validated engine
fixes (spec: `docs/superpowers/specs/2026-08-24-credibility-engine-design.md`,
decisions D1–D8).

- **`core/fpl_diff.py`** — the feed churn detector: compact bootstrap snapshot
  (`data/fpl/feed_snapshot.json`), categorised diff (renames, club moves,
  status/price changes, arrivals/departures, transfer-out z-spikes ≥ 3.0),
  human report via `python3 -m core.fpl_diff`. Would have caught the Sangaré
  rename, the Konsa move and the Watkins exodus.
- **Player dossiers + the publish gate** (`games/fpl/dossier.py` +
  `evmax/fpl_build.dossier_gate`): every published player is red iff status
  ≠ 'a', proxy start prob < 0.75, club changed since the snapshot, outflow
  spike, or unresolved name — and a red **aborts the build** unless a research
  note with non-empty `sources:` dated on/after the feed snapshot overrides
  it. Deliberately no `--force-publish` (D1: refusal, not warning). The GW1
  states gate green off the committed round-1 notes.
- **Optimizer v2** (`evmax/fpl_articles`, D6): objective = XI xPts + the best
  player's again (the doubled captain), compared by the formation sweep and
  both repair loops — pinned by a test where a 15.5m premium enters under the
  joint objective and is sold under the plain sum; XI minutes floor
  (start_prob ≥ 0.75 unless a sourced note vouches, threaded from the priors
  through the build); bench cost capped at 18.5.
- **`core/fpl_strength.py`** (D6): per-team att/def multipliers fitted in log
  space from every real-market odds-cache entry, recency-weighted 0.85/week,
  shrunk (k=2) toward the FDR-calibrated prior. `games/fpl/model.gameweek_odds`
  re-prices absent/fdr-sourced future entries from the table once ≥2 real
  gameweeks exist (`source: strength_table_v1`); the current week's real odds
  always win; below 2 real GWs the FDR prior stays, so a GW1-only world builds
  identically.
- **Transfer optimizer v1** (`games/fpl/transfers.py` +
  `manage.py fpl --round N --transfers [--bank M]`): every legal single swap
  scored on the discounted-horizon delta (0.95/week), hit-adjusted at 0 FTs,
  red-dossier players forced to the top of the sale block regardless of delta
  — the Watkins rule; GW2's Watkins call is its first live user.
- **Accuracy grading v1** (`games/fpl/grading.py` + `scripts/grade_gw.py`):
  our frozen x_points vs FPL's own `ep_next` (now frozen per player into the
  projection snapshots for future gameweeks) vs realized points, banked to
  `evmax/assets/accuracy/gw{N}.json`; squad-level projected-vs-realized from
  the frozen envelope meta. The C-metric, banked weekly; a site surface comes
  with the next site phase.
- **Runbooks + learnings**: `docs/runbooks/thursday-pre-deadline.md` and
  `monday-post-gw.md` (numbered, exact commands, "schedule later" sections
  PARKED per D3); `docs/research/season-learnings.md` seeded with GW1's six
  entries in mistake → root cause → structural fix → status form.
- **IndexNow on every deploy**: the ownership key file `/{key}.txt` moved
  into the shared site chrome (an FPL publish used to silently drop it —
  only the WC build wrote it), and the inline curl in `scripts/deploy.sh` is
  replaced by the tested `scripts/indexnow_ping.py --out dist` (stdlib,
  injectable opener, ≤10k URLs, exits nonzero but NEVER raises on network
  failure — a failed ping must not break a deploy). Google doesn't consume
  IndexNow; the one-time GSC sitemap submission is documented in the Thursday
  runbook's first-time appendix.

Suite: 832 → 914, all offline, synthetic payloads shaped like the real APIs.

## 2026-08-24 — FPL phase 4c: the live duel (points so far) + consensus reset machinery

The WC-style "so far" reality layer, FPL edition. New **`core/fpl_live.py`**
(network/pure split, mirroring fpl_api): `event/{gw}/live/` +
`fixtures/?event={gw}` behind `refresh_live` (cache `data/fpl/live_gw{N}.json`,
always overwritten — a convenience, not a record) and a pure **`grade_squad`**
returning per-player {name, club, points, multiplier, status
played|pending|blank|autosub_in, note} plus total_so_far / players_pending /
autosubs_applied / captain_effective. Autosubs walk the PUBLISHED bench order —
first player who actually PLAYED whose entry keeps the XI formation legal
(≥3 DEF, ≥2 MID, ≥1 FWD; GK swaps GK-only); the armband falls captain→vice,
never to the sub; pending players stay "to play". Everything is provisional
mid-gameweek by construction — the next rebuild self-corrects. Names shift
under a live season ("Sangaré" → "I.Sangaré"), so every live join resolves via
the state files' new validated **`aliases`** map and FAILS LOUDLY listing every
unresolved name (a silent skip would publish a 14-man total as if real).

**`--gw N --live`** renders exactly two live surfaces: the landing duel strip
gains each squad's realized total ("**44** so far · 1 to play") next to the
frozen projections, and each squad page gets a compact realized table above the
frozen prose, stamped "live — updates on rebuild · as of <fetch> UTC". Default
is auto — on when the bootstrap marks the gameweek current and a fixture has
started, cache-only (never the network), `--no-live` opts out. The standing
07-04 freeze is now test-enforced: with the clock pinned, a --live build and a
plain build differ in EXACTLY four files (the landing's root + section copies
and the two squad pages' HTML); every other article byte — squad JSON
envelopes and md twins included — survives byte-identically.

**`--gw N --reset-consensus`** (owner decision: from GW2 the Consensus XI is
the actual most-owned legal template; the GW1 expert mention-tally retires
with a method note; the squad declares its first Wildcard): new
`games/fpl/consensus.py` builds the top-selected_by_percent 15, greedily
legalised under budget/quota/club-cap (budget repair sheds the least ownership
per pound saved), XI = the most-owned legal formation, captain = the
highest-owned premium (≥10.0m) with the vice next; writes
state_consensus.json (house style, `chips_used: ["wildcard"]`, method_note)
only after games/fpl/state.py validates it — an illegal template aborts and
leaves the current file untouched. Implemented + tested on synthetic
bootstraps only; the owner triggers it before the GW2 deadline. README gains
the in-gameweek routine (`--live` rebuild + deploy after each match day; the
one-off consensus reset). Suite: 748 → 832, all offline, synthetic payloads
shaped like the real API.

## 2026-08-19 — Phase 4 review fixes (pre-merge)

Nine findings from the pre-merge review of the FPL port, fixed one commit
each. Correctness: **`kickoff_order` is now a dense rank over the published
top-20's distinct kickoff instants** (it enumerated all ~560 rows, giving two
players in the same match different orders and letting the captains prose
claim a false "kicks off later" — the vice sentence now claims first/later
only when the instants genuinely differ); **the sim cache key covers kickoff
times** (a fixture re-slotted for TV with unchanged odds used to HIT and serve
the stale kickoff); **the FPL sitemap keeps prior gameweeks** (the disk-walk
only covered `out/round`, so building GW2 would have dropped every GW1 URL — a
deindexing request); **both builds write the root-level site chrome** via one
shared `write_site_chrome` (the FPL build produced no GSC verification file,
`/_redirects` or `/track-record/` while pointing at the latter from its own
nav and sitemap).

Honesty of the prose: **"seven expert sources" now derives from
`source_count` in the consensus state** (validated, stamped through
`squad_article` onto entries) and the **"the consensus XI owns him" sentence
renders only when the consensus squad actually owns Haaland** (flag stamped by
the build, the only layer holding both squads); **FPL pages describe the
ceiling as what it is** — the average of a player's best 15% of simulations, a
tail mean strictly ≥ the p85 the old "85th-percentile" wording claimed (WC
text byte-identical via the Section descriptor). Double-gameweek minimum fix:
`_derive_row` documents that bonus/defcon/cs_points are per-MATCH while
x_points is per-WEEK, rows carry their club's fixture count, and the defenders
prose frames the columns as components of the weekly total only for
single-fixture players (full per-sim rework deferred to a pre-first-DGW task).
Hardening: the state validator rejects bool `bench_order` and validates
`free_transfers` as a non-negative int; `TestGameweekBuild` skips (not errors)
without the data cache. WC pages verified byte-identical at render level.
Suite: 696 → 725.

## 2026-08-19 — FPL phase 4b: the two squad slugs, the landing duel, the FPL rate page

The site now fields its own teams. Two persistent squad states —
`games/fpl/state.json` (**The Model XI**: pure engine EV over the discounted
GW1–6 horizon, 3-5-2, B.Fernandes (c), Thiago vice, £100.0, no Haaland by
conviction) and `games/fpl/state_consensus.json` (**The Consensus XI**: the
best-follower team from the 7-source expert mention-tally, 3-5-2, Haaland (c),
B.Fernandes vice, £99.5) — are validated at build time by the new
`games/fpl/state.py`: exact FPL web_names (diacritics intact — "Gross" is not
"Groß"), position/quota/budget/club-cap legality, XI formation, exactly one
captain + one vice (both starters), bench_order 1–4 with the GK first. Prices
come from the bootstrap at load time, never stored.

Two new slugs publish them — **`our-squad`** ("Our squad", the hero) and
**`consensus-squad`** ("The consensus XI") — eight FPL articles per gameweek
now, each squad page carrying the XI on the pitch (captain badged from the
state, not rank), the full page family, and a `squad` meta block in its JSON
envelope. `fpl_articles.squad_article` joins state to artifact rows in state
order and RAISES on a name with no row — a published squad never silently
ships a 14-man team. Hand-written prose per the Phase 4 standard: our-squad
states the model's reasoning (horizon EV, market-implied rates, the no-Haaland
conviction — a template line that auto-retires the day he joins — captain by
EV); consensus-squad states the method (mention-tally, majority captain,
minutes from sourced research notes). No bookmaker names, no expert text.

The FPL landing leads with our-squad, captains is the first feed card, and a
**model-vs-consensus duel strip** shows both squads' projected XI totals
(captain doubled) side by side from the squad metas — no new simulation; the
strip can never disagree with the pages it links. Duel markup and CSS are
injected only when a duel is passed, so World Cup landings keep today's bytes.
**`/rate/` now serves the section that built last**: a gameweek build titles it
"Rate my FPL team", states the 15 = 2/5/5/3 shape, points at the gameweek
players feed and explains FPL's post-deadline autosubs (rate.js labels results
via a `data-unit` attribute, defaulting to "Round"); the WC rate page was
verified byte-identical against the pre-change renderer. Preflight grew squad
checks: both states load + validate, every state name matches the artifact
rows, projected totals are finite.

Verified on a real GW1 production build (offline, cached feeds, sim cache HIT):
`/round/` byte-untouched (checksummed before/after), hero + duel render — the
duel shows **65.92 (model) vs 60.74 (consensus)** projected — and all eight
projection snapshots froze pre-lock. Post-GW realized-vs-projected is next
phase (needs live data). 65 new tests. Suite: 696.

## 2026-08-19 — FPL port phase 4: the site (`/fpl/gw{N}/`, six articles, `--gw` CLI)

The FPL section exists. `python3 -m evmax.build --gw N` builds six articles per
gameweek under `/fpl/gw{N}/` — `captains`, `wildcard`, `ticker`, `defenders`,
`efficiency`, `defcon` — each with the full page family (HTML, JSON envelope keyed
`"gameweek"` not `"round"`, agent-facing `.md` twin, players bulk feed, llms.txt,
sitemap). **`/` now serves the current gameweek** (owner decision 2026-07-30): the
FPL build writes the landing to both `/index.html` and `/fpl/gw{N}/index.html`. The
World Cup tree under `/round/N/` is never touched — its landing survives at
`/round/8/`, its URLs stay in the FPL build's sitemap (dropping them reads as a
deindexing request), and `--round` builds exactly what it built yesterday.

How the one renderer serves two competitions: a `Section` descriptor in
`evmax/render.py` (paths, unit words, pill labels, points-table naming,
methodology line) threads through every page function **with a World Cup
default**, so every existing call site renders byte-identical HTML — the WC suites
passed unchanged, which was the regression gate. This is deliberately NOT the
templating refactor (spec §12, September): a second page family sharing
primitives, not one template engine.

The FPL-specific pieces live outside the frozen WC modules: `evmax/fpl_articles.py`
(pure ranking + squad building) and `evmax/fpl_build.py` (pipeline + preflight).
The 15-man squad builder enforces the **three-per-club cap** on every selection and
every swap — the one rule `articles.wildcard_squad` doesn't have, and retrofitting
it would have put the track record's dependency at risk. The ticker is one row per
CLUB (not per fixture) so **blanks and doubles** render correctly months before
live data exhibits them (synthetic tests only, by necessity), sums expected clean
sheets across a double (points-denominated, so it can exceed 1.0), and labels every
row's provenance — `market` / `model` / `mixed` — because ESPN prices only days
ahead and silent uniformity would misrepresent confidence.

The carried Phase 3 double-gameweek bonus question is **settled, and the answer is
NO**: `total_points`' `played/sims` scaling never approaches 2.0 for a doubled
player (`ps.sims` counts per match appearance), so the assembly path is a per-MATCH
average — exactly half the week. The order book's `x_points` now reads off
`SimPointsAccumulator.mean()`, which sums a player's matches within each sim.
Pinned at 2x in `tests/test_fpl_model.TestDoubleGameweekTotalPoints`.

Also landed on the way: derived row columns in the cached artifact (`captain_ev`,
`value`, `p_defcon`, `cs_points`, `kickoff`; rounding at the single `_derive_row`
choke point), per-match scoreline summaries stored IN the artifact (spec §6 —
`MatchSample` doesn't survive JSON, so derivation happens before the store),
`simcache.artifacts_for()` so preflight can tell an expected first-build miss from
an unexpected one, a **GW-stage filter** in the FPL model layer (WC round numbers
collide with FPL gameweek numbers in the shared SCHEDULE; without it the ticker
published 48 national teams), section-namespaced prose caching
(`data/articles/fpl-gw{N}/` — GW1 no longer collides with WC round 1), an FPL
field glossary + `defcon`/`ticker` focus blocks in the LLM prompt, and hand-written
prose templates for all six slugs so a `--no-llm` build reads like a real article
("B.Fernandes is the gameweek 1 captain", never "Gameweek analysis: Captains").

Verified on a real GW1 build (50k sims, offline off the cached feeds): 563 players,
legal 3-5-2 at 98.0m under the club cap, 20-club ticker with no blanks, projection
snapshots frozen to `evmax/assets/projections/fpl-gw1/` (GW1 was still open — the
same production-only + pre-lock guards as the WC's). 78 new tests. Suite: 631.

## 2026-08-19 — FPL market lambdas: the fixture layer exists now (`core/fpl_odds.py`)

Found two days before the GW1 deadline: every FPL fixture simulated at **identical
league-average lambdas** (1.445 home / 1.35 away). `ratings.TEAM_RATINGS` holds only
national teams, so `Fixture.lambdas()` fell back to `TeamRating(name)` defaults for all
20 PL clubs — Arsenal (h) v Coventry and Newcastle v Liverpool were the same match to
the engine. The order book carried zero fixture signal; rankings were pure player
priors.

New `core/fpl_odds.py`: fetches the gameweek's ESPN `eng.1` scoreboards (the dates come
from FPL's own fixtures feed), reuses the WC path end-to-end (`espn.parse_scoreboard` →
`espn.derive_match`: de-vig → Dixon-Coles solve), maps ESPN team names onto FPL short
names via an explicit 20-club table (raises on an unknown club rather than guessing),
and caches to `data/fpl/odds_gw{N}.json`. `games/fpl/model.load_gameweek` applies the
lambdas to the GW's fixtures and reports loudly — both the success ("market lambdas
applied to 10 fixture(s)") and any fixture left on flat priors. `espn.scoreboard_url` /
`fetch_scoreboard` gained an optional `league` parameter defaulting to today's
behaviour; no WC call site changes.

Measured effect on GW1 (50k sims, DraftKings closing lines 2026-08-19): Bruno
Fernandes 6.94 → **8.81** xPts (Hull away, λ 2.18), Haaland 5.69 → 7.74 (λ 2.35 v
Bournemouth), Saka #10 → #3 (ARS λ 2.56, 81% home win), Senesi #8 → #20 (Spurs away
at Brentford). The sim cache invalidates automatically — lambdas were already in the
cache key.

Known gaps, deliberate: ESPN prices only days ahead (GW2 unpriced on 2026-08-19), so
future-GW projection still needs a strength-persistence layer; the `Team Clean Sheet`
market the spec flagged is not consumed yet; solved `rho` is stored but the engine
remains independent-Poisson per team.

10 new tests in `tests/test_fpl_odds.py` (offline, synthetic ESPN payloads shaped from
the live 2026-08-19 response). Suite: 553.

## 2026-07-30 — FPL ceiling: tail mean replaces the goal-percentile (phase 4)

The 2026-07-28 fix that made the goal-percentile ceiling unconditional exposed the flaw
it had been hiding: a percentile over a **discrete** goal count is a step function.
Measured at `goal_share=0.35`, 40k sims: `P(play) 1.00→0.61` gave `p85(goals)=1.0`
(ceiling/xPts 1.84–2.72), while `P(play) 0.50→0.20` gave `p85(goals)=0.0` — ceiling
pinned to xPts exactly. Above ~55% start probability every player's ceiling sat in a
narrow 5.1–5.8 band; below it the column carried no signal at all. Confirmed live on
GW1: Senesi, Tarkowski, Rice, Virgil, Szoboszlai, Verbruggen, Gabriel and others all
printed `ceil == xPts` to two decimal places.

Replaced with a **tail mean**: the mean of simulated total FPL points across the top
`(1 − q)` fraction of sims (q=0.85), taken over the player's full, zero-padded per-sim
distribution. A mean over a tail averages many sims rather than reading off one order
statistic of a small integer-valued variable, so it stays smooth as appearance
probability moves through the region that broke the percentile.

- **`core/engine_events.py`** — `per_match_hook` gained a third argument, `sim_index`
  (the match's position in the outer sim loop), and each hook row gained an 11th field,
  the player's already-sampled DefCon count. Both are additive and consume no extra
  `rng` calls — `tests/test_engine_determinism.py`'s pinned digest is unchanged.
  `sim_index` exists so a hook can tell "two matches in the same sim" (a double
  gameweek, where a player's points for that sim are the sum across both) apart from
  "two matches in two different sims" — impossible to do correctly without it.
- **`games/fpl/model.py`** — new `SimPointsAccumulator`, a `per_match_hook` consumer
  that records each player's total FPL points per sim, summing across matches within a
  sim for double gameweeks. `mean(name)` is the unconditional mean (zero-padded for
  non-appearances, `sims` passed at construction since this pipeline has no separate
  finalise step); `tail_mean(name, q=0.85)` is the new ceiling. The tail-size floor
  (`max(1, round((1-q) * sims))`) is pulled into a standalone `_tail_mean(values, q)`
  so the statistic itself is unit-tested against hand-built distributions, independent
  of the engine.
  Kept as a class SEPARATE from `BonusAccumulator` (whose existing cross-sim-average API
  and test suite stay untouched) rather than merging the two. Both need a match's bonus
  award, so the BPS rank/tie logic was pulled out of `BonusAccumulator.observe` into a
  module-level `_bonus_awards(rows, baselines)` that both classes call — reused, not
  duplicated; each accumulator's own total does not double-count a bonus award.
  `BonusAccumulator.observe` gained the same third `sim_index` parameter (unused —
  bonus is already correctly per-match) purely to match the new hook signature.
- **Retired `ceiling_points` and `_unconditional_goal_samples`** — confirmed nothing
  outside `games/fpl/model.py` and its tests called either. `build_rows`'s `ceiling`
  column now reads `points.tail_mean(name)`; `x_points` is unchanged (`total_points`).
  `total_points` and the component assembly it exercises were kept and cross-checked
  against the new distribution's `mean()` (`TestDistributionMeanAgreesWithTotalPoints`)
  — the two paths agree to within ~0.03 pts across start probabilities 1.0/0.6/0.3,
  which is real end-to-end validation of the whole per-sim scoring path.
- **Verified on GW1, 8,000 sims:** the appearance-probability cliff is gone (40k-sim
  sweep, `goal_share=0.35`: tail mean 12.31 → 11.68 → 11.02 → 10.67 → 10.33 → 7.79 as
  `P(play)` runs 1.00 → 0.80 → 0.61 → 0.50 → 0.40 → 0.20 — strictly decreasing, no
  adjacent step over 2x). `ceil >= xPts` holds on all 563 modelled players, not just
  the printed top 30. The **order book's own sort key is `x_points`**, so the printed
  ranking is byte-identical to before this change; only the `ceil` values move — up
  across the board, most for the previously-flat rotation/defensive players (Senesi
  4.44→10.51, Tarkowski 4.40→10.82, Rice 4.12→9.58, Virgil 4.01→10.21). Ranked BY
  ceiling instead, the top 12 does reorder: Enzo/Tavernier/Mbeumo drop out and
  Welbeck/Calvert-Lewin/Mateta enter, because forwards' variance is now weighed by
  actual point upside rather than a floored goal percentile.

## 2026-07-28 — FPL port, phase 3 (sim caching)

Plan: `docs/superpowers/plans/2026-07-28-fpl-port-phase3.md`. Implements STRATEGY.md's
07-06 owner requirement that per-round build artifacts become incremental, while staying
static-first on the CDN — no database, no server.

- **`core/simcache.py`** — content-addressed cache for per-gameweek sim output. Stores the
  DERIVED per-player rows (not 50k raw samples), so a copy or layout change re-renders with
  no sim at all.
- **Measured on GW1 at 8,000 sims: 7.79s cold, 0.17s warm — ~46x.** `--no-cache` forces a
  fresh run (7.68s) as an operator escape hatch.
- **The key covers everything that determines the numbers:** gameweek, sim count, seed,
  per-match lambdas, a projection of every sim-affecting `PlayerPrior` field, the research
  entries, the four sim-affecting config dials (`GOAL_CONCENTRATION`,
  `PEN_TAKER_GOAL_BONUS`, `DEVIG_METHOD`, `research_weight`) — and a **fingerprint of the
  model source itself** (`engine_events.py`, `fpl_priors.py`, `blend.py`, `research.py`,
  `games/fpl/model.py`).
- **Why the source fingerprint is load-bearing:** without it, editing a scoring constant
  would silently serve a stale artifact and publish a number that was never recomputed —
  the worst available failure for a site whose positioning is published methodology.
  Verified by touching `games/fpl/model.py` and observing a full re-simulation.
  `blend.py` and `research.py` were added to the fingerprint after review: both shape sim
  output (`effective_goal_weight` calls `blend.blend_rate`; `ResearchEntry.adjust` applies
  the overlay), and hashing research entries as *data* does not cover the logic that
  interprets them. `odds_math.py` and `ratings.py` stay out deliberately — they reach the
  sim only through the lambdas, which are hashed as computed values.
- A corrupt or unreadable artifact is a **miss, not an error**: the cost of a miss is
  re-running the sim, whereas raising would break a build over a recoverable problem.
- **`run()` refactored** to expose `build_rows(priors_by_team, players_by_name, gameweek,
  sims, use_cache=True)`. The old shape could not be tested without full integration setup,
  which is precisely how the phase-1/2 defects hid.
- **Gap closed in passing:** the FPL path never passed `research=` to `simulate_round` (only
  `research_weight`), unlike `games/fifa/model.py`. Now wired. Behaviourally inert today —
  no overlap between existing `research/players/*.md` names and the FPL pool — but it means
  the per-gameweek research pass will actually reach the engine.

## 2026-07-28 — FPL port, phases 1-2 (data layer + model)

Spec: `docs/superpowers/specs/2026-07-28-fpl-port-design.md`.
Plan: `docs/superpowers/plans/2026-07-28-fpl-port-phase1-2.md`.
Target: GW1 lock `2026-08-21T17:30:00Z`. Public evmax site is the deliverable; the
private order book is the instrument for validating the model by playing the game.

### Data layer

- **`core/fpl_api.py`** — official FPL API client for `bootstrap-static` / `fixtures` /
  `element-summary`, cached to `data/fpl/`. Network isolated in `fetch_*`; every `parse_*`
  pure and fixture-tested offline. **Deadlines are read in UTC from
  `events[].deadline_time`** — the official rules page localises them to the viewer's
  timezone (it rendered GW1 as 19:30 CEST against the true 17:30Z) and must never be
  scraped.
- **`core/fpl_priors.py`** — the player layer inverts from market-derived to **xG-derived**.
  ESPN carries NO player-level props for `eng.1`: all 172 prop markets on a sampled GW1
  fixture were match-level, so the World Cup's anytime-goalscorer path is empty at build
  time. FPL's own feed ships last season's per-90 rates instead, which slot into the
  engine's existing `prior_share` blend slot — if props ever appear, the `market_rate` path
  lights up with no code change. Availability gating from `status` +
  `chance_of_playing_next_round` addresses the crude-minutes weakness logged in
  STRATEGY.md §9. Promoted-club players and new signings (163 of 563) fall back to a
  position-and-price prior and are flagged in the run output.
- **Gameweek semantics** (`core/fixtures.py`) — `round_lock_time` now prefers a registered
  deadline over first kickoff (they differ: GW1 locks 17:30Z, first kickoff 19:00Z), plus
  blank/double helpers. The live feed is a clean 10 fixtures per gameweek and will not
  exhibit blanks or doubles for months, so those are tested against synthetic fixtures.
- **`config.ESPN_LEAGUE`** parameterises the odds client's league slug.

### Engine extensions (all additive; World Cup behaviour unchanged)

Guiding principle: **the engine samples raw events, each game applies its own rules.**

- Injectable `priors` provider, resolved once per team instead of inside the sim loop.
- `PlayerSample` gains `conceded` (FIFA's `conc_beyond` stores `max(0, ga-1)`, from which
  FPL's `floor(ga/2)` is not derivable), `played_60` (FPL pays 1 under 60 minutes and 2 at
  60+), and per-sim `save_samples` / `defcon_samples` (because
  `E[floor(x/n)] != floor(E[x]/n)`, and a threshold crossing cannot come from a mean).
- `per_match_hook(match_id, rows)` for rank-within-match quantities.
- **`tests/test_engine_determinism.py`** pins the engine's exact output for a fixed seed.
  Added because the existing suite could NOT have caught an RNG-sequence change: every
  other test of `simulate_round` asserts directionally or with a tolerance, so a shifted
  sequence leaves distributions statistically identical and all tests green — while moving
  every published projection. Verified by direct byte-for-byte comparison against the
  pre-extension commit: identical across every accumulator and the full scoreline
  distribution over 4000 sims.

### FPL scoring (`games/fpl/model.py`)

- 2026/27 table with **GK goals at 10** and DefCon paying forwards. Both divisors
  (1 point per 3 saves, -1 per 2 conceded) are pinned from the official rules page, **not**
  from `game_config.scoring`, which reports unit values and mis-prices every goalkeeper if
  read literally. Provenance per row in `games/fpl/rules.md`.
- DefCon modelled as `2 x P(count >= threshold)`, not as a rate — `2 x rate/threshold` is
  wrong in both tails.
- **Bonus points** — rank-within-match from a per-90 BPS baseline plus exact event deltas.
  Reconstructing BPS from components is impossible (30+ components including crosses,
  dribbles and pass-completion tiers, none observable), so unobservable components ride in
  the baseline. Ties consume award positions per the official rule: two tied on top both
  take 3 and the third-most BPS takes 1, not 2.

### Defects found by RUNNING the order book (no unit test caught these)

- **FPL `web_name` is not unique across clubs.** 14 collisions in the GW1 pool; the shared
  engine keys its accumulator by name alone, so Cole Palmer (CHE, MID, £9.5m) and Alex
  Palmer (IPS, GK, £4.0m) merged into one player — putting a £4.0m backup keeper 4th on
  expected points. Fixed at the FPL boundary (`core/fpl_priors`), NOT in the shared engine,
  which would have broken research/`market_rates` lookups and the determinism pin.
  14 collisions -> 0; the 533 already-unique names are untouched.
- **The ceiling was not comparable to the mean beside it** — `ceiling_points` omitted saves,
  conceded, DefCon and bonus that `total_points` includes, so `ceil < xPts` on ~1 row in 6.
- **`bootstrap-static` zeroes every DefCon field for all 563 players** (verified: 0 of 563
  non-zero for `defensive_contribution`, `clearances_blocks_interceptions`, `recoveries`,
  `tackles`) while backfilling `minutes`, `expected_goals` and `bps`. The DefCon-leaders
  article — the chosen differentiator — would have been computed entirely from zeros. Data
  recovered from `element-summary/{id}/history_past` via a **one-time** incremental cached
  backfill (400 fetched, 0 failed); last season's history is immutable and in-season the
  bootstrap field populates itself. Same shape as the existing one-time `data/athletes.json`
  resolution, so consistent with §4.5 polite fetching.
- **Raw per-90 DefCon rates from tiny samples are meaningless** — a player with 1 minute of
  history scored 90.00 per 90, and 14 players under 200 minutes carried rates above the 12
  threshold, which would have topped the leaderboard on pure noise. Now shrunk toward
  measured position priors (DEF 7.72, MID 7.96, FWD 4.46, GK 0.00, from the 267 players with
  >=900 minutes) with `K = 3` pseudo-appearances. Chosen over a hard minutes cutoff, which
  would silently zero injury returns and arrivals from abroad. Goalkeepers are gated to zero
  at three independent layers.

### Caught in final code review

- **Conditional components were added to an unconditional expectation.** `expected_points`
  divides by total sims, but `save_samples` / `defcon_samples` / `conceded` / the bonus
  accumulator are all populated only on sims where the player featured — so four
  `E[x | played]` terms were being added to an `E[x]` term. Measured: three defenders with an
  identical DefCon rate but start probabilities of 1.0 / 0.5 / 0.2 all received the same
  0.47 DefCon points. A player featuring one week in five was paid like a nailed starter,
  which corrupted the DefCon-leaders ranking specifically. Now scaled by `played / sims`.
  Invisible to every prior test because they all used `start_prob=1.0` fixtures.
- Penalty goals are not distinguished from open-play goals in the BPS credit (the official
  table pays 12 for a penalty regardless of position, vs 24 for a forward's non-penalty
  goal). The engine does not sample penalty goals separately, so this is now recorded in the
  not-modelled list rather than silently wrong.
- **Open question, not fixed:** `ceiling_points` mixes an unconditional mean-goal term with a
  conditional percentile term, so a fringe player keeps ~75% of a nailed starter's ceiling on
  20% of the minutes. This is inherited World Cup behaviour (`games/fifa/model.py` has the
  same shape) and is a product decision about what "ceiling" should mean, so it is deferred
  to Phase 4 where the risky/differentials article is its consumer. See the plan document.

### Status and known gaps

- **Uncalibrated.** No realized FPL data exists until GW1 completes; the backtest harness
  grades from GW1 forward (spec §7.4).
- **No fixture-difficulty signal yet.** ESPN `eng.1` odds are not wired in, so every GW1
  fixture gets identical lambdas (1.445 home / 1.35 away from `BASE_GOALS` and `HOME_ADV`) —
  Arsenal-Coventry is priced exactly like Hull-Man Utd. Rankings are driven entirely by each
  player's own rates. Belongs with Phase 4's fixture ticker, its first real consumer.
- `manage.py --refresh` silently runs the World Cup ESPN path for `fpl` and writes WC data
  into `data/schedule.json`. Harmless but misleading; not yet fixed.
- Spec §7.1's last-season/in-season rate blend is only half-built: the dial
  (`FPL_PRIOR_SHRINKAGE_MATCHES`) exists but is unconsumed and `team_matches` is hard-coded
  to 38. Correct preseason, must be wired before GW2.

## 2026-07-06 — QF prep: slot-life weighting (the USA lesson)

- **Slot-life weighting** (`games/holdet_common.py`): `advance_prob` (P(win 90') + ½P(draw))
  and `slot_life` (expected remaining rounds a squad slot stays alive; rounds beyond the
  current opponent priced at a neutral 0.5). Motivation: equal round-EV on France and on a
  coin-flip team are not equal holdings — Germany (R32) and the USA (R16) each killed
  multiple slots at once and cost a fee per slot to rebuild.
- **Optimiser rebuilt** (`optimize_holdet.py`): objective is now growth × slot_life; live
  market prices/ownership from `holdet_api` (was: stale `data/holdet_prices.json`); round
  as a CLI arg (was: hardcoded 2). EV games cap coin-flip teams (advance prob inside
  `COINFLIP_BAND` 0.35–0.65) at `CONCENTRATION_LIMIT` (2) players; the variance game is
  exempt (stacking is its strategy).
- **Concentration flag** in every Holdet order book: warns when >2 players share a
  coin-flip team in knockouts (correlated elimination risk a linear EV never shows).
- Tests: `tests/test_slot_life.py` (7). Known wrinkle: abbreviated names in state.json
  ("E. Martinez") don't match market rows — post-round state sync should use full names.

## 2026-07-06 — MID tackles/chances recalibrated against realized FIFA points

- **FIFA** (`games/fifa/model.py`) — MID non-goal stat credit recalibrated from realized
  R1–R5 data (official FIFA `roundPoints` joined to Holdet per-round events; residual after
  goals/assists/CS/appearance/cards isolates the tackles+chances credit, n=288 full-90
  MID player-rounds). Findings: realized credit averages **0.84 pts/90** vs the ~1.27/90
  the old constants paid every MID (+0.44/90 over-credit), and the goal/assist-share role
  shaping had **zero realized signal** (corr −0.00, OLS |t| < 0.7 — the real spread,
  ball-winners ~2/90 vs metronomes ~0.3/90, isn't predictable from our priors). New
  constants: flat `1.5` tackles/90 + `0.68` chances/90 (= 0.84 pts/90), shaping K's set
  to 0. Evidence gate (R2–R5 backtest, identical sims, old vs new): MID MAE 2.20 → 2.07
  and MID Spearman .215 → .229, improved in **every** round; GK/DEF/FWD untouched; MID
  cross-position bias now in line with other positions (was relatively over-ranked).
- **Holdet stat feed** (`core/realized.py` docstring) — three more event ids decoded by
  regressing FIFA roundPoints residuals on event counts: **222 = yellow card**,
  **219/223 = red card / own goal**, **465 = penalty save**.

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
