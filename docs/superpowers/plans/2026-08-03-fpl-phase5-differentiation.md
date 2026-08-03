# FPL Phase 5 — Differentiation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the model able to tell one club's fixture from another's, and one cheap defender from another — by using four signals the codebase already has access to and currently throws away.

**Architecture:** Three of the four are pure data-retention fixes in existing parsers (`fpl_api.parse_fixtures`, `fpl_api.parse_teams`, the `element-summary` fetch), feeding a new `core/fpl_ratings.py` that finally populates Premier League team ratings. The fourth is a consumption path for the owner's own lineup notes, built on the `core/research.py` overlay that already exists and is already wired into the sim.

**Tech Stack:** Python 3.9 stdlib only. `unittest`. No new dependencies, no new external sources.

**Prior phase:** `docs/superpowers/plans/2026-07-30-fpl-port-phase4.md` (the site). Baseline: 684 tests passing on branch `fpl-phase4`.

---

## Why this phase exists

Phase 4 shipped a working site and, in the process, exposed that the model cannot
differentiate. `ratings.match_lambdas` returns `(1.445, 1.35)` for **every** Premier
League pairing, because `TEAM_RATINGS` has no Premier League clubs and `get_team`
falls back to a neutral default. With no GW1 odds posted yet, the published fixture
ticker shows all 20 clubs at a 26% clean sheet. It is ranking on rounding noise.

The concrete case that motivated this, from the owner (2026-08-03): a £5.0m Liverpool
defender being discussed as an obvious pick. In the current model he is
indistinguishable from a £5.0m Hull defender. Checking the feed:

```
Jacquet   LIV DEF  £5.0m   2.4% owned   0 minutes   0 starts   0 past seasons
```

He is one of the 163 players on the price-based cold-start prior. Testing each signal
against him is what scoped this phase, because it separates what each one can and
cannot do:

| Signal | Helps Jacquet? |
|---|---|
| Team strength / fixture difficulty | **Yes** — makes a Liverpool clean sheet worth more than a Hull one |
| Last-season history | **No** — he has zero past seasons; nothing to retrieve |
| Predicted lineups | **Decisive** — whether he is nailed is the entire question |

So last-season history is worth having, but it serves a different cohort (Kerkez,
Virgil — established players whose rates we already fetch and then discard). It would
never have surfaced the player in question. Both are in scope; do not conflate them.

## Owner decisions (2026-08-03)

1. **All four workstreams in scope.**
2. **The owner writes the lineup notes; this codebase consumes them.** No web-search
   pass, no scraping, no automated team-news ingestion. The work here is to make the
   notes cheap to write, safe to consume, and loud when they are missing, stale, or
   name-mismatched. Do not build a scraper.

## What is available, verified against the cached feed

| Signal | Where it lives | Current state |
|---|---|---|
| Fixture difficulty (FDR) | `fixtures.json` → `team_h_difficulty` / `team_a_difficulty`, integers 1–5 | Cached; `parse_fixtures` drops it |
| Team strength | `bootstrap` → `strength_overall_home` / `strength_overall_away`, integers 2–5 | Cached; `parse_teams` drops it |
| Last-season history | `element-summary` → `history_past[]` | We fetch this for ~400 players and keep only `defcon_per90` + `minutes` |
| Lineups | Not in the FPL API | `core/research.py` overlay exists, is wired into the sim, and is unused for FPL |

**`strength_attack_*` and `strength_defence_*` are all zero preseason** — verified on
all 20 clubs. Only `strength_overall_home/away` carries signal, so the attack/defence
decomposition has to be derived rather than read. They may populate in-season; the
implementation should prefer them when non-zero (Task 2 covers this).

GW1 FDR, for reference — it discriminates sharply where our lambdas do not:

```
ARS (H) diff 2  v  COV (A) diff 5
MCI (H) diff 3  v  BOU (A) diff 5
HUL (H) diff 4  v  MUN (A) diff 2
```

---

## File structure

| File | Responsibility |
|---|---|
| `core/fpl_api.py` (modify) | Retain FDR, team strength and full `history_past`. Parsers only; no derivation. |
| `core/fpl_ratings.py` (create) | Turn club strength into `TeamRating`s and register them. The single place FPL data becomes a lambda input. |
| `core/fpl_priors.py` (modify) | Consume `history_past` to sharpen per-90 rates and clean-sheet share. |
| `games/fpl/model.py` (modify) | Register ratings during `load_gameweek`; carry FDR onto match summaries. |
| `evmax/fpl_articles.py` (modify) | Surface FDR in the ticker. |
| `evmax/fpl_build.py` (modify) | Preflight: unmatched, stale and missing lineup notes. |
| `scripts/fpl_notes.py` (create) | Turn the owner's shorthand into `research/players/*.md` frontmatter. |
| `tests/test_fpl_ratings.py` (create) | Rating derivation and calibration. |
| `tests/test_fpl_notes.py` (create) | Shorthand parsing and name matching. |

---

## Task 1: Retain what the parsers are discarding

Pure data retention. No behaviour changes anywhere yet — this task only makes the
signals reachable, so it is safe to land on its own and everything after it depends
on it.

**Files:** Modify `core/fpl_api.py`; Test `tests/test_fpl_api.py`

- [ ] **Step 1: Write the failing tests**

```python
class TestFixtureDifficultyRetained(unittest.TestCase):
    def test_parse_fixtures_keeps_both_difficulties(self):
        raw = [{"event": 1, "team_h": 1, "team_a": 2, "id": 9,
                "kickoff_time": "2026-08-21T19:00:00Z",
                "team_h_difficulty": 2, "team_a_difficulty": 5}]
        row = fpl_api.parse_fixtures(raw, {1: "ARS", 2: "COV"})[0]
        self.assertEqual(row["home_difficulty"], 2)
        self.assertEqual(row["away_difficulty"], 5)

    def test_missing_difficulty_is_none_not_zero(self):
        """Zero would read as 'easiest possible fixture'; absent must stay absent."""
        raw = [{"event": 1, "team_h": 1, "team_a": 2, "id": 9,
                "kickoff_time": "2026-08-21T19:00:00Z"}]
        row = fpl_api.parse_fixtures(raw, {1: "ARS", 2: "COV"})[0]
        self.assertIsNone(row["home_difficulty"])


class TestTeamStrengthRetained(unittest.TestCase):
    def test_parse_team_strength(self):
        raw = {"teams": [{"id": 1, "short_name": "ARS", "name": "Arsenal",
                          "strength_overall_home": 4, "strength_overall_away": 5,
                          "strength_attack_home": 0, "strength_attack_away": 0,
                          "strength_defence_home": 0, "strength_defence_away": 0}]}
        out = fpl_api.parse_team_strength(raw)
        self.assertEqual(out["ARS"]["overall_home"], 4)
        self.assertEqual(out["ARS"]["overall_away"], 5)

    def test_zero_attack_defence_reads_as_unavailable(self):
        """Preseason these are 0 for every club — that is 'no data', not 'weakest'."""
        raw = {"teams": [{"id": 1, "short_name": "ARS", "name": "Arsenal",
                          "strength_overall_home": 4, "strength_overall_away": 5,
                          "strength_attack_home": 0, "strength_attack_away": 0,
                          "strength_defence_home": 0, "strength_defence_away": 0}]}
        out = fpl_api.parse_team_strength(raw)
        self.assertIsNone(out["ARS"]["attack_home"])
        self.assertIsNone(out["ARS"]["defence_home"])

    def test_nonzero_attack_defence_is_kept(self):
        raw = {"teams": [{"id": 1, "short_name": "ARS", "name": "Arsenal",
                          "strength_overall_home": 4, "strength_overall_away": 5,
                          "strength_attack_home": 1300, "strength_attack_away": 1310,
                          "strength_defence_home": 1200, "strength_defence_away": 1210}]}
        out = fpl_api.parse_team_strength(raw)
        self.assertEqual(out["ARS"]["attack_home"], 1300)


class TestHistoryPastRetained(unittest.TestCase):
    def test_parse_history_past_keeps_the_scoring_columns(self):
        es = {"history_past": [
            {"season_name": "2024/25", "minutes": 1800, "total_points": 90,
             "clean_sheets": 8, "goals_conceded": 30, "bps": 300, "starts": 20,
             "expected_goals": "3.1", "expected_assists": "2.4",
             "expected_goals_conceded": "28.5", "defensive_contribution": 140},
            {"season_name": "2025/26", "minutes": 2251, "total_points": 85,
             "clean_sheets": 6, "goals_conceded": 37, "bps": 357, "starts": 27,
             "expected_goals": "2.2", "expected_assists": "1.9",
             "expected_goals_conceded": "35.0", "defensive_contribution": 210},
        ]}
        out = fpl_api.parse_history_past(es)
        self.assertEqual(len(out), 2)
        last = out[-1]
        self.assertEqual(last["season_name"], "2025/26")
        self.assertEqual(last["minutes"], 2251)
        self.assertAlmostEqual(last["expected_goals"], 2.2)
        self.assertAlmostEqual(last["expected_goals_conceded"], 35.0)

    def test_empty_history_is_an_empty_list(self):
        """A summer signing with no Premier League record — the cold-start case."""
        self.assertEqual(fpl_api.parse_history_past({"history_past": []}), [])
        self.assertEqual(fpl_api.parse_history_past({}), [])
```

- [ ] **Step 2: Run, verify fail** — `python3 -m unittest tests.test_fpl_api -v`

- [ ] **Step 3: Implement**

Add `home_difficulty` / `away_difficulty` to `parse_fixtures`' output dict, reading
`team_h_difficulty` / `team_a_difficulty` with `.get()` so absent stays `None`.

Add `parse_team_strength(raw) -> {short_name: {...}}`. Map the zero attack/defence
fields to `None`, because zero means "not published yet" and a downstream consumer
treating it as a rating would rank every club as maximally weak.

Add `parse_history_past(element_summary) -> list[dict]`, newest last, coercing the
string-typed expected-goal fields to float via the module's existing `_f` helper.

Follow the file's existing parser conventions — these are pure functions with no
network, matching `parse_players` and `parse_teams`.

- [ ] **Step 4: Run, verify pass.**

- [ ] **Step 5: Commit**

```bash
git add core/fpl_api.py tests/test_fpl_api.py && git commit -m "feat(fpl): retain fixture difficulty, team strength and full season history"
```

---

## Task 2: Premier League team ratings

The core of the phase. `ratings.TEAM_RATINGS` is a hand-set dict keyed by team name
holding `TeamRating(attack, defence)`; `get_team` falls back to a neutral default,
which is why every PL fixture gets identical lambdas. This task derives real ratings
from club strength and registers them.

**Files:** Create `core/fpl_ratings.py`; Test `tests/test_fpl_ratings.py`

### The derivation, and why

`strength_overall_home/away` is an integer 2–5. Convert to a multiplicative
attack/defence pair around the league mean, so a league-average club scores exactly
1.0 on both and reproduces today's baseline goal level. **Total goals stay
calibrated; only the spread across clubs changes.** That is the property to preserve:
we are redistributing goals, not inventing them.

A single "overall" number cannot separate attack from defence, so a strong club gets
*both* a higher attack and a lower defence-conceded factor, symmetrically. This is a
deliberate approximation, and it is documented as such: when FPL populates the
`strength_attack_*` / `strength_defence_*` fields in-season, prefer them and drop the
symmetry assumption.

Spread is controlled by one `config.py` dial rather than hard-coded, because the raw
2–5 scale is coarse and the right amount of spread is a calibration question that only
realized results can answer.

- [ ] **Step 1: Write the failing tests**

```python
class TestStrengthToRating(unittest.TestCase):
    def test_league_average_club_is_neutral(self):
        """The calibration anchor: an average club must not move the goal level."""
        strengths = {c: {"overall_home": 3, "overall_away": 3,
                         "attack_home": None, "attack_away": None,
                         "defence_home": None, "defence_away": None}
                     for c in ("A", "B", "C")}
        r = fpl_ratings.derive(strengths)
        self.assertAlmostEqual(r["A"].attack, 1.0, places=6)
        self.assertAlmostEqual(r["A"].defence, 1.0, places=6)

    def test_stronger_club_attacks_more_and_concedes_less(self):
        strengths = {"STRONG": {"overall_home": 5, "overall_away": 5},
                     "WEAK": {"overall_home": 2, "overall_away": 2},
                     "MID": {"overall_home": 3, "overall_away": 3}}
        r = fpl_ratings.derive(_fill(strengths))
        self.assertGreater(r["STRONG"].attack, r["WEAK"].attack)
        self.assertLess(r["STRONG"].defence, r["WEAK"].defence)

    def test_spread_is_config_controlled(self):
        strengths = _fill({"S": {"overall_home": 5, "overall_away": 5},
                           "W": {"overall_home": 2, "overall_away": 2}})
        tight = fpl_ratings.derive(strengths, spread=0.05)
        wide = fpl_ratings.derive(strengths, spread=0.40)
        self.assertLess(tight["S"].attack, wide["S"].attack)

    def test_zero_spread_reproduces_todays_uniform_behaviour(self):
        """The escape hatch: spread=0 must give back exactly what we have now, so a
        regression can be isolated to the ratings rather than the plumbing."""
        strengths = _fill({"S": {"overall_home": 5, "overall_away": 5},
                           "W": {"overall_home": 2, "overall_away": 2}})
        r = fpl_ratings.derive(strengths, spread=0.0)
        self.assertAlmostEqual(r["S"].attack, r["W"].attack, places=6)

    def test_prefers_published_attack_defence_when_available(self):
        """In-season FPL populates these; once it does, the symmetry assumption in
        the overall-only path is strictly worse and must not be used."""
        strengths = {
            "A": {"overall_home": 3, "overall_away": 3, "attack_home": 1400,
                  "attack_away": 1400, "defence_home": 1000, "defence_away": 1000},
            "B": {"overall_home": 3, "overall_away": 3, "attack_home": 1000,
                  "attack_away": 1000, "defence_home": 1400, "defence_away": 1400},
        }
        r = fpl_ratings.derive(strengths)
        self.assertGreater(r["A"].attack, r["B"].attack)
        self.assertLess(r["A"].defence, r["B"].defence)


class TestRegistration(unittest.TestCase):
    def test_registering_changes_match_lambdas(self):
        """The whole point: two different fixtures must stop returning the same
        numbers. Restores TEAM_RATINGS afterwards."""
        from core import ratings
        saved = dict(ratings.TEAM_RATINGS)
        try:
            fpl_ratings.register(_fill({
                "LIV": {"overall_home": 5, "overall_away": 5},
                "COV": {"overall_home": 2, "overall_away": 2},
                "MID": {"overall_home": 3, "overall_away": 3}}))
            strong = ratings.match_lambdas("LIV", "COV", neutral=False)
            weak = ratings.match_lambdas("COV", "LIV", neutral=False)
            self.assertNotAlmostEqual(strong[0], weak[0], places=3)
            self.assertGreater(strong[0], weak[0])   # LIV at home outscores COV at home
            self.assertLess(strong[1], weak[1])      # and concedes less
        finally:
            ratings.TEAM_RATINGS.clear()
            ratings.TEAM_RATINGS.update(saved)

    def test_registration_does_not_disturb_world_cup_ratings(self):
        """TEAM_RATINGS is shared with the World Cup, whose track record grades off
        unchanged numbers. Registering FPL clubs must only ADD keys."""
        from core import ratings
        saved = dict(ratings.TEAM_RATINGS)
        try:
            before = {k: (v.attack, v.defence) for k, v in ratings.TEAM_RATINGS.items()}
            fpl_ratings.register(_fill({"LIV": {"overall_home": 5, "overall_away": 5}}))
            after = {k: (v.attack, v.defence) for k, v in ratings.TEAM_RATINGS.items()
                     if k in before}
            self.assertEqual(before, after)
        finally:
            ratings.TEAM_RATINGS.clear()
            ratings.TEAM_RATINGS.update(saved)
```

Write the `_fill` helper that pads a partial strength dict with `None` attack/defence
keys, so the tests above stay readable.

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement `core/fpl_ratings.py`**

`derive(strengths, spread=None) -> {club: ratings.TeamRating}`:
- default `spread` from a new `config.FPL_RATING_SPREAD` (start at `0.25`)
- if every club has non-`None` `attack_home`, use the published attack/defence fields,
  normalised to their own league mean
- otherwise use `overall_home`/`overall_away` averaged per club, normalised to the
  league mean, with `attack = 1 + spread * z` and `defence = 1 - spread * z` where `z`
  is the club's normalised deviation
- clamp both factors to a sane floor (never ≤ 0)

`register(strengths) -> None` writes the derived ratings into `ratings.TEAM_RATINGS`,
adding keys only.

Document the symmetry approximation and the in-season upgrade path in the module
docstring.

- [ ] **Step 4: Run, verify pass.**

- [ ] **Step 5: Wire it into `load_gameweek`**

In `games/fpl/model.load_gameweek`, call `fpl_ratings.register(...)` from the parsed
bootstrap before priors are built, so any unpriced fixture's `Fixture.lambdas()`
falls back to a real rating instead of the neutral default.

- [ ] **Step 6: Verify the ticker actually differentiates**

```bash
python3 -m evmax.build --gw 1 --sims 4000 --out /tmp/evmax-p5 --url https://evmax.ai --no-llm
python3 -c "
import json
e = json.load(open('/tmp/evmax-p5/api/fpl/gw1/ticker.json'))['entries']
for r in e[:6] + e[-3:]:
    print(f\"{r['rank']:3} {r['name']:5} {r['opponents']:16} cs={r['exp_clean_sheets']:.3f} xGA={r['exp_goals_against']:.2f}\")
print('distinct clean-sheet values:', len({r['exp_clean_sheets'] for r in e}))
"
```

**Expected: many distinct values, not 20 identical ones.** Report the spread between
the best and worst club. If it is still flat, the registration is not reaching
`Fixture.lambdas()` — find out why rather than increasing `spread`.

- [ ] **Step 7: Commit**

```bash
git add core/fpl_ratings.py config.py games/fpl/model.py tests/test_fpl_ratings.py && git commit -m "feat(fpl): derive Premier League team ratings from published club strength"
```

---

## Task 3: Surface fixture difficulty in the ticker

FDR is the lingua franca of FPL — readers already think in it, and quoting it makes
the ticker legible without them learning our scale. It is **displayed**, not used to
derive lambdas: it is FPL's editorial judgement, coarse and symmetric, whereas Task
2's ratings decompose into attack and defence. Showing both also gives a free
sanity check — if our model and FDR disagree wildly on a fixture, one of them is
wrong and the operator should look.

**Files:** Modify `games/fpl/model.py`, `evmax/fpl_articles.py`, `evmax/fpl_build.py`; Test `tests/test_fpl_articles.py`

- [ ] **Step 1: Write the failing tests**

```python
class TestTickerDifficulty(unittest.TestCase):
    def test_ticker_carries_each_clubs_own_difficulty(self):
        m = _match("ARS", "COV")
        m["home_difficulty"], m["away_difficulty"] = 2, 5
        out = fpl_articles.ticker([m], ["ARS", "COV"])
        by = {e["name"]: e for e in out}
        self.assertEqual(by["ARS"]["difficulty"], 2)
        self.assertEqual(by["COV"]["difficulty"], 5)

    def test_double_gameweek_averages_difficulty(self):
        """Two fixtures, one number — the mean is the honest summary, and the
        `fixtures` column already tells the reader it covers two games."""
        a = _match("ARS", "COV"); a["home_difficulty"], a["away_difficulty"] = 2, 5
        b = _match("BUR", "ARS", kickoff="2026-08-24T19:00:00+00:00")
        b["home_difficulty"], b["away_difficulty"] = 3, 4
        out = fpl_articles.ticker([a, b], ["ARS", "COV", "BUR"])
        self.assertAlmostEqual({e["name"]: e for e in out}["ARS"]["difficulty"], 3.0)

    def test_blank_club_has_no_difficulty(self):
        out = fpl_articles.ticker([_match("ARS", "COV")], ["ARS", "COV", "EVE"])
        self.assertIsNone({e["name"]: e for e in out}["EVE"]["difficulty"])

    def test_absent_difficulty_does_not_crash(self):
        """Older cached artifacts have no difficulty keys at all."""
        out = fpl_articles.ticker([_match("ARS", "COV")], ["ARS", "COV"])
        self.assertIsNone({e["name"]: e for e in out}["ARS"]["difficulty"])
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement**

- `games/fpl/model.match_summaries` carries `home_difficulty` / `away_difficulty`
  through from the parsed fixture onto each match summary.
- `Fixture` gains the two fields (default `None`) and `load_gameweek` populates them
  when registering.
- `fpl_articles.ticker` aggregates each club's own side's difficulty, averaging across
  a double and leaving `None` for a blank.
- `fpl_build._COLUMNS["ticker"]` gains `"difficulty"`; add a `_COL_LABEL` entry
  (`"FDR"` — the term readers know).

- [ ] **Step 4: Run, verify pass.** Then the full suite.

- [ ] **Step 5: Commit**

```bash
git add games/fpl/model.py core/fixtures.py evmax/fpl_articles.py evmax/fpl_build.py evmax/render.py tests/test_fpl_articles.py && git commit -m "feat(fpl): surface FPL fixture difficulty in the ticker"
```

---

## Task 4: Sharpen priors with last-season history

We already fetch `element-summary` for ~400 players and keep two fields. This task
keeps the rest and uses it where the bootstrap per-90s are thin.

**This does nothing for a player with no Premier League history** — that is the point
of Task 5. Do not add a fallback here that pretends otherwise.

**Files:** Modify `core/fpl_api.py`, `core/fpl_priors.py`; Test `tests/test_fpl_priors.py`

- [ ] **Step 1: Write the failing tests**

```python
class TestHistoryBackedPriors(unittest.TestCase):
    def test_clean_sheet_share_from_history(self):
        """A defender who kept 10 clean sheets in 38 starts carries a different
        defensive profile from one who kept 2 — bootstrap's per-90s do not say so."""
        hist = [{"season_name": "2025/26", "minutes": 3420, "starts": 38,
                 "clean_sheets": 10, "goals_conceded": 53, "bps": 593,
                 "expected_goals_conceded": 48.0, "total_points": 175}]
        p = fpl_priors.history_profile(hist)
        self.assertAlmostEqual(p["clean_sheet_rate"], 10 / 38, places=3)
        self.assertAlmostEqual(p["conceded_per90"], 53 * 90 / 3420, places=3)

    def test_most_recent_season_wins(self):
        hist = [{"season_name": "2024/25", "minutes": 900, "starts": 10,
                 "clean_sheets": 1, "goals_conceded": 20, "bps": 100,
                 "expected_goals_conceded": 18.0, "total_points": 40},
                {"season_name": "2025/26", "minutes": 3420, "starts": 38,
                 "clean_sheets": 10, "goals_conceded": 53, "bps": 593,
                 "expected_goals_conceded": 48.0, "total_points": 175}]
        self.assertAlmostEqual(fpl_priors.history_profile(hist)["clean_sheet_rate"],
                               10 / 38, places=3)

    def test_thin_season_is_ignored(self):
        """A 90-minute cameo is not a season. Below the minutes floor, the profile
        must report no data rather than an estimate from one appearance."""
        hist = [{"season_name": "2025/26", "minutes": 90, "starts": 1,
                 "clean_sheets": 1, "goals_conceded": 0, "bps": 12,
                 "expected_goals_conceded": 0.9, "total_points": 6}]
        self.assertIsNone(fpl_priors.history_profile(hist))

    def test_no_history_is_none(self):
        """Jacquet's case — must return None, not a fabricated profile."""
        self.assertIsNone(fpl_priors.history_profile([]))
```

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement**

- Extend the `element-summary` cache to store `history_past` alongside the DefCon
  fields. **Change the cache filename or add a version key**, because the existing
  400-entry cache has the old shape and a silent shape change would serve partial
  data. Old entries must be re-fetched, not reinterpreted.
- Lift the `minutes > 0` skip in `fetch_defcon_backfill` so a player with zero
  bootstrap minutes but real prior-season history is still fetched. Note in the
  docstring that this widens the fetch set and why. Keep the incremental cache so a
  populated cache still costs no calls.
- Add `fpl_priors.history_profile(history_past) -> dict | None` returning
  `clean_sheet_rate`, `conceded_per90`, `xgc_per90`, `bps_per90`, `points_per_start`
  from the most recent season clearing a minutes floor (`config.FPL_HISTORY_MIN_MINUTES`,
  start at 450).
- Use the profile in `build_with_flags` where it beats the bootstrap value; leave the
  cold-start path untouched.

- [ ] **Step 4: Run, verify pass.** Full suite green.

- [ ] **Step 5: Commit**

```bash
git add core/fpl_api.py core/fpl_priors.py config.py tests/test_fpl_priors.py tests/test_fpl_api.py && git commit -m "feat(fpl): use full last-season history to sharpen player priors"
```

---

## Task 5: Consume the owner's lineup notes

**The owner writes the notes. This codebase does not fetch team news.** No scraping,
no web search, no external calls. Everything here is about making the notes cheap to
write and dangerous to get silently wrong.

`core/research.py` already provides the whole overlay — `status`
(`nailed | rotation_risk | doubtful | out | suspended`), `start_prob_override`,
`lambda_multiplier`, `round`, `sources`, `updated` — and `build_artifact` already
loads it. The gap is entirely ergonomic and diagnostic.

**The dangerous failure is a name mismatch.** The feed uses `web_name`: "Virgil", not
"Van Dijk"; "B.Fernandes", not "Bruno Fernandes". A note whose name matches nothing
is silently ignored, which is exactly how the site once published an article about a
ruled-out player. Unmatched notes must fail loudly.

**Files:** Create `scripts/fpl_notes.py`; Modify `evmax/fpl_build.py`; Test `tests/test_fpl_notes.py`

- [ ] **Step 1: Write the failing tests**

```python
class TestShorthandParsing(unittest.TestCase):
    def test_simple_lines(self):
        text = """
        Jacquet nailed
        Gomez out
        Bradley rotation
        """
        out = fpl_notes.parse(text)
        self.assertEqual(out["Jacquet"]["status"], "nailed")
        self.assertEqual(out["Gomez"]["status"], "out")
        self.assertEqual(out["Bradley"]["status"], "rotation_risk")

    def test_explicit_start_probability(self):
        out = fpl_notes.parse("Jacquet 0.9")
        self.assertAlmostEqual(out["Jacquet"]["start_prob_override"], 0.9)

    def test_status_and_probability_together(self):
        out = fpl_notes.parse("Jacquet nailed 0.95")
        self.assertEqual(out["Jacquet"]["status"], "nailed")
        self.assertAlmostEqual(out["Jacquet"]["start_prob_override"], 0.95)

    def test_trailing_comment_becomes_a_source(self):
        out = fpl_notes.parse("Jacquet nailed # Slot presser 20 Aug")
        self.assertEqual(out["Jacquet"]["sources"], ["Slot presser 20 Aug"])

    def test_blank_lines_and_comments_ignored(self):
        self.assertEqual(fpl_notes.parse("\n\n# just a heading\n"), {})

    def test_unknown_status_word_raises(self):
        """Silently dropping an unrecognised word would lose a real instruction."""
        with self.assertRaises(ValueError):
            fpl_notes.parse("Jacquet definitelystarting")


class TestNameMatching(unittest.TestCase):
    FEED = ["Virgil", "B.Fernandes", "Jacquet", "Gomez"]

    def test_exact_match(self):
        self.assertEqual(fpl_notes.match_name("Jacquet", self.FEED), "Jacquet")

    def test_case_insensitive(self):
        self.assertEqual(fpl_notes.match_name("jacquet", self.FEED), "Jacquet")

    def test_unmatched_returns_none_with_suggestions(self):
        m, suggestions = fpl_notes.match_name_verbose("Van Dijk", self.FEED)
        self.assertIsNone(m)
        self.assertTrue(suggestions)

    def test_ambiguous_prefix_is_not_guessed(self):
        """Two plausible targets must not be resolved by coin flip."""
        m, _ = fpl_notes.match_name_verbose("G", ["Gomez", "Gabriel"])
        self.assertIsNone(m)


class TestNoteWriting(unittest.TestCase):
    def test_writes_frontmatter_research_py_can_read(self):
        # write into a temp research dir, then load via core.research and assert the
        # ResearchEntry round-trips with the right status and round
        ...
```

Write the round-trip test out properly — it is the one that proves the two halves fit.

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement `scripts/fpl_notes.py`**

A small CLI:

```bash
python3 scripts/fpl_notes.py --gw 1 <<'EOF'
Jacquet nailed 0.9   # Slot presser
Gomez out
Bradley rotation
EOF
```

- `parse(text)` → `{name: {status, start_prob_override, sources}}`. Accept the natural
  shorthand: a bare status word, a bare float, both, and a `#` comment as the source.
  Map `rotation` → `rotation_risk` (the overlay's vocabulary) and reject anything
  unrecognised rather than dropping it.
- `match_name` / `match_name_verbose` against the live feed's `web_name` list, with
  suggestions on a miss and **no guessing when ambiguous**.
- Write one `research/players/<name>.md` per entry with `round: <gw>` pinned, plus
  `updated` and `sources`. Refuse to write an unmatched name; print the suggestions
  and exit non-zero so a typo cannot silently become a no-op.
- Print a summary of what was written.

- [ ] **Step 4: Preflight checks in `evmax/fpl_build.py`**

Three warnings:
1. **Unmatched note** — a `research/players/*.md` whose name matches no player in the
   feed. This is the silent-failure case; it must be loud.
2. **Stale note** — pinned to a past gameweek, mirroring `build.expired_risk_flags`.
   Reuse that function if its shape fits rather than writing a second one.
3. **No lineup notes at all for this gameweek** — informational, not alarming, but the
   operator should know the model is running on bootstrap `status` alone.

Test each.

- [ ] **Step 5: Document the workflow in `games/fpl/rules.md`**

A short section: how to write notes, the accepted shorthand, what each status does to
the model, and the fact that notes are pinned per gameweek and expire.

- [ ] **Step 6: Run the full suite, then a real build with a note in place**

Write a note for the motivating case and confirm it moves the number:

```bash
python3 scripts/fpl_notes.py --gw 1 <<'EOF'
Jacquet nailed 0.9   # owner note, Discord 3 Aug
EOF
python3 -m evmax.build --gw 1 --sims 4000 --out /tmp/evmax-p5 --url https://evmax.ai --no-llm
```

Report Jacquet's `x_points` and rank before and after the note. **If the note does not
move his projection, the overlay is not reaching him — investigate rather than
declaring success.**

- [ ] **Step 7: Commit**

```bash
git add scripts/fpl_notes.py evmax/fpl_build.py games/fpl/rules.md tests/test_fpl_notes.py && git commit -m "feat(fpl): consume owner-written lineup notes, with loud name-mismatch guards"
```

---

## Task 6: Verify, rebuild, document

- [ ] **Step 1:** Full suite green. Record the count.
- [ ] **Step 2:** Rebuild GW1 into `dist/`, confirm `dist/round/` is byte-unchanged by
      checksum (as in phase 4), and confirm the ticker now discriminates.
- [ ] **Step 3:** Re-check the motivating case end to end: where does a £5.0m nailed
      Liverpool defender rank in the efficiency and defenders articles now, versus
      before this phase? Report both.
- [ ] **Step 4:** `CHANGELOG.md` entry covering all four workstreams, the symmetry
      approximation in the ratings and its in-season upgrade path, the note-writing
      workflow, and — explicitly — that FDR is displayed rather than used to derive
      lambdas, with the reason.
- [ ] **Step 5:** Commit.

---

## Self-Review

- **Signal coverage:** FDR → T1 + T3; team strength → T1 + T2; last-season history →
  T1 + T4; lineups → T5. All four owner-requested workstreams mapped.
- **The motivating case is a test, not an anecdote:** T2 gives Jacquet Liverpool's
  defensive environment, T5 lets the owner assert he is nailed, and T6 Step 3 measures
  whether the two together actually surface him. T4 is explicitly documented as
  useless for him, so nobody later mistakes it for the fix.
- **Calibration is preserved, not assumed:** T2's league-average-is-neutral test is
  the anchor, and `spread=0` reproduces today's behaviour exactly so a regression can
  be isolated to the ratings rather than the plumbing.
- **The World Cup stays frozen:** the only shared file this phase touches is
  `ratings.TEAM_RATINGS`, and T2 has a dedicated test that registration only adds
  keys. The existing suite remains the regression gate.
- **No scraping anywhere.** T5 is a consumption path for owner-written notes. If an
  implementer finds themselves reaching for a network call in T5, they have
  misread the task.
