"""Phase 4c task 2: the --live build layer — duel strip so-far totals, the
squad pages' realized panel, and the freeze guarantee (article files
byte-identical when only --live changes).

Offline: live data is canned grade_squad output or mocked cache reads; the
end-to-end class uses the repo's cached bootstrap exactly like
tests/test_fpl_site.TestGameweekBuild does (and skips without it).
"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from core import fpl_api
from evmax import fpl_build, render

_FETCHED_AT = "2026-08-22T18:00:00+00:00"


def _grade(total=44, pending=1, rows=None):
    return {
        "rows": rows if rows is not None else [
            {"name": "Raya", "club": "ARS", "points": 3, "multiplier": 1,
             "status": "played", "note": ""},
            {"name": "B.Fernandes", "club": "MUN", "points": 6, "multiplier": 2,
             "status": "played", "note": ""},
            {"name": "E.Le Fée", "club": "SUN", "points": 0, "multiplier": 1,
             "status": "pending", "note": "to play"},
            {"name": "Watkins", "club": "AVL", "points": 0, "multiplier": 0,
             "status": "blank", "note": "0 minutes — N.Williams comes in"},
            {"name": "N.Williams", "club": "NFO", "points": 2, "multiplier": 1,
             "status": "autosub_in", "note": "in for Watkins"},
            {"name": "Sánchez", "club": "CHE", "points": 1, "multiplier": 0,
             "status": "played", "note": ""},
        ],
        "total_so_far": total,
        "players_pending": pending,
        "autosubs_applied": [{"out": "Watkins", "in": "N.Williams"}],
        "captain_effective": "B.Fernandes",
    }


_LIVE_DATA = {"fetched_at": _FETCHED_AT,
              "model": _grade(44, 1),
              "consensus": _grade(42, 0)}

_DUEL = {
    "model": {"projected_total": 74.17, "formation": "3-5-2",
              "captain": "B.Fernandes", "team_name": "The Model XI"},
    "consensus": {"projected_total": 60.4, "formation": "3-5-2",
                  "captain": "Haaland", "team_name": "The Consensus XI"},
}


class TestDuelStripLive(unittest.TestCase):
    def test_live_duel_shows_so_far_totals_and_pending(self):
        duel = dict(_DUEL, live=_LIVE_DATA)
        html = render._duel_strip_html(duel, 1, section=render.FPL)
        self.assertIn("<b>44</b> so far · 1 to play", html)
        self.assertIn("<b>42</b> so far · all played", html)
        # the frozen projections stay right next to the realized totals
        self.assertIn("74.17", html)
        self.assertIn("60.40", html)

    def test_duel_without_live_data_has_no_so_far_markup(self):
        html = render._duel_strip_html(dict(_DUEL), 1, section=render.FPL)
        self.assertNotIn("so far", html)
        self.assertNotIn("duel-so-far", html)

    def test_one_sided_live_data_renders_one_side_only(self):
        duel = dict(_DUEL, live={"model": _grade(44, 1)})
        html = render._duel_strip_html(duel, 1, section=render.FPL)
        self.assertEqual(html.count("duel-so-far"), 1)


class TestSquadLivePanel(unittest.TestCase):
    def test_panel_shows_total_pending_rows_and_the_stamp(self):
        html = render.squad_live_panel_html(_grade(44, 1), _FETCHED_AT)
        self.assertIn("<b>44</b> pts so far · 1 to play", html)
        self.assertIn("live — updates on rebuild · as of 2026-08-22 18:00 UTC",
                      html)
        for name in ("Raya", "B.Fernandes", "N.Williams", "Sánchez"):
            self.assertIn(name, html)
        self.assertIn("to play", html)
        self.assertIn("autosub in", html)
        self.assertIn("in for Watkins", html)

    def test_captain_row_doubles_and_bench_rows_grey_out(self):
        html = render.squad_live_panel_html(_grade(), _FETCHED_AT)
        self.assertIn(">12 (c)<", html)          # 6 pts × the armband
        self.assertIn('class="lp-out"', html)    # multiplier-0 rows marked
        self.assertIn(">(1)<", html)             # unused bench: raw, bracketed

    def test_all_played_panel_says_so(self):
        html = render.squad_live_panel_html(_grade(42, 0), _FETCHED_AT)
        self.assertIn("<b>42</b> pts so far · all played", html)

    def test_empty_grade_renders_nothing(self):
        self.assertEqual(render.squad_live_panel_html(None, _FETCHED_AT), "")

    def test_article_page_embeds_panel_and_css_only_when_passed(self):
        prose = {"headline": "H", "standfirst": "S", "body_html": "<p>B</p>",
                 "bottom_line": "BL", "source": "template"}
        entries = [{"name": "A", "rank": 1, "x_points": 6.0, "price": 5.0,
                    "captain_ev": 12.0}]
        args = (1, "our-squad", "T", prose, entries, ["x_points"],
                "/api/fpl/gw1/our-squad.json", "")
        plain = render.article_page(*args, section=render.FPL)
        self.assertNotIn("live-panel", plain)
        panel = render.squad_live_panel_html(_grade(), _FETCHED_AT)
        live = render.article_page(*args, section=render.FPL, live_html=panel)
        self.assertIn('class="live-panel"', live)
        self.assertIn(".live-panel{", live)      # CSS rides only with the panel
        # the panel renders above the prose, after the byline
        self.assertLess(live.find('<div class="meta">'),
                        live.find('class="live-panel"'))
        self.assertLess(live.find('class="live-panel"'),
                        live.find('<div class="prose">'))

    def test_article_page_with_empty_live_html_is_byte_identical(self):
        prose = {"headline": "H", "standfirst": "S", "body_html": "<p>B</p>",
                 "bottom_line": "BL", "source": "template"}
        entries = [{"name": "A", "rank": 1, "x_points": 6.0, "price": 5.0,
                    "captain_ev": 12.0}]
        args = (5, "captains", "T", prose, entries, ["x_points"],
                "/api/round/5/captains.json", "")
        self.assertEqual(render.article_page(*args),
                         render.article_page(*args, live_html=""))


def _boot_events(gameweek=1, is_current=True):
    return {"events": [{"id": gameweek, "is_current": is_current,
                        "is_next": not is_current}]}


class TestLiveDefault(unittest.TestCase):
    _NOW = datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc)

    def _default(self, boot, fixtures):
        with mock.patch.object(fpl_build.fpl_api, "read_cache",
                               return_value=fixtures):
            return fpl_build._live_default(1, boot, now=self._NOW)

    def test_on_when_current_and_a_fixture_started(self):
        fx = [{"event": 1, "team_h": 1, "team_a": 2, "started": True,
               "kickoff_time": "2026-08-22T14:00:00Z"}]
        self.assertTrue(self._default(_boot_events(is_current=True), fx))

    def test_off_before_any_kickoff(self):
        fx = [{"event": 1, "team_h": 1, "team_a": 2, "started": False,
               "kickoff_time": "2026-08-22T16:30:00Z"}]
        self.assertFalse(self._default(_boot_events(is_current=True), fx))

    def test_off_when_the_gameweek_is_not_current(self):
        fx = [{"event": 1, "team_h": 1, "team_a": 2, "started": True,
               "kickoff_time": "2026-08-22T14:00:00Z"}]
        self.assertFalse(self._default(_boot_events(is_current=False), fx))

    def test_other_gameweeks_fixtures_do_not_count(self):
        fx = [{"event": 2, "team_h": 1, "team_a": 2, "started": True,
               "kickoff_time": "2026-08-22T14:00:00Z"}]
        self.assertFalse(self._default(_boot_events(is_current=True), fx))

    def test_off_with_no_bootstrap_or_no_event(self):
        self.assertFalse(fpl_build._live_default(1, None, now=self._NOW))
        self.assertFalse(fpl_build._live_default(
            1, {"events": [{"id": 2, "is_current": True}]}, now=self._NOW))


class TestLiveLayer(unittest.TestCase):
    _STATES = {"model": {"squad": []}, "consensus": {"squad": []}}
    _PAYLOAD = {"gameweek": 1, "fetched_at": _FETCHED_AT,
                "live": {"elements": []}, "fixtures": []}

    def test_refresh_fetches_and_grades_both_squads(self):
        with mock.patch.object(fpl_build.fpl_live, "refresh_live",
                               return_value=self._PAYLOAD) as refresh, \
             mock.patch.object(fpl_build.fpl_live, "grade_squad",
                               return_value=_grade()) as grade:
            live_data, warnings = fpl_build.live_layer(
                1, self._STATES, {"elements": []}, refresh=True)
        refresh.assert_called_once_with(1)
        self.assertEqual(grade.call_count, 2)
        self.assertEqual(live_data["fetched_at"], _FETCHED_AT)
        self.assertEqual(live_data["model"]["total_so_far"], 44)
        self.assertEqual(warnings, [])

    def test_auto_mode_reads_the_cache_never_the_network(self):
        with mock.patch.object(fpl_build.fpl_live, "refresh_live") as refresh, \
             mock.patch.object(fpl_build.fpl_live, "read_live_cache",
                               return_value=self._PAYLOAD), \
             mock.patch.object(fpl_build.fpl_live, "grade_squad",
                               return_value=_grade()):
            live_data, warnings = fpl_build.live_layer(
                1, self._STATES, {}, refresh=False)
        refresh.assert_not_called()
        self.assertIsNotNone(live_data)
        self.assertEqual(warnings, [])

    def test_failed_refresh_falls_back_to_the_cache_with_a_warning(self):
        with mock.patch.object(fpl_build.fpl_live, "refresh_live",
                               side_effect=OSError("offline")), \
             mock.patch.object(fpl_build.fpl_live, "read_live_cache",
                               return_value=self._PAYLOAD), \
             mock.patch.object(fpl_build.fpl_live, "grade_squad",
                               return_value=_grade()):
            live_data, warnings = fpl_build.live_layer(
                1, self._STATES, {}, refresh=True)
        self.assertIsNotNone(live_data)
        self.assertTrue(any("LIVE REFRESH FAILED" in w for w in warnings))

    def test_no_data_at_all_aborts_an_explicit_live_build(self):
        with mock.patch.object(fpl_build.fpl_live, "refresh_live",
                               side_effect=OSError("offline")), \
             mock.patch.object(fpl_build.fpl_live, "read_live_cache",
                               return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                fpl_build.live_layer(1, self._STATES, {}, refresh=True)
        self.assertIn("--live", str(ctx.exception))

    def test_auto_mode_without_a_cache_skips_with_a_warning(self):
        with mock.patch.object(fpl_build.fpl_live, "read_live_cache",
                               return_value=None):
            live_data, warnings = fpl_build.live_layer(
                1, self._STATES, {}, refresh=False)
        self.assertIsNone(live_data)
        self.assertTrue(any("LIVE LAYER SKIPPED" in w for w in warnings))

    def test_unresolved_squad_name_aborts_the_build(self):
        """grade_squad fails loudly listing unresolved names; the build must
        turn that into a clean abort, never a 14-man published total."""
        with mock.patch.object(fpl_build.fpl_live, "read_live_cache",
                               return_value=self._PAYLOAD), \
             mock.patch.object(fpl_build.fpl_live, "grade_squad",
                               side_effect=ValueError(
                                   "live join failed — 'Sangaré'")):
            with self.assertRaises(SystemExit) as ctx:
                fpl_build.live_layer(1, self._STATES, {}, refresh=False)
        self.assertIn("Sangaré", str(ctx.exception))


class TestCliLiveFlag(unittest.TestCase):
    def _kwargs(self, argv):
        from evmax import build as build_mod
        with mock.patch.object(build_mod, "fpl_build") as fake:
            with mock.patch("sys.argv", ["build"] + argv):
                build_mod.main()
        return fake.build.call_args.kwargs

    def test_live_flag_passes_true(self):
        self.assertIs(self._kwargs(["--gw", "1", "--no-llm", "--live"])["live"],
                      True)

    def test_no_live_flag_passes_false(self):
        self.assertIs(
            self._kwargs(["--gw", "1", "--no-llm", "--no-live"])["live"],
            False)

    def test_default_is_auto(self):
        self.assertIsNone(self._kwargs(["--gw", "1", "--no-llm"])["live"])


class _FrozenDatetime(datetime):
    """fpl_build's clock, pinned: two builds must differ ONLY by --live."""

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 8, 22, 18, 0, 0, tzinfo=tz or timezone.utc)


class TestFrozenArticlesUnderLive(unittest.TestCase):
    """THE phase 4c freeze gate: with the clock pinned, a --live build and a
    plain build produce byte-identical trees EXCEPT the landing (root +
    section copy) and the two squad pages' HTML (the panel block). Every
    other article file — HTML, JSON envelope, markdown twin, both squad
    slugs' JSON/md included — is a frozen published claim."""

    _ALLOWED_DIFF = {
        "index.html",                            # the landing (root copy)
        os.path.join("fpl", "gw1", "index.html"),
        os.path.join("fpl", "gw1", "our-squad", "index.html"),
        os.path.join("fpl", "gw1", "consensus-squad", "index.html"),
    }

    @classmethod
    def setUpClass(cls):
        if fpl_api.read_cache("bootstrap") is None:
            raise unittest.SkipTest(
                "data/fpl bootstrap cache missing — populate with "
                "`python3 manage.py fpl --round 1 --refresh`")
        cls._saved_site_url = render.SITE_URL
        cls.base = tempfile.TemporaryDirectory()
        cls.live = tempfile.TemporaryDirectory()
        cls.prose = tempfile.TemporaryDirectory()
        with mock.patch.object(fpl_build, "datetime", _FrozenDatetime):
            fpl_build.build(gameweek=1, sims=200, out=cls.base.name,
                            url="https://example.test", use_llm=False,
                            cache_dir=cls.prose.name, live=False)
            with mock.patch.object(fpl_build, "live_layer",
                                   return_value=(dict(_LIVE_DATA), [])):
                fpl_build.build(gameweek=1, sims=200, out=cls.live.name,
                                url="https://example.test", use_llm=False,
                                cache_dir=cls.prose.name, live=True)

    @classmethod
    def tearDownClass(cls):
        render.SITE_URL = cls._saved_site_url
        cls.base.cleanup()
        cls.live.cleanup()
        cls.prose.cleanup()

    @staticmethod
    def _tree(root):
        out = {}
        for dirpath, _dirs, files in os.walk(root):
            for fname in files:
                path = os.path.join(dirpath, fname)
                with open(path, "rb") as fh:
                    out[os.path.relpath(path, root)] = fh.read()
        return out

    def test_live_touches_only_the_landing_and_the_two_squad_pages(self):
        base, live = self._tree(self.base.name), self._tree(self.live.name)
        self.assertEqual(sorted(base), sorted(live))   # no file appears/vanishes
        differing = {rel for rel in base if base[rel] != live[rel]}
        self.assertEqual(differing, self._ALLOWED_DIFF)

    def test_the_live_surfaces_actually_carry_the_live_layer(self):
        live = self._tree(self.live.name)
        landing = live["index.html"].decode("utf-8")
        self.assertIn("<b>44</b> so far · 1 to play", landing)
        self.assertIn("<b>42</b> so far · all played", landing)
        for slug, total in (("our-squad", 44), ("consensus-squad", 42)):
            page = live[os.path.join("fpl", "gw1", slug,
                                     "index.html")].decode("utf-8")
            self.assertIn('class="live-panel"', page)
            self.assertIn(f"<b>{total}</b> pts so far", page)
            self.assertIn("updates on rebuild", page)

    def test_squad_json_and_markdown_twins_stay_frozen(self):
        """Belt and braces on top of the tree diff: the squad slugs' JSON
        envelope and md twin are article BODIES and must never move."""
        base, live = self._tree(self.base.name), self._tree(self.live.name)
        for slug in ("our-squad", "consensus-squad"):
            for rel in (os.path.join("api", "fpl", "gw1", f"{slug}.json"),
                        os.path.join("fpl", "gw1", f"{slug}.md")):
                self.assertEqual(base[rel], live[rel], rel)


if __name__ == "__main__":
    unittest.main()
