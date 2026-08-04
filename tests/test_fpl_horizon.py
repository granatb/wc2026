"""Phase 6: multi-gameweek horizon aggregation."""
from __future__ import annotations

import unittest

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
