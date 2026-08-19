"""Phase 4: FPL section rendering, preflight and the end-to-end gameweek build."""
from __future__ import annotations

import json
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


_TICKER_ENTRY = {"name": "ARS", "rank": 1, "opponents": "LIV (H)", "fixtures": 1,
                 "exp_clean_sheets": 0.42, "exp_goals_for": 1.9,
                 "exp_goals_against": 0.9, "env": "balanced", "basis": "market"}
_DEFCON_ENTRY = {"name": "Gabriel", "rank": 1, "position": "DEF", "team": "ARS",
                 "p_defcon": 0.71, "defcon": 1.42, "defcon_threshold": 10,
                 "x_points": 5.4, "price": 6.0}


class TestFplTemplates(unittest.TestCase):
    def _prose(self, slug, entries):
        return writer.article_prose(slug, 1, entries, ["x_points"],
                                    cache_dir="/nonexistent", use_llm=False,
                                    cache_name="fpl-gw1", unit="Gameweek")

    def test_every_fpl_slug_has_a_real_template(self):
        cases = {
            "captains": [dict(_ENTRIES[0], captain_ev=12.0, ceiling=10.0,
                              kickoff_order=1, team="ARS", position="FWD")],
            "wildcard": [dict(_ENTRIES[0], role="XI", team="ARS", position="MID",
                              ceiling=9.0)],
            "ticker": [_TICKER_ENTRY],
            "defenders": [dict(_ENTRIES[0], position="DEF", team="ARS",
                               cs_points=1.6, defcon=1.4, bonus=0.5, ceiling=9.0)],
            "efficiency": [dict(_ENTRIES[0], value=1.2, tier="Budget", team="ARS",
                                position="MID", ceiling=9.0)],
            "defcon": [_DEFCON_ENTRY],
        }
        for slug, entries in cases.items():
            prose = self._prose(slug, entries)
            with self.subTest(slug=slug):
                self.assertNotIn("analysis:", prose["headline"].lower(),
                                 f"{slug} fell through to the generic template")
                self.assertTrue(prose["standfirst"])
                self.assertTrue(prose["bottom_line"])
                self.assertIn("<p>", prose["body_html"])

    def test_defcon_prose_states_the_probability_and_threshold(self):
        prose = self._prose("defcon", [_DEFCON_ENTRY])
        self.assertIn("71", prose["standfirst"] + prose["body_html"])
        self.assertIn("10", prose["body_html"])

    def test_ticker_prose_names_blanks(self):
        entries = [_TICKER_ENTRY,
                   dict(_TICKER_ENTRY, name="EVE", rank=2, fixtures=0,
                        opponents="—", exp_clean_sheets=0.0, env="blank",
                        basis="—")]
        prose = self._prose("ticker", entries)
        self.assertIn("EVE", prose["body_html"])
        self.assertIn("blank", prose["body_html"].lower())

    def test_empty_entries_do_not_crash_any_slug(self):
        for slug in ("captains", "wildcard", "ticker", "defenders", "efficiency",
                     "defcon"):
            with self.subTest(slug=slug):
                prose = self._prose(slug, [])
                self.assertTrue(prose["headline"])


from datetime import datetime, timezone
from unittest import mock

from core import fixtures as core_fixtures
from evmax import fpl_build


def _fx(match_id, home, away, gw=1, priced=True):
    return core_fixtures.Fixture(
        match_id=match_id, home=home, away=away,
        kickoff=datetime(2026, 8, 21, 19, 0, tzinfo=timezone.utc),
        stage="GW", fantasy_round=gw, neutral=False,
        lam_home=1.5 if priced else None, lam_away=1.1 if priced else None)


class TestFplPreflight(unittest.TestCase):
    def test_aborts_when_the_gameweek_has_no_fixtures(self):
        with mock.patch.object(core_fixtures, "by_round", return_value=[]):
            with self.assertRaises(SystemExit) as ctx:
                fpl_build.preflight(1, players=[{"status": "i"}], cold_start=[])
        self.assertIn("no fixtures", str(ctx.exception).lower())

    def test_warns_on_unpriced_fixtures(self):
        fx = [_fx("m1", "ARS", "LIV"), _fx("m2", "BUR", "EVE", priced=False)]
        with mock.patch.object(core_fixtures, "by_round", return_value=fx):
            warnings = fpl_build.preflight(1, players=[{"status": "i"}],
                                           cold_start=[])
        self.assertTrue(any("BUR" in w and "unpriced" in w.lower()
                            for w in warnings))

    def test_warns_on_cold_start_players(self):
        fx = [_fx("m1", "ARS", "LIV")]
        with mock.patch.object(core_fixtures, "by_round", return_value=fx):
            warnings = fpl_build.preflight(
                1, players=[{"status": "i"}],
                cold_start=[{"name": "Newbie"}, {"name": "Rookie"}])
        self.assertTrue(any("cold-start" in w.lower() and "Newbie" in w
                            for w in warnings))

    def test_warns_when_no_player_carries_an_availability_flag(self):
        """Real FPL always has injuries. A bootstrap where all 563 players are
        status 'a' is a stale cache, and it would silently publish ruled-out
        players as nailed starters."""
        fx = [_fx("m1", "ARS", "LIV")]
        with mock.patch.object(core_fixtures, "by_round", return_value=fx):
            warnings = fpl_build.preflight(
                1, players=[{"status": "a"}, {"status": "a"}], cold_start=[])
        self.assertTrue(any("stale" in w.lower() for w in warnings))

    def test_no_stale_warning_when_flags_are_present(self):
        fx = [_fx("m1", "ARS", "LIV")]
        with mock.patch.object(core_fixtures, "by_round", return_value=fx):
            warnings = fpl_build.preflight(
                1, players=[{"status": "a"}, {"status": "i"}], cold_start=[])
        self.assertFalse(any("stale" in w.lower() for w in warnings))

    def test_unexpected_cache_miss_is_reported(self):
        """A miss with no stored artifact for this gameweek is expected (first
        build). A miss WITH stored artifacts means an input or the model source
        changed — worth saying out loud, because it explains a slow build."""
        with mock.patch.object(fpl_build.simcache, "artifacts_for",
                               return_value=["stale-key"]):
            warnings = fpl_build.cache_warnings(1, cache_hit=False)
        self.assertTrue(any("stale-key" in w or "1 stale" in w for w in warnings))

    def test_first_build_miss_is_silent(self):
        with mock.patch.object(fpl_build.simcache, "artifacts_for",
                               return_value=[]):
            self.assertEqual(fpl_build.cache_warnings(1, cache_hit=False), [])

    def test_cache_hit_is_silent(self):
        with mock.patch.object(fpl_build.simcache, "artifacts_for",
                               return_value=["k"]):
            self.assertEqual(fpl_build.cache_warnings(1, cache_hit=True), [])


class TestGameweekBuild(unittest.TestCase):
    """End-to-end into a temp dir. Uses the real cached bootstrap/fixtures but a
    tiny sim count — this asserts the pipeline's SHAPE, not its numbers."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = cls.tmp.name
        cls._saved_site_url = render.SITE_URL
        fpl_build.build(gameweek=1, sims=200, out=cls.out,
                        url="https://example.test", use_llm=False)

    @classmethod
    def tearDownClass(cls):
        # build() mutates the module-global SITE_URL; this module runs before
        # the WC render/build tests, which pin URLs built from it.
        render.SITE_URL = cls._saved_site_url
        cls.tmp.cleanup()

    def _read(self, path):
        with open(os.path.join(self.out, path.lstrip("/")), encoding="utf-8") as fh:
            return fh.read()

    def test_all_six_articles_render(self):
        for slug in fpl_build.ARTICLES:
            with self.subTest(slug=slug):
                html = self._read(f"/fpl/gw1/{slug}/index.html")
                self.assertIn("<!doctype html>", html)
                self.assertIn("Gameweek 1", html)

    def test_json_and_markdown_twins_exist(self):
        for slug in fpl_build.ARTICLES:
            with self.subTest(slug=slug):
                env = json.loads(self._read(f"/api/fpl/gw1/{slug}.json"))
                self.assertEqual(env["gameweek"], 1)
                self.assertEqual(env["competition"], "fantasy_premier_league")
                self.assertTrue(self._read(f"/fpl/gw1/{slug}.md"))

    def test_landing_is_written_to_both_the_section_and_the_root(self):
        section = self._read("/fpl/gw1/index.html")
        root = self._read("/index.html")
        self.assertEqual(section, root)
        self.assertIn("Fantasy Premier League", root)

    def test_world_cup_pages_are_never_written(self):
        self.assertFalse(os.path.exists(os.path.join(self.out, "round")))

    def test_players_feed_carries_no_price_or_ownership(self):
        """Same guardrail as the World Cup bulk feed: derived model outputs plus
        name/team/position only. Price and ownership stay per-article context."""
        feed = json.loads(self._read("/api/fpl/gw1/players.json"))
        self.assertTrue(feed["players"])
        for p in feed["players"][:20]:
            self.assertNotIn("price", p)
            self.assertNotIn("ownership_pct", p)

    def test_projection_snapshot_is_not_written_for_a_non_production_build(self):
        """Snapshots are the track record's ground truth — a test build into a temp
        dir must never touch them."""
        snap = os.path.join(os.path.dirname(os.path.abspath(fpl_build.__file__)),
                            "assets", "projections", "fpl-gw1")
        self.assertFalse(os.path.isdir(snap))

    def test_sitemap_keeps_the_world_cup_tree(self):
        xml = self._read("/sitemap.xml")
        self.assertIn("/fpl/gw1/", xml)


class TestCliRouting(unittest.TestCase):
    def test_gw_routes_to_the_fpl_build(self):
        from evmax import build as build_mod
        with mock.patch.object(build_mod, "fpl_build") as fake:
            with mock.patch("sys.argv", ["build", "--gw", "3", "--no-llm"]):
                build_mod.main()
        fake.build.assert_called_once()
        self.assertEqual(fake.build.call_args.kwargs["gameweek"], 3)

    def test_round_still_routes_to_the_world_cup_build(self):
        from evmax import build as build_mod
        with mock.patch.object(build_mod, "build") as fake:
            with mock.patch("sys.argv", ["build", "--round", "5", "--no-llm"]):
                build_mod.main()
        fake.assert_called_once()

    def test_exactly_one_of_round_or_gw_is_required(self):
        from evmax import build as build_mod
        with mock.patch("sys.argv", ["build", "--no-llm"]):
            with self.assertRaises(SystemExit):
                build_mod.main()


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
