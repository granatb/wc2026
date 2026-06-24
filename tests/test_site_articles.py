import json
import os
import tempfile
import unittest

from site import articles


class LoadPlayerMetaTest(unittest.TestCase):
    def _write(self, players):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"_comment": "x", "players": players}, fh)
        self.addCleanup(os.remove, path)
        return path

    def test_maps_name_to_metadata(self):
        path = self._write([
            {"name": "Kane", "aliases": [], "team": "England", "fifa_pos": "FWD",
             "fifa_price": 11.0, "ownership": 42.0},
        ])
        meta = articles.load_player_meta(path)
        self.assertEqual(meta["Kane"]["team"], "England")
        self.assertEqual(meta["Kane"]["position"], "FWD")
        self.assertEqual(meta["Kane"]["price"], 11.0)
        self.assertEqual(meta["Kane"]["ownership_pct"], 42.0)

    def test_aliases_also_resolve(self):
        path = self._write([
            {"name": "Bruno Fernandes", "aliases": ["B. Fernandes"], "team": "Portugal",
             "fifa_pos": "MID", "fifa_price": 9.5, "ownership": 18.0},
        ])
        meta = articles.load_player_meta(path)
        self.assertIn("B. Fernandes", meta)
        self.assertEqual(meta["B. Fernandes"]["position"], "MID")


class BuildRowsTest(unittest.TestCase):
    def setUp(self):
        self.means = {
            "Kane": {"position": "FWD", "goals": 0.8, "assists": 0.2, "clean_sheet": 0.3,
                     "played": 1.0, "yellow": 0.1, "red": 0.0, "sot": 1.2, "saves": 0.0,
                     "conc_beyond": 0.4, "minutes": 90.0, "goal_share": 0.4, "assist_share": 0.2},
        }
        self.samples = {"Kane": [0, 1, 0, 2, 1]}
        self.meta = {"Kane": {"team": "England", "position": "FWD", "price": 11.0,
                              "ownership_pct": 42.0}}
        self.kickoffs = {"England": "2026-06-26T19:00:00+00:00"}

    def test_row_has_xpts_ceiling_captain_value_kickoff(self):
        rows = articles.build_rows(self.means, self.samples, self.meta, self.kickoffs)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["name"], "Kane")
        self.assertGreater(r["x_points"], 0)
        self.assertAlmostEqual(r["captain_ev"], 2 * r["x_points"], places=6)
        self.assertGreaterEqual(r["ceiling"], r["x_points"])  # P85 goals >= mean goals
        self.assertAlmostEqual(r["value"], r["x_points"] / 11.0, places=6)
        self.assertEqual(r["kickoff"], "2026-06-26T19:00:00+00:00")

    def test_players_without_meta_or_position_are_skipped(self):
        means = dict(self.means)
        means["Ghost"] = dict(self.means["Kane"])  # no meta entry
        rows = articles.build_rows(means, {"Kane": [0, 1], "Ghost": [0]}, self.meta, self.kickoffs)
        self.assertEqual([r["name"] for r in rows], ["Kane"])
