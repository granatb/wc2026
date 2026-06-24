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

    def test_summary_sentence_efficiency_mentions_value(self):
        entries = [{"name": "Amad Diallo", "team": "CIV", "x_points": 8.55, "price": 5.5,
                    "value": 1.55, "ownership_pct": 1.0}]
        s = render.summary_sentence("efficiency", entries)
        self.assertIn("Amad Diallo", s)
        self.assertIn("8.55", s)   # xPts
        self.assertIn("5.5", s)    # price


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


# ── sample data shared by HtmlTest, PitchSvgTest, EvBarTest ──────────────────

_SAMPLE_XI = [
    {"rank": 1,  "name": "Harry Kane",    "team": "ENG", "position": "FWD",
     "x_points": 9.16, "captain_ev": 18.31, "ownership_pct": 38.6},
    {"rank": 2,  "name": "Lionel Messi",  "team": "ARG", "position": "FWD",
     "x_points": 9.03, "captain_ev": 18.06, "ownership_pct": 25.8},
    {"rank": 3,  "name": "Amad Diallo",   "team": "CIV", "position": "FWD",
     "x_points": 8.55, "captain_ev": 17.10, "ownership_pct": 1.0},
    {"rank": 4,  "name": "Florian Wirtz", "team": "GER", "position": "MID",
     "x_points": 7.80, "captain_ev": 15.60, "ownership_pct": 12.0},
    {"rank": 5,  "name": "Ismael Saibari","team": "MAR", "position": "MID",
     "x_points": 7.50, "captain_ev": 15.00, "ownership_pct": 3.0},
    {"rank": 6,  "name": "Phil Foden",    "team": "ENG", "position": "MID",
     "x_points": 7.20, "captain_ev": 14.40, "ownership_pct": 18.0},
    {"rank": 7,  "name": "Jamal Musiala", "team": "GER", "position": "MID",
     "x_points": 7.00, "captain_ev": 14.00, "ownership_pct": 22.0},
    {"rank": 8,  "name": "Noussair Mazraoui", "team": "MAR", "position": "DEF",
     "x_points": 5.80, "captain_ev": 11.60, "ownership_pct": 8.0},
    {"rank": 9,  "name": "Kieran Trippier","team": "ENG", "position": "DEF",
     "x_points": 5.60, "captain_ev": 11.20, "ownership_pct": 14.0},
    {"rank": 10, "name": "David Raum",    "team": "GER", "position": "DEF",
     "x_points": 5.40, "captain_ev": 10.80, "ownership_pct": 6.0},
    {"rank": 11, "name": "Yassine Bounou","team": "MAR", "position": "GK",
     "x_points": 5.00, "captain_ev": 10.00, "ownership_pct": 11.0},
]

_SAMPLE_PROSE = {
    "headline": "Back Kane — but the brave move is Amad Diallo.",
    "standfirst": ("50,000 simulations make England's striker the safe armband. "
                   "They also flag a 1%-owned forward as the highest-leverage punt."),
    "body_html": ("<p>The model ran every Round 3 fixture 50,000 times. "
                  "<b>Harry Kane</b> comes out on top: 9.16 expected points, "
                  "or <b>18.31 as captain</b>.</p>"),
    "bottom_line": "Hold Kane if you have him.",
    "source": "template",
}


class HtmlTest(unittest.TestCase):
    def setUp(self):
        self.entries = [
            {"rank": 1, "name": "Bruno Fernandes", "team": "Portugal", "position": "MID",
             "x_points": 5.67, "captain_ev": 11.34, "ceiling": 9.1, "price": 9.5,
             "ownership_pct": 18.0, "value": 0.6, "kickoff": "2026-06-27T23:30:00+00:00"},
        ]
        self.nav = [("captains", "Best captain picks"), ("best-xi", "Best World Cup Fantasy XI")]
        self.prose = {
            "headline": "Bruno Fernandes leads the captain board",
            "standfirst": "Portugal's midfielder tops this round's captain EV at 11.34.",
            "body_html": "<p>Bruno Fernandes projects <b>11.34 captain EV</b> this round.</p>",
            "bottom_line": "Captain Bruno Fernandes.",
            "source": "template",
        }
        self.viz_html = '<svg viewBox="0 0 100 40"><rect width="80" height="20" fill="#0f7a45"/></svg>'

    def test_article_page_has_head_jsonld_table_and_summary(self):
        h = render.article_page(
            round_no=3, article="captains",
            title="Best captain picks — Round 3",
            prose=self.prose,
            entries=self.entries, columns=["captain_ev", "x_points"],
            nav=self.nav, json_url="/api/round/3/captains.json",
            viz_html=self.viz_html,
            generated_at="2026-06-24T12:00:00+00:00")
        self.assertIn("<!doctype html>", h.lower())
        self.assertIn("application/ld+json", h)         # JSON-LD present
        self.assertIn("Bruno Fernandes", h)
        self.assertIn("11.3", h)                         # captain EV appears in table
        self.assertIn('rel="alternate"', h)              # link to JSON
        self.assertIn("Best World Cup Fantasy XI", h)    # cross-link nav
        self.assertIn("Monte-Carlo", h)                  # methodology

    def test_article_page_has_article_schema_and_prose_headline(self):
        h = render.article_page(
            round_no=3, article="captains",
            title="Best captain picks — Round 3",
            prose=self.prose,
            entries=self.entries, columns=["captain_ev", "x_points"],
            nav=self.nav, json_url="/api/round/3/captains.json",
            viz_html=self.viz_html,
            generated_at="2026-06-24T12:00:00+00:00")
        self.assertIn('"Article"', h)                           # Article JSON-LD type
        self.assertIn(self.prose["headline"], h)                # prose headline rendered
        self.assertIn("datePublished", h)                       # datePublished in Article LD
        self.assertIn("2026-06-24T12:00:00+00:00", h)          # generated_at value present
        self.assertNotIn("&amp;", h.split(
            '<script type="application/ld+json">')[1].split("</script>")[0])  # no double-escaping in LD

    def test_hub_page_links_all_articles(self):
        h = render.hub_page(round_no=3, nav=self.nav,
                            highlights={"captains": "Captain Bruno Fernandes (11.3 EV)"})
        self.assertIn("Best captain picks", h)
        self.assertIn("/round/3/captains/", h)
        self.assertIn("Captain Bruno Fernandes", h)

    def test_landing_page_featured_and_feed(self):
        feed = [
            {"slug": "best-xi", "headline": "The model's Round 3 XI",
             "teaser": "A 3-4-3 built around Kane.", "stat_value": "58.7",
             "stat_label": "total xPts"},
            {"slug": "differentials", "headline": "Three low-owned forwards worth picking",
             "teaser": "Diallo leads the differential board.",
             "stat_value": "1.0%", "stat_label": "top pick owned"},
            {"slug": "best-value-xi", "headline": "Best value XI this round",
             "teaser": "Diallo at 1.45 xPts/million.",
             "stat_value": "1.45", "stat_label": "xPts / million"},
        ]
        featured = {
            "slug": "captains",
            "prose": _SAMPLE_PROSE,
            "viz_html": self.viz_html,
        }
        h = render.landing_page(round_no=3, featured=featured, feed=feed, nav=self.nav)
        self.assertIn(_SAMPLE_PROSE["headline"], h)             # featured headline
        self.assertIn("Round 3 XI", h)                          # feed card 1 (apostrophe escaped)
        self.assertIn("Three low-owned forwards worth picking", h)  # feed card 2
        self.assertIn("Best value XI this round", h)            # feed card 3
        self.assertIn("/round/3/best-xi/", h)                   # feed card links
        self.assertIn("/round/3/differentials/", h)
        self.assertIn("/round/3/captains/", h)                  # featured link


class PitchSvgTest(unittest.TestCase):
    def test_pitch_svg_returns_svg(self):
        svg = render.pitch_svg(_SAMPLE_XI)
        self.assertTrue(svg.startswith("<svg"), "pitch_svg should return an SVG element")
        self.assertIn("</svg>", svg)

    def test_pitch_svg_contains_11_surnames(self):
        svg = render.pitch_svg(_SAMPLE_XI)
        # Each player's last name should appear as a text node
        for entry in _SAMPLE_XI:
            surname = entry["name"].split()[-1]
            self.assertIn(surname, svg,
                          f"surname '{surname}' not found in pitch SVG")

    def test_pitch_svg_flags_captain(self):
        svg = render.pitch_svg(_SAMPLE_XI)
        # Captain badge: red circle with "C" label
        self.assertIn(">C<", svg, "captain badge 'C' not found in pitch SVG")


class EvBarTest(unittest.TestCase):
    def setUp(self):
        self.entries = [
            {"name": "Harry Kane",   "captain_ev": 18.31, "ownership_pct": 38.6},
            {"name": "Lionel Messi", "captain_ev": 18.06, "ownership_pct": 25.8},
            {"name": "Amad Diallo",  "captain_ev": 17.10, "ownership_pct": 1.0},
        ]

    def test_ev_bar_returns_svg(self):
        svg = render.ev_bar(self.entries, "captain_ev")
        self.assertTrue(svg.startswith("<svg"), "ev_bar should return an SVG element")
        self.assertIn("</svg>", svg)

    def test_ev_bar_contains_top_value(self):
        svg = render.ev_bar(self.entries, "captain_ev")
        # Top value 18.31 should appear as a label
        self.assertIn("18.31", svg)

    def test_ev_bar_empty_is_safe(self):
        svg = render.ev_bar([], "captain_ev")
        self.assertTrue(svg.startswith("<svg"))


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
