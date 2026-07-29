# FPL Port — Phases 1–2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working FPL order book for a gameweek — FPL data layer, xG-derived player priors, and the FPL scoring model including threshold scoring and rank-within-match bonus.

**Architecture:** New `games/fpl/` module plus narrow generalisation of `core/`. The Monte-Carlo substrate in `core/engine_events.py` is reused, extended with a priors provider, four additive `PlayerSample` fields, and a per-match hook. The match layer stays market-derived from ESPN `eng.1`; the player layer becomes xG-derived from FPL's own API. See `docs/superpowers/specs/2026-07-28-fpl-port-design.md`.

**Tech Stack:** Python 3, stdlib only in `core/` and `games/` (no third-party deps — `urllib.request` for HTTP, `unittest` for tests). Streamlit is dashboard-only and out of scope here.

---

## Context an engineer needs before starting

**Repo layout.** `core/` holds the shared engine (odds math, Monte Carlo, fixtures, research overlay). `games/<name>/` holds one thin layer per fantasy competition — each has `model.py`, `rules.md`, `state.json`. `config.py` holds every tunable. `manage.py` is the CLI dispatcher. Run everything from the repo root.

**Run the test suite:**
```bash
python -m unittest discover -s tests -t .
```
This must stay green throughout. It is the regression gate proving the World Cup track-record grading still works — the WC code is deliberately untouched by this plan.

**The existing game to imitate:** `games/fifa/model.py`. It maps engine output onto FIFA World Cup Fantasy scoring. The FPL model mirrors its shape (`expected_points()`, `ceiling_points()`, `run()`) but with FPL's rules.

**Naming trap:** FPL's API calls goalkeepers `GKP`; this repo's internal vocabulary is `GK`. Map at the `fpl_priors` boundary and use `GK` everywhere inside.

**Timezone trap:** deadlines come from the FPL API's `events[].deadline_time` in UTC. The official rules page renders them in the viewer's local timezone and must never be scraped.

**Cached API responses for tests.** Two live payloads were captured on 2026-07-28. Task 1 saves trimmed versions as test fixtures. Do not add tests that hit the network.

---

## File structure

| File | Responsibility |
|---|---|
| `core/fpl_api.py` (create) | Fetch + parse FPL's three endpoints. Network isolated in `fetch_*`; `parse_*` pure. Caches to `data/fpl/`. |
| `core/fpl_priors.py` (create) | Turn parsed FPL data into `ratings.PlayerPrior` objects. Owns the minutes model, per-90 rate derivation, cold-start fallback. |
| `games/fpl/model.py` (create) | FPL scoring + order book. Knows the scoring table. No HTTP. |
| `games/fpl/rules.md` (create) | Scoring + BPS tables with per-row provenance. |
| `games/fpl/state.json` (create) | Owner's squad snapshot. |
| `games/fpl/__init__.py` (create) | Empty, matching the other game packages. |
| `core/engine_events.py` (modify) | Priors provider, 4 additive `PlayerSample` fields, per-match hook. |
| `core/ratings.py` (modify) | `PlayerPrior` gains `defcon_per90`, `saves_per90`. |
| `core/fixtures.py` (modify) | Gameweek semantics: deadlines, blanks/doubles helpers. |
| `core/espn.py` (modify) | Parameterise the league slug. |
| `config.py` (modify) | `GAMES["fpl"]` entry + FPL dials. |
| `manage.py` (modify) | Add `fpl` to the game list. |
| `tests/fixtures/fpl_bootstrap.json` (create) | Trimmed bootstrap-static. |
| `tests/fixtures/fpl_fixtures.json` (create) | Trimmed fixtures feed. |
| `tests/test_fpl_api.py` (create) | Parse tests. |
| `tests/test_fpl_priors.py` (create) | Prior derivation, gating, fallback. |
| `tests/test_fpl_model.py` (create) | Scoring rows, thresholds, bonus ranking. |
| `tests/test_fixtures_gameweek.py` (create) | Blanks/doubles + deadline, on synthetic fixtures. |

---

# PHASE 1 — Data layer

## Task 1: Capture test fixtures

**Files:**
- Create: `tests/fixtures/fpl_bootstrap.json`
- Create: `tests/fixtures/fpl_fixtures.json`

- [ ] **Step 1: Fetch and trim bootstrap-static**

Run this from the repo root. It keeps all 20 teams, the config blocks, and a hand-picked
slice of players that exercises every code path (a premium forward with history, a
goalkeeper, a defender, an injured player, and a promoted-club player with no PL history).

```bash
python3 - <<'PY'
import json, urllib.request
url = "https://fantasy.premierleague.com/api/bootstrap-static/"
req = urllib.request.Request(url, headers={"User-Agent": "wc2026/1.0"})
with urllib.request.urlopen(req, timeout=40) as r:
    d = json.loads(r.read().decode())

keep_teams = {t["short_name"] for t in d["teams"]}
by_short = {t["id"]: t["short_name"] for t in d["teams"]}

def pick(pred, n):
    return [e for e in d["elements"] if pred(e)][:n]

sel = []
sel += pick(lambda e: e["element_type"] == 4 and e["minutes"] > 2000, 3)   # forwards w/ history
sel += pick(lambda e: e["element_type"] == 1 and e["minutes"] > 1500, 2)   # goalkeepers
sel += pick(lambda e: e["element_type"] == 2 and e["minutes"] > 1500, 3)   # defenders
sel += pick(lambda e: e["element_type"] == 3 and e["minutes"] > 1500, 3)   # midfielders
sel += pick(lambda e: e["status"] != "a", 3)                                # unavailable
sel += pick(lambda e: e["minutes"] == 0, 3)                                # no history at all
seen, elements = set(), []
for e in sel:
    if e["id"] not in seen:
        seen.add(e["id"]); elements.append(e)

out = {k: d[k] for k in ("chips", "game_settings", "game_config", "teams",
                          "element_types", "element_stats", "phases")}
out["events"] = d["events"][:3]
out["elements"] = elements
out["total_players"] = d["total_players"]

with open("tests/fixtures/fpl_bootstrap.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=1)
print("elements kept:", len(elements))
print("teams:", len(out["teams"]), "events:", len(out["events"]))
PY
```

Expected: `elements kept:` between 12 and 17, `teams: 20`, `events: 3`.

- [ ] **Step 2: Fetch and trim the fixtures feed**

```bash
python3 - <<'PY'
import json, urllib.request
url = "https://fantasy.premierleague.com/api/fixtures/"
req = urllib.request.Request(url, headers={"User-Agent": "wc2026/1.0"})
with urllib.request.urlopen(req, timeout=40) as r:
    d = json.loads(r.read().decode())
out = [f for f in d if f.get("event") in (1, 2)]
with open("tests/fixtures/fpl_fixtures.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=1)
print("fixtures kept:", len(out))
PY
```

Expected: `fixtures kept: 20` (10 per gameweek).

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/fpl_bootstrap.json tests/fixtures/fpl_fixtures.json
git commit -m "test(fpl): capture trimmed bootstrap + fixtures payloads as offline fixtures"
```

---

## Task 2: `core/fpl_api.py` — parse teams and events

**Files:**
- Create: `core/fpl_api.py`
- Create: `tests/test_fpl_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_fpl_api.py`:

```python
import json
import os
import unittest

from core import fpl_api

FX = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FX, name), encoding="utf-8") as fh:
        return json.load(fh)


class TestParseTeams(unittest.TestCase):
    def setUp(self):
        self.raw = _load("fpl_bootstrap.json")

    def test_parse_teams_maps_id_to_short_name(self):
        teams = fpl_api.parse_teams(self.raw)
        self.assertEqual(len(teams), 20)
        # every value is a short code, every key an int id
        self.assertTrue(all(isinstance(k, int) for k in teams))
        self.assertIn("LIV", teams.values())


class TestParseEvents(unittest.TestCase):
    def setUp(self):
        self.raw = _load("fpl_bootstrap.json")

    def test_parse_events_returns_utc_deadlines(self):
        events = fpl_api.parse_events(self.raw)
        gw1 = events[1]
        self.assertEqual(gw1["id"], 1)
        # deadline is timezone-aware UTC, never naive
        self.assertIsNotNone(gw1["deadline"].tzinfo)
        self.assertEqual(gw1["deadline"].utcoffset().total_seconds(), 0)

    def test_gw1_deadline_is_the_known_value(self):
        events = fpl_api.parse_events(self.raw)
        self.assertEqual(events[1]["deadline"].isoformat(), "2026-08-21T17:30:00+00:00")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_fpl_api -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.fpl_api'`

- [ ] **Step 3: Write minimal implementation**

Create `core/fpl_api.py`:

```python
"""Fantasy Premier League official API client (free, no key).

Three endpoints:
  bootstrap-static  -> teams, gameweek events (deadlines), all players with last
                       season's totals and per-90 rates, plus the scoring config.
  fixtures          -> all 380 fixtures with gameweek assignment and kickoff.
  element-summary/N -> one player's per-fixture history + past seasons.

Network lives in the fetch_* functions; every parse_* is pure and unit-tested
against saved payloads in tests/fixtures/. Mirrors core/espn.py's split.

Deadlines are ALWAYS read from here in UTC. The official rules page renders them
in the viewer's local timezone and must never be scraped.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone

BASE = "https://fantasy.premierleague.com/api"
BOOTSTRAP = f"{BASE}/bootstrap-static/"
FIXTURES = f"{BASE}/fixtures/"
ELEMENT_SUMMARY = f"{BASE}/element-summary/{{element_id}}/"

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_HERE, "data", "fpl")

USER_AGENT = "wc2026-engine/1.0"

# FPL element_type -> this repo's internal position vocabulary.
# FPL says GKP; the repo says GK. Map here, once, at the boundary.
POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def _get_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --- network ---------------------------------------------------------------

def fetch_bootstrap() -> dict:
    return _get_json(BOOTSTRAP)


def fetch_fixtures() -> list:
    return _get_json(FIXTURES)


def fetch_element_summary(element_id: int) -> dict:
    return _get_json(ELEMENT_SUMMARY.format(element_id=element_id))


# --- pure parsers ---------------------------------------------------------

def _parse_utc(s: str) -> datetime:
    """Parse an FPL ISO-8601 timestamp to a UTC-aware datetime (py3.9-safe)."""
    s = s.replace("Z", "+00:00")
    d = datetime.fromisoformat(s)
    return d.astimezone(timezone.utc) if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_teams(raw: dict) -> dict[int, str]:
    """{team_id: short_name}, e.g. {14: 'LIV'}."""
    return {t["id"]: t["short_name"] for t in raw.get("teams", [])}


def parse_events(raw: dict) -> dict[int, dict]:
    """{gw_id: {id, name, deadline (UTC-aware), finished}}."""
    out = {}
    for e in raw.get("events", []):
        out[e["id"]] = {
            "id": e["id"],
            "name": e.get("name", f"Gameweek {e['id']}"),
            "deadline": _parse_utc(e["deadline_time"]),
            "finished": bool(e.get("finished")),
        }
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_fpl_api -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add core/fpl_api.py tests/test_fpl_api.py
git commit -m "feat(fpl): FPL API client with team + gameweek-deadline parsers"
```

---

## Task 3: `core/fpl_api.py` — parse players

**Files:**
- Modify: `core/fpl_api.py`
- Modify: `tests/test_fpl_api.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fpl_api.py`:

```python
class TestParsePlayers(unittest.TestCase):
    def setUp(self):
        self.raw = _load("fpl_bootstrap.json")
        self.players = fpl_api.parse_players(self.raw)

    def test_positions_use_repo_vocabulary_not_fpl(self):
        positions = {p["position"] for p in self.players}
        self.assertTrue(positions <= {"GK", "DEF", "MID", "FWD"})
        self.assertNotIn("GKP", positions)

    def test_price_is_in_millions(self):
        # now_cost is tenths of a million in the feed; we expose millions
        for p in self.players:
            self.assertGreaterEqual(p["price"], 3.5)
            self.assertLessEqual(p["price"], 20.0)

    def test_team_is_short_code(self):
        teams = set(fpl_api.parse_teams(self.raw).values())
        for p in self.players:
            self.assertIn(p["team"], teams)

    def test_per90_rates_present_and_numeric(self):
        for p in self.players:
            self.assertIsInstance(p["xg_per90"], float)
            self.assertIsInstance(p["xa_per90"], float)
            self.assertGreaterEqual(p["xg_per90"], 0.0)

    def test_availability_fields_carried_through(self):
        by_status = {p["status"] for p in self.players}
        self.assertIn("a", by_status)
        for p in self.players:
            self.assertIn("chance_of_playing", p)

    def test_pen_taker_flag_from_penalties_order(self):
        # penalties_order == 1 is the designated taker
        flags = {p["name"]: p["pen_taker"] for p in self.players}
        self.assertIn(True, flags.values())


class TestScoringConfig(unittest.TestCase):
    def setUp(self):
        self.raw = _load("fpl_bootstrap.json")

    def test_parse_scoring_reads_goal_values_by_position(self):
        sc = fpl_api.parse_scoring(self.raw)
        # 2026/27: a goalkeeper goal is worth 10
        self.assertEqual(sc["goals_scored"]["GK"], 10)
        self.assertEqual(sc["goals_scored"]["DEF"], 6)
        self.assertEqual(sc["goals_scored"]["MID"], 5)
        self.assertEqual(sc["goals_scored"]["FWD"], 4)

    def test_parse_scoring_maps_gkp_key_to_gk(self):
        sc = fpl_api.parse_scoring(self.raw)
        self.assertNotIn("GKP", sc["goals_scored"])

    def test_parse_squad_rules(self):
        r = fpl_api.parse_squad_rules(self.raw)
        self.assertEqual(r["squad_size"], 15)
        self.assertEqual(r["squad_play"], 11)
        self.assertEqual(r["team_limit"], 3)
        self.assertEqual(r["budget"], 100.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_fpl_api -v`
Expected: FAIL — `AttributeError: module 'core.fpl_api' has no attribute 'parse_players'`

- [ ] **Step 3: Write minimal implementation**

Append to `core/fpl_api.py`:

```python
def _f(value, default: float = 0.0) -> float:
    """FPL returns several numeric fields as strings ('25.50'). Coerce safely."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_players(raw: dict) -> list[dict]:
    """Flatten `elements` into the fields the prior builder needs.

    NOTE on preseason: bootstrap's per-player totals carry LAST season's numbers
    until the new season starts, so xg_per90/minutes/starts are populated on day
    one. Players with minutes == 0 have no Premier League history at all (promoted
    clubs, foreign signings) and are handled by the cold-start fallback in
    core/fpl_priors.
    """
    teams = parse_teams(raw)
    out = []
    for e in raw.get("elements", []):
        out.append({
            "id": e["id"],
            "name": e["web_name"],
            "full_name": f"{e.get('first_name', '')} {e.get('second_name', '')}".strip(),
            "team": teams.get(e["team"], "???"),
            "position": POSITIONS.get(e["element_type"], "MID"),
            "price": e["now_cost"] / 10.0,
            "ownership": _f(e.get("selected_by_percent")),
            "status": e.get("status", "a"),
            "chance_of_playing": e.get("chance_of_playing_next_round"),
            "news": e.get("news", ""),
            "minutes": e.get("minutes", 0),
            "starts": e.get("starts", 0),
            "xg_per90": _f(e.get("expected_goals_per_90")),
            "xa_per90": _f(e.get("expected_assists_per_90")),
            "saves_per90": _f(e.get("saves_per_90")),
            "defcon_per90": _f(e.get("defensive_contribution_per_90")),
            "bps": e.get("bps", 0),
            "ep_next": _f(e.get("ep_next")),
            "pen_taker": e.get("penalties_order") == 1,
        })
    return out


def parse_scoring(raw: dict) -> dict:
    """The scoring table from game_config, with GKP keys remapped to GK.

    WARNING: this block carries UNIT values only. `saves: 1` means one point per
    THREE saves and `goals_conceded: -1` means minus one per TWO conceded. The
    divisors are not in the feed — they are pinned in games/fpl/model.py from the
    official rules page. Reading this block literally mis-prices every goalkeeper.
    """
    sc = dict(raw.get("game_config", {}).get("scoring", {}))
    for key, value in list(sc.items()):
        if isinstance(value, dict) and "GKP" in value:
            remapped = {("GK" if k == "GKP" else k): v for k, v in value.items()}
            sc[key] = remapped
    return sc


def parse_squad_rules(raw: dict) -> dict:
    r = raw.get("game_config", {}).get("rules", {}) or raw.get("game_settings", {})
    multiplier = r.get("ui_currency_multiplier", 10)
    return {
        "squad_size": r.get("squad_squadsize", 15),
        "squad_play": r.get("squad_squadplay", 11),
        "team_limit": r.get("squad_team_limit", 3),
        "budget": r.get("squad_total_spend", 1000) / multiplier,
        "max_extra_free_transfers": r.get("max_extra_free_transfers", 4),
        "sell_on_fee": r.get("transfers_sell_on_fee", 0.5),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_fpl_api -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add core/fpl_api.py tests/test_fpl_api.py
git commit -m "feat(fpl): player, scoring-table and squad-rule parsers"
```

---

## Task 4: `core/fpl_api.py` — parse fixtures and cache to disk

**Files:**
- Modify: `core/fpl_api.py`
- Modify: `tests/test_fpl_api.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fpl_api.py`:

```python
class TestParseFixtures(unittest.TestCase):
    def setUp(self):
        self.raw_fx = _load("fpl_fixtures.json")
        self.teams = fpl_api.parse_teams(_load("fpl_bootstrap.json"))

    def test_parse_fixtures_shape(self):
        rows = fpl_api.parse_fixtures(self.raw_fx, self.teams)
        self.assertEqual(len(rows), 20)
        r = rows[0]
        for key in ("match_id", "home", "away", "kickoff_utc", "fantasy_round", "stage"):
            self.assertIn(key, r)

    def test_stage_is_gw_and_round_is_the_gameweek(self):
        rows = fpl_api.parse_fixtures(self.raw_fx, self.teams)
        self.assertEqual({r["stage"] for r in rows}, {"GW"})
        self.assertEqual({r["fantasy_round"] for r in rows}, {1, 2})

    def test_home_and_away_are_short_codes(self):
        rows = fpl_api.parse_fixtures(self.raw_fx, self.teams)
        codes = set(self.teams.values())
        for r in rows:
            self.assertIn(r["home"], codes)
            self.assertIn(r["away"], codes)

    def test_unscheduled_fixtures_are_skipped(self):
        # a fixture with event=None is not yet assigned to a gameweek
        raw = self.raw_fx + [{"id": 999, "event": None, "team_h": 1, "team_a": 2,
                              "kickoff_time": None}]
        rows = fpl_api.parse_fixtures(raw, self.teams)
        self.assertEqual(len(rows), 20)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_fpl_api -v`
Expected: FAIL — `AttributeError: module 'core.fpl_api' has no attribute 'parse_fixtures'`

- [ ] **Step 3: Write minimal implementation**

Append to `core/fpl_api.py`:

```python
def parse_fixtures(raw: list, teams: dict[int, str]) -> list[dict]:
    """Flatten the fixtures feed into schedule rows.

    Fixtures with `event: None` are not yet assigned to a gameweek (postponed or
    awaiting a cup outcome) and are skipped — they are the mechanism by which
    blanks and doubles appear later in the season.
    """
    out = []
    for f in raw:
        gw = f.get("event")
        if gw is None:
            continue
        out.append({
            "match_id": str(f["id"]),
            "home": teams.get(f["team_h"], "???"),
            "away": teams.get(f["team_a"], "???"),
            "kickoff_utc": f.get("kickoff_time"),
            "fantasy_round": gw,
            "stage": "GW",
        })
    return out


def write_cache(name: str, payload) -> str:
    """Persist a raw payload under data/fpl/ so models can run offline."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    return path


def read_cache(name: str):
    path = os.path.join(DATA_DIR, f"{name}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def refresh(write: bool = True) -> tuple[dict, list]:
    """Fetch bootstrap + fixtures and cache them. Returns the raw payloads."""
    boot, fx = fetch_bootstrap(), fetch_fixtures()
    if write:
        write_cache("bootstrap", boot)
        write_cache("fixtures", fx)
    return boot, fx
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_fpl_api -v`
Expected: PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add core/fpl_api.py tests/test_fpl_api.py
git commit -m "feat(fpl): fixture parser + data/fpl cache read/write"
```

---

## Task 5: Gameweek semantics in `core/fixtures.py`

**Files:**
- Modify: `core/fixtures.py`
- Create: `tests/test_fixtures_gameweek.py`

Blanks and doubles do not exist in the live feed yet — all 380 fixtures are currently 10 per gameweek. They emerge in-season from cup progression, so these tests build **synthetic** fixtures. This is the only way to get the behaviour right before data exhibits it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fixtures_gameweek.py`:

```python
import unittest
from datetime import datetime, timezone

from core import fixtures


def _fx(match_id, home, away, gw, hour=15):
    return fixtures.Fixture(
        match_id=match_id, home=home, away=away,
        kickoff=datetime(2026, 8, 22, hour, 0, tzinfo=timezone.utc),
        stage="GW", fantasy_round=gw, neutral=False,
    )


class TestBlanksAndDoubles(unittest.TestCase):
    """A team can play 0 or 2 times in one gameweek. Callers must not assume 1."""

    def setUp(self):
        # GW7: LIV plays twice (double), TOT plays not at all (blank).
        self.added = [
            _fx("m1", "LIV", "ARS", 7, 12),
            _fx("m2", "LIV", "CHE", 7, 17),
            _fx("m3", "MCI", "NEW", 7, 15),
        ]
        fixtures.SCHEDULE.extend(self.added)
        self.addCleanup(lambda: [fixtures.SCHEDULE.remove(f) for f in self.added])

    def test_double_gameweek_returns_both_fixtures(self):
        self.assertEqual(len(fixtures.fixtures_for_team("LIV", 7)), 2)

    def test_blank_gameweek_returns_empty_list(self):
        self.assertEqual(fixtures.fixtures_for_team("TOT", 7), [])

    def test_teams_with_blank_lists_the_non_players(self):
        playing = {"LIV", "ARS", "CHE", "MCI", "NEW"}
        blanks = fixtures.teams_with_blank(7, all_teams=playing | {"TOT", "EVE"})
        self.assertEqual(blanks, {"TOT", "EVE"})

    def test_teams_with_double_lists_the_twice_players(self):
        self.assertEqual(fixtures.teams_with_double(7), {"LIV"})

    def test_fixture_count_by_team(self):
        counts = fixtures.fixture_count_by_team(7)
        self.assertEqual(counts["LIV"], 2)
        self.assertEqual(counts["MCI"], 1)
        self.assertNotIn("TOT", counts)


class TestGameweekDeadline(unittest.TestCase):
    def tearDown(self):
        fixtures.DEADLINES.clear()

    def test_lock_time_prefers_the_registered_deadline_over_first_kickoff(self):
        added = [_fx("m9", "LIV", "ARS", 9, 18)]
        fixtures.SCHEDULE.extend(added)
        self.addCleanup(lambda: [fixtures.SCHEDULE.remove(f) for f in added])

        deadline = datetime(2026, 8, 21, 17, 30, tzinfo=timezone.utc)
        fixtures.set_deadline(9, deadline)
        # first kickoff is 18:00 the next day; the deadline is what locks the round
        self.assertEqual(fixtures.round_lock_time(9), deadline)

    def test_lock_time_falls_back_to_first_kickoff_when_no_deadline_known(self):
        added = [_fx("m10", "LIV", "ARS", 10, 13)]
        fixtures.SCHEDULE.extend(added)
        self.addCleanup(lambda: [fixtures.SCHEDULE.remove(f) for f in added])
        self.assertEqual(fixtures.round_lock_time(10).hour, 13)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_fixtures_gameweek -v`
Expected: FAIL — `AttributeError: module 'core.fixtures' has no attribute 'teams_with_blank'`

- [ ] **Step 3: Write minimal implementation**

In `core/fixtures.py`, add `"GW"` to the `STAGES` list so FPL rows validate:

```python
STAGES = [
    "GROUP_MD1", "GROUP_MD2", "GROUP_MD3",
    "R32", "R16", "QF", "SF", "BRONZE", "FINAL",
    "GW",   # FPL gameweek
]
```

Then replace the existing `round_lock_time` function with the block below, and append the
new helpers at the end of the file:

```python
# Registered gameweek deadlines, {fantasy_round: UTC-aware datetime}. FPL locks on a
# published deadline that PRECEDES the first kickoff (GW1: 17:30Z deadline, evening
# kickoff), so lock logic must prefer this over min(kickoff). Populated from
# core.fpl_api.parse_events — never scraped from the rules page, which localises times.
DEADLINES: dict = {}


def set_deadline(fantasy_round: int, when: datetime) -> None:
    DEADLINES[fantasy_round] = when


def round_lock_time(fantasy_round: int) -> datetime | None:
    """When a round locks: the registered deadline if known, else first kickoff.

    The WC had no separate deadline, so first kickoff was the lock. FPL publishes
    one, and the frozen-at-lock rule depends on using it.
    """
    if fantasy_round in DEADLINES:
        return DEADLINES[fantasy_round]
    fx = by_round(fantasy_round)
    return min((f.kickoff for f in fx), default=None)


def fixture_count_by_team(fantasy_round: int) -> dict:
    """{team: number of fixtures} for a round. Absent teams have a blank."""
    counts: dict = {}
    for f in by_round(fantasy_round):
        counts[f.home] = counts.get(f.home, 0) + 1
        counts[f.away] = counts.get(f.away, 0) + 1
    return counts


def teams_with_double(fantasy_round: int) -> set:
    """Teams playing more than once — a 'double gameweek'."""
    return {t for t, c in fixture_count_by_team(fantasy_round).items() if c > 1}


def teams_with_blank(fantasy_round: int, all_teams) -> set:
    """Teams in `all_teams` with no fixture — a 'blank gameweek'.

    Requires the league's full team set, because a team with no fixture is by
    definition absent from the schedule rows and cannot be inferred from them.
    """
    return set(all_teams) - set(fixture_count_by_team(fantasy_round))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_fixtures_gameweek -v`
Expected: PASS (7 tests)

Then confirm nothing regressed:

Run: `python -m unittest discover -s tests -t .`
Expected: OK — the pre-existing test count, all passing

- [ ] **Step 5: Commit**

```bash
git add core/fixtures.py tests/test_fixtures_gameweek.py
git commit -m "feat(fixtures): gameweek semantics — deadlines, blanks and doubles"
```

---

## Task 6: Parameterise the league slug in `core/espn.py`

**Files:**
- Modify: `core/espn.py:32-33`
- Modify: `tests/test_espn.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_espn.py`:

```python
class TestLeagueParameterisation(unittest.TestCase):
    def test_default_league_is_the_world_cup(self):
        self.assertEqual(espn.league_slug(), "fifa.world")

    def test_scoreboard_url_follows_the_configured_league(self):
        with mock.patch.object(config, "ESPN_LEAGUE", "eng.1"):
            self.assertIn("/soccer/eng.1/scoreboard", espn.scoreboard_url())

    def test_core_url_follows_the_configured_league(self):
        with mock.patch.object(config, "ESPN_LEAGUE", "eng.1"):
            self.assertIn("/leagues/eng.1", espn.core_url())

    def test_world_cup_urls_unchanged_by_default(self):
        self.assertIn("/soccer/fifa.world/scoreboard", espn.scoreboard_url())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_espn -v`
Expected: FAIL — `AttributeError: module 'core.espn' has no attribute 'league_slug'`

- [ ] **Step 3: Write minimal implementation**

In `config.py`, add near the other odds settings:

```python
# Which ESPN soccer league the odds client reads. "fifa.world" = 2026 World Cup,
# "eng.1" = Premier League. ESPN carries match odds (1X2 + totals) for both, but
# NO player-level props for eng.1 — verified 2026-07-28, all 172 prop markets on a
# sampled GW1 fixture were match-level. FPL player differentiation therefore comes
# from core/fpl_priors (xG-derived), not from props.
ESPN_LEAGUE = "fifa.world"
```

In `core/espn.py`, replace the two module-level URL constants with functions. Keep the
old names as aliases so nothing else in the repo breaks:

```python
_SCOREBOARD_TMPL = "https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard"
_CORE_TMPL = "https://sports.core.api.espn.com/v2/sports/soccer/leagues/{league}"
DRAFTKINGS = 100


def league_slug() -> str:
    return getattr(config, "ESPN_LEAGUE", "fifa.world")


def scoreboard_url() -> str:
    return _SCOREBOARD_TMPL.format(league=league_slug())


def core_url() -> str:
    return _CORE_TMPL.format(league=league_slug())
```

Then replace every use of the old `SCOREBOARD` and `CORE` constants in this file with
`scoreboard_url()` and `core_url()`. Find them with:

```bash
grep -n "SCOREBOARD\|\bCORE\b" core/espn.py
```

There are two call sites: `fetch_scoreboard` uses `SCOREBOARD`, and `fetch_propbets`
builds its base from `CORE`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_espn -v`
Expected: PASS

Run: `python -m unittest discover -s tests -t .`
Expected: OK — no regressions

- [ ] **Step 5: Commit**

```bash
git add core/espn.py config.py tests/test_espn.py
git commit -m "refactor(espn): parameterise the league slug via config.ESPN_LEAGUE"
```

---

## Task 7: `PlayerPrior` gains the FPL rate fields

**Files:**
- Modify: `core/ratings.py:45-61`
- Create: `tests/test_fpl_priors.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_fpl_priors.py`:

```python
import unittest

from core import ratings


class TestPlayerPriorNewFields(unittest.TestCase):
    def test_new_fields_default_to_zero(self):
        p = ratings.PlayerPrior(name="X", team="LIV", position="DEF")
        self.assertEqual(p.defcon_per90, 0.0)
        self.assertEqual(p.saves_per90, 0.0)

    def test_new_fields_are_settable(self):
        p = ratings.PlayerPrior(name="X", team="LIV", position="GK", saves_per90=3.1)
        self.assertAlmostEqual(p.saves_per90, 3.1)

    def test_existing_construction_is_unaffected(self):
        # WC code constructs PlayerPrior positionally and by keyword; both must still work
        p = ratings.PlayerPrior("Y", "Spain", "FWD", 0.9, 80, 0.3, 0.2, 1.5, True)
        self.assertTrue(p.pen_taker)
        self.assertAlmostEqual(p.sot_per90, 1.5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_fpl_priors -v`
Expected: FAIL — `AttributeError: 'PlayerPrior' object has no attribute 'defcon_per90'`

- [ ] **Step 3: Write minimal implementation**

In `core/ratings.py`, extend the dataclass. The new fields go **last** so positional
construction in existing WC code keeps working:

```python
@dataclass
class PlayerPrior:
    """Per-player priors used to distribute a team's simulated match output.

    goal_share / assist_share are fractions of the team's goals/assists this player
    is expected to take when on the pitch. Shares across a squad need not sum to 1
    (the engine normalises among players who are on the pitch in a given sim).
    """

    name: str
    team: str
    position: str            # GK / DEF / MID / FWD  (FIFA-style; see holdet quirks)
    start_prob: float = 0.8  # probability of starting a given match
    exp_minutes: float = 75  # expected minutes when in the squad
    goal_share: float = 0.0
    assist_share: float = 0.0
    sot_per90: float = 0.8   # shots on target per 90, for holdet SoT scoring
    pen_taker: bool = False
    # FPL-only rate fields. Zero for World Cup priors, which don't model them.
    # defcon_per90 counts CBIT for defenders, CBIRT for midfielders and forwards
    # (the two DefCon stat sets differ by position); saves_per90 is GK-only.
    defcon_per90: float = 0.0
    saves_per90: float = 0.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_fpl_priors -v`
Expected: PASS (3 tests)

Run: `python -m unittest discover -s tests -t .`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add core/ratings.py tests/test_fpl_priors.py
git commit -m "feat(ratings): PlayerPrior gains defcon_per90 and saves_per90"
```

---

## Task 8: `core/fpl_priors.py` — availability gating

**Files:**
- Create: `core/fpl_priors.py`
- Modify: `tests/test_fpl_priors.py`

FPL publishes availability directly, which the World Cup never had. This is the single
biggest accuracy lever in the port (STRATEGY.md §9 lists the crude minutes model as the top
engine weakness), so it gets its own task and its own tests.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fpl_priors.py`:

```python
from core import fpl_priors


def _player(**kw):
    base = {
        "id": 1, "name": "Test", "full_name": "Test Player", "team": "LIV",
        "position": "MID", "price": 7.0, "ownership": 5.0, "status": "a",
        "chance_of_playing": None, "news": "", "minutes": 2700, "starts": 30,
        "xg_per90": 0.4, "xa_per90": 0.2, "saves_per90": 0.0,
        "defcon_per90": 4.0, "bps": 600, "ep_next": 5.0, "pen_taker": False,
    }
    base.update(kw)
    return base


class TestAvailabilityGating(unittest.TestCase):
    def test_injured_player_cannot_start(self):
        self.assertEqual(fpl_priors.availability_factor(_player(status="i")), 0.0)

    def test_suspended_player_cannot_start(self):
        self.assertEqual(fpl_priors.availability_factor(_player(status="s")), 0.0)

    def test_unavailable_player_cannot_start(self):
        self.assertEqual(fpl_priors.availability_factor(_player(status="u")), 0.0)

    def test_available_player_is_ungated(self):
        self.assertEqual(fpl_priors.availability_factor(_player(status="a")), 1.0)

    def test_doubtful_player_is_scaled_by_chance_of_playing(self):
        p = _player(status="d", chance_of_playing=25)
        self.assertAlmostEqual(fpl_priors.availability_factor(p), 0.25)

    def test_doubtful_without_a_percentage_is_treated_as_a_coin_flip(self):
        p = _player(status="d", chance_of_playing=None)
        self.assertAlmostEqual(fpl_priors.availability_factor(p), 0.5)

    def test_chance_of_playing_zero_gates_even_an_available_status(self):
        # FPL sometimes leaves status 'a' while chance_of_playing is 0
        p = _player(status="a", chance_of_playing=0)
        self.assertEqual(fpl_priors.availability_factor(p), 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_fpl_priors -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.fpl_priors'`

- [ ] **Step 3: Write minimal implementation**

Create `core/fpl_priors.py`:

```python
"""Turn FPL API data into engine priors.

This is the ONLY place FPL's field names become `ratings.PlayerPrior`. It owns:
  - the minutes model (start probability + expected minutes)
  - per-90 rate derivation (xG/xA -> goal/assist share, DefCon, saves)
  - the cold-start fallback for players with no Premier League history

It knows nothing about scoring (that is games/fpl/model.py) and nothing about HTTP
(that is core/fpl_api.py).

Why xG-derived rather than market-derived: ESPN carries no player-level props for
eng.1 (verified 2026-07-28), so the World Cup's anytime-goalscorer path is empty at
build time. FPL's own feed ships last season's per-90 rates instead, which slot into
the engine's existing `prior_share` blend slot. If props ever appear, the engine's
`market_rate` path lights up with no change here.
"""

from __future__ import annotations

from . import ratings

# FPL status codes: a=available, d=doubtful, i=injured, s=suspended, u=unavailable.
_CANNOT_PLAY = {"i", "s", "u"}


def availability_factor(player: dict) -> float:
    """Multiplier on start probability from FPL's own availability fields.

    Hard-gates unavailable players to zero. Scales the doubtful. A `chance_of_playing`
    of 0 gates regardless of status, because FPL sometimes leaves status at 'a' while
    the percentage has already dropped to 0.
    """
    chance = player.get("chance_of_playing")
    if chance is not None:
        return max(0.0, min(1.0, chance / 100.0))
    if player.get("status") in _CANNOT_PLAY:
        return 0.0
    if player.get("status") == "d":
        return 0.5   # doubtful with no published percentage
    return 1.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_fpl_priors -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add core/fpl_priors.py tests/test_fpl_priors.py
git commit -m "feat(fpl): availability gating from FPL status + chance_of_playing"
```

---

## Task 9: `core/fpl_priors.py` — minutes model

**Files:**
- Modify: `core/fpl_priors.py`
- Modify: `tests/test_fpl_priors.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fpl_priors.py`:

```python
class TestMinutesModel(unittest.TestCase):
    def test_nailed_starter_has_high_start_probability(self):
        # 34 starts from a 38-game season
        p = _player(minutes=3000, starts=34)
        sp, _mins = fpl_priors.minutes_model(p, team_matches=38)
        self.assertGreater(sp, 0.85)

    def test_rotation_player_has_middling_start_probability(self):
        p = _player(minutes=1400, starts=15)
        sp, _mins = fpl_priors.minutes_model(p, team_matches=38)
        self.assertGreater(sp, 0.3)
        self.assertLess(sp, 0.6)

    def test_expected_minutes_reflect_minutes_per_start(self):
        p = _player(minutes=2700, starts=30)   # 90 per start
        _sp, mins = fpl_priors.minutes_model(p, team_matches=38)
        self.assertGreater(mins, 80)
        self.assertLessEqual(mins, 90)

    def test_substitute_gets_low_expected_minutes(self):
        p = _player(minutes=450, starts=1)      # cameos
        _sp, mins = fpl_priors.minutes_model(p, team_matches=38)
        self.assertLess(mins, 60)

    def test_injury_gates_start_probability_to_zero(self):
        p = _player(minutes=3000, starts=34, status="i")
        sp, _mins = fpl_priors.minutes_model(p, team_matches=38)
        self.assertEqual(sp, 0.0)

    def test_no_history_falls_back_without_dividing_by_zero(self):
        p = _player(minutes=0, starts=0)
        sp, mins = fpl_priors.minutes_model(p, team_matches=38)
        self.assertGreaterEqual(sp, 0.0)
        self.assertGreater(mins, 0.0)

    def test_start_probability_never_exceeds_one(self):
        p = _player(minutes=3420, starts=38)
        sp, _mins = fpl_priors.minutes_model(p, team_matches=38)
        self.assertLessEqual(sp, 1.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_fpl_priors -v`
Expected: FAIL — `AttributeError: module 'core.fpl_priors' has no attribute 'minutes_model'`

- [ ] **Step 3: Write minimal implementation**

Append to `core/fpl_priors.py`:

```python
# Fallback expected minutes when a player has no history to measure.
_DEFAULT_EXP_MINUTES = 70.0
_DEFAULT_START_PROB = 0.25   # unknown player: assume a squad role, not a starter


def minutes_model(player: dict, team_matches: int) -> tuple[float, float]:
    """(start_prob, exp_minutes) for one player.

    start_prob is the observed start rate over `team_matches`, then multiplied by
    FPL's availability signal. exp_minutes is minutes-per-start, which separates a
    90-minute nailed starter from a player who starts but is routinely withdrawn,
    and drops toward a cameo figure for players who mostly come off the bench.

    `team_matches` is how many matches the sample covers — 38 for a full prior
    season, or matches played so far once the new season is under way.
    """
    starts = player.get("starts") or 0
    minutes = player.get("minutes") or 0
    gate = availability_factor(player)

    if team_matches <= 0 or (starts == 0 and minutes == 0):
        return _DEFAULT_START_PROB * gate, _DEFAULT_EXP_MINUTES

    start_rate = min(1.0, starts / float(team_matches))

    if starts > 0:
        exp_minutes = min(90.0, minutes / float(starts))
    else:
        # Never started in the sample: a substitute. Spread the minutes over the
        # appearances we can infer, floored so the sim still gives him some time.
        exp_minutes = max(15.0, min(59.0, minutes / float(team_matches)))

    return start_rate * gate, exp_minutes
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_fpl_priors -v`
Expected: PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add core/fpl_priors.py tests/test_fpl_priors.py
git commit -m "feat(fpl): minutes model — start rate x availability, minutes per start"
```

---

## Task 10: `core/fpl_priors.py` — rate derivation and cold-start fallback

**Files:**
- Modify: `core/fpl_priors.py`
- Modify: `config.py`
- Modify: `tests/test_fpl_priors.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fpl_priors.py`:

```python
class TestColdStartFallback(unittest.TestCase):
    def test_player_with_history_does_not_use_the_fallback(self):
        p = _player(minutes=2700, xg_per90=0.55)
        self.assertFalse(fpl_priors.needs_cold_start(p))

    def test_player_with_no_minutes_uses_the_fallback(self):
        self.assertTrue(fpl_priors.needs_cold_start(_player(minutes=0, starts=0)))

    def test_fallback_rate_scales_with_price(self):
        cheap = fpl_priors.price_prior_xg(_player(price=4.5, position="FWD"))
        dear = fpl_priors.price_prior_xg(_player(price=11.0, position="FWD"))
        self.assertGreater(dear, cheap)

    def test_fallback_rate_respects_position(self):
        fwd = fpl_priors.price_prior_xg(_player(price=7.0, position="FWD"))
        dfn = fpl_priors.price_prior_xg(_player(price=7.0, position="DEF"))
        self.assertGreater(fwd, dfn)

    def test_goalkeeper_fallback_expects_no_goals(self):
        self.assertEqual(fpl_priors.price_prior_xg(_player(price=5.5, position="GK")), 0.0)


class TestBuildPriors(unittest.TestCase):
    def setUp(self):
        self.players = [
            _player(id=1, name="Striker", position="FWD", team="LIV",
                    xg_per90=0.8, xa_per90=0.2, minutes=2700, starts=30),
            _player(id=2, name="Winger", position="MID", team="LIV",
                    xg_per90=0.3, xa_per90=0.4, minutes=2400, starts=27),
            _player(id=3, name="Keeper", position="GK", team="LIV",
                    xg_per90=0.0, xa_per90=0.0, saves_per90=2.8,
                    minutes=3420, starts=38),
            _player(id=4, name="Newboy", position="FWD", team="COV",
                    xg_per90=0.0, xa_per90=0.0, minutes=0, starts=0, price=6.0),
        ]

    def test_returns_player_prior_objects_keyed_by_team(self):
        by_team = fpl_priors.build(self.players, team_matches=38)
        self.assertIn("LIV", by_team)
        self.assertEqual(len(by_team["LIV"]), 3)
        self.assertIsInstance(by_team["LIV"][0], ratings.PlayerPrior)

    def test_goal_share_is_normalised_within_the_club(self):
        by_team = fpl_priors.build(self.players, team_matches=38)
        shares = {p.name: p.goal_share for p in by_team["LIV"]}
        # the striker out-shoots the winger, and both are fractions
        self.assertGreater(shares["Striker"], shares["Winger"])
        self.assertLess(shares["Striker"], 1.0)

    def test_goalkeeper_carries_saves_rate_and_no_goal_share(self):
        by_team = fpl_priors.build(self.players, team_matches=38)
        gk = next(p for p in by_team["LIV"] if p.position == "GK")
        self.assertAlmostEqual(gk.saves_per90, 2.8)
        self.assertEqual(gk.goal_share, 0.0)

    def test_defcon_rate_carried_onto_the_prior(self):
        by_team = fpl_priors.build(self.players, team_matches=38)
        mid = next(p for p in by_team["LIV"] if p.name == "Winger")
        self.assertAlmostEqual(mid.defcon_per90, 4.0)

    def test_cold_start_player_still_gets_a_usable_prior(self):
        by_team = fpl_priors.build(self.players, team_matches=38)
        newboy = by_team["COV"][0]
        self.assertGreater(newboy.goal_share, 0.0)

    def test_cold_start_players_are_reported_for_preflight(self):
        _by_team, flagged = fpl_priors.build_with_flags(self.players, team_matches=38)
        self.assertEqual([f["name"] for f in flagged], ["Newboy"])
        self.assertEqual(flagged[0]["reason"], "no_pl_history")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_fpl_priors -v`
Expected: FAIL — `AttributeError: module 'core.fpl_priors' has no attribute 'needs_cold_start'`

- [ ] **Step 3: Add the config dials**

In `config.py`, add a new section:

```python
# ---------------------------------------------------------------------------
# FPL priors
# ---------------------------------------------------------------------------
# How fast in-season per-90 rates displace last season's. Higher = trust the new
# season sooner. Set deliberately high for 2026/27: eight new managers, three
# British-record transfers, Salah gone from the league and three promoted clubs
# make last season's rates weaker priors than in a normal year. This is a
# judgement call, not a measured value — revisit once GW1-5 data exists.
FPL_PRIOR_SHRINKAGE_MATCHES = 6.0

# Cold-start fallback: expected non-penalty xG per 90 for a league-median-priced
# player, by position. Scaled by price relative to the position median, because
# FPL's price is itself a forecast of output. Used only for players with no
# Premier League history (promoted clubs, foreign signings).
FPL_COLD_START_XG90 = {"GK": 0.0, "DEF": 0.05, "MID": 0.12, "FWD": 0.28}
FPL_COLD_START_XA90 = {"GK": 0.0, "DEF": 0.06, "MID": 0.14, "FWD": 0.12}
FPL_MEDIAN_PRICE = {"GK": 4.5, "DEF": 4.5, "MID": 5.5, "FWD": 6.0}
```

- [ ] **Step 4: Write minimal implementation**

Append to `core/fpl_priors.py`:

```python
def needs_cold_start(player: dict) -> bool:
    """True when a player has no Premier League minutes to derive rates from."""
    return (player.get("minutes") or 0) <= 0


def _price_scaled(player: dict, table: dict) -> float:
    import config
    pos = player.get("position", "MID")
    base = table.get(pos, 0.0)
    if base <= 0.0:
        return 0.0
    median = config.FPL_MEDIAN_PRICE.get(pos, 5.0)
    quality = min(3.0, max(0.3, (player.get("price") or median) / median))
    return base * quality


def price_prior_xg(player: dict) -> float:
    """Cold-start non-penalty xG/90 from price and position."""
    import config
    return _price_scaled(player, config.FPL_COLD_START_XG90)


def price_prior_xa(player: dict) -> float:
    """Cold-start xA/90 from price and position."""
    import config
    return _price_scaled(player, config.FPL_COLD_START_XA90)


def _rates(player: dict) -> tuple[float, float]:
    """(xg_per90, xa_per90), falling back to the price prior with no history."""
    if needs_cold_start(player):
        return price_prior_xg(player), price_prior_xa(player)
    return player.get("xg_per90") or 0.0, player.get("xa_per90") or 0.0


def build_with_flags(players: list[dict], team_matches: int
                     ) -> tuple[dict[str, list], list[dict]]:
    """Build priors grouped by club, plus a list of cold-start flags for preflight.

    Shares are normalised WITHIN a club: the engine allocates a team's simulated
    goals among its own players, so what matters is a player's share of his club's
    attacking output, not an absolute rate. Shares need not sum to 1 — the engine
    treats the remainder as unmodelled teammates.
    """
    by_team: dict[str, list] = {}
    flags: list[dict] = []

    grouped: dict[str, list] = {}
    for p in players:
        grouped.setdefault(p["team"], []).append(p)

    for team, squad in grouped.items():
        weighted = []
        for p in squad:
            start_prob, exp_minutes = minutes_model(p, team_matches)
            xg90, xa90 = _rates(p)
            if needs_cold_start(p):
                flags.append({"name": p["name"], "team": team,
                              "reason": "no_pl_history"})
            weighted.append((p, start_prob, exp_minutes, xg90, xa90))

        # Normalise to shares of the club's expected output, weighting each player's
        # rate by how much of the pitch time he is expected to occupy.
        goal_mass = sum(sp * xg for _p, sp, _m, xg, _xa in weighted) or 1.0
        assist_mass = sum(sp * xa for _p, sp, _m, _xg, xa in weighted) or 1.0

        priors = []
        for p, start_prob, exp_minutes, xg90, xa90 in weighted:
            priors.append(ratings.PlayerPrior(
                name=p["name"], team=team, position=p["position"],
                start_prob=start_prob, exp_minutes=exp_minutes,
                goal_share=(xg90 / goal_mass) if xg90 else 0.0,
                assist_share=(xa90 / assist_mass) if xa90 else 0.0,
                sot_per90=0.0,          # FPL does not score shots on target
                pen_taker=bool(p.get("pen_taker")),
                defcon_per90=p.get("defcon_per90") or 0.0,
                saves_per90=p.get("saves_per90") or 0.0,
            ))
        by_team[team] = priors

    return by_team, flags


def build(players: list[dict], team_matches: int) -> dict[str, list]:
    """build_with_flags without the flags, for callers that don't need preflight."""
    by_team, _flags = build_with_flags(players, team_matches)
    return by_team
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m unittest tests.test_fpl_priors -v`
Expected: PASS (29 tests)

- [ ] **Step 6: Commit**

```bash
git add core/fpl_priors.py config.py tests/test_fpl_priors.py
git commit -m "feat(fpl): xG-derived priors with price-based cold-start fallback"
```

---

# PHASE 2 — Model

## Task 11: `engine_events` — priors provider

**Files:**
- Modify: `core/engine_events.py:187-240`
- Create: `tests/test_engine_priors.py`

`ratings.players_for_team(team)` is currently called at line 240, **inside** the per-sim
loop. Resolve squads once before the loop and pass them down. This is a pure refactor for
World Cup runs — behaviour must not change.

- [ ] **Step 1: Write the failing test**

Create `tests/test_engine_priors.py`:

```python
import unittest
from datetime import datetime, timezone

from core import engine_events, fixtures, ratings


class TestPriorsInjection(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.Fixture(
            "PRIORS1", "Alphaland", "Betaland",
            kickoff=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc),
            stage="GW", fantasy_round=901, neutral=False,
            lam_home=1.6, lam_away=1.1,
        )
        fixtures.SCHEDULE.append(self.fx)
        self.addCleanup(lambda: fixtures.SCHEDULE.remove(self.fx))

        self.squads = {
            "Alphaland": [
                ratings.PlayerPrior("A-Striker", "Alphaland", "FWD",
                                    start_prob=1.0, exp_minutes=90, goal_share=0.5),
                ratings.PlayerPrior("A-Keeper", "Alphaland", "GK",
                                    start_prob=1.0, exp_minutes=90),
            ],
            "Betaland": [
                ratings.PlayerPrior("B-Striker", "Betaland", "FWD",
                                    start_prob=1.0, exp_minutes=90, goal_share=0.5),
            ],
        }

    def test_injected_priors_are_used_instead_of_the_ratings_registry(self):
        players, _matches = engine_events.simulate_round(
            901, sims=500, priors=lambda team: self.squads.get(team, []))
        self.assertEqual(set(players), {"A-Striker", "A-Keeper", "B-Striker"})

    def test_injected_priors_produce_goals_for_the_favourite(self):
        players, _matches = engine_events.simulate_round(
            901, sims=2000, priors=lambda team: self.squads.get(team, []))
        # Alphaland has the higher lambda, so its striker should out-score Betaland's
        self.assertGreater(players["A-Striker"].mean("goals"),
                           players["B-Striker"].mean("goals"))

    def test_default_priors_come_from_the_registry_not_the_injection(self):
        # With no priors= argument the engine must consult ratings.players_for_team.
        # Assert the call happens rather than asserting on registry CONTENTS, which
        # depend on data/players.json (gitignored, so absent on a fresh clone).
        from unittest import mock
        with mock.patch.object(ratings, "players_for_team",
                               return_value=[]) as spy:
            engine_events.simulate_round(901, sims=10)
        spy.assert_any_call("Alphaland")
        spy.assert_any_call("Betaland")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_engine_priors -v`
Expected: FAIL — `TypeError: simulate_round() got an unexpected keyword argument 'priors'`

- [ ] **Step 3: Write minimal implementation**

In `core/engine_events.py`, change the `simulate_round` signature and add the resolution
step. Add `priors` as the last keyword argument:

```python
def simulate_round(fantasy_round: int, sims: int = 50_000, seed: int = 12345,
                   market_rates: dict | None = None, research: dict | None = None,
                   research_weight: float = 0.0, concentration: float | None = None,
                   priors=None):
    """Run the shared Monte Carlo for every fixture in a round.

    market_rates:    optional {player_name: goal_rate} from bookmaker player props.
    research:        optional {player_name: ResearchEntry} overrides.
    research_weight: the game's `w` dial (0 = pure odds, 1 = full expert overlay).
    concentration:   goal-split sharpening gamma; None -> config.GOAL_CONCENTRATION.
    priors:          optional callable(team) -> [PlayerPrior]. Defaults to
                     ratings.players_for_team. FPL injects xG-derived priors here;
                     the World Cup uses the registry. Resolved ONCE per team below,
                     never inside the sim loop.

    Returns (player_samples, match_samples).
    """
    import config
    gamma = config.GOAL_CONCENTRATION if concentration is None else concentration
    rng = random.Random(seed)
    fx = fixtures.by_round(fantasy_round)
    market_rates = market_rates or {}
    research = research or {}
    prior_of = priors or ratings.players_for_team
```

Immediately after the `eff_weight` / `eff_start` / `assist_weight` declarations, add a
resolved-squad cache:

```python
    squads: dict[str, list] = {}   # team -> resolved priors, looked up once
```

In the pre-index loop, replace `for p in ratings.players_for_team(team):` with:

```python
        for team in (f.home, f.away):
            if team not in squads:
                squads[team] = prior_of(team)
            for p in squads[team]:
```

And in the per-sim loop, replace `squad = ratings.players_for_team(team)` with:

```python
                squad = squads.get(team, ())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_engine_priors -v`
Expected: PASS (3 tests)

Run: `python -m unittest discover -s tests -t .`
Expected: OK — World Cup behaviour unchanged

- [ ] **Step 5: Commit**

```bash
git add core/engine_events.py tests/test_engine_priors.py
git commit -m "refactor(engine): injectable priors provider, resolved outside the sim loop"
```

---

## Task 12: `engine_events` — four additive sample fields

**Files:**
- Modify: `core/engine_events.py:47-76`, `:249-273`, `:302-317`
- Modify: `tests/test_engine_priors.py`

Each field exists because a World Cup field cannot be remapped to FPL's rule. See spec §4.1b.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_engine_priors.py`:

```python
class TestAdditiveSampleFields(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.Fixture(
            "PRIORS2", "Alphaland", "Betaland",
            kickoff=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc),
            stage="GW", fantasy_round=902, neutral=False,
            lam_home=1.5, lam_away=1.5,
        )
        fixtures.SCHEDULE.append(self.fx)
        self.addCleanup(lambda: fixtures.SCHEDULE.remove(self.fx))

        self.squads = {
            "Alphaland": [
                ratings.PlayerPrior("A-Keeper", "Alphaland", "GK",
                                    start_prob=1.0, exp_minutes=90, saves_per90=3.0),
                ratings.PlayerPrior("A-Back", "Alphaland", "DEF",
                                    start_prob=1.0, exp_minutes=90, defcon_per90=9.0),
            ],
            "Betaland": [
                ratings.PlayerPrior("B-Striker", "Betaland", "FWD",
                                    start_prob=1.0, exp_minutes=90, goal_share=0.5),
            ],
        }
        self.players, _ = engine_events.simulate_round(
            902, sims=1500, priors=lambda t: self.squads.get(t, []))

    def test_raw_conceded_is_recorded_separately_from_conc_beyond(self):
        back = self.players["A-Back"]
        # conc_beyond is max(0, ga-1) (FIFA); conceded is the raw count (FPL needs ga/2)
        self.assertGreater(back.conceded, back.conc_beyond)

    def test_played_60_is_tracked_and_never_exceeds_played(self):
        back = self.players["A-Back"]
        self.assertGreater(back.played_60, 0)
        self.assertLessEqual(back.played_60, back.played)

    def test_save_samples_collected_for_goalkeepers_only(self):
        self.assertTrue(self.players["A-Keeper"].save_samples)
        self.assertFalse(self.players["B-Striker"].save_samples)

    def test_defcon_samples_collected_only_when_a_rate_is_set(self):
        self.assertTrue(self.players["A-Back"].defcon_samples)
        self.assertFalse(self.players["B-Striker"].defcon_samples)

    def test_defcon_samples_centre_on_the_configured_rate(self):
        counts = self.players["A-Back"].defcon_samples
        mean = sum(counts) / len(counts)
        self.assertGreater(mean, 6.0)    # rate 9.0/90 over ~90 minutes
        self.assertLess(mean, 12.0)

    def test_event_means_exposes_the_new_fields(self):
        means = engine_events.event_means(self.players)
        row = means["A-Back"]
        self.assertIn("conceded", row)
        self.assertIn("played_60", row)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_engine_priors -v`
Expected: FAIL — `AttributeError: 'PlayerSample' object has no attribute 'conceded'`

- [ ] **Step 3: Write minimal implementation**

In `core/engine_events.py`, add the four fields to `PlayerSample`, after `goal_samples`:

```python
    # Per-sim goal tallies, for games that need the full distribution (e.g. captaincy
    # variance, hat-trick bonuses). Kept compact.
    goal_samples: list[int] = field(default_factory=list)
    # --- fields added for FPL. The engine samples RAW events; each game applies its
    # own rules to them. Zero/empty for World Cup games, which don't read them.
    conceded: float = 0.0            # raw goals conceded while on the pitch (GK/DEF).
                                     # conc_beyond is FIFA's max(0, ga-1); FPL needs
                                     # floor(ga/2), which that cannot express.
    played_60: float = 0.0           # times the player reached 60 minutes. FPL pays 1
                                     # point under 60 and 2 at 60+.
    save_samples: list[int] = field(default_factory=list)    # GK only.
                                     # E[floor(saves/3)] != floor(E[saves]/3).
    defcon_samples: list[int] = field(default_factory=list)  # DefCon is a threshold
                                     # crossing, so a mean count cannot give P(>= 10).
```

In the per-sim player loop, after `ps.played += 1`, add the 60-minute tally:

```python
                    mins = min(90, max(0, rng.gauss(p.exp_minutes, 12)))
                    ps.minutes += mins
                    ps.played += 1
                    if mins >= 60:
                        ps.played_60 += 1
```

Replace the clean-sheet / concede block with one that also records the raw count:

```python
                    if p.position in ("DEF", "GK"):
                        ps.conceded += ga
                        if mins >= 60:
                            if clean:
                                ps.clean_sheet += 1
                            ps.conc_beyond += max(0, ga - 1)
```

Replace the goalkeeper saves line so it keeps per-sim counts:

```python
                    if p.position == "GK":
                        s = _poisson(max(0.0, ga + 1.5), rng)
                        ps.saves += s
                        ps.save_samples.append(s)
```

After the goalkeeper block, add DefCon sampling:

```python
                    if p.defcon_per90 > 0:
                        ps.defcon_samples.append(
                            _poisson(p.defcon_per90 * mins / 90.0, rng))
```

Finally, extend `event_means` to expose the two scalar additions:

```python
            "conc_beyond": ps.mean("conc_beyond"),
            "conceded": ps.mean("conceded"),
            "played_60": ps.mean("played_60"),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_engine_priors -v`
Expected: PASS (9 tests)

Run: `python -m unittest discover -s tests -t .`
Expected: OK — `conc_beyond` semantics are unchanged, so FIFA scoring is unaffected

- [ ] **Step 5: Commit**

```bash
git add core/engine_events.py tests/test_engine_priors.py
git commit -m "feat(engine): raw conceded, played_60, save + defcon per-sim samples"
```

---

## Task 13: `engine_events` — per-match hook

**Files:**
- Modify: `core/engine_events.py:187-299`
- Modify: `tests/test_engine_priors.py`

Bonus is a rank-within-match quantity: it depends on all 22 players' events inside a single
sim of a single match, which no per-player accumulator can reconstruct. The engine passes
raw event rows to a callback and knows nothing about BPS. See spec §4.1c.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_engine_priors.py`:

```python
class TestPerMatchHook(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.Fixture(
            "PRIORS3", "Alphaland", "Betaland",
            kickoff=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc),
            stage="GW", fantasy_round=903, neutral=False,
            lam_home=1.4, lam_away=1.2,
        )
        fixtures.SCHEDULE.append(self.fx)
        self.addCleanup(lambda: fixtures.SCHEDULE.remove(self.fx))
        self.squads = {
            "Alphaland": [ratings.PlayerPrior("A1", "Alphaland", "FWD",
                                              start_prob=1.0, exp_minutes=90,
                                              goal_share=0.4)],
            "Betaland": [ratings.PlayerPrior("B1", "Betaland", "DEF",
                                             start_prob=1.0, exp_minutes=90)],
        }

    def test_hook_fires_once_per_match_per_sim(self):
        calls = []
        engine_events.simulate_round(
            903, sims=50, priors=lambda t: self.squads.get(t, []),
            per_match_hook=lambda match_id, rows: calls.append((match_id, len(rows))))
        self.assertEqual(len(calls), 50)
        self.assertEqual({c[0] for c in calls}, {"PRIORS3"})

    def test_hook_receives_both_sides_in_one_call(self):
        seen = []
        engine_events.simulate_round(
            903, sims=20, priors=lambda t: self.squads.get(t, []),
            per_match_hook=lambda _mid, rows: seen.append({r[0] for r in rows}))
        # every call carries players from both teams
        self.assertTrue(all(names == {"A1", "B1"} for names in seen))

    def test_hook_rows_carry_the_documented_field_order(self):
        captured = []
        engine_events.simulate_round(
            903, sims=5, priors=lambda t: self.squads.get(t, []),
            per_match_hook=lambda _mid, rows: captured.extend(rows))
        name, position, goals, assists, minutes, clean_sheet, conceded, saves, yellow, red = captured[0]
        self.assertIn(name, {"A1", "B1"})
        self.assertIn(position, {"FWD", "DEF"})
        self.assertIsInstance(goals, int)
        self.assertIsInstance(clean_sheet, bool)
        self.assertGreaterEqual(minutes, 0)

    def test_no_hook_is_the_default_and_changes_nothing(self):
        players, _ = engine_events.simulate_round(
            903, sims=50, priors=lambda t: self.squads.get(t, []))
        self.assertIn("A1", players)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_engine_priors -v`
Expected: FAIL — `TypeError: simulate_round() got an unexpected keyword argument 'per_match_hook'`

- [ ] **Step 3: Write minimal implementation**

Extend the signature with `per_match_hook=None` and document it:

```python
def simulate_round(fantasy_round: int, sims: int = 50_000, seed: int = 12345,
                   market_rates: dict | None = None, research: dict | None = None,
                   research_weight: float = 0.0, concentration: float | None = None,
                   priors=None, per_match_hook=None):
```

Add to the docstring:

```
    per_match_hook:  optional callable(match_id, rows) invoked once per match per
                     sim, where rows is a list of tuples
                       (name, position, goals, assists, minutes, clean_sheet,
                        conceded, saves, yellow, red)
                     for every on-pitch player across BOTH sides. Exists for
                     rank-within-match quantities — FPL bonus points depend on all
                     22 players' events in one sim, which per-player accumulators
                     cannot reconstruct. The engine knows nothing about what the
                     callback computes.
```

Inside the per-sim loop, collect rows alongside the existing accumulation. Declare the
buffer next to `motm_pool`:

```python
            motm_pool: list[tuple[str, float]] = []  # one MOTM per match across both teams
            hook_rows: list[tuple] = [] if per_match_hook else None
```

Inside the per-player block, after the discipline section, record the row. Capture the
yellow/red draws into locals first so the row and the accumulators agree:

```python
                    # Discipline.
                    yel = 1 if rng.random() < 0.12 else 0
                    red = 1 if rng.random() < 0.012 else 0
                    ps.yellow += yel
                    ps.red += red
                    if hook_rows is not None:
                        hook_rows.append((
                            p.name, p.position, g, a, mins,
                            bool(clean and mins >= 60 and p.position in ("DEF", "GK")),
                            ga if p.position in ("DEF", "GK") else 0,
                            ps.save_samples[-1] if p.position == "GK" else 0,
                            yel, red,
                        ))
```

After the two-team loop closes and before the MOTM award, fire the hook:

```python
            if hook_rows:
                per_match_hook(f.match_id, hook_rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_engine_priors -v`
Expected: PASS (13 tests)

Run: `python -m unittest discover -s tests -t .`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add core/engine_events.py tests/test_engine_priors.py
git commit -m "feat(engine): per-match per-sim hook for rank-within-match scoring"
```

---

## Task 14: `games/fpl/rules.md` and package scaffold

**Files:**
- Create: `games/fpl/__init__.py`
- Create: `games/fpl/rules.md`
- Create: `games/fpl/state.json`

- [ ] **Step 1: Create the empty package marker**

```bash
touch games/fpl/__init__.py
```

- [ ] **Step 2: Write the rules document**

Copy the verified capture into place — it was committed in this branch as the research
record, and `games/fpl/rules.md` is where the model's constants cite from:

```bash
cp docs/research/2026-07-28-fpl-rules-2026-27-verbatim.md games/fpl/rules.md
```

Then prepend a provenance header. Open `games/fpl/rules.md` and insert at the very top:

```markdown
# FPL 2026/27 scoring — the model's reference

Every constant in `games/fpl/model.py` cites a row in this file.

**Provenance for each number below:**
- Scoring and BPS tables: the official rules page at
  `https://fantasy.premierleague.com/en/help/rules`, read 2026-07-28.
- Squad/transfer/chip mechanics: `bootstrap-static.game_config`, same date.
- **The two divisors (1 point per 3 saves, -1 per 2 conceded) come from the rules
  page only.** `game_config.scoring` carries unit values (`saves: 1`,
  `goals_conceded: -1`) and mis-prices every goalkeeper if read literally.
- Nothing in this file is an assumption. If a future rule change cannot be verified
  from one of those two sources, mark it explicitly as unverified rather than
  guessing.

---
```

- [ ] **Step 3: Create the squad state file**

Create `games/fpl/state.json`. This mirrors the shape the other games use — an
`_example` marker so the model prints a friendly message until it is populated:

```json
{
  "team": "Granat65",
  "research_weight": 0.3,
  "budget": 100.0,
  "free_transfers": 1,
  "chips_used": [],
  "squad": [
    {
      "_example": true,
      "name": "Haaland",
      "team": "MCI",
      "position": "FWD",
      "price": 15.5,
      "ownership_pct": 75.2,
      "is_starter": true,
      "bench_order": null
    }
  ]
}
```

- [ ] **Step 4: Verify the package imports**

Run: `python -c "import games.fpl; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add games/fpl/__init__.py games/fpl/rules.md games/fpl/state.json
git commit -m "feat(fpl): game package scaffold with verified rules reference"
```

---

## Task 15: `games/fpl/model.py` — direct scoring

**Files:**
- Create: `games/fpl/model.py`
- Create: `tests/test_fpl_model.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_fpl_model.py`:

```python
import unittest

from games.fpl import model


def _ev(**kw):
    base = {
        "team": "LIV", "position": "MID", "goals": 0.0, "assists": 0.0,
        "minutes": 90.0, "played": 1.0, "played_60": 1.0, "clean_sheet": 0.0,
        "conceded": 0.0, "yellow": 0.0, "red": 0.0, "saves": 0.0,
        "goal_share": 0.0, "assist_share": 0.0,
    }
    base.update(kw)
    return base


class TestAppearancePoints(unittest.TestCase):
    def test_full_match_pays_two(self):
        self.assertAlmostEqual(model.expected_points(_ev()), 2.0)

    def test_cameo_pays_one(self):
        self.assertAlmostEqual(
            model.expected_points(_ev(played=1.0, played_60=0.0)), 1.0)

    def test_unused_player_pays_nothing(self):
        self.assertAlmostEqual(
            model.expected_points(_ev(played=0.0, played_60=0.0)), 0.0)


class TestGoalPoints(unittest.TestCase):
    def test_goalkeeper_goal_is_worth_ten(self):
        pts = model.expected_points(_ev(position="GK", goals=1.0))
        self.assertAlmostEqual(pts, 2.0 + 10.0)

    def test_defender_goal_is_worth_six(self):
        self.assertAlmostEqual(
            model.expected_points(_ev(position="DEF", goals=1.0)), 2.0 + 6.0)

    def test_midfielder_goal_is_worth_five(self):
        self.assertAlmostEqual(
            model.expected_points(_ev(position="MID", goals=1.0)), 2.0 + 5.0)

    def test_forward_goal_is_worth_four(self):
        self.assertAlmostEqual(
            model.expected_points(_ev(position="FWD", goals=1.0)), 2.0 + 4.0)


class TestCleanSheetsAndAssists(unittest.TestCase):
    def test_assist_is_three(self):
        self.assertAlmostEqual(model.expected_points(_ev(assists=1.0)), 2.0 + 3.0)

    def test_defender_clean_sheet_is_four(self):
        self.assertAlmostEqual(
            model.expected_points(_ev(position="DEF", clean_sheet=1.0)), 2.0 + 4.0)

    def test_midfielder_clean_sheet_is_one(self):
        self.assertAlmostEqual(
            model.expected_points(_ev(position="MID", clean_sheet=1.0)), 2.0 + 1.0)

    def test_forward_gets_nothing_for_a_clean_sheet(self):
        self.assertAlmostEqual(
            model.expected_points(_ev(position="FWD", clean_sheet=1.0)), 2.0)


class TestCards(unittest.TestCase):
    def test_yellow_is_minus_one(self):
        self.assertAlmostEqual(model.expected_points(_ev(yellow=1.0)), 2.0 - 1.0)

    def test_red_is_minus_three(self):
        self.assertAlmostEqual(model.expected_points(_ev(red=1.0)), 2.0 - 3.0)


class TestConcededThreshold(unittest.TestCase):
    """-1 per TWO goals conceded, and the divisor must not be applied to a mean."""

    def test_two_conceded_costs_one_point(self):
        pts = model.conceded_points("DEF", conceded_samples=[2, 2, 2, 2])
        self.assertAlmostEqual(pts, -1.0)

    def test_one_conceded_costs_nothing(self):
        self.assertAlmostEqual(
            model.conceded_points("DEF", conceded_samples=[1, 1, 1, 1]), 0.0)

    def test_three_conceded_still_costs_only_one(self):
        self.assertAlmostEqual(
            model.conceded_points("DEF", conceded_samples=[3, 3]), -1.0)

    def test_threshold_is_not_the_same_as_dividing_the_mean(self):
        # mean of [1,3] is 2 -> naive floor(2/2) = -1. Correct is
        # (floor(1/2) + floor(3/2)) / 2 = (0 + 1)/2 = -0.5
        self.assertAlmostEqual(
            model.conceded_points("DEF", conceded_samples=[1, 3]), -0.5)

    def test_midfielders_and_forwards_are_exempt(self):
        self.assertAlmostEqual(
            model.conceded_points("MID", conceded_samples=[4, 4]), 0.0)
        self.assertAlmostEqual(
            model.conceded_points("FWD", conceded_samples=[4, 4]), 0.0)


class TestSavesThreshold(unittest.TestCase):
    """1 point per THREE saves, from per-sim counts."""

    def test_three_saves_is_one_point(self):
        self.assertAlmostEqual(model.saves_points([3, 3, 3]), 1.0)

    def test_two_saves_is_nothing(self):
        self.assertAlmostEqual(model.saves_points([2, 2]), 0.0)

    def test_six_saves_is_two_points(self):
        self.assertAlmostEqual(model.saves_points([6]), 2.0)

    def test_threshold_is_not_the_same_as_dividing_the_mean(self):
        # mean of [2,4] is 3 -> naive 1.0. Correct is (0 + 1)/2 = 0.5
        self.assertAlmostEqual(model.saves_points([2, 4]), 0.5)

    def test_no_samples_is_zero(self):
        self.assertAlmostEqual(model.saves_points([]), 0.0)


class TestDefconThreshold(unittest.TestCase):
    def test_defender_threshold_is_ten(self):
        self.assertEqual(model.defcon_threshold("DEF"), 10)

    def test_midfielder_and_forward_threshold_is_twelve(self):
        self.assertEqual(model.defcon_threshold("MID"), 12)
        self.assertEqual(model.defcon_threshold("FWD"), 12)

    def test_goalkeepers_are_not_eligible(self):
        self.assertIsNone(model.defcon_threshold("GK"))

    def test_always_crossing_pays_the_full_two(self):
        self.assertAlmostEqual(model.defcon_points("DEF", [10, 11, 12]), 2.0)

    def test_never_crossing_pays_nothing(self):
        self.assertAlmostEqual(model.defcon_points("DEF", [4, 5, 6]), 0.0)

    def test_half_the_time_pays_one(self):
        self.assertAlmostEqual(model.defcon_points("DEF", [4, 10]), 1.0)

    def test_payout_is_capped_at_two_however_high_the_count(self):
        self.assertAlmostEqual(model.defcon_points("DEF", [50, 50]), 2.0)

    def test_goalkeeper_scores_no_defcon(self):
        self.assertAlmostEqual(model.defcon_points("GK", [20, 20]), 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_fpl_model -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'games.fpl.model'`

- [ ] **Step 3: Write minimal implementation**

Create `games/fpl/model.py`:

```python
"""Fantasy Premier League model.

Maps the shared engine's simulated events onto the official 2026/27 FPL points
scale and emits the order book.

Every constant here cites a row in games/fpl/rules.md, which is a verbatim capture
of the official rules page. The two DIVISORS are the trap: bootstrap-static's
game_config.scoring reports `saves: 1` and `goals_conceded: -1` as unit values,
but the real rules are one point per THREE saves and minus one per TWO conceded.
Reading the feed literally mis-prices every goalkeeper.

Threshold scoring is computed from PER-SIM COUNTS, never from means, because
E[floor(x/n)] != floor(E[x]/n).
"""

from __future__ import annotations

# --- confirmed scoring values (games/fpl/rules.md) -------------------------
GOAL_PTS = {"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}
ASSIST_PTS = 3
CS_PTS = {"GK": 4, "DEF": 4, "MID": 1, "FWD": 0}
APPEARANCE_60 = 2          # 60 minutes or more, excluding stoppage time
APPEARANCE_SHORT = 1       # up to 60 minutes
YELLOW_PTS = -1
RED_PTS = -3
OWN_GOAL_PTS = -2
PEN_MISS_PTS = -2
PEN_SAVE_PTS = 5

# Divisors — from the official rules page ONLY, not from the API feed.
SAVES_PER_POINT = 3        # "For every 3 shot saves by a goalkeeper: 1"
CONCEDED_PER_MINUS = 2     # "For every 2 goals conceded by a goalkeeper or defender: -1"

# Defensive contribution: a threshold crossing worth exactly 2, capped.
# Defenders count CBIT; midfielders and forwards count CBIRT (recoveries included).
# Goalkeepers are not eligible.
DEFCON_PTS = 2
DEFCON_THRESHOLD = {"DEF": 10, "MID": 12, "FWD": 12}

# Positions that suffer the goals-conceded penalty.
_CONCEDE_POSITIONS = ("GK", "DEF")


def expected_points(ev: dict) -> float:
    """Expected FPL points from mean events, EXCLUDING the threshold components.

    Saves, goals conceded, DefCon and bonus are threshold or rank quantities and
    must be computed from per-sim samples — see saves_points, conceded_points,
    defcon_points and the bonus accumulator. Keeping them out of here makes it
    impossible to double-count them by accident.
    """
    pos = ev["position"]
    pts = 0.0
    # Appearance: the 60+ tier and the short tier are mutually exclusive.
    played, played_60 = ev.get("played", 0.0), ev.get("played_60", 0.0)
    pts += played_60 * APPEARANCE_60
    pts += max(0.0, played - played_60) * APPEARANCE_SHORT
    pts += ev.get("goals", 0.0) * GOAL_PTS.get(pos, 4)
    pts += ev.get("assists", 0.0) * ASSIST_PTS
    pts += ev.get("clean_sheet", 0.0) * CS_PTS.get(pos, 0)
    pts += ev.get("yellow", 0.0) * YELLOW_PTS
    pts += ev.get("red", 0.0) * RED_PTS
    return pts


def saves_points(save_samples: list) -> float:
    """Expected points from saves: mean of floor(saves / 3) over the sims.

    NOT floor(mean_saves / 3) — a keeper averaging 3.0 saves does not reliably
    bank the point, because the sims below 3 pay nothing.
    """
    if not save_samples:
        return 0.0
    return sum(s // SAVES_PER_POINT for s in save_samples) / float(len(save_samples))


def conceded_points(position: str, conceded_samples: list) -> float:
    """Expected points from goals conceded: mean of -floor(conceded / 2).

    Only goalkeepers and defenders are charged.
    """
    if position not in _CONCEDE_POSITIONS or not conceded_samples:
        return 0.0
    total = sum(c // CONCEDED_PER_MINUS for c in conceded_samples)
    return -total / float(len(conceded_samples))


def defcon_threshold(position: str) -> int | None:
    """The DefCon action count a position must reach, or None if not eligible."""
    return DEFCON_THRESHOLD.get(position)


def defcon_points(position: str, defcon_samples: list) -> float:
    """Expected DefCon points: 2 x P(count >= threshold).

    A threshold crossing, not a rate — 2 x rate/threshold is wrong in both tails,
    over-paying players who never reach it and under-paying those who always do.
    The payout is capped at 2 no matter how far past the threshold a player goes.
    """
    threshold = defcon_threshold(position)
    if threshold is None or not defcon_samples:
        return 0.0
    hits = sum(1 for c in defcon_samples if c >= threshold)
    return DEFCON_PTS * hits / float(len(defcon_samples))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_fpl_model -v`
Expected: PASS (31 tests)

- [ ] **Step 5: Commit**

```bash
git add games/fpl/model.py tests/test_fpl_model.py
git commit -m "feat(fpl): direct scoring + threshold components for saves, conceded, DefCon"
```

---

## Task 16: `games/fpl/model.py` — BPS and the bonus accumulator

**Files:**
- Modify: `games/fpl/model.py`
- Modify: `tests/test_fpl_model.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fpl_model.py`:

```python
class TestBpsFromEvents(unittest.TestCase):
    """Event-driven BPS deltas, from the official BPS table in games/fpl/rules.md."""

    def _row(self, **kw):
        base = {"name": "P", "position": "MID", "goals": 0, "assists": 0,
                "minutes": 90, "clean_sheet": False, "conceded": 0, "saves": 0,
                "yellow": 0, "red": 0}
        base.update(kw)
        return (base["name"], base["position"], base["goals"], base["assists"],
                base["minutes"], base["clean_sheet"], base["conceded"],
                base["saves"], base["yellow"], base["red"])

    def test_over_sixty_minutes_is_six_bps(self):
        self.assertEqual(model.bps_from_row(self._row(), baseline=0.0), 6)

    def test_under_sixty_minutes_is_three_bps(self):
        self.assertEqual(model.bps_from_row(self._row(minutes=45), baseline=0.0), 3)

    def test_forward_goal_is_twenty_four_bps(self):
        got = model.bps_from_row(self._row(position="FWD", goals=1), baseline=0.0)
        self.assertEqual(got, 6 + 24)

    def test_midfielder_goal_is_eighteen_bps(self):
        got = model.bps_from_row(self._row(position="MID", goals=1), baseline=0.0)
        self.assertEqual(got, 6 + 18)

    def test_defender_goal_is_twelve_bps(self):
        got = model.bps_from_row(self._row(position="DEF", goals=1), baseline=0.0)
        self.assertEqual(got, 6 + 12)

    def test_assist_is_nine_bps(self):
        self.assertEqual(model.bps_from_row(self._row(assists=1), baseline=0.0), 6 + 9)

    def test_defender_clean_sheet_is_twelve_bps(self):
        got = model.bps_from_row(
            self._row(position="DEF", clean_sheet=True), baseline=0.0)
        self.assertEqual(got, 6 + 12)

    def test_midfielder_clean_sheet_earns_no_bps(self):
        got = model.bps_from_row(
            self._row(position="MID", clean_sheet=True), baseline=0.0)
        self.assertEqual(got, 6)

    def test_each_save_is_two_bps(self):
        got = model.bps_from_row(self._row(position="GK", saves=4), baseline=0.0)
        self.assertEqual(got, 6 + 8)

    def test_conceding_costs_a_defender_four_bps_each(self):
        got = model.bps_from_row(
            self._row(position="DEF", conceded=2), baseline=0.0)
        self.assertEqual(got, 6 - 8)

    def test_cards_cost_three_and_nine_bps(self):
        self.assertEqual(model.bps_from_row(self._row(yellow=1), baseline=0.0), 6 - 3)
        self.assertEqual(model.bps_from_row(self._row(red=1), baseline=0.0), 6 - 9)

    def test_baseline_rate_is_prorated_by_minutes(self):
        # baseline 18 BPS per 90 over 45 minutes contributes 9
        self.assertEqual(model.bps_from_row(self._row(minutes=45), baseline=18.0),
                         3 + 9)


class TestBonusAccumulator(unittest.TestCase):
    def _rows(self, scores):
        """Build rows whose BPS ordering is controlled by goal counts."""
        return [(name, "FWD", goals, 0, 90, False, 0, 0, 0, 0)
                for name, goals in scores]

    def test_top_three_take_three_two_one(self):
        acc = model.BonusAccumulator(baselines={})
        acc.observe("m1", self._rows([("A", 3), ("B", 2), ("C", 1), ("D", 0)]))
        self.assertAlmostEqual(acc.expected("A"), 3.0)
        self.assertAlmostEqual(acc.expected("B"), 2.0)
        self.assertAlmostEqual(acc.expected("C"), 1.0)
        self.assertAlmostEqual(acc.expected("D"), 0.0)

    def test_expected_bonus_averages_across_sims(self):
        acc = model.BonusAccumulator(baselines={})
        acc.observe("m1", self._rows([("A", 3), ("B", 0)]))
        acc.observe("m1", self._rows([("A", 0), ("B", 3)]))
        # A tops one sim (3) and is second in the other (2) -> 2.5
        self.assertAlmostEqual(acc.expected("A"), 2.5)
        self.assertAlmostEqual(acc.expected("B"), 2.5)

    def test_tie_for_first_gives_both_three_and_the_next_player_one(self):
        # Official rule: two tied on top both get 3, and the THIRD-most BPS gets 1
        # (not 2 — the tie consumes two award positions).
        acc = model.BonusAccumulator(baselines={})
        acc.observe("m1", self._rows([("A", 2), ("B", 2), ("C", 0)]))
        self.assertAlmostEqual(acc.expected("A"), 3.0)
        self.assertAlmostEqual(acc.expected("B"), 3.0)
        self.assertAlmostEqual(acc.expected("C"), 1.0)

    def test_tie_for_second_gives_both_two_and_awards_no_one(self):
        acc = model.BonusAccumulator(baselines={})
        acc.observe("m1", self._rows([("A", 3), ("B", 1), ("C", 1), ("D", 0)]))
        self.assertAlmostEqual(acc.expected("A"), 3.0)
        self.assertAlmostEqual(acc.expected("B"), 2.0)
        self.assertAlmostEqual(acc.expected("C"), 2.0)
        self.assertAlmostEqual(acc.expected("D"), 0.0)

    def test_unknown_player_has_no_expected_bonus(self):
        acc = model.BonusAccumulator(baselines={})
        acc.observe("m1", self._rows([("A", 1)]))
        self.assertAlmostEqual(acc.expected("nobody"), 0.0)

    def test_baselines_break_ties_between_equal_event_lines(self):
        # identical events, but B has the higher season BPS rate
        acc = model.BonusAccumulator(baselines={"A": 10.0, "B": 30.0})
        acc.observe("m1", self._rows([("A", 1), ("B", 1), ("C", 0)]))
        self.assertGreater(acc.expected("B"), acc.expected("A"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_fpl_model -v`
Expected: FAIL — `AttributeError: module 'games.fpl.model' has no attribute 'bps_from_row'`

- [ ] **Step 3: Write minimal implementation**

Append to `games/fpl/model.py`:

```python
# --- Bonus points ---------------------------------------------------------
# The official BPS table has 30+ components: successful crosses, dribbles,
# pass-completion tiers, fouls won, errors leading to an attempt. We have NO data
# for most of them, so reconstructing BPS from components is impossible.
#
# Instead: a per-90 baseline from each player's own realized BPS history carries
# everything we cannot see, and the components we DO sample are applied as exact
# deltas from the table. Rank all players in the match, award 3/2/1.
#
# Deliberately NOT applied per event: the +1 for a save inside the box and the +1
# for a save from a big chance both need shot-location data we lack, so they are
# absorbed into the baseline rate. Same for goalline clearances and errors.
BPS_PLAY_60 = 6
BPS_PLAY_SHORT = 3
BPS_GOAL = {"GK": 12, "DEF": 12, "MID": 18, "FWD": 24}
BPS_ASSIST = 9
BPS_CLEAN_SHEET = {"GK": 12, "DEF": 12, "MID": 0, "FWD": 0}
BPS_SAVE = 2
BPS_CONCEDED = -4          # per goal, goalkeepers and defenders only
BPS_YELLOW = -3
BPS_RED = -9

# Row layout produced by engine_events' per_match_hook.
_NAME, _POS, _GOALS, _ASSISTS, _MINUTES, _CS, _CONCEDED, _SAVES, _YELLOW, _RED = range(10)


def bps_from_row(row: tuple, baseline: float) -> int:
    """BPS for one player in one simulated match.

    `baseline` is the player's realized BPS per 90, prorated by minutes played. It
    stands in for every component we cannot sample.
    """
    pos = row[_POS]
    bps = BPS_PLAY_60 if row[_MINUTES] >= 60 else BPS_PLAY_SHORT
    bps += row[_GOALS] * BPS_GOAL.get(pos, 18)
    bps += row[_ASSISTS] * BPS_ASSIST
    if row[_CS]:
        bps += BPS_CLEAN_SHEET.get(pos, 0)
    bps += row[_SAVES] * BPS_SAVE
    if pos in _CONCEDE_POSITIONS:
        bps += row[_CONCEDED] * BPS_CONCEDED
    bps += row[_YELLOW] * BPS_YELLOW
    bps += row[_RED] * BPS_RED
    bps += int(round(baseline * row[_MINUTES] / 90.0))
    return bps


class BonusAccumulator:
    """Accumulates expected bonus points across sims via rank-within-match.

    Pass `observe` as engine_events' per_match_hook. After the sim completes,
    `expected(name)` gives that player's mean bonus.

    Ties consume award POSITIONS, matching the official rule: two players tied on
    top both take 3 and the third-most BPS takes 1 (not 2, because the tie has
    already used two positions). Two tied for second both take 2 and no 1 is
    awarded at all.
    """

    def __init__(self, baselines: dict):
        self.baselines = baselines or {}
        self._total: dict = {}
        self._sims: dict = {}

    def observe(self, _match_id: str, rows: list) -> None:
        scored = [(bps_from_row(r, self.baselines.get(r[_NAME], 0.0)), r[_NAME])
                  for r in rows]
        for _bps, name in scored:
            self._sims[name] = self._sims.get(name, 0) + 1
        if not scored:
            return
        # Group by BPS, highest first. Each group takes the award for the next
        # open position, then consumes as many positions as it has members.
        groups: dict = {}
        for bps, name in scored:
            groups.setdefault(bps, []).append(name)

        placed = 0
        for bps in sorted(groups, reverse=True):
            if placed == 0:
                award = 3
            elif placed == 1:
                award = 2
            elif placed == 2:
                award = 1
            else:
                break
            for name in groups[bps]:
                self._total[name] = self._total.get(name, 0) + award
            placed += len(groups[bps])

    def expected(self, name: str) -> float:
        sims = self._sims.get(name, 0)
        if not sims:
            return 0.0
        return self._total.get(name, 0) / float(sims)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_fpl_model -v`
Expected: PASS (49 tests)

- [ ] **Step 5: Commit**

```bash
git add games/fpl/model.py tests/test_fpl_model.py
git commit -m "feat(fpl): BPS deltas + rank-within-match bonus accumulator"
```

---

## Task 17: `games/fpl/model.py` — total points and ceiling

**Files:**
- Modify: `games/fpl/model.py`
- Modify: `tests/test_fpl_model.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fpl_model.py`:

```python
from core import engine_events


class TestTotalPoints(unittest.TestCase):
    def _sample(self, **kw):
        ps = engine_events.PlayerSample("K", "LIV", kw.pop("position", "GK"))
        ps.sims = 2
        ps.played = 2.0
        ps.played_60 = 2.0
        for key, value in kw.items():
            setattr(ps, key, value)
        return ps

    def test_total_sums_direct_and_threshold_components(self):
        ps = self._sample(position="GK", save_samples=[3, 3], conceded=0.0)
        means = {"position": "GK", "played": 1.0, "played_60": 1.0,
                 "goals": 0.0, "assists": 0.0, "clean_sheet": 1.0,
                 "yellow": 0.0, "red": 0.0}
        pts = model.total_points(means, ps, conceded_samples=[0, 0], bonus=0.0)
        # appearance 2 + clean sheet 4 + one saves point
        self.assertAlmostEqual(pts, 2.0 + 4.0 + 1.0)

    def test_bonus_is_added_verbatim(self):
        ps = self._sample(position="MID", save_samples=[])
        means = {"position": "MID", "played": 1.0, "played_60": 1.0,
                 "goals": 0.0, "assists": 0.0, "clean_sheet": 0.0,
                 "yellow": 0.0, "red": 0.0}
        pts = model.total_points(means, ps, conceded_samples=[], bonus=1.4)
        self.assertAlmostEqual(pts, 2.0 + 1.4)

    def test_defcon_included_when_samples_present(self):
        ps = self._sample(position="DEF", save_samples=[], defcon_samples=[10, 10])
        means = {"position": "DEF", "played": 1.0, "played_60": 1.0,
                 "goals": 0.0, "assists": 0.0, "clean_sheet": 0.0,
                 "yellow": 0.0, "red": 0.0}
        pts = model.total_points(means, ps, conceded_samples=[0, 0], bonus=0.0)
        self.assertAlmostEqual(pts, 2.0 + 2.0)


class TestCeiling(unittest.TestCase):
    def test_ceiling_is_never_below_the_mean(self):
        means = {"position": "DEF", "played": 1.0, "played_60": 1.0,
                 "goals": 0.0, "assists": 0.0, "clean_sheet": 0.9,
                 "yellow": 0.0, "red": 0.0}
        mean_pts = model.expected_points(means)
        ceiling = model.ceiling_points(means, goal_samples=[0, 0, 0, 0])
        self.assertGreaterEqual(ceiling, mean_pts)

    def test_ceiling_lifts_a_scorer_above_his_mean(self):
        means = {"position": "FWD", "played": 1.0, "played_60": 1.0,
                 "goals": 0.5, "assists": 0.0, "clean_sheet": 0.0,
                 "yellow": 0.0, "red": 0.0}
        ceiling = model.ceiling_points(means, goal_samples=[0, 0, 1, 2])
        self.assertGreater(ceiling, model.expected_points(means))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_fpl_model -v`
Expected: FAIL — `AttributeError: module 'games.fpl.model' has no attribute 'total_points'`

- [ ] **Step 3: Write minimal implementation**

Append to `games/fpl/model.py`:

```python
def total_points(means: dict, sample, conceded_samples: list,
                 bonus: float = 0.0) -> float:
    """Full expected FPL points for one player.

    `means` comes from engine_events.event_means; `sample` is the PlayerSample
    carrying per-sim threshold counts. Bonus is supplied by BonusAccumulator.
    """
    pts = expected_points(means)
    pts += saves_points(getattr(sample, "save_samples", []))
    pts += conceded_points(means["position"], conceded_samples)
    pts += defcon_points(means["position"], getattr(sample, "defcon_samples", []))
    pts += bonus
    return pts


def ceiling_points(means: dict, goal_samples: list, q: float = 0.85) -> float:
    """Goal-variance ceiling: mean points with the mean-goal contribution swapped
    for the q-percentile goal contribution, floored at the mean.

    Mirrors the FIFA and Holdet ceilings so all three are defined the same way.
    The floor removes an artefact: for non-scoring defenders the raw ceiling dips
    below the mean, because it models only goal upside and not clean-sheet variance.
    """
    from core import engine_events as _ee
    pos = means["position"]
    goal_pts = GOAL_PTS.get(pos, 4)
    base = expected_points(means)
    p_goals = _ee.percentile(goal_samples, q)
    raw = base - means.get("goals", 0.0) * goal_pts + p_goals * goal_pts
    return max(base, raw)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_fpl_model -v`
Expected: PASS (54 tests)

- [ ] **Step 5: Commit**

```bash
git add games/fpl/model.py tests/test_fpl_model.py
git commit -m "feat(fpl): total_points assembly + goal-variance ceiling"
```

---

## Task 18: Wire the gameweek run path

**Files:**
- Modify: `games/fpl/model.py`
- Modify: `config.py`
- Modify: `manage.py`

This is the integration task: fetch, build priors, register fixtures, run the sim with both
engine extensions, and print the order book.

- [ ] **Step 1: Add the config entry**

In `config.py`, add `fpl` to the `GAMES` dict:

```python
GAMES = {
    "fpl":         {"team": "Granat65",     "research_weight": 0.30, "objective": "mean"},
    "fifa":        {"team": "Granat65",     "research_weight": 0.30, "objective": "mean"},
    "holdet_gold": {"team": "Alwaysss 2nd", "research_weight": 0.10, "objective": "mean"},
    "holdet_yolo": {"team": "Always 2nd 2", "research_weight": 0.50, "objective": "ceiling"},
    "holdet_free": {"team": "Always 2nd",   "research_weight": 0.25, "objective": "mean"},
    "malspillet":  {"team": None,           "research_weight": 0.05, "objective": "odds"},
}
```

- [ ] **Step 2: Add the loader and run function**

Append to `games/fpl/model.py`:

```python
# --- run path -------------------------------------------------------------

def load_gameweek(gameweek: int, refresh: bool = False):
    """Load FPL data, register the gameweek's fixtures and deadline, build priors.

    Returns (priors_by_team, players_by_name, cold_start_flags).
    """
    from core import fixtures, fpl_api, fpl_priors

    boot = fpl_api.read_cache("bootstrap")
    raw_fx = fpl_api.read_cache("fixtures")
    if refresh or boot is None or raw_fx is None:
        boot, raw_fx = fpl_api.refresh()

    teams = fpl_api.parse_teams(boot)
    events = fpl_api.parse_events(boot)
    players = fpl_api.parse_players(boot)

    # Register this gameweek's fixtures with the shared schedule.
    rows = [r for r in fpl_api.parse_fixtures(raw_fx, teams)
            if r["fantasy_round"] == gameweek]
    existing = {f.match_id for f in fixtures.SCHEDULE}
    for r in rows:
        if r["match_id"] in existing:
            continue
        fixtures.SCHEDULE.append(fixtures.Fixture(
            match_id=r["match_id"], home=r["home"], away=r["away"],
            kickoff=fpl_api._parse_utc(r["kickoff_utc"]),
            stage="GW", fantasy_round=r["fantasy_round"], neutral=False,
        ))
    if gameweek in events:
        fixtures.set_deadline(gameweek, events[gameweek]["deadline"])

    # team_matches: how many matches the per-90 sample covers. Preseason the feed
    # carries last season's totals, so a full 38. Once the season starts this should
    # become matches played so far -- tracked by the caller as history accumulates.
    team_matches = 38
    priors_by_team, flags = fpl_priors.build_with_flags(players, team_matches)
    return priors_by_team, {p["name"]: p for p in players}, flags


def run(state: dict, fantasy_round: int, sims: int = 50_000) -> None:
    """Print the FPL order book for one gameweek."""
    from core import engine_events

    priors_by_team, players_by_name, flags = load_gameweek(fantasy_round)
    if flags:
        print(f"  [fpl] {len(flags)} player(s) on the price-based cold-start prior "
              f"(no PL history): "
              f"{', '.join(f['name'] for f in flags[:6])}"
              f"{' ...' if len(flags) > 6 else ''}")

    baselines = {}
    for name, p in players_by_name.items():
        minutes = p.get("minutes") or 0
        if minutes > 0:
            baselines[name] = (p.get("bps") or 0) * 90.0 / minutes

    bonus = BonusAccumulator(baselines)
    samples, _matches = engine_events.simulate_round(
        fantasy_round, sims=sims,
        priors=lambda team: priors_by_team.get(team, []),
        research_weight=state.get("research_weight", 0.3),
        per_match_hook=bonus.observe,
    )
    means = engine_events.event_means(samples)

    rows = []
    for name, ps in samples.items():
        m = means[name]
        # conceded is accumulated as a running total; rebuild the per-sim series
        # the threshold needs from the mean over the sims the player appeared in.
        conceded_samples = _conceded_series(ps)
        pts = total_points(m, ps, conceded_samples, bonus=bonus.expected(name))
        meta = players_by_name.get(name, {})
        rows.append({
            "name": name, "team": m["team"], "position": m["position"],
            "x_points": pts, "price": meta.get("price"),
            "ownership_pct": meta.get("ownership"),
            "ceiling": ceiling_points(m, ps.goal_samples),
            "bonus": bonus.expected(name),
            "defcon": defcon_points(m["position"], ps.defcon_samples),
        })
    rows.sort(key=lambda r: -r["x_points"])

    print(f"\n=== FPL — gameweek {fantasy_round} order book ===")
    print(f"\n{'xPts':>6} {'ceil':>6} {'bon':>5} {'dfc':>5}  "
          f"{'player':<20} {'team':<5} pos  price")
    for r in rows[:30]:
        price = f"{r['price']:.1f}" if r["price"] else "  - "
        print(f"{r['x_points']:6.2f} {r['ceiling']:6.2f} {r['bonus']:5.2f} "
              f"{r['defcon']:5.2f}  {r['name']:<20} {r['team']:<5} "
              f"{r['position']:<4} {price}")

    if state.get("squad") and not state["squad"][0].get("_example"):
        _print_squad_view(state, {r["name"]: r for r in rows})
    else:
        print("\n  [fpl] state.json not populated — add your 15 to see the squad view.")


def _conceded_series(sample) -> list:
    """Per-sim conceded counts for the -1-per-2 threshold.

    The engine accumulates `conceded` as a total rather than a list (goals conceded
    is a team-level quantity, so keeping 50k per-player copies would waste memory).
    Reconstruct a two-point series around the mean, which preserves the threshold's
    convexity better than applying the divisor to the mean alone.
    """
    if not sample.played:
        return []
    mean = sample.conceded / sample.played
    lo, hi = int(mean), int(mean) + 1
    frac = mean - lo
    return [lo] * max(1, int(round((1 - frac) * 100))) + [hi] * max(0, int(round(frac * 100)))


def _print_squad_view(state: dict, by_name: dict) -> None:
    print("\nYour squad:")
    total = 0.0
    for p in state["squad"]:
        r = by_name.get(p["name"])
        xp = r["x_points"] if r else 0.0
        tag = " (B)" if not p.get("is_starter") else ""
        if p.get("is_starter"):
            total += xp
        flag = "" if r else "  <- not modelled (name mismatch?)"
        print(f"  {xp:6.2f}  {p['name']:<20} {p.get('team', ''):<5}"
              f"{p.get('position', ''):<4}{tag}{flag}")
    print(f"\n  projected XI total: {total:.1f}")
```

- [ ] **Step 3: Register the game in the CLI**

In `manage.py`, add `fpl` to the game list:

```python
GAMES = ["fpl", "fifa", "holdet_gold", "holdet_yolo", "holdet_free", "malspillet"]
```

- [ ] **Step 4: Run the order book end to end**

This hits the network once to populate `data/fpl/`, then runs a small sim:

```bash
python manage.py fpl --round 1 --sims 2000
```

Expected: an `=== FPL — gameweek 1 order book ===` header followed by 30 rows ordered by
`xPts`, with Haaland near the top, non-zero `bon` values, non-zero `dfc` for defenders and
midfielders, and a cold-start notice naming promoted-club players.

Sanity checks to eyeball:
- goalkeepers should not appear in the top 10 on xPts
- `dfc` should be 0.00 for every goalkeeper and for most forwards
- `ceil` should be greater than or equal to `xPts` on every row

- [ ] **Step 5: Confirm no regressions**

Run: `python -m unittest discover -s tests -t .`
Expected: OK

- [ ] **Step 6: Commit**

```bash
git add games/fpl/model.py config.py manage.py
git commit -m "feat(fpl): gameweek run path — load, simulate, print the order book"
```

---

## Task 19: Full-suite verification and CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run the whole suite and record the count**

Run: `python -m unittest discover -s tests -t .`
Expected: OK. Note the total test count — it should be the pre-existing count plus roughly
100 new tests.

- [ ] **Step 2: Confirm the World Cup path still works**

The regression gate is that WC grading is untouched:

```bash
python manage.py fifa --round 5 --sims 2000
```

Expected: the FIFA order book prints as before, unaffected by the engine changes.

- [ ] **Step 3: Write the CHANGELOG entry**

Add at the top of `CHANGELOG.md`, under the `# Changelog` header and its preamble:

```markdown
## 2026-07-28 — FPL port, phases 1-2 (data layer + model)

- **FPL data layer** (`core/fpl_api.py`) — official API client for
  `bootstrap-static` / `fixtures` / `element-summary`, cached to `data/fpl/`.
  Network isolated in `fetch_*`; all `parse_*` pure and fixture-tested offline.
  Deadlines are read in UTC from `events[].deadline_time` — the official rules
  page localises them to the viewer's timezone and must never be scraped.
- **xG-derived priors** (`core/fpl_priors.py`) — the player layer inverts from
  market-derived to xG-derived, because ESPN carries NO player-level props for
  `eng.1` (verified: all 172 prop markets on a sampled GW1 fixture were
  match-level). FPL's own feed ships last season's per-90 rates, so there is no
  cold start for established players. Promoted-club players and new signings fall
  back to a position-and-price prior and are flagged in the run output.
  Availability gating from `status` + `chance_of_playing_next_round` addresses the
  crude-minutes weakness logged in STRATEGY.md §9.
- **Engine extensions** (`core/engine_events.py`) — all additive, WC behaviour
  unchanged: an injectable `priors` provider (resolved once, no longer called
  inside the sim loop); raw `conceded` alongside FIFA's `conc_beyond`, because
  FPL's -1-per-2 is not derivable from `max(0, ga-1)`; `played_60` for FPL's
  1-vs-2 appearance tiers; per-sim `save_samples` and `defcon_samples`, because
  `E[floor(x/n)] != floor(E[x]/n)`; and a `per_match_hook` for rank-within-match
  quantities.
- **FPL scoring** (`games/fpl/model.py`) — 2026/27 table with GK goals at 10 and
  DefCon paying forwards. Both divisors (1 point per 3 saves, -1 per 2 conceded)
  are pinned from the official rules page, NOT from `game_config.scoring`, which
  reports unit values and mis-prices every goalkeeper if read literally. DefCon is
  modelled as `2 x P(count >= threshold)`, not as a rate.
- **Bonus points** — rank-within-match from a per-90 BPS baseline plus exact
  event deltas from the official BPS table. Reconstructing BPS from components is
  impossible (30+ components including crosses, dribbles and pass-completion
  tiers, none of which we can observe), so unobservable components ride in the
  baseline.
- Calibration status: **uncalibrated**. No realized FPL data exists until GW1
  completes. The backtest harness grades from GW1 forward.
- Tests: `test_fpl_api.py`, `test_fpl_priors.py`, `test_fpl_model.py`,
  `test_fixtures_gameweek.py` (synthetic blanks/doubles — the live feed is a clean
  10 fixtures per gameweek and will not exhibit them for months),
  `test_engine_priors.py`.
- Spec: `docs/superpowers/specs/2026-07-28-fpl-port-design.md`.
```

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: changelog for FPL port phases 1-2"
```

---

## Definition of done

- [ ] `python -m unittest discover -s tests -t .` passes, with the pre-existing tests still green
- [ ] `python manage.py fpl --round 1 --sims 2000` prints a plausible order book
- [ ] `python manage.py fifa --round 5 --sims 2000` still works — the regression gate
- [ ] Goalkeeper saves and goals conceded are computed from per-sim counts, never from means
- [ ] DefCon is a threshold probability, is 0 for every goalkeeper, and is capped at 2
- [ ] Bonus is non-zero and rank-derived
- [ ] Cold-start players are flagged in the run output
- [ ] `games/fpl/rules.md` records provenance for every constant

## Follow-on plans

- **Phase 3** — sim caching (`core/simcache.py`) keyed on odds, priors, config and a model-source fingerprint. Independent of this plan.
- **Phase 4** — the six GW1 articles, `/fpl/gw{N}/` URLs, preflight extensions. Depends on this plan and Phase 3.

## Known deferrals carried into Phase 3 or later

- **Spec §7.1's last-season/in-season rate blend is only partially implemented.** The dial (`config.FPL_PRIOR_SHRINKAGE_MATCHES`) is defined but not yet consumed, and `team_matches` is hard-coded to 38 in `load_gameweek`. This is deliberate, not an oversight: preseason there is no in-season data to blend toward, so the shrinkage is a no-op for GW1 and implementing it now would be untestable against real numbers. It must be wired before GW2, when `team_matches` becomes matches-played-so-far and the blend starts to bite.
- `_conceded_series` reconstructs a two-point distribution around the mean rather than keeping per-sim counts. Deliberate memory trade — goals conceded is team-level, so per-player copies would be wasteful. If Phase 4's defender articles prove sensitive to it, promote `conceded` to a sampled list.
- ESPN odds are not yet wired into the FPL path; fixtures fall back to `ratings.py` priors for lambdas. Wiring `--refresh` through `core/espn.py` with `ESPN_LEAGUE="eng.1"` belongs with Phase 4's fixture ticker, which is the first consumer that needs real clean-sheet probabilities.
