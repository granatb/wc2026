# Phase 2A — Distributions (engine → card → page)

> REQUIRED SUB-SKILL: superpowers:executing-plans, task-by-task.
> Branch `phase2-distributions` off main. Suite 982 green at start, green at every
> commit. Python 3.9 stdlib only, `from __future__ import annotations`, explicit-path
> staging, no push/merge/deploy. Never touch `core/engine_events.py`. WC pages
> byte-identical. Frozen GW1 artifacts + `evmax/assets/projections/` untouched.
> Spec: `docs/superpowers/specs/2026-08-26-phase2-design.md` (D1, D2, P1).
> NOTE: a parallel agent works `phase2-dataset-mcp` on dataset/MCP/accuracy — it owns
> `evmax/fpl_build.py`'s WRITE-OUT block and new files under `mcp/`, `docs/DATASET.md`.
> You own row derivation, `games/fpl/model.py`, `evmax/fpl_players.py`, the new article.
> If you must touch fpl_build, keep it to the article-registration lines and say so.

### Task 1: histogram capture
**Files:** `games/fpl/model.py`, test `tests/test_fpl_model.py`
`SimPointsAccumulator.histogram(name) -> dict[int,int]`: counts of each integer total
over ALL sims (zero-padded for non-appearances, same convention as `mean`). Keys are
ints, sparse. `build_rows` adds `"distribution": points.histogram(name)` to each row
(inside the cached artifact — the simcache key already covers the model source, so a
new column invalidates correctly).
- [ ] Failing tests: hand-built accumulator over 10 sims → exact PMF; counts sum to
  `sims`; a never-appearing player is `{0: sims}`; the histogram's mean reconstructs
  `mean(name)` to 1e-9.
- [ ] Run to verify failure. - [ ] Implement. - [ ] Full suite. - [ ] Commit
  `feat(fpl): per-player point histograms captured from the sims`.

### Task 2: derived distribution stats
**Files:** `games/fpl/model.py` (`_derive_row`), test `tests/test_fpl_model.py`
From `distribution` derive, on the row: `p10`, `median`, `p90` (percentiles over the
PMF, lower-bound convention: smallest x with cumulative ≥ q), `mode` (highest-count
value; ties → lowest), `p_haul` (P ≥ 10), `p_blank` (P ≤ 2). Round probabilities to 4dp,
percentiles are ints. Document in the `_derive_row` docstring that these are WEEK-level
(unlike bonus/defcon per-match, per the existing note).
- [ ] Failing tests: hand-built PMF with known quartiles; tie-break on mode; p_haul on a
  PMF with mass exactly at 10 (inclusive); all six fields present on a real GW2 row.
- [ ] Run. - [ ] Implement. - [ ] Full suite. - [ ] Commit
  `feat(fpl): floor, most-likely, ceiling and haul odds derived from the histogram`.

### Task 3: the card's distribution chart
**Files:** `evmax/fpl_players.py`, test `tests/test_fpl_players.py`
`_distribution_svg(payload) -> str`: inline SVG bar chart of the PMF (bars for points
0..max where count > 0, clipped at the 99th percentile so one freak sim can't flatten
it), floor/mode/ceiling marked with thin rules + tiny labels, site palette, ~180x54.
Deterministic (no RNG). Replaces the reserved slot in `card_html`: the chart renders in
the card body under the stat rows with the caption "50,000 simulations · floor P10 ·
most likely · ceiling"; the premium slot text becomes "🔒 Premium — coming soon:
your-team fit · dossier alerts" (D1: distributions are free). Per-player JSON gains the
full `distribution` + the six derived fields (replacing `distribution: null`).
- [ ] Failing tests: chart present in card html for a payload with a distribution; ABSENT
  (graceful) when the artifact predates histograms; premium slot no longer claims
  distribution; JSON carries `distribution` + `p10`/`median`/`mode`/`p90`/`p_haul`/
  `p_blank`; SVG is deterministic across two calls.
- [ ] Run. - [ ] Implement. - [ ] Full suite. - [ ] Commit
  `feat(fpl): the distribution chart lands on the player card`.

### Task 4: `/fpl/gw{N}/distributions/` — the ninth article
**Files:** `evmax/fpl_articles.py`, `evmax/writer.py`, `evmax/fpl_build.py` (article
registration ONLY), tests `tests/test_fpl_articles.py`, `tests/test_fpl_site.py`
Pure ranking fn `distributions(rows)`: top 8 by `captain_ev` with their PMF summaries,
plus `beats(a, b)` = P(A > B) + 0.5·P(A = B) computed by convolving the two PMFs
(independence approximation — the prose MUST say so). Article slug `distributions`,
title "Points distributions", full page family like every other slug. Hand-written
prose template: the captain candidates' spreads, who has the higher floor vs the higher
ceiling, the haul/blank table. No bookmaker names.
- [ ] Failing tests: `beats` on two hand-built PMFs (known answer, incl. the tie half-
  credit); ranking order; the article renders with 8 rows; the prose states the
  independence approximation; sitemap/llms.txt carry the slug; JSON envelope shape.
- [ ] Run. - [ ] Implement. - [ ] Full suite. - [ ] Commit
  `feat(fpl): the distributions article — spreads, floors and haul odds`.

### Task 5: verification
- [ ] Build GW2 into a temp dir; screenshot a player page and the distributions article
  with headless Chrome into
  `/private/tmp/claude-501/-Users-bartlomiej-granat/3d62b63f-34db-4a8c-a6d3-c80067810eb9/scratchpad/phase2/`
  (`card.png`, `distributions.png`); LOOK at them; iterate until the chart is legible at
  card size. - [ ] CHANGELOG entry. - [ ] Commit.
