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

    def test_captains_prose_never_claims_a_later_kickoff_for_the_same_match(self):
        """Two candidates sharing a kickoff instant share a kickoff_order —
        the prose must not tell the reader either of them kicks off later."""
        first = dict(_ENTRIES[0], captain_ev=12.0, ceiling=10.0, team="ARS",
                     position="FWD", kickoff_order=1)
        second = dict(first, name="B", captain_ev=11.0)
        prose = self._prose("captains", [first, second])
        self.assertNotIn("kicks off later", prose["body_html"])
        self.assertNotIn("kicks off first", prose["body_html"])

    def test_captains_prose_flags_a_genuinely_later_kickoff(self):
        first = dict(_ENTRIES[0], captain_ev=12.0, ceiling=10.0, team="ARS",
                     position="FWD", kickoff_order=1)
        second = dict(first, name="B", captain_ev=11.0, kickoff_order=2)
        prose = self._prose("captains", [first, second])
        self.assertIn("kicks off later", prose["body_html"])

    def test_defenders_component_framing_needs_a_single_fixture(self):
        """Review finding 7 (minimum fix): cs_points/defcon/bonus are
        per-MATCH quantities while x_points is per-WEEK, so the 'X from clean
        sheets, Y from DefCon, Z from bonus' breakdown is only true when the
        player has exactly one fixture this gameweek."""
        base = dict(_ENTRIES[0], position="DEF", team="ARS", cs_points=1.6,
                    defcon=1.4, bonus=0.5, ceiling=9.0)
        for single in (dict(base, fixtures=1), dict(base)):   # absent = single
            prose = self._prose("defenders", [single])
            self.assertIn("of it from clean sheets alone", prose["standfirst"])
            self.assertIn("from clean sheets", prose["body_html"])
        double = self._prose("defenders", [dict(base, fixtures=2)])
        self.assertNotIn("of it from clean sheets alone", double["standfirst"])
        self.assertNotIn("from defensive contribution and", double["body_html"])
        self.assertIn("per-match", double["body_html"])
        self.assertIn("2 fixtures", double["standfirst"])

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


def _snapshot_state():
    """{filename: mtime_ns} of the GW1 projection snapshot dir, or None if absent.

    The dir legitimately exists on a checkout where a REAL production build ran
    pre-lock (Task 13 does exactly that), so the temp-dir build test asserts it
    was left untouched rather than absent."""
    snap = os.path.join(os.path.dirname(os.path.abspath(fpl_build.__file__)),
                        "assets", "projections", "fpl-gw1")
    if not os.path.isdir(snap):
        return None
    return {f: os.stat(os.path.join(snap, f)).st_mtime_ns
            for f in sorted(os.listdir(snap))}


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

    # Pre-seeded before the build: a frozen World Cup page tree, exactly like a
    # production out/ dir that already carries published rounds. The build must
    # leave it byte-untouched AND keep its URLs in the sitemap (D5).
    _WC_PAGES = ("round/8/index.html", "round/8/captains/index.html")
    _WC_SENTINEL = "<!doctype html><!-- frozen WC page -->"

    @classmethod
    def setUpClass(cls):
        # Same courtesy as TestLoadStates: on a fresh checkout data/ is empty
        # (it is gitignored), and that is a skip, not an error — the build's
        # own preflight SystemExit would otherwise report as a test failure.
        from core import fpl_api
        if fpl_api.read_cache("bootstrap") is None:
            raise unittest.SkipTest(
                "data/fpl bootstrap cache missing — populate with "
                "`python3 manage.py fpl --round 1 --refresh`")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = cls.tmp.name
        for rel in cls._WC_PAGES:
            path = os.path.join(cls.out, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(cls._WC_SENTINEL)
        cls._saved_site_url = render.SITE_URL
        cls._snap_before = _snapshot_state()
        # An empty prose-cache dir pins this build to the TEMPLATE tier:
        # the owner's curated data/articles/fpl-gw1/ cache (gitignored, wins
        # the tier) must never change what this suite asserts about prose.
        cls._prose_tmp = tempfile.TemporaryDirectory()
        # player_pages_cap: the smoke build writes the top 40 player pages,
        # not all 563 — the shape is identical, the suite stays fast.
        cls.PLAYER_CAP = 40
        fpl_build.build(gameweek=1, sims=200, out=cls.out,
                        url="https://example.test", use_llm=False,
                        cache_dir=cls._prose_tmp.name,
                        player_pages_cap=cls.PLAYER_CAP)

    @classmethod
    def tearDownClass(cls):
        # build() mutates the module-global SITE_URL; this module runs before
        # the WC render/build tests, which pin URLs built from it.
        render.SITE_URL = cls._saved_site_url
        cls.tmp.cleanup()
        cls._prose_tmp.cleanup()

    def _read(self, path):
        with open(os.path.join(self.out, path.lstrip("/")), encoding="utf-8") as fh:
            return fh.read()

    def test_all_eight_articles_render(self):
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
        """The pre-seeded WC tree must come through the build byte-untouched
        and gain no siblings — those pages are frozen published claims."""
        found = []
        for dirpath, _dirs, files in os.walk(os.path.join(self.out, "round")):
            found += [os.path.relpath(os.path.join(dirpath, f), self.out)
                      for f in files]
        self.assertEqual(sorted(found), sorted(self._WC_PAGES))
        for rel in self._WC_PAGES:
            self.assertEqual(self._read(rel), self._WC_SENTINEL)

    def test_players_feed_carries_no_price_or_ownership(self):
        """Same guardrail as the World Cup bulk feed: derived model outputs plus
        name/team/position only. Price and ownership stay per-article context."""
        feed = json.loads(self._read("/api/fpl/gw1/players.json"))
        self.assertTrue(feed["players"])
        for p in feed["players"][:20]:
            self.assertNotIn("price", p)
            self.assertNotIn("ownership_pct", p)

    def test_players_feed_links_each_players_card_page(self):
        """The instant search (/js/players.js) links results through the
        feed's `page` field."""
        feed = json.loads(self._read("/api/fpl/gw1/players.json"))
        paged = [p for p in feed["players"] if p.get("page")]
        self.assertEqual(len(paged), self.PLAYER_CAP)
        self.assertTrue(all(p["page"].startswith("/fpl/players/")
                            for p in paged))

    def test_player_pages_and_json_twins_capped_by_the_smoke_cap(self):
        """One page + one JSON per (capped) player; page carries the card and
        declares its JSON twin; the JSON carries the expanded schema."""
        import re
        root = os.path.join(self.out, "fpl", "players")
        page_dirs = [d for d in os.listdir(root)
                     if os.path.isdir(os.path.join(root, d))]
        self.assertEqual(len(page_dirs), self.PLAYER_CAP)
        slug = sorted(page_dirs)[0]
        html = self._read(f"/fpl/players/{slug}/index.html")
        self.assertIn('<figure class="player-card"', html)
        self.assertIn("pc-premium", html)               # reserved premium slot
        m = re.search(r'href="(/api/fpl/gw1/players/\d+\.json)"', html)
        self.assertIsNotNone(m)
        env = json.loads(self._read(m.group(1)))
        for key in ("projection", "season", "ranks", "verdict", "verdict_tier",
                    "fixtures", "six_week_xpts", "squads", "notes", "page"):
            self.assertIn(key, env)
        self.assertIsNone(env["distribution"])          # reserved, null
        self.assertEqual(env["gameweek"], 1)
        self.assertEqual(env["license"], render.DATA_LICENSE_URL)
        # GW1 caches exist on this checkout, so the strip prices something
        self.assertTrue(env["fixtures"])

    def test_players_index_and_tier_boards_render(self):
        html = self._read("/fpl/players/index.html")
        self.assertIn("<h1>Check your player</h1>", html)
        self.assertIn('data-players-url="/api/fpl/gw1/players.json"', html)
        self.assertIn('<script src="/js/players.js" defer></script>', html)
        for seg in ("gk", "def", "mid", "fwd"):
            tier = self._read(f"/fpl/tiers/{seg}/index.html")
            self.assertIn("tiered S to D", tier)
        # the copied first-party JS actually shipped
        self.assertTrue(os.path.exists(os.path.join(self.out, "js",
                                                    "players.js")))

    def test_landing_opens_with_the_full_top_cards_row(self):
        """Owner correction 2026-08-25: FULL card faces at the very top —
        above the duel strip and the hero article — not thumbnails."""
        html = self._read("/index.html")
        self.assertIn("This week's top cards — from 50,000 simulations", html)
        self.assertEqual(html.count('<figure class="player-card"'), 4)
        self.assertNotIn("tc-card", html)               # thumbnails are gone
        self.assertIn('href="/fpl/players/"', html)
        # the row renders BEFORE the duel strip and the featured article
        row_at = html.find('<section class="top-cards-full">')
        self.assertGreater(row_at, -1)
        self.assertLess(row_at, html.find('<div class="duel">'))
        self.assertLess(row_at, html.find('<section class="feat">'))
        # the row's cards are the feed's own top four by x_points, each face
        # linking to its player page
        feed = json.loads(self._read("/api/fpl/gw1/players.json"))
        top = sorted(feed["players"],
                     key=lambda p: (-p["x_points"], p["name"]))[0]
        self.assertIn(f'href="{top["page"]}"', html)

    def test_sitemap_and_llms_txt_carry_the_player_surfaces(self):
        xml = self._read("/sitemap.xml")
        self.assertIn("https://example.test/fpl/players/</loc>", xml)
        self.assertIn("https://example.test/fpl/tiers/gk/</loc>", xml)
        self.assertEqual(xml.count("https://example.test/fpl/players/"),
                         self.PLAYER_CAP + 1)          # index + one per player
        txt = self._read("/llms.txt")
        self.assertIn("## Player cards", txt)
        self.assertIn("/fpl/players/", txt)
        self.assertIn("/api/fpl/gw1/players/{element_id}.json", txt)

    def test_projection_snapshot_is_not_written_for_a_non_production_build(self):
        """Snapshots are the track record's ground truth — a test build into a temp
        dir must never touch them. A real pre-lock production build may already
        have created the dir on this checkout, so assert byte-for-byte
        untouched (same files, same mtimes) rather than absent."""
        self.assertEqual(_snapshot_state(), self._snap_before)

    def test_landing_leads_with_our_squad_then_captains_then_the_duel(self):
        html = self._read("/index.html")
        # hero: our-squad is the featured block
        self.assertIn("Featured · Our Squad", html)
        self.assertIn('href="/fpl/gw1/our-squad/"', html)
        # captains is the #2 surface: first card of the feed
        feed_at = html.find('<div class="feed">')
        self.assertGreater(feed_at, -1)
        cap_at = html.find('href="/fpl/gw1/captains/"', feed_at)
        cons_at = html.find('href="/fpl/gw1/consensus-squad/"', feed_at)
        self.assertGreater(cap_at, -1)
        self.assertGreater(cons_at, cap_at)
        # duel strip: both labels present with two projected totals
        self.assertIn('class="duel"', html)
        self.assertIn(">Model<", html)
        self.assertIn(">Consensus<", html)

    def test_duel_totals_match_the_squad_articles_own_meta(self):
        """The strip's numbers are the two articles' projected_total — the
        landing must never disagree with the pages it links to."""
        html = self._read("/index.html")
        for slug in ("our-squad", "consensus-squad"):
            env = json.loads(self._read(f"/api/fpl/gw1/{slug}.json"))
            self.assertIn(f'{env["squad"]["projected_total"]:.2f}', html)

    def test_squad_articles_publish_the_full_page_family_with_meta(self):
        """The two squad slugs are first-class articles: HTML + JSON envelope
        (with the squad meta block) + .md twin, like the six existing ones."""
        for slug, captain in (("our-squad", "B.Fernandes"),
                              ("consensus-squad", "Haaland")):
            with self.subTest(slug=slug):
                env = json.loads(self._read(f"/api/fpl/gw1/{slug}.json"))
                self.assertEqual(len(env["entries"]), 15)
                self.assertEqual(env["squad"]["captain"], captain)
                # Formation is weekly state content, not a constant: assert it
                # is well-formed and consistent with the entries themselves.
                self.assertRegex(env["squad"]["formation"], r"^\d-\d-\d$")
                xi = [e for e in env["entries"] if e.get("role") == "XI"]
                d = sum(1 for e in xi if e["position"] == "DEF")
                m = sum(1 for e in xi if e["position"] == "MID")
                f = sum(1 for e in xi if e["position"] == "FWD")
                self.assertEqual(env["squad"]["formation"], f"{d}-{m}-{f}")
                self.assertGreater(env["squad"]["projected_total"],
                                   env["squad"]["xi_xpoints"])
                md = self._read(f"/fpl/gw1/{slug}.md")
                self.assertIn(captain, md)

    def test_player_entries_carry_their_clubs_fixture_count(self):
        """The build stamps per-club fixture counts from the match summaries
        so the prose can tell a single from a double gameweek (finding 7)."""
        env = json.loads(self._read("/api/fpl/gw1/defenders.json"))
        self.assertTrue(env["entries"])
        for e in env["entries"]:
            self.assertEqual(e["fixtures"], 1)      # GW1 has no doubles

    def test_squad_prose_facts_come_from_the_states(self):
        """Review finding 5, end to end: prose facts derive from the states.
        The consensus method line depends on which era the state is from —
        expert mention-tally (source_count present) vs the ownership-template
        reset (wildcard declared) — so the expectation is read from the state
        file, not hardcoded to one week's method."""
        import json as _json
        cons_state = _json.load(open("games/fpl/state_consensus.json"))
        cons = self._read("/fpl/gw1/consensus-squad/index.html")
        # The method line always frames the tally; the count word appears
        # only when the state carries source_count (review finding 5).
        self.assertIn("mention-tally", cons.lower())
        if cons_state.get("source_count"):
            self.assertIn("expert sources", cons)
        ours = self._read("/fpl/gw1/our-squad/index.html")
        model_state = _json.load(open("games/fpl/state.json"))
        names = {e["name"] for e in cons_state["squad"]}
        if "Haaland" in names and "Haaland" not in {e["name"] for e in model_state["squad"]}:
            self.assertIn("owns him", ours)

    def test_root_site_chrome_is_regenerated(self):
        """Review finding 4: a deploy replaces the whole tree, so an FPL build
        that omits the root-level shared files strips the GSC verification,
        /_redirects and the /track-record/ page its own nav and sitemap link
        to. Both builds write them via the same shared writer."""
        from evmax import build as wc_build
        self.assertEqual(self._read(f"/{wc_build._GSC_VERIFICATION_FILE}"),
                         wc_build._GSC_VERIFICATION_CONTENT)
        redirects = self._read("/_redirects")
        self.assertIn(wc_build._GSC_VERIFICATION_FILE, redirects)
        self.assertIn("/round/5/best-xi/ /round/5/wildcard/ 301", redirects)
        self.assertIn("<!doctype html>", self._read("/track-record/index.html"))
        record = json.loads(self._read("/api/track-record.json"))
        self.assertIn("rounds", record)
        # Task 8: the IndexNow ownership key rides in the same chrome — an
        # FPL publish that dropped /{key}.txt would silently de-verify the
        # domain for the post-deploy ping (scripts/indexnow_ping.py).
        key = wc_build.indexnow_key()
        self.assertEqual(self._read(f"/{key}.txt"), key + "\n")

    def test_track_record_leads_with_the_fpl_ledger(self):
        """Owner correction 2026-08-25 ("track record is still wc"): an FPL
        build's /track-record/ opens with the graded FPL ledger, the WC
        retrospective follows under its own heading, and the grading JSONs
        ship verbatim under /api/fpl/accuracy/."""
        html = self._read("/track-record/index.html")
        fpl_at = html.find("FPL 2026/27 — the graded ledger")
        wc_at = html.find("World Cup 2026 — the retrospective")
        self.assertGreater(fpl_at, -1)
        self.assertLess(fpl_at, wc_at)
        self.assertIn("<td>GW1</td>", html)
        self.assertIn("<td>2.734</td>", html)
        self.assertIn("65.92 → 44", html)
        self.assertIn("60.74 → 53", html)
        self.assertIn("0-1 (crowd leads)", html)
        self.assertIn("Projections frozen pre-deadline; grading JSONs public",
                      html)
        # the linked grading JSON is the committed file, byte-for-byte
        import evmax
        src = os.path.join(os.path.dirname(os.path.abspath(evmax.__file__)),
                           "assets", "accuracy", "gw1.json")
        with open(src, encoding="utf-8") as fh:
            self.assertEqual(self._read("/api/fpl/accuracy/gw1.json"),
                             fh.read())

    def test_rate_page_serves_the_fpl_section(self):
        html = self._read("/rate/index.html")
        self.assertIn("Rate my FPL team", html)
        self.assertIn('data-players-url="/api/fpl/gw1/players.json"', html)
        self.assertIn('data-unit="Gameweek"', html)
        self.assertNotIn("World Cup", html)

    def test_sitemap_keeps_the_world_cup_tree(self):
        """The pre-seeded WC pages are still live and still indexed (D5): a
        sitemap that drops them reads to a crawler as a deindexing request."""
        xml = self._read("/sitemap.xml")
        self.assertIn("/fpl/gw1/", xml)
        self.assertIn("https://example.test/round/8/</loc>", xml)
        self.assertIn("https://example.test/round/8/captains/</loc>", xml)


class TestPersistedUrls(unittest.TestCase):
    """Review finding 3: the sitemap disk-walk must keep EVERY page already on
    disk — the World Cup tree AND prior FPL gameweeks. Building GW2 with a
    walk that only covers out/round would drop every GW1 URL, which reads to
    a crawler as a request to deindex the lot."""

    @staticmethod
    def _touch(out, rel):
        path = os.path.join(out, rel, "index.html")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("<!doctype html>")

    def test_prior_gameweeks_and_wc_tree_are_kept(self):
        with tempfile.TemporaryDirectory() as out:
            for rel in ("round/8", "round/8/captains",
                        "fpl/gw1", "fpl/gw1/captains", "fpl/gw2"):
                self._touch(out, rel)
            urls = fpl_build._persisted_urls(out, current_gameweek=2)
        self.assertIn("/round/8/", urls)
        self.assertIn("/round/8/captains/", urls)
        self.assertIn("/fpl/gw1/", urls)
        self.assertIn("/fpl/gw1/captains/", urls)
        # the gameweek being built is added explicitly by sitemap_xml's nav —
        # listing it here would duplicate every URL
        self.assertNotIn("/fpl/gw2/", urls)

    def test_current_gameweek_exclusion_is_exact(self):
        """Building gw2 must not swallow gw20 — the exclusion matches the
        path segment, not a string prefix."""
        with tempfile.TemporaryDirectory() as out:
            for rel in ("fpl/gw2", "fpl/gw2/captains", "fpl/gw20"):
                self._touch(out, rel)
            urls = fpl_build._persisted_urls(out, current_gameweek=2)
        self.assertEqual(urls, ["/fpl/gw20/"])

    def test_empty_out_dir_yields_no_urls(self):
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(fpl_build._persisted_urls(out, 1), [])


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


def _squad_entries(captain="Cap", vice="Vice", with_haaland=False,
                   source_count=None, consensus_owns_haaland=None):
    """15 squad_article-shaped entries: XI in state order + ordered bench.

    source_count / consensus_owns_haaland mirror the keys squad_article and
    fpl_build stamp on entries — the prose derives its facts from these, so
    the tests hand them in the same way the build does."""
    def e(name, pos, xp, role, order=None, cap=False, v=False):
        entry = {"name": name, "team": "ARS", "position": pos, "x_points": xp,
                 "captain_ev": round(2 * xp, 2), "ceiling": xp * 1.7,
                 "value": round(xp / 5.0, 3), "price": 5.0, "ownership_pct": 9.0,
                 "role": role, "bench_order": order, "is_captain": cap,
                 "is_vice": v, "rank": 0}
        if source_count is not None:
            entry["source_count"] = source_count
        if consensus_owns_haaland is not None:
            entry["consensus_owns_haaland"] = consensus_owns_haaland
        return entry
    xi = [e("Gk1", "GK", 4.0, "XI"),
          e("D1", "DEF", 5.0, "XI"), e("D2", "DEF", 4.5, "XI"),
          e("D3", "DEF", 4.0, "XI"),
          e(captain, "MID", 8.0, "XI", cap=True),
          e(vice, "MID", 7.0, "XI", v=True),
          e("M3", "MID", 6.0, "XI"), e("M4", "MID", 5.5, "XI"),
          e("M5", "MID", 5.0, "XI"),
          e("Haaland" if with_haaland else "F1", "FWD", 6.5, "XI"),
          e("F2", "FWD", 5.5, "XI")]
    bench = [e("Gk2", "GK", 3.0, "Bench", 1), e("D4", "DEF", 2.5, "Bench", 2),
             e("F3", "FWD", 3.5, "Bench", 3), e("D5", "DEF", 2.0, "Bench", 4)]
    for i, entry in enumerate(xi + bench, 1):
        entry["rank"] = i
    return xi + bench


class TestSquadSlugTemplates(unittest.TestCase):
    """Task 3 gate: hand-written prose that reads as a real article --no-llm."""

    def _prose(self, slug, entries):
        return writer.article_prose(slug, 1, entries, ["x_points"],
                                    cache_dir="/nonexistent", use_llm=False,
                                    cache_name="fpl-gw1", unit="Gameweek")

    def test_both_squad_slugs_have_real_templates(self):
        for slug in ("our-squad", "consensus-squad"):
            with self.subTest(slug=slug):
                prose = self._prose(slug, _squad_entries())
                self.assertNotIn("analysis:", prose["headline"].lower())
                self.assertTrue(prose["standfirst"])
                self.assertTrue(prose["bottom_line"])
                self.assertIn("<p>", prose["body_html"])

    def test_our_squad_states_the_models_reasoning(self):
        prose = self._prose("our-squad", _squad_entries())
        text = prose["standfirst"] + prose["body_html"]
        self.assertIn("horizon", text)              # horizon EV, not one-week
        self.assertIn("market-implied", text)       # lambdas, bookmaker-free
        self.assertIn("Cap", prose["headline"])     # captain by EV, named
        # XI 61.0 + captain 8.0 = 69.0 with the armband
        self.assertIn("69.00", text)

    def test_our_squad_names_the_no_haaland_conviction(self):
        prose = self._prose("our-squad", _squad_entries())
        self.assertIn("Haaland", prose["body_html"])
        self.assertIn("conviction", prose["body_html"])

    def test_no_haaland_line_vanishes_if_he_ever_joins(self):
        prose = self._prose("our-squad", _squad_entries(with_haaland=True))
        self.assertNotIn("No Haaland", prose["body_html"])

    def test_consensus_ownership_claim_only_renders_when_true(self):
        """Review finding 5: 'the consensus XI on this site owns him' is a
        checkable claim about the OTHER squad — it must render only when the
        consensus squad actually owns Haaland (flag stamped by the build)."""
        owns = self._prose("our-squad",
                           _squad_entries(consensus_owns_haaland=True))
        self.assertIn("consensus XI on this site owns him", owns["body_html"])
        for entries in (_squad_entries(consensus_owns_haaland=False),
                        _squad_entries()):        # absent flag = no claim
            prose = self._prose("our-squad", entries)
            self.assertNotIn("consensus XI", prose["body_html"])
            self.assertIn("No Haaland", prose["body_html"])   # conviction stays

    def test_consensus_squad_states_the_method_not_a_model_claim(self):
        prose = self._prose("consensus-squad",
                            _squad_entries(captain="Haaland", source_count=7))
        text = prose["standfirst"] + prose["body_html"]
        self.assertIn("seven", text)                # the 7-source corpus
        self.assertIn("expert consensus", text)     # named in prose as such
        self.assertIn("majority", text)             # majority captain
        self.assertIn("research notes", text)       # minutes provenance
        self.assertIn("Haaland", prose["standfirst"])

    def test_consensus_source_count_derives_from_the_data(self):
        """Review finding 5: 'seven expert sources' was hardcoded — a GW2 tally
        over nine sources would have published a false seven."""
        prose = self._prose("consensus-squad",
                            _squad_entries(captain="Haaland", source_count=9))
        text = prose["standfirst"] + prose["body_html"]
        self.assertIn("nine", text)
        self.assertNotIn("seven", text)

    def test_consensus_prose_claims_no_count_when_the_data_has_none(self):
        prose = self._prose("consensus-squad",
                            _squad_entries(captain="Haaland"))
        text = prose["standfirst"] + prose["body_html"]
        self.assertNotIn("seven", text)
        self.assertNotIn("of them this gameweek", text)
        self.assertIn("expert consensus", text)     # the method claim survives

    def test_never_names_a_bookmaker(self):
        for slug in ("our-squad", "consensus-squad"):
            prose = self._prose(slug, _squad_entries())
            text = (prose["headline"] + prose["standfirst"]
                    + prose["body_html"] + prose["bottom_line"]).lower()
            for banned in ("bet365", "pinnacle", "william hill", "betfair",
                           "unibet", "bookmaker", "bookie"):
                self.assertNotIn(banned, text)

    def test_empty_entries_do_not_crash(self):
        for slug in ("our-squad", "consensus-squad"):
            with self.subTest(slug=slug):
                self.assertTrue(self._prose(slug, [])["headline"])


class TestSquadRenderPieces(unittest.TestCase):
    def test_pitch_svg_flags_the_state_captain_not_rank_one(self):
        xi = [e for e in _squad_entries() if e["role"] == "XI"]
        svg = render.pitch_svg(xi)
        self.assertEqual(svg.count(">C</text>"), 1)
        # move the armband; the badge must move with it
        for e in xi:
            e["is_captain"] = e["name"] == "F2"
        svg2 = render.pitch_svg(xi)
        self.assertEqual(svg2.count(">C</text>"), 1)
        self.assertNotEqual(svg, svg2)

    def test_pitch_svg_fpl_flags_captain_and_vice_once(self):
        xi = [e for e in _squad_entries() if e["role"] == "XI"]
        svg = render.pitch_svg_fpl(xi)
        self.assertEqual(svg.count('r="17"'), 11)      # one disc per player
        self.assertEqual(svg.count(">C</text>"), 1)
        self.assertLessEqual(svg.count(">V</text>"), 1)
        for e in xi:                                    # armband moves with the state
            e["is_captain"] = e["name"] == "F2"
        self.assertNotEqual(render.pitch_svg_fpl(xi), svg)

    def test_pitch_svg_without_captain_flags_keeps_the_rank_rule(self):
        xi = [{"name": f"P{i}", "position": "MID", "x_points": 5.0, "rank": i}
              for i in range(1, 12)]
        svg = render.pitch_svg(xi)
        self.assertEqual(svg.count(">C</text>"), 1)

    def test_summary_sentence_quotes_the_duel_number(self):
        s = render.summary_sentence("our-squad", _squad_entries())
        self.assertIn("Our", s)
        self.assertIn("Cap", s)
        self.assertIn("69.0", s)
        s2 = render.summary_sentence("consensus-squad",
                                     _squad_entries(captain="Haaland"))
        self.assertIn("consensus", s2)
        self.assertIn("Haaland", s2)

    def test_squad_fig_caption_does_not_claim_optimality(self):
        cap = render._article_fig_caption("our-squad", ["x_points"])
        self.assertNotIn("optimal", cap)
        self.assertIn("Our", cap)
        cap2 = render._article_fig_caption("consensus-squad", ["x_points"])
        self.assertIn("consensus", cap2)
        # the wildcard caption is untouched
        self.assertIn("optimal", render._article_fig_caption("wildcard", []))


class TestCeilingWording(unittest.TestCase):
    """Review finding 6: FPL's ceiling is a tail MEAN (the average of a
    player's best 15% of sims, games/fpl/model.tail_mean), strictly >= the
    p85 — '85th-percentile outcome' misstates the statistic on FPL pages.
    The World Cup section's percentile text stays byte-identical."""

    _COLS = ["x_points", "ceiling"]

    def test_fpl_pages_describe_the_tail_mean(self):
        html = render.article_page(1, "captains", "T", _PROSE,
                                   [dict(_ENTRIES[0], ceiling=9.0)], self._COLS,
                                   "/api/fpl/gw1/captains.json", "",
                                   section=render.FPL)
        self.assertIn("best 15%", html)
        self.assertNotIn("85th-percentile", html)

    def test_wc_pages_keep_the_percentile_text(self):
        html = render.article_page(5, "captains", "T", _PROSE,
                                   [dict(_ENTRIES[0], ceiling=9.0)], self._COLS,
                                   "/api/round/5/captains.json", "")
        self.assertIn("85th-percentile", html)
        self.assertNotIn("best 15%", html)

    def test_fig_caption_follows_the_section(self):
        fpl = render._article_fig_caption("captains", ["captain_ev"],
                                          section=render.FPL)
        self.assertIn("best 15%", fpl)
        self.assertNotIn("85th-percentile", fpl)
        wc = render._article_fig_caption("captains", ["captain_ev"])
        self.assertIn("85th-percentile", wc)

    def test_fpl_captains_prose_states_the_tail_mean(self):
        entries = [dict(_ENTRIES[0], captain_ev=12.0, ceiling=10.0, team="ARS",
                        position="FWD", kickoff_order=1)]
        prose = writer.article_prose("captains", 1, entries, self._COLS,
                                     cache_dir="/nonexistent", use_llm=False,
                                     cache_name="fpl-gw1", unit="Gameweek")
        self.assertNotIn("85th-percentile", prose["body_html"])
        self.assertIn("best 15%", prose["body_html"])


class TestLoadStates(unittest.TestCase):
    def test_invalid_states_abort_the_build_naming_both_files(self):
        # a player pool the real squads cannot resolve against
        fake = [{"name": "Nobody", "team": "AAA", "position": "GK", "price": 4.0}]
        with self.assertRaises(SystemExit) as ctx:
            fpl_build.load_states(fake)
        msg = str(ctx.exception)
        self.assertIn("state.json", msg)
        self.assertIn("state_consensus.json", msg)

    def test_real_states_load_against_the_real_bootstrap(self):
        from core import fpl_api
        boot = fpl_api.read_cache("bootstrap")
        if boot is None:
            self.skipTest("bootstrap cache missing")
        states = fpl_build.load_states(fpl_api.parse_players(boot))
        self.assertEqual(states["model"]["strategy"], "model")
        self.assertEqual(states["consensus"]["strategy"], "consensus")


_DUEL = {
    "model": {"projected_total": 74.17, "formation": "3-5-2",
              "captain": "B.Fernandes", "team_name": "The Model XI"},
    "consensus": {"projected_total": 60.4, "formation": "3-5-2",
                  "captain": "Haaland", "team_name": "The Consensus XI"},
}


class TestLandingDuel(unittest.TestCase):
    def _landing(self, duel=None, section=None):
        featured = {"slug": "our-squad",
                    "prose": {"headline": "H", "standfirst": "S",
                              "body_html": "<p>B</p>", "bottom_line": "BL",
                              "source": "template"},
                    "viz_html": ""}
        feed = [{"slug": "captains", "headline": "H", "teaser": "T",
                 "stat_value": "12.0", "stat_label": "Captain EV"}]
        return render.landing_page(1, featured, feed, date_str="20 August 2026",
                                   duel=duel, section=section or render.FPL)

    def test_duel_strip_shows_both_totals_and_labels(self):
        html = self._landing(duel=_DUEL)
        self.assertIn("74.17", html)
        self.assertIn("60.40", html)
        self.assertIn(">Model<", html)
        self.assertIn(">Consensus<", html)
        self.assertIn("B.Fernandes (c)", html)
        self.assertIn("Haaland (c)", html)

    def test_duel_sides_link_to_the_two_squad_articles(self):
        html = self._landing(duel=_DUEL)
        self.assertIn('href="/fpl/gw1/our-squad/"', html)
        self.assertIn('href="/fpl/gw1/consensus-squad/"', html)

    def test_no_duel_means_no_duel_markup_or_css(self):
        """The World Cup landing never passes a duel; its bytes must not grow
        the strip's class names or stylesheet."""
        html = self._landing(duel=None, section=render.WC)
        self.assertNotIn("duel", html)

    def test_no_top_cards_means_no_card_markup_or_css(self):
        """Same gate for the player-cards module: a landing built without
        pre_feed_html/extra_style — every World Cup build — must not grow the
        module's class names or the CARD_CSS block."""
        html = self._landing(duel=None, section=render.WC)
        self.assertNotIn("tc-card", html)
        self.assertNotIn("top-cards", html)
        self.assertNotIn(".player-card", html)

    def test_wc_llms_txt_carries_no_player_cards_section(self):
        txt = render.llms_txt(5, [("captains", "Best captain picks")])
        self.assertNotIn("Player cards", txt)


class TestRatePageSection(unittest.TestCase):
    def test_fpl_rate_page_copy_feed_and_unit(self):
        html = render.rate_page(1, section=render.FPL)
        self.assertIn("<title>Rate my FPL team | ", html)
        self.assertIn("2 goalkeepers, 5 defenders, 5 midfielders", html)
        self.assertIn('data-players-url="/api/fpl/gw1/players.json"', html)
        self.assertIn('data-unit="Gameweek"', html)
        self.assertIn("after the gameweek", html)
        self.assertNotIn("World Cup", html)
        self.assertNotIn("/api/round/", html)
        # the nav pill still highlights the rate page
        self.assertIn('href="/rate/" class="on"', html)

    def test_wc_rate_page_defaults_keep_todays_output(self):
        html = render.rate_page(5)
        self.assertIn("<title>Rate my World Cup fantasy team | ", html)
        self.assertIn('data-players-url="/api/round/5/players.json"', html)
        self.assertNotIn("data-unit", html)
        self.assertIn("manual subs are allowed up", html)

    def test_fpl_rate_picker_is_a_pitch(self):
        """Owner correction 2026-08-25 ("rate my team doesn't look like a
        pitch"): the FPL picker lays the 15 slots out on the grass — position
        rows on a half-pitch, bench strip below — while keeping the exact
        slot/captain contract rate.js already reads."""
        html = render.rate_page(1, section=render.FPL)
        self.assertIn('class="pitch-picker" id="slot-grid"', html)
        self.assertIn('class="pp-lines"', html)          # white markings SVG
        self.assertIn(".pp-pitch{", html)                # pitch CSS shipped
        self.assertIn("repeating-linear-gradient", html)  # mow-stripe grass
        # position rows on the pitch, top to bottom, then the bench strip
        order = [html.find(f'class="pp-row pp-{p}"')
                 for p in ("fwd", "mid", "def", "gk")]
        self.assertTrue(all(at > -1 for at in order))
        self.assertEqual(order, sorted(order))
        self.assertLess(order[-1], html.find('class="pp-bench"'))
        # the same 11+4 slot contract rate.js reads, captain radios 0..10
        self.assertEqual(html.count('data-bench="0"'), 11)
        self.assertEqual(html.count('data-bench="1"'), 4)
        for v in range(11):
            self.assertIn(f'name="cap" value="{v}"', html)
        # paste flow, no-JS fallback and the shared script all survive
        self.assertIn("prefer to paste the whole squad as text?", html)
        self.assertIn("<noscript>", html)
        self.assertIn('<script src="/js/rate.js" defer></script>', html)

    def test_wc_rate_page_carries_no_pitch_markup_or_css(self):
        html = render.rate_page(5)
        self.assertIn('class="slot-grid" id="slot-grid"', html)
        self.assertNotIn("pitch-picker", html)
        self.assertNotIn("pp-pitch", html)
        self.assertNotIn("pp-bench", html)

    def test_rate_js_defaults_the_unit_to_round(self):
        """The shared rate.js must keep labelling WC results 'Round N' when the
        page carries no data-unit attribute."""
        path = os.path.join(os.path.dirname(os.path.abspath(render.__file__)),
                            "assets", "js", "rate.js")
        with open(path, encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn('form.getAttribute("data-unit") || "Round"', js)
        self.assertNotIn('", Round " + roundNo', js)


class TestSquadBuildGuards(unittest.TestCase):
    _META = {"xi_xpoints": 61.0, "projected_total": 69.0}

    def test_state_name_missing_from_rows_aborts_cleanly(self):
        """spec: 'every state name matches the artifact rows' is a preflight
        abort, not a traceback."""
        with mock.patch.object(fpl_build.fpl_articles, "squad_article",
                               side_effect=ValueError(
                                   "squad player 'Ghost' has no row")):
            with self.assertRaises(SystemExit) as ctx:
                fpl_build.entries_or_abort([], [], [], {"model": {},
                                                        "consensus": {}})
        msg = str(ctx.exception)
        self.assertIn("Ghost", msg)
        self.assertIn("preflight", msg)

    def test_finite_totals_pass(self):
        fpl_build.squad_preflight({"our-squad": dict(self._META),
                                   "consensus-squad": dict(self._META)})

    def test_non_finite_total_aborts_naming_the_squad(self):
        bad = {"our-squad": dict(self._META),
               "consensus-squad": {"xi_xpoints": float("nan"),
                                   "projected_total": 69.0}}
        with self.assertRaises(SystemExit) as ctx:
            fpl_build.squad_preflight(bad)
        self.assertIn("consensus-squad", str(ctx.exception))

    def test_missing_meta_aborts(self):
        with self.assertRaises(SystemExit):
            fpl_build.squad_preflight({"our-squad": dict(self._META)})

    def test_eight_articles_and_the_two_squads_lead(self):
        self.assertEqual(len(fpl_build.ARTICLES), 8)
        self.assertEqual(fpl_build.ARTICLES[0], "our-squad")
        self.assertEqual(fpl_build.ARTICLES[1], "captains")
        self.assertIn("consensus-squad", fpl_build.ARTICLES)


class TestPublishGate(unittest.TestCase):
    """Phase 5 task 2 (spec D1): a build whose published squad contains a
    red-flagged player exits with the gate message unless a sourced, dated
    note overrides. Synthetic states à la tests/test_fpl_live_build.py —
    the gate function is exercised directly, exactly like live_layer is."""

    @staticmethod
    def _boot(status="a"):
        return {"teams": [{"id": 1, "short_name": "AVL"}],
                "elements": [{"id": 10, "web_name": "Watkins", "team": 1,
                              "element_type": 4, "status": status,
                              "now_cost": 90, "selected_by_percent": "20.0",
                              "transfers_in_event": 0,
                              "transfers_out_event": 0,
                              "news": "Hamstring" if status != "a" else ""}]}

    _STATE = {"team_name": "The Model XI", "aliases": {},
              "squad": [{"name": "Watkins", "position": "FWD",
                         "is_starter": True, "bench_order": None,
                         "is_captain": True, "is_vice": False}]}

    def _gate(self, status, notes=None):
        from core import fpl_api, ratings
        boot = self._boot(status)
        priors = {"AVL": [ratings.PlayerPrior(name="Watkins", team="AVL",
                                              position="FWD",
                                              start_prob=0.87)]}
        with mock.patch.object(fpl_build.research, "load_entries",
                               return_value=notes or {}), \
             mock.patch("core.fpl_diff.load_previous", return_value=None):
            fpl_build.dossier_gate(1, {"model": self._STATE},
                                   fpl_api.parse_players(boot), priors, boot)

    def test_green_squad_gates_silently(self):
        self._gate("a")

    def test_injured_player_without_note_aborts_naming_him(self):
        with self.assertRaises(SystemExit) as ctx:
            self._gate("i")
        msg = str(ctx.exception)
        self.assertIn("Watkins", msg)
        self.assertIn("publish gate", msg)
        self.assertIn("Hamstring", msg)

    def test_sourced_note_lets_the_same_red_through(self):
        from core.research import ResearchEntry
        note = ResearchEntry(name="Watkins",
                             sources=["https://example.test/press-conf"],
                             updated="2026-08-24")
        self._gate("i", notes={"Watkins": note})


class TestFplTrackRecord(unittest.TestCase):
    """Task 2026-08-25 (owner: "track record is still wc"): FPL builds render
    /track-record/ with the graded FPL ledger FIRST, the WC retrospective
    under its own heading; WC builds keep today's page byte-identical."""

    def test_ledger_reads_the_committed_gw1_grading(self):
        rows = fpl_build.fpl_track_ledger()
        self.assertGreaterEqual(len(rows), 1)
        gw1 = rows[0]
        self.assertEqual(gw1["gw"], 1)
        self.assertEqual(gw1["mae_ours"], 2.734)
        self.assertIsNone(gw1["mae_ep_next"])
        self.assertEqual(gw1["model_projected"], 65.92)
        self.assertEqual(gw1["model_realized"], 44)
        self.assertEqual(gw1["consensus_projected"], 60.74)
        self.assertEqual(gw1["consensus_realized"], 53)
        # GW1 went to the crowd: 44 < 53 official points
        self.assertEqual(gw1["duel_model"], 0)
        self.assertEqual(gw1["duel_consensus"], 1)
        self.assertEqual(gw1["duel_label"], "crowd leads")
        self.assertEqual(gw1["json_path"], "/api/fpl/accuracy/gw1.json")

    def test_duel_score_is_running_across_gameweeks(self):
        import os
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            for gw, ours, cons in ((1, 44, 53), (2, 70, 60), (3, 50, 50)):
                with open(os.path.join(tmp, f"gw{gw}.json"), "w",
                          encoding="utf-8") as fh:
                    json.dump({"gameweek": gw, "mae_ours": 2.0,
                               "mae_ep_next": 2.5,
                               "squads": {
                                   "our-squad": {"projected": 65.0,
                                                 "realized_official": ours},
                                   "consensus-squad": {"projected": 60.0,
                                                       "realized_official": cons},
                               }}, fh)
            with mock.patch.object(fpl_build, "_accuracy_dir",
                                   return_value=tmp):
                rows = fpl_build.fpl_track_ledger()
        self.assertEqual([(r["duel_model"], r["duel_consensus"],
                           r["duel_label"]) for r in rows],
                         [(0, 1, "crowd leads"), (1, 1, "level"),
                          (1, 1, "level")])

    def _page(self, fpl):
        record = {"rounds": [], "summary": {"rounds_graded": 0,
                                            "mean_captain_mae": None,
                                            "mean_spearman": None,
                                            "captain_regrets": []}}
        return render.track_record_page(record, fpl=fpl)

    def test_fpl_section_renders_first_with_the_gw1_row(self):
        html = self._page(fpl_build.fpl_track_ledger())
        fpl_at = html.find("FPL 2026/27 — the graded ledger")
        wc_at = html.find("World Cup 2026 — the retrospective")
        stand_at = html.find("Before every round locks")
        self.assertGreater(fpl_at, -1)
        self.assertGreater(wc_at, -1)
        # FPL first; the existing WC record under its own heading
        self.assertLess(fpl_at, wc_at)
        self.assertLess(wc_at, stand_at)
        # the graded GW1 row, exactly as banked
        self.assertIn("<td>GW1</td>", html)
        self.assertIn("<td>2.734</td>", html)
        self.assertIn("65.92 → 44", html)
        self.assertIn("60.74 → 53", html)
        self.assertIn("0-1 (crowd leads)", html)
        # the one-line method note + public grading JSONs
        self.assertIn("Projections frozen pre-deadline; grading JSONs public",
                      html)
        self.assertIn('href="/api/fpl/accuracy/gw1.json"', html)

    def test_wc_page_is_byte_identical_without_a_ledger(self):
        self.assertEqual(self._page(None), self._page([]))
        html = self._page(None)
        self.assertNotIn("FPL 2026/27", html)
        self.assertNotIn("tr-section-h", html)
        self.assertNotIn("/api/fpl/accuracy/", html)
