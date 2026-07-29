import json
import os
import unittest

from core import fpl_api

FX = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FX, name), encoding="utf-8") as fh:
        return json.load(fh)


class TestParseTeams(unittest.TestCase):
    def setUp(self):
        self.raw = _load("fpl_bootstrap.json")

    def test_parse_teams_maps_id_to_short_name(self):
        teams = fpl_api.parse_teams(self.raw)
        self.assertEqual(len(teams), 20)
        # every value is a short code, every key an int id
        self.assertTrue(all(isinstance(k, int) for k in teams))
        self.assertIn("LIV", teams.values())


class TestParseEvents(unittest.TestCase):
    def setUp(self):
        self.raw = _load("fpl_bootstrap.json")

    def test_parse_events_returns_utc_deadlines(self):
        events = fpl_api.parse_events(self.raw)
        gw1 = events[1]
        self.assertEqual(gw1["id"], 1)
        # deadline is timezone-aware UTC, never naive
        self.assertIsNotNone(gw1["deadline"].tzinfo)
        self.assertEqual(gw1["deadline"].utcoffset().total_seconds(), 0)

    def test_gw1_deadline_is_the_known_value(self):
        events = fpl_api.parse_events(self.raw)
        self.assertEqual(events[1]["deadline"].isoformat(), "2026-08-21T17:30:00+00:00")


class TestParsePlayers(unittest.TestCase):
    def setUp(self):
        self.raw = _load("fpl_bootstrap.json")
        self.players = fpl_api.parse_players(self.raw)

    def test_positions_use_repo_vocabulary_not_fpl(self):
        positions = {p["position"] for p in self.players}
        self.assertTrue(positions <= {"GK", "DEF", "MID", "FWD"})
        self.assertNotIn("GKP", positions)

    def test_price_is_in_millions(self):
        # now_cost is tenths of a million in the feed; we expose millions
        for p in self.players:
            self.assertGreaterEqual(p["price"], 3.5)
            self.assertLessEqual(p["price"], 20.0)

    def test_team_is_short_code(self):
        teams = set(fpl_api.parse_teams(self.raw).values())
        for p in self.players:
            self.assertIn(p["team"], teams)

    def test_per90_rates_present_and_numeric(self):
        for p in self.players:
            self.assertIsInstance(p["xg_per90"], float)
            self.assertIsInstance(p["xa_per90"], float)
            self.assertGreaterEqual(p["xg_per90"], 0.0)

    def test_availability_fields_carried_through(self):
        by_status = {p["status"] for p in self.players}
        self.assertIn("a", by_status)
        for p in self.players:
            self.assertIn("chance_of_playing", p)

    def test_pen_taker_flag_from_penalties_order(self):
        # penalties_order == 1 is the designated taker
        flags = {p["name"]: p["pen_taker"] for p in self.players}
        self.assertIn(True, flags.values())


class TestScoringConfig(unittest.TestCase):
    def setUp(self):
        self.raw = _load("fpl_bootstrap.json")

    def test_parse_scoring_reads_goal_values_by_position(self):
        sc = fpl_api.parse_scoring(self.raw)
        # 2026/27: a goalkeeper goal is worth 10
        self.assertEqual(sc["goals_scored"]["GK"], 10)
        self.assertEqual(sc["goals_scored"]["DEF"], 6)
        self.assertEqual(sc["goals_scored"]["MID"], 5)
        self.assertEqual(sc["goals_scored"]["FWD"], 4)

    def test_parse_scoring_maps_gkp_key_to_gk(self):
        sc = fpl_api.parse_scoring(self.raw)
        self.assertNotIn("GKP", sc["goals_scored"])

    def test_parse_squad_rules(self):
        r = fpl_api.parse_squad_rules(self.raw)
        self.assertEqual(r["squad_size"], 15)
        self.assertEqual(r["squad_play"], 11)
        self.assertEqual(r["team_limit"], 3)
        self.assertEqual(r["budget"], 100.0)
