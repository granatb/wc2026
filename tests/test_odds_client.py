import json
import os
import unittest

from core import odds

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "odds_event_sample.json")


class TestOddsClient(unittest.TestCase):
    def setUp(self):
        with open(FIXTURE, encoding="utf-8") as fh:
            self.raw = json.load(fh)

    def test_normalize_shape(self):
        n = odds.normalize_event(self.raw)
        self.assertEqual(n["match_id"], "match_bra_srb")
        self.assertEqual(n["home"], "Brazil")
        self.assertIsNotNone(n["h2h"]["home"])
        self.assertIsNotNone(n["h2h"]["draw"])
        self.assertEqual(n["totals"]["line"], 2.5)

    def test_consensus_averages_books(self):
        n = odds.normalize_event(self.raw)
        self.assertAlmostEqual(n["h2h"]["home"], (1.55 + 1.57) / 2)

    def test_derive_match_gives_stronger_home(self):
        d = odds.derive_match(odds.normalize_event(self.raw))
        self.assertGreater(d["lam_home"], d["lam_away"])
        self.assertAlmostEqual(sum(d["p1x2"].values()), 1.0, places=6)
        self.assertGreater(d["p1x2"]["home"], d["p1x2"]["away"])

    def test_player_goal_rates(self):
        props = {"bookmakers": [{"key": "pinnacle", "markets": [
            {"key": "player_goal_scorer_anytime", "outcomes": [
                {"description": "Vinicius Jr", "price": 2.5},
                {"description": "Richarlison", "price": 3.5},
            ]}
        ]}]}
        rates = odds.player_goal_rates(props)
        self.assertIn("Vinicius Jr", rates)
        self.assertGreater(rates["Vinicius Jr"], rates["Richarlison"])

    def test_fetch_without_key_raises(self):
        os.environ.pop("ODDS_API_KEY", None)
        with self.assertRaises(RuntimeError):
            odds.fetch_events()

    def test_load_cached_missing_returns_none(self):
        self.assertIsNone(odds.load_cached("does_not_exist_xyz"))


if __name__ == "__main__":
    unittest.main()
