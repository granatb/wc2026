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
