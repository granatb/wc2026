# FPL Phase 4b — the two squad slugs, the landing duel, the FPL rate page

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans, task-by-task.
> Work on the EXISTING branch `fpl-port-phase4` (Phase 4 landed there; do not merge, do
> not push). Suite: `python3 -m unittest discover -s tests -t .` — 631 tests green at
> start, green at every commit. Stage by explicit path only.

**Goal:** the owner-decided (2026-08-19) product shape: `/fpl/gw{N}/our-squad/` (the
hero) and `/fpl/gw{N}/consensus-squad/`, the landing led by our-squad with captains
second and a model-vs-consensus duel strip, and `/rate/` serving the FPL section.
Everything builds on Phase 4's Section descriptor, artifact columns, prose templates
and preflight — read `docs/superpowers/plans/2026-07-30-fpl-port-phase4.md` (including
its "Amended 2026-08-19" block) and the Phase 4 entry in CHANGELOG.md before starting.

**Context:** spec `docs/superpowers/specs/2026-07-28-fpl-port-design.md`; strategy
decisions in `docs/STRATEGY.md` (08-19 rows). The squads below were decided this
session from the horizon-optimized order book + expert consensus tally; provenance in
`docs/research/2026-08-19-squad-provenance.html`.

## The two squads (owner-approved content — do not re-optimize)

Both £100.0-legal, 2 GK / 5 DEF / 5 MID / 3 FWD, ≤3 per club. Names are FPL
`web_name`s — validate every one against `data/fpl/bootstrap.json` at build time and
fail preflight on any mismatch.

**Model squad ("The Model XI") — `games/fpl/state.json`** — 3-5-2, captain
B.Fernandes, vice Thiago:
- XI: Raya (GK); Virgil, Senesi, Tarkowski (DEF); B.Fernandes (c), Ndiaye,
  Gibbs-White, E.Le Fée, Szoboszlai (MID); Thiago, Watkins (FWD)
- Bench (order): 1. Sánchez (GK), 2. N.Williams (DEF), 3. Calvert-Lewin (FWD),
  4. Shaw (DEF)
- Identity: pure engine EV over the discounted GW1–6 horizon; no ownership shields —
  no Haaland by conviction.

**Consensus squad ("The Consensus XI") — `games/fpl/state_consensus.json`** — 3-5-2,
captain Haaland, vice B.Fernandes:
- XI: Verbruggen (GK); Mosquera, Calafiori, Shaw (DEF); B.Fernandes, Mbeumo,
  Szoboszlai, Groß, Sangaré (MID); Haaland (c), João Pedro (FWD)
- Bench (order): 1. Kinsky (GK), 2. Hume (DEF), 3. Calvert-Lewin (FWD), 4. Diop (DEF)
- Identity: best-follower — mention-tally across the 7-source expert corpus
  (`docs/research/2026-08-19-gw1-experts/`), majority captain, shield included.

## Tasks

- [ ] **1. State schema + the two state files.** Extend the `games/fpl/state.json`
  shape (it still holds the `_example`): `team_name`, `strategy` ("model" |
  "consensus"), `squad` of 15 entries {name, position, is_starter, bench_order
  (null for XI), is_captain, is_vice}, `chips_used`, `free_transfers`. Write both
  files with the squads above. Pure loader + validator in `games/fpl/state.py` (new):
  quota/budget/club-cap legality, every name resolves against bootstrap (ß/diacritics
  intact — names are exact web_names), exactly 1 captain + 1 vice, bench_order 1–4
  with the GK first. Tests for every validation failure mode. Prices come from
  bootstrap at load time, never stored.

- [ ] **2. Squad article data in `evmax/fpl_articles.py`.** `squad_article(state,
  rows)`: join state to artifact rows, XI/bench split in state order, per-player
  xPts/ceiling/captain_ev/value columns, XI total, captain doubled in the projected
  total, formation string derived from the XI. Works identically for both state
  files. Unit tests incl. a state name missing from rows (must raise, not skip).

- [ ] **3. The two slugs.** `our-squad` and `consensus-squad` join ARTICLES with
  titles "Our squad" and "The consensus XI" (keep <title> under ~65 chars with the
  "— Gameweek N | evmax" suffix). Hand-written prose templates per Phase 4's
  standard: our-squad states the model's reasoning (horizon EV, market lambdas, the
  no-Haaland conviction, captain by EV); consensus-squad states the method
  (mention-tally across 7 named-in-prose-as-"expert consensus" sources, majority
  captain) and that its minutes come from sourced research notes. NEVER name
  bookmakers; never reproduce expert text. Both pages get the full page family
  (JSON envelope, .md twin, sitemap, llms.txt) exactly like the six existing slugs.

- [ ] **4. Landing duel.** The FPL landing leads with our-squad as the hero card,
  captains second, then the feed. Add a compact duel strip: both squads' projected
  XI totals (captain doubled) side by side, labeled "model" vs "consensus" — data
  from Task 2, no new simulation. Post-GW realized-vs-projected is explicitly OUT
  of scope (needs live data; next phase). WC landing byte-identical (regression
  gate as in Phase 4).

- [ ] **5. `/rate/` serves the FPL section.** Section-aware rate page: when building
  a gameweek, `/rate/` copy says FPL (title "Rate my FPL team | …", squad-shape hints
  15 = 2/5/5/3), reads the gameweek players feed Phase 4 already emits, and the nav
  pill highlights per section. WC builds keep today's WC rate page byte-identical.
  The pitch-layout picker upgrade is NOT in scope — slot autocomplete stays.

- [ ] **6. Pipeline + preflight + e2e.** `--gw` builds all eight articles; preflight
  additionally checks: both state files load and validate, every state name matches
  the artifact rows, projected totals are finite. e2e build test into a temp dir
  (8 articles + landing + rate). Then a real GW1 production build into `dist/`
  verified by hand: hero renders, duel strip shows both totals, `/round/` untouched
  (before/after listing identical). CHANGELOG entry; suite count updated.

## Out of scope
Realized-points recap (needs live GW data), transfers/chip articles, pitch-style
rate picker, EO/rank columns, merging or pushing the branch.
