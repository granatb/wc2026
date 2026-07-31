"""Phase 4: FPL section rendering, preflight and the end-to-end gameweek build."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest import mock

from core import fixtures as core_fixtures
from evmax import fpl_build, prompts, render, writer


class TestSectionDescriptor(unittest.TestCase):
    def test_world_cup_section_paths(self):
        self.assertEqual(render.WC.article_path(5, "captains"), "/round/5/captains/")
        self.assertEqual(render.WC.md_path(5, "captains"), "/round/5/captains.md")
        self.assertEqual(render.WC.json_path(5, "captains"),
                         "/api/round/5/captains.json")
        self.assertEqual(render.WC.landing_path(5), "/round/5/")
        self.assertEqual(render.WC.players_json_path(5),
                         "/api/round/5/players.json")
        self.assertEqual(render.WC.kicker(5), "Round 5")

    def test_fpl_section_paths(self):
        self.assertEqual(render.FPL.article_path(1, "defcon"), "/fpl/gw1/defcon/")
        self.assertEqual(render.FPL.md_path(1, "defcon"), "/fpl/gw1/defcon.md")
        self.assertEqual(render.FPL.json_path(1, "defcon"),
                         "/api/fpl/gw1/defcon.json")
        self.assertEqual(render.FPL.landing_path(1), "/fpl/gw1/")
        self.assertEqual(render.FPL.players_json_path(1),
                         "/api/fpl/gw1/players.json")
        self.assertEqual(render.FPL.kicker(1), "Gameweek 1")


_PROSE = {"headline": "H", "standfirst": "S", "body_html": "<p>B</p>",
          "bottom_line": "BL", "source": "template"}
_ENTRIES = [{"name": "A", "rank": 1, "x_points": 6.0, "price": 5.0, "captain_ev": 6.0}]


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

    def test_world_cup_switcher_still_says_rounds(self):
        html = render.article_page(2, "captains", "T", _PROSE, _ENTRIES,
                                   ["x_points"], "/api/round/2/captains.json", "",
                                   available_rounds=[1, 2])
        self.assertIn(">R1<", html)
        self.assertIn("Rounds", html)

    def test_fpl_switcher_label_reads_gameweeks(self):
        html = render.article_page(2, "captains", "T", _PROSE, _ENTRIES,
                                   ["x_points"], "/api/fpl/gw2/captains.json", "",
                                   section=render.FPL, available_rounds=[1, 2])
        self.assertIn("Gameweeks", html)
        self.assertNotIn("GWounds", html)


class TestArticleMdSection(unittest.TestCase):
    def test_fpl_markdown_twin_points_at_the_fpl_tree(self):
        md = render.article_md(1, "captains", "T", _PROSE, _ENTRIES, ["x_points"],
                               "2026-08-20T00:00:00+00:00", "20 August 2026",
                               canonical_path="/fpl/gw1/captains/",
                               section=render.FPL)
        self.assertIn("/api/fpl/gw1/captains.json", md)
        self.assertNotIn("/api/round/", md)

    def test_world_cup_markdown_twin_is_unchanged(self):
        md = render.article_md(5, "captains", "T", _PROSE, _ENTRIES, ["x_points"],
                               "2026-06-24T00:00:00+00:00", "24 June 2026",
                               canonical_path="/round/5/captains/")
        self.assertIn("/api/round/5/captains.json", md)


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

    def test_landing_defaults_to_world_cup(self):
        featured = {"slug": "captains", "prose": _PROSE, "viz_html": ""}
        html = render.landing_page(1, featured, [], date_str="1 July 2026")
        self.assertIn("World Cup Fantasy", html)


class TestAgentFilesSection(unittest.TestCase):
    def test_llms_txt_lists_fpl_urls(self):
        txt = render.llms_txt(1, [("captains", "Best captain picks")],
                              section=render.FPL)
        self.assertIn("/fpl/gw1/captains/", txt)
        self.assertIn("/api/fpl/gw1/captains.json", txt)
        self.assertIn("Gameweek 1", txt)

    def test_llms_txt_defaults_to_world_cup(self):
        txt = render.llms_txt(5, [("captains", "Best captain picks")])
        self.assertIn("/round/5/captains/", txt)

    def test_sitemap_includes_fpl_urls(self):
        xml = render.sitemap_xml(1, [("captains", "Best captain picks")],
                                 lastmod="2026-08-20", section=render.FPL)
        self.assertIn("/fpl/gw1/", xml)
        self.assertIn("/fpl/gw1/captains/", xml)

    def test_sitemap_can_carry_extra_urls(self):
        """The FPL build must keep the World Cup tree in the sitemap — those pages
        are still live and still indexed, and a sitemap that drops them reads to a
        crawler as a deindexing request."""
        xml = render.sitemap_xml(1, [("captains", "T")], lastmod="2026-08-20",
                                 section=render.FPL,
                                 extra_urls=["/round/8/", "/round/8/captains/"])
        self.assertIn("/round/8/captains/", xml)

    def test_sitemap_defaults_have_no_extra_urls(self):
        xml = render.sitemap_xml(5, [("captains", "T")], lastmod="2026-06-24")
        self.assertIn("/round/5/captains/", xml)


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
        self.assertNotIn("gameweek", env)


class TestFeedCardSection(unittest.TestCase):
    def test_fpl_feed_card_links_into_the_fpl_tree(self):
        html = render.feed_card("defcon", 1, "H", "T", "0.72", "P(DefCon)",
                                section=render.FPL)
        self.assertIn('href="/fpl/gw1/defcon/"', html)

    def test_default_feed_card_is_unchanged(self):
        html = render.feed_card("captains", 5, "H", "T", "9.9", "Captain EV")
        self.assertIn('href="/round/5/captains/"', html)


class TestFplColumnLabels(unittest.TestCase):
    def test_every_fpl_column_has_a_reader_facing_label(self):
        """A missing label falls back to the raw dict key, which ships things like
        'exp_clean_sheets' as a table header."""
        for col in ("p_defcon", "cs_points", "exp_clean_sheets", "exp_goals_for",
                    "exp_goals_against", "fixtures", "basis", "value", "defcon",
                    "bonus"):
            with self.subTest(col=col):
                self.assertIn(col, render._COL_LABEL)
                self.assertNotEqual(render._COL_LABEL[col], col)


class TestSectionMethodology(unittest.TestCase):
    def test_world_cup_methodology_is_the_global_default(self):
        self.assertEqual(render.WC.methodology, render.METHODOLOGY)

    def test_fpl_methodology_does_not_mention_the_world_cup(self):
        self.assertNotIn("World Cup", render.FPL.methodology)

    def test_fpl_article_page_carries_fpl_methodology(self):
        html = render.article_page(1, "defcon", "T", _PROSE, _ENTRIES,
                                   ["x_points"], "/api/fpl/gw1/defcon.json", "",
                                   section=render.FPL)
        self.assertNotIn("World Cup", html)

    def test_fpl_article_json_carries_fpl_methodology(self):
        env = render.article_json("fantasy_premier_league", 1, "defcon", "T",
                                  "2026-08-20T00:00:00+00:00", 50000, _ENTRIES,
                                  section=render.FPL)
        self.assertNotIn("World Cup", env["methodology"])

    def test_fpl_markdown_twin_carries_fpl_methodology(self):
        md = render.article_md(1, "defcon", "T", _PROSE, _ENTRIES, ["x_points"],
                               "2026-08-20T00:00:00+00:00", "20 August 2026",
                               canonical_path="/fpl/gw1/defcon/",
                               section=render.FPL)
        self.assertNotIn("World Cup", md)

    def test_world_cup_article_page_is_unchanged(self):
        html = render.article_page(5, "captains", "T", _PROSE, _ENTRIES,
                                   ["x_points"], "/api/round/5/captains.json", "")
        self.assertIn(render.METHODOLOGY, html)


_TICKER_ENTRY = {"name": "ARS", "rank": 1, "opponents": "LIV (H)", "fixtures": 1,
                 "exp_clean_sheets": 0.42, "exp_goals_for": 1.9,
                 "exp_goals_against": 0.9, "env": "balanced", "basis": "market"}
_DEFCON_ENTRY = {"name": "Gabriel", "rank": 1, "position": "DEF", "team": "ARS",
                 "p_defcon": 0.71, "defcon": 1.42, "defcon_threshold": 10,
                 "x_points": 5.4, "price": 6.0}


class TestProseCacheNamespace(unittest.TestCase):
    def test_fpl_and_world_cup_caches_do_not_collide(self):
        import os, tempfile
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
        self.assertIn("Round", p)
        self.assertIn("5", p)

    def test_fpl_prompt_says_gameweek_and_carries_the_glossary(self):
        p = prompts.build_prompt("defcon", 1, _ENTRIES, unit="Gameweek")
        self.assertIn("Gameweek", p)
        self.assertIn("p_defcon", p)
        self.assertIn("exp_clean_sheets", p)

    def test_world_cup_prompt_does_not_carry_the_fpl_glossary(self):
        p = prompts.build_prompt("captains", 5, _ENTRIES)
        self.assertNotIn("p_defcon", p)


class TestFplTemplates(unittest.TestCase):
    def _prose(self, slug, entries):
        return writer.article_prose(slug, 1, entries, ["x_points"],
                                    cache_dir="/nonexistent", use_llm=False,
                                    cache_name="fpl-gw1", unit="Gameweek")

    def _cases(self):
        return {
            "captains": [dict(_ENTRIES[0], captain_ev=12.0, ceiling=10.0,
                              kickoff_order=1, team="ARS", position="FWD"),
                         dict(_ENTRIES[0], name="B", captain_ev=10.0, ceiling=9.0,
                              kickoff_order=2, team="LIV", position="MID",
                              x_points=5.0)],
            "wildcard": [dict(_ENTRIES[0], role="XI", rank=1, team="ARS",
                              position="MID", ceiling=9.0)],
            "ticker": [_TICKER_ENTRY],
            "defenders": [dict(_ENTRIES[0], position="DEF", team="ARS",
                               cs_points=1.6, defcon=1.4, bonus=0.5, ceiling=9.0)],
            "efficiency": [dict(_ENTRIES[0], value=1.2, tier="Budget", team="ARS",
                                position="MID", ceiling=9.0)],
            "defcon": [_DEFCON_ENTRY],
        }

    def test_every_fpl_slug_has_a_real_template(self):
        for slug, entries in self._cases().items():
            prose = self._prose(slug, entries)
            with self.subTest(slug=slug):
                self.assertNotIn("analysis:", prose["headline"].lower(),
                                 f"{slug} fell through to the generic template")
                self.assertTrue(prose["standfirst"])
                self.assertTrue(prose["bottom_line"])
                self.assertIn("<p>", prose["body_html"])

    def test_world_cup_slugs_keep_their_own_templates(self):
        """captains/wildcard/defenders/efficiency exist in BOTH competitions; the
        WC prose must be unaffected by the FPL table."""
        wc = writer.article_prose(
            "captains", 5,
            [dict(_ENTRIES[0], captain_ev=12.0, ceiling=10.0, team="BRA",
                  position="FWD")],
            ["x_points"], cache_dir="/nonexistent", use_llm=False)
        fpl = self._prose("captains", self._cases()["captains"])
        self.assertNotEqual(wc["headline"], fpl["headline"])

    def test_defcon_prose_states_the_probability_and_threshold(self):
        prose = self._prose("defcon", [_DEFCON_ENTRY])
        blob = prose["standfirst"] + prose["body_html"]
        self.assertIn("71", blob)
        self.assertIn("10", blob)

    def test_ticker_prose_names_blanks_and_doubles(self):
        entries = [_TICKER_ENTRY,
                   dict(_TICKER_ENTRY, name="EVE", rank=2, fixtures=0,
                        opponents="—", exp_clean_sheets=0.0, env="blank",
                        basis="—"),
                   dict(_TICKER_ENTRY, name="MCI", rank=3, fixtures=2,
                        opponents="BUR (H), TOT (A)", exp_clean_sheets=0.8,
                        env="double", basis="mixed")]
        prose = self._prose("ticker", entries)
        body = prose["body_html"]
        self.assertIn("EVE", body)
        self.assertIn("MCI", body)
        self.assertIn("blank", body.lower())
        self.assertIn("double", body.lower())

    def test_ticker_prose_omits_the_paragraph_when_there_are_none(self):
        prose = self._prose("ticker", [_TICKER_ENTRY])
        self.assertNotIn("blank", prose["body_html"].lower())

    def test_empty_entries_do_not_crash_any_slug(self):
        for slug in ("captains", "wildcard", "ticker", "defenders", "efficiency",
                     "defcon"):
            with self.subTest(slug=slug):
                prose = self._prose(slug, [])
                self.assertTrue(prose["headline"])

    def test_names_are_html_escaped(self):
        entries = [dict(_ENTRIES[0], name="O'Riley & Sons", captain_ev=12.0,
                        ceiling=10.0, kickoff_order=1, team="BHA", position="MID")]
        prose = self._prose("captains", entries)
        self.assertNotIn("O'Riley & Sons", prose["body_html"])
        self.assertIn("&amp;", prose["body_html"])


def _fx(match_id, home, away, gw=1, priced=True):
    return core_fixtures.Fixture(
        match_id=match_id, home=home, away=away,
        kickoff=datetime(2026, 8, 21, 19, 0, tzinfo=timezone.utc),
        stage="GW", fantasy_round=gw, neutral=False,
        lam_home=1.5 if priced else None, lam_away=1.1 if priced else None)


class TestFplPreflight(unittest.TestCase):
    def _preflight(self, fx, players, cold_start, boot=True):
        with mock.patch.object(core_fixtures, "by_round", return_value=fx), \
             mock.patch.object(fpl_build.fpl_api, "read_cache",
                               return_value={} if boot else None):
            return fpl_build.preflight(1, players=players, cold_start=cold_start)

    def test_aborts_when_the_gameweek_has_no_fixtures(self):
        with self.assertRaises(SystemExit) as ctx:
            self._preflight([], [{"status": "i"}], [])
        self.assertIn("no fixtures", str(ctx.exception).lower())

    def test_aborts_when_the_bootstrap_cache_is_missing(self):
        with self.assertRaises(SystemExit) as ctx:
            self._preflight([_fx("m1", "ARS", "LIV")], [{"status": "i"}], [],
                            boot=False)
        self.assertIn("bootstrap", str(ctx.exception).lower())

    def test_abort_message_names_the_fix_command(self):
        """An operator hitting this at 17:00 on deadline day needs the command, not
        a diagnosis."""
        with self.assertRaises(SystemExit) as ctx:
            self._preflight([], [{"status": "i"}], [])
        self.assertIn("manage.py fpl", str(ctx.exception))

    def test_warns_on_unpriced_fixtures(self):
        fx = [_fx("m1", "ARS", "LIV"), _fx("m2", "BUR", "EVE", priced=False)]
        warnings = self._preflight(fx, [{"status": "i"}], [])
        self.assertTrue(any("BUR" in w and "unpriced" in w.lower()
                            for w in warnings))

    def test_no_unpriced_warning_when_all_fixtures_are_priced(self):
        warnings = self._preflight([_fx("m1", "ARS", "LIV")], [{"status": "i"}], [])
        self.assertFalse(any("unpriced" in w.lower() for w in warnings))

    def test_warns_on_cold_start_players(self):
        warnings = self._preflight(
            [_fx("m1", "ARS", "LIV")], [{"status": "i"}],
            [{"name": "Newbie"}, {"name": "Rookie"}])
        self.assertTrue(any("cold-start" in w.lower() and "Newbie" in w
                            for w in warnings))

    def test_cold_start_warning_truncates_a_long_list(self):
        cold = [{"name": f"P{i}"} for i in range(20)]
        warnings = self._preflight([_fx("m1", "ARS", "LIV")], [{"status": "i"}],
                                   cold)
        cold_warning = next(w for w in warnings if "cold-start" in w.lower())
        self.assertIn("20", cold_warning)
        self.assertLess(len(cold_warning), 400)

    def test_warns_when_no_player_carries_an_availability_flag(self):
        """Real FPL always has injuries. A bootstrap where every player is status
        'a' is a stale cache, and it would silently publish ruled-out players as
        nailed starters."""
        warnings = self._preflight([_fx("m1", "ARS", "LIV")],
                                   [{"status": "a"}, {"status": "a"}], [])
        self.assertTrue(any("stale" in w.lower() for w in warnings))

    def test_no_stale_warning_when_flags_are_present(self):
        warnings = self._preflight([_fx("m1", "ARS", "LIV")],
                                   [{"status": "a"}, {"status": "i"}], [])
        self.assertFalse(any("stale" in w.lower() for w in warnings))

    def test_no_stale_warning_on_an_empty_player_list(self):
        """Zero players is a different failure; do not also claim staleness."""
        warnings = self._preflight([_fx("m1", "ARS", "LIV")], [], [])
        self.assertFalse(any("stale" in w.lower() for w in warnings))


class TestCacheWarnings(unittest.TestCase):
    def test_unexpected_cache_miss_is_reported(self):
        """A miss with no stored artifact for this gameweek is expected (first
        build). A miss WITH stored artifacts means an input or the model source
        changed — worth saying out loud, because it explains a slow build."""
        with mock.patch.object(fpl_build.simcache, "artifacts_for",
                               return_value=["stale-key-abcdef"]):
            warnings = fpl_build.cache_warnings(1, cache_hit=False)
        self.assertEqual(len(warnings), 1)
        self.assertIn("1 stale", warnings[0])

    def test_first_build_miss_is_silent(self):
        with mock.patch.object(fpl_build.simcache, "artifacts_for",
                               return_value=[]):
            self.assertEqual(fpl_build.cache_warnings(1, cache_hit=False), [])

    def test_cache_hit_is_silent(self):
        with mock.patch.object(fpl_build.simcache, "artifacts_for",
                               return_value=["k"]):
            self.assertEqual(fpl_build.cache_warnings(1, cache_hit=True), [])
