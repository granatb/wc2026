"""Tests for the /rate/ tool: the self-hosted JS asset, and (when local data/
caches are available) an end-to-end smoke build of the players.json feed and
/rate/ page."""

import json
import os
import re
import shutil
import tempfile
import unittest

from evmax import build, render

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_JS_PATH = os.path.join(_REPO_ROOT, "evmax", "assets", "js", "rate.js")

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


@_NEEDS_DATA
class RateSmokeBuildTest(unittest.TestCase):
    """End-to-end smoke build into a temp dir: players.json shape + /rate/
    page + /js/rate.js all present, matching the CLI's data guardrails."""

    def setUp(self):
        self.out = tempfile.mkdtemp(prefix="evmax_rate_test_")
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)

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
