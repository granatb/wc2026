import unittest

from games.fpl import model


def _ev(**kw):
    base = {
        "team": "LIV", "position": "MID", "goals": 0.0, "assists": 0.0,
        "minutes": 90.0, "played": 1.0, "played_60": 1.0, "clean_sheet": 0.0,
        "conceded": 0.0, "yellow": 0.0, "red": 0.0, "saves": 0.0,
        "goal_share": 0.0, "assist_share": 0.0,
    }
    base.update(kw)
    return base


class TestAppearancePoints(unittest.TestCase):
    def test_full_match_pays_two(self):
        self.assertAlmostEqual(model.expected_points(_ev()), 2.0)

    def test_cameo_pays_one(self):
        self.assertAlmostEqual(
            model.expected_points(_ev(played=1.0, played_60=0.0)), 1.0)

    def test_unused_player_pays_nothing(self):
        self.assertAlmostEqual(
            model.expected_points(_ev(played=0.0, played_60=0.0)), 0.0)


class TestGoalPoints(unittest.TestCase):
    def test_goalkeeper_goal_is_worth_ten(self):
        pts = model.expected_points(_ev(position="GK", goals=1.0))
        self.assertAlmostEqual(pts, 2.0 + 10.0)

    def test_defender_goal_is_worth_six(self):
        self.assertAlmostEqual(
            model.expected_points(_ev(position="DEF", goals=1.0)), 2.0 + 6.0)

    def test_midfielder_goal_is_worth_five(self):
        self.assertAlmostEqual(
            model.expected_points(_ev(position="MID", goals=1.0)), 2.0 + 5.0)

    def test_forward_goal_is_worth_four(self):
        self.assertAlmostEqual(
            model.expected_points(_ev(position="FWD", goals=1.0)), 2.0 + 4.0)


class TestCleanSheetsAndAssists(unittest.TestCase):
    def test_assist_is_three(self):
        self.assertAlmostEqual(model.expected_points(_ev(assists=1.0)), 2.0 + 3.0)

    def test_defender_clean_sheet_is_four(self):
        self.assertAlmostEqual(
            model.expected_points(_ev(position="DEF", clean_sheet=1.0)), 2.0 + 4.0)

    def test_midfielder_clean_sheet_is_one(self):
        self.assertAlmostEqual(
            model.expected_points(_ev(position="MID", clean_sheet=1.0)), 2.0 + 1.0)

    def test_forward_gets_nothing_for_a_clean_sheet(self):
        self.assertAlmostEqual(
            model.expected_points(_ev(position="FWD", clean_sheet=1.0)), 2.0)


class TestCards(unittest.TestCase):
    def test_yellow_is_minus_one(self):
        self.assertAlmostEqual(model.expected_points(_ev(yellow=1.0)), 2.0 - 1.0)

    def test_red_is_minus_three(self):
        self.assertAlmostEqual(model.expected_points(_ev(red=1.0)), 2.0 - 3.0)


class TestConcededThreshold(unittest.TestCase):
    """-1 per TWO goals conceded, and the divisor must not be applied to a mean."""

    def test_two_conceded_costs_one_point(self):
        pts = model.conceded_points("DEF", conceded_samples=[2, 2, 2, 2])
        self.assertAlmostEqual(pts, -1.0)

    def test_one_conceded_costs_nothing(self):
        self.assertAlmostEqual(
            model.conceded_points("DEF", conceded_samples=[1, 1, 1, 1]), 0.0)

    def test_three_conceded_still_costs_only_one(self):
        self.assertAlmostEqual(
            model.conceded_points("DEF", conceded_samples=[3, 3]), -1.0)

    def test_threshold_is_not_the_same_as_dividing_the_mean(self):
        # mean of [1,3] is 2 -> naive floor(2/2) = -1. Correct is
        # (floor(1/2) + floor(3/2)) / 2 = (0 + 1)/2 = -0.5
        self.assertAlmostEqual(
            model.conceded_points("DEF", conceded_samples=[1, 3]), -0.5)

    def test_midfielders_and_forwards_are_exempt(self):
        self.assertAlmostEqual(
            model.conceded_points("MID", conceded_samples=[4, 4]), 0.0)
        self.assertAlmostEqual(
            model.conceded_points("FWD", conceded_samples=[4, 4]), 0.0)


class TestSavesThreshold(unittest.TestCase):
    """1 point per THREE saves, from per-sim counts."""

    def test_three_saves_is_one_point(self):
        self.assertAlmostEqual(model.saves_points([3, 3, 3]), 1.0)

    def test_two_saves_is_nothing(self):
        self.assertAlmostEqual(model.saves_points([2, 2]), 0.0)

    def test_six_saves_is_two_points(self):
        self.assertAlmostEqual(model.saves_points([6]), 2.0)

    def test_threshold_is_not_the_same_as_dividing_the_mean(self):
        # mean of [2,4] is 3 -> naive 1.0. Correct is (0 + 1)/2 = 0.5
        self.assertAlmostEqual(model.saves_points([2, 4]), 0.5)

    def test_no_samples_is_zero(self):
        self.assertAlmostEqual(model.saves_points([]), 0.0)


class TestDefconThreshold(unittest.TestCase):
    def test_defender_threshold_is_ten(self):
        self.assertEqual(model.defcon_threshold("DEF"), 10)

    def test_midfielder_and_forward_threshold_is_twelve(self):
        self.assertEqual(model.defcon_threshold("MID"), 12)
        self.assertEqual(model.defcon_threshold("FWD"), 12)

    def test_goalkeepers_are_not_eligible(self):
        self.assertIsNone(model.defcon_threshold("GK"))

    def test_always_crossing_pays_the_full_two(self):
        self.assertAlmostEqual(model.defcon_points("DEF", [10, 11, 12]), 2.0)

    def test_never_crossing_pays_nothing(self):
        self.assertAlmostEqual(model.defcon_points("DEF", [4, 5, 6]), 0.0)

    def test_half_the_time_pays_one(self):
        self.assertAlmostEqual(model.defcon_points("DEF", [4, 10]), 1.0)

    def test_payout_is_capped_at_two_however_high_the_count(self):
        self.assertAlmostEqual(model.defcon_points("DEF", [50, 50]), 2.0)

    def test_goalkeeper_scores_no_defcon(self):
        self.assertAlmostEqual(model.defcon_points("GK", [20, 20]), 0.0)
