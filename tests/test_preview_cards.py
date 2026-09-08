"""Preview cards (owner decision 2026-09-08).

Between a gameweek's last whistle and Thursday the site shows cards for the
NEXT open gameweek — a fresh simulation on today's inputs, labelled as a
preview, published under its own API path, replaced by Thursday's real
cards. The locked gameweek's own forecast surfaces stay frozen.
"""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from evmax import fpl_players
from tests.test_fpl_players import _payloads


PREVIEW = {"gameweek": 4, "as_of": "2026-09-08T09:30:00+00:00",
           "deadline": "2026-09-11T17:30:00Z"}


def _preview_payloads():
    payloads, _ = _payloads()
    for p in payloads:
        p["preview"] = dict(PREVIEW)
        p["gameweek"] = 4
    return payloads


class PreviewGameweekTest(unittest.TestCase):
    boot = {"events": [
        {"id": 3, "deadline_time": "2026-09-04T17:30:00Z"},
        {"id": 4, "deadline_time": "2026-09-11T17:30:00Z"},
        {"id": 5, "deadline_time": "2026-09-19T12:30:00Z"},
    ]}

    def test_first_open_deadline_wins(self):
        from evmax import fpl_build
        now = datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc)
        self.assertEqual(fpl_build._preview_gameweek(self.boot, now), 4)

    def test_no_open_gameweek_previews_nothing(self):
        from evmax import fpl_build
        now = datetime(2026, 9, 30, tzinfo=timezone.utc)
        self.assertIsNone(fpl_build._preview_gameweek(self.boot, now))
        self.assertIsNone(fpl_build._preview_gameweek(None, now))


class PreviewNoteTest(unittest.TestCase):
    def test_note_names_gameweek_date_and_deadline(self):
        html = fpl_players.preview_note_html(PREVIEW)
        self.assertIn("Gameweek 4", html)
        self.assertIn("8 September", html)
        self.assertIn("Thursday", html)
        self.assertIn("Fri 11 Sep, 18:30 UK", html)

    def test_no_preview_no_note(self):
        self.assertEqual(fpl_players.preview_note_html(None), "")


class PreviewSurfacesTest(unittest.TestCase):
    def test_top_cards_label_the_preview(self):
        html = fpl_players.top_cards_html(_preview_payloads())
        self.assertIn('class="tcf-preview"', html)
        self.assertIn("Our picks for gameweek 4 · preview", html)
        # The fixture squad has no crowd movement, so the transfer rows are
        # omitted (as designed); what matters is that no row still says
        # "this gameweek" about a week that is over.
        self.assertNotIn("this gameweek", html)

    def test_top_cards_without_preview_are_unchanged(self):
        payloads, _ = _payloads()
        html = fpl_players.top_cards_html(payloads)
        self.assertNotIn("tcf-preview", html)
        self.assertIn("Our picks this gameweek", html)

    def test_player_page_points_at_the_preview_json(self):
        p = _preview_payloads()[0]
        html = fpl_players.player_page_html(p, 4, date_str="8 September 2026")
        self.assertIn("/api/fpl/preview/players/11.json", html)
        self.assertNotIn("/api/fpl/gw4/players/", html)
        self.assertIn("Gameweek 4 preview", html)
        self.assertIn('class="pc-preview"', html)

    def test_player_page_without_preview_keeps_the_gameweek_json(self):
        payloads, _ = _payloads()
        html = fpl_players.player_page_html(payloads[0], 2)
        self.assertIn("/api/fpl/gw2/players/11.json", html)
        self.assertNotIn("preview", html.lower().split("<article")[1][:400])

    def test_index_and_tiers_carry_the_label(self):
        payloads = _preview_payloads()
        idx = fpl_players.index_page_html(payloads, 4, fpl_players.PREVIEW_FEED_PATH,
                                          preview=PREVIEW)
        self.assertIn("Gameweek 4 preview", idx)
        self.assertIn(fpl_players.PREVIEW_FEED_PATH, idx)
        tier = fpl_players.tier_page_html("MID", payloads, 4, preview=PREVIEW)
        self.assertIn("Gameweek 4 preview", tier)
        self.assertIn('class="pc-preview"', tier)


class LockedBuildPreviewTest(unittest.TestCase):
    def test_locked_build_shows_preview_cards_not_a_notice(self):
        from evmax import fpl_build, render
        from core import fpl_api, engine_events as engine
        if fpl_api.read_cache("bootstrap") is None:
            self.skipTest("local FPL cache unavailable")
        payloads = _preview_payloads()
        rows = [dict(p["projection"], name=p["name"], team=p["team"],
                     position=p["position"]) for p in payloads]
        fake = (payloads, [], {}, rows, dict(PREVIEW))
        site_url = render.SITE_URL
        try:
            with tempfile.TemporaryDirectory() as tmp, \
                 patch.object(fpl_build, "_preview_gameweek", return_value=4), \
                 patch.object(fpl_build, "_preview_payloads", return_value=fake), \
                 patch.object(fpl_build.fpl_model, "load_gameweek",
                              side_effect=AssertionError("historical data reload")), \
                 patch.object(engine, "simulate_round",
                              side_effect=AssertionError("historical resimulation")):
                fpl_build.build(1, 200, tmp, use_llm=False, live=False)
                out = Path(tmp)
                landing = (out / "index.html").read_text()
                self.assertNotIn("Legacy archive", landing)
                self.assertIn("Our picks for gameweek 4 · preview", landing)
                index = (out / "fpl/players/index.html").read_text()
                self.assertIn("player-index-table", index)
                self.assertNotIn("incomplete player archive", index)
                self.assertTrue((out / "api/fpl/preview/players/11.json").is_file())
                feed = json.loads((out / "api/fpl/preview/players.json").read_text())
                self.assertEqual(feed["gameweek"], 4)
                self.assertEqual(feed["preview"]["gameweek"], 4)
                # The locked gameweek's own board is still declared unavailable.
                dataset = json.loads((out / "api/fpl/dataset/gw1.json").read_text())
                self.assertEqual(dataset["status"], "unavailable")
        finally:
            render.SITE_URL = site_url


if __name__ == "__main__":
    unittest.main()
