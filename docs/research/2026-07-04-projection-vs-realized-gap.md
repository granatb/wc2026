# FIFA fantasy: projection-vs-realized gap, quantified (2026-07-04)

Owner reports his own FIFA WC fantasy team scoring 100+ pts/round while the engine's
projected XI total (`scripts/rate_team.py` / evmax `/rate/`) sits at 50-60. This note
reconstructs his actual squads, computes engine-projected vs. official-realized totals,
and decomposes the gap. **Scope note applies only to FIFA fantasy** — Holdet is a
separate scoring system and unaffected by anything here.

## Data-availability constraint

`games/fifa/state.json` has only ever been committed twice:

| commit | `current_round` | maps to | squad locked |
|---|---|---|---|
| `dc17578` | 2 | Round 2 (group MD2, 18-24 Jun) | 3-5-2, captain Ruben Vargas |
| `2e34c77` | 4 | Round 4 (R32 knockout, 28 Jun-4 Jul) | 4-4-2, captain Mbappé, chip "Qualification Booster" |

Round-to-date mapping confirmed from `data/schedule.json`'s `fantasy_round` field:
R1/R2 = group matchdays 1-2, R3 = group MD3 (excluded from the public track record per
an existing owner decision in `evmax/backtest.py`), **R4 = Round of 32**, R5 = Round of
16 (deadline was today, 4 Jul 19:00 — squad not yet locked, hence the uncommitted
working-tree edit to `state.json` is just R4's squad carried forward with metadata
prepped for R16, not a distinct playable round).

**Rounds 1 and 3 have no recoverable owner squad anywhere in the repo** — no git
snapshot, no reddit rate-my-team thread, no other log of his actual picks. Only R2 and
R4 are reconstructed below. Treat this as a 2-round sample, not four.

## Method

- Owner's actual XI + captain: from the two `state.json` snapshots above.
- Engine projected total: `scripts/rate_team.py`'s `build_rows(round, sims)` (the same
  path used for live rate-my-team replies), captain doubled. Both rounds ran with an
  **empty** `player_rates_rN.json` (odds-only market blend never populated for R2 or
  R4), so the two projections are apples-to-apples.
- Realized total: official FIFA fantasy feed cache (`data/fifa/players.json`,
  `stats.roundPoints[str(round)]`), matched via `core.fifa_api.lookup` — the same
  source `evmax/backtest.py` grades against.
- Level bias: `realized - projected`, averaged across the **entire matched player
  pool** for that round (n=740 for R2, n=509 for R4), not just the owner's 11 — isolates
  a systematic engine-wide effect from anything specific to his picks.
- Bench/manual-sub optionality: best realized-points XI reachable from the full 15-man
  squad while respecting the locked formation's per-position starting counts (e.g. R2's
  3-5-2 = 1 GK/3 DEF/5 MID/2 FWD). Assumes any such final XI was reachable via
  in-round manual subs before each entering player's own kickoff — a reasonable
  approximation given the rules (`games/fifa/rules.md`), not a strict per-kickoff
  feasibility proof.
- Chip: "Qualification Booster" (R4 only) — per `research/rounds/r4-news-2026-06-28.md`,
  "+2 per starter who advances." Not implemented anywhere in the engine, so it is
  **entirely absent** from the projected total. Computed here as `+2 × (starters whose
  team is not `status: eliminated` post-R32)`, using `data/fifa/players.json`'s live
  status field. **Assumption, unverified against the FIFA feed's internals:** this is
  added as a separate line on top of summed `roundPoints`; if FIFA's feed already folds
  the booster into individual `roundPoints`, this double-counts it.

## Results

### Round 2 (group MD2, 3-5-2, captain Ruben Vargas, no chip)

| | engine projected | realized |
|---|---:|---:|
| Static XI (captain ×2) | 62.03 | 87.00 |

Gap = **+24.97**.

- Pool-wide level bias: **+0.636 pts/player** (n=740) → ×11 starters = **+7.0** (28% of gap)
- Captain-specific variance: Ruben Vargas alone (real 15 vs projected 3.46, doubled)
  contributes **+23.08** of the +24.97 — i.e. one low-owned chain-captain pick accounts
  for essentially the entire gap on its own.
- Bench optionality (hindsight): swapping bench DEF Nuno Mendes (15) + Muñoz (14) in for
  starting DEF Kimmich (2) + Gabriel Magalhães (7) = **+20.0** pts available that the
  static XI didn't capture.
- Hindsight-optimal static-legal total: 87 + 20 = **107** — already above "100+" from
  bench management alone, without needing to assume any chip or lucky-timing effect.

### Round 4 (R32 knockout, 4-4-2, captain Mbappé, chip = Qualification Booster)

| | engine projected | realized |
|---|---:|---:|
| Static XI (captain ×2) | 65.98 | 77.00 |

Gap = **+11.02**.

- Pool-wide level bias: **+0.363 pts/player** (n=509) → ×11 = **+4.0** (36% of gap)
- Bench optionality (hindsight): only **+1.0** (Bruno Fernandes for Bellingham) — this
  bench was already well-constructed, unlike R2's.
- Chip: 9 of 11 starters advanced past R32 (only Kimmich + Wirtz didn't — Germany
  eliminated) → **+18.0** (see assumption above).
- Combined ceiling: 77 (static realized) + 1 (bench) + 18 (chip) = **96** — close to,
  though slightly under, a "100+" claim; the remainder is plausibly live captain-chain
  execution (his own notes show a planned Mbappé→Kane→Messi chain) or timing on the
  scouting bonus, neither of which is reconstructable from `state.json` alone.

## Does the known "-2.3 xPts/player" bias explain this?

No — and applying it here would be a category error. That figure
(`docs/research/2026-07-03-engine-roadmap-full-synthesis.md`) is the engine's own xPts
running low **against Rotowire's projections**, in group-stage matches, and the roadmap
doc itself flags it as unresolved: it explicitly lists "settles whether the −2.3 gap is
bias (fixable) or Rotowire miscalibration" and "split the −2.3 gap into bias vs
irreducible variance" as open work.

This analysis instead measures engine-vs-**realized** directly, which is the relevant
comparison for "why does the owner's score beat the engine's total":

- Directly measured level bias is **+0.4 to +0.6 pts/player** — roughly 4-6x smaller
  than -2.3, and it only explains **28-36%** of either round's static gap.
- Naively applying -2.3 × 11 starters (+25.3) happens to roughly match R2's gap
  (24.97) by coincidence — but R2's gap is 92% one captain's variance, not a broad
  per-player shortfall, so the "match" is not evidence the bias is real at that
  magnitude. For R4, -2.3 × 11 (+25.3) is **more than double** the entire gap (11.02) —
  applying it would push projected totals well past realized, i.e. it overcorrects.
- The dominant drivers of "he scores 100+, we project 50-60" are, in order: (1) high
  variance on differential/chain captain picks, amplified ×2 by the armband, (2) bench
  management catching rotation/differential starters the engine didn't back, and — R4
  only — (3) a chip worth +18 pts that the engine doesn't model at all. Systematic
  level bias is real but a minor contributor (~30%), not the primary explanation.

**Additionally: the -2.3 figure itself is stale.** Per prior project notes, that number
was measured on R2 *before* the 2026-06-22 rules-fidelity pass (correct goal values,
scouting-bonus EV, POTM/DEF-defcon correction, `GOAL_CONCENTRATION` tuning). After that
pass, the same R2-vs-Rotowire cross-check the -2.3 figure came from had already closed
to a mean ratio of ~0.85-0.90 (Pearson r ~0.6) — i.e. the "known -2.3/player" bias
description in this task's brief predates fixes that substantially addressed it. It
should not be treated as current without re-running that specific Rotowire cross-check
post-fix.

## Recommendation

Do not touch `DEVIG_METHOD` defaults (the n≥40 evidence gate in
`scripts/devig_bakeoff.py` correctly isn't met by a 2-round sample). No code change is
justified by this data. Two things worth doing to evmax build output:

1. **Display-level note**, not a number change: on any published "projected XI total,"
   add a line to the effect of "median estimate — captain and differential picks are
   high-variance; a single haul or a well-timed manual sub commonly swings the realized
   total by 15-25+ pts in either direction, more than any known systematic bias." This
   is honest about *why* totals diverge without implying the projection itself is
   miscalibrated.
2. **Model the chip mechanically, not via calibration.** The Qualification Booster is a
   deterministic, computable effect (+2 × advancing starters) the engine currently
   omits entirely for knockout rounds — worth more (+18 in this one round) than the
   entire measured level bias. This is a real gap in coverage, separate from any
   xPts-accuracy question, and is the highest-value fix if the site wants knockout-round
   projected totals to be closer to what a chip-using manager will actually see.

No additive/multiplicative correction on xPts is recommended given the small,
stage-inconsistent measured bias (+0.636 in a group round vs +0.363 in a knockout
round) and the fact that it explains a minority of the gap either way.
