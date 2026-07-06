"""Tests for the /rate/ tool: the self-hosted JS asset, the CLI's pure helper
functions (name matching + sub-chain notes), and (when local data/ caches are
available) an end-to-end smoke build of the players.json feed and /rate/ page."""

import importlib.util
import json
import os
import re
import shutil
import tempfile
import unittest
from unittest import mock

from evmax import build, render

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_JS_PATH = os.path.join(_REPO_ROOT, "evmax", "assets", "js", "rate.js")
_CLI_PATH = os.path.join(_REPO_ROOT, "scripts", "rate_team.py")


def _load_rate_team_module():
    spec = importlib.util.spec_from_file_location("rate_team_cli", _CLI_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# Integration tests against the REAL local caches (data/ is gitignored, absent in CI).
_HAS_LIVE_DATA = os.path.exists(os.path.join(_REPO_ROOT, "data", "schedule.json"))
_NEEDS_DATA = unittest.skipUnless(_HAS_LIVE_DATA,
                                  "requires local data/ caches (skipped in CI)")


class RateJsAssetTest(unittest.TestCase):
    """The site's first first-party JavaScript: self-hosted, zero external
    requests. build.py copies this file verbatim into dist/js/, so its
    content on disk IS what ships."""

    def setUp(self):
        with open(_JS_PATH, encoding="utf-8") as fh:
            self.js = fh.read()

    def test_file_exists_and_is_nonempty(self):
        self.assertTrue(os.path.exists(_JS_PATH))
        self.assertGreater(len(self.js), 500)

    def test_no_external_http_urls(self):
        # Any literal http(s):// URL would indicate a third-party request --
        # the only network call this script makes is a same-origin relative
        # fetch to /api/round/{N}/players.json.
        self.assertNotIn("http://", self.js)
        self.assertNotIn("https://", self.js)

    def test_no_cookies_or_web_storage(self):
        # The header comment mentions "localStorage/sessionStorage" (to declare
        # that none is used) -- assert on actual API usage, not the file text.
        code = "\n".join(
            line for line in self.js.splitlines()
            if not line.strip().startswith(("//", "*", "/*")))
        self.assertNotIn("document.cookie", code)
        self.assertNotIn("localStorage.", code)
        self.assertNotIn("sessionStorage.", code)

    def test_declares_self_hosted_zero_tracking_policy_in_header_comment(self):
        header = self.js[:1200]
        self.assertIn("self-hosted", header.lower())
        self.assertTrue(
            re.search(r"no\s+tracking|zero\s+tracking|no analytics", header, re.IGNORECASE))

    def test_fetches_players_json_same_origin(self):
        self.assertIn("fetch(playersUrl", self.js)

    def test_ports_norm_matching_semantics(self):
        # normalize() must lowercase, strip diacritics via NFD, and keep only
        # alnum -- same contract as scripts/rate_team.py's _norm().
        self.assertIn("normalize(\"NFD\")", self.js)
        self.assertIn("toLowerCase", self.js)

    def test_parses_bench_tag(self):
        self.assertIn('"(b)"', self.js)

    def test_has_chain_note_and_xi_only_total_label(self):
        self.assertIn("chainNote", self.js)
        self.assertIn("XI only", self.js)

    def test_has_optimal_xi_and_ceiling(self):
        self.assertIn("optimalXi", self.js)
        self.assertIn("optimalSummary", self.js)
        self.assertIn("ceilingTotal", self.js)

    def test_has_round_and_hero_button_hooks(self):
        # slot picker / round-switcher live in render.py markup, not this JS --
        # just confirm the datalist-filling wiring this feature depends on.
        self.assertIn("fillDatalist", self.js)
        self.assertIn("slotsAsText", self.js)


class RateTeamCliChainNoteTest(unittest.TestCase):
    """Unit tests for the CLI's pure helpers -- no engine/network needed, so
    these run in CI. chain_note() is the sub-chain logic: a bench player
    isn't a wasted slot if a same-position XI starter kicks off earlier,
    since manual subs (unlike DNP-only autosubs) are allowed up to the
    round's last kickoff."""

    def setUp(self):
        self.mod = _load_rate_team_module()

    def _row(self, name, position, kickoff):
        return {"name": name, "position": position, "x_points": 5.0,
                "captain_ev": 10.0, "kickoff": kickoff}

    def test_earlier_same_position_starter_gives_chain_note(self):
        starter = self._row("Early Guy", "FWD", "2026-07-06T19:00:00+00:00")
        bench = self._row("Late Guy", "FWD", "2026-07-07T16:00:00+00:00")
        note = self.mod.chain_note(bench, [starter])
        self.assertIn("Early Guy", note)
        self.assertIn("chain option", note)
        self.assertIn("21h", note)  # 19:00 Jul 6 -> 16:00 Jul 7 = 21h

    def test_no_note_when_bench_kicks_off_first(self):
        starter = self._row("Later Starter", "FWD", "2026-07-07T16:00:00+00:00")
        bench = self._row("Earlier Bench", "FWD", "2026-07-06T19:00:00+00:00")
        self.assertEqual(self.mod.chain_note(bench, [starter]), "")

    def test_no_note_across_different_positions(self):
        starter = self._row("Defender", "DEF", "2026-07-06T19:00:00+00:00")
        bench = self._row("Forward", "FWD", "2026-07-07T16:00:00+00:00")
        self.assertEqual(self.mod.chain_note(bench, [starter]), "")

    def test_no_note_without_kickoff_data(self):
        starter = self._row("Starter", "FWD", "2026-07-06T19:00:00+00:00")
        bench = {"name": "Bench Guy", "position": "FWD", "x_points": 5.0,
                  "captain_ev": 10.0, "kickoff": None}
        self.assertEqual(self.mod.chain_note(bench, [starter]), "")


class CaptainChainTest(unittest.TestCase):
    """captain_chain(): the armband can be rolled forward mid-round, so the
    tool should recommend a kickoff-ordered chain ending at the best static
    captain, with earlier links included only when their ceiling beats the
    anchor's single xPts (a haul worth locking)."""

    def setUp(self):
        self.mod = _load_rate_team_module()

    def _row(self, name, xp, cev, ceil, kickoff):
        return {"name": name, "position": "FWD", "x_points": xp,
                "captain_ev": cev, "ceiling": ceil, "kickoff": kickoff}

    def test_chain_orders_early_links_before_anchor(self):
        mbappe = self._row("Mbappe", 6.1, 12.2, 13.0, "2026-07-04T21:00:00+00:00")
        saibari = self._row("Saibari", 5.7, 11.4, 9.2, "2026-07-04T17:00:00+00:00")
        messi = self._row("Messi", 7.1, 14.2, 13.5, "2026-07-07T16:00:00+00:00")
        chain = self.mod.captain_chain([mbappe, messi, saibari])
        self.assertEqual([r["name"] for r in chain], ["Saibari", "Mbappe", "Messi"])

    def test_low_ceiling_early_player_excluded(self):
        # ceiling below the anchor's xPts -> a "haul" still loses to just
        # captaining the anchor, so he's not a link
        plodder = self._row("Plodder", 3.0, 6.0, 5.0, "2026-07-04T17:00:00+00:00")
        messi = self._row("Messi", 7.1, 14.2, 13.5, "2026-07-07T16:00:00+00:00")
        self.assertEqual(self.mod.captain_chain([plodder, messi]), [])

    def test_one_link_per_kickoff_slot_highest_cev_wins(self):
        a = self._row("Lesser", 5.0, 10.0, 9.0, "2026-07-04T21:00:00+00:00")
        b = self._row("Greater", 6.1, 12.2, 13.0, "2026-07-04T21:00:00+00:00")
        messi = self._row("Messi", 7.1, 14.2, 13.5, "2026-07-07T16:00:00+00:00")
        chain = self.mod.captain_chain([a, b, messi])
        self.assertEqual([r["name"] for r in chain], ["Greater", "Messi"])

    def test_no_chain_when_anchor_kicks_off_first(self):
        messi = self._row("Messi", 7.1, 14.2, 13.5, "2026-07-04T16:00:00+00:00")
        late = self._row("Late", 6.1, 12.2, 13.0, "2026-07-07T21:00:00+00:00")
        self.assertEqual(self.mod.captain_chain([messi, late]), [])


class OptimalXiTest(unittest.TestCase):
    """optimal_xi_and_total(): the honest comparison point for a rated squad
    -- the model's own best legal XI this round, by x_points, with its own
    best captain doubled."""

    def setUp(self):
        self.mod = _load_rate_team_module()

    def _row(self, name, pos, xp, cev, ceil):
        return {"name": name, "position": pos, "x_points": xp, "captain_ev": cev, "ceiling": ceil}

    def test_optimal_beats_or_ties_a_suboptimal_selection(self):
        rows = (
            [self._row(f"GK{i}", "GK", 3.0 + i * 0.1, 6.0, 3.0) for i in range(2)]
            + [self._row(f"DEF{i}", "DEF", 3.0 + i * 0.1, 6.0, 3.0) for i in range(6)]
            + [self._row(f"MID{i}", "MID", 4.0 + i * 0.1, 8.0, 6.0) for i in range(6)]
            + [self._row(f"FWD{i}", "FWD", 5.0 + i * 0.1, 10.0, 8.0) for i in range(4)]
        )
        xi, cap, total, ceiling_total = self.mod.optimal_xi_and_total(rows)
        self.assertEqual(len(xi), 11)
        self.assertEqual(cap["name"], "FWD3")  # highest captain_ev in the pool
        # captain counted twice: sum(xi) + cap's own x_points once more
        expected = sum(r["x_points"] for r in xi) + cap["x_points"]
        self.assertAlmostEqual(total, expected, places=6)
        self.assertGreater(total, 0)
        self.assertGreater(ceiling_total, 0)


@_NEEDS_DATA
class RateSmokeBuildTest(unittest.TestCase):
    """End-to-end smoke build into a temp dir: players.json shape + /rate/
    page + /js/rate.js all present, matching the CLI's data guardrails."""

    def setUp(self):
        self.out = tempfile.mkdtemp(prefix="evmax_rate_test_")
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)
        # The reddit kit is an operator artifact written outside `out` -- redirect
        # it too, so the smoke build can't overwrite the live data/reddit/ copy.
        patcher = mock.patch.object(build, "_REDDIT_DIR",
                                    os.path.join(self.out, "reddit"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_players_json_has_no_price_or_ownership(self):
        build.build(5, sims=200, out=self.out, url="https://evmax.ai", use_llm=False)
        path = os.path.join(self.out, "api", "round", "5", "players.json")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["round"], 5)
        self.assertIn("methodology", data)
        self.assertIn("license", data)
        self.assertGreater(len(data["players"]), 0)
        for p in data["players"]:
            self.assertIn("name", p)
            self.assertIn("team", p)
            self.assertIn("position", p)
            self.assertIn("x_points", p)
            self.assertIn("captain_ev", p)
            self.assertIn("ceiling", p)
            self.assertIn("kickoff", p)
            self.assertIn("flag", p)
            self.assertNotIn("price", p)
            self.assertNotIn("ownership_pct", p)
            self.assertNotIn("ownership", p)

    def test_rate_page_and_js_are_emitted(self):
        build.build(5, sims=200, out=self.out, url="https://evmax.ai", use_llm=False)
        self.assertTrue(os.path.exists(os.path.join(self.out, "rate", "index.html")))
        self.assertTrue(os.path.exists(os.path.join(self.out, "js", "rate.js")))
        with open(os.path.join(self.out, "rate", "index.html"), encoding="utf-8") as fh:
            html = fh.read()
        self.assertIn('id="team-input"', html)
        self.assertIn("/js/rate.js", html)


if __name__ == "__main__":
    unittest.main()
