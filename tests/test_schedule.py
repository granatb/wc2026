import os
import tempfile
import unittest

from core import schedule_api, fixtures


class TestScheduleApi(unittest.TestCase):
    def test_map_round(self):
        self.assertEqual(schedule_api.map_round("Group Stage - 2"), ("GROUP_MD2", 2))
        self.assertEqual(schedule_api.map_round("Round of 16"), ("R16", 5))
        self.assertEqual(schedule_api.map_round("Final"), ("FINAL", 8))

    def test_normalize_fixture(self):
        item = {
            "fixture": {"id": 42, "date": "2026-06-20T18:00:00+00:00"},
            "teams": {"home": {"name": "Brazil"}, "away": {"name": "Serbia"}},
            "league": {"round": "Group Stage - 2"},
        }
        n = schedule_api.normalize_fixture(item)
        self.assertEqual(n["match_id"], "42")
        self.assertEqual(n["home"], "Brazil")
        self.assertEqual(n["fantasy_round"], 2)
        self.assertEqual(n["stage"], "GROUP_MD2")


class TestFixturesLoader(unittest.TestCase):
    def test_load_from_json_and_round_filter(self):
        rows = [
            {"match_id": "1", "home": "Mexico", "away": "Korea",
             "kickoff_utc": "2026-06-18T19:00:00Z", "stage": "GROUP_MD2", "fantasy_round": 2},
            {"match_id": "2", "home": "Brazil", "away": "Serbia",
             "kickoff_utc": "2026-06-18T22:00:00Z", "stage": "GROUP_MD2", "fantasy_round": 2},
            {"match_id": "3", "home": "Spain", "away": "Japan",
             "kickoff_utc": "2026-06-24T19:00:00Z", "stage": "GROUP_MD3", "fantasy_round": 3},
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            import json
            json.dump(rows, fh)
            path = fh.name
        try:
            loaded = fixtures.load_from_json(path)
            self.assertEqual(len(loaded), 3)
            r2 = [f for f in loaded if f.fantasy_round == 2]
            self.assertEqual(len(r2), 2)
            # host nation Mexico flagged non-neutral
            mex = next(f for f in loaded if f.home == "Mexico")
            self.assertFalse(mex.neutral)
            lock = min(f.kickoff for f in r2)
            self.assertEqual(lock.hour, 19)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
