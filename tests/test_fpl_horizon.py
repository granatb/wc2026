"""Phase 6: multi-gameweek horizon aggregation."""
from __future__ import annotations

import math
import unittest
from datetime import datetime, timezone

from core import fpl_horizon


class TestWindow(unittest.TestCase):
    def test_window_is_the_requested_length(self):
        self.assertEqual(fpl_horizon.window(1, 6), [1, 2, 3, 4, 5, 6])

    def test_window_clamps_at_the_end_of_the_season(self):
        """GW36 with a 6-week horizon has only three gameweeks left."""
        self.assertEqual(fpl_horizon.window(36, 6), [36, 37, 38])

    def test_window_never_runs_past_38(self):
        self.assertEqual(fpl_horizon.window(38, 6), [38])

    def test_length_of_one_is_just_this_gameweek(self):
        self.assertEqual(fpl_horizon.window(5, 1), [5])


def _matches():
    """ARS: GW1 home easy, GW2 away hard. COV: the mirror. GW1 priced, GW2 not."""
    return [
        {"fantasy_round": 1, "home": "ARS", "away": "COV",
         "p_cs_home": 0.40, "p_cs_away": 0.10,
         "exp_home_goals": 2.0, "exp_away_goals": 0.8,
         "home_difficulty": 2, "away_difficulty": 5, "market": True},
        {"fantasy_round": 2, "home": "COV", "away": "ARS",
         "p_cs_home": 0.12, "p_cs_away": 0.35,
         "exp_home_goals": 0.9, "exp_away_goals": 1.8,
         "home_difficulty": 5, "away_difficulty": 2, "market": False},
    ]


class TestClubHorizon(unittest.TestCase):
    def test_sums_clean_sheets_across_the_window_undecayed(self):
        out = fpl_horizon.club_horizon(_matches(), ["ARS", "COV"],
                                       window=[1, 2], decay=1.0)
        self.assertAlmostEqual(out["ARS"]["exp_clean_sheets"], 0.75)   # 0.40 + 0.35
        self.assertEqual(out["ARS"]["fixtures"], 2)

    def test_goals_for_and_against_follow_the_right_side(self):
        """ARS score 2.0 at home in GW1 and 1.8 away in GW2; they concede 0.8 then
        0.9. A swap here inverts every recommendation."""
        out = fpl_horizon.club_horizon(_matches(), ["ARS", "COV"],
                                       window=[1, 2], decay=1.0)
        self.assertAlmostEqual(out["ARS"]["exp_goals_for"], 3.8)
        self.assertAlmostEqual(out["ARS"]["exp_goals_against"], 1.7)

    def test_decay_discounts_later_gameweeks(self):
        out = fpl_horizon.club_horizon(_matches(), ["ARS", "COV"],
                                       window=[1, 2], decay=0.5)
        self.assertAlmostEqual(out["ARS"]["exp_clean_sheets"], 0.40 + 0.5 * 0.35)

    def test_zero_decay_reproduces_the_single_gameweek(self):
        """The calibration anchor: decay=0 must collapse to gameweek one exactly,
        so a horizon regression can be told apart from a ratings regression."""
        out = fpl_horizon.club_horizon(_matches(), ["ARS", "COV"],
                                       window=[1, 2], decay=0.0)
        self.assertAlmostEqual(out["ARS"]["exp_clean_sheets"], 0.40)
        self.assertAlmostEqual(out["ARS"]["exp_goals_for"], 2.0)

    def test_fixture_count_is_never_decayed(self):
        """Counts are facts about the calendar, not forecasts — a blank three weeks
        out is still a blank."""
        out = fpl_horizon.club_horizon(_matches(), ["ARS"], window=[1, 2], decay=0.5)
        self.assertEqual(out["ARS"]["fixtures"], 2)

    def test_a_blank_inside_the_window_shows_a_lower_fixture_count(self):
        out = fpl_horizon.club_horizon(_matches(), ["ARS", "COV", "EVE"],
                                       window=[1, 2], decay=1.0)
        self.assertEqual(out["EVE"]["fixtures"], 0)
        self.assertEqual(out["EVE"]["exp_clean_sheets"], 0.0)

    def test_a_double_inside_the_window_counts_both(self):
        ms = _matches() + [
            {"fantasy_round": 2, "home": "ARS", "away": "EVE",
             "p_cs_home": 0.30, "p_cs_away": 0.10,
             "exp_home_goals": 1.7, "exp_away_goals": 0.9,
             "home_difficulty": 2, "away_difficulty": 4, "market": False}]
        out = fpl_horizon.club_horizon(ms, ["ARS", "COV", "EVE"],
                                       window=[1, 2], decay=1.0)
        self.assertEqual(out["ARS"]["fixtures"], 3)

    def test_per_gameweek_detail_is_retained_for_the_grid(self):
        """The article renders a cell per gameweek, so the aggregate is not enough."""
        cells = fpl_horizon.club_horizon(_matches(), ["ARS"], window=[1, 2],
                                         decay=1.0)["ARS"]["by_gameweek"]
        self.assertEqual(cells[1][0]["opponent"], "COV")
        self.assertEqual(cells[1][0]["venue"], "H")
        self.assertEqual(cells[1][0]["difficulty"], 2)
        self.assertEqual(cells[2][0]["venue"], "A")

    def test_a_blank_gameweek_cell_is_an_empty_list(self):
        """Distinguishable from 'no data' — the grid renders it as a blank."""
        cells = fpl_horizon.club_horizon(_matches(), ["ARS", "EVE"], window=[1, 2],
                                         decay=1.0)["EVE"]["by_gameweek"]
        self.assertEqual(cells[1], [])
        self.assertEqual(cells[2], [])

    def test_mean_difficulty_across_the_window(self):
        out = fpl_horizon.club_horizon(_matches(), ["ARS"], window=[1, 2], decay=1.0)
        self.assertAlmostEqual(out["ARS"]["difficulty"], 2.0)   # 2 then 2

    def test_provenance_degrades_across_the_window(self):
        """Odds reach a week or two out; a six-week aggregate is mostly model-derived
        and must not inherit gameweek one's `market` label."""
        out = fpl_horizon.club_horizon(_matches(), ["ARS"], window=[1, 2], decay=1.0)
        self.assertEqual(out["ARS"]["basis"], "mixed")

    def test_all_priced_reads_as_market(self):
        ms = [dict(m, market=True) for m in _matches()]
        out = fpl_horizon.club_horizon(ms, ["ARS"], window=[1, 2], decay=1.0)
        self.assertEqual(out["ARS"]["basis"], "market")

    def test_matches_outside_the_window_are_ignored(self):
        ms = _matches() + [
            {"fantasy_round": 9, "home": "ARS", "away": "EVE",
             "p_cs_home": 0.99, "p_cs_away": 0.0, "exp_home_goals": 5.0,
             "exp_away_goals": 0.0, "home_difficulty": 1, "away_difficulty": 5,
             "market": False}]
        out = fpl_horizon.club_horizon(ms, ["ARS"], window=[1, 2], decay=1.0)
        self.assertEqual(out["ARS"]["fixtures"], 2)

    def test_does_not_mutate_the_input(self):
        ms = _matches()
        fpl_horizon.club_horizon(ms, ["ARS"], window=[1, 2], decay=1.0)
        self.assertEqual(ms, _matches())


class TestMatchProjection(unittest.TestCase):
    def test_clean_sheet_is_the_opponents_zero(self):
        """A team keeps a clean sheet iff the OPPONENT fails to score. Getting this
        backwards silently inverts every defensive recommendation."""
        p = fpl_horizon.match_projection(1.6, 1.1)
        self.assertAlmostEqual(p["p_cs_home"], math.exp(-1.1), places=6)
        self.assertAlmostEqual(p["p_cs_away"], math.exp(-1.6), places=6)

    def test_expected_goals_are_the_lambdas(self):
        p = fpl_horizon.match_projection(1.6, 1.1)
        self.assertAlmostEqual(p["exp_home_goals"], 1.6, places=6)
        self.assertAlmostEqual(p["exp_away_goals"], 1.1, places=6)

    def test_stronger_home_side_has_the_higher_clean_sheet(self):
        p = fpl_horizon.match_projection(2.2, 0.6)
        self.assertGreater(p["p_cs_home"], p["p_cs_away"])

    def test_zero_lambda_gives_a_certain_clean_sheet(self):
        p = fpl_horizon.match_projection(1.5, 0.0)
        self.assertAlmostEqual(p["p_cs_home"], 1.0, places=6)


def _register(rows: list):
    """Replace fixtures.SCHEDULE with `rows`; returns a restore callable.

    Same try/finally pattern as tests/test_fpl_model.py's synthetic gameweeks --
    SCHEDULE is module-global and shared with the World Cup track, so a test that
    leaks a fixture into it corrupts every later test in the process.
    """
    from core import fixtures

    saved = list(fixtures.SCHEDULE)
    fixtures.SCHEDULE.clear()
    fixtures.SCHEDULE.extend(rows)

    def restore():
        fixtures.SCHEDULE.clear()
        fixtures.SCHEDULE.extend(saved)

    return restore


def _fx(match_id, home, away, gw, *, lam_home=None, lam_away=None,
        stage=None, home_difficulty=None, away_difficulty=None, day=21):
    from core import fixtures

    return fixtures.Fixture(
        match_id=match_id, home=home, away=away,
        kickoff=datetime(2026, 8, day, 19, 0, tzinfo=timezone.utc),
        stage=fixtures.FPL_STAGE if stage is None else stage,
        fantasy_round=gw, neutral=False,
        lam_home=lam_home, lam_away=lam_away,
        home_difficulty=home_difficulty, away_difficulty=away_difficulty)


class TestProjectionAgreesWithTheSimulation(unittest.TestCase):
    """The analytic path and the simulated path must not drift.

    build_artifact simulates the current gameweek; the horizon projects the rest
    analytically. If the two disagree on the SAME fixture, the six-week view is
    telling a different story from the one-week view for no defensible reason.
    """

    def test_current_gameweek_agrees_within_tolerance(self):
        from core.ratings import PlayerPrior
        from games.fpl import model as fpl_model

        gameweek = 93
        squads = {
            "Home": [PlayerPrior(name="H-Def", team="Home", position="DEF",
                                 start_prob=1.0, exp_minutes=90, defcon_per90=9.0)],
            "Away": [PlayerPrior(name="A-Gk", team="Away", position="GK",
                                 start_prob=1.0, exp_minutes=90, saves_per90=3.5)],
        }
        players_by_name = {
            "H-Def": {"name": "H-Def", "price": 4.5, "ownership": 2.0,
                      "minutes": 2700, "bps": 500},
            "A-Gk": {"name": "A-Gk", "price": 5.0, "ownership": 5.0,
                     "minutes": 3420, "bps": 700},
        }
        restore = _register([_fx("agree-1", "Home", "Away", gameweek,
                                 lam_home=1.6, lam_away=1.1)])
        try:
            artifact, _hit = fpl_model.build_artifact(
                squads, players_by_name, gameweek, 4000, use_cache=False)
        finally:
            restore()

        simulated = artifact["matches"][0]
        projected = fpl_horizon.match_projection(1.6, 1.1)
        for key in ("p_cs_home", "p_cs_away", "exp_home_goals", "exp_away_goals"):
            self.assertAlmostEqual(
                simulated[key], projected[key], delta=0.03,
                msg=f"{key}: simulated {simulated[key]} vs projected "
                    f"{projected[key]} — the one-week and six-week views disagree")


class TestHorizonMatches(unittest.TestCase):
    def _schedule(self):
        """Three gameweeks. GW1 priced with FDR, GW2/GW3 unpriced model lambdas."""
        return [
            _fx("h-1", "Home", "Away", 1, lam_home=1.6, lam_away=1.1,
                home_difficulty=2, away_difficulty=5, day=21),
            _fx("h-2", "Away", "Home", 2, home_difficulty=4, away_difficulty=3,
                day=28),
            _fx("h-3", "Home", "Third", 3, home_difficulty=2, away_difficulty=4,
                day=31),
        ]

    def test_projects_every_fixture_in_the_window(self):
        restore = _register(self._schedule())
        try:
            out = fpl_horizon.horizon_matches(gameweek=1, length=3)
        finally:
            restore()

        self.assertEqual(len(out), 3)
        self.assertEqual([m["fantasy_round"] for m in out], [1, 2, 3])
        for m in out:
            for key in ("fantasy_round", "home", "away", "p_cs_home", "p_cs_away",
                        "exp_home_goals", "exp_away_goals", "home_difficulty",
                        "away_difficulty", "market"):
                self.assertIn(key, m, f"{key} missing from a horizon match dict")

        first = out[0]
        self.assertEqual((first["home"], first["away"]), ("Home", "Away"))
        self.assertAlmostEqual(first["p_cs_home"], math.exp(-1.1), places=6)
        self.assertAlmostEqual(first["exp_home_goals"], 1.6, places=6)
        self.assertEqual(first["home_difficulty"], 2)
        self.assertEqual(first["away_difficulty"], 5)

    def test_the_window_bounds_what_is_projected(self):
        """length=2 must stop at GW2 — the third fixture is outside the window."""
        restore = _register(self._schedule())
        try:
            out = fpl_horizon.horizon_matches(gameweek=1, length=2)
        finally:
            restore()
        self.assertEqual([m["fantasy_round"] for m in out], [1, 2])

    def test_unpriced_fixtures_still_get_club_differentiated_lambdas(self):
        """Phase 5's ratings are what make a six-week view possible: a fixture with
        no odds must still project something other than a league-average draw."""
        from core import ratings

        restore = _register(self._schedule())
        saved_ratings = dict(ratings.TEAM_RATINGS)
        ratings.TEAM_RATINGS["Home"] = ratings.TeamRating(
            name="Home", attack=1.4, defence=0.6)
        ratings.TEAM_RATINGS["Away"] = ratings.TeamRating(
            name="Away", attack=0.6, defence=1.4)
        try:
            out = fpl_horizon.horizon_matches(gameweek=2, length=1)
        finally:
            ratings.TEAM_RATINGS.clear()
            ratings.TEAM_RATINGS.update(saved_ratings)
            restore()
        self.assertFalse(out[0]["market"])
        # GW2 is Away (weak) at home to Home (strong): the visitors are the side
        # more likely to keep it clean.
        self.assertGreater(out[0]["p_cs_away"], out[0]["p_cs_home"])

    def test_market_flag_tracks_priced_fixtures(self):
        restore = _register(self._schedule())
        try:
            out = fpl_horizon.horizon_matches(gameweek=1, length=3)
        finally:
            restore()
        by_round = {m["fantasy_round"]: m for m in out}
        self.assertTrue(by_round[1]["market"], "an odds-priced fixture reads as model")
        self.assertFalse(by_round[2]["market"], "a ratings fallback reads as market")
        self.assertFalse(by_round[3]["market"])

    def test_only_fpl_fixtures_are_included(self):
        """The schedule is shared with the World Cup and buckets on fantasy_round
        alone, so a World Cup tie in the same numbered round must not appear."""
        restore = _register(self._schedule() + [
            _fx("wc-1", "Mexico", "South Africa", 2, lam_home=1.9, lam_away=0.7,
                stage="STATUS_FULL_TIME")])
        try:
            out = fpl_horizon.horizon_matches(gameweek=1, length=3)
        finally:
            restore()
        self.assertEqual(len(out), 3)
        teams = {t for m in out for t in (m["home"], m["away"])}
        self.assertNotIn("Mexico", teams)
        self.assertNotIn("South Africa", teams)

    def test_defaults_to_the_configured_window_length(self):
        import config

        restore = _register(self._schedule())
        try:
            out = fpl_horizon.horizon_matches(gameweek=1)
        finally:
            restore()
        # The configured window is 6 gameweeks; only three carry fixtures here.
        self.assertGreaterEqual(config.FPL_HORIZON_LENGTH, 3)
        self.assertEqual(len(out), 3)

    def test_output_feeds_club_horizon_directly(self):
        """The contract that matters: horizon_matches' dicts are exactly what
        club_horizon consumes, with no adapter in between."""
        restore = _register(self._schedule())
        try:
            ms = fpl_horizon.horizon_matches(gameweek=1, length=3)
        finally:
            restore()
        out = fpl_horizon.club_horizon(ms, ["Home", "Away", "Third"],
                                       window=[1, 2, 3], decay=1.0)
        self.assertEqual(out["Home"]["fixtures"], 3)
        self.assertEqual(out["Third"]["fixtures"], 1)
        self.assertEqual(out["Home"]["basis"], "mixed")
        self.assertGreater(out["Home"]["exp_clean_sheets"], 0.0)


class TestHorizonInTheArtifact(unittest.TestCase):
    """build_artifact carries the horizon, and carries it identically whether the
    sim ran or the cache served it."""

    GAMEWEEK = 30      # inside the season, so window() is non-empty

    def _build(self, use_cache):
        from core.ratings import PlayerPrior
        from games.fpl import model as fpl_model

        squads = {
            "Home": [PlayerPrior(name="H-Def", team="Home", position="DEF",
                                 start_prob=1.0, exp_minutes=90, defcon_per90=9.0)],
            "Away": [PlayerPrior(name="A-Gk", team="Away", position="GK",
                                 start_prob=1.0, exp_minutes=90, saves_per90=3.5)],
            # In the league, never in the window's fixtures -- the blank row.
            "Third": [PlayerPrior(name="T-Mid", team="Third", position="MID",
                                  start_prob=1.0, exp_minutes=90, goal_share=0.3)],
        }
        players_by_name = {
            "H-Def": {"name": "H-Def", "price": 4.5, "ownership": 2.0,
                      "minutes": 2700, "bps": 500},
            "A-Gk": {"name": "A-Gk", "price": 5.0, "ownership": 5.0,
                     "minutes": 3420, "bps": 700},
            "T-Mid": {"name": "T-Mid", "price": 6.0, "ownership": 3.0,
                      "minutes": 2700, "bps": 400},
        }
        gw = self.GAMEWEEK
        restore = _register([
            _fx("art-1", "Home", "Away", gw, lam_home=1.6, lam_away=1.1,
                home_difficulty=2, away_difficulty=5, day=21),
            _fx("art-2", "Away", "Home", gw + 1, home_difficulty=4,
                away_difficulty=3, day=28),
        ])
        try:
            return fpl_model.build_artifact(squads, players_by_name, gw, 300,
                                            use_cache=use_cache)
        finally:
            restore()

    def test_artifact_carries_a_club_horizon(self):
        artifact, _hit = self._build(use_cache=False)
        horizon = artifact["horizon"]
        self.assertEqual(set(horizon), {"Home", "Away", "Third"})
        self.assertEqual(horizon["Home"]["fixtures"], 2)
        self.assertEqual(horizon["Third"]["fixtures"], 0,
                         "a club blank for the whole window must still get a row")
        self.assertGreater(horizon["Home"]["exp_clean_sheets"], 0.0)

    def test_by_gameweek_keys_survive_the_cache_as_ints(self):
        """json.dump stringifies dict keys, so a cache HIT would otherwise hand the
        grid string gameweeks where a fresh build hands it ints."""
        import shutil
        import tempfile
        from unittest import mock

        from core import simcache

        tmp = tempfile.mkdtemp(prefix="fpl_horizon_cache_")
        patcher = mock.patch.object(simcache, "CACHE_DIR", tmp)
        patcher.start()
        try:
            fresh, hit_fresh = self._build(use_cache=True)
            served, hit_served = self._build(use_cache=True)
        finally:
            patcher.stop()
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertFalse(hit_fresh)
        self.assertTrue(hit_served)
        self.assertEqual(fresh["horizon"], served["horizon"])
        self.assertIn(self.GAMEWEEK, served["horizon"]["Home"]["by_gameweek"])

    def test_a_pre_phase6_artifact_degrades_instead_of_crashing(self):
        """A hand-copied artifact with no `horizon` key must not take a build down."""
        from games.fpl import model as fpl_model

        self.assertEqual(fpl_model._rehydrate_horizon({}), {})
        self.assertEqual(fpl_model._rehydrate_horizon(None), {})

    def test_the_window_length_is_in_the_cache_key(self):
        """Changing FPL_HORIZON_LENGTH must invalidate: otherwise flipping 6 to 8
        silently serves a six-week horizon under an eight-week heading."""
        import shutil
        import tempfile
        from unittest import mock

        import config
        from core import simcache

        tmp = tempfile.mkdtemp(prefix="fpl_horizon_key_")
        patcher = mock.patch.object(simcache, "CACHE_DIR", tmp)
        patcher.start()
        try:
            _first, hit_first = self._build(use_cache=True)
            with mock.patch.object(config, "FPL_HORIZON_LENGTH",
                                   config.FPL_HORIZON_LENGTH + 2):
                _second, hit_second = self._build(use_cache=True)
            _third, hit_third = self._build(use_cache=True)
        finally:
            patcher.stop()
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertFalse(hit_first)
        self.assertFalse(hit_second, "the window length is not in the cache key")
        self.assertTrue(hit_third, "the original key stopped matching")

    def test_the_decay_dial_is_in_the_cache_key(self):
        import shutil
        import tempfile
        from unittest import mock

        import config
        from core import simcache

        tmp = tempfile.mkdtemp(prefix="fpl_decay_key_")
        patcher = mock.patch.object(simcache, "CACHE_DIR", tmp)
        patcher.start()
        try:
            _first, hit_first = self._build(use_cache=True)
            with mock.patch.object(config, "FPL_HORIZON_DECAY", 0.5):
                _second, hit_second = self._build(use_cache=True)
        finally:
            patcher.stop()
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertFalse(hit_first)
        self.assertFalse(hit_second, "the decay dial is not in the cache key")

    def test_a_future_fixture_getting_priced_invalidates_the_artifact(self):
        """The horizon reads FUTURE gameweeks' lambdas, which are not in the sim's
        own fixture list. If they are missing from the key, a GW+1 fixture being
        priced leaves the six-week grid stale while the artifact claims currency."""
        import shutil
        import tempfile
        from unittest import mock

        from core.ratings import PlayerPrior
        from core import simcache
        from games.fpl import model as fpl_model

        squads = {
            "Home": [PlayerPrior(name="H-Def", team="Home", position="DEF",
                                 start_prob=1.0, exp_minutes=90, defcon_per90=9.0)],
            "Away": [PlayerPrior(name="A-Gk", team="Away", position="GK",
                                 start_prob=1.0, exp_minutes=90, saves_per90=3.5)],
        }
        players_by_name = {
            "H-Def": {"name": "H-Def", "price": 4.5, "ownership": 2.0,
                      "minutes": 2700, "bps": 500},
            "A-Gk": {"name": "A-Gk", "price": 5.0, "ownership": 5.0,
                     "minutes": 3420, "bps": 700},
        }
        gw = self.GAMEWEEK

        def build(next_week_priced):
            restore = _register([
                _fx("prc-1", "Home", "Away", gw, lam_home=1.6, lam_away=1.1, day=21),
                _fx("prc-2", "Away", "Home", gw + 1, day=28,
                    lam_home=2.4 if next_week_priced else None,
                    lam_away=0.5 if next_week_priced else None),
            ])
            try:
                return fpl_model.build_artifact(squads, players_by_name, gw, 300,
                                                use_cache=True)
            finally:
                restore()

        tmp = tempfile.mkdtemp(prefix="fpl_future_price_")
        patcher = mock.patch.object(simcache, "CACHE_DIR", tmp)
        patcher.start()
        try:
            unpriced, hit_unpriced = build(False)
            priced, hit_priced = build(True)
        finally:
            patcher.stop()
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertFalse(hit_unpriced)
        self.assertFalse(hit_priced,
                         "a future fixture getting priced did not invalidate the key")
        self.assertNotEqual(unpriced["horizon"]["Home"]["exp_clean_sheets"],
                            priced["horizon"]["Home"]["exp_clean_sheets"])
