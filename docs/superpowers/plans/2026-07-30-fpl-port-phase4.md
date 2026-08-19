# FPL Port — Phase 4 Implementation Plan (the site)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish six Fantasy Premier League articles per gameweek at `/fpl/gw{N}/`, built from the Phase 1–3 engine, with `/` becoming the GW1 landing page — while every published World Cup URL under `/round/N/` keeps serving byte-identical HTML.

**Architecture:** `render.py` gains a `Section` descriptor (paths, labels, unit words) threaded through the page functions with a World-Cup default, so no existing call site changes behaviour. FPL-specific ranking and squad-building live in a new `evmax/fpl_articles.py`; the build pipeline lives in a new `evmax/fpl_build.py`, reached via `python3 -m evmax.build --gw N`. The model layer (`games/fpl/model.py`) grows the derived columns and per-match summaries the articles consume, inside the cached artifact.

**Tech Stack:** Python 3.9 stdlib only. `unittest` (the suite is `unittest`, not pytest). No new third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-07-28-fpl-port-design.md` — Phase 4 row in §11.

---

## Context an engineer needs before starting

**Run the suite:** `python3 -m unittest discover -s tests -t .` — currently **543 tests, passing**, ~100s. It must stay green at every commit. Run it before you start so you know the baseline is clean on your machine.

**Environment:** Python is `python3` (3.9.6); there is no bare `python`. `dict[str, int]` and `int | None` are legal only in annotation position, which works because every module carries `from __future__ import annotations`. New modules must carry it too.

**`tests/test_engine_determinism.py` pins the shared engine's exact output.** Nothing in this phase should touch `core/engine_events.py`. If that test fails, stop and work out why before continuing.

**The World Cup site is the regression gate.** `/track-record/` grades our published WC predictions off frozen snapshots; `tests/test_site_render.py` (930 lines) and `tests/test_site_build.py` pin the WC page output. Every signature you change in `render.py` gets a **default that reproduces today's behaviour exactly**. If a WC render test needs editing, you have changed the wrong thing.

**Two owner decisions already made (2026-07-30), do not re-litigate:**
1. **`/` becomes the FPL landing at GW1.** The FPL build writes both `/index.html` and `/fpl/gw{N}/index.html`. The WC tree under `/round/N/` is never touched by the FPL build — D5's "stays live forever" commitment is about those URLs, not the root. The WC landing survives at `/round/8/`.
2. **Hand-written prose templates for all six FPL slugs**, with the LLM tier on top. A `--no-llm` build must read like a real article, not "Gameweek analysis: Defcon".

**Amended 2026-08-19 (owner):** a seventh slug, **`our-squad`, is the hero** — the site's
own real 15 (engine-picked from `games/fpl/state.json`), with transfers, captain and the
reasoning, frozen at deadline like every article. The landing leads with `our-squad`,
`captains` second; the other five are the supporting feed. From GW2 the article opens
with last GW's realized-vs-expected recap (the WC "Our XI so far" pattern, but as prose +
table inside the frozen article of the NEXT gameweek — published articles stay frozen).
The wildcard/knapsack article stays, but it is advice for wildcarders, not our team.

**Amended 2026-08-19 (owner), second squad:** an eighth slug, **`consensus-squad`** ("The
Consensus XI") — the best-follower team: mention-tally across the expert research corpus
(`docs/research/*-gw1-experts/` pattern, refreshed per GW from Bartek-supplied/curated
notes), built quota/budget/club-legal, majority captain (Haaland GW1). Published and
graded weekly next to `our-squad`; the landing shows both squads as a duel plus
`captains`. Both squads play under real rules (FT banking, hits, chips) — two persistent
states, e.g. `state.json` (model) + `state_consensus.json`. GW1 baseline: consensus 15
costs £99.5; model-vs-consensus XI xPts 68.21 vs 54.45 as-modelled, 68.20 with
expert-asserted starters — the entire gap is start-probability information, which is the
point of running both.

**Data is already cached.** `data/fpl/bootstrap.json`, `data/fpl/fixtures.json` and `data/fpl/defcon_backfill.json` exist locally: 563 players, 20 teams, prices £4.0–£15.5 (median £5.0). You can build GW1 offline without touching the network. `data/` is gitignored — never commit anything under it.

**What Phase 4 is NOT.** Not the templating refactor (deferred to the September international break, spec §12) — you are adding a second page family that shares primitives, not collapsing both into one template engine. Not transfers, chip-timing or `ep_next`-comparison articles. Not the backtest harness (there is no realized FPL data until GW1 completes, spec §7.4) — but Phase 4 *does* write the projection snapshots that harness will later grade.

**The six articles and their slugs** (spec §8). Keep titles short: the `<title>` becomes `"{title} — Gameweek N | evmax"` and Bing errors above ~65 characters.

| Slug | Title | Engine output |
|---|---|---|
| `captains` | Best captain picks | 2× xP, ordered, annotated with kickoff order |
| `wildcard` | Draft squad & wildcard XI | £100.0m knapsack, max 3/club, legal formation |
| `ticker` | Fixture ticker — clean sheets | Per-club CS probability, expected goals for/against |
| `defenders` | Best defenders & keepers | DEF/GK xP with CS, DefCon and bonus split out |
| `efficiency` | Best value — points per million | xP per £m, price-tiered |
| `defcon` | DefCon leaders | `P(CBIT ≥ 10)` / `P(CBIRT ≥ 12)` |

---

## File structure

| File | Responsibility |
|---|---|
| `games/fpl/model.py` (modify) | Derived row columns + per-match summaries, both inside the cached artifact. |
| `core/simcache.py` (modify) | One helper: list stored artifacts for a gameweek, so preflight can report an *unexpected* miss. |
| `evmax/render.py` (modify) | `Section` descriptor; page functions take `section=WC` and default to today's output. |
| `evmax/fpl_articles.py` (create) | FPL ranking + squad building. Pure; no I/O, no HTTP. |
| `evmax/fpl_build.py` (create) | The GW build pipeline and its preflight. Owns all file writing. |
| `evmax/writer.py` (modify) | Section-aware prose cache path; six FPL templates. |
| `evmax/prompts.py` (modify) | `unit` word + FPL field glossary in the LLM prompt. |
| `evmax/build.py` (modify) | `--gw` routes to `fpl_build`; `--round` keeps today's behaviour. |
| `tests/test_fpl_articles.py` (create) | Ranking, squad legality, ticker blanks/doubles. |
| `tests/test_fpl_site.py` (create) | Section rendering, preflight, end-to-end build into a temp dir. |
| `tests/test_fpl_model.py` (modify) | Double-gameweek cross-check; new row columns; match summaries. |

---

## Task 1: Settle the carried double-gameweek bonus question

The Phase 3 plan closes with an open question: `BonusAccumulator.expected()` returns a per-match average that `total_points` scales by `played / sims`, which for a double gameweek approaches 2.0 — so the product *may* already be the correct sum, but nobody has verified it. Option 1 from that note is the cheap test: build a synthetic double-gameweek fixture pair and assert `total_points` agrees with `SimPointsAccumulator.mean()`, which sums per sim explicitly and is already double-GW tested.

Do this first. If it fails, every `x_points` number the rest of Phase 4 publishes is wrong for doubles, and you want to know before six articles are built on top of it.

**Files:**
- Test: `tests/test_fpl_model.py`

- [x] **Step 1: Write the failing test**

Append to `tests/test_fpl_model.py`:

```python
class TestDoubleGameweekTotalPoints(unittest.TestCase):
    """The carried Phase 3 question: does total_points sum bonus across a double?

    SimPointsAccumulator.mean() sums each sim's matches explicitly and has its own
    double-gameweek coverage, so it is the reference. total_points goes through the
    older assembly path (expected_points + conditional components scaled by
    played/sims) and is the one in question.
    """

    def _double_gameweek_samples(self, sims=4000):
        """Simulate a synthetic gameweek where one team plays TWICE."""
        from core import fixtures
        from core.ratings import PlayerPrior

        squads = {
            "Alpha": [PlayerPrior(name="A-Striker", position="FWD", start_prob=1.0,
                                  exp_minutes=90, goal_share=0.4, assist_share=0.2),
                      PlayerPrior(name="A-Keeper", position="GK", start_prob=1.0,
                                  exp_minutes=90, saves_per90=3.0)],
            "Beta": [PlayerPrior(name="B-Striker", position="FWD", start_prob=1.0,
                                 exp_minutes=90, goal_share=0.4, assist_share=0.2)],
            "Gamma": [PlayerPrior(name="G-Striker", position="FWD", start_prob=1.0,
                                  exp_minutes=90, goal_share=0.4, assist_share=0.2)],
        }
        saved = list(fixtures.SCHEDULE)
        try:
            fixtures.SCHEDULE.clear()
            for mid, home, away in (("dgw-1", "Alpha", "Beta"),
                                    ("dgw-2", "Gamma", "Alpha")):
                fixtures.SCHEDULE.append(fixtures.Fixture(
                    match_id=mid, home=home, away=away,
                    kickoff=datetime(2026, 8, 21, 17, 30, tzinfo=timezone.utc),
                    stage="GW", fantasy_round=99, neutral=False,
                    lam_home=1.5, lam_away=1.2))
            baselines = {}
            bonus = fpl_model.BonusAccumulator(baselines)
            points = fpl_model.SimPointsAccumulator(baselines, sims)

            def hook(match_id, rows, sim_index):
                bonus.observe(match_id, rows, sim_index)
                points.observe(match_id, rows, sim_index)

            samples, _ = engine_events.simulate_round(
                99, sims=sims, seed=4242,
                priors=lambda team: squads.get(team, []),
                per_match_hook=hook)
            return samples, engine_events.event_means(samples), bonus, points
        finally:
            fixtures.SCHEDULE.clear()
            fixtures.SCHEDULE.extend(saved)

    def test_double_gameweek_player_agrees_with_per_sim_distribution(self):
        samples, means, bonus, points = self._double_gameweek_samples()
        ps = samples["A-Striker"]          # Alpha plays twice
        assembled = fpl_model.total_points(
            means["A-Striker"], ps, fpl_model._conceded_series(ps),
            bonus=bonus.expected("A-Striker"))
        reference = points.mean("A-Striker")
        self.assertAlmostEqual(assembled, reference, delta=0.35,
                               msg=f"double-GW mismatch: assembled={assembled:.3f} "
                                   f"per-sim={reference:.3f}")

    def test_single_fixture_player_still_agrees(self):
        """Control: a single-fixture player must agree just as closely, so a
        failure above is attributable to the double and not to general drift."""
        samples, means, bonus, points = self._double_gameweek_samples()
        ps = samples["B-Striker"]          # Beta plays once
        assembled = fpl_model.total_points(
            means["B-Striker"], ps, fpl_model._conceded_series(ps),
            bonus=bonus.expected("B-Striker"))
        self.assertAlmostEqual(assembled, points.mean("B-Striker"), delta=0.35)
```

Check the imports at the top of `tests/test_fpl_model.py` — it must import `datetime`, `timezone`, `engine_events` and `fpl_model`. Add whatever is missing.

- [x] **Step 2: Run it**

```bash
python3 -m unittest tests.test_fpl_model.TestDoubleGameweekTotalPoints -v
```

This test may PASS on the first run — that is a legitimate outcome, not a mistake. It is a **characterisation test** answering an open question, so both results are informative:

- **PASS** → the per-match average × `played/sims` really does reconstruct the sum. Record that in Step 3 and move on.
- **FAIL** → the assembly path under-counts (or over-counts) bonus across a double. Take option 2 from the Phase 3 note: change `build_rows` (Task 2) to read `x_points` off `points.mean(name)` instead of `total_points(...)`, which removes the whole class of question. Do not hand-patch the scaling factor.

- [x] **Step 3: Record the answer**

Add a comment above `BonusAccumulator.expected` in `games/fpl/model.py` stating what the test established. If it passed:

```python
    def expected(self, name: str) -> float:
        """Mean bonus per MATCH APPEARANCE, not per sim.

        Double gameweeks: total_points scales this by sample.played / sample.sims,
        which for a two-fixture team approaches 2.0 — so the product reconstructs
        the SUM across both matches. Verified 2026-07-30 against
        SimPointsAccumulator.mean() on a synthetic double
        (tests/test_fpl_model.TestDoubleGameweekTotalPoints); the question carried
        over from the Phase 3 plan is settled, and this scaling is load-bearing —
        do not "simplify" it to a per-sim divisor.
        """
```

- [x] **Step 4: Run the full suite**

```bash
python3 -m unittest discover -s tests -t .
```

Expected: 545 tests, all passing.

- [x] **Step 5: Commit**

```bash
git add tests/test_fpl_model.py games/fpl/model.py && git commit -m "test(fpl): settle the double-gameweek bonus question with a synthetic cross-check"
```

---

## Task 2: Derived row columns the articles need

`build_rows` currently emits `name, team, position, x_points, price, ownership_pct, ceiling, bonus, defcon`. The six articles additionally need `captain_ev` (captains), `value` (efficiency), `p_defcon` (the DefCon article's headline stat — a probability, not points), `cs_points` (the defenders article splits clean-sheet points out), and `kickoff` (captain ordering).

Rounding is applied here too: the WC rows round on the way out and the FPL rows do not, which makes cached artifacts noisier than they need to be and prints 14 significant figures into the JSON feed.

**Files:**
- Modify: `games/fpl/model.py`
- Test: `tests/test_fpl_model.py`

- [x] **Step 1: Write the failing test**

Append to `tests/test_fpl_model.py`:

```python
class TestDerivedRowColumns(unittest.TestCase):
    def test_derived_columns_present_and_consistent(self):
        row = fpl_model._derive_row(
            name="Testy", means={"team": "ARS", "position": "DEF",
                                 "clean_sheet": 0.4},
            x_points=6.0, ceiling=11.0, bonus=0.5, defcon_pts=1.2,
            p_defcon=0.6, price=5.5, ownership=12.3,
            kickoff="2026-08-21T19:00:00+00:00")
        self.assertEqual(row["captain_ev"], 12.0)
        self.assertEqual(row["value"], 1.091)          # 6.0 / 5.5
        self.assertEqual(row["p_defcon"], 0.6)
        self.assertEqual(row["cs_points"], 1.6)        # 0.4 * CS_PTS["DEF"] == 4
        self.assertEqual(row["kickoff"], "2026-08-21T19:00:00+00:00")

    def test_value_is_none_without_a_price(self):
        row = fpl_model._derive_row(
            name="Pricy", means={"team": "ARS", "position": "MID",
                                 "clean_sheet": 0.0},
            x_points=6.0, ceiling=9.0, bonus=0.0, defcon_pts=0.0, p_defcon=0.0,
            price=None, ownership=None, kickoff=None)
        self.assertIsNone(row["value"])
        self.assertEqual(row["captain_ev"], 12.0)

    def test_p_defcon_is_the_points_column_halved(self):
        """defcon points are exactly 2 x P(threshold) x P(played), so the two
        columns must never disagree — the article prints one and the table the
        other."""
        row = fpl_model._derive_row(
            name="Blocker", means={"team": "BUR", "position": "DEF",
                                   "clean_sheet": 0.2},
            x_points=4.0, ceiling=7.0, bonus=0.0, defcon_pts=1.44, p_defcon=0.72,
            price=4.5, ownership=1.0, kickoff=None)
        self.assertAlmostEqual(row["defcon"], row["p_defcon"] * fpl_model.DEFCON_PTS,
                               places=6)

    def test_build_rows_carries_the_new_columns(self):
        rows = _tiny_build_rows()      # helper defined below
        self.assertTrue(rows)
        for key in ("captain_ev", "value", "p_defcon", "cs_points", "kickoff"):
            self.assertIn(key, rows[0], f"{key} missing from build_rows output")
```

Add this module-level helper to the same file, near the other helpers:

```python
def _tiny_build_rows(sims=300, gameweek=98):
    """A 2-team, 1-fixture synthetic gameweek run through build_rows, cache off."""
    from core import fixtures
    from core.ratings import PlayerPrior

    squads = {
        "Home": [PlayerPrior(name="H-Def", position="DEF", start_prob=1.0,
                             exp_minutes=90, defcon_per90=9.0),
                 PlayerPrior(name="H-Fwd", position="FWD", start_prob=1.0,
                             exp_minutes=90, goal_share=0.5)],
        "Away": [PlayerPrior(name="A-Gk", position="GK", start_prob=1.0,
                             exp_minutes=90, saves_per90=3.5)],
    }
    players_by_name = {
        "H-Def": {"name": "H-Def", "price": 4.5, "ownership": 2.0,
                  "minutes": 2700, "bps": 500},
        "H-Fwd": {"name": "H-Fwd", "price": 8.0, "ownership": 30.0,
                  "minutes": 2700, "bps": 600},
        "A-Gk": {"name": "A-Gk", "price": 5.0, "ownership": 5.0,
                 "minutes": 3420, "bps": 700},
    }
    saved = list(fixtures.SCHEDULE)
    try:
        fixtures.SCHEDULE.clear()
        fixtures.SCHEDULE.append(fixtures.Fixture(
            match_id="tiny-1", home="Home", away="Away",
            kickoff=datetime(2026, 8, 21, 19, 0, tzinfo=timezone.utc),
            stage="GW", fantasy_round=gameweek, neutral=False,
            lam_home=1.6, lam_away=1.1))
        return fpl_model.build_rows(
            {t: s for t, s in squads.items()}, players_by_name,
            gameweek, sims, use_cache=False)
    finally:
        fixtures.SCHEDULE.clear()
        fixtures.SCHEDULE.extend(saved)
```

- [x] **Step 2: Run it, verify it fails**

```bash
python3 -m unittest tests.test_fpl_model.TestDerivedRowColumns -v
```

Expected: FAIL — `AttributeError: module 'games.fpl.model' has no attribute '_derive_row'`.

- [x] **Step 3: Implement**

In `games/fpl/model.py`, add above `build_rows`:

```python
def _kickoffs_by_team(fx: list) -> dict:
    """{team: EARLIEST kickoff ISO string} for the gameweek.

    Earliest, not only, because a double-gameweek team has two. The captains
    article orders by the first fixture — that is the one a manager's captain
    decision is locked against.
    """
    out: dict = {}
    for f in fx:
        iso = f.kickoff.isoformat()
        for team in (f.home, f.away):
            if team not in out or iso < out[team]:
                out[team] = iso
    return out


def _derive_row(*, name: str, means: dict, x_points: float, ceiling: float,
                bonus: float, defcon_pts: float, p_defcon: float,
                price, ownership, kickoff) -> dict:
    """One order-book row with every column the six articles consume.

    Kept as a standalone pure function (rather than an inline dict literal in
    build_rows) so the derived columns can be unit-tested against hand-computed
    inputs without running a simulation.

    Rounding happens HERE and only here: these rows are what the cache stores and
    what the public JSON feed serves, and 14 significant figures of Monte-Carlo
    noise is not information.
    """
    pos = means["position"]
    return {
        "name": name,
        "team": means["team"],
        "position": pos,
        "x_points": round(x_points, 2),
        "captain_ev": round(2 * x_points, 2),
        "ceiling": round(ceiling, 2),
        "price": price,
        "ownership_pct": ownership,
        "value": round(x_points / price, 3) if price else None,
        "bonus": round(bonus, 2),
        # Points and probability are the same quantity in two units
        # (points == 2 x probability). The DefCon article headlines the
        # probability; the tables print the points. Emitting both keeps every
        # surface reading the same number.
        "defcon": round(defcon_pts, 2),
        "p_defcon": round(p_defcon, 3),
        "cs_points": round(means.get("clean_sheet", 0.0) * CS_PTS.get(pos, 0), 2),
        "kickoff": kickoff,
    }
```

Then replace the row-assembly loop inside `build_rows` (the `for name, ps in samples.items():` block) with:

```python
    kickoffs = _kickoffs_by_team(fx)
    rows = []
    for name, ps in samples.items():
        m = means[name]
        conceded_samples = _conceded_series(ps)
        player_bonus = bonus.expected(name)
        pts = total_points(m, ps, conceded_samples, bonus=player_bonus)
        p_played = appearance_probability(ps)
        meta = players_by_name.get(name, {})
        # Scaled by P(played): the raw threshold probability is conditional on
        # appearing, which would show a rotation player as if he started every
        # week. See appearance_probability's docstring.
        p_defcon = defcon_probability(m["position"], ps.defcon_samples) * p_played
        rows.append(_derive_row(
            name=name, means=m, x_points=pts, ceiling=points.tail_mean(name),
            bonus=player_bonus, defcon_pts=p_defcon * DEFCON_PTS,
            p_defcon=p_defcon, price=meta.get("price"),
            ownership=meta.get("ownership"),
            kickoff=kickoffs.get(m["team"])))
    rows.sort(key=lambda r: -r["x_points"])
```

That references a `defcon_probability` helper that does not exist yet — `defcon_points` currently computes the probability and multiplies by 2 in one step. Split it, so the probability has a name:

```python
def defcon_probability(position: str, defcon_samples: list) -> float:
    """P(defensive-contribution count >= this position's threshold).

    Conditional on having played, like save_samples and defcon_samples generally
    (they only accumulate on sims where the player was on the pitch). Callers
    scale by appearance_probability to make it unconditional.
    """
    threshold = defcon_threshold(position)
    if threshold is None or not defcon_samples:
        return 0.0
    hits = sum(1 for c in defcon_samples if c >= threshold)
    return hits / float(len(defcon_samples))


def defcon_points(position: str, defcon_samples: list) -> float:
    """Expected DefCon points: 2 x P(count >= threshold).

    A threshold crossing, not a rate — 2 x rate/threshold is wrong in both tails,
    over-paying players who never reach it and under-paying those who always do.
    The payout is capped at 2 no matter how far past the threshold a player goes.
    """
    return DEFCON_PTS * defcon_probability(position, defcon_samples)
```

- [x] **Step 4: Run the tests**

```bash
python3 -m unittest tests.test_fpl_model -v
```

Expected: PASS, including the existing DefCon tests — `defcon_points` is unchanged in behaviour, only in composition.

- [x] **Step 5: Commit**

```bash
git add games/fpl/model.py tests/test_fpl_model.py && git commit -m "feat(fpl): derived row columns (captain EV, value, DefCon probability, CS points, kickoff)"
```

---

## Task 3: Per-match summaries in the cached artifact

Spec §6 says the artifact holds "the per-player derived rows … plus the per-match scoreline distribution". Only the rows are stored today: `build_rows` throws away `simulate_round`'s second return value. The fixture ticker cannot be built without it, and re-simulating just to get scorelines would defeat the cache.

`MatchSample` objects are not JSON-serialisable, so the derivation has to happen before the store — which is correct anyway: reading a simulated distribution is the model's job, and article framing (environment labels, confidence copy) stays in `fpl_articles`.

This task also gives the caller a cache hit/miss signal, which Task 11's preflight needs.

**Files:**
- Modify: `games/fpl/model.py`, `core/simcache.py`
- Test: `tests/test_fpl_model.py`, `tests/test_simcache.py`

- [x] **Step 1: Write the failing tests**

Append to `tests/test_fpl_model.py`:

```python
class TestMatchSummaries(unittest.TestCase):
    def test_summary_fields_and_probability_normalisation(self):
        artifact, _hit = _tiny_build_artifact()
        self.assertEqual(len(artifact["matches"]), 1)
        m = artifact["matches"][0]
        for key in ("match_id", "home", "away", "kickoff", "exp_home_goals",
                    "exp_away_goals", "exp_total", "top_scoreline", "p_home",
                    "p_draw", "p_away", "p_cs_home", "p_cs_away", "market"):
            self.assertIn(key, m)
        self.assertAlmostEqual(m["p_home"] + m["p_draw"] + m["p_away"], 1.0, places=2)
        self.assertAlmostEqual(m["exp_total"],
                               m["exp_home_goals"] + m["exp_away_goals"], places=2)

    def test_no_advancement_fields_ever(self):
        """FPL has no knockout. articles.match_predictions would emit p_advance_*
        for any round >= 4; this path must never grow that field, or GW4 would
        publish a survival probability for a league season."""
        artifact, _hit = _tiny_build_artifact(gameweek=7)
        self.assertNotIn("p_advance_home", artifact["matches"][0])
        self.assertNotIn("p_advance_away", artifact["matches"][0])

    def test_market_flag_tracks_priced_fixtures(self):
        """A fixture with odds-derived lambdas is market-derived; one falling back
        to ratings is not. The ticker labels the columns from this."""
        priced, _ = _tiny_build_artifact()
        self.assertTrue(priced["matches"][0]["market"])
        unpriced, _ = _tiny_build_artifact(priced=False)
        self.assertFalse(unpriced["matches"][0]["market"])

    def test_artifact_round_trips_through_the_cache(self):
        first, hit_first = _tiny_build_artifact(use_cache=True, gameweek=97)
        second, hit_second = _tiny_build_artifact(use_cache=True, gameweek=97)
        self.assertFalse(hit_first)
        self.assertTrue(hit_second)
        self.assertEqual(first["matches"], second["matches"])
        self.assertEqual(first["rows"], second["rows"])
```

Add the helper next to `_tiny_build_rows`:

```python
def _tiny_build_artifact(sims=300, gameweek=98, priced=True, use_cache=False):
    """_tiny_build_rows' fixture, but returning the full (artifact, cache_hit)."""
    from core import fixtures
    from core.ratings import PlayerPrior

    squads = {
        "Home": [PlayerPrior(name="H-Def", position="DEF", start_prob=1.0,
                             exp_minutes=90, defcon_per90=9.0)],
        "Away": [PlayerPrior(name="A-Gk", position="GK", start_prob=1.0,
                             exp_minutes=90, saves_per90=3.5)],
    }
    players_by_name = {
        "H-Def": {"name": "H-Def", "price": 4.5, "ownership": 2.0,
                  "minutes": 2700, "bps": 500},
        "A-Gk": {"name": "A-Gk", "price": 5.0, "ownership": 5.0,
                 "minutes": 3420, "bps": 700},
    }
    saved = list(fixtures.SCHEDULE)
    try:
        fixtures.SCHEDULE.clear()
        fixtures.SCHEDULE.append(fixtures.Fixture(
            match_id="tiny-1", home="Home", away="Away",
            kickoff=datetime(2026, 8, 21, 19, 0, tzinfo=timezone.utc),
            stage="GW", fantasy_round=gameweek, neutral=False,
            lam_home=1.6 if priced else None,
            lam_away=1.1 if priced else None))
        return fpl_model.build_artifact(
            squads, players_by_name, gameweek, sims, use_cache=use_cache)
    finally:
        fixtures.SCHEDULE.clear()
        fixtures.SCHEDULE.extend(saved)
```

Append to `tests/test_simcache.py`:

```python
class TestArtifactsForGameweek(unittest.TestCase):
    def test_lists_only_this_gameweeks_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(simcache, "CACHE_DIR", tmp):
                simcache.store("aaa", {"rows": []}, meta={"gameweek": 1})
                simcache.store("bbb", {"rows": []}, meta={"gameweek": 1})
                simcache.store("ccc", {"rows": []}, meta={"gameweek": 2})
                self.assertEqual(sorted(simcache.artifacts_for(1)), ["aaa", "bbb"])
                self.assertEqual(simcache.artifacts_for(2), ["ccc"])
                self.assertEqual(simcache.artifacts_for(3), [])

    def test_missing_cache_dir_is_empty_not_an_error(self):
        with mock.patch.object(simcache, "CACHE_DIR", "/nonexistent/path/xyz"):
            self.assertEqual(simcache.artifacts_for(1), [])
```

Make sure `tempfile` and `mock` are imported at the top of `tests/test_simcache.py`.

- [x] **Step 2: Run them, verify they fail**

```bash
python3 -m unittest tests.test_fpl_model.TestMatchSummaries tests.test_simcache.TestArtifactsForGameweek -v
```

Expected: FAIL — no `build_artifact`, no `artifacts_for`.

- [x] **Step 3: Implement**

In `core/simcache.py`, add at the end:

```python
def artifacts_for(gameweek: int) -> list:
    """Cache keys of every stored artifact whose meta says it is this gameweek's.

    Preflight uses this to tell an EXPECTED miss (nothing built for this gameweek
    yet) from an UNEXPECTED one (artifacts exist, but an input or the model source
    changed since) — spec §9's "the sim cache missed unexpectedly" warning.

    Unreadable or meta-less files are skipped, not raised on: this is diagnostics,
    and it must never be the reason a build dies.
    """
    if not os.path.isdir(CACHE_DIR):
        return []
    out = []
    for fname in os.listdir(CACHE_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(CACHE_DIR, fname), encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError):
            continue
        if (payload.get("meta") or {}).get("gameweek") == gameweek:
            out.append(fname[:-len(".json")])
    return out
```

In `games/fpl/model.py`, add the pure summariser above `build_rows`:

```python
def match_summaries(match_samples: dict, fx: list) -> list:
    """One JSON-safe dict per fixture: scoreline distribution, 1X2, clean sheets.

    Derived here rather than in the site layer because MatchSample objects do not
    survive a JSON round trip, and spec §6 requires the cached artifact to carry
    the per-match distribution — so the derivation must happen before the store.

    Deliberately NOT evmax.articles.match_predictions: that function emits
    p_advance_home/p_advance_away for any round >= 4 (World Cup knockout), which
    for gameweek 4 of a league season would publish a survival probability for a
    tie that does not exist.

    `market` records whether the fixture's lambdas came from the odds feed or fell
    back to ratings priors, so the ticker can label each column's provenance
    instead of presenting a uniform confidence it does not have (spec §8).
    """
    out = []
    for f in fx:
        ms = match_samples.get(f.match_id)
        if ms is not None and ms.sims > 0:
            probs = ms.outcome_probs()
            p_home = probs.get("H", 0.0)
            p_draw = probs.get("D", 0.0)
            p_away = probs.get("A", 0.0)
            best_sl = max(ms.scorelines, key=lambda k: ms.scorelines[k])
            mh, ma = ms.marginal_home(), ms.marginal_away()
            exp_h = sum(g * p for g, p in mh.items())
            exp_a = sum(g * p for g, p in ma.items())
            # A team keeps a clean sheet iff the OPPONENT scores zero.
            p_cs_home, p_cs_away = ma.get(0, 0.0), mh.get(0, 0.0)
        else:
            # No sample for this fixture (a blank, or a match the engine skipped).
            p_home = p_draw = p_away = 0.0
            best_sl = (0, 0)
            exp_h = exp_a = p_cs_home = p_cs_away = 0.0

        total_p = p_home + p_draw + p_away
        if total_p > 0:
            p_home, p_draw, p_away = (p_home / total_p, p_draw / total_p,
                                      p_away / total_p)

        out.append({
            "match_id": f.match_id,
            "home": f.home,
            "away": f.away,
            "kickoff": f.kickoff.isoformat(),
            "exp_home_goals": round(exp_h, 2),
            "exp_away_goals": round(exp_a, 2),
            "exp_total": round(exp_h + exp_a, 2),
            "top_scoreline": f"{best_sl[0]}-{best_sl[1]}",
            "p_home": round(p_home, 3),
            "p_draw": round(p_draw, 3),
            "p_away": round(p_away, 3),
            "p_cs_home": round(p_cs_home, 3),
            "p_cs_away": round(p_cs_away, 3),
            "market": f.lam_home is not None and f.lam_away is not None,
        })
    out.sort(key=lambda m: m["kickoff"])
    return out
```

Now restructure the run path. Rename the body of `build_rows` to `build_artifact`, returning `(artifact, cache_hit)`, and make `build_rows` a thin wrapper so `run()` and the existing tests keep working:

```python
def build_artifact(priors_by_team: dict, players_by_name: dict, gameweek: int,
                   sims: int, use_cache: bool = True) -> tuple:
    """Simulate (or fetch from cache) and return ({"rows", "matches"}, cache_hit).

    [keep the existing docstring paragraph about the cache key here]
    """
    # ... everything from the existing build_rows up to and including the
    #     `key = simcache.cache_key(...)` call is UNCHANGED ...

    if use_cache:
        cached = simcache.load(key)
        if cached is not None:
            return {"rows": cached["rows"],
                    "matches": cached.get("matches", [])}, True

    # ... the simulation and row assembly are UNCHANGED, except that
    #     simulate_round's second return value is now KEPT ...
    samples, match_samples = engine_events.simulate_round(
        gameweek, sims=sims, seed=_SEED,
        priors=lambda team: priors_by_team.get(team, []),
        research=research_entries,
        research_weight=research_weight,
        per_match_hook=_hook,
    )

    # ... row assembly from Task 2 ...

    artifact = {"rows": rows, "matches": match_summaries(match_samples, fx)}
    if use_cache:
        simcache.store(key, artifact, meta={"gameweek": gameweek, "sims": sims})
    return artifact, False


def build_rows(priors_by_team: dict, players_by_name: dict, gameweek: int,
               sims: int, use_cache: bool = True) -> list:
    """The order-book rows alone — `run()`'s view of build_artifact.

    Kept so the CLI order book and its tests do not have to care about the match
    layer, which only the site consumes.
    """
    artifact, _hit = build_artifact(priors_by_team, players_by_name, gameweek,
                                    sims, use_cache=use_cache)
    return artifact["rows"]
```

Note `cached.get("matches", [])`: artifacts written before this task have no `matches` key. They cannot actually be served — the source fingerprint covers `games/fpl/model.py`, so editing this file invalidates every one of them — but the `.get` costs nothing and means a hand-copied artifact degrades rather than crashing.

- [x] **Step 4: Run the tests**

```bash
python3 -m unittest tests.test_fpl_model tests.test_simcache -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add games/fpl/model.py core/simcache.py tests/test_fpl_model.py tests/test_simcache.py && git commit -m "feat(fpl): per-match summaries in the cached artifact + gameweek artifact listing"
```

---

## Task 4: `render.Section` and section-aware article pages

`render.article_page` hardcodes three World-Cup facts: the `.md` alternate link path, the OpenGraph canonical path, and the kicker's `· Round {round_no}`. `article_md` hardcodes the JSON URL and canonical. Everything else in those functions is section-neutral.

A `Section` descriptor carries the differences. Defaults keep every existing call site byte-identical — that is the regression gate, and `tests/test_site_render.py` is what proves it.

**Files:**
- Modify: `evmax/render.py`
- Test: `tests/test_fpl_site.py` (create)

- [x] **Step 1: Write the failing test**

Create `tests/test_fpl_site.py`:

```python
"""Phase 4: FPL section rendering, preflight and the end-to-end gameweek build."""
from __future__ import annotations

import unittest

from evmax import render


class TestSectionDescriptor(unittest.TestCase):
    def test_world_cup_section_paths(self):
        self.assertEqual(render.WC.article_path(5, "captains"), "/round/5/captains/")
        self.assertEqual(render.WC.md_path(5, "captains"), "/round/5/captains.md")
        self.assertEqual(render.WC.json_path(5, "captains"),
                         "/api/round/5/captains.json")
        self.assertEqual(render.WC.landing_path(5), "/round/5/")
        self.assertEqual(render.WC.kicker(5), "Round 5")

    def test_fpl_section_paths(self):
        self.assertEqual(render.FPL.article_path(1, "defcon"), "/fpl/gw1/defcon/")
        self.assertEqual(render.FPL.md_path(1, "defcon"), "/fpl/gw1/defcon.md")
        self.assertEqual(render.FPL.json_path(1, "defcon"),
                         "/api/fpl/gw1/defcon.json")
        self.assertEqual(render.FPL.landing_path(1), "/fpl/gw1/")
        self.assertEqual(render.FPL.kicker(1), "Gameweek 1")


_PROSE = {"headline": "H", "standfirst": "S", "body_html": "<p>B</p>",
          "bottom_line": "BL", "source": "template"}
_ENTRIES = [{"name": "A", "rank": 1, "x_points": 6.0, "price": 5.0}]


class TestArticlePageSection(unittest.TestCase):
    def test_default_is_unchanged_world_cup_output(self):
        html = render.article_page(5, "captains", "T", _PROSE, _ENTRIES,
                                   ["x_points"], "/api/round/5/captains.json", "")
        self.assertIn('href="/round/5/captains.md"', html)
        self.assertIn("/round/5/captains/", html)
        self.assertIn("Round 5", html)

    def test_fpl_section_rewrites_every_path_and_label(self):
        html = render.article_page(1, "defcon", "T", _PROSE, _ENTRIES,
                                   ["x_points"], "/api/fpl/gw1/defcon.json", "",
                                   section=render.FPL)
        self.assertIn('href="/fpl/gw1/defcon.md"', html)
        self.assertIn("/fpl/gw1/defcon/", html)
        self.assertIn("Gameweek 1", html)
        self.assertNotIn("/round/1/", html)

    def test_switcher_pills_use_the_section_abbreviation(self):
        html = render.article_page(2, "captains", "T", _PROSE, _ENTRIES,
                                   ["x_points"], "/api/fpl/gw2/captains.json", "",
                                   section=render.FPL, available_rounds=[1, 2])
        self.assertIn('href="/fpl/gw1/"', html)
        self.assertIn(">GW1<", html)
        self.assertNotIn(">R1<", html)


class TestArticleMdSection(unittest.TestCase):
    def test_fpl_markdown_twin_points_at_the_fpl_tree(self):
        md = render.article_md(1, "captains", "T", _PROSE, _ENTRIES, ["x_points"],
                               "2026-08-20T00:00:00+00:00", "20 August 2026",
                               canonical_path="/fpl/gw1/captains/",
                               section=render.FPL)
        self.assertIn("/api/fpl/gw1/captains.json", md)
        self.assertNotIn("/api/round/", md)
```

- [x] **Step 2: Run it, verify it fails**

```bash
python3 -m unittest tests.test_fpl_site -v
```

Expected: FAIL — `AttributeError: module 'evmax.render' has no attribute 'WC'`.

- [x] **Step 3: Implement**

In `evmax/render.py`, add after the `SITE_URL` / brand constants near the top:

```python
class Section:
    """A URL namespace and its reader-facing vocabulary.

    The site serves two competitions from one renderer. Rather than fork the page
    functions (or do the September templating refactor early), each function takes
    a Section and defaults to WC, so every existing call site keeps producing
    byte-identical HTML.

    unit_abbr is the round-switcher pill label: "R5" for the World Cup, "GW5" for
    FPL.
    """

    def __init__(self, key, label, unit, unit_abbr, base, api_base):
        self.key = key                # "round" | "fpl"
        self.label = label            # "World Cup Fantasy" | "Fantasy Premier League"
        self.unit = unit              # "Round" | "Gameweek"
        self.unit_abbr = unit_abbr    # "R" | "GW"
        self.base = base              # "/round/{r}" | "/fpl/gw{r}"
        self.api_base = api_base      # "/api/round/{r}" | "/api/fpl/gw{r}"

    def landing_path(self, n):
        return self.base.format(r=n) + "/"

    def article_path(self, n, slug):
        return f"{self.base.format(r=n)}/{slug}/"

    def md_path(self, n, slug):
        return f"{self.base.format(r=n)}/{slug}.md"

    def json_path(self, n, slug):
        return f"{self.api_base.format(r=n)}/{slug}.json"

    def players_json_path(self, n):
        return f"{self.api_base.format(r=n)}/players.json"

    def kicker(self, n):
        return f"{self.unit} {n}"

    def switcher_base(self):
        return self.base + "/"


WC = Section("round", "World Cup Fantasy", "Round", "R",
             "/round/{r}", "/api/round/{r}")
FPL = Section("fpl", "Fantasy Premier League", "Gameweek", "GW",
              "/fpl/gw{r}", "/api/fpl/gw{r}")
```

Give `_round_switcher_html` the abbreviation:

```python
def _round_switcher_html(available_rounds, current_round, base_path="/round/{r}/",
                         abbr="R"):
    """[keep the existing docstring]"""
    if not available_rounds or len(available_rounds) <= 1:
        return ""
    tabs = "".join(
        f'<a class="round-tab{" active" if r == current_round else ""}" '
        f'href="{base_path.format(r=r)}">{abbr}{r}</a>'
        for r in available_rounds
    )
    return f'<div class="round-switcher"><span class="rs-label">{abbr}ounds</span>{tabs}</div>'
```

That `{abbr}ounds` is wrong — it produces "Rounds" for the WC by luck and "GWounds" for FPL. Use an explicit label instead:

```python
    label = "Rounds" if abbr == "R" else "Gameweeks"
    return f'<div class="round-switcher"><span class="rs-label">{label}</span>{tabs}</div>'
```

Now `article_page`: add `section=WC` as the final keyword parameter, and replace the three hardcoded facts.

```python
def article_page(round_no, article, title, prose, entries, columns, json_url, viz_html,
                 generated_at=None, date_str=None, show_table=True,
                 available_rounds=None, section=WC):
```

```python
    kicker_label = _html.escape(
        _COL_LABEL.get(article, article.replace("-", " ").title())
        + f" · {section.kicker(round_no)}")
```

```python
<link rel="alternate" type="text/markdown" href="{section.md_path(round_no, article)}">
{_og_meta(prose["headline"], summary, section.article_path(round_no, article), "article")}
```

```python
{_round_switcher_html(available_rounds or [round_no], round_no,
                      base_path=section.switcher_base(), abbr=section.unit_abbr)}
```

And `article_md`: add `section=WC` to the signature and replace its hardcoded JSON URL.

```python
    json_url = f"{SITE_URL}{section.json_path(round_no, slug)}"
```

- [x] **Step 4: Run the tests**

```bash
python3 -m unittest tests.test_fpl_site tests.test_site_render -v
```

Expected: PASS, both files. `test_site_render` passing unchanged is the point of this task — if it does not, a default is wrong.

- [x] **Step 5: Commit**

```bash
git add evmax/render.py tests/test_fpl_site.py && git commit -m "feat(site): Section descriptor; article pages render under any URL namespace"
```

---

## Task 5: Section-aware landing, feed, sitemap and llms.txt

Same treatment for the remaining page functions. These carry the "World Cup Fantasy" brand string and `/round/` paths in `<title>`, meta description, the page label, feed card links and the agent-facing files.

**Files:**
- Modify: `evmax/render.py`
- Test: `tests/test_fpl_site.py`

- [x] **Step 1: Write the failing test**

Append to `tests/test_fpl_site.py`:

```python
class TestLandingSection(unittest.TestCase):
    def _landing(self, section):
        featured = {"slug": "captains", "prose": _PROSE, "viz_html": ""}
        feed = [{"slug": "defcon", "headline": "H", "teaser": "T",
                 "stat_value": "0.72", "stat_label": "P(DefCon)"}]
        return render.landing_page(1, featured, feed, date_str="20 August 2026",
                                   section=section)

    def test_fpl_landing_brands_and_links_as_fpl(self):
        html = self._landing(render.FPL)
        self.assertIn("Fantasy Premier League", html)
        self.assertIn("Gameweek 1", html)
        self.assertIn('href="/fpl/gw1/defcon/"', html)
        self.assertNotIn("World Cup", html)

    def test_world_cup_landing_is_unchanged(self):
        html = self._landing(render.WC)
        self.assertIn("World Cup Fantasy", html)
        self.assertIn('href="/round/1/defcon/"', html)


class TestAgentFilesSection(unittest.TestCase):
    def test_llms_txt_lists_fpl_urls(self):
        txt = render.llms_txt(1, [("captains", "Best captain picks")],
                              section=render.FPL)
        self.assertIn("/fpl/gw1/captains/", txt)
        self.assertIn("/api/fpl/gw1/captains.json", txt)
        self.assertIn("Gameweek 1", txt)

    def test_sitemap_includes_fpl_urls(self):
        xml = render.sitemap_xml(1, [("captains", "Best captain picks")],
                                 lastmod="2026-08-20", section=render.FPL)
        self.assertIn("/fpl/gw1/", xml)
        self.assertIn("/fpl/gw1/captains/", xml)

    def test_sitemap_can_carry_extra_urls(self):
        """The FPL build must keep the World Cup tree in the sitemap — those pages
        are still live and still indexed (D5), and a sitemap that drops them is a
        deindexing request."""
        xml = render.sitemap_xml(1, [("captains", "T")], lastmod="2026-08-20",
                                 section=render.FPL,
                                 extra_urls=["/round/8/", "/round/8/captains/"])
        self.assertIn("/round/8/captains/", xml)


class TestArticleJsonSection(unittest.TestCase):
    def test_envelope_names_the_unit(self):
        env = render.article_json("fantasy_premier_league", 1, "defcon", "T",
                                  "2026-08-20T00:00:00+00:00", 50000, _ENTRIES,
                                  section=render.FPL)
        self.assertEqual(env["gameweek"], 1)
        self.assertNotIn("round", env)

    def test_world_cup_envelope_keeps_the_round_key(self):
        env = render.article_json("fifa_world_cup_fantasy", 5, "captains", "T",
                                  "2026-06-24T00:00:00+00:00", 50000, _ENTRIES)
        self.assertEqual(env["round"], 5)
```

- [x] **Step 2: Run it, verify it fails**

```bash
python3 -m unittest tests.test_fpl_site -v
```

Expected: FAIL — `landing_page() got an unexpected keyword argument 'section'`.

- [x] **Step 3: Implement**

`article_json` — add `section=WC` and key the unit off it:

```python
def article_json(competition, fantasy_round, article, title, generated_at, sims,
                 entries, extra_fields=None, section=WC):
    """extra_fields: optional dict merged into the envelope as additional top-level
    keys (e.g. wildcard's {"squad": {...}} meta). Never overrides the standard keys.

    The unit key is named for the section — "round" for the World Cup, "gameweek"
    for FPL — because a consumer reading `"round": 1` off an FPL feed would
    reasonably think it meant a knockout round.
    """
    env = {
        "competition": competition,
        section.key if section.key == "round" else "gameweek": fantasy_round,
        "article": article,
        ...
    }
```

A conditional key inside a dict literal is unreadable. Write it plainly:

```python
    unit_key = "round" if section.key == "round" else "gameweek"
    env = {
        "competition": competition,
        unit_key: fantasy_round,
        "article": article,
        "title": title,
        "generated_at": generated_at,
        "sims": sims,
        "methodology": METHODOLOGY,
        "entries": entries,
        "source": SITE_URL,
        "license": DATA_LICENSE_URL,
        "license_text": DATA_LICENSE_TEXT,
    }
```

`feed_card` — add `section=WC`, and use `section.article_path(round_no, slug)` for the `href`.

`landing_page` — add `section=WC`, then replace, throughout the function body:
- `f"World Cup Fantasy Round {round_no}"` → `f"{section.label} {section.kicker(round_no)}"`
- `f"/round/{round_no}/{feat_slug}/"` → `section.article_path(round_no, feat_slug)`
- `f'<div class="pagelabel">World Cup Fantasy · Round {round_no}</div>'` → `f'<div class="pagelabel">{section.label} · {section.kicker(round_no)}</div>'`
- the `<title>` and `<meta name="description">` strings → same substitution
- pass `section` down to every `feed_card(...)`, `_round_switcher_html(...)`, `_fixtures_rail_html(...)` and `_live_xi_html(...)` call it makes

`_fixtures_rail_html` and `_live_xi_html` both build `/round/{n}/…` links; give each a `section=WC` parameter and use `section.article_path(...)`.

`llms_txt` — add `section=WC`:

```python
        f"## {section.kicker(round_no)} articles",
        ...
        lines.append(f"- [{title}]({SITE_URL}{section.article_path(round_no, slug)}) — "
                     f"data: {SITE_URL}{section.json_path(round_no, slug)}"
                     f" · markdown: {SITE_URL}{section.md_path(round_no, slug)}")
        ...
        f"- Full player projections: {SITE_URL}{section.players_json_path(round_no)}",
```

`sitemap_xml` — add `section=WC` and `extra_urls=None`:

```python
def sitemap_xml(round_no, nav, lastmod=None, section=WC, extra_urls=None):
    """extra_urls: absolute site paths to include verbatim, beyond this section's
    own pages. The FPL build passes the World Cup tree here: those pages are still
    live and still indexed (spec D5), and a sitemap that silently drops them reads
    to a crawler as a request to deindex them."""
    urls = [f"{SITE_URL}/", f"{SITE_URL}{section.landing_path(round_no)}"]
    urls += [f"{SITE_URL}{section.article_path(round_no, slug)}" for slug, _ in nav]
    urls += [f"{SITE_URL}{p}" for p in (extra_urls or [])]
```

- [x] **Step 4: Run the tests**

```bash
python3 -m unittest tests.test_fpl_site tests.test_site_render tests.test_site_build -v
```

Expected: PASS across all three. The WC suites must not need a single edit.

- [x] **Step 5: Commit**

```bash
git add evmax/render.py tests/test_fpl_site.py && git commit -m "feat(site): section-aware landing page, feed cards, sitemap and llms.txt"
```

---

## Task 6: FPL article ranking — captains, defenders, efficiency, DefCon leaders

Four of the six articles are ranking functions over the enriched rows. They live in a new module because their FPL-specific bits (goalkeepers belong in the defenders article; DefCon is FPL-only) do not belong in the World Cup's `articles.py`, which is a frozen dependency of the track record.

Price tiers are the one thing worth reusing: `articles.price_tier`'s Budget/Mid/Premium thresholds (£5.5 / £8.0) happen to be exactly FPL's own vernacular for enabler / mid-price / premium, and the cached feed's £4.0–£15.5 range sits across them correctly.

**Files:**
- Create: `evmax/fpl_articles.py`
- Test: `tests/test_fpl_articles.py` (create)

- [x] **Step 1: Write the failing tests**

Create `tests/test_fpl_articles.py`:

```python
"""Phase 4: FPL-specific article ranking and squad building."""
from __future__ import annotations

import unittest

from evmax import fpl_articles


def _row(name, pos, xp, price=5.0, team="ARS", **kw):
    row = {
        "name": name, "position": pos, "team": team,
        "x_points": xp, "captain_ev": round(2 * xp, 2), "ceiling": xp * 1.8,
        "price": price, "value": round(xp / price, 3) if price else None,
        "ownership_pct": 10.0, "bonus": 0.4, "defcon": 0.0, "p_defcon": 0.0,
        "cs_points": 0.0, "kickoff": "2026-08-21T19:00:00+00:00",
    }
    row.update(kw)
    return row


class TestCaptains(unittest.TestCase):
    def test_ranked_by_captain_ev_with_ranks(self):
        rows = [_row("Low", "MID", 4.0), _row("High", "FWD", 7.0)]
        out = fpl_articles.captains(rows)
        self.assertEqual([e["name"] for e in out], ["High", "Low"])
        self.assertEqual([e["rank"] for e in out], [1, 2])

    def test_kickoff_order_is_annotated(self):
        """A manager picks a captain against the deadline but a VICE against the
        chain of kickoffs — kickoff_order 1 is the earliest of the candidates."""
        rows = [_row("Late", "FWD", 7.0, kickoff="2026-08-23T15:00:00+00:00"),
                _row("Early", "MID", 6.0, kickoff="2026-08-21T19:00:00+00:00")]
        out = fpl_articles.captains(rows)
        by_name = {e["name"]: e for e in out}
        self.assertEqual(by_name["Early"]["kickoff_order"], 1)
        self.assertEqual(by_name["Late"]["kickoff_order"], 2)

    def test_missing_kickoff_sorts_last_without_crashing(self):
        rows = [_row("NoKo", "FWD", 7.0, kickoff=None),
                _row("Known", "MID", 6.0)]
        out = fpl_articles.captains(rows)
        by_name = {e["name"]: e for e in out}
        self.assertEqual(by_name["Known"]["kickoff_order"], 1)
        self.assertEqual(by_name["NoKo"]["kickoff_order"], 2)


class TestDefenders(unittest.TestCase):
    def test_includes_goalkeepers_and_excludes_outfield_attackers(self):
        rows = [_row("Keeper", "GK", 5.0), _row("Back", "DEF", 6.0),
                _row("Mid", "MID", 8.0), _row("Fwd", "FWD", 9.0)]
        out = fpl_articles.defenders(rows)
        self.assertEqual(sorted(e["name"] for e in out), ["Back", "Keeper"])

    def test_ranked_by_x_points(self):
        rows = [_row("Keeper", "GK", 5.0), _row("Back", "DEF", 6.0)]
        self.assertEqual([e["name"] for e in fpl_articles.defenders(rows)],
                         ["Back", "Keeper"])


class TestEfficiency(unittest.TestCase):
    def test_ranked_by_value_and_tiered(self):
        rows = [_row("Cheap", "DEF", 4.0, price=4.5),
                _row("Prem", "FWD", 9.0, price=14.0)]
        out = fpl_articles.efficiency(rows)
        self.assertEqual(out[0]["name"], "Cheap")     # 0.889 vs 0.643 per million
        self.assertEqual(out[0]["tier"], "Budget")
        self.assertEqual(out[1]["tier"], "Premium")

    def test_priceless_rows_are_dropped(self):
        rows = [_row("NoPrice", "MID", 8.0, price=None), _row("Ok", "MID", 4.0)]
        self.assertEqual([e["name"] for e in fpl_articles.efficiency(rows)], ["Ok"])


class TestDefconLeaders(unittest.TestCase):
    def test_ranked_by_probability_not_points(self):
        rows = [_row("Solid", "DEF", 4.0, p_defcon=0.71, defcon=1.42),
                _row("Flaky", "DEF", 6.0, p_defcon=0.20, defcon=0.40)]
        out = fpl_articles.defcon_leaders(rows)
        self.assertEqual([e["name"] for e in out], ["Solid", "Flaky"])

    def test_goalkeepers_are_excluded(self):
        """GK is not DefCon-eligible (games/fpl/model.DEFCON_THRESHOLD has no GK),
        so a keeper in this list would be a published impossibility."""
        rows = [_row("Keeper", "GK", 5.0, p_defcon=0.9),
                _row("Back", "DEF", 4.0, p_defcon=0.5)]
        self.assertEqual([e["name"] for e in fpl_articles.defcon_leaders(rows)],
                         ["Back"])

    def test_zero_probability_players_are_dropped(self):
        """A player with no DefCon history projects 0.0 and would pad the list with
        names that can never earn the points."""
        rows = [_row("Back", "DEF", 4.0, p_defcon=0.5),
                _row("Nothing", "MID", 6.0, p_defcon=0.0)]
        self.assertEqual([e["name"] for e in fpl_articles.defcon_leaders(rows)],
                         ["Back"])

    def test_threshold_is_carried_for_the_prose(self):
        rows = [_row("Back", "DEF", 4.0, p_defcon=0.5),
                _row("Engine", "MID", 6.0, p_defcon=0.4)]
        out = fpl_articles.defcon_leaders(rows)
        by_name = {e["name"]: e for e in out}
        self.assertEqual(by_name["Back"]["defcon_threshold"], 10)
        self.assertEqual(by_name["Engine"]["defcon_threshold"], 12)
```

- [x] **Step 2: Run them, verify they fail**

```bash
python3 -m unittest tests.test_fpl_articles -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'evmax.fpl_articles'`.

- [x] **Step 3: Implement**

Create `evmax/fpl_articles.py`:

```python
"""Ranking and squad selection for the FPL articles.

Pure: no I/O, no HTTP, no simulation. Input is the enriched order-book rows from
games.fpl.model.build_artifact; output is ranked entry lists the site renders.

Separate from evmax/articles.py on purpose. That module is a frozen dependency of
the World Cup track record — /track-record/ grades published WC predictions off
snapshots built with it, and the existing suite passing is the regression gate for
this whole port (spec §4 "Untouched"). FPL-specific rules (goalkeepers belong in
the defenders article; DefCon exists at all; a three-per-club squad cap) go here.

Reused from articles.py where the rule is genuinely identical, not merely similar:
XI formation limits and price tiers.
"""

from __future__ import annotations

from evmax.articles import (POS_MAX, POS_MIN, SQUAD_QUOTA, XI_SIZE,
                            formation_of, legal_xi_formations, price_tier)
from games.fpl.model import DEFCON_THRESHOLD

# FPL squad rules (2026/27 official, games/fpl/rules.md).
SQUAD_BUDGET = 100.0
MAX_PER_CLUB = 3
# Positions the defenders article covers. FPL pays goalkeepers a 4-point clean
# sheet and a 10-point goal, so they belong with defenders rather than in an
# article of their own — the reader's decision is "which end of the pitch do I
# spend on", and one article answers it.
DEFENSIVE_POSITIONS = ("DEF", "GK")


def _ranked(rows: list, key: str, reverse: bool = True) -> list:
    out = [dict(r) for r in sorted(rows, key=lambda r: r[key], reverse=reverse)]
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


def captains(rows: list) -> list:
    """Captain candidates by captain EV, annotated with their kickoff order.

    kickoff_order exists because the captain and the VICE are two different
    decisions. The captain is picked against the deadline; the vice matters only
    if the captain does not play, so a manager wants to know whether their vice
    kicks off before or after their captain. 1 is the earliest kickoff among the
    candidates.

    A row with no kickoff (a blank gameweek for that club) sorts last rather than
    raising — `None` is not comparable to a string, so it needs an explicit key.
    """
    ranked = _ranked(rows, "captain_ev")
    by_kickoff = sorted(ranked, key=lambda r: (r.get("kickoff") is None,
                                               r.get("kickoff") or ""))
    order = {id(r): i for i, r in enumerate(by_kickoff, 1)}
    for r in ranked:
        r["kickoff_order"] = order[id(r)]
    return ranked


def defenders(rows: list) -> list:
    """Defenders and goalkeepers by expected points.

    The rows carry cs_points, defcon and bonus as separate columns, so the article
    can show a reader WHERE a defender's points come from — a 6.0 built on clean
    sheets is a different bet from a 6.0 built on DefCon.
    """
    return _ranked([r for r in rows if r.get("position") in DEFENSIVE_POSITIONS],
                   "x_points")


def efficiency(rows: list) -> list:
    """Points per million, tagged with a price tier.

    Rows with no price are dropped: value is undefined without one, and a null in
    the primary sort column would order arbitrarily.
    """
    ranked = _ranked([r for r in rows if r.get("value") is not None], "value")
    for r in ranked:
        r["tier"] = price_tier(r.get("price"))
    return ranked


def defcon_leaders(rows: list) -> list:
    """Players by P(defensive contribution >= their position's threshold).

    Ranked on the PROBABILITY, not the points: the points column is exactly
    2 x the probability, so the ordering is identical, but the probability is the
    number the article is about — "Gabriel hits 10 CBIT in 71% of simulations" is
    the claim, and "1.42 DefCon points" is its consequence.

    Goalkeepers are excluded because they are not DefCon-eligible at all, and
    players projecting exactly zero are excluded because they pad the list with
    names that cannot earn the points.
    """
    pool = [r for r in rows
            if DEFCON_THRESHOLD.get(r.get("position")) is not None
            and (r.get("p_defcon") or 0.0) > 0.0]
    ranked = _ranked(pool, "p_defcon")
    for r in ranked:
        r["defcon_threshold"] = DEFCON_THRESHOLD[r["position"]]
    return ranked
```

- [x] **Step 4: Run the tests**

```bash
python3 -m unittest tests.test_fpl_articles -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add evmax/fpl_articles.py tests/test_fpl_articles.py && git commit -m "feat(fpl): captains, defenders, efficiency and DefCon-leader rankings"
```

---

## Task 7: The 15-man squad with a three-per-club cap

The wildcard article needs a legal FPL squad: 15 players (2 GK / 5 DEF / 5 MID / 3 FWD), £100.0m, a legal XI formation, and **at most three players from any one club**. The club cap is the one rule the World Cup version does not have — `articles.wildcard_squad` is a 190-line greedy builder with no notion of clubs, pinned by WC tests, and retrofitting the cap into it would put the track record's dependency at risk for no benefit.

Write a separate builder. It reuses `legal_xi_formations()` and `formation_of()` (the XI limits are genuinely identical between the two games) and keeps the same "cheap bench, spend everything on the XI" philosophy, but enforces the club cap at every selection and every swap.

**Files:**
- Modify: `evmax/fpl_articles.py`
- Test: `tests/test_fpl_articles.py`

- [x] **Step 1: Write the failing tests**

Append to `tests/test_fpl_articles.py`:

```python
def _pool(n_per_pos=8, teams=("ARS", "LIV", "MCI", "CHE", "NEW", "AVL", "BHA")):
    """A pool big enough to build a legal 15 in any formation, priced 4.0-9.0."""
    rows, i = [], 0
    for pos in ("GK", "DEF", "MID", "FWD"):
        for k in range(n_per_pos):
            i += 1
            rows.append(_row(f"{pos}{k}", pos, 8.0 - k * 0.4,
                             price=4.0 + k * 0.5, team=teams[i % len(teams)]))
    return rows


class TestFplSquad(unittest.TestCase):
    def test_squad_is_fifteen_with_the_right_quota(self):
        entries, meta = fpl_articles.fpl_squad(_pool())
        self.assertEqual(len(entries), 15)
        counts = {}
        for e in entries:
            counts[e["position"]] = counts.get(e["position"], 0) + 1
        self.assertEqual(counts, {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3})

    def test_within_budget(self):
        entries, meta = fpl_articles.fpl_squad(_pool())
        self.assertLessEqual(meta["total_cost"], 100.0)
        self.assertAlmostEqual(meta["left_over"], 100.0 - meta["total_cost"], places=2)

    def test_no_more_than_three_per_club(self):
        entries, _meta = fpl_articles.fpl_squad(_pool())
        counts = {}
        for e in entries:
            counts[e["team"]] = counts.get(e["team"], 0) + 1
        self.assertTrue(all(c <= 3 for c in counts.values()),
                        f"club cap violated: {counts}")

    def test_club_cap_holds_when_one_club_dominates_the_pool(self):
        """The adversarial case: the eleven best players all play for one club, so
        a cap-blind greedy build would pick them and ship an illegal squad."""
        rows = _pool()
        for r in rows[:11]:
            r["team"] = "ARS"
            r["x_points"] = 12.0
            r["value"] = round(12.0 / r["price"], 3)
        entries, _meta = fpl_articles.fpl_squad(rows)
        arsenal = sum(1 for e in entries if e["team"] == "ARS")
        self.assertLessEqual(arsenal, 3)

    def test_xi_formation_is_legal(self):
        entries, meta = fpl_articles.fpl_squad(_pool())
        xi = [e for e in entries if e["role"] == "XI"]
        self.assertEqual(len(xi), 11)
        counts = {pos: sum(1 for e in xi if e["position"] == pos)
                  for pos in ("GK", "DEF", "MID", "FWD")}
        self.assertEqual(counts["GK"], 1)
        self.assertTrue(3 <= counts["DEF"] <= 5)
        self.assertTrue(2 <= counts["MID"] <= 5)
        self.assertTrue(1 <= counts["FWD"] <= 3)
        self.assertEqual(meta["formation"],
                         f"{counts['DEF']}-{counts['MID']}-{counts['FWD']}")

    def test_roles_and_ranks(self):
        entries, _meta = fpl_articles.fpl_squad(_pool())
        xi = [e for e in entries if e["role"] == "XI"]
        bench = [e for e in entries if e["role"] == "Bench"]
        self.assertEqual(len(bench), 4)
        self.assertEqual([e["rank"] for e in xi], list(range(1, 12)))
        self.assertEqual([e["rank"] for e in bench], [12, 13, 14, 15])

    def test_impossible_budget_raises(self):
        rows = _pool()
        for r in rows:
            r["price"] = 15.0
        with self.assertRaises(ValueError):
            fpl_articles.fpl_squad(rows)

    def test_priceless_rows_are_excluded(self):
        rows = _pool()
        rows[0]["price"] = None
        entries, _meta = fpl_articles.fpl_squad(rows)
        self.assertNotIn(rows[0]["name"], [e["name"] for e in entries])
```

- [x] **Step 2: Run them, verify they fail**

```bash
python3 -m unittest tests.test_fpl_articles.TestFplSquad -v
```

Expected: FAIL — `module 'evmax.fpl_articles' has no attribute 'fpl_squad'`.

- [x] **Step 3: Implement**

Append to `evmax/fpl_articles.py`:

```python
def _club_counts(squad: list) -> dict:
    counts: dict = {}
    for r in squad:
        counts[r["team"]] = counts.get(r["team"], 0) + 1
    return counts


def _club_ok(squad: list, candidate: dict, replacing=None) -> bool:
    """Would adding `candidate` (optionally replacing `replacing`) stay legal?"""
    counts = _club_counts(squad)
    if replacing is not None:
        counts[replacing["team"]] = counts.get(replacing["team"], 0) - 1
    return counts.get(candidate["team"], 0) < MAX_PER_CLUB


def _key(r: dict) -> tuple:
    """Identity for squad membership. Name alone collides across test fixtures and,
    in principle, across two real players sharing a web_name."""
    return (r["name"], r["team"], r["position"], r["price"])


def fpl_squad(rows: list, budget: float = SQUAD_BUDGET,
              max_per_club: int = MAX_PER_CLUB) -> tuple:
    """A legal 15-man FPL squad: quota, budget, formation and club cap.

    Returns (entries, meta) with the same shape articles.wildcard_squad returns, so
    the renderer and the pitch SVG need no FPL-specific handling:
      entries: 15 row copies, each with role ("XI"/"Bench") and a 1-based rank
               (1-11 XI by x_points desc, 12-15 bench).
      meta:    {"total_cost", "xi_xpoints", "formation", "budget", "left_over"}

    Method: sweep every legal XI formation, greedily build the cheapest legal bench
    and the best XI for each, repair over budget by the smallest xPts-lost-per-pound,
    then spend what is left on the best xPts-gained-per-pound XI upgrade. Best
    xi_xpoints wins.

    The club cap is checked on every selection AND every swap, not once at the end.
    Checking at the end would mean rejecting an otherwise-optimal squad with no way
    to repair it; checking inline means the search only ever walks legal states.

    Still a greedy heuristic, not an exact solver — same as the World Cup builder,
    and the same caveat applies: it will not always find the true optimum.

    Raises ValueError if no legal squad exists in any formation.
    """
    pool = [r for r in rows if r.get("price") is not None and r.get("team")]
    for pos, need in SQUAD_QUOTA.items():
        have = sum(1 for r in pool if r.get("position") == pos)
        if have < need:
            raise ValueError(
                f"insufficient {pos} pool for an FPL squad: need {need}, have {have}")

    best = None
    last_err = None
    for xi_counts in legal_xi_formations():
        try:
            entries, meta = _squad_for_formation(pool, xi_counts, budget,
                                                 max_per_club)
        except ValueError as e:
            last_err = e
            continue
        key = (meta["xi_xpoints"], -meta["total_cost"])
        if best is None or key > best[0]:
            best = (key, entries, meta)
    if best is None:
        raise ValueError(f"no legal FPL squad in any formation: {last_err}")
    return best[1], best[2]


def _squad_for_formation(pool: list, xi_counts: dict, budget: float,
                         max_per_club: int) -> tuple:
    """One greedy build with the XI formation fixed. See fpl_squad's docstring."""
    global MAX_PER_CLUB
    saved_cap, MAX_PER_CLUB = MAX_PER_CLUB, max_per_club
    try:
        return _build(pool, xi_counts, budget)
    finally:
        MAX_PER_CLUB = saved_cap
```

Mutating a module global to pass a parameter is a bug waiting to happen — it is not thread-safe and it hides the dependency. Thread the cap explicitly instead:

```python
def _squad_for_formation(pool: list, xi_counts: dict, budget: float,
                         cap: int) -> tuple:
    """One greedy build with the XI formation fixed. See fpl_squad's docstring."""

    def club_ok(squad, candidate, replacing=None):
        counts = _club_counts(squad)
        if replacing is not None:
            counts[replacing["team"]] = counts.get(replacing["team"], 0) - 1
        return counts.get(candidate["team"], 0) < cap

    # --- Bench: the cheapest legal filler at each position the XI does not field.
    # Philosophy carried over from the World Cup builder: spend nothing on the
    # bench, spend everything on the XI.
    squad: list = []
    bench_flags: dict = {}

    def take(candidate, is_bench):
        squad.append(dict(candidate))
        bench_flags[_key(candidate)] = is_bench

    bench_quota = {pos: SQUAD_QUOTA[pos] - xi_counts.get(pos, 0)
                   for pos in SQUAD_QUOTA}
    bench_quota["GK"] = 1                      # 2 keepers, exactly 1 starts
    for pos in ("GK", "DEF", "MID", "FWD"):
        need = bench_quota[pos]
        candidates = sorted([r for r in pool if r["position"] == pos],
                            key=lambda r: (r["price"], -r["x_points"]))
        taken = 0
        for c in candidates:
            if taken >= need:
                break
            if _key(c) in bench_flags or not club_ok(squad, c):
                continue
            take(c, True)
            taken += 1
        if taken < need:
            raise ValueError(f"cannot fill the {pos} bench under the club cap")

    # --- XI: the best x_points players completing each position's quota.
    for pos in ("GK", "DEF", "MID", "FWD"):
        need = xi_counts.get(pos, 1 if pos == "GK" else 0)
        candidates = sorted([r for r in pool if r["position"] == pos],
                            key=lambda r: -r["x_points"])
        taken = 0
        for c in candidates:
            if taken >= need:
                break
            if _key(c) in bench_flags or not club_ok(squad, c):
                continue
            take(c, False)
            taken += 1
        if taken < need:
            raise ValueError(f"cannot fill the {pos} XI slots under the club cap")

    def total_cost(sq):
        return round(sum(r["price"] for r in sq), 2)

    def in_squad(sq):
        return {_key(r) for r in sq}

    # --- Repair 3a: downgrade until legal on budget, smallest xPts loss per pound.
    guard = 0
    while total_cost(squad) > budget and guard < len(squad) * len(pool):
        guard += 1
        best_swap, best_ratio = None, None
        members = in_squad(squad)
        for i, slot in enumerate(squad):
            cheaper = [r for r in pool
                       if r["position"] == slot["position"]
                       and _key(r) not in members
                       and r["price"] < slot["price"]
                       and club_ok(squad, r, replacing=slot)]
            if not cheaper:
                continue
            cheaper.sort(key=lambda r: (r["price"], -r["x_points"]))
            repl = cheaper[0]
            saved = slot["price"] - repl["price"]
            ratio = ((slot["x_points"] - repl["x_points"]) / saved
                     if saved > 0 else float("inf"))
            if best_ratio is None or ratio < best_ratio:
                best_ratio, best_swap = ratio, (i, repl)
        if best_swap is None:
            break
        i, repl = best_swap
        was_bench = bench_flags[_key(squad[i])]
        squad[i] = dict(repl)
        bench_flags[_key(repl)] = was_bench

    if total_cost(squad) > budget:
        raise ValueError(
            f"no legal 15-man squad fits within budget {budget}m "
            f"(cheapest assembled squad costs {total_cost(squad)}m)")

    # --- Repair 3b: spend what is left on the best XI upgrade per pound.
    guard = 0
    while guard < len(squad) * len(pool):
        guard += 1
        left_over = round(budget - total_cost(squad), 2)
        if left_over <= 0:
            break
        best_swap, best_ratio = None, 0.0
        members = in_squad(squad)
        for i, slot in enumerate(squad):
            if bench_flags[_key(slot)]:
                continue           # the bench stays cheap by design
            better = [r for r in pool
                      if r["position"] == slot["position"]
                      and _key(r) not in members
                      and r["price"] <= left_over + slot["price"]
                      and r["x_points"] > slot["x_points"]
                      and club_ok(squad, r, replacing=slot)]
            if not better:
                continue
            better.sort(key=lambda r: -r["x_points"])
            repl = better[0]
            spent = repl["price"] - slot["price"]
            ratio = ((repl["x_points"] - slot["x_points"]) / spent
                     if spent > 0 else float("inf"))
            if ratio > best_ratio:
                best_ratio, best_swap = ratio, (i, repl)
        if best_swap is None:
            break
        i, repl = best_swap
        squad[i] = dict(repl)
        bench_flags[_key(repl)] = False

    # --- Finalize.
    xi = sorted([r for r in squad if not bench_flags[_key(r)]],
                key=lambda r: -r["x_points"])
    bench = sorted([r for r in squad if bench_flags[_key(r)]],
                   key=lambda r: -r["x_points"])

    # Legality gate. The construction above should be safe by design; this raises
    # rather than ever publishing an illegal lineup — the World Cup site shipped a
    # 2-5-3 once because only the pool, not the XI's slots, was guarded.
    counts = {pos: sum(1 for r in xi if r["position"] == pos) for pos in POS_MIN}
    for pos, need in POS_MIN.items():
        if not (need <= counts.get(pos, 0) <= POS_MAX[pos]):
            raise ValueError(
                f"FPL XI violates formation limits at {pos}: {counts.get(pos, 0)} "
                f"(legal range {need}-{POS_MAX[pos]}); formation {formation_of(xi)}")
    clubs = _club_counts(squad)
    over = {t: c for t, c in clubs.items() if c > cap}
    if over:
        raise ValueError(f"FPL squad violates the {cap}-per-club cap: {over}")

    entries = []
    for i, r in enumerate(xi, 1):
        e = dict(r)
        e["role"], e["rank"] = "XI", i
        entries.append(e)
    for i, r in enumerate(bench, len(xi) + 1):
        e = dict(r)
        e["role"], e["rank"] = "Bench", i
        entries.append(e)

    cost = total_cost(squad)
    meta = {
        "total_cost": cost,
        "xi_xpoints": round(sum(r["x_points"] for r in xi), 2),
        "formation": formation_of(xi),
        "budget": budget,
        "left_over": round(budget - cost, 2),
    }
    return entries, meta
```

Update `fpl_squad`'s call to match: `_squad_for_formation(pool, xi_counts, budget, max_per_club)`. Delete the `_club_ok` module-level helper drafted above — `club_ok` is now a closure over `cap`, and two functions doing the same job with different cap sources is exactly the drift this task is trying to avoid.

- [x] **Step 4: Run the tests**

```bash
python3 -m unittest tests.test_fpl_articles -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add evmax/fpl_articles.py tests/test_fpl_articles.py && git commit -m "feat(fpl): 15-man squad builder with the three-per-club cap"
```

---

## Task 8: The fixture ticker — blanks, doubles and provenance

The ticker is one row per club, not one per fixture, because a club can play **zero or two** times in a gameweek (spec §5.1). Neither case exists in the current feed and neither will for months — they emerge from cup progression — so they have to be correct before any live data exhibits them. That means synthetic tests are the only way to get this right, and they are not optional.

The other requirement is spec §8's confidence labelling: ESPN prices fixtures only a week or two out, so a fixture is either market-derived or priors-derived, and the column must say which. Silent uniformity would be a misrepresentation.

**Files:**
- Modify: `evmax/fpl_articles.py`
- Test: `tests/test_fpl_articles.py`

- [x] **Step 1: Write the failing tests**

Append to `tests/test_fpl_articles.py`:

```python
def _match(home, away, p_cs_home=0.4, p_cs_away=0.2, gf=1.6, ga=1.1,
           market=True, kickoff="2026-08-21T19:00:00+00:00"):
    return {"match_id": f"{home}-{away}", "home": home, "away": away,
            "kickoff": kickoff, "exp_home_goals": gf, "exp_away_goals": ga,
            "exp_total": round(gf + ga, 2), "top_scoreline": "2-1",
            "p_home": 0.5, "p_draw": 0.25, "p_away": 0.25,
            "p_cs_home": p_cs_home, "p_cs_away": p_cs_away, "market": market}


class TestTicker(unittest.TestCase):
    def test_one_row_per_club_with_opponent_and_both_sides(self):
        out = fpl_articles.ticker([_match("ARS", "LIV")], ["ARS", "LIV"])
        self.assertEqual(sorted(e["name"] for e in out), ["ARS", "LIV"])
        by_name = {e["name"]: e for e in out}
        self.assertEqual(by_name["ARS"]["opponents"], "LIV (H)")
        self.assertEqual(by_name["LIV"]["opponents"], "ARS (A)")
        self.assertAlmostEqual(by_name["ARS"]["exp_goals_for"], 1.6)
        self.assertAlmostEqual(by_name["ARS"]["exp_goals_against"], 1.1)
        self.assertAlmostEqual(by_name["LIV"]["exp_goals_for"], 1.1)
        self.assertAlmostEqual(by_name["LIV"]["exp_goals_against"], 1.6)

    def test_double_gameweek_sums_goals_and_clean_sheets(self):
        matches = [_match("ARS", "LIV", p_cs_home=0.4, gf=1.6, ga=1.1),
                   _match("BUR", "ARS", p_cs_away=0.5, gf=0.9, ga=1.8,
                          kickoff="2026-08-24T19:00:00+00:00")]
        out = fpl_articles.ticker(matches, ["ARS", "LIV", "BUR"])
        ars = {e["name"]: e for e in out}["ARS"]
        self.assertEqual(ars["fixtures"], 2)
        self.assertEqual(ars["opponents"], "LIV (H), BUR (A)")
        self.assertAlmostEqual(ars["exp_clean_sheets"], 0.9)      # 0.4 + 0.5
        self.assertAlmostEqual(ars["exp_goals_for"], 3.4)         # 1.6 + 1.8
        self.assertAlmostEqual(ars["exp_goals_against"], 2.0)     # 1.1 + 0.9

    def test_blank_gameweek_club_is_listed_with_zeroes(self):
        """A blank is the single most actionable thing a ticker can tell a manager
        — omitting the club entirely hides it."""
        out = fpl_articles.ticker([_match("ARS", "LIV")], ["ARS", "LIV", "EVE"])
        eve = {e["name"]: e for e in out}["EVE"]
        self.assertEqual(eve["fixtures"], 0)
        self.assertEqual(eve["opponents"], "—")
        self.assertEqual(eve["exp_clean_sheets"], 0.0)
        self.assertEqual(eve["env"], "blank")

    def test_sorted_by_expected_clean_sheets_with_ranks(self):
        matches = [_match("ARS", "LIV", p_cs_home=0.6, p_cs_away=0.1)]
        out = fpl_articles.ticker(matches, ["ARS", "LIV"])
        self.assertEqual([e["name"] for e in out], ["ARS", "LIV"])
        self.assertEqual([e["rank"] for e in out], [1, 2])

    def test_provenance_is_per_club(self):
        matches = [_match("ARS", "LIV", market=True),
                   _match("BUR", "EVE", market=False)]
        out = fpl_articles.ticker(matches, ["ARS", "LIV", "BUR", "EVE"])
        by_name = {e["name"]: e for e in out}
        self.assertEqual(by_name["ARS"]["basis"], "market")
        self.assertEqual(by_name["BUR"]["basis"], "model")
        self.assertEqual(by_name["EVE"]["basis"], "model")

    def test_mixed_provenance_double_reports_the_weaker_basis(self):
        """One priced fixture and one unpriced is not "market" — claiming it would
        overstate the confidence of the combined number."""
        matches = [_match("ARS", "LIV", market=True),
                   _match("BUR", "ARS", market=False,
                          kickoff="2026-08-24T19:00:00+00:00")]
        out = fpl_articles.ticker(matches, ["ARS", "LIV", "BUR"])
        self.assertEqual({e["name"]: e for e in out}["ARS"]["basis"], "mixed")

    def test_environment_labels(self):
        matches = [_match("ARS", "LIV", gf=2.2, ga=1.4),     # 3.6 total -> blowout
                   _match("BUR", "EVE", gf=1.0, ga=0.9)]     # 1.9 total -> avoid
        out = fpl_articles.ticker(matches, ["ARS", "LIV", "BUR", "EVE"])
        by_name = {e["name"]: e for e in out}
        self.assertEqual(by_name["ARS"]["env"], "blowout")
        self.assertEqual(by_name["BUR"]["env"], "avoid")
```

- [x] **Step 2: Run them, verify they fail**

```bash
python3 -m unittest tests.test_fpl_articles.TestTicker -v
```

Expected: FAIL — no `ticker`.

- [x] **Step 3: Implement**

Append to `evmax/fpl_articles.py`:

```python
# Goal-environment thresholds on a fixture's combined expected goals. Carried
# over from the World Cup ticker: the question ("is this a game to target
# attackers in?") and the scale (goals per match) are the same in both games.
ENV_BLOWOUT_MIN = 3.0
ENV_AVOID_MAX = 2.1


def _env_for(exp_total: float, fixture_count: int) -> str:
    if fixture_count == 0:
        return "blank"
    if fixture_count > 1:
        return "double"
    if exp_total >= ENV_BLOWOUT_MIN:
        return "blowout"
    if exp_total <= ENV_AVOID_MAX:
        return "avoid"
    return "balanced"


def ticker(matches: list, clubs: list) -> list:
    """One row per club: expected clean sheets, goals for/against, provenance.

    Per CLUB, not per fixture, because FPL gameweeks have blanks and doubles
    (spec §5.1). `clubs` is the full league list, so a club with no fixture this
    gameweek still gets a row — a blank is the most actionable thing a ticker can
    tell a manager, and dropping the club would hide it.

    exp_clean_sheets SUMS across a double rather than computing "at least one
    clean sheet". A defender is paid per clean sheet kept, so two fixtures at 45%
    are worth 0.9 clean sheets of points, not the 70% chance of keeping at least
    one. The summed figure is the one that maps to points; it can exceed 1.0 and
    that is correct.

    `basis` is spec §8's confidence label: "market" when every one of the club's
    fixtures is odds-derived, "model" when none is, "mixed" for a double with one
    of each. Mixed reports as mixed rather than rounding up to market — the
    combined number is only as good as its weaker half, and the site's whole
    positioning is that it says which is which.
    """
    agg: dict = {c: {"name": c, "fixtures": 0, "opponents": [],
                     "exp_clean_sheets": 0.0, "exp_goals_for": 0.0,
                     "exp_goals_against": 0.0, "exp_total": 0.0,
                     "market": 0, "model": 0, "kickoff": None}
                 for c in clubs}

    for m in matches:
        for team, opponent, venue, p_cs, gf, ga in (
            (m["home"], m["away"], "H", m.get("p_cs_home", 0.0),
             m.get("exp_home_goals", 0.0), m.get("exp_away_goals", 0.0)),
            (m["away"], m["home"], "A", m.get("p_cs_away", 0.0),
             m.get("exp_away_goals", 0.0), m.get("exp_home_goals", 0.0)),
        ):
            row = agg.get(team)
            if row is None:
                # A club in the fixture list but not in `clubs` — take it anyway
                # rather than silently dropping a real fixture.
                row = agg[team] = {"name": team, "fixtures": 0, "opponents": [],
                                   "exp_clean_sheets": 0.0, "exp_goals_for": 0.0,
                                   "exp_goals_against": 0.0, "exp_total": 0.0,
                                   "market": 0, "model": 0, "kickoff": None}
            row["fixtures"] += 1
            row["opponents"].append((m["kickoff"], f"{opponent} ({venue})"))
            row["exp_clean_sheets"] += p_cs
            row["exp_goals_for"] += gf
            row["exp_goals_against"] += ga
            row["exp_total"] += m.get("exp_total", gf + ga)
            row["market" if m.get("market") else "model"] += 1
            if row["kickoff"] is None or m["kickoff"] < row["kickoff"]:
                row["kickoff"] = m["kickoff"]

    out = []
    for row in agg.values():
        ordered = [label for _ko, label in sorted(row["opponents"])]
        if row["market"] and row["model"]:
            basis = "mixed"
        elif row["market"]:
            basis = "market"
        else:
            basis = "model"
        out.append({
            "name": row["name"],
            # `team` is what the shared table renderer prints in its second
            # column; the ticker's subject IS a club, so the opponent list is the
            # useful thing to put there.
            "team": ", ".join(ordered) if ordered else "—",
            "position": "—",
            "opponents": ", ".join(ordered) if ordered else "—",
            "fixtures": row["fixtures"],
            "exp_clean_sheets": round(row["exp_clean_sheets"], 3),
            "exp_goals_for": round(row["exp_goals_for"], 2),
            "exp_goals_against": round(row["exp_goals_against"], 2),
            "env": _env_for(row["exp_total"], row["fixtures"]),
            "basis": basis if row["fixtures"] else "—",
            "kickoff": row["kickoff"],
        })

    out.sort(key=lambda r: (-r["exp_clean_sheets"], r["name"]))
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out
```

- [x] **Step 4: Run the tests**

```bash
python3 -m unittest tests.test_fpl_articles -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add evmax/fpl_articles.py tests/test_fpl_articles.py && git commit -m "feat(fpl): fixture ticker with blank/double aggregation and per-club provenance"
```

---

## Task 9: Section-aware prose — cache path, unit word, FPL glossary

`writer.article_prose` caches to `data/articles/round-{N}/{slug}.md`. An FPL gameweek 1 would collide with World Cup round 1's cached prose and serve a year-old article about Brazil. The LLM prompt says "Round : {n}" and has no vocabulary for `p_defcon`, `exp_clean_sheets`, `basis` or `cs_points`.

**Files:**
- Modify: `evmax/writer.py`, `evmax/prompts.py`
- Test: `tests/test_fpl_site.py`

- [x] **Step 1: Write the failing tests**

Append to `tests/test_fpl_site.py`:

```python
import os
import tempfile

from evmax import prompts, writer


class TestProseCacheNamespace(unittest.TestCase):
    def test_fpl_and_world_cup_caches_do_not_collide(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, headline in (("round-1", "World Cup one"),
                                   ("fpl-gw1", "Gameweek one")):
                os.makedirs(os.path.join(tmp, name))
                with open(os.path.join(tmp, name, "captains.md"), "w",
                          encoding="utf-8") as fh:
                    fh.write(f"# {headline}\n\n> Standfirst\n\nBody.\n\n"
                             f"**Bottom line:** BL\n")
            wc = writer.article_prose("captains", 1, _ENTRIES, ["x_points"],
                                      cache_dir=tmp, use_llm=False)
            fpl = writer.article_prose("captains", 1, _ENTRIES, ["x_points"],
                                       cache_dir=tmp, use_llm=False,
                                       cache_name="fpl-gw1")
            self.assertNotEqual(wc["headline"], fpl["headline"])
            self.assertIn("Gameweek", fpl["headline"])


class TestPromptUnit(unittest.TestCase):
    def test_default_prompt_says_round(self):
        p = prompts.build_prompt("captains", 5, _ENTRIES)
        self.assertIn("Round        : 5", p)

    def test_fpl_prompt_says_gameweek_and_carries_the_glossary(self):
        p = prompts.build_prompt("defcon", 1, _ENTRIES, unit="Gameweek")
        self.assertIn("Gameweek     : 1", p)
        self.assertIn("p_defcon", p)
        self.assertIn("exp_clean_sheets", p)
        self.assertNotIn("p_advance", p.split("--- DATA ---")[0].split(
            "Refer to the data fields")[1])
```

That last assertion is too clever and will break on any prompt rewording. Replace it with the thing actually worth pinning:

```python
    def test_world_cup_prompt_does_not_carry_the_fpl_glossary(self):
        p = prompts.build_prompt("captains", 5, _ENTRIES)
        self.assertNotIn("p_defcon", p)
```

- [x] **Step 2: Run them, verify they fail**

```bash
python3 -m unittest tests.test_fpl_site.TestProseCacheNamespace tests.test_fpl_site.TestPromptUnit -v
```

Expected: FAIL — `article_prose() got an unexpected keyword argument 'cache_name'`.

- [x] **Step 3: Implement**

In `evmax/writer.py`, extend `article_prose`:

```python
def article_prose(
    article: str,
    round_no: int,
    entries: list,
    columns: list,
    cache_dir: str = "data/articles",
    use_llm: bool = True,
    subject=None,
    cache_name: str | None = None,
    unit: str = "Round",
) -> dict:
    """Generate prose for an article using tiered resolution: cache → LLM → template.

    cache_name : subdirectory under cache_dir, defaulting to "round-{round_no}".
                 The FPL build passes "fpl-gw{n}" — without it, FPL gameweek 1 and
                 World Cup round 1 share a cache entry and one serves the other's
                 article.
    unit       : the reader-facing word for the period ("Round" or "Gameweek"),
                 passed through to the LLM prompt and the templates.
    """
    cache_path = os.path.join(cache_dir, cache_name or f"round-{round_no}",
                              f"{article}.md")
    if os.path.isfile(cache_path):
        return _parse_cache_md(cache_path)

    if use_llm:
        result = _llm_prose(article, round_no, entries, columns, cache_dir,
                            subject=subject, unit=unit)
        if result is not None:
            return result

    return _template_prose(article, entries, columns, round_no=round_no,
                           subject=subject, unit=unit)
```

Thread `unit` through `_llm_prose` (which passes it to `build_prompt`) and `_template_prose`. In `_template_prose`, pass it to the template lambdas by making the generic fallback unit-aware:

```python
_GENERIC_TEMPLATE = {
    "headline": lambda e, r, slug, subj, unit="Round": (
        f"{unit} analysis: {slug.replace('-', ' ').title()}"),
    ...
}
```

and at the call site:

```python
        headline = _GENERIC_TEMPLATE["headline"](entries, round_no, article, subj, unit)
```

Also extend the FPL-slug template dispatch — `_template_prose` currently hardcodes the no-subject article list. Add the FPL team-framed slugs:

```python
    elif article in ("best-xi", "wildcard", "matches", "fixtures", "ticker"):
        subj = None
```

In `evmax/prompts.py`, parameterise the unit and add the glossary. Change the header line in `ARTICLE_PROMPT`:

```python
Article slug : {slug}
{unit:<13}: {round_no}
```

and add a `{fpl_glossary}` placeholder immediately after the existing field-vocabulary block. Then:

```python
_FPL_GLOSSARY = """\
  - p_defcon → the probability that player records enough defensive actions to earn
    the 2-point defensive-contribution bonus. Write it as a percentage, e.g. 71%.
    The threshold is 10 for defenders and 12 for midfielders and forwards; the entry
    carries it as defcon_threshold. Goalkeepers are not eligible at all.
  - defcon → the POINTS that probability is worth (exactly 2 x p_defcon). Prefer the
    probability in prose; the table already prints the points.
  - cs_points → the share of a defender's or goalkeeper's projection that comes from
    clean sheets, as opposed to DefCon, bonus or attacking returns. Use it to say
    WHERE a defensive pick's points come from.
  - bonus → expected bonus points from the BPS rank-within-match model.
  - exp_clean_sheets → expected clean sheets for that club this gameweek. It SUMS
    across a double gameweek, so it can exceed 1.0 — say "1.2 expected clean sheets
    across two fixtures", never "120% chance of a clean sheet".
  - fixtures → how many matches that club plays this gameweek. 0 is a BLANK (say so
    explicitly, it is the most actionable thing on the page); 2 is a DOUBLE.
  - opponents → already formatted as "LIV (H), BUR (A)" — quote it as-is.
  - basis → "market" means that club's fixture is priced by the betting market;
    "model" means it is not yet priced and the numbers come from our own team
    ratings; "mixed" means one of each across a double. Say which, plainly, when you
    cite a ticker number — never present model-derived and market-derived numbers as
    if they carried the same confidence.
  - kickoff_order → the order this player's match kicks off among the candidates
    (1 = earliest). Relevant to the vice-captain decision, not the captain one.
"""


def build_prompt(slug, round_no, entries, subject=None, unit="Round"):
    ...
    return ARTICLE_PROMPT.format(
        slug=slug,
        unit=unit,
        round_no=round_no,
        fpl_glossary=_FPL_GLOSSARY if unit == "Gameweek" else "",
        subject_instruction=subject_instruction,
        entries_json=json.dumps(entries, ensure_ascii=False, indent=2),
    )
```

Add FPL branches to the `subject_instruction` chain, before the generic `elif subject is not None:` fallback:

```python
    elif slug == "defcon":
        subject_instruction = (
            "Focus      : Rank players by how reliably they earn the 2-point "
            "defensive-contribution bonus (p_defcon). This is a THRESHOLD, not a "
            "rate — a player either clears his position's action count in a given "
            "match or he does not — so frame it as 'hits the threshold in X% of "
            "simulations', never as an average number of actions. Name the best "
            "defender and the best midfielder separately: their thresholds differ "
            "(10 vs 12), so they are not competing for the same slot.\n"
        )
    elif slug == "ticker":
        subject_instruction = (
            "Focus      : Cover the gameweek club by club — who has the best "
            "clean-sheet odds (exp_clean_sheets), which fixtures are worth "
            "targeting attackers in (env=\"blowout\"), which to fade "
            "(env=\"avoid\"). Call out every club with fixtures=0 (a BLANK) and "
            "every club with fixtures=2 (a DOUBLE) explicitly and early — those "
            "are the two facts that change a manager's week. State the `basis` "
            "for any number you cite.\n"
        )
```

- [x] **Step 4: Run the tests**

```bash
python3 -m unittest tests.test_fpl_site tests.test_site_writer -v
```

Expected: PASS both. `test_site_writer` unchanged proves the WC prose path is intact.

- [x] **Step 5: Commit**

```bash
git add evmax/writer.py evmax/prompts.py tests/test_fpl_site.py && git commit -m "feat(site): section-aware prose cache, gameweek unit and FPL field glossary"
```

---

## Task 10: Deterministic prose templates for the six FPL slugs

Owner decision: a `--no-llm` build must read like a real article. The generic fallback produces "Gameweek analysis: Defcon" and a sentence about captain EV, which is not publishable for an article whose entire subject is a threshold probability.

**Files:**
- Modify: `evmax/writer.py`
- Test: `tests/test_fpl_site.py`

- [x] **Step 1: Write the failing test**

Append to `tests/test_fpl_site.py`:

```python
_TICKER_ENTRY = {"name": "ARS", "rank": 1, "opponents": "LIV (H)", "fixtures": 1,
                 "exp_clean_sheets": 0.42, "exp_goals_for": 1.9,
                 "exp_goals_against": 0.9, "env": "balanced", "basis": "market"}
_DEFCON_ENTRY = {"name": "Gabriel", "rank": 1, "position": "DEF", "team": "ARS",
                 "p_defcon": 0.71, "defcon": 1.42, "defcon_threshold": 10,
                 "x_points": 5.4, "price": 6.0}


class TestFplTemplates(unittest.TestCase):
    def _prose(self, slug, entries):
        return writer.article_prose(slug, 1, entries, ["x_points"],
                                    cache_dir="/nonexistent", use_llm=False,
                                    cache_name="fpl-gw1", unit="Gameweek")

    def test_every_fpl_slug_has_a_real_template(self):
        cases = {
            "captains": [dict(_ENTRIES[0], captain_ev=12.0, ceiling=10.0,
                              kickoff_order=1, team="ARS", position="FWD")],
            "wildcard": [dict(_ENTRIES[0], role="XI", team="ARS", position="MID",
                              ceiling=9.0)],
            "ticker": [_TICKER_ENTRY],
            "defenders": [dict(_ENTRIES[0], position="DEF", team="ARS",
                               cs_points=1.6, defcon=1.4, bonus=0.5, ceiling=9.0)],
            "efficiency": [dict(_ENTRIES[0], value=1.2, tier="Budget", team="ARS",
                                position="MID", ceiling=9.0)],
            "defcon": [_DEFCON_ENTRY],
        }
        for slug, entries in cases.items():
            prose = self._prose(slug, entries)
            with self.subTest(slug=slug):
                self.assertNotIn("analysis:", prose["headline"].lower(),
                                 f"{slug} fell through to the generic template")
                self.assertTrue(prose["standfirst"])
                self.assertTrue(prose["bottom_line"])
                self.assertIn("<p>", prose["body_html"])

    def test_defcon_prose_states_the_probability_and_threshold(self):
        prose = self._prose("defcon", [_DEFCON_ENTRY])
        self.assertIn("71", prose["standfirst"] + prose["body_html"])
        self.assertIn("10", prose["body_html"])

    def test_ticker_prose_names_blanks(self):
        entries = [_TICKER_ENTRY,
                   dict(_TICKER_ENTRY, name="EVE", rank=2, fixtures=0,
                        opponents="—", exp_clean_sheets=0.0, env="blank",
                        basis="—")]
        prose = self._prose("ticker", entries)
        self.assertIn("EVE", prose["body_html"])
        self.assertIn("blank", prose["body_html"].lower())

    def test_empty_entries_do_not_crash_any_slug(self):
        for slug in ("captains", "wildcard", "ticker", "defenders", "efficiency",
                     "defcon"):
            with self.subTest(slug=slug):
                prose = self._prose(slug, [])
                self.assertTrue(prose["headline"])
```

- [x] **Step 2: Run it, verify it fails**

```bash
python3 -m unittest tests.test_fpl_site.TestFplTemplates -v
```

Expected: FAIL — headlines read "Gameweek analysis: Defcon".

- [x] **Step 3: Implement**

The existing `_TEMPLATES` dict is keyed by slug, and four FPL slugs (`captains`, `wildcard`, `defenders`, `efficiency`) collide with World Cup slugs that must keep their current prose. Key the FPL templates separately and select on the unit.

In `evmax/writer.py`, after `_TEMPLATES`, add:

```python
def _pct(v) -> str:
    return f"{(v or 0.0) * 100:.0f}%"


_FPL_TEMPLATES = {
    "captains": {
        "headline": lambda e, r, subj: (
            f"{subj or e[0]['name']} is the gameweek {r} captain"),
        "standfirst": lambda e, r, subj: (
            f"{_fmt_pts(e[0]['captain_ev'])} captain EV, "
            f"{_fmt_pts(e[0]['ceiling'])} ceiling — the best armband in the model."),
        "body": lambda e, r, subj: (
            f"<p>{html.escape(e[0]['name'])} ({html.escape(e[0].get('team', ''))}) "
            f"projects {_fmt_pts(e[0]['captain_ev'])} captained, off "
            f"{_fmt_pts(e[0]['x_points'])} expected points, with a ceiling of "
            f"{_fmt_pts(e[0]['ceiling'])} — his 85th-percentile simulation.</p>"
            + (f"<p>{html.escape(e[1]['name'])} is the alternative at "
               f"{_fmt_pts(e[1]['captain_ev'])}. "
               + ("He kicks off first, so he is the safer vice."
                  if e[1].get("kickoff_order", 99) < e[0].get("kickoff_order", 99)
                  else "He kicks off later, so he works as a vice only if your "
                       "captain's match is already done.")
               + "</p>" if len(e) > 1 else "")),
        "bottom_line": lambda e, r, subj: (
            f"Captain {e[0]['name']} — {_fmt_pts(e[0]['captain_ev'])} is the "
            f"highest doubled projection on the board."),
    },
    "wildcard": {
        "headline": lambda e, r, subj: (
            f"The gameweek {r} draft squad: {_wc_formation(e)}"),
        "standfirst": lambda e, r, subj: (
            f"A legal 15 for {_wc_total_cost(e):.1f}m, with an XI projecting "
            f"{_wc_xi_xpoints(e):.1f} points."),
        "body": lambda e, r, subj: (
            f"<p>The model's draft squad lines up {_wc_formation(e)} and costs "
            f"{_wc_total_cost(e):.1f}m of the 100.0m budget, leaving "
            f"{_wc_left_over(e):.1f}m in the bank. The starting XI projects "
            f"{_wc_xi_xpoints(e):.1f} points.</p>"
            f"<p>The bench is deliberately cheap — four enablers that make the 15 "
            f"legal so the spending sits in the XI. No club contributes more than "
            f"three players, which is the squad rule that most often forces a "
            f"compromise on the premium picks.</p>"),
        "bottom_line": lambda e, r, subj: (
            f"Build around this {_wc_formation(e)}: "
            f"{_wc_xi_xpoints(e):.1f} projected points for "
            f"{_wc_total_cost(e):.1f}m."),
    },
    "ticker": {
        "headline": lambda e, r, subj: (
            f"Gameweek {r} fixture ticker: {e[0]['name']} lead the clean sheets"),
        "standfirst": lambda e, r, subj: (
            f"{e[0]['name']} project {e[0]['exp_clean_sheets']:.2f} expected clean "
            f"sheets against {e[0]['opponents']}."),
        "body": lambda e, r, subj: (
            f"<p>{html.escape(e[0]['name'])} top the ticker at "
            f"{e[0]['exp_clean_sheets']:.2f} expected clean sheets "
            f"({html.escape(e[0]['opponents'])}), conceding an expected "
            f"{e[0]['exp_goals_against']:.1f}. "
            f"{'These numbers are market-derived.' if e[0].get('basis') == 'market' else 'These numbers come from our own team ratings, not the betting market — treat them as the softer read.'}"
            f"</p>"
            + _fpl_ticker_blanks_doubles(e)),
        "bottom_line": lambda e, r, subj: (
            f"Target {e[0]['name']} defenders — "
            f"{e[0]['exp_clean_sheets']:.2f} expected clean sheets is the best on "
            f"the board."),
    },
    "defenders": {
        "headline": lambda e, r, subj: (
            f"{subj or e[0]['name']} leads the gameweek {r} defenders"),
        "standfirst": lambda e, r, subj: (
            f"{_fmt_pts(e[0]['x_points'])} expected points, with "
            f"{_fmt_pts(e[0].get('cs_points', 0))} of it from clean sheets alone."),
        "body": lambda e, r, subj: (
            f"<p>{html.escape(e[0]['name'])} "
            f"({html.escape(e[0].get('team', ''))}) projects "
            f"{_fmt_pts(e[0]['x_points'])}: "
            f"{_fmt_pts(e[0].get('cs_points', 0))} from clean sheets, "
            f"{_fmt_pts(e[0].get('defcon', 0))} from defensive contribution and "
            f"{_fmt_pts(e[0].get('bonus', 0))} from bonus. Where a defender's "
            f"points come from matters as much as the total — a clean-sheet "
            f"projection lives or dies on one fixture, while defensive "
            f"contribution pays regardless of the scoreline.</p>"),
        "bottom_line": lambda e, r, subj: (
            f"{e[0]['name']} at {_fmt_price(e[0].get('price'))} is the defensive "
            f"pick of the gameweek."),
    },
    "efficiency": {
        "headline": lambda e, r, subj: (
            f"{subj or e[0]['name']} is the best value in gameweek {r}"),
        "standfirst": lambda e, r, subj: (
            f"{e[0]['value']:.2f} points per million at "
            f"{_fmt_price(e[0].get('price'))}."),
        "body": lambda e, r, subj: (
            f"<p>{html.escape(e[0]['name'])} returns {e[0]['value']:.2f} points "
            f"per million — {_fmt_pts(e[0]['x_points'])} expected points at "
            f"{_fmt_price(e[0].get('price'))}.</p>"
            + _wc_efficiency_tier_paragraph(e)),
        "bottom_line": lambda e, r, subj: _wc_efficiency_tier_bottom_line(e),
    },
    "defcon": {
        "headline": lambda e, r, subj: (
            f"{subj or e[0]['name']} is the gameweek {r} DefCon banker"),
        "standfirst": lambda e, r, subj: (
            f"He clears the {e[0]['defcon_threshold']}-action threshold in "
            f"{_pct(e[0]['p_defcon'])} of simulations."),
        "body": lambda e, r, subj: (
            f"<p>{html.escape(e[0]['name'])} "
            f"({html.escape(e[0].get('team', ''))}) records at least "
            f"{e[0]['defcon_threshold']} defensive actions in "
            f"{_pct(e[0]['p_defcon'])} of our simulations, worth "
            f"{_fmt_pts(e[0].get('defcon', 0))} on its own. Defensive "
            f"contribution is a threshold, not a rate: a player either clears the "
            f"count in a given match or earns nothing, which is why we quote the "
            f"hit rate rather than an average.</p>"
            + (f"<p>{html.escape(e[1]['name'])} is next at "
               f"{_pct(e[1]['p_defcon'])} against a "
               f"{e[1]['defcon_threshold']}-action threshold.</p>"
               if len(e) > 1 else "")),
        "bottom_line": lambda e, r, subj: (
            f"{e[0]['name']} is the most reliable route to the 2-point defensive "
            f"bonus — {_pct(e[0]['p_defcon'])} of simulations."),
    },
}


def _fpl_ticker_blanks_doubles(entries: list) -> str:
    """A paragraph naming the gameweek's blanks and doubles, or "" if there are
    none. These are the two facts that change a manager's week, so they are never
    left to the reader to spot in the table."""
    blanks = [e["name"] for e in entries if e.get("fixtures") == 0]
    doubles = [e["name"] for e in entries if (e.get("fixtures") or 0) > 1]
    parts = []
    if doubles:
        parts.append(f"{', '.join(doubles)} play twice — a double gameweek, and "
                     f"the single biggest edge available")
    if blanks:
        parts.append(f"{', '.join(blanks)} have a blank gameweek and score nothing")
    if not parts:
        return ""
    return "<p>" + html.escape("; ".join(parts).capitalize()) + ".</p>"
```

Then select the FPL table in `_template_prose`:

```python
    table = _FPL_TEMPLATES if unit == "Gameweek" else _TEMPLATES
    tmpl = table.get(article)
```

and make the empty-entries early return unit-aware:

```python
    if not entries:
        body_html = "<p>No entries available for this article.</p>"
        return {
            "headline": f"{unit} analysis: {article}",
            ...
        }
```

- [x] **Step 4: Run the tests**

```bash
python3 -m unittest tests.test_fpl_site tests.test_site_writer -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add evmax/writer.py tests/test_fpl_site.py && git commit -m "feat(site): deterministic prose templates for the six FPL articles"
```

---

## Task 11: FPL preflight (spec §9)

Four warnings the spec names, plus the hard aborts that stop a build dying later with a misleading error. The World Cup's `_preflight` is the model: abort on missing caches, warn loudly on anything that would publish a visibly wrong number.

**Files:**
- Create: `evmax/fpl_build.py`
- Test: `tests/test_fpl_site.py`

- [x] **Step 1: Write the failing tests**

Append to `tests/test_fpl_site.py`:

```python
from datetime import datetime, timezone
from unittest import mock

from core import fixtures as core_fixtures
from evmax import fpl_build


def _fx(match_id, home, away, gw=1, priced=True):
    return core_fixtures.Fixture(
        match_id=match_id, home=home, away=away,
        kickoff=datetime(2026, 8, 21, 19, 0, tzinfo=timezone.utc),
        stage="GW", fantasy_round=gw, neutral=False,
        lam_home=1.5 if priced else None, lam_away=1.1 if priced else None)


class TestFplPreflight(unittest.TestCase):
    def test_aborts_when_the_gameweek_has_no_fixtures(self):
        with mock.patch.object(core_fixtures, "by_round", return_value=[]):
            with self.assertRaises(SystemExit) as ctx:
                fpl_build.preflight(1, players=[{"status": "i"}], cold_start=[])
        self.assertIn("no fixtures", str(ctx.exception).lower())

    def test_warns_on_unpriced_fixtures(self):
        fx = [_fx("m1", "ARS", "LIV"), _fx("m2", "BUR", "EVE", priced=False)]
        with mock.patch.object(core_fixtures, "by_round", return_value=fx):
            warnings = fpl_build.preflight(1, players=[{"status": "i"}],
                                           cold_start=[])
        self.assertTrue(any("BUR" in w and "unpriced" in w.lower()
                            for w in warnings))

    def test_warns_on_cold_start_players(self):
        fx = [_fx("m1", "ARS", "LIV")]
        with mock.patch.object(core_fixtures, "by_round", return_value=fx):
            warnings = fpl_build.preflight(
                1, players=[{"status": "i"}],
                cold_start=[{"name": "Newbie"}, {"name": "Rookie"}])
        self.assertTrue(any("cold-start" in w.lower() and "Newbie" in w
                            for w in warnings))

    def test_warns_when_no_player_carries_an_availability_flag(self):
        """Real FPL always has injuries. A bootstrap where all 563 players are
        status 'a' is a stale cache, and it would silently publish ruled-out
        players as nailed starters."""
        fx = [_fx("m1", "ARS", "LIV")]
        with mock.patch.object(core_fixtures, "by_round", return_value=fx):
            warnings = fpl_build.preflight(
                1, players=[{"status": "a"}, {"status": "a"}], cold_start=[])
        self.assertTrue(any("stale" in w.lower() for w in warnings))

    def test_no_stale_warning_when_flags_are_present(self):
        fx = [_fx("m1", "ARS", "LIV")]
        with mock.patch.object(core_fixtures, "by_round", return_value=fx):
            warnings = fpl_build.preflight(
                1, players=[{"status": "a"}, {"status": "i"}], cold_start=[])
        self.assertFalse(any("stale" in w.lower() for w in warnings))

    def test_unexpected_cache_miss_is_reported(self):
        """A miss with no stored artifact for this gameweek is expected (first
        build). A miss WITH stored artifacts means an input or the model source
        changed — worth saying out loud, because it explains a slow build."""
        with mock.patch.object(fpl_build.simcache, "artifacts_for",
                               return_value=["stale-key"]):
            warnings = fpl_build.cache_warnings(1, cache_hit=False)
        self.assertTrue(any("stale-key" in w or "1 stale" in w for w in warnings))

    def test_first_build_miss_is_silent(self):
        with mock.patch.object(fpl_build.simcache, "artifacts_for",
                               return_value=[]):
            self.assertEqual(fpl_build.cache_warnings(1, cache_hit=False), [])

    def test_cache_hit_is_silent(self):
        with mock.patch.object(fpl_build.simcache, "artifacts_for",
                               return_value=["k"]):
            self.assertEqual(fpl_build.cache_warnings(1, cache_hit=True), [])
```

- [x] **Step 2: Run them, verify they fail**

```bash
python3 -m unittest tests.test_fpl_site.TestFplPreflight -v
```

Expected: FAIL — `No module named 'evmax.fpl_build'`.

- [x] **Step 3: Implement**

Create `evmax/fpl_build.py` with the preflight only (the build pipeline lands in Task 12):

```python
"""Build the evmax FPL section for one gameweek.

Usage:
    python3 -m evmax.build --gw 1 [--sims 50000] [--out dist]
                           [--url https://evmax.ai] [--no-llm]
Run from the repo root.

The World Cup tree under /round/N/ is never written by this module. Those pages
are frozen published claims that /track-record/ grades against reality, and the
FPL build has no business touching them (spec D5).
"""
from __future__ import annotations

import os

from core import fpl_api, simcache

# A gameweek with no availability flags at all. FPL's bootstrap always carries
# some — injuries, suspensions, doubts — so an all-clear feed means a stale cache,
# not a miraculously healthy league.
_STALE_IF_NO_FLAGS = True


def preflight(gameweek: int, players: list, cold_start: list) -> list:
    """Abort on anything that makes a build impossible; return warnings for the rest.

    Returns the warning strings rather than printing them, so the caller controls
    where they land and the tests can assert on them. The caller prints them, and
    repeats a one-line summary on the FINAL line of output — the World Cup site
    shipped an expired injury note because the operator's `| tail -1` hid a
    correctly-firing guard (07-08).
    """
    from core import fixtures

    problems = []
    if fpl_api.read_cache("bootstrap") is None:
        problems.append(
            "data/fpl/bootstrap.json is missing — populate the cache with\n"
            f"    python3 manage.py fpl --round {gameweek} --refresh\n"
            "  (data/ is gitignored: a fresh checkout has no cached FPL feed)")
    fx = fixtures.by_round(gameweek)
    if not fx:
        problems.append(
            f"no fixtures registered for gameweek {gameweek} — the FPL fixtures "
            f"feed is missing or stale; refresh it with\n"
            f"    python3 manage.py fpl --round {gameweek} --refresh")
    if problems:
        raise SystemExit("evmax fpl build preflight failed:\n- " +
                         "\n- ".join(problems))

    warnings = []

    unpriced = [f for f in fx if f.lam_home is None or f.lam_away is None]
    if unpriced:
        names = ", ".join(f"{f.home} vs {f.away}" for f in unpriced)
        warnings.append(
            f"UNPRICED FIXTURE(S) — team-ratings fallback in effect: {names}. "
            f"Those clubs' rows are model-derived, not market-derived; the ticker "
            f"labels them, but check the odds feed before publishing.")

    if cold_start:
        names = ", ".join(f.get("name", "?") for f in cold_start[:6])
        more = " ..." if len(cold_start) > 6 else ""
        warnings.append(
            f"{len(cold_start)} PLAYER(S) ON THE PRICE-BASED COLD-START PRIOR (no "
            f"Premier League history): {names}{more}. Their projections lean on "
            f"price alone — verify before featuring one.")

    if _STALE_IF_NO_FLAGS and players:
        flagged = sum(1 for p in players if p.get("status", "a") != "a")
        if flagged == 0:
            warnings.append(
                f"STALE AVAILABILITY DATA — 0 of {len(players)} players carry a "
                f"non-available status. A real gameweek always has injuries and "
                f"suspensions, so the bootstrap cache is almost certainly old. "
                f"Refresh before publishing or the site will present ruled-out "
                f"players as nailed starters.")

    return warnings


def cache_warnings(gameweek: int, cache_hit: bool) -> list:
    """Spec §9's "the sim cache missed unexpectedly".

    A miss on the FIRST build of a gameweek is expected and silent. A miss when
    artifacts for this gameweek already exist means an input changed — priors,
    odds, research, config, or the model source fingerprint. That is usually
    intended, but it is worth saying out loud: it explains why a build that should
    have been instant just ran 50,000 simulations, and it is the one signal that
    would catch an accidental edit to a scoring constant.
    """
    if cache_hit:
        return []
    stale = simcache.artifacts_for(gameweek)
    if not stale:
        return []
    return [f"SIM CACHE MISS with {len(stale)} stale artifact(s) for gameweek "
            f"{gameweek} ({', '.join(k[:8] for k in stale[:4])}) — an input or a "
            f"model source changed since the last build. Expected after a code or "
            f"data change; investigate if you changed neither."]
```

- [x] **Step 4: Run the tests**

```bash
python3 -m unittest tests.test_fpl_site.TestFplPreflight -v
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add evmax/fpl_build.py tests/test_fpl_site.py && git commit -m "feat(fpl): build preflight — unpriced fixtures, cold starts, stale availability, cache misses"
```

---

## Task 12: The gameweek build pipeline and the `--gw` CLI

Assemble it: load the gameweek, build the artifact, rank the six articles, render pages, JSON, markdown twins and agent files under `/fpl/gw{N}/`, and write the root landing.

**Files:**
- Modify: `evmax/fpl_build.py`, `evmax/build.py`
- Test: `tests/test_fpl_site.py`

- [x] **Step 1: Write the failing test**

Append to `tests/test_fpl_site.py`:

```python
class TestGameweekBuild(unittest.TestCase):
    """End-to-end into a temp dir. Uses the real cached bootstrap/fixtures but a
    tiny sim count — this asserts the pipeline's SHAPE, not its numbers."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = cls.tmp.name
        fpl_build.build(gameweek=1, sims=200, out=cls.out,
                        url="https://example.test", use_llm=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _read(self, path):
        with open(os.path.join(self.out, path.lstrip("/")), encoding="utf-8") as fh:
            return fh.read()

    def test_all_six_articles_render(self):
        for slug in fpl_build.ARTICLES:
            with self.subTest(slug=slug):
                html = self._read(f"/fpl/gw1/{slug}/index.html")
                self.assertIn("<!doctype html>", html)
                self.assertIn("Gameweek 1", html)

    def test_json_and_markdown_twins_exist(self):
        for slug in fpl_build.ARTICLES:
            with self.subTest(slug=slug):
                env = json.loads(self._read(f"/api/fpl/gw1/{slug}.json"))
                self.assertEqual(env["gameweek"], 1)
                self.assertEqual(env["competition"], "fantasy_premier_league")
                self.assertTrue(self._read(f"/fpl/gw1/{slug}.md"))

    def test_landing_is_written_to_both_the_section_and_the_root(self):
        section = self._read("/fpl/gw1/index.html")
        root = self._read("/index.html")
        self.assertEqual(section, root)
        self.assertIn("Fantasy Premier League", root)

    def test_world_cup_pages_are_never_written(self):
        self.assertFalse(os.path.exists(os.path.join(self.out, "round")))

    def test_players_feed_carries_no_price_or_ownership(self):
        """Same guardrail as the World Cup bulk feed: derived model outputs plus
        name/team/position only. Price and ownership stay per-article context."""
        feed = json.loads(self._read("/api/fpl/gw1/players.json"))
        self.assertTrue(feed["players"])
        for p in feed["players"][:20]:
            self.assertNotIn("price", p)
            self.assertNotIn("ownership_pct", p)

    def test_projection_snapshot_is_not_written_for_a_non_production_build(self):
        """Snapshots are the track record's ground truth — a test build into a temp
        dir must never touch them."""
        snap = os.path.join(os.path.dirname(os.path.abspath(fpl_build.__file__)),
                            "assets", "projections", "fpl-gw1")
        self.assertFalse(os.path.isdir(snap))

    def test_sitemap_keeps_the_world_cup_tree(self):
        xml = self._read("/sitemap.xml")
        self.assertIn("/fpl/gw1/", xml)


class TestCliRouting(unittest.TestCase):
    def test_gw_routes_to_the_fpl_build(self):
        from evmax import build as build_mod
        with mock.patch.object(build_mod, "fpl_build") as fake:
            with mock.patch("sys.argv", ["build", "--gw", "3", "--no-llm"]):
                build_mod.main()
        fake.build.assert_called_once()
        self.assertEqual(fake.build.call_args.kwargs["gameweek"], 3)

    def test_round_still_routes_to_the_world_cup_build(self):
        from evmax import build as build_mod
        with mock.patch.object(build_mod, "build") as fake:
            with mock.patch("sys.argv", ["build", "--round", "5", "--no-llm"]):
                build_mod.main()
        fake.assert_called_once()

    def test_exactly_one_of_round_or_gw_is_required(self):
        from evmax import build as build_mod
        with mock.patch("sys.argv", ["build", "--no-llm"]):
            with self.assertRaises(SystemExit):
                build_mod.main()
```

Add `import json` to the test file's imports.

- [x] **Step 2: Run it, verify it fails**

```bash
python3 -m unittest tests.test_fpl_site.TestGameweekBuild -v
```

Expected: FAIL — `module 'evmax.fpl_build' has no attribute 'build'`.

- [x] **Step 3: Implement**

Append to `evmax/fpl_build.py`:

```python
import json
import shutil
from datetime import datetime, timezone

from core import fixtures, fpl_api, research, simcache
from evmax import fpl_articles, render, writer
from games.fpl import model as fpl_model

ARTICLES = ["captains", "wildcard", "ticker", "defenders", "efficiency", "defcon"]

ARTICLE_TITLES = {
    # Short: the <title> becomes "{title} — Gameweek N | evmax" and Bing errors
    # above ~65 characters.
    "captains": "Best captain picks",
    "wildcard": "Draft squad & wildcard XI",
    "ticker": "Fixture ticker — clean sheets",
    "defenders": "Best defenders & keepers",
    "efficiency": "Best value — points per million",
    "defcon": "DefCon leaders",
}

_COLUMNS = {
    "captains":   ["captain_ev", "x_points", "ceiling", "price", "ownership_pct"],
    "wildcard":   ["x_points", "price", "captain_ev", "ceiling", "ownership_pct"],
    "ticker":     ["exp_clean_sheets", "exp_goals_for", "exp_goals_against",
                   "fixtures", "basis"],
    "defenders":  ["x_points", "cs_points", "defcon", "bonus", "price"],
    "efficiency": ["value", "x_points", "price", "ownership_pct", "ceiling"],
    "defcon":     ["p_defcon", "defcon", "x_points", "price", "ownership_pct"],
}

# Articles whose chart metric is points-denominated get the floor+ceiling reach
# bar. value (pts/million), p_defcon (a probability) and exp_clean_sheets (a
# count) are different units — mixing raw ceiling points into those bars would be
# dimensionally wrong. captains charts captain_ev, so its ceiling companion needs
# the same doubling to land on the same scale.
_CEILING_PAIRED_METRIC = {
    "captains":  ("captain_ev", 2.0),
    "defenders": ("x_points", 1.0),
}

_ARTICLE_VIZ_MAX_ROWS = 10
_FEATURED_VIZ_MAX_ROWS = 8


def _article_entries(rows: list, matches: list, clubs: list) -> tuple:
    """{slug: entries} plus the wildcard squad's meta, which is not a flat list."""
    squad_entries, squad_meta = fpl_articles.fpl_squad(rows)
    return {
        "captains":   fpl_articles.captains(rows)[:20],
        "wildcard":   squad_entries,
        "ticker":     fpl_articles.ticker(matches, clubs),
        "defenders":  fpl_articles.defenders(rows)[:20],
        "efficiency": fpl_articles.efficiency(rows)[:20],
        "defcon":     fpl_articles.defcon_leaders(rows)[:20],
    }, squad_meta


def build(gameweek: int, sims: int = 50_000, out: str = "dist",
          url: str = "https://evmax.ai", use_llm: bool = True,
          use_cache: bool = True) -> None:
    render.SITE_URL = url
    section = render.FPL
    generated_at = datetime.now(timezone.utc).isoformat()
    date_str = _format_date(generated_at)

    priors_by_team, players_by_name, cold_start = fpl_model.load_gameweek(gameweek)
    boot = fpl_api.read_cache("bootstrap")
    all_players = fpl_api.parse_players(boot) if boot else []

    warnings = preflight(gameweek, all_players, cold_start)

    artifact, cache_hit = fpl_model.build_artifact(
        priors_by_team, players_by_name, gameweek, sims, use_cache=use_cache)
    warnings += cache_warnings(gameweek, cache_hit)
    rows, matches = artifact["rows"], artifact["matches"]
    if not rows:
        raise SystemExit(
            f"evmax fpl build: the simulation produced no players for gameweek "
            f"{gameweek} — the priors are empty, which usually means the bootstrap "
            f"cache is stale. Refresh with `python3 manage.py fpl --round "
            f"{gameweek} --refresh`.")

    clubs = sorted({p["team"] for p in all_players}) or sorted(priors_by_team)
    entries_map, squad_meta = _article_entries(rows, matches, clubs)

    # /fpl/gw{N}/ pages accumulate the same way the WC's /round/{N}/ ones do:
    # build() never clears `out`, so past gameweeks persist and the switcher is
    # generated from what is actually on disk.
    gw_root = os.path.join(out, "fpl")
    available = sorted(
        {int(d[2:]) for d in os.listdir(gw_root)
         if d.startswith("gw") and d[2:].isdigit()} | {gameweek}
    ) if os.path.isdir(gw_root) else [gameweek]

    def w(path: str, text: str) -> None:
        full = os.path.join(out, path.lstrip("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)

    # --- Bulk players feed. Same guardrail as the World Cup's: derived model
    # outputs and name/team/position ONLY. No price, no ownership — those stay
    # per-player context inside articles, never in the public bulk feed.
    notes = research.load_entries("players", gameweek)
    w(section.players_json_path(gameweek), json.dumps({
        "gameweek": gameweek,
        "generated_at": generated_at,
        "methodology": render.METHODOLOGY,
        "license": render.DATA_LICENSE_URL,
        "players": [
            {"name": r["name"], "team": r.get("team"),
             "position": r.get("position"), "x_points": r["x_points"],
             "captain_ev": r["captain_ev"], "ceiling": r["ceiling"],
             "kickoff": r.get("kickoff"),
             "flag": _player_flag(r["name"], notes)}
            for r in rows
        ],
    }, ensure_ascii=False, indent=2))

    prose_map: dict = {}
    used_leads: set = set()
    is_production = os.path.basename(os.path.normpath(out)) == "dist"

    for slug in ARTICLES:
        entries = entries_map[slug]
        columns = _COLUMNS[slug]
        title = f"{ARTICLE_TITLES[slug]} — Gameweek {gameweek}"
        json_url = section.json_path(gameweek, slug)

        if slug in ("wildcard", "ticker"):
            subject = None            # squad- and club-framed, no lead player
        else:
            subject = next((e["name"] for e in entries
                            if e["name"] not in used_leads),
                           entries[0]["name"] if entries else None)
            if subject:
                used_leads.add(subject)

        prose = writer.article_prose(slug, gameweek, entries, columns,
                                     cache_dir="data/articles", use_llm=use_llm,
                                     subject=subject,
                                     cache_name=f"fpl-gw{gameweek}",
                                     unit="Gameweek")
        prose_map[slug] = prose

        if slug == "wildcard":
            viz_html = render.pitch_svg([e for e in entries
                                         if e.get("role") == "XI"])
        else:
            pair = _CEILING_PAIRED_METRIC.get(slug)
            if pair:
                metric, scale = pair
                viz_html = render.ev_bar(entries, metric,
                                         max_rows=_ARTICLE_VIZ_MAX_ROWS,
                                         reach_metric="ceiling", reach_scale=scale)
            else:
                viz_html = render.ev_bar(entries, columns[0],
                                         max_rows=_ARTICLE_VIZ_MAX_ROWS)

        extra = {"squad": squad_meta} if slug == "wildcard" else None
        env = render.article_json("fantasy_premier_league", gameweek, slug, title,
                                  generated_at, sims, entries,
                                  extra_fields=extra, section=section)
        env_json = json.dumps(env, ensure_ascii=False, indent=2)
        w(json_url, env_json)

        # Point-in-time projection archive — the ground truth the backtest harness
        # will grade from GW1 forward (spec §7.4). Two guards, same as the World
        # Cup's: production builds only, and only while the gameweek is still open,
        # so a post-hoc rebuild cannot contaminate a published claim.
        lock = fixtures.round_lock_time(gameweek)
        if is_production and (lock is None or datetime.now(timezone.utc) < lock):
            snap_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "assets", "projections", f"fpl-gw{gameweek}")
            os.makedirs(snap_dir, exist_ok=True)
            with open(os.path.join(snap_dir, f"{slug}.json"), "w",
                      encoding="utf-8") as fh:
                fh.write(env_json)

        w(f"{section.base.format(r=gameweek)}/{slug}/index.html",
          render.article_page(gameweek, slug, title, prose, entries, columns,
                              json_url, viz_html, generated_at=generated_at,
                              date_str=date_str, available_rounds=available,
                              section=section))
        w(section.md_path(gameweek, slug),
          render.article_md(gameweek, slug, title, prose, entries, columns,
                            generated_at, date_str,
                            canonical_path=section.article_path(gameweek, slug),
                            section=section))

    # --- Static pages and assets (shared with the World Cup section) ----------
    w("/about/index.html", render.about_page())
    w("/privacy/index.html", render.privacy_page())
    w("/thanks/index.html", render.thanks_page())
    w("/confirmed/index.html", render.confirmed_page())
    _copy_assets(out)

    # --- Landing -------------------------------------------------------------
    featured = {
        "slug": "captains",
        "prose": prose_map["captains"],
        "viz_html": render.ev_bar(
            entries_map["captains"][:_FEATURED_VIZ_MAX_ROWS], "captain_ev",
            width=400, row_h=40, label_size=15, value_size=14, bar_h=22,
            reach_metric="ceiling", reach_scale=2.0),
    }
    feed = []
    for slug in ARTICLES:
        if slug == "captains":
            continue
        entries, columns = entries_map[slug], _COLUMNS[slug]
        top = entries[0] if entries else {}
        feed.append({
            "slug": slug,
            "headline": prose_map[slug]["headline"],
            "teaser": prose_map[slug]["standfirst"],
            "stat_value": render._fmt(columns[0], top),
            "stat_label": render._COL_LABEL.get(columns[0], columns[0]),
        })

    landing = render.landing_page(gameweek, featured, feed, date_str=date_str,
                                  fixtures=matches, available_rounds=available,
                                  section=section)
    w(f"{section.base.format(r=gameweek)}/index.html", landing)
    # Owner decision 2026-07-30: FPL takes the root. The World Cup tree under
    # /round/N/ is untouched and stays live (spec D5) — its landing survives at
    # /round/8/ — but GW1 is the year's largest FPL search peak and the root
    # belongs to the live competition.
    w("/index.html", landing)

    # --- Agent / meta files --------------------------------------------------
    nav = [(slug, ARTICLE_TITLES[slug]) for slug in ARTICLES]
    w("/api/latest.json", json.dumps(
        {"gameweek": gameweek, "generated_at": generated_at,
         "articles": {s: section.json_path(gameweek, s) for s in ARTICLES}},
        ensure_ascii=False, indent=2))
    w("/llms.txt", render.llms_txt(gameweek, nav, section=section))
    w("/robots.txt", render.robots_txt())
    w("/sitemap.xml", render.sitemap_xml(gameweek, nav, lastmod=generated_at[:10],
                                         section=section,
                                         extra_urls=_world_cup_urls(out)))

    for line in warnings:
        print(f"\n!!! {line}\n")
    suffix = (f" | !!! {len(warnings)} WARNING(S) — see above / rerun without "
              f"filters" if warnings else "")
    print(f"Built FPL gameweek {gameweek} → {out}/ "
          f"({len(rows)} players, {len(ARTICLES)} articles, "
          f"sim cache {'HIT' if cache_hit else 'MISS'}){suffix}")


def _world_cup_urls(out: str) -> list:
    """Every World Cup page already on disk, so the FPL sitemap keeps them listed.

    Those URLs are still live and still indexed (spec D5). A sitemap that drops
    them reads to a crawler as a request to deindex them, which would take the
    track record's own evidence out of search.
    """
    root = os.path.join(out, "round")
    if not os.path.isdir(root):
        return []
    urls = []
    for dirpath, _dirs, filenames in os.walk(root):
        if "index.html" in filenames:
            rel = os.path.relpath(dirpath, out).replace(os.sep, "/")
            urls.append(f"/{rel}/")
    return sorted(urls)


def _player_flag(name: str, notes: dict):
    """out / doubtful / None — the same small public vocabulary the World Cup feed
    exposes. Imported rather than reimplemented so the two never drift."""
    from evmax.articles import player_flag
    return player_flag(name, notes)


def _format_date(generated_at: str) -> str:
    dt = datetime.fromisoformat(generated_at)
    try:
        return dt.strftime("%-d %B %Y")
    except ValueError:
        return dt.strftime("%d %B %Y").lstrip("0")


def _copy_assets(out: str) -> None:
    """Brand images, self-hosted fonts and the first-party JS. No third-party
    requests on load — the site's GDPR posture depends on it."""
    here = os.path.dirname(os.path.abspath(__file__))
    for src_name, dst_name, exts in (("brand", "brand", (".png", ".svg")),
                                     ("fonts", "fonts", (".woff2",)),
                                     ("js", "js", (".js",))):
        src = os.path.join(here, "assets", src_name)
        dst = os.path.join(out, dst_name)
        if not os.path.isdir(src):
            continue
        os.makedirs(dst, exist_ok=True)
        for fname in os.listdir(src):
            if fname.endswith(exts):
                shutil.copy2(os.path.join(src, fname), os.path.join(dst, fname))
```

Move the module's `import os` to sit with the rest of these imports rather than leaving two import blocks.

Then wire the CLI. In `evmax/build.py`, add `from evmax import fpl_build` to the imports and replace `main()`:

```python
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Build the evmax static site for one round or gameweek.")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--round", type=int,
                       help="World Cup fantasy round number")
    group.add_argument("--gw", type=int,
                       help="Fantasy Premier League gameweek number")
    ap.add_argument("--sims", type=int, default=50_000,
                    help="Monte-Carlo simulation count (default 50 000)")
    ap.add_argument("--out", default="dist",
                    help="Output directory (default dist/)")
    ap.add_argument("--url", default="https://evmax.ai",
                    help="Canonical site URL (default https://evmax.ai)")
    ap.add_argument("--no-llm", dest="no_llm", action="store_true",
                    help="Skip the LLM tier; use cache-or-template only")
    ap.add_argument("--no-cache", dest="no_cache", action="store_true",
                    help="FPL only: always simulate, ignoring the sim cache")
    a = ap.parse_args()
    if a.gw is not None:
        fpl_build.build(gameweek=a.gw, sims=a.sims, out=a.out, url=a.url,
                        use_llm=not a.no_llm, use_cache=not a.no_cache)
    else:
        build(a.round, a.sims, a.out, a.url, use_llm=not a.no_llm)
```

- [x] **Step 4: Run the tests**

```bash
python3 -m unittest tests.test_fpl_site -v
```

Expected: PASS. Then the whole suite:

```bash
python3 -m unittest discover -s tests -t .
```

Expected: all green.

- [x] **Step 5: Commit**

```bash
git add evmax/fpl_build.py evmax/build.py tests/test_fpl_site.py && git commit -m "feat(fpl): gameweek build pipeline and the --gw CLI"
```

---

## Task 13: Real GW1 build, verification and changelog

The phase's "done when" is a full GW1 build into `dist/`. Run it for real, look at the output, and record what shipped.

**Files:**
- Modify: `CHANGELOG.md`, `README.md`

- [x] **Step 1: Build gameweek 1 into a scratch directory first**

```bash
python3 -m evmax.build --gw 1 --sims 8000 --out /tmp/evmax-gw1 --url https://evmax.ai --no-llm
```

Expected: six articles, a warning line if any fixture is unpriced or any player is on the cold-start prior, and a final summary line. A non-`dist` output directory means no projection snapshot is written — confirm none appeared:

```bash
ls evmax/assets/projections/ | grep fpl || echo "no fpl snapshot (correct for a scratch build)"
```

- [x] **Step 2: Check the output by hand**

```bash
python3 -c "
import json
for slug in ('captains','wildcard','ticker','defenders','efficiency','defcon'):
    env = json.load(open(f'/tmp/evmax-gw1/api/fpl/gw1/{slug}.json'))
    top = env['entries'][0]
    print(f\"{slug:11} {len(env['entries']):3} entries | top: {top.get('name')}\")
"
```

Then read three pages in a browser or with `python3 -m http.server` from `/tmp/evmax-gw1`. You are checking for things tests cannot: does the DefCon article's chart axis make sense as a probability, does the ticker read correctly with 20 clubs and no blanks, does the wildcard pitch draw eleven players.

Sanity-check the squad against the rules by hand:

```bash
python3 -c "
import json
env = json.load(open('/tmp/evmax-gw1/api/fpl/gw1/wildcard.json'))
e = env['entries']
clubs = {}
for p in e: clubs[p['team']] = clubs.get(p['team'], 0) + 1
print('squad size:', len(e), '| cost:', env['squad']['total_cost'],
      '| formation:', env['squad']['formation'])
print('max per club:', max(clubs.values()), '(must be <= 3)')
print('XI xPts:', env['squad']['xi_xpoints'])
"
```

- [x] **Step 3: Build into `dist/` for real**

```bash
python3 -m evmax.build --gw 1 --sims 50000 --out dist --url https://evmax.ai
```

Confirm the World Cup tree survived untouched:

```bash
git status --short dist/ | head; ls dist/round/ && ls dist/fpl/
```

`dist/` is a build output — check whether it is gitignored before assuming anything about `git status` here. The substantive check is that `dist/round/` still contains every round it did before, and that `dist/index.html` now says "Fantasy Premier League".

```bash
grep -c "Fantasy Premier League" dist/index.html
grep -c "World Cup" dist/round/8/index.html
```

Expected: both non-zero.

- [x] **Step 4: Run the full suite one more time**

```bash
python3 -m unittest discover -s tests -t .
```

Expected: all green. Record the final test count — it goes in the changelog header.

- [x] **Step 5: Write the changelog and update the README**

Add a dated entry at the top of `CHANGELOG.md` covering: the six articles and their URL namespace; the `Section` descriptor and why the templating refactor is still deferred; the three-per-club squad cap; the ticker's blank/double aggregation and provenance labelling; the answer to the carried double-gameweek bonus question; and the root takeover with the WC tree's survival. Update the test count in the file's header line.

In `README.md`, add the FPL build command next to the existing World Cup one, and note that `/` now serves the current gameweek.

- [x] **Step 6: Commit**

```bash
git add CHANGELOG.md README.md && git commit -m "docs: changelog and README for FPL port phase 4 (the site)"
```

---

## Self-Review

**Spec coverage.** §8's six articles → T6 (captains, defenders, efficiency, defcon), T7 (wildcard), T8 (ticker). §8's `/fpl/gw{N}/` namespace and CLI → T4, T5, T12. §8's ticker confidence labelling → T8. §9's four preflight warnings → T11 (unpriced fixtures, cold-start players, stale availability, unexpected cache miss). §6's "per-match scoreline distribution" in the artifact — unimplemented in Phase 3 — → T3. §7.4's projection archive for the future backtest → T12. §5.1's blanks and doubles → T8, with synthetic tests because live data will not exhibit them for months. §11's "done when: full GW1 build into `dist/`" → T13. The carried Phase 3 double-gameweek question → T1.

**Out of scope and deliberately absent:** the templating refactor (§12, September), transfers/chips/`ep_next` articles (§12), the backtest harness itself (§7.4 — no realized data until GW1 completes), and `/rate/` for FPL (the World Cup tool stays as-is; the FPL players feed is written but no rater page consumes it yet).

**Two places the plan tells you to correct a draft rather than showing only the final code** — T4's `{abbr}ounds` switcher label and T7's global-mutating `_squad_for_formation`. Both are written that way on purpose: they are the obvious first implementation and both are wrong, so the plan shows the trap and the fix rather than leaving an implementer to find it in review.

**Type consistency.** `Section` methods (`landing_path`, `article_path`, `md_path`, `json_path`, `players_json_path`, `kicker`, `switcher_base`) are used with those exact names in T4, T5 and T12. `build_artifact` returns `(artifact, cache_hit)` in T3 and is unpacked that way in T12. `fpl_squad` returns `(entries, meta)` with `meta` carrying `total_cost`/`xi_xpoints`/`formation`/`budget`/`left_over` — produced in T7, consumed in T10's wildcard template and T12's `extra_fields`. `ticker` rows carry `exp_clean_sheets`/`exp_goals_for`/`exp_goals_against`/`fixtures`/`basis`/`env`/`opponents` — produced in T8, listed in T12's `_COLUMNS["ticker"]`, referenced in T10's ticker template and T9's glossary. `defcon_leaders` rows carry `p_defcon` and `defcon_threshold` — produced in T6, consumed in T10 and T9.

**One column-label gap to watch:** `render._COL_LABEL` has no entries for `p_defcon`, `cs_points`, `exp_clean_sheets`, `exp_goals_for`, `exp_goals_against`, `fixtures`, `basis` or `value` under FPL naming, so `_fmt` and the table headers will fall back to the raw key. Add them to `_COL_LABEL` in T5 alongside the other render changes — reader-facing labels like "Clean sheets", "P(DefCon)", "CS pts", "xGF", "xGA", "Fixtures", "Basis". The T12 landing test exercises `render._fmt(columns[0], top)` on `exp_clean_sheets` and `p_defcon`, so a missing label shows up as an ugly stat label rather than a failure — check it by eye in T13 Step 2.
