# FPL Port — Phase 3 Implementation Plan (sim caching)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cache per-gameweek simulation output so copy and layout changes never re-run 50,000 sims, while any change that *should* change the numbers invalidates the cache automatically.

**Architecture:** A new `core/simcache.py` computes a content-addressed key from everything that determines sim output — including a fingerprint of the model source itself — and stores the derived per-player rows plus per-match scoreline distributions under `data/fpl/simcache/`. `games/fpl/model.run()` consults it before simulating.

**Tech Stack:** Python 3.9 stdlib only (`hashlib`, `json`). No third-party dependencies.

---

## Context an engineer needs before starting

**Run the suite:** `python3 -m unittest discover -s tests -t .` — currently **510 tests, passing**, ~100s. Must stay green.

**Environment:** Python is `python3` (3.9.6); there is no bare `python`. `dict[str, int]` and `int | None` are legal only in annotation position, which works because modules carry `from __future__ import annotations`.

**`tests/test_engine_determinism.py` pins the shared engine's exact output.** Nothing in this phase should touch `core/engine_events.py`. If that test fails, stop.

**Why this phase exists.** A 38-gameweek season means ~38 builds minimum, and in practice several per gameweek as copy is revised. Today every build re-runs the full Monte Carlo. STRATEGY.md's 07-06 owner decision was that per-round build artifacts must become incremental while staying static-first on the CDN.

**What is NOT the goal.** Not a database. Not a server. Not caching across gameweeks (old gameweeks are already never rebuilt). Just: same inputs → skip the sim.

**The load-bearing subtlety.** The cache key MUST include a fingerprint of the model source. Without it, editing a scoring constant in `games/fpl/model.py` would silently reuse a stale artifact and publish a number that was never recomputed — the worst possible failure for a site whose whole positioning is published methodology.

**No existing memoisation to extend.** Tests keep sim cost down by passing `sims=200` and sharing a build in `setUpClass` (`tests/test_site_rate.py:221`), and by patching `fixtures.by_round`. There is no cache to build on; this is new.

---

## File structure

| File | Responsibility |
|---|---|
| `core/simcache.py` (create) | Key computation + artifact read/write. Knows nothing about FPL scoring or HTTP. |
| `games/fpl/model.py` (modify) | Consults the cache in the run path. |
| `tests/test_simcache.py` (create) | Key sensitivity and round-trip tests, all offline. |

`data/fpl/simcache/` holds the artifacts. `data/` is gitignored — never commit anything under it.

---

## Task 1: Model-source fingerprint

**Files:**
- Create: `core/simcache.py`
- Create: `tests/test_simcache.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_simcache.py`:

```python
import os
import unittest
from unittest import mock

from core import simcache


class TestSourceFingerprint(unittest.TestCase):
    def test_fingerprint_is_stable_across_calls(self):
        self.assertEqual(simcache.source_fingerprint(), simcache.source_fingerprint())

    def test_fingerprint_is_a_hex_digest(self):
        fp = simcache.source_fingerprint()
        self.assertEqual(len(fp), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in fp))

    def test_fingerprint_covers_the_model_and_engine_sources(self):
        # The files whose content must invalidate the cache.
        for path in simcache.FINGERPRINT_SOURCES:
            self.assertTrue(os.path.exists(path), f"missing: {path}")
        self.assertTrue(any(p.endswith("engine_events.py")
                            for p in simcache.FINGERPRINT_SOURCES))
        self.assertTrue(any(p.endswith(os.path.join("fpl", "model.py"))
                            for p in simcache.FINGERPRINT_SOURCES))
        self.assertTrue(any(p.endswith("fpl_priors.py")
                            for p in simcache.FINGERPRINT_SOURCES))

    def test_changing_a_source_file_changes_the_fingerprint(self):
        before = simcache.source_fingerprint()
        real = simcache._read_source

        def tampered(path):
            text = real(path)
            return text + "\n# a scoring constant changed\n" if "model.py" in path else text

        with mock.patch.object(simcache, "_read_source", side_effect=tampered):
            after = simcache.source_fingerprint()
        self.assertNotEqual(before, after)

    def test_a_missing_source_file_does_not_raise(self):
        with mock.patch.object(simcache, "_read_source", side_effect=lambda p: ""):
            self.assertEqual(len(simcache.source_fingerprint()), 64)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_simcache -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.simcache'`

- [ ] **Step 3: Write minimal implementation**

Create `core/simcache.py`:

```python
"""Content-addressed cache for per-gameweek simulation output.

A 38-gameweek season means dozens of site builds, and today every one re-runs the
full Monte Carlo. This caches the DERIVED per-player rows and per-match scoreline
distributions keyed by everything that determines them, so a copy or layout change
re-renders with no sim at all — while anything that should change the numbers
invalidates the key automatically.

The model-source fingerprint is the load-bearing part. Without it, editing a
scoring constant would silently reuse a stale artifact and publish a number that
was never recomputed. For a site whose positioning is published methodology, that
is the worst available failure mode.

Knows nothing about FPL scoring or HTTP: callers hand it inputs and an artifact.
"""

from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_HERE, "data", "fpl", "simcache")

# Sources whose CONTENT determines simulated output. Editing any of them must
# invalidate every cached artifact.
FINGERPRINT_SOURCES = [
    os.path.join(_HERE, "core", "engine_events.py"),
    os.path.join(_HERE, "core", "fpl_priors.py"),
    os.path.join(_HERE, "games", "fpl", "model.py"),
]


def _read_source(path: str) -> str:
    """Read a source file for fingerprinting. Missing files hash as empty.

    Separated out so tests can substitute tampered content without touching disk.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def source_fingerprint() -> str:
    """SHA-256 over the concatenated content of FINGERPRINT_SOURCES."""
    h = hashlib.sha256()
    for path in FINGERPRINT_SOURCES:
        h.update(os.path.basename(path).encode())
        h.update(b"\0")
        h.update(_read_source(path).encode())
        h.update(b"\0")
    return h.hexdigest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_simcache -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add core/simcache.py tests/test_simcache.py
git commit -m "feat(simcache): model-source fingerprint so stale sims cannot be published"
```

---

## Task 2: The cache key

**Files:**
- Modify: `core/simcache.py`
- Modify: `tests/test_simcache.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_simcache.py`:

```python
class TestCacheKey(unittest.TestCase):
    def _inputs(self, **kw):
        base = {
            "gameweek": 1,
            "sims": 50_000,
            "seed": 12345,
            "lambdas": {"m1": (1.44, 1.35), "m2": (1.60, 1.10)},
            "priors": {"Haaland": (0.89, 0.35, 0.05, 0.0, 0.0)},
            "research": {"Haaland": "nailed"},
            "config": {"GOAL_CONCENTRATION": 1.2, "PEN_TAKER_GOAL_BONUS": 0.10},
        }
        base.update(kw)
        return base

    def test_same_inputs_give_the_same_key(self):
        self.assertEqual(simcache.cache_key(**self._inputs()),
                         simcache.cache_key(**self._inputs()))

    def test_key_is_order_independent_for_dict_inputs(self):
        a = self._inputs(priors={"A": (1.0,), "B": (2.0,)})
        b = self._inputs(priors={"B": (2.0,), "A": (1.0,)})
        self.assertEqual(simcache.cache_key(**a), simcache.cache_key(**b))

    def test_different_gameweek_changes_the_key(self):
        self.assertNotEqual(simcache.cache_key(**self._inputs()),
                            simcache.cache_key(**self._inputs(gameweek=2)))

    def test_different_lambdas_change_the_key(self):
        other = self._inputs(lambdas={"m1": (2.10, 0.90), "m2": (1.60, 1.10)})
        self.assertNotEqual(simcache.cache_key(**self._inputs()),
                            simcache.cache_key(**other))

    def test_different_priors_change_the_key(self):
        other = self._inputs(priors={"Haaland": (0.50, 0.35, 0.05, 0.0, 0.0)})
        self.assertNotEqual(simcache.cache_key(**self._inputs()),
                            simcache.cache_key(**other))

    def test_different_research_changes_the_key(self):
        other = self._inputs(research={"Haaland": "doubtful"})
        self.assertNotEqual(simcache.cache_key(**self._inputs()),
                            simcache.cache_key(**other))

    def test_different_sim_config_changes_the_key(self):
        other = self._inputs(config={"GOAL_CONCENTRATION": 1.6,
                                     "PEN_TAKER_GOAL_BONUS": 0.10})
        self.assertNotEqual(simcache.cache_key(**self._inputs()),
                            simcache.cache_key(**other))

    def test_different_sim_count_changes_the_key(self):
        self.assertNotEqual(simcache.cache_key(**self._inputs()),
                            simcache.cache_key(**self._inputs(sims=10_000)))

    def test_different_seed_changes_the_key(self):
        self.assertNotEqual(simcache.cache_key(**self._inputs()),
                            simcache.cache_key(**self._inputs(seed=999)))

    def test_a_changed_model_source_changes_the_key(self):
        before = simcache.cache_key(**self._inputs())
        real = simcache._read_source

        def tampered(path):
            text = real(path)
            return text + "\n# GOAL_PTS edited\n" if "model.py" in path else text

        with mock.patch.object(simcache, "_read_source", side_effect=tampered):
            after = simcache.cache_key(**self._inputs())
        self.assertNotEqual(before, after,
                            "editing the model source MUST invalidate the cache")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_simcache -v`
Expected: FAIL — `AttributeError: module 'core.simcache' has no attribute 'cache_key'`

- [ ] **Step 3: Write minimal implementation**

Append to `core/simcache.py`:

```python
def _canonical(value) -> str:
    """Deterministic JSON for hashing.

    `sort_keys` makes dict iteration order irrelevant, so two runs that build the
    same inputs in a different order still hit the same key. Tuples serialise as
    lists, which is fine — we only need determinism, not round-tripping.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def cache_key(*, gameweek: int, sims: int, seed: int, lambdas: dict,
              priors: dict, research: dict, config: dict) -> str:
    """SHA-256 over every input that determines simulated output.

    lambdas:  {match_id: (lam_home, lam_away)} — the match layer.
    priors:   {player_name: tuple of prior fields} — the player layer.
    research: {player_name: whatever the overlay contributes}.
    config:   sim-affecting dials only. Do NOT pass the whole config module —
              unrelated dials (site URL, article copy) would cause spurious misses.
    """
    h = hashlib.sha256()
    for part in (gameweek, sims, seed, lambdas, priors, research, config):
        h.update(_canonical(part).encode())
        h.update(b"\0")
    h.update(source_fingerprint().encode())
    return h.hexdigest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_simcache -v`
Expected: PASS (15 tests)

- [ ] **Step 5: Commit**

```bash
git add core/simcache.py tests/test_simcache.py
git commit -m "feat(simcache): content-addressed key over lambdas, priors, research and config"
```

---

## Task 3: Artifact read/write

**Files:**
- Modify: `core/simcache.py`
- Modify: `tests/test_simcache.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_simcache.py`:

```python
import shutil
import tempfile


class TestArtifactRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="simcache_test_")
        patcher = mock.patch.object(simcache, "CACHE_DIR", self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_miss_returns_none(self):
        self.assertIsNone(simcache.load("nosuchkey"))

    def test_store_then_load_round_trips(self):
        artifact = {"rows": [{"name": "Haaland", "x_points": 5.8}],
                    "matches": {"m1": {"H": 0.6, "D": 0.2, "A": 0.2}}}
        simcache.store("k1", artifact, meta={"gameweek": 1})
        got = simcache.load("k1")
        self.assertEqual(got["rows"], artifact["rows"])
        self.assertEqual(got["matches"], artifact["matches"])

    def test_stored_artifact_carries_its_meta(self):
        simcache.store("k2", {"rows": []}, meta={"gameweek": 7, "sims": 200})
        got = simcache.load("k2")
        self.assertEqual(got["meta"]["gameweek"], 7)
        self.assertEqual(got["meta"]["sims"], 200)

    def test_a_different_key_is_a_miss(self):
        simcache.store("k3", {"rows": [{"name": "X"}]})
        self.assertIsNone(simcache.load("k4"))

    def test_corrupt_artifact_is_treated_as_a_miss_not_a_crash(self):
        path = simcache._path("k5")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not valid json")
        self.assertIsNone(simcache.load("k5"))

    def test_store_creates_the_cache_directory(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        simcache.store("k6", {"rows": []})
        self.assertIsNotNone(simcache.load("k6"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_simcache -v`
Expected: FAIL — `AttributeError: module 'core.simcache' has no attribute 'load'`

- [ ] **Step 3: Write minimal implementation**

Append to `core/simcache.py`:

```python
def _path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")


def load(key: str):
    """The cached artifact for `key`, or None on a miss.

    A corrupt or unreadable artifact is a MISS, not an error: the cost of a miss is
    re-running the sim, whereas raising would break a build over a recoverable
    problem.
    """
    path = _path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def store(key: str, artifact: dict, meta: dict | None = None) -> str:
    """Persist `artifact` under `key`. Returns the path written."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    payload = dict(artifact)
    payload["meta"] = dict(meta or {})
    payload["meta"]["fingerprint"] = source_fingerprint()
    path = _path(key)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_simcache -v`
Expected: PASS (21 tests)

- [ ] **Step 5: Commit**

```bash
git add core/simcache.py tests/test_simcache.py
git commit -m "feat(simcache): artifact store/load with corrupt-as-miss semantics"
```

---

## Task 4: Wire the cache into the FPL run path

**Files:**
- Modify: `games/fpl/model.py`
- Modify: `manage.py`
- Modify: `tests/test_fpl_model.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fpl_model.py`:

```python
class TestRunUsesTheSimCache(unittest.TestCase):
    """The run path must skip simulate_round entirely on a cache hit."""

    def setUp(self):
        import shutil, tempfile
        from core import simcache
        self.tmp = tempfile.mkdtemp(prefix="fpl_cache_test_")
        p = mock.patch.object(simcache, "CACHE_DIR", self.tmp)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_second_call_with_identical_inputs_does_not_simulate(self):
        # Drive build_rows twice; the second must be served from cache.
        calls = []
        real = model.engine_events.simulate_round

        def counting(*a, **kw):
            calls.append(1)
            return real(*a, **kw)

        with mock.patch.object(model.engine_events, "simulate_round",
                              side_effect=counting):
            model.build_rows(_TINY_PRIORS, _TINY_META, gameweek=901, sims=50)
            model.build_rows(_TINY_PRIORS, _TINY_META, gameweek=901, sims=50)
        self.assertEqual(len(calls), 1, "second call should have hit the cache")

    def test_changed_priors_force_a_fresh_simulation(self):
        calls = []
        real = model.engine_events.simulate_round

        def counting(*a, **kw):
            calls.append(1)
            return real(*a, **kw)

        changed = {"H": [ratings.PlayerPrior("A1", "H", "FWD", start_prob=0.4,
                                            exp_minutes=90, goal_share=0.5)]}
        with mock.patch.object(model.engine_events, "simulate_round",
                              side_effect=counting):
            model.build_rows(_TINY_PRIORS, _TINY_META, gameweek=901, sims=50)
            model.build_rows(changed, _TINY_META, gameweek=901, sims=50)
        self.assertEqual(len(calls), 2, "changed priors must invalidate the cache")

    def test_cache_can_be_bypassed(self):
        calls = []
        real = model.engine_events.simulate_round

        def counting(*a, **kw):
            calls.append(1)
            return real(*a, **kw)

        with mock.patch.object(model.engine_events, "simulate_round",
                              side_effect=counting):
            model.build_rows(_TINY_PRIORS, _TINY_META, gameweek=901, sims=50)
            model.build_rows(_TINY_PRIORS, _TINY_META, gameweek=901, sims=50,
                             use_cache=False)
        self.assertEqual(len(calls), 2, "use_cache=False must always simulate")

    def test_cached_rows_match_freshly_simulated_rows(self):
        fresh = model.build_rows(_TINY_PRIORS, _TINY_META, gameweek=901, sims=50,
                                 use_cache=False)
        model.build_rows(_TINY_PRIORS, _TINY_META, gameweek=901, sims=50)
        cached = model.build_rows(_TINY_PRIORS, _TINY_META, gameweek=901, sims=50)
        self.assertEqual([r["name"] for r in fresh], [r["name"] for r in cached])
        for a, b in zip(fresh, cached):
            self.assertAlmostEqual(a["x_points"], b["x_points"], places=6)
```

You will need module-level fixtures in that test file. Add them next to the other helpers:

```python
_TINY_PRIORS = {
    "H": [ratings.PlayerPrior("A1", "H", "FWD", start_prob=1.0, exp_minutes=90,
                              goal_share=0.5)],
    "A": [ratings.PlayerPrior("B1", "A", "DEF", start_prob=1.0, exp_minutes=90,
                              defcon_per90=9.0)],
}
_TINY_META = {"A1": {"price": 7.0, "ownership": 5.0, "minutes": 2700, "bps": 600},
              "B1": {"price": 4.5, "ownership": 2.0, "minutes": 2700, "bps": 500}}
```

and the test module needs `from core import ratings`, `from unittest import mock`, and a registered fixture for gameweek 901 — follow the pattern in `tests/test_engine_priors.py`, which appends a `fixtures.Fixture` in `setUp` and removes it in cleanup.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_fpl_model -v`
Expected: FAIL — `AttributeError: module 'games.fpl.model' has no attribute 'build_rows'`

- [ ] **Step 3: Write minimal implementation**

**Refactor `run()` first.** Extract the simulate-and-derive logic out of `run()` into a testable `build_rows(priors_by_team, players_by_name, gameweek, sims, use_cache=True)` that returns the sorted list of row dicts. `run()` then becomes: load the gameweek, call `build_rows`, print.

`build_rows` should:

1. Build the cache-key inputs from what it has:
   - `lambdas` — `{f.match_id: f.lambdas() for f in fixtures.by_round(gameweek)}`
   - `priors` — a canonical projection of each `PlayerPrior`'s fields, keyed by name. Include every field that affects the sim: `start_prob`, `exp_minutes`, `goal_share`, `assist_share`, `sot_per90`, `pen_taker`, `defcon_per90`, `saves_per90`.
   - `research` — the research entries for this gameweek, projected to something JSON-canonical
   - `config` — ONLY the sim-affecting dials: `GOAL_CONCENTRATION`, `PEN_TAKER_GOAL_BONUS`, `DEVIG_METHOD`
2. `simcache.cache_key(...)` those inputs
3. On a hit, return the cached rows directly
4. On a miss, simulate, derive the rows, `simcache.store(...)`, and return them

**Do not include the BPS baselines in the key separately** — they derive from `players_by_name`'s `bps`/`minutes`, so include those in the meta projection you hash. State in your report how you handled that.

Add `--no-cache` to `manage.py` and thread it through, so an operator can always force a fresh sim.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_fpl_model -v`
Expected: PASS

Run: `python3 -m unittest discover -s tests -t .`
Expected: OK, 510 + new tests

- [ ] **Step 5: Commit**

```bash
git add games/fpl/model.py manage.py tests/test_fpl_model.py
git commit -m "feat(fpl): serve the order book from the sim cache when inputs are unchanged"
```

---

## Task 5: Measure it, and verify invalidation for real

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Measure a cold vs warm run**

```bash
rm -rf data/fpl/simcache
time python3 manage.py fpl --round 1 --sims 20000 > /dev/null
time python3 manage.py fpl --round 1 --sims 20000 > /dev/null
```

Record both wall-clock times. The second must be dramatically faster.

- [ ] **Step 2: Verify a model edit actually invalidates**

Append a harmless comment to `games/fpl/model.py`, re-run, and confirm it simulates again rather than serving the stale artifact:

```bash
echo "# cache-invalidation check" >> games/fpl/model.py
time python3 manage.py fpl --round 1 --sims 20000 > /dev/null
git checkout games/fpl/model.py
```

That run must be slow again. **If it is fast, the fingerprint is not wired in and the cache is unsafe** — stop and report.

- [ ] **Step 3: Verify `--no-cache` forces a fresh sim**

```bash
time python3 manage.py fpl --round 1 --sims 20000 --no-cache > /dev/null
```

Must be slow.

- [ ] **Step 4: Write the CHANGELOG entry**

Add a `## 2026-07-28 — FPL port, phase 3 (sim caching)` section above the phases 1-2 entry, recording: what the key covers, why the source fingerprint is load-bearing, the measured cold/warm times, and that `--no-cache` exists as an escape hatch.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: changelog for FPL port phase 3"
```

---

## Definition of done

- [ ] `python3 -m unittest discover -s tests -t .` passes, 510 + new tests
- [ ] `tests/test_engine_determinism.py` still passes (engine untouched)
- [ ] A warm run is dramatically faster than a cold one, with measured numbers recorded
- [ ] Editing `games/fpl/model.py` invalidates the cache — verified by observing a slow run
- [ ] Changing priors invalidates the cache — verified by test
- [ ] `--no-cache` always simulates
- [ ] Cached rows are numerically identical to freshly simulated ones
- [ ] Nothing under `data/` is committed

## Out of scope

Caching for the World Cup games (the tournament is over; they are never rebuilt). Cross-gameweek caching. Any change to `core/engine_events.py`.

## Carried into Phase 4: is `BonusAccumulator.expected()` right for a double gameweek?

Flagged by the tail-mean implementer, and I could not settle it either way without data.

`BonusAccumulator.expected()` divides accumulated bonus by the number of MATCH appearances,
giving a per-match average. `total_points` then scales it by `sample.played / sample.sims`
(the T18e appearance fix). For a double gameweek `played` increments once per match, so
`played / sims` approaches 2.0 — which multiplied by a per-match average yields the sum
across both matches. **That may already be correct by construction.**

But it is unverified, because the fixture feed has no double gameweeks yet and will not for
months. The new `SimPointsAccumulator` sums per sim explicitly and has a dedicated
double-gameweek test, so the `ceiling` column is definitely right; the `x_points` column
goes through the older assembly path and is the one in question.

**Do not guess-fix this.** Two concrete ways to settle it:
1. Build a synthetic double-gameweek fixture pair and assert `total_points` agrees with
   `SimPointsAccumulator.mean()` for a player appearing in both — the cross-check that
   already exists for single fixtures, extended to doubles.
2. Or retire the assembly path for `x_points` and read both columns off the distribution,
   which removes the whole class of question. That was deliberately not done here to keep
   `total_points` as an independent cross-check of the per-sim path.

Option 1 first — it is cheap and tells you whether option 2 is even needed.
