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


class TestBpsFromEvents(unittest.TestCase):
    """Event-driven BPS deltas, from the official BPS table in games/fpl/rules.md."""

    def _row(self, **kw):
        base = {"name": "P", "position": "MID", "goals": 0, "assists": 0,
                "minutes": 90, "clean_sheet": False, "conceded": 0, "saves": 0,
                "yellow": 0, "red": 0}
        base.update(kw)
        return (base["name"], base["position"], base["goals"], base["assists"],
                base["minutes"], base["clean_sheet"], base["conceded"],
                base["saves"], base["yellow"], base["red"])

    def test_over_sixty_minutes_is_six_bps(self):
        self.assertEqual(model.bps_from_row(self._row(), baseline=0.0), 6)

    def test_under_sixty_minutes_is_three_bps(self):
        self.assertEqual(model.bps_from_row(self._row(minutes=45), baseline=0.0), 3)

    def test_forward_goal_is_twenty_four_bps(self):
        got = model.bps_from_row(self._row(position="FWD", goals=1), baseline=0.0)
        self.assertEqual(got, 6 + 24)

    def test_midfielder_goal_is_eighteen_bps(self):
        got = model.bps_from_row(self._row(position="MID", goals=1), baseline=0.0)
        self.assertEqual(got, 6 + 18)

    def test_defender_goal_is_twelve_bps(self):
        got = model.bps_from_row(self._row(position="DEF", goals=1), baseline=0.0)
        self.assertEqual(got, 6 + 12)

    def test_assist_is_nine_bps(self):
        self.assertEqual(model.bps_from_row(self._row(assists=1), baseline=0.0), 6 + 9)

    def test_defender_clean_sheet_is_twelve_bps(self):
        got = model.bps_from_row(
            self._row(position="DEF", clean_sheet=True), baseline=0.0)
        self.assertEqual(got, 6 + 12)

    def test_midfielder_clean_sheet_earns_no_bps(self):
        got = model.bps_from_row(
            self._row(position="MID", clean_sheet=True), baseline=0.0)
        self.assertEqual(got, 6)

    def test_each_save_is_two_bps(self):
        got = model.bps_from_row(self._row(position="GK", saves=4), baseline=0.0)
        self.assertEqual(got, 6 + 8)

    def test_conceding_costs_a_defender_four_bps_each(self):
        got = model.bps_from_row(
            self._row(position="DEF", conceded=2), baseline=0.0)
        self.assertEqual(got, 6 - 8)

    def test_cards_cost_three_and_nine_bps(self):
        self.assertEqual(model.bps_from_row(self._row(yellow=1), baseline=0.0), 6 - 3)
        self.assertEqual(model.bps_from_row(self._row(red=1), baseline=0.0), 6 - 9)

    def test_baseline_rate_is_prorated_by_minutes(self):
        # baseline 18 BPS per 90 over 45 minutes contributes 9
        self.assertEqual(model.bps_from_row(self._row(minutes=45), baseline=18.0),
                         3 + 9)


class TestBonusAccumulator(unittest.TestCase):
    def _rows(self, scores):
        """Build rows whose BPS ordering is controlled by goal counts."""
        return [(name, "FWD", goals, 0, 90, False, 0, 0, 0, 0)
                for name, goals in scores]

    def test_top_three_take_three_two_one(self):
        acc = model.BonusAccumulator(baselines={})
        acc.observe("m1", self._rows([("A", 3), ("B", 2), ("C", 1), ("D", 0)]))
        self.assertAlmostEqual(acc.expected("A"), 3.0)
        self.assertAlmostEqual(acc.expected("B"), 2.0)
        self.assertAlmostEqual(acc.expected("C"), 1.0)
        self.assertAlmostEqual(acc.expected("D"), 0.0)

    def test_expected_bonus_averages_across_sims(self):
        acc = model.BonusAccumulator(baselines={})
        acc.observe("m1", self._rows([("A", 3), ("B", 0)]))
        acc.observe("m1", self._rows([("A", 0), ("B", 3)]))
        # A tops one sim (3) and is second in the other (2) -> 2.5
        self.assertAlmostEqual(acc.expected("A"), 2.5)
        self.assertAlmostEqual(acc.expected("B"), 2.5)

    def test_tie_for_first_gives_both_three_and_the_next_player_one(self):
        # Official rule: two tied on top both get 3, and the THIRD-most BPS gets 1
        # (not 2 — the tie consumes two award positions).
        acc = model.BonusAccumulator(baselines={})
        acc.observe("m1", self._rows([("A", 2), ("B", 2), ("C", 0)]))
        self.assertAlmostEqual(acc.expected("A"), 3.0)
        self.assertAlmostEqual(acc.expected("B"), 3.0)
        self.assertAlmostEqual(acc.expected("C"), 1.0)

    def test_tie_for_second_gives_both_two_and_awards_no_one(self):
        acc = model.BonusAccumulator(baselines={})
        acc.observe("m1", self._rows([("A", 3), ("B", 1), ("C", 1), ("D", 0)]))
        self.assertAlmostEqual(acc.expected("A"), 3.0)
        self.assertAlmostEqual(acc.expected("B"), 2.0)
        self.assertAlmostEqual(acc.expected("C"), 2.0)
        self.assertAlmostEqual(acc.expected("D"), 0.0)

    def test_unknown_player_has_no_expected_bonus(self):
        acc = model.BonusAccumulator(baselines={})
        acc.observe("m1", self._rows([("A", 1)]))
        self.assertAlmostEqual(acc.expected("nobody"), 0.0)

    def test_baselines_break_ties_between_equal_event_lines(self):
        # identical events, but B has the higher season BPS rate
        acc = model.BonusAccumulator(baselines={"A": 10.0, "B": 30.0})
        acc.observe("m1", self._rows([("A", 1), ("B", 1), ("C", 0)]))
        self.assertGreater(acc.expected("B"), acc.expected("A"))


from core import engine_events


class TestTotalPoints(unittest.TestCase):
    def _sample(self, **kw):
        ps = engine_events.PlayerSample("K", "LIV", kw.pop("position", "GK"))
        ps.sims = 2
        ps.played = 2.0
        ps.played_60 = 2.0
        for key, value in kw.items():
            setattr(ps, key, value)
        return ps

    def test_total_sums_direct_and_threshold_components(self):
        ps = self._sample(position="GK", save_samples=[3, 3], conceded=0.0)
        means = {"position": "GK", "played": 1.0, "played_60": 1.0,
                 "goals": 0.0, "assists": 0.0, "clean_sheet": 1.0,
                 "yellow": 0.0, "red": 0.0}
        pts = model.total_points(means, ps, conceded_samples=[0, 0], bonus=0.0)
        # appearance 2 + clean sheet 4 + one saves point
        self.assertAlmostEqual(pts, 2.0 + 4.0 + 1.0)

    def test_bonus_is_added_verbatim(self):
        ps = self._sample(position="MID", save_samples=[])
        means = {"position": "MID", "played": 1.0, "played_60": 1.0,
                 "goals": 0.0, "assists": 0.0, "clean_sheet": 0.0,
                 "yellow": 0.0, "red": 0.0}
        pts = model.total_points(means, ps, conceded_samples=[], bonus=1.4)
        self.assertAlmostEqual(pts, 2.0 + 1.4)

    def test_defcon_included_when_samples_present(self):
        ps = self._sample(position="DEF", save_samples=[], defcon_samples=[10, 10])
        means = {"position": "DEF", "played": 1.0, "played_60": 1.0,
                 "goals": 0.0, "assists": 0.0, "clean_sheet": 0.0,
                 "yellow": 0.0, "red": 0.0}
        pts = model.total_points(means, ps, conceded_samples=[0, 0], bonus=0.0)
        self.assertAlmostEqual(pts, 2.0 + 2.0)


class TestCeiling(unittest.TestCase):
    def test_ceiling_is_never_below_the_mean(self):
        means = {"position": "DEF", "played": 1.0, "played_60": 1.0,
                 "goals": 0.0, "assists": 0.0, "clean_sheet": 0.9,
                 "yellow": 0.0, "red": 0.0}
        mean_pts = model.expected_points(means)
        ceiling = model.ceiling_points(means, goal_samples=[0, 0, 0, 0])
        self.assertGreaterEqual(ceiling, mean_pts)

    def test_ceiling_lifts_a_scorer_above_his_mean(self):
        means = {"position": "FWD", "played": 1.0, "played_60": 1.0,
                 "goals": 0.5, "assists": 0.0, "clean_sheet": 0.0,
                 "yellow": 0.0, "red": 0.0}
        ceiling = model.ceiling_points(means, goal_samples=[0, 0, 1, 2])
        self.assertGreater(ceiling, model.expected_points(means))
