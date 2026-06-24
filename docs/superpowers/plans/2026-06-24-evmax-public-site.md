# evmax Public Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a static, agent-friendly evmax website — a set of FIFA World Cup Fantasy "article" pages (best XI, captains, high-ceiling XI, differentials, best-value XI, blowout-fixture transfers) plus per-article JSON, `llms.txt`, `robots.txt`, and `sitemap.xml` — from the existing wc2026 engine, deployable to Cloudflare Pages today.

**Architecture:** A new `site/` layer sits on top of the untouched engine. `site/articles.py` holds pure ranking/selection logic (no I/O); `site/render.py` holds pure HTML/SVG/JSON/text emitters; `site/build.py` is the CLI that runs `engine_events.simulate_round`, enriches players with `data/players.json` metadata, calls the pure functions, and writes a `dist/` tree. Pure functions are unit-tested offline with tiny fixtures (no 50k-sim runs in tests).

**Tech Stack:** Python 3 stdlib only (f-strings for HTML, hand-built inline SVG — no template/chart deps so it ships with zero install). Tests use `unittest` (matching the existing `tests/` suite). Deploy via Cloudflare Pages direct upload of `dist/`.

---

## File Structure

- Create: `site/__init__.py` — marks the package.
- Create: `site/articles.py` — pure logic: load player metadata, build enriched rows, rank captains/value, filter differentials, formation-constrained XI selection, blowout-fixture detection.
- Create: `site/render.py` — pure emitters: JSON envelope, inline-SVG bar chart, article HTML page, hub HTML page, `llms.txt`, `robots.txt`, `sitemap.xml`, summary sentence.
- Create: `site/build.py` — CLI orchestration: run the engine for a round, assemble all articles, write the `dist/` tree.
- Create: `tests/test_site_articles.py` — unit tests for `site/articles.py` (tiny fixtures).
- Create: `tests/test_site_render.py` — unit tests for `site/render.py` (string/JSON assertions).
- Engine files (`core/`, `games/fifa/model.py`) are **read-only** here — imported, never modified.

Shared constants used across tasks (define once in `site/articles.py`, import where needed):

```python
POS_MIN = {"GK": 1, "DEF": 3, "MID": 2, "FWD": 1}
POS_MAX = {"GK": 1, "DEF": 5, "MID": 5, "FWD": 3}
XI_SIZE = 11
DIFF_MAX_OWNERSHIP = 10.0   # percent — "differential" cutoff
DIFF_MIN_XPTS = 4.0         # only surface differentials worth owning
BLOWOUT_FIXTURES = 2        # how many top-lambda fixtures count as "blowouts"
ARTICLES = ["best-xi", "captains", "high-ceiling-xi", "differentials",
            "best-value-xi", "blowout-transfers"]
ARTICLE_TITLES = {
    "best-xi": "Best World Cup Fantasy XI",
    "captains": "Best captain picks",
    "high-ceiling-xi": "High-ceiling / differential XI",
    "differentials": "Best differentials (low-owned)",
    "best-value-xi": "Best value XI",
    "blowout-transfers": "Best transfers for the blowout fixtures",
}
```

The enriched **row** dict (produced by `build_rows`, consumed everywhere):

```python
{"name": str, "team": str, "position": str,        # "GK"|"DEF"|"MID"|"FWD"
 "x_points": float, "captain_ev": float, "ceiling": float,
 "price": float | None, "ownership_pct": float | None,
 "value": float | None,                             # x_points / price
 "kickoff": str | None}                             # ISO-8601 UTC
```

---

## Task 1: Package skeleton + player-metadata loader

**Files:**
- Create: `site/__init__.py`
- Create: `site/articles.py`
- Test: `tests/test_site_articles.py`

- [ ] **Step 1: Create the package marker**

Create `site/__init__.py` with a single line:

```python
"""evmax static-site layer over the wc2026 engine (pure stdlib)."""
```

- [ ] **Step 2: Write the failing test for `load_player_meta`**

Create `tests/test_site_articles.py`:

```python
import json
import os
import tempfile
import unittest

from site import articles


class LoadPlayerMetaTest(unittest.TestCase):
    def _write(self, players):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"_comment": "x", "players": players}, fh)
        self.addCleanup(os.remove, path)
        return path

    def test_maps_name_to_metadata(self):
        path = self._write([
            {"name": "Kane", "aliases": [], "team": "England", "fifa_pos": "FWD",
             "fifa_price": 11.0, "ownership": 42.0},
        ])
        meta = articles.load_player_meta(path)
        self.assertEqual(meta["Kane"]["team"], "England")
        self.assertEqual(meta["Kane"]["position"], "FWD")
        self.assertEqual(meta["Kane"]["price"], 11.0)
        self.assertEqual(meta["Kane"]["ownership_pct"], 42.0)

    def test_aliases_also_resolve(self):
        path = self._write([
            {"name": "Bruno Fernandes", "aliases": ["B. Fernandes"], "team": "Portugal",
             "fifa_pos": "MID", "fifa_price": 9.5, "ownership": 18.0},
        ])
        meta = articles.load_player_meta(path)
        self.assertIn("B. Fernandes", meta)
        self.assertEqual(meta["B. Fernandes"]["position"], "MID")
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_articles -v`
Expected: FAIL with `AttributeError: module 'site.articles' has no attribute 'load_player_meta'` (or ImportError for the empty module).

- [ ] **Step 4: Implement `load_player_meta` and the shared constants**

Create `site/articles.py` starting with the constants block from the File Structure section above, then:

```python
import json
import os

from core import fixtures

_PLAYERS_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "players.json")


def load_player_meta(path: str = _PLAYERS_JSON) -> dict:
    """name (and aliases) -> {team, position, price, ownership_pct} from data/players.json."""
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    out = {}
    for p in raw.get("players", []):
        meta = {
            "team": p.get("team"),
            "position": p.get("fifa_pos"),
            "price": p.get("fifa_price"),
            "ownership_pct": p.get("ownership"),
        }
        out[p["name"]] = meta
        for alias in p.get("aliases", []):
            out.setdefault(alias, meta)
    return out
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_articles -v`
Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
cd ~/wc2026 && git add site/__init__.py site/articles.py tests/test_site_articles.py
git commit -m "feat(site): player-metadata loader + shared constants"
```

(If `~/wc2026` is not yet a git repo, first run `git init && git add -A && git commit -m "chore: snapshot engine before evmax site"`, then the above.)

---

## Task 2: Build enriched rows

**Files:**
- Modify: `site/articles.py`
- Test: `tests/test_site_articles.py`

- [ ] **Step 1: Write the failing test for `build_rows`**

Append to `tests/test_site_articles.py`:

```python
class BuildRowsTest(unittest.TestCase):
    def setUp(self):
        self.means = {
            "Kane": {"position": "FWD", "goals": 0.8, "assists": 0.2, "clean_sheet": 0.3,
                     "played": 1.0, "yellow": 0.1, "red": 0.0, "sot": 1.2, "saves": 0.0,
                     "conc_beyond": 0.4, "minutes": 90.0, "goal_share": 0.4, "assist_share": 0.2},
        }
        self.samples = {"Kane": [0, 1, 0, 2, 1]}
        self.meta = {"Kane": {"team": "England", "position": "FWD", "price": 11.0,
                              "ownership_pct": 42.0}}
        self.kickoffs = {"England": "2026-06-26T19:00:00+00:00"}

    def test_row_has_xpts_ceiling_captain_value_kickoff(self):
        rows = articles.build_rows(self.means, self.samples, self.meta, self.kickoffs)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["name"], "Kane")
        self.assertGreater(r["x_points"], 0)
        self.assertAlmostEqual(r["captain_ev"], 2 * r["x_points"], places=6)
        self.assertGreaterEqual(r["ceiling"], r["x_points"])  # P85 goals >= mean goals
        self.assertAlmostEqual(r["value"], r["x_points"] / 11.0, places=6)
        self.assertEqual(r["kickoff"], "2026-06-26T19:00:00+00:00")

    def test_players_without_meta_or_position_are_skipped(self):
        means = dict(self.means)
        means["Ghost"] = dict(self.means["Kane"])  # no meta entry
        rows = articles.build_rows(means, {"Kane": [0, 1], "Ghost": [0]}, self.meta, self.kickoffs)
        self.assertEqual([r["name"] for r in rows], ["Kane"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_articles.BuildRowsTest -v`
Expected: FAIL with `AttributeError: ... has no attribute 'build_rows'`.

- [ ] **Step 3: Implement `build_rows`**

Add to `site/articles.py`:

```python
from games.fifa import model as fifa_model


def build_rows(means: dict, samples: dict, meta: dict, kickoffs: dict) -> list:
    """Enrich the engine's per-player means with metadata into ranked-ready rows.

    means:    name -> event-means dict (from engine_events.event_means)
    samples:  name -> goal_samples list (from PlayerSample.goal_samples)
    meta:     name -> {team, position, price, ownership_pct} (load_player_meta)
    kickoffs: team -> ISO-8601 kickoff string for the round
    Players missing metadata or a position are skipped.
    """
    rows = []
    for name, ev in means.items():
        m = meta.get(name)
        if not m or not m.get("position"):
            continue
        xp = fifa_model.expected_points(ev)
        ceiling = fifa_model.ceiling_points(ev, samples.get(name, []))
        price = m.get("price")
        rows.append({
            "name": name,
            "team": m.get("team"),
            "position": m["position"],
            "x_points": round(xp, 2),
            "captain_ev": round(2 * xp, 2),
            "ceiling": round(ceiling, 2),
            "price": price,
            "ownership_pct": m.get("ownership_pct"),
            "value": round(xp / price, 3) if price else None,
            "kickoff": kickoffs.get(m.get("team")),
        })
    return rows
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_articles.BuildRowsTest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/wc2026 && git add site/articles.py tests/test_site_articles.py
git commit -m "feat(site): build enriched player rows (xpts/ceiling/value/kickoff)"
```

---

## Task 3: Ranking, differentials, value

**Files:**
- Modify: `site/articles.py`
- Test: `tests/test_site_articles.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_site_articles.py`:

```python
def _row(name, pos, xp, own=20.0, price=8.0, ceiling=None):
    return {"name": name, "team": name + "land", "position": pos, "x_points": xp,
            "captain_ev": 2 * xp, "ceiling": ceiling if ceiling is not None else xp,
            "price": price, "ownership_pct": own, "value": xp / price, "kickoff": None}


class RankingTest(unittest.TestCase):
    def setUp(self):
        self.rows = [
            _row("A", "FWD", 9.0, own=50.0, price=11.0),
            _row("B", "MID", 6.0, own=3.0, price=6.0),
            _row("C", "DEF", 4.5, own=1.0, price=4.0),
        ]

    def test_rank_captains_orders_by_captain_ev_desc_and_assigns_rank(self):
        out = articles.rank_captains(self.rows)
        self.assertEqual([r["name"] for r in out], ["A", "B", "C"])
        self.assertEqual(out[0]["rank"], 1)

    def test_rank_value_orders_by_value_desc(self):
        out = articles.rank_value(self.rows)
        # C: 4.5/4=1.125, B: 6/6=1.0, A: 9/11=0.818
        self.assertEqual([r["name"] for r in out], ["C", "B", "A"])

    def test_differentials_filter_low_owned_and_min_xpts(self):
        out = articles.differentials(self.rows)
        # own<10 AND x_points>=4.0 -> B(6.0,own3) and C(4.5,own1); A excluded (own 50)
        self.assertEqual(sorted(r["name"] for r in out), ["B", "C"])
        self.assertEqual(out[0]["x_points"], 6.0)  # sorted by xpts desc -> B first
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_articles.RankingTest -v`
Expected: FAIL (`rank_captains` / `rank_value` / `differentials` not defined).

- [ ] **Step 3: Implement the three functions**

Add to `site/articles.py`:

```python
def _ranked(rows, key, reverse=True):
    out = [dict(r) for r in sorted(rows, key=lambda r: r[key], reverse=reverse)]
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


def rank_captains(rows: list) -> list:
    return _ranked(rows, "captain_ev")


def rank_value(rows: list) -> list:
    return _ranked([r for r in rows if r.get("value") is not None], "value")


def differentials(rows: list, max_ownership: float = DIFF_MAX_OWNERSHIP,
                  min_xpts: float = DIFF_MIN_XPTS) -> list:
    pool = [r for r in rows
            if r.get("ownership_pct") is not None
            and r["ownership_pct"] < max_ownership
            and r["x_points"] >= min_xpts]
    return _ranked(pool, "x_points")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_articles.RankingTest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/wc2026 && git add site/articles.py tests/test_site_articles.py
git commit -m "feat(site): captain/value ranking + differentials filter"
```

---

## Task 4: Formation-constrained XI selection

**Files:**
- Modify: `site/articles.py`
- Test: `tests/test_site_articles.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_site_articles.py`:

```python
class SelectXITest(unittest.TestCase):
    def _pool(self):
        rows = []
        rows += [_row(f"GK{i}", "GK", 5 - i * 0.1) for i in range(3)]
        rows += [_row(f"DEF{i}", "DEF", 6 - i * 0.1) for i in range(8)]
        rows += [_row(f"MID{i}", "MID", 7 - i * 0.1) for i in range(8)]
        rows += [_row(f"FWD{i}", "FWD", 8 - i * 0.1) for i in range(6)]
        return rows

    def test_returns_valid_xi(self):
        xi = articles.select_xi(self._pool(), "x_points")
        self.assertEqual(len(xi), articles.XI_SIZE)
        counts = {}
        for r in xi:
            counts[r["position"]] = counts.get(r["position"], 0) + 1
        self.assertEqual(counts["GK"], 1)
        self.assertGreaterEqual(counts["DEF"], 3)
        self.assertGreaterEqual(counts["MID"], 2)
        self.assertGreaterEqual(counts["FWD"], 1)
        for pos, mx in articles.POS_MAX.items():
            self.assertLessEqual(counts.get(pos, 0), mx)

    def test_ranks_by_the_given_key(self):
        # high-ceiling XI should sort on ceiling, not x_points
        pool = self._pool()
        pool[10]["ceiling"] = 99.0  # a DEF with huge ceiling
        xi = articles.select_xi(pool, "ceiling")
        self.assertEqual(xi[0]["ceiling"], 99.0)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_articles.SelectXITest -v`
Expected: FAIL (`select_xi` not defined).

- [ ] **Step 3: Implement `select_xi`**

Add to `site/articles.py`:

```python
def select_xi(rows: list, key: str) -> list:
    """Greedy formation-constrained XI maximizing `key` (e.g. 'x_points' or 'ceiling').
    Fills position minimums first, then the remaining slots by best `key` within maxima."""
    pools = {pos: sorted([r for r in rows if r["position"] == pos and r.get(key) is not None],
                         key=lambda r: r[key], reverse=True)
             for pos in POS_MIN}
    chosen, counts = [], {}
    for pos in POS_MIN:
        take = pools[pos][:POS_MIN[pos]]
        chosen += take
        counts[pos] = len(take)
    leftovers = []
    for pos in POS_MIN:
        leftovers += pools[pos][POS_MIN[pos]:]
    leftovers.sort(key=lambda r: r[key], reverse=True)
    for r in leftovers:
        if len(chosen) >= XI_SIZE:
            break
        pos = r["position"]
        if counts.get(pos, 0) < POS_MAX[pos]:
            chosen.append(r)
            counts[pos] = counts.get(pos, 0) + 1
    chosen.sort(key=lambda r: r[key], reverse=True)
    return chosen
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_articles.SelectXITest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/wc2026 && git add site/articles.py tests/test_site_articles.py
git commit -m "feat(site): formation-constrained XI selection"
```

---

## Task 5: Blowout fixtures + blowout transfers

**Files:**
- Modify: `site/articles.py`
- Test: `tests/test_site_articles.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_site_articles.py`:

```python
class BlowoutTest(unittest.TestCase):
    def test_blowout_transfers_picks_attackers_from_highest_lambda_fixtures(self):
        # two fixtures; (Spain vs Malta) has the biggest combined lambda
        fixture_totals = {("Spain", "Malta"): 4.2, ("Iran", "Qatar"): 2.1}
        teams_in_blowout = {"Spain", "Malta"}
        rows = [
            _row("Oyarzabal", "FWD", 7.0), _row("Pedri", "MID", 5.5),
            _row("Cucurella", "DEF", 3.0),       # defender -> excluded (attackers only)
            _row("IranFwd", "FWD", 6.0),         # not in a blowout fixture
        ]
        for r in rows:
            r["team"] = {"Oyarzabal": "Spain", "Pedri": "Spain", "Cucurella": "Spain",
                         "IranFwd": "Iran"}[r["name"]]
        out = articles.blowout_transfers(rows, teams_in_blowout)
        self.assertEqual([r["name"] for r in out], ["Oyarzabal", "Pedri"])
        self.assertEqual(out[0]["rank"], 1)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_articles.BlowoutTest -v`
Expected: FAIL (`blowout_transfers` not defined).

- [ ] **Step 3: Implement `blowout_teams` and `blowout_transfers`**

Add to `site/articles.py`:

```python
def blowout_teams(fantasy_round: int, top_n: int = BLOWOUT_FIXTURES) -> set:
    """Teams playing in the round's highest combined-lambda (most lopsided/high-scoring)
    fixtures. Uses core.fixtures lambdas (odds-derived where present)."""
    fx = fixtures.by_round(fantasy_round)
    scored = []
    for f in fx:
        lh, la = f.lambdas()
        scored.append((lh + la, f))
    scored.sort(key=lambda t: t[0], reverse=True)
    teams = set()
    for _total, f in scored[:top_n]:
        teams.add(f.home)
        teams.add(f.away)
    return teams


def blowout_transfers(rows: list, teams: set) -> list:
    """Attackers (FWD/MID) from the blowout fixtures, ranked by x_points."""
    pool = [r for r in rows if r["team"] in teams and r["position"] in ("FWD", "MID")]
    return _ranked(pool, "x_points")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_articles.BlowoutTest -v`
Expected: PASS.

- [ ] **Step 5: Run the full articles suite**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_articles -v`
Expected: PASS (all tests).

- [ ] **Step 6: Commit**

```bash
cd ~/wc2026 && git add site/articles.py tests/test_site_articles.py
git commit -m "feat(site): blowout-fixture detection + transfer picks"
```

---

## Task 6: JSON envelope + summary sentence

**Files:**
- Create: `site/render.py`
- Test: `tests/test_site_render.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_site_render.py`:

```python
import json
import unittest

from site import render


class JsonEnvelopeTest(unittest.TestCase):
    def setUp(self):
        self.entries = [
            {"rank": 1, "name": "Bruno Fernandes", "team": "Portugal", "position": "MID",
             "x_points": 5.67, "captain_ev": 11.34, "ceiling": 9.1, "price": 9.5,
             "ownership_pct": 18.0, "value": 0.6, "kickoff": "2026-06-27T23:30:00+00:00"},
        ]

    def test_envelope_has_required_fields(self):
        env = render.article_json("fifa_world_cup_fantasy", 3, "captains",
                                  "Best captain picks — Round 3",
                                  "2026-06-24T12:00:00+00:00", 50000, self.entries)
        self.assertEqual(env["competition"], "fifa_world_cup_fantasy")
        self.assertEqual(env["round"], 3)
        self.assertEqual(env["article"], "captains")
        self.assertEqual(env["sims"], 50000)
        self.assertEqual(env["entries"][0]["name"], "Bruno Fernandes")
        self.assertIn("methodology", env)
        self.assertEqual(env["source"], "https://evmax.pages.dev")
        # must be JSON-serializable
        json.dumps(env)

    def test_summary_sentence_is_stat_dense(self):
        s = render.summary_sentence("captains", self.entries)
        self.assertIn("Bruno Fernandes", s)
        self.assertIn("11.3", s)  # captain EV, one decimal
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_render -v`
Expected: FAIL (module/functions not defined).

- [ ] **Step 3: Implement the envelope, methodology, and summary**

Create `site/render.py`:

```python
"""Pure emitters for the evmax static site (HTML/SVG/JSON/text). No I/O."""

SITE_URL = "https://evmax.pages.dev"
METHODOLOGY = ("Market odds (de-vigged) → Dixon-Coles scorelines → 50k Monte-Carlo "
               "simulations, scored on the official FIFA World Cup Fantasy points table.")


def article_json(competition, fantasy_round, article, title, generated_at, sims, entries):
    return {
        "competition": competition,
        "round": fantasy_round,
        "article": article,
        "title": title,
        "generated_at": generated_at,
        "sims": sims,
        "methodology": METHODOLOGY,
        "entries": entries,
        "source": SITE_URL,
        "license": "Attribution requested: evmax",
    }


def summary_sentence(article, entries):
    if not entries:
        return "No qualifying players this round."
    top = entries[0]
    name, team = top["name"], top.get("team", "")
    if article == "captains":
        return (f"Captain {name} ({team}): {top['captain_ev']:.1f} expected points — "
                f"the highest captain EV in this round.")
    if article == "differentials":
        return (f"{name} ({team}) is the standout differential: {top['x_points']:.1f} xPts "
                f"at just {top['ownership_pct']:.1f}% ownership.")
    if article == "best-value-xi":
        return (f"{name} ({team}) leads on value: {top['x_points']:.1f} xPts for "
                f"{top['price']:.1f}m.")
    if article == "high-ceiling-xi":
        return (f"{name} ({team}) has the highest ceiling: up to {top['ceiling']:.1f} points.")
    if article == "blowout-transfers":
        return (f"{name} ({team}) is the top attacker in this round's most lopsided fixtures "
                f"at {top['x_points']:.1f} xPts.")
    return f"{name} ({team}) tops the list at {top['x_points']:.1f} expected points."
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_render -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/wc2026 && git add site/render.py tests/test_site_render.py
git commit -m "feat(site): JSON envelope + stat-dense summary sentences"
```

---

## Task 7: Inline-SVG bar chart

**Files:**
- Modify: `site/render.py`
- Test: `tests/test_site_render.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_site_render.py`:

```python
class SvgChartTest(unittest.TestCase):
    def test_svg_contains_bars_and_labels(self):
        svg = render.svg_bar_chart([("Bruno", 11.3), ("Wirtz", 10.1), ("Kane", 9.2)], "EV")
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn("</svg>", svg)
        self.assertEqual(svg.count("<rect"), 3)
        self.assertIn("Bruno", svg)
        self.assertIn("11.3", svg)

    def test_empty_input_is_safe(self):
        svg = render.svg_bar_chart([], "EV")
        self.assertTrue(svg.startswith("<svg"))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_render.SvgChartTest -v`
Expected: FAIL (`svg_bar_chart` not defined).

- [ ] **Step 3: Implement `svg_bar_chart`**

Add to `site/render.py`:

```python
import html as _html


def svg_bar_chart(pairs, unit, width=520, row_h=34):
    """Horizontal bar chart as a standalone inline SVG (no JS). pairs = [(label, value)]."""
    pairs = list(pairs)
    height = max(row_h * len(pairs) + 10, 40)
    if not pairs:
        return f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg"></svg>'
    vmax = max(v for _, v in pairs) or 1.0
    label_w, pad = 150, 8
    bar_max = width - label_w - 60
    rows = []
    for i, (label, value) in enumerate(pairs):
        y = i * row_h + pad
        bw = max(2, bar_max * (value / vmax))
        lbl = _html.escape(str(label))
        rows.append(
            f'<text x="0" y="{y + 16}" font-size="13" fill="#cbd5e1">{lbl}</text>'
            f'<rect x="{label_w}" y="{y + 4}" width="{bw:.1f}" height="18" rx="3" '
            f'fill="#22d3ee"/>'
            f'<text x="{label_w + bw + 6:.1f}" y="{y + 17}" font-size="12" '
            f'fill="#e2e8f0">{value:.1f}</text>')
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" '
            f'xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-label="{_html.escape(unit)} chart">' + "".join(rows) + "</svg>")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_render.SvgChartTest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/wc2026 && git add site/render.py tests/test_site_render.py
git commit -m "feat(site): inline-SVG horizontal bar chart"
```

---

## Task 8: Article HTML page + hub page

**Files:**
- Modify: `site/render.py`
- Test: `tests/test_site_render.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_site_render.py`:

```python
class HtmlTest(unittest.TestCase):
    def setUp(self):
        self.entries = [
            {"rank": 1, "name": "Bruno Fernandes", "team": "Portugal", "position": "MID",
             "x_points": 5.67, "captain_ev": 11.34, "ceiling": 9.1, "price": 9.5,
             "ownership_pct": 18.0, "value": 0.6, "kickoff": "2026-06-27T23:30:00+00:00"},
        ]
        self.nav = [("captains", "Best captain picks"), ("best-xi", "Best World Cup Fantasy XI")]

    def test_article_page_has_head_jsonld_table_and_summary(self):
        h = render.article_page(round_no=3, article="captains",
                                title="Best captain picks — Round 3",
                                entries=self.entries, columns=["captain_ev", "x_points"],
                                nav=self.nav, json_url="/api/round/3/captains.json")
        self.assertIn("<!doctype html>", h.lower())
        self.assertIn("application/ld+json", h)         # JSON-LD present
        self.assertIn("Bruno Fernandes", h)
        self.assertIn("11.3", h)                         # summary number
        self.assertIn('rel="alternate"', h)              # link to JSON
        self.assertIn("Best World Cup Fantasy XI", h)    # cross-link nav
        self.assertIn("Monte-Carlo", h)                  # methodology

    def test_hub_page_links_all_articles(self):
        h = render.hub_page(round_no=3, nav=self.nav,
                            highlights={"captains": "Captain Bruno Fernandes (11.3 EV)"})
        self.assertIn("Best captain picks", h)
        self.assertIn("/round/3/captains/", h)
        self.assertIn("Captain Bruno Fernandes", h)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_render.HtmlTest -v`
Expected: FAIL (`article_page` / `hub_page` not defined).

- [ ] **Step 3: Implement `article_page` and `hub_page`**

Add to `site/render.py`:

```python
import json as _json

_COL_LABEL = {"x_points": "xPts", "captain_ev": "Captain EV", "ceiling": "Ceiling",
              "value": "Value", "price": "Price", "ownership_pct": "Owned %"}


def _fmt(col, row):
    v = row.get(col)
    if v is None:
        return "—"
    if col == "ownership_pct":
        return f"{v:.1f}%"
    if col == "price":
        return f"{v:.1f}"
    return f"{v:.2f}" if isinstance(v, float) else str(v)


def _table(entries, columns):
    head = "".join(f"<th>{_COL_LABEL.get(c, c)}</th>" for c in columns)
    body = []
    for r in entries:
        cells = (f'<td class="name">{_html.escape(r["name"])}</td>'
                 f'<td>{_html.escape(r.get("team") or "")}</td>'
                 f'<td>{_html.escape(r.get("position") or "")}</td>')
        cells += "".join(f"<td>{_fmt(c, r)}</td>" for c in columns)
        body.append(f"<tr><td>{r.get('rank','')}</td>{cells}</tr>")
    return (f'<table><thead><tr><th>#</th><th>Player</th><th>Team</th><th>Pos</th>'
            f'{head}</tr></thead><tbody>{"".join(body)}</tbody></table>')


_STYLE = ("body{margin:0;background:#0b1120;color:#e2e8f0;font:16px/1.5 system-ui,sans-serif}"
          "main{max-width:880px;margin:0 auto;padding:24px}"
          "h1{font-size:1.6rem;line-height:1.2}a{color:#22d3ee}"
          ".lede{font-size:1.15rem;color:#f8fafc;margin:12px 0 20px}"
          "nav a{display:inline-block;margin:0 12px 8px 0}"
          "table{width:100%;border-collapse:collapse;margin:16px 0}"
          "th,td{padding:6px 8px;text-align:left;border-bottom:1px solid #1e293b;font-size:14px}"
          ".name{font-weight:600}.method{color:#94a3b8;font-size:13px;margin-top:24px}")


def _nav_html(nav, round_no):
    return "<nav>" + "".join(
        f'<a href="/round/{round_no}/{slug}/">{_html.escape(title)}</a>'
        for slug, title in nav) + "</nav>"


def article_page(round_no, article, title, entries, columns, nav, json_url):
    chart_pairs = [(r["name"], r.get(columns[0]) or 0.0) for r in entries[:6]]
    jsonld = _json.dumps({
        "@context": "https://schema.org", "@type": "Dataset", "name": title,
        "description": METHODOLOGY, "url": f"{SITE_URL}{json_url}",
        "creator": {"@type": "Organization", "name": "evmax"},
        "variableMeasured": [_COL_LABEL.get(c, c) for c in columns],
    })
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html.escape(title)} | evmax</title>
<meta name="description" content="{_html.escape(summary_sentence(article, entries))}">
<link rel="alternate" type="application/json" href="{json_url}">
<style>{_STYLE}</style>
<script type="application/ld+json">{jsonld}</script>
</head><body><main>
<h1>{_html.escape(title)}</h1>
<p class="lede">{_html.escape(summary_sentence(article, entries))}</p>
{svg_bar_chart(chart_pairs, _COL_LABEL.get(columns[0], columns[0]))}
{_table(entries, columns)}
<p class="method"><strong>Method:</strong> {METHODOLOGY} Data: free market odds + our simulation. Backtested results coming.</p>
<p class="method">Machine-readable: <a href="{json_url}">{json_url}</a></p>
<h2 style="font-size:1.1rem">More Round {round_no} picks</h2>
{_nav_html(nav, round_no)}
</main></body></html>"""


def hub_page(round_no, nav, highlights):
    cards = []
    for slug, title in nav:
        hl = _html.escape(highlights.get(slug, ""))
        cards.append(f'<p><a href="/round/{round_no}/{slug}/"><strong>{_html.escape(title)}</strong></a><br>'
                     f'<span class="method">{hl}</span></p>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>World Cup Fantasy Round {round_no} — picks, captains, differentials | evmax</title>
<meta name="description" content="Simulation-based World Cup Fantasy picks for Round {round_no}: best XI, captains, differentials, value and blowout-fixture transfers from 50k Monte-Carlo runs.">
<style>{_STYLE}</style>
</head><body><main>
<h1>World Cup Fantasy — Round {round_no}</h1>
<p class="lede">Simulation-based picks from 50,000 Monte-Carlo runs on market odds. Pick a list:</p>
{"".join(cards)}
<p class="method"><strong>Method:</strong> {METHODOLOGY}</p>
</main></body></html>"""
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_render.HtmlTest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/wc2026 && git add site/render.py tests/test_site_render.py
git commit -m "feat(site): article + hub HTML pages with JSON-LD"
```

---

## Task 9: llms.txt, robots.txt, sitemap.xml

**Files:**
- Modify: `site/render.py`
- Test: `tests/test_site_render.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_site_render.py`:

```python
class AgentFilesTest(unittest.TestCase):
    def setUp(self):
        self.nav = [("captains", "Best captain picks"), ("best-xi", "Best World Cup Fantasy XI")]

    def test_llms_txt_lists_articles_and_json(self):
        t = render.llms_txt(round_no=3, nav=self.nav)
        self.assertIn("evmax", t)
        self.assertIn("/round/3/captains/", t)
        self.assertIn("/api/round/3/captains.json", t)

    def test_robots_allows_ai_bots(self):
        r = render.robots_txt()
        for bot in ["GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"]:
            self.assertIn(bot, r)
        self.assertIn("Sitemap:", r)

    def test_sitemap_lists_pages(self):
        x = render.sitemap_xml(round_no=3, nav=self.nav)
        self.assertIn("<urlset", x)
        self.assertIn(f"{render.SITE_URL}/round/3/captains/", x)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_render.AgentFilesTest -v`
Expected: FAIL (functions not defined).

- [ ] **Step 3: Implement the three emitters**

Add to `site/render.py`:

```python
_AI_BOTS = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-Web",
            "PerplexityBot", "Google-Extended", "CCBot", "Applebot-Extended"]


def llms_txt(round_no, nav):
    lines = [
        "# evmax — simulation-based World Cup Fantasy picks",
        "",
        "> Free, transparent fantasy picks from 50,000 Monte-Carlo simulations on "
        "de-vigged market odds, scored on the official FIFA World Cup Fantasy table. "
        "Numbers are machine-readable JSON; attribution to evmax is requested.",
        "",
        f"## Round {round_no} articles",
    ]
    for slug, title in nav:
        lines.append(f"- [{title}]({SITE_URL}/round/{round_no}/{slug}/) — "
                     f"data: {SITE_URL}/api/round/{round_no}/{slug}.json")
    lines += ["", "## API", f"- Article index: {SITE_URL}/api/latest.json"]
    return "\n".join(lines) + "\n"


def robots_txt():
    blocks = [f"User-agent: {b}\nAllow: /" for b in _AI_BOTS]
    blocks.append("User-agent: *\nAllow: /")
    return "\n\n".join(blocks) + f"\n\nSitemap: {SITE_URL}/sitemap.xml\n"


def sitemap_xml(round_no, nav):
    urls = [f"{SITE_URL}/", f"{SITE_URL}/round/{round_no}/"]
    urls += [f"{SITE_URL}/round/{round_no}/{slug}/" for slug, _ in nav]
    items = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f'{items}</urlset>')
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/wc2026 && python3 -m unittest tests.test_site_render.AgentFilesTest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/wc2026 && git add site/render.py tests/test_site_render.py
git commit -m "feat(site): llms.txt, robots.txt, sitemap.xml emitters"
```

---

## Task 10: Build CLI — assemble articles and write dist/

**Files:**
- Create: `site/build.py`

- [ ] **Step 1: Implement the build orchestrator**

Create `site/build.py`:

```python
"""Build the evmax static site for one round into dist/.

Usage: python3 site/build.py --round 3 [--sims 50000] [--out dist] [--url https://evmax.pages.dev]
Run from the repo root.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from core import engine_events, espn, fixtures, research
from site import articles, render


def _kickoffs_for_round(fantasy_round: int) -> dict:
    out = {}
    for f in fixtures.by_round(fantasy_round):
        for team in (f.home, f.away):
            iso = f.kickoff.isoformat()
            if team not in out or iso < out[team]:
                out[team] = iso
    return out


# article slug -> (table columns, chart metric, builder(rows, round) -> entries)
def _article_entries(rows, fantasy_round):
    blow = articles.blowout_teams(fantasy_round)
    return {
        "best-xi":          (["x_points", "price", "ownership_pct"], articles.select_xi(rows, "x_points")),
        "captains":         (["captain_ev", "x_points", "ownership_pct"], articles.rank_captains(rows)[:20]),
        "high-ceiling-xi":  (["ceiling", "x_points", "ownership_pct"], articles.select_xi(rows, "ceiling")),
        "differentials":    (["x_points", "ownership_pct", "price"], articles.differentials(rows)[:20]),
        "best-value-xi":    (["value", "x_points", "price"], articles.select_xi(articles.rank_value(rows), "value")),
        "blowout-transfers":(["x_points", "captain_ev", "price"], articles.blowout_transfers(rows, blow)[:20]),
    }


def build(fantasy_round: int, sims: int, out: str, url: str) -> None:
    render.SITE_URL = url
    generated_at = datetime.now(timezone.utc).isoformat()

    players, _matches = engine_events.simulate_round(
        fantasy_round, sims=sims,
        market_rates=espn.load_player_rates(fantasy_round),
        research=research.load_entries("players", fantasy_round),
        research_weight=0.30)
    means = engine_events.event_means(players)
    samples = {name: ps.goal_samples for name, ps in players.items()}
    meta = articles.load_player_meta()
    kickoffs = _kickoffs_for_round(fantasy_round)
    rows = articles.build_rows(means, samples, meta, kickoffs)

    built = _article_entries(rows, fantasy_round)
    nav = [(slug, articles.ARTICLE_TITLES[slug]) for slug in articles.ARTICLES]

    def w(path, text):
        full = os.path.join(out, path.lstrip("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)

    highlights, latest_index = {}, {}
    for slug, (columns, entries) in built.items():
        title = f"{articles.ARTICLE_TITLES[slug]} — Round {fantasy_round}"
        json_url = f"/api/round/{fantasy_round}/{slug}.json"
        env = render.article_json("fifa_world_cup_fantasy", fantasy_round, slug, title,
                                  generated_at, sims, entries)
        w(json_url, json.dumps(env, ensure_ascii=False, indent=2))
        w(f"/round/{fantasy_round}/{slug}/index.html",
          render.article_page(fantasy_round, slug, title, entries, columns, nav, json_url))
        highlights[slug] = render.summary_sentence(slug, entries)
        latest_index[slug] = json_url

    w(f"/round/{fantasy_round}/index.html", render.hub_page(fantasy_round, nav, highlights))
    w("/index.html", render.hub_page(fantasy_round, nav, highlights))
    w("/api/latest.json", json.dumps(
        {"round": fantasy_round, "generated_at": generated_at, "articles": latest_index},
        ensure_ascii=False, indent=2))
    w("/llms.txt", render.llms_txt(fantasy_round, nav))
    w("/robots.txt", render.robots_txt())
    w("/sitemap.xml", render.sitemap_xml(fantasy_round, nav))
    print(f"Built round {fantasy_round} → {out}/ ({len(rows)} players, {len(built)} articles)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--sims", type=int, default=50_000)
    ap.add_argument("--out", default="dist")
    ap.add_argument("--url", default="https://evmax.pages.dev")
    a = ap.parse_args()
    build(a.round, a.sims, a.out, a.url)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-test the build with a tiny sim count**

Run: `cd ~/wc2026 && python3 site/build.py --round 3 --sims 200 --out /tmp/evmax_smoke`
Expected: prints `Built round 3 → /tmp/evmax_smoke/ (N players, 6 articles)` with N > 50.

- [ ] **Step 3: Verify the output tree and JSON validity**

Run:
```bash
cd ~/wc2026 && find /tmp/evmax_smoke -type f | sort && \
python3 -c "import json; json.load(open('/tmp/evmax_smoke/api/round/3/captains.json')); \
print('captains entries:', len(json.load(open('/tmp/evmax_smoke/api/round/3/captains.json'))['entries']))"
```
Expected: lists `index.html`, `round/3/<6 articles>/index.html`, `api/round/3/<6>.json`, `api/latest.json`, `llms.txt`, `robots.txt`, `sitemap.xml`; prints a non-zero captains entry count.

- [ ] **Step 4: Eyeball one page in a browser**

Run: `open /tmp/evmax_smoke/round/3/captains/index.html`
Expected: headline, a bar chart, and a ranked table render. (Internal `/round/...` links won't resolve from `file://` — that's expected; they work once served.)

- [ ] **Step 5: Commit**

```bash
cd ~/wc2026 && git add site/build.py
git commit -m "feat(site): build CLI assembling all articles into dist/"
```

---

## Task 11: Full production build + Cloudflare Pages deploy

**Files:** none (operational).

- [ ] **Step 1: Run the full suite**

Run: `cd ~/wc2026 && python3 -m unittest discover -s tests -t . -v`
Expected: all tests pass (engine + new site tests).

- [ ] **Step 2: Refresh odds + ownership, then build at full sim count**

Run:
```bash
cd ~/wc2026 && python3 manage.py fifa --round 3 --refresh >/dev/null 2>&1 || true
python3 -c "from core import fifa_api; fifa_api.refresh()"   # refresh ownership snapshot
python3 site/build.py --round 3 --sims 50000 --out dist
```
Expected: `Built round 3 → dist/ (N players, 6 articles)`. (The `manage.py --refresh` updates match odds; the `fifa_api.refresh()` updates the ownership snapshot used by differentials. `players.json` is regenerated by the repo's existing `build_players.py` if ownership looks stale — run it if needed.)

- [ ] **Step 3: Sanity-check headline numbers against the personal model**

Run: `cd ~/wc2026 && python3 manage.py fifa --round 3 | head -20`
Compare the captain-EV leaders to `dist/api/round/3/captains.json`. Expected: the top names overlap sensibly (the public ranking spans all players, so it can include names not in your squad — that's correct).

- [ ] **Step 4: Deploy to Cloudflare Pages**

Option A (no install — dashboard): create a Pages project named `evmax` at dash.cloudflare.com → Pages → "Upload assets", drag the `dist/` folder. Live at `https://evmax.pages.dev`.

Option B (CLI): `npx wrangler pages deploy dist --project-name evmax`
Expected: a `*.pages.dev` URL prints; opening it shows the hub page and all six articles, with `/llms.txt`, `/robots.txt`, `/sitemap.xml`, and `/api/round/3/captains.json` all reachable.

- [ ] **Step 5: Verify agent-surface reachability on the live URL**

Run: `curl -s https://evmax.pages.dev/llms.txt | head && curl -s https://evmax.pages.dev/api/round/3/captains.json | python3 -m json.tool | head`
Expected: `llms.txt` lists the articles; the JSON parses and shows ranked entries.

---

## Self-Review notes

- **Spec coverage:** §2 article set → Tasks 3–5 + build (`_article_entries`); §3 global ranking via engine → Task 2 + Task 10 (build bypasses `model.run`); §4 static `dist/` tree → Task 10; §5 hook/transparency layout → Task 8; §6 JSON shape → Task 6/10; §7 agent files (JSON-LD/llms.txt/robots/sitemap) → Tasks 8–9; §8 generic-over-game → competition string is a parameter in `article_json`/`build` (Holdet reuses by swapping the scoring model + `*_pos`/`*_price`/`*_ownership` fields, a later plan); §9 deploy → Task 11; §10 risks → no betting/affiliate content emitted, ESPN-odds-only data, coverage/ownership-freshness handled by skipping unmatched players + `generated_at`.
- **Deferred per spec (not in this plan):** backtesting harness, Holdet sibling, FPL, accounts/payments, social auto-posting, live updates, LLM-citation testing, scheduling.
- **Type consistency:** the row dict keys (`x_points`, `captain_ev`, `ceiling`, `value`, `ownership_pct`, `kickoff`) are identical across `build_rows`, ranking/selection, `_table`, `_fmt`, and `article_json`. Article slugs come from the single `ARTICLES`/`ARTICLE_TITLES` source in `site/articles.py`.
- **Known v1 limitation:** MID defensive-contribution and some props are modeled estimates (documented in the methodology line); acceptable and disclosed.
