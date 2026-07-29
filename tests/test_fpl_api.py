import json
import os
import unittest
from unittest import mock

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


class TestParseFixtures(unittest.TestCase):
    def setUp(self):
        self.raw_fx = _load("fpl_fixtures.json")
        self.teams = fpl_api.parse_teams(_load("fpl_bootstrap.json"))

    def test_parse_fixtures_shape(self):
        rows = fpl_api.parse_fixtures(self.raw_fx, self.teams)
        self.assertEqual(len(rows), 20)
        r = rows[0]
        for key in ("match_id", "home", "away", "kickoff_utc", "fantasy_round", "stage"):
            self.assertIn(key, r)

    def test_stage_is_gw_and_round_is_the_gameweek(self):
        rows = fpl_api.parse_fixtures(self.raw_fx, self.teams)
        self.assertEqual({r["stage"] for r in rows}, {"GW"})
        self.assertEqual({r["fantasy_round"] for r in rows}, {1, 2})

    def test_home_and_away_are_short_codes(self):
        rows = fpl_api.parse_fixtures(self.raw_fx, self.teams)
        codes = set(self.teams.values())
        for r in rows:
            self.assertIn(r["home"], codes)
            self.assertIn(r["away"], codes)

    def test_unscheduled_fixtures_are_skipped(self):
        # a fixture with event=None is not yet assigned to a gameweek
        raw = self.raw_fx + [{"id": 999, "event": None, "team_h": 1, "team_a": 2,
                              "kickoff_time": None}]
        rows = fpl_api.parse_fixtures(raw, self.teams)
        self.assertEqual(len(rows), 20)


class TestDefconRateFromHistory(unittest.TestCase):
    """bootstrap-static zeroes every DefCon field; element-summary's history_past
    carries last season's real numbers instead. defensive_contribution is already
    the correct positional aggregate (CBIT for defenders, CBIRT for mid/fwd) --
    this just converts it to a per-90 rate."""

    def test_per90_conversion_matches_known_value(self):
        # Gabriel, 2025/26: 277 DefCon over 2750 minutes -> 9.07 per 90.
        history_past = [
            {"season_name": "2024/25", "minutes": 3200, "defensive_contribution": 210},
            {"season_name": "2025/26", "minutes": 2750, "defensive_contribution": 277},
        ]
        rate, minutes = fpl_api.defcon_rate_from_history(history_past)
        self.assertAlmostEqual(rate, 9.07, places=2)
        self.assertEqual(minutes, 2750)

    def test_picks_most_recent_season_regardless_of_array_order(self):
        history_past = [
            {"season_name": "2025/26", "minutes": 2750, "defensive_contribution": 277},
            {"season_name": "2024/25", "minutes": 1000, "defensive_contribution": 999},
        ]
        rate, minutes = fpl_api.defcon_rate_from_history(history_past)
        self.assertEqual(minutes, 2750)
        self.assertAlmostEqual(rate, 9.07, places=2)

    def test_seasons_with_zero_minutes_are_skipped(self):
        history_past = [{"season_name": "2025/26", "minutes": 0,
                         "defensive_contribution": 0}]
        self.assertEqual(fpl_api.defcon_rate_from_history(history_past), (0.0, 0))

    def test_empty_or_missing_history_returns_zero(self):
        self.assertEqual(fpl_api.defcon_rate_from_history([]), (0.0, 0))
        self.assertEqual(fpl_api.defcon_rate_from_history(None), (0.0, 0))

    def test_matches_the_real_element_summary_fixture(self):
        raw = _load("fpl_element_summary.json")
        rate, minutes = fpl_api.defcon_rate_from_history(raw["history_past"])
        self.assertAlmostEqual(rate, 9.07, places=2)
        self.assertEqual(minutes, 2750)


class TestFetchDefconBackfill(unittest.TestCase):
    """The one-time backfill: fetch element-summary only for ids the cache is
    missing, cache to data/fpl/, skip zero-minute players, tolerate failures."""

    CACHE_NAME = "defcon_backfill_test"

    def _cache_path(self):
        return os.path.join(fpl_api.DATA_DIR, f"{self.CACHE_NAME}.json")

    def tearDown(self):
        path = self._cache_path()
        if os.path.exists(path):
            os.remove(path)

    @staticmethod
    def _players(id_minutes):
        return [{"id": i, "name": f"P{i}", "minutes": m} for i, m in id_minutes]

    @staticmethod
    def _summary(**overrides):
        row = {"season_name": "2025/26", "minutes": 2750,
               "defensive_contribution": 277}
        row.update(overrides)
        return {"history_past": [row]}

    def test_fetches_and_caches_then_a_rerun_fetches_nothing(self):
        players = self._players([(1, 2000), (2, 1500)])
        fetch_mock = mock.Mock(return_value=self._summary())

        result = fpl_api.fetch_defcon_backfill(
            players, fetch=fetch_mock, delay=0, sleep=lambda *_a: None,
            cache_name=self.CACHE_NAME)

        self.assertEqual(fetch_mock.call_count, 2)
        self.assertAlmostEqual(result[1]["defcon_per90"], 9.07, places=2)
        self.assertEqual(result[1]["minutes"], 2750)

        fetch_mock2 = mock.Mock(return_value=self._summary())
        result2 = fpl_api.fetch_defcon_backfill(
            players, fetch=fetch_mock2, delay=0, sleep=lambda *_a: None,
            cache_name=self.CACHE_NAME)

        fetch_mock2.assert_not_called()
        self.assertAlmostEqual(result2[1]["defcon_per90"], result[1]["defcon_per90"])
        self.assertAlmostEqual(result2[2]["defcon_per90"], result[2]["defcon_per90"])

    def test_zero_minute_players_are_never_fetched(self):
        players = self._players([(3, 0)])
        fetch_mock = mock.Mock()

        result = fpl_api.fetch_defcon_backfill(
            players, fetch=fetch_mock, delay=0, sleep=lambda *_a: None,
            cache_name=self.CACHE_NAME)

        fetch_mock.assert_not_called()
        self.assertNotIn(3, result)

    def test_player_absent_from_result_when_fetch_fails(self):
        players = self._players([(10, 2000), (11, 2000)])

        def flaky(pid):
            if pid == 10:
                raise RuntimeError("simulated network failure")
            return self._summary()

        fetch_mock = mock.Mock(side_effect=flaky)
        result = fpl_api.fetch_defcon_backfill(
            players, fetch=fetch_mock, delay=0, sleep=lambda *_a: None,
            cache_name=self.CACHE_NAME)

        self.assertEqual(fetch_mock.call_count, 2)
        self.assertNotIn(10, result)
        self.assertIn(11, result)
        self.assertAlmostEqual(result[11]["defcon_per90"], 9.07, places=2)
