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
    missing, cache to data/fpl/, tolerate failures.

    Zero-minute players USED to be skipped here; they no longer are (see
    TestHistoryBackfillCache.test_zero_minute_players_are_now_fetched for why)."""

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


class TestFixtureDifficultyRetained(unittest.TestCase):
    def test_parse_fixtures_keeps_both_difficulties(self):
        raw = [{"event": 1, "team_h": 1, "team_a": 2, "id": 9,
                "kickoff_time": "2026-08-21T19:00:00Z",
                "team_h_difficulty": 2, "team_a_difficulty": 5}]
        row = fpl_api.parse_fixtures(raw, {1: "ARS", 2: "COV"})[0]
        self.assertEqual(row["home_difficulty"], 2)
        self.assertEqual(row["away_difficulty"], 5)

    def test_missing_difficulty_is_none_not_zero(self):
        """Zero would read as 'easiest possible fixture'; absent must stay absent."""
        raw = [{"event": 1, "team_h": 1, "team_a": 2, "id": 9,
                "kickoff_time": "2026-08-21T19:00:00Z"}]
        row = fpl_api.parse_fixtures(raw, {1: "ARS", 2: "COV"})[0]
        self.assertIsNone(row["home_difficulty"])
        self.assertIsNone(row["away_difficulty"])

    def test_existing_fixture_fields_are_unchanged(self):
        """Additive only — every current consumer must keep working."""
        raw = [{"event": 1, "team_h": 1, "team_a": 2, "id": 9,
                "kickoff_time": "2026-08-21T19:00:00Z",
                "team_h_difficulty": 2, "team_a_difficulty": 5}]
        row = fpl_api.parse_fixtures(raw, {1: "ARS", 2: "COV"})[0]
        for key in ("match_id", "home", "away", "kickoff_utc", "fantasy_round",
                    "stage"):
            self.assertIn(key, row)


class TestTeamStrengthRetained(unittest.TestCase):
    RAW = {"teams": [
        {"id": 1, "short_name": "ARS", "name": "Arsenal",
         "strength_overall_home": 4, "strength_overall_away": 5,
         "strength_attack_home": 0, "strength_attack_away": 0,
         "strength_defence_home": 0, "strength_defence_away": 0},
        {"id": 2, "short_name": "COV", "name": "Coventry",
         "strength_overall_home": 2, "strength_overall_away": 2,
         "strength_attack_home": 0, "strength_attack_away": 0,
         "strength_defence_home": 0, "strength_defence_away": 0},
    ]}

    def test_keyed_by_short_name_with_overall_strength(self):
        out = fpl_api.parse_team_strength(self.RAW)
        self.assertEqual(out["ARS"]["overall_home"], 4)
        self.assertEqual(out["ARS"]["overall_away"], 5)
        self.assertEqual(out["COV"]["overall_home"], 2)

    def test_zero_attack_defence_reads_as_unavailable(self):
        """Preseason these are 0 for every club — that is 'no data', not 'weakest'.
        A consumer treating 0 as a rating would rank the whole league as awful."""
        out = fpl_api.parse_team_strength(self.RAW)
        self.assertIsNone(out["ARS"]["attack_home"])
        self.assertIsNone(out["ARS"]["attack_away"])
        self.assertIsNone(out["ARS"]["defence_home"])
        self.assertIsNone(out["ARS"]["defence_away"])

    def test_nonzero_attack_defence_is_kept(self):
        """In-season FPL populates these; then they are strictly better than the
        overall figure and later tasks prefer them."""
        raw = {"teams": [dict(self.RAW["teams"][0],
                              strength_attack_home=1300, strength_attack_away=1310,
                              strength_defence_home=1200, strength_defence_away=1210)]}
        out = fpl_api.parse_team_strength(raw)
        self.assertEqual(out["ARS"]["attack_home"], 1300)
        self.assertEqual(out["ARS"]["defence_away"], 1210)

    def test_parse_teams_is_unchanged(self):
        """The existing id -> short_name map has other callers."""
        self.assertEqual(fpl_api.parse_teams(self.RAW), {1: "ARS", 2: "COV"})


class TestHistoryPastRetained(unittest.TestCase):
    ES = {"history_past": [
        {"season_name": "2024/25", "minutes": 1800, "total_points": 90,
         "clean_sheets": 8, "goals_conceded": 30, "bps": 300, "starts": 20,
         "expected_goals": "3.1", "expected_assists": "2.4",
         "expected_goals_conceded": "28.5", "defensive_contribution": 140},
        {"season_name": "2025/26", "minutes": 2251, "total_points": 85,
         "clean_sheets": 6, "goals_conceded": 37, "bps": 357, "starts": 27,
         "expected_goals": "2.2", "expected_assists": "1.9",
         "expected_goals_conceded": "35.0", "defensive_contribution": 210},
    ]}

    def test_keeps_every_season_in_feed_order(self):
        out = fpl_api.parse_history_past(self.ES)
        self.assertEqual([s["season_name"] for s in out], ["2024/25", "2025/26"])

    def test_scoring_columns_survive(self):
        last = fpl_api.parse_history_past(self.ES)[-1]
        self.assertEqual(last["minutes"], 2251)
        self.assertEqual(last["starts"], 27)
        self.assertEqual(last["clean_sheets"], 6)
        self.assertEqual(last["goals_conceded"], 37)
        self.assertEqual(last["bps"], 357)
        self.assertEqual(last["total_points"], 85)
        self.assertEqual(last["defensive_contribution"], 210)

    def test_string_typed_expected_goals_are_floats(self):
        """The feed sends these as strings; arithmetic downstream would break."""
        last = fpl_api.parse_history_past(self.ES)[-1]
        self.assertIsInstance(last["expected_goals"], float)
        self.assertAlmostEqual(last["expected_goals"], 2.2)
        self.assertAlmostEqual(last["expected_goals_conceded"], 35.0)
        self.assertAlmostEqual(last["expected_assists"], 1.9)

    def test_empty_history_is_an_empty_list(self):
        """A summer signing with no Premier League record — the cold-start case,
        which must return [] rather than raising or fabricating a season."""
        self.assertEqual(fpl_api.parse_history_past({"history_past": []}), [])
        self.assertEqual(fpl_api.parse_history_past({}), [])

    def test_missing_columns_do_not_raise(self):
        """Older seasons predate some of these fields."""
        out = fpl_api.parse_history_past(
            {"history_past": [{"season_name": "2016/17", "minutes": 900}]})
        self.assertEqual(out[0]["minutes"], 900)
        self.assertEqual(out[0]["clean_sheets"], 0)


class TestHistoryBackfillCache(unittest.TestCase):
    """The widened backfill: every player is fetched (not just those with
    bootstrap minutes), full history_past is stored, and cache entries written in
    the pre-history shape are re-fetched rather than served partial."""

    CACHE_NAME = "player_backfill_test"

    def _cache_path(self):
        return os.path.join(fpl_api.DATA_DIR, f"{self.CACHE_NAME}.json")

    def tearDown(self):
        path = self._cache_path()
        if os.path.exists(path):
            os.remove(path)

    def _seed_cache(self, payload):
        fpl_api.write_cache(self.CACHE_NAME, payload)

    @staticmethod
    def _players(id_minutes):
        return [{"id": i, "name": f"P{i}", "minutes": m} for i, m in id_minutes]

    @staticmethod
    def _summary(**overrides):
        row = {"season_name": "2025/26", "minutes": 2750, "starts": 30,
               "clean_sheets": 12, "goals_conceded": 30, "bps": 700,
               "total_points": 180, "expected_goals_conceded": "28.5",
               "defensive_contribution": 277}
        row.update(overrides)
        return {"history_past": [row]}

    def _run(self, players, fetch):
        return fpl_api.fetch_defcon_backfill(
            players, fetch=fetch, delay=0, sleep=lambda *_a: None,
            cache_name=self.CACHE_NAME)

    def test_zero_minute_players_are_now_fetched(self):
        """A player injured all last season has 0 bootstrap minutes but real prior
        history. The old DefCon-only fetch skipped him."""
        players = self._players([(3, 0), (4, 2000)])
        fetch_mock = mock.Mock(return_value=self._summary())

        result = self._run(players, fetch_mock)

        self.assertEqual([c.args[0] for c in fetch_mock.call_args_list], [3, 4])
        self.assertIn(3, result)

    def test_history_past_is_stored_alongside_the_defcon_fields(self):
        result = self._run(self._players([(1, 2000)]), mock.Mock(
            return_value=self._summary()))
        entry = result[1]
        self.assertAlmostEqual(entry["defcon_per90"], 277 * 90 / 2750, places=3)
        self.assertEqual(entry["minutes"], 2750)
        self.assertEqual(entry["history_past"][0]["clean_sheets"], 12)
        self.assertEqual(entry["history_past"][0]["starts"], 30)
        # string-typed in the feed, float on the way out
        self.assertAlmostEqual(
            entry["history_past"][0]["expected_goals_conceded"], 28.5)

    def test_no_premier_league_record_caches_an_empty_history(self):
        """A summer signing: [] is the honest answer and must be cached as such,
        not left missing (which would re-fetch him forever)."""
        result = self._run(self._players([(7, 0)]),
                           mock.Mock(return_value={"history_past": []}))
        self.assertEqual(result[7]["history_past"], [])

    def test_a_populated_cache_costs_no_calls(self):
        players = self._players([(1, 2000), (2, 0)])
        self._run(players, mock.Mock(return_value=self._summary()))

        fetch_mock2 = mock.Mock(return_value=self._summary())
        result = self._run(players, fetch_mock2)

        fetch_mock2.assert_not_called()
        self.assertEqual(sorted(result), [1, 2])
        self.assertEqual(result[1]["history_past"][0]["bps"], 700)

    def test_old_shape_cache_entries_are_refetched(self):
        """The pre-Task-4 file holds {"defcon_per90", "minutes"} only. Serving one
        of those would report "no history" for a player who has plenty."""
        self._seed_cache({"1": {"defcon_per90": 9.07, "minutes": 2750}})
        fetch_mock = mock.Mock(return_value=self._summary())

        result = self._run(self._players([(1, 2000)]), fetch_mock)

        fetch_mock.assert_called_once_with(1)
        self.assertEqual(result[1]["history_past"][0]["season_name"], "2025/26")

    def test_a_failed_fetch_leaves_the_player_absent_and_retryable(self):
        def flaky(pid):
            if pid == 10:
                raise RuntimeError("simulated network failure")
            return self._summary()

        result = self._run(self._players([(10, 2000), (11, 0)]),
                           mock.Mock(side_effect=flaky))
        self.assertNotIn(10, result)
        self.assertIn(11, result)
