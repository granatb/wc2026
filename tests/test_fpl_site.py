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
# captain_ev included because article_page("captains", ...) always derives its
# meta description through summary_sentence, which reads it.
_ENTRIES = [{"name": "A", "rank": 1, "x_points": 6.0, "price": 5.0,
             "captain_ev": 12.0}]


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


class TestArticleMdSection(unittest.TestCase):
    def test_fpl_markdown_twin_points_at_the_fpl_tree(self):
        md = render.article_md(1, "captains", "T", _PROSE, _ENTRIES, ["x_points"],
                               "2026-08-20T00:00:00+00:00", "20 August 2026",
                               canonical_path="/fpl/gw1/captains/",
                               section=render.FPL)
        self.assertIn("/api/fpl/gw1/captains.json", md)
        self.assertNotIn("/api/round/", md)


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

    def test_world_cup_prompt_does_not_carry_the_fpl_glossary(self):
        p = prompts.build_prompt("captains", 5, _ENTRIES)
        self.assertNotIn("p_defcon", p)
