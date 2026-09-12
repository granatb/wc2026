"""The expert scan (owner decision 2026-09-12): a linked table of what the
public sources recommended, beside our own row."""
import json
import os
import tempfile
import unittest
from unittest import mock

from core import experts
from evmax import experts_page

SCAN = {
    "gameweek": 4, "checked_at": "2026-09-12T10:10:00+00:00",
    "sources": [
        {"key": "a", "name": "Source A", "url": "https://a.example/gw4", "published": "2026-09-11",
         "captain": "Palmer", "vice": "João Pedro", "transfers_in": ["Isak", "Rogers"],
         "transfers_out": [], "chip": None, "note": "Chelsea triple-up"},
        {"key": "b", "name": "Source B", "url": "https://b.example/gw4", "published": "2026-09-10",
         "captain": "B.Fernandes", "transfers_in": ["Isak"], "transfers_out": ["Szoboszlai"],
         "chip": "Free Hit"},
        {"key": "c", "name": "Source C", "url": "https://c.example/gw4", "published": "2026-09-11",
         "captain": "Palmer", "transfers_in": [], "transfers_out": []},
    ],
    "model": {"transfers_in": ["Palmer", "Thomas"], "transfers_out": ["Ndiaye", "Senesi"],
              "hold_against_the_crowd": ["Szoboszlai"]},
}
OUR = {"captain": "Cole Palmer", "vice": "Szoboszlai", "chip": {"gameweek": 4, "chip": "3xc"},
       "projected_total": 69.57, "squad": ["Cole Palmer", "Szoboszlai", "B.Fernandes", "Raya"]}


class ValidateTest(unittest.TestCase):
    def test_accepts_a_good_scan_and_rejects_a_bad_one(self):
        experts.validate(json.loads(json.dumps(SCAN)))
        for broken in (dict(SCAN, sources=[]), dict(SCAN, gameweek="4"),
                       dict(SCAN, sources=[dict(SCAN["sources"][0], url="not a link")]),
                       dict(SCAN, sources=[SCAN["sources"][0], SCAN["sources"][0]])):
            with self.assertRaises(ValueError):
                experts.validate(broken)

    def test_load_returns_none_without_a_file(self):
        with mock.patch.object(experts, "ROOT", tempfile.mkdtemp()):
            self.assertIsNone(experts.load(99))


class TalliesTest(unittest.TestCase):
    def test_counts_and_comparison(self):
        t = experts.tallies(SCAN)
        self.assertEqual(t["captains"][0], ("Palmer", 2))
        self.assertEqual(t["transfers_in"][0], ("Isak", 2))
        c = experts.compare_with_model(SCAN, OUR)
        self.assertTrue(c["captain_agreement"])          # Palmer == Cole Palmer
        self.assertIn("Isak", c["they_buy_we_lack"])
        self.assertNotIn("Palmer", c["they_buy_we_lack"])   # we own him
        self.assertEqual(c["they_sell_we_hold"], ["Szoboszlai"])

    def test_same_player_is_loose_on_spelling(self):
        self.assertTrue(experts.same_player("Palmer", "Cole Palmer"))
        self.assertTrue(experts.same_player("Bruno Fernandes", "B.Fernandes"))
        self.assertTrue(experts.same_player("Joao Pedro", "João Pedro"))
        self.assertFalse(experts.same_player("Palmer", "Saka"))


class PageTest(unittest.TestCase):
    def test_every_source_is_linked_and_our_row_is_present(self):
        from evmax import render
        html = experts_page.page_html(SCAN, 4, OUR, date_str="12 September 2026", section=render.FPL)
        for s in SCAN["sources"]:
            self.assertIn(f'href="{s["url"]}"', html)
            self.assertIn(s["name"], html)
        self.assertIn('class="xp-ours"', html)
        self.assertIn("Triple Captain", html)
        self.assertIn("Cole Palmer", html)
        self.assertIn("Where they agree, where they split", html)
        self.assertIn("Palmer leads the sources with 2 of 3", html)
        self.assertIn("held by us: Szoboszlai", html)
        # derived-only: no numbers of theirs on the page
        self.assertNotIn("7.8", html)

    def test_feed_entry_and_json_twin(self):
        card = experts_page.feed_entry(SCAN, OUR)
        self.assertEqual(card["slug"], "experts")
        self.assertEqual(card["stat_value"], "3")
        self.assertIn("agree on the armband", card["teaser"])
        j = experts_page.public_json(SCAN, OUR)
        self.assertEqual(j["comparison"]["top_captain"], "Palmer")
        self.assertEqual(j["tallies"]["transfers_in"][0], ["Isak", 2] if isinstance(j["tallies"]["transfers_in"][0], list) else ("Isak", 2))


class BuildTest(unittest.TestCase):
    def test_page_feed_card_and_sitemap_appear_when_a_scan_exists(self):
        from evmax import fpl_build, render
        from core import fpl_api
        if fpl_api.read_cache("bootstrap") is None:
            self.skipTest("local FPL cache unavailable")
        site_url = render.SITE_URL
        try:
            with tempfile.TemporaryDirectory() as tmp, \
                 mock.patch.object(experts, "load", side_effect=lambda gw: dict(SCAN, gameweek=gw)):
                fpl_build.build(1, 200, tmp, use_llm=False, live=False, preview=False)
                page = open(os.path.join(tmp, "fpl/gw1/experts/index.html"), encoding="utf-8").read()
                self.assertIn("What the experts say", page)
                self.assertIn('href="https://a.example/gw4"', page)
                landing = open(os.path.join(tmp, "index.html"), encoding="utf-8").read()
                self.assertIn('href="/fpl/gw1/experts/"', landing)
                self.assertIn("Sources read", landing)
                sitemap = open(os.path.join(tmp, "sitemap.xml"), encoding="utf-8").read()
                self.assertIn("/fpl/gw1/experts/", sitemap)
                self.assertTrue(os.path.exists(os.path.join(tmp, "api/fpl/gw1/experts.json")))
        finally:
            render.SITE_URL = site_url
