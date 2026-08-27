# FPL Phase 6 — The Horizon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop answering the World Cup's question. Publish the multi-gameweek view FPL managers actually plan against — a fixture-run grid, a squad optimised over a horizon rather than one Saturday, and a transfer plan that respects the one-free-transfer-a-week constraint.

**Architecture:** All of it runs on data already cached and already parsed. `fpl_api.parse_fixtures` returns all 380 fixtures across all 38 gameweeks, 100% carrying FDR, and Phase 5's `core/fpl_ratings.py` produces lambdas for any fixture whether the bookmakers have priced it or not. A new `core/fpl_horizon.py` computes per-club and per-player projections over a window; the articles consume it.

**Tech Stack:** Python 3.9 stdlib only. `unittest`. No new dependencies, no new data sources.

**Prior phase:** `docs/superpowers/plans/2026-08-03-fpl-phase5-differentiation.md`. Baseline: 810 tests passing on branch `fpl-phase4`, deployed to evmax.ai.

---

## Why this phase exists

Phase 4 built six articles and Phase 5 made them able to tell clubs apart. Both
answered the World Cup's question: **who scores most this Saturday.** That is the
right question for eight knockout rounds. It is the wrong one for a 38-week league,
and the owner named the gap (2026-08-04): "it seems like we are not looking at what
the usual FPL fantasy looks at and it's way more long term."

The rules make it concrete. From `bootstrap-static.game_config.rules` and
`games/fpl/rules.md`:

- **One free transfer per gameweek**, bankable to a maximum of 5
  (`max_extra_free_transfers = 4`). Anything beyond costs **−4 points**.
- **50% sell-on fee** on any price rise you realise.
- **Wildcard is unavailable in GW1** — `bootstrap-static.chips` gives its window as
  GW2–19, then GW20–38. Free Hit is the same. Only Bench Boost and Triple Captain
  are legal in GW1.

So a manager's GW1 squad is roughly 90% of their GW5 squad, and they cannot cheaply
undo it. **A squad optimised for one gameweek is a mistake paid off over a month.**

Our own published output demonstrates the failure. The GW1 ticker ranks Arsenal the
best clean-sheet buy on the board. Their next six:

```
GW1 vs COV (FDR 2)   GW2 at AVL (4)   GW3 vs CHE (4)
GW4 at SUN (3)       GW5 at BHA (3)   GW6 vs LEE (2)
```

True for Saturday, and it walks a reader into Villa away and Chelsea with one
transfer a week to escape. A six-week grid gives the opposite and correct advice:
take the GW1 pop, be out by GW2.

**Why this is newly cheap.** Before Phase 5 a six-gameweek ticker would have been 20
identical rows repeated six times — market odds reach only a week or two out, so
every future fixture fell to the neutral default. Phase 5's ratings work on any
fixture. The long-term view became possible precisely because of what was just
built, and the spec anticipated it: §8 already describes a multi-GW ticker
"market-derived for the near gameweek and priors-derived beyond it. Each column
states which."

## A correctness bug to fix on the way

The `wildcard` article is titled **"Draft squad & wildcard XI"** and is live on GW1,
where the wildcard chip cannot legally be played. For GW1 the same 15 players are
simply the season-opener squad, with no rebuild available until GW2. The article is
right; its name describes a chip the reader cannot use. Task 4 fixes the framing to
be gameweek-aware.

## Scope

**In:** a horizon engine, a fixture-run grid article, a horizon-optimised squad, and
a transfer-plan article.

**Out:** price-change prediction (needs net-transfer velocity we do not capture, and
it is a different data problem); chip-timing recommendations beyond flagging blanks
and doubles (needs realized data to calibrate); a true 38-gameweek transfer-path
optimiser (combinatorially large, and spec §12 already deferred it). Say so in the
changelog rather than half-building any of them.

---

## File structure

| File | Responsibility |
|---|---|
| `core/fpl_horizon.py` (create) | Per-club and per-player projections over a gameweek window. Pure; no I/O. |
| `games/fpl/model.py` (modify) | Build the horizon artifact alongside the single-gameweek one. |
| `evmax/fpl_articles.py` (modify) | `fixture_runs`, `horizon_squad`, `transfer_plan`. |
| `evmax/fpl_build.py` (modify) | Two new articles; gameweek-aware squad titling. |
| `evmax/render.py` (modify) | A grid renderer for the fixture-run table. |
| `evmax/writer.py`, `evmax/prompts.py` (modify) | Templates and glossary for the new slugs. |
| `tests/test_fpl_horizon.py` (create) | Window maths, blanks and doubles across a window. |

---

## Task 1: The horizon engine

**Files:** Create `core/fpl_horizon.py`; Test `tests/test_fpl_horizon.py`

A window is `range(gw, gw + n)`. For each club, aggregate across its fixtures in that
window: expected clean sheets, expected goals for and against, mean FDR, and a count
of fixtures (which is how blanks and doubles surface — a club can have 0 or 2 in any
single gameweek, so over six it might have 5 or 7).

**The decay question, and why it is a dial.** A fixture five weeks out is worth less
to a decision made today: team news, form and injuries will all move first. Weight
each gameweek by `config.FPL_HORIZON_DECAY ** offset`, defaulting to `0.85`. Set it
to `1.0` and every gameweek counts equally; set it to `0.0` and the horizon collapses
to the current gameweek, which must reproduce the existing single-gameweek numbers
exactly. **That last property is the calibration anchor and gets a test.**

- [ ] **Step 1: Write the failing tests**

```python
class TestWindow(unittest.TestCase):
    def test_window_is_the_requested_length(self):
        self.assertEqual(fpl_horizon.window(1, 6), [1, 2, 3, 4, 5, 6])

    def test_window_clamps_at_the_end_of_the_season(self):
        """GW36 with a 6-week horizon has only three gameweeks left."""
        self.assertEqual(fpl_horizon.window(36, 6), [36, 37, 38])

    def test_window_never_runs_past_38(self):
        self.assertEqual(fpl_horizon.window(38, 6), [38])


class TestClubHorizon(unittest.TestCase):
    def _matches(self):
        # ARS: GW1 home easy, GW2 away hard. COV: the mirror.
        return [
            {"fantasy_round": 1, "home": "ARS", "away": "COV",
             "p_cs_home": 0.40, "p_cs_away": 0.10,
             "exp_home_goals": 2.0, "exp_away_goals": 0.8,
             "home_difficulty": 2, "away_difficulty": 5, "market": True},
            {"fantasy_round": 2, "home": "COV", "away": "ARS",
             "p_cs_home": 0.12, "p_cs_away": 0.35,
             "exp_home_goals": 0.9, "exp_away_goals": 1.8,
             "home_difficulty": 5, "away_difficulty": 2, "market": False},
        ]

    def test_sums_clean_sheets_across_the_window_undecayed(self):
        out = fpl_horizon.club_horizon(self._matches(), ["ARS", "COV"],
                                       window=[1, 2], decay=1.0)
        self.assertAlmostEqual(out["ARS"]["exp_clean_sheets"], 0.75)   # 0.40 + 0.35
        self.assertEqual(out["ARS"]["fixtures"], 2)

    def test_decay_discounts_later_gameweeks(self):
        out = fpl_horizon.club_horizon(self._matches(), ["ARS", "COV"],
                                       window=[1, 2], decay=0.5)
        self.assertAlmostEqual(out["ARS"]["exp_clean_sheets"], 0.40 + 0.5 * 0.35)

    def test_zero_decay_reproduces_the_single_gameweek(self):
        """The calibration anchor: decay=0 must collapse to gameweek one exactly,
        so a horizon regression can be told apart from a ratings regression."""
        out = fpl_horizon.club_horizon(self._matches(), ["ARS", "COV"],
                                       window=[1, 2], decay=0.0)
        self.assertAlmostEqual(out["ARS"]["exp_clean_sheets"], 0.40)

    def test_a_blank_inside_the_window_lowers_the_fixture_count(self):
        """A club with five fixtures in a six-week window has a blank, and that is
        the single most actionable fact a run grid can carry."""
        out = fpl_horizon.club_horizon(self._matches(), ["ARS", "COV", "EVE"],
                                       window=[1, 2], decay=1.0)
        self.assertEqual(out["EVE"]["fixtures"], 0)

    def test_per_gameweek_detail_is_retained_for_the_grid(self):
        """The article renders a cell per gameweek, so the aggregate is not enough."""
        out = fpl_horizon.club_horizon(self._matches(), ["ARS"], window=[1, 2],
                                       decay=1.0)
        cells = out["ARS"]["by_gameweek"]
        self.assertEqual(cells[1]["opponent"], "COV")
        self.assertEqual(cells[1]["venue"], "H")
        self.assertEqual(cells[1]["difficulty"], 2)
        self.assertEqual(cells[2]["venue"], "A")

    def test_provenance_degrades_across_the_window(self):
        """Odds reach a week or two out; a six-week aggregate is mostly model-derived
        and must say so rather than inheriting GW1's `market` label."""
        out = fpl_horizon.club_horizon(self._matches(), ["ARS"], window=[1, 2],
                                       decay=1.0)
        self.assertEqual(out["ARS"]["basis"], "mixed")
```

- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** `window`, `club_horizon`, and `config.FPL_HORIZON_DECAY = 0.85` / `FPL_HORIZON_LENGTH = 6`.
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit.**

---

## Task 2: Simulating the window

`build_artifact` currently simulates one gameweek. The horizon needs the other five.

**Do not run six full Monte-Carlo simulations at 50k sims each** — that is six times
the build cost for a column that is a planning aid, not a published projection. The
match layer is what the run grid needs, and match-level clean-sheet and goal
expectations come straight from the fixture lambdas via a Poisson grid. No player
sim is required.

Add `fpl_horizon.match_projection(fixture)` computing `p_cs_home`, `p_cs_away`,
`exp_home_goals`, `exp_away_goals` analytically from `Fixture.lambdas()` — the same
maths `articles.match_predictions` already uses as its fallback path. Reuse it rather
than writing a third Poisson grid; check whether it can be lifted into a shared
helper without disturbing the World Cup path.

Cache the horizon alongside the gameweek artifact, keyed on the window and the same
source fingerprint.

- [ ] Tests: the analytic projection agrees with the simulated one for the current
      gameweek to within a stated tolerance (this is the check that the two paths
      have not drifted); a window costs one sim, not six.
- [ ] Commit.

---

## Task 3: The fixture-run grid article

Slug `runs`, title **"Fixture ticker — the next six"**.

One row per club, one column per gameweek, cell showing opponent, venue and FDR,
sorted by the horizon's expected clean sheets. This is the most-used planning tool in
FPL and the reason the phase exists.

`render._rank_table_html` renders flat columns and cannot express a grid, so this
needs a small dedicated renderer. Keep it in `render.py` beside the other table
builders, and give it the same responsive treatment — a 20×6 grid must scroll inside
its own container on mobile rather than forcing the page to scroll sideways.

- [ ] Tests: a blank renders visibly as a blank rather than an empty cell (they are
      different facts); a double renders both opponents in one cell; the grid is
      sorted by the horizon aggregate, not by gameweek one.
- [ ] The article must state its provenance honestly: near gameweeks market-derived
      where priced, later ones model-derived, per spec §8.
- [ ] Commit.

---

## Task 4: Horizon squad, and the wildcard naming fix

Two changes to the squad article.

**A. Optimise over the window.** `fpl_squad` currently maximises `x_points` for one
gameweek. Give it a horizon-weighted objective: each player's expected points summed
across the window with the same decay, using their club's fixture run. A cheap
defender at a club with an easy run should beat an expensive one facing a hard six
weeks — which is the actual decision, given one transfer a week.

Keep the single-gameweek objective available and tested. `decay=0` must reproduce
today's squad exactly.

**B. Fix the naming.** The wildcard chip's window is GW2–19 and GW20–38
(`bootstrap-static.chips`), so in GW1 it cannot be played. Title the article from the
gameweek: **"Season-opener squad"** for GW1, **"Wildcard squad"** from GW2. Derive
the legality from the chips data rather than hard-coding `if gameweek == 1` — the
same rule governs the second-half wildcard and a hard-coded 1 would be wrong at
GW20.

- [ ] Tests: the chip-window helper says wildcard is illegal at GW1 and legal at GW2
      and GW20; the title follows; a horizon-optimised squad differs from a
      single-gameweek one on a fixture set where the runs diverge; `decay=0`
      reproduces the current squad.
- [ ] Commit.

---

## Task 5: The transfer-plan article

Slug `transfers`, title **"Transfer plan — the next six"**.

This is the article that encodes the rules the owner asked about, and it must respect
them or it is worse than nothing:

- One free transfer per gameweek, bankable to 5.
- An extra transfer costs −4, so a move must clear 4 points **over the horizon** to
  be worth taking as a hit. That threshold is the article's whole argument and should
  be stated in the prose, not just applied silently.
- The 50% sell-on fee makes churn expensive.

Rank transfer targets by **horizon gain over the incumbent at the same position**,
not raw points. Flag which moves clear the −4 bar and which do not. Where a club's
run turns sharply (Arsenal GW1→GW2), say when to sell, not just what to buy.

**No squad state is available** — `games/fpl/state.json` is the owner's private
order book and is deliberately not a site input. So the public article ranks targets
against a *replacement-level* player at each position, the way
`articles.transfer_priorities` already does for the World Cup. Read that function
first; reuse its value-over-replacement shape if it fits, and say so.

- [ ] Tests: a target whose horizon gain is under 4 is labelled not-worth-a-hit; the
      free-transfer path is always ranked above the hit path; a club with a blank in
      the window is discounted appropriately.
- [ ] Prose template plus a prompt focus block that names the −4 threshold, the
      bankable-to-5 rule and the sell-on fee, so the LLM tier cannot invent
      different rules.
- [ ] Commit.

---

## Task 6: Wire in, rebuild, document

- [ ] Both new slugs into `fpl_build.ARTICLES`, `ARTICLE_TITLES`, `_COLUMNS`, with
      `_COL_LABEL` entries for every new column (a missing label ships a raw dict key
      as a table header — this has bitten twice).
- [ ] Full suite green. World Cup suites unedited.
- [ ] Rebuild GW1 into `dist/`, confirm `dist/round/` is byte-unchanged by checksum.
- [ ] **Report the Arsenal case explicitly:** does the run grid now say "GW1 pop,
      out by GW2"? That is the phase's headline result and the reason it was scoped.
- [ ] CHANGELOG: the horizon engine and its decay dial; the analytic match
      projection and why it is not six sims; the wildcard naming fix and that the
      chip is illegal in GW1; the transfer article's −4 threshold; and explicitly
      what is still out (price prediction, chip timing, the full 38-week optimiser).
- [ ] Commit, push.

---

## Self-Review

- **The owner's two asks map to Tasks 4 and 5:** "the general best team now" is the
  horizon squad, "one given some strategy" is the transfer plan, and the strategy in
  question is the one the rules actually impose — one transfer a week, −4 for a
  second, no wildcard until GW2.
- **Every task has a collapse-to-today anchor.** `decay=0` reproduces the current
  numbers in Tasks 1 and 4, so a horizon regression can always be told apart from a
  ratings regression.
- **No new data.** All 380 fixtures with 100% FDR coverage are already cached and
  already parsed; Phase 5's ratings already price unpriced fixtures. If an
  implementer reaches for a network call, they have misread the plan.
- **Honest provenance carries through.** A six-week aggregate is mostly
  model-derived, and Task 1 makes the basis label degrade rather than inherit
  gameweek one's.
- **A published error gets fixed:** the wildcard article is currently named for a
  chip GW1 readers cannot play.
