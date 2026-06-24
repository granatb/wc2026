import json
import unittest

from evmax import render


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
