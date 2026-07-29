import unittest
from datetime import datetime, timezone
from unittest import mock

from core import engine_events, fixtures, ratings
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
    """The ceiling column must be comparable to total_points (xPts): it has to
    include the SAME non-goal components (saves, conceded, DefCon, bonus), or a
    ceiling can silently print below its own expected value. Regression observed
    live: Szoboszlai 3.76 xPts / 3.21 ceil, Verbruggen 3.59 / 2.92, Rice 3.57 /
    2.73, Pickford 3.46 / 2.88 -- all ceil < xPts.
    """

    def _sample(self, **kw):
        ps = engine_events.PlayerSample("K", "LIV", kw.pop("position", "GK"))
        ps.sims = 2
        ps.played = 2.0
        ps.played_60 = 2.0
        for key, value in kw.items():
            setattr(ps, key, value)
        return ps

    def test_ceiling_at_least_matches_total_for_a_keeper_with_no_goal_threat(self):
        # The exact failing shape: saves + bonus dominate, goals are irrelevant,
        # so the old goal-only ceiling floored at expected_points() (which drops
        # saves/conceded/DefCon/bonus) and printed below the real total.
        means = {"position": "GK", "played": 1.0, "played_60": 1.0,
                 "goals": 0.0, "assists": 0.0, "clean_sheet": 0.6,
                 "yellow": 0.0, "red": 0.0}
        sample = self._sample(position="GK", goal_samples=[0, 0, 0, 0],
                              save_samples=[3, 3, 3, 3])
        conceded_samples = [0, 0]
        bonus = 1.4

        total = model.total_points(means, sample, conceded_samples, bonus=bonus)
        ceiling = model.ceiling_points(means, sample, conceded_samples, bonus=bonus)
        self.assertGreaterEqual(ceiling, total)

    def test_ceiling_at_least_matches_total_for_a_creative_midfielder(self):
        # High bonus and DefCon, low goal threat.
        means = {"position": "MID", "played": 1.0, "played_60": 1.0,
                 "goals": 0.05, "assists": 0.3, "clean_sheet": 0.3,
                 "yellow": 0.0, "red": 0.0}
        sample = self._sample(position="MID", goal_samples=[0, 0, 0, 1],
                              defcon_samples=[13, 13])
        conceded_samples = []
        bonus = 1.8

        total = model.total_points(means, sample, conceded_samples, bonus=bonus)
        ceiling = model.ceiling_points(means, sample, conceded_samples, bonus=bonus)
        self.assertGreaterEqual(ceiling, total)

    def test_ceiling_is_strictly_above_total_for_a_striker_with_goal_variance(self):
        # The fix must not turn the ceiling into a no-op that just returns total.
        means = {"position": "FWD", "played": 1.0, "played_60": 1.0,
                 "goals": 0.4, "assists": 0.0, "clean_sheet": 0.0,
                 "yellow": 0.0, "red": 0.0}
        sample = self._sample(position="FWD", goal_samples=[0, 0, 1, 2, 3])
        conceded_samples: list = []
        bonus = 0.0

        total = model.total_points(means, sample, conceded_samples, bonus=bonus)
        ceiling = model.ceiling_points(means, sample, conceded_samples, bonus=bonus)
        self.assertGreater(ceiling, total)

    def test_defcon_and_bonus_both_move_the_ceiling(self):
        # Same (zero) goal variance in both scenarios, so the entire delta must
        # come from DefCon and bonus -- proof those components are IN the ceiling,
        # not just floored against.
        means = {"position": "DEF", "played": 1.0, "played_60": 1.0,
                 "goals": 0.0, "assists": 0.0, "clean_sheet": 0.4,
                 "yellow": 0.0, "red": 0.0}
        conceded_samples = [0, 0]

        low_sample = self._sample(position="DEF", goal_samples=[0, 0, 0, 0],
                                  defcon_samples=[4, 4])
        high_sample = self._sample(position="DEF", goal_samples=[0, 0, 0, 0],
                                   defcon_samples=[10, 10])

        low = model.ceiling_points(means, low_sample, conceded_samples, bonus=0.5)
        high = model.ceiling_points(means, high_sample, conceded_samples, bonus=2.5)

        # defcon_points("DEF", [4,4]) == 0.0, defcon_points("DEF", [10,10]) == 2.0
        # bonus delta is 2.0 -> total delta must be exactly 4.0
        self.assertAlmostEqual(high - low, 4.0)


# ---------------------------------------------------------------------------
# Appearance-probability scaling (denominator-mismatch regression).
#
# saves_points, conceded_points, defcon_points and BonusAccumulator.expected all
# divide by counts that only grow when a player is ON THE PITCH (len(save_samples),
# len(defcon_samples), sample.played, self._sims[name]) -- i.e. they are
# E[component | played]. expected_points(means), by contrast, divides by
# ps.sims -- the total sim count, incremented for every player on every sim
# BEFORE the on-pitch guard -- so it is E[component] unconditionally. Adding a
# conditional expectation to an unconditional one overpays (or, for the negative
# conceded penalty, over-penalises) any player who does not start every single
# sim.
#
# Every fixture above uses played_60=played=sims (start_prob=1.0), which makes
# P(played) == 1 and hides the bug completely. These tests deliberately vary
# start_prob and use a REAL simulate_round run rather than hand-built
# PlayerSample objects, because hand-built fixtures are exactly what let the
# original bug hide from the whole existing suite.
# ---------------------------------------------------------------------------


class _RealSimMixin:
    """Builds real simulate_round output with varied start probabilities."""

    SIMS = 20000

    def _register(self, fx):
        fixtures.SCHEDULE.append(fx)
        self.addCleanup(lambda: fixtures.SCHEDULE.remove(fx))

    def _shared_match_squads(self, fantasy_round, position, rate_kw):
        """Nailed/Rotator/Fringe (start_prob 1.0/0.5/0.2) share ONE team and
        match, exactly like the reviewer's three-defender proof."""
        fx = fixtures.Fixture(
            f"SHARE{fantasy_round}", "Home", "Away",
            kickoff=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc),
            stage="GW", fantasy_round=fantasy_round, neutral=False,
            lam_home=1.4, lam_away=1.1,
        )
        self._register(fx)
        squads = {
            "Home": [
                ratings.PlayerPrior("Nailed", "Home", position, start_prob=1.0,
                                    exp_minutes=90, **rate_kw),
                ratings.PlayerPrior("Rotator", "Home", position, start_prob=0.5,
                                    exp_minutes=90, **rate_kw),
                ratings.PlayerPrior("Fringe", "Home", position, start_prob=0.2,
                                    exp_minutes=90, **rate_kw),
            ],
            "Away": [
                ratings.PlayerPrior("Filler", "Away", "FWD", start_prob=1.0,
                                    exp_minutes=90, goal_share=0.3),
            ],
        }
        return engine_events.simulate_round(
            fantasy_round, sims=self.SIMS, priors=lambda t: squads.get(t, []))

    def _independent_matches_squads(self, fantasy_round, position, rate_kw,
                                    per_match_hook=None):
        """Nailed/Rotator/Fringe each get their OWN match against an identical
        filler opponent, for quantities (saves, bonus) that need one occupant
        per team/rank rather than three team-mates competing for one slot."""
        squads = {}
        for i, (name, sp) in enumerate(
                [("Nailed", 1.0), ("Rotator", 0.5), ("Fringe", 0.2)]):
            home, away = f"H{fantasy_round}_{i}", f"A{fantasy_round}_{i}"
            fx = fixtures.Fixture(
                f"INDEP{fantasy_round}_{i}", home, away,
                kickoff=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc),
                stage="GW", fantasy_round=fantasy_round, neutral=False,
                lam_home=1.4, lam_away=1.1,
            )
            self._register(fx)
            squads[home] = [ratings.PlayerPrior(name, home, position,
                                                start_prob=sp, exp_minutes=90,
                                                **rate_kw)]
            squads[away] = [ratings.PlayerPrior(f"Filler{i}", away, "MID",
                                                start_prob=1.0, exp_minutes=90)]
        return engine_events.simulate_round(
            fantasy_round, sims=self.SIMS, priors=lambda t: squads.get(t, []),
            per_match_hook=per_match_hook)

    def _p_play(self, players, names):
        return {n: players[n].played / players[n].sims for n in names}

    def _assert_scales_with_appearance(self, deltas, p_play, tol=0.05):
        for name in ("Rotator", "Fringe"):
            expected_ratio = p_play[name] / p_play["Nailed"]
            actual_ratio = deltas[name] / deltas["Nailed"]
            self.assertAlmostEqual(
                actual_ratio, expected_ratio, delta=tol,
                msg=f"{name}: expected ratio ~{expected_ratio:.3f} "
                    f"(P(play) proportional), got {actual_ratio:.3f}")
        # The flat-conditional bug: a fringe player (P(play) ~= 0.2) landing at
        # ~same magnitude as a nailed starter, rather than ~20% of it.
        self.assertLess(abs(deltas["Fringe"]), abs(deltas["Nailed"]) * 0.35)


class TestDefconAppearanceScaling(_RealSimMixin, unittest.TestCase):
    def test_defcon_points_scale_with_appearance_probability(self):
        players, _ = self._shared_match_squads(970, "DEF", {"defcon_per90": 8.0})
        means = engine_events.event_means(players)
        deltas = {}
        for name in ("Nailed", "Rotator", "Fringe"):
            m = means[name]
            total = model.total_points(m, players[name], conceded_samples=[],
                                       bonus=0.0)
            # conceded_samples=[] and no save_samples/bonus on a DEF player
            # isolate the DefCon contribution exactly.
            deltas[name] = total - model.expected_points(m)

        p_play = self._p_play(players, deltas)
        self._assert_scales_with_appearance(deltas, p_play)


class TestSavesAppearanceScaling(_RealSimMixin, unittest.TestCase):
    def test_saves_points_scale_with_appearance_probability(self):
        players, _ = self._independent_matches_squads(
            971, "GK", {"saves_per90": 3.0})
        means = engine_events.event_means(players)
        deltas = {}
        for name in ("Nailed", "Rotator", "Fringe"):
            m = means[name]
            total = model.total_points(m, players[name], conceded_samples=[],
                                       bonus=0.0)
            # conceded_samples=[] isolates saves (GK has no DefCon eligibility
            # and bonus is 0 here).
            deltas[name] = total - model.expected_points(m)

        p_play = self._p_play(players, deltas)
        self._assert_scales_with_appearance(deltas, p_play)


class TestBonusAppearanceScaling(_RealSimMixin, unittest.TestCase):
    def test_bonus_scales_with_appearance_probability(self):
        acc = model.BonusAccumulator(baselines={})
        players, _ = self._independent_matches_squads(
            972, "FWD", {"goal_share": 0.4}, per_match_hook=acc.observe)
        means = engine_events.event_means(players)
        deltas = {}
        for name in ("Nailed", "Rotator", "Fringe"):
            m = means[name]
            b = acc.expected(name)
            total = model.total_points(m, players[name], conceded_samples=[],
                                       bonus=b)
            # conceded_samples=[] and a FWD with no DefCon rate isolate bonus.
            deltas[name] = total - model.expected_points(m)

        p_play = self._p_play(players, deltas)
        self._assert_scales_with_appearance(deltas, p_play)


class TestConcededAppearanceScaling(_RealSimMixin, unittest.TestCase):
    def test_conceded_penalty_scales_with_appearance_and_stays_negative(self):
        players, _ = self._shared_match_squads(973, "DEF", {})
        means = engine_events.event_means(players)
        deltas = {}
        for name in ("Nailed", "Rotator", "Fringe"):
            m = means[name]
            ps = players[name]
            conceded_samples = model._conceded_series(ps)
            total = model.total_points(m, ps, conceded_samples, bonus=0.0)
            deltas[name] = total - model.expected_points(m)
            self.assertLess(deltas[name], 0.0, f"{name}: penalty must stay negative")

        p_play = self._p_play(players, deltas)
        self._assert_scales_with_appearance(deltas, p_play)


class TestCeilingAppearanceScaling(_RealSimMixin, unittest.TestCase):
    def test_ceiling_not_inflated_for_a_rotation_player(self):
        players, _ = self._shared_match_squads(974, "DEF", {"defcon_per90": 8.0})
        means = engine_events.event_means(players)
        nailed, fringe = players["Nailed"], players["Fringe"]
        cs_nailed = model._conceded_series(nailed)
        cs_fringe = model._conceded_series(fringe)

        total_nailed = model.total_points(means["Nailed"], nailed, cs_nailed, bonus=0.0)
        total_fringe = model.total_points(means["Fringe"], fringe, cs_fringe, bonus=0.0)
        ceiling_nailed = model.ceiling_points(means["Nailed"], nailed, cs_nailed, bonus=0.0)
        ceiling_fringe = model.ceiling_points(means["Fringe"], fringe, cs_fringe, bonus=0.0)

        self.assertGreaterEqual(ceiling_nailed, total_nailed)
        self.assertGreaterEqual(ceiling_fringe, total_fringe)
        # Old bug: fringe's DefCon (and hence total/ceiling) looked like a
        # nailed starter's. P(play) ~= 0.2 for Fringe vs 1.0 for Nailed, so the
        # ceiling must land well below, not "essentially the same".
        self.assertLess(ceiling_fringe, ceiling_nailed * 0.5)

    def test_ceiling_still_at_least_total_for_every_appearance_probability(self):
        players, _ = self._shared_match_squads(975, "DEF", {"defcon_per90": 8.0})
        means = engine_events.event_means(players)
        for name in ("Nailed", "Rotator", "Fringe"):
            ps = players[name]
            conceded_samples = model._conceded_series(ps)
            total = model.total_points(means[name], ps, conceded_samples, bonus=0.3)
            ceiling = model.ceiling_points(means[name], ps, conceded_samples, bonus=0.3)
            self.assertGreaterEqual(ceiling, total, f"{name}: ceiling < total")


class TestNailedStarterUnaffectedByAppearanceScaling(unittest.TestCase):
    """A player who appears in every sim (played == sims, P(play) == 1) must
    produce EXACTLY the same total as before the fix -- this was already the
    correct case and scaling by 1.0 must be a no-op."""

    def _sample(self, **kw):
        ps = engine_events.PlayerSample("K", "LIV", kw.pop("position", "DEF"))
        ps.sims = 4
        ps.played = 4.0
        ps.played_60 = 4.0
        for key, value in kw.items():
            setattr(ps, key, value)
        return ps

    def test_defcon_unaffected_when_always_played(self):
        ps = self._sample(defcon_samples=[10, 10, 4, 10])
        means = {"position": "DEF", "played": 1.0, "played_60": 1.0,
                 "goals": 0.0, "assists": 0.0, "clean_sheet": 0.0,
                 "yellow": 0.0, "red": 0.0}
        pts = model.total_points(means, ps, conceded_samples=[], bonus=0.0)
        # defcon_points("DEF", [10,10,4,10]) == 2 * 3/4 == 1.5; P(play) == 1
        self.assertAlmostEqual(pts, 2.0 + 1.5)

    def test_saves_conceded_and_bonus_unaffected_when_always_played(self):
        ps = self._sample(position="GK", save_samples=[3, 3, 6, 0])
        means = {"position": "GK", "played": 1.0, "played_60": 1.0,
                 "goals": 0.0, "assists": 0.0, "clean_sheet": 0.0,
                 "yellow": 0.0, "red": 0.0}
        pts = model.total_points(means, ps, conceded_samples=[2, 2, 4, 0], bonus=1.4)
        # saves_points([3,3,6,0]) == (1+1+2+0)/4 == 1.0
        # conceded_points("GK", [2,2,4,0]) == -(1+1+2+0)/4 == -1.0
        self.assertAlmostEqual(pts, 2.0 + 1.0 - 1.0 + 1.4)


class TestZeroSimsGuard(unittest.TestCase):
    def test_sims_zero_does_not_raise(self):
        ps = engine_events.PlayerSample("K", "LIV", "DEF")
        ps.sims = 0
        ps.played = 0.0
        means = {"position": "DEF", "played": 0.0, "played_60": 0.0,
                 "goals": 0.0, "assists": 0.0, "clean_sheet": 0.0,
                 "yellow": 0.0, "red": 0.0}
        pts = model.total_points(means, ps, conceded_samples=[], bonus=0.0)
        self.assertAlmostEqual(pts, 0.0)
        ceiling = model.ceiling_points(means, ps, conceded_samples=[], bonus=0.0)
        self.assertAlmostEqual(ceiling, 0.0)


# ---------------------------------------------------------------------------
# build_rows / sim cache wiring
# ---------------------------------------------------------------------------

_TINY_PRIORS = {
    "H": [ratings.PlayerPrior("A1", "H", "FWD", start_prob=1.0, exp_minutes=90,
                              goal_share=0.5)],
    "A": [ratings.PlayerPrior("B1", "A", "DEF", start_prob=1.0, exp_minutes=90,
                              defcon_per90=9.0)],
}
_TINY_META = {"A1": {"price": 7.0, "ownership": 5.0, "minutes": 2700, "bps": 600},
              "B1": {"price": 4.5, "ownership": 2.0, "minutes": 2700, "bps": 500}}


class TestRunUsesTheSimCache(unittest.TestCase):
    """The run path must skip simulate_round entirely on a cache hit."""

    def setUp(self):
        import shutil
        import tempfile

        from core import simcache

        self.tmp = tempfile.mkdtemp(prefix="fpl_cache_test_")
        p = mock.patch.object(simcache, "CACHE_DIR", self.tmp)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        # A registered fixture for the test gameweek, following the pattern in
        # tests/test_engine_priors.py: append to the shared schedule in setUp,
        # remove it via addCleanup so this test can't leak state into others.
        self.fx = fixtures.Fixture(
            "FPLCACHE1", "H", "A",
            kickoff=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc),
            stage="GW", fantasy_round=901, neutral=False,
            lam_home=1.6, lam_away=1.1,
        )
        fixtures.SCHEDULE.append(self.fx)
        self.addCleanup(lambda: fixtures.SCHEDULE.remove(self.fx))

    def test_second_call_with_identical_inputs_does_not_simulate(self):
        # Drive build_rows twice; the second must be served from cache.
        calls = []
        real = model.engine_events.simulate_round

        def counting(*a, **kw):
            calls.append(1)
            return real(*a, **kw)

        with mock.patch.object(model.engine_events, "simulate_round",
                              side_effect=counting):
            model.build_rows(_TINY_PRIORS, _TINY_META, gameweek=901, sims=50)
            model.build_rows(_TINY_PRIORS, _TINY_META, gameweek=901, sims=50)
        self.assertEqual(len(calls), 1, "second call should have hit the cache")

    def test_changed_priors_force_a_fresh_simulation(self):
        calls = []
        real = model.engine_events.simulate_round

        def counting(*a, **kw):
            calls.append(1)
            return real(*a, **kw)

        changed = {"H": [ratings.PlayerPrior("A1", "H", "FWD", start_prob=0.4,
                                            exp_minutes=90, goal_share=0.5)]}
        with mock.patch.object(model.engine_events, "simulate_round",
                              side_effect=counting):
            model.build_rows(_TINY_PRIORS, _TINY_META, gameweek=901, sims=50)
            model.build_rows(changed, _TINY_META, gameweek=901, sims=50)
        self.assertEqual(len(calls), 2, "changed priors must invalidate the cache")

    def test_cache_can_be_bypassed(self):
        calls = []
        real = model.engine_events.simulate_round

        def counting(*a, **kw):
            calls.append(1)
            return real(*a, **kw)

        with mock.patch.object(model.engine_events, "simulate_round",
                              side_effect=counting):
            model.build_rows(_TINY_PRIORS, _TINY_META, gameweek=901, sims=50)
            model.build_rows(_TINY_PRIORS, _TINY_META, gameweek=901, sims=50,
                             use_cache=False)
        self.assertEqual(len(calls), 2, "use_cache=False must always simulate")

    def test_cached_rows_match_freshly_simulated_rows(self):
        fresh = model.build_rows(_TINY_PRIORS, _TINY_META, gameweek=901, sims=50,
                                 use_cache=False)
        model.build_rows(_TINY_PRIORS, _TINY_META, gameweek=901, sims=50)
        cached = model.build_rows(_TINY_PRIORS, _TINY_META, gameweek=901, sims=50)
        self.assertEqual([r["name"] for r in fresh], [r["name"] for r in cached])
        for a, b in zip(fresh, cached):
            self.assertAlmostEqual(a["x_points"], b["x_points"], places=6)
