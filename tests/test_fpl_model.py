import unittest
from datetime import datetime, timezone
from unittest import mock

from core import engine_events, fixtures, ratings
from games.fpl import model
from games.fpl import model as fpl_model


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

    def test_sim_points_accumulator_with_zero_sims_does_not_raise(self):
        acc = model.SimPointsAccumulator(baselines={}, sims=0)
        self.assertAlmostEqual(acc.mean("nobody"), 0.0)
        self.assertAlmostEqual(acc.tail_mean("nobody"), 0.0)


def _tiny_build_rows(sims=300, gameweek=98):
    """A 2-team, 1-fixture synthetic gameweek run through build_rows, cache off."""
    from core import fixtures
    from core.ratings import PlayerPrior

    squads = {
        "Home": [PlayerPrior(name="H-Def", team="Home", position="DEF",
                             start_prob=1.0, exp_minutes=90, defcon_per90=9.0),
                 PlayerPrior(name="H-Fwd", team="Home", position="FWD",
                             start_prob=1.0, exp_minutes=90, goal_share=0.5)],
        "Away": [PlayerPrior(name="A-Gk", team="Away", position="GK",
                             start_prob=1.0, exp_minutes=90, saves_per90=3.5)],
    }
    players_by_name = {
        "H-Def": {"name": "H-Def", "price": 4.5, "ownership": 2.0,
                  "minutes": 2700, "bps": 500},
        "H-Fwd": {"name": "H-Fwd", "price": 8.0, "ownership": 30.0,
                  "minutes": 2700, "bps": 600},
        "A-Gk": {"name": "A-Gk", "price": 5.0, "ownership": 5.0,
                 "minutes": 3420, "bps": 700},
    }
    saved = list(fixtures.SCHEDULE)
    try:
        fixtures.SCHEDULE.clear()
        fixtures.SCHEDULE.append(fixtures.Fixture(
            match_id="tiny-1", home="Home", away="Away",
            kickoff=datetime(2026, 8, 21, 19, 0, tzinfo=timezone.utc),
            stage="GW", fantasy_round=gameweek, neutral=False,
            lam_home=1.6, lam_away=1.1))
        return fpl_model.build_rows(
            {t: s for t, s in squads.items()}, players_by_name,
            gameweek, sims, use_cache=False)
    finally:
        fixtures.SCHEDULE.clear()
        fixtures.SCHEDULE.extend(saved)


def _tiny_build_artifact(sims=300, gameweek=98, priced=True, use_cache=False):
    """_tiny_build_rows' fixture, but returning the full (artifact, cache_hit)."""
    from core import fixtures
    from core.ratings import PlayerPrior

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
    saved = list(fixtures.SCHEDULE)
    try:
        fixtures.SCHEDULE.clear()
        fixtures.SCHEDULE.append(fixtures.Fixture(
            match_id="tiny-1", home="Home", away="Away",
            kickoff=datetime(2026, 8, 21, 19, 0, tzinfo=timezone.utc),
            stage="GW", fantasy_round=gameweek, neutral=False,
            lam_home=1.6 if priced else None,
            lam_away=1.1 if priced else None))
        return fpl_model.build_artifact(
            squads, players_by_name, gameweek, sims, use_cache=use_cache)
    finally:
        fixtures.SCHEDULE.clear()
        fixtures.SCHEDULE.extend(saved)


class TestMatchSummaries(unittest.TestCase):
    def test_summary_fields_and_probability_normalisation(self):
        artifact, _hit = _tiny_build_artifact()
        self.assertEqual(len(artifact["matches"]), 1)
        m = artifact["matches"][0]
        for key in ("match_id", "home", "away", "kickoff", "exp_home_goals",
                    "exp_away_goals", "exp_total", "top_scoreline", "p_home",
                    "p_draw", "p_away", "p_cs_home", "p_cs_away", "market"):
            self.assertIn(key, m)
        self.assertAlmostEqual(m["p_home"] + m["p_draw"] + m["p_away"], 1.0, places=2)
        self.assertAlmostEqual(m["exp_total"],
                               m["exp_home_goals"] + m["exp_away_goals"], places=2)

    def test_no_advancement_fields_ever(self):
        """FPL has no knockout. articles.match_predictions would emit p_advance_*
        for any round >= 4; this path must never grow that field, or GW4 would
        publish a survival probability for a league season."""
        artifact, _hit = _tiny_build_artifact(gameweek=7)
        self.assertNotIn("p_advance_home", artifact["matches"][0])
        self.assertNotIn("p_advance_away", artifact["matches"][0])

    def test_market_flag_tracks_priced_fixtures(self):
        """A fixture with odds-derived lambdas is market-derived; one falling back
        to ratings is not. The ticker labels the columns from this."""
        priced, _ = _tiny_build_artifact()
        self.assertTrue(priced["matches"][0]["market"])
        unpriced, _ = _tiny_build_artifact(priced=False)
        self.assertFalse(unpriced["matches"][0]["market"])

    def test_artifact_round_trips_through_the_cache(self):
        # CACHE_DIR is patched to a fresh temp dir so the first call is a real
        # miss on EVERY suite run — against the real dir, the artifact stored by
        # a previous run would make hit_first True and fail the assertion.
        import tempfile

        from core import simcache

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(simcache, "CACHE_DIR", tmp):
                first, hit_first = _tiny_build_artifact(use_cache=True, gameweek=97)
                second, hit_second = _tiny_build_artifact(use_cache=True, gameweek=97)
        self.assertFalse(hit_first)
        self.assertTrue(hit_second)
        self.assertEqual(first["matches"], second["matches"])
        self.assertEqual(first["rows"], second["rows"])

    def test_cached_distribution_keys_come_back_as_ints(self):
        """JSON object keys are strings, so a cache hit would otherwise serve
        {"5": 61} where a fresh simulation serves {5: 61} — and every consumer
        does integer arithmetic on those keys."""
        import tempfile

        from core import simcache

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(simcache, "CACHE_DIR", tmp):
                _first, hit_first = _tiny_build_artifact(use_cache=True,
                                                         gameweek=95)
                second, hit_second = _tiny_build_artifact(use_cache=True,
                                                          gameweek=95)
        self.assertFalse(hit_first)
        self.assertTrue(hit_second)
        for r in second["rows"]:
            self.assertTrue(r["distribution"])
            for k in r["distribution"]:
                self.assertIsInstance(k, int)


class TestGwStageFilter(unittest.TestCase):
    """The shared SCHEDULE holds World Cup rounds AND FPL gameweeks, and their
    round numbers collide (WC round 1 == FPL GW1). The FPL artifact must only
    see stage=="GW" fixtures — otherwise the ticker publishes 48 national teams
    and the preflight warns about unpriced June fixtures."""

    def test_non_gw_fixtures_are_excluded_from_the_artifact(self):
        from core import fixtures
        saved = list(fixtures.SCHEDULE)
        try:
            fixtures.SCHEDULE.clear()
            # A World Cup fixture sharing the same fantasy_round number.
            fixtures.SCHEDULE.append(fixtures.Fixture(
                match_id="wc-1", home="Mexico", away="South Africa",
                kickoff=datetime(2026, 6, 11, 20, 0, tzinfo=timezone.utc),
                stage="GROUP_MD1", fantasy_round=98, neutral=False,
                lam_home=1.4, lam_away=0.9))
        finally:
            # _tiny_build_artifact saves/clears/restores SCHEDULE itself, so we
            # re-add the WC fixture inside a fresh saved copy instead.
            pass
        try:
            from core.ratings import PlayerPrior
            squads = {
                "Home": [PlayerPrior(name="H-Def", team="Home", position="DEF",
                                     start_prob=1.0, exp_minutes=90,
                                     defcon_per90=9.0)],
            }
            fixtures.SCHEDULE.append(fixtures.Fixture(
                match_id="tiny-gw", home="Home", away="Away",
                kickoff=datetime(2026, 8, 21, 19, 0, tzinfo=timezone.utc),
                stage="GW", fantasy_round=98, neutral=False,
                lam_home=1.6, lam_away=1.1))
            artifact, _hit = fpl_model.build_artifact(
                squads, {}, 98, 100, use_cache=False)
            match_ids = [m["match_id"] for m in artifact["matches"]]
            self.assertEqual(match_ids, ["tiny-gw"],
                             "non-GW fixtures leaked into the FPL artifact")
        finally:
            fixtures.SCHEDULE.clear()
            fixtures.SCHEDULE.extend(saved)


class TestDerivedRowColumns(unittest.TestCase):
    def test_derived_columns_present_and_consistent(self):
        row = fpl_model._derive_row(
            name="Testy", means={"team": "ARS", "position": "DEF",
                                 "clean_sheet": 0.4},
            x_points=6.0, ceiling=11.0, bonus=0.5, defcon_pts=1.2,
            p_defcon=0.6, price=5.5, ownership=12.3,
            kickoff="2026-08-21T19:00:00+00:00")
        self.assertEqual(row["captain_ev"], 12.0)
        self.assertEqual(row["value"], 1.091)          # 6.0 / 5.5
        self.assertEqual(row["p_defcon"], 0.6)
        self.assertEqual(row["cs_points"], 1.6)        # 0.4 * CS_PTS["DEF"] == 4
        self.assertEqual(row["kickoff"], "2026-08-21T19:00:00+00:00")

    def test_value_is_none_without_a_price(self):
        row = fpl_model._derive_row(
            name="Pricy", means={"team": "ARS", "position": "MID",
                                 "clean_sheet": 0.0},
            x_points=6.0, ceiling=9.0, bonus=0.0, defcon_pts=0.0, p_defcon=0.0,
            price=None, ownership=None, kickoff=None)
        self.assertIsNone(row["value"])
        self.assertEqual(row["captain_ev"], 12.0)

    def test_p_defcon_is_the_points_column_halved(self):
        """defcon points are exactly 2 x P(threshold) x P(played), so the two
        columns must never disagree — the article prints one and the table the
        other."""
        row = fpl_model._derive_row(
            name="Blocker", means={"team": "BUR", "position": "DEF",
                                   "clean_sheet": 0.2},
            x_points=4.0, ceiling=7.0, bonus=0.0, defcon_pts=1.44, p_defcon=0.72,
            price=4.5, ownership=1.0, kickoff=None)
        self.assertAlmostEqual(row["defcon"], row["p_defcon"] * fpl_model.DEFCON_PTS,
                               places=6)

    def test_build_rows_carries_the_new_columns(self):
        rows = _tiny_build_rows()      # helper defined above
        self.assertTrue(rows)
        for key in ("captain_ev", "value", "p_defcon", "cs_points", "kickoff"):
            self.assertIn(key, rows[0], f"{key} missing from build_rows output")


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


class TestTailMeanStatistic(unittest.TestCase):
    """The tail-mean arithmetic itself, over hand-built distributions -- proves
    the statistic in isolation, independent of the engine or the per-sim row
    scoring that normally produces its input."""

    def test_hand_built_distribution_matches_hand_computed_value(self):
        # 10 sims' worth of totals; q=0.85 -> tail size = max(1, round(0.15*10))
        # = max(1, round(1.5)) = 2 -> top two values [8, 10] -> mean 9.0
        values = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10]
        self.assertAlmostEqual(model._tail_mean(values, q=0.85), 9.0)

    def test_tail_size_never_degenerates_to_empty(self):
        # round((1-0.85)*3) == round(0.45) == 0 without the floor -> must clamp
        # to 1, taking just the single highest value.
        values = [1.0, 2.0, 3.0]
        self.assertAlmostEqual(model._tail_mean(values, q=0.85), 3.0)

    def test_empty_distribution_is_zero(self):
        self.assertAlmostEqual(model._tail_mean([], q=0.85), 0.0)

    def test_matches_via_sim_points_accumulator_with_synthetic_rows(self):
        # Drive the accumulator through observe() with hand-built rows so the
        # SAME known distribution is produced via the real per-sim path, not
        # just by poking at the bare statistic.
        acc = model.SimPointsAccumulator(baselines={}, sims=4)
        # position FWD, 90 minutes -> appearance 2 pts; goals * GOAL_PTS["FWD"]==4.
        # Each row is the ONLY player in its match, so _bonus_awards ranks him
        # first every time -> +3 bonus on every observed sim.
        # sim 0: 0 goals -> 2 + 3       = 5.
        # sim 1: 1 goal  -> 2 + 4 + 3   = 9.
        # sim 2: 2 goals -> 2 + 8 + 3   = 13.
        # sim 3: player never observed (did not feature) -> zero-padded.
        for sim_index, goals in ((0, 0), (1, 1), (2, 2)):
            row = ("P", "FWD", goals, 0, 90, False, 0, 0, 0, 0, 0)
            acc.observe("m", [row], sim_index)
        # distribution (zero-padded) = [5, 9, 13, 0]; q=0.85 -> tail size
        # max(1, round(0.15 * 4)) = max(1, round(0.6)) = 1 -> top value only.
        self.assertAlmostEqual(acc.tail_mean("P", q=0.85), 13.0)
        self.assertAlmostEqual(acc.mean("P"), (5 + 9 + 13 + 0) / 4.0)


class TestHistogram(unittest.TestCase):
    """SimPointsAccumulator.histogram — the discrete PMF the whole of Phase 2A
    is built on (spec 2026-08-26 D2). Same zero-padded convention as mean():
    a sim the player did not feature in contributes a 0, not an absence."""

    def _acc_over_ten_sims(self):
        # One player, alone in his match, FWD, 90 minutes -> 2 appearance pts
        # + 4/goal + 3 bonus (only ranked player). Featured in sims 0..7 only;
        # sims 8 and 9 are non-appearances and must zero-pad.
        acc = model.SimPointsAccumulator(baselines={}, sims=10)
        goals_by_sim = {0: 0, 1: 0, 2: 1, 3: 1, 4: 1, 5: 2, 6: 2, 7: 3}
        for sim_index, goals in goals_by_sim.items():
            acc.observe("m", [("P", "FWD", goals, 0, 90, False, 0, 0, 0, 0, 0)],
                        sim_index)
        return acc

    def test_hand_built_accumulator_gives_the_exact_pmf(self):
        acc = self._acc_over_ten_sims()
        # 0 goals -> 5, 1 goal -> 9, 2 goals -> 13, 3 goals -> 17.
        self.assertEqual(acc.histogram("P"),
                         {0: 2, 5: 2, 9: 3, 13: 2, 17: 1})

    def test_keys_are_plain_ints(self):
        acc = self._acc_over_ten_sims()
        for k, v in acc.histogram("P").items():
            self.assertIsInstance(k, int)
            self.assertIsInstance(v, int)

    def test_counts_sum_to_the_sim_count(self):
        acc = self._acc_over_ten_sims()
        self.assertEqual(sum(acc.histogram("P").values()), acc.sims)

    def test_never_appearing_player_is_all_mass_at_zero(self):
        acc = self._acc_over_ten_sims()
        self.assertEqual(acc.histogram("ghost"), {0: 10})

    def test_histogram_mean_reconstructs_mean(self):
        acc = self._acc_over_ten_sims()
        hist = acc.histogram("P")
        reconstructed = (sum(pts * n for pts, n in hist.items())
                         / float(acc.sims))
        self.assertAlmostEqual(reconstructed, acc.mean("P"), delta=1e-9)

    def test_zero_sims_gives_an_empty_histogram(self):
        acc = model.SimPointsAccumulator(baselines={}, sims=0)
        self.assertEqual(acc.histogram("nobody"), {})

    def test_negative_totals_keep_their_sign(self):
        # sim 0: a red card (-3) on a sub-60 cameo (+1), alone in the match so
        # he still takes the 3 bonus -> 1. sim 1: the same cameo clean -> 4.
        # Column order is (name, pos, goals, assists, minutes, cs, conceded,
        # saves, yellow, red, defcon).
        acc = model.SimPointsAccumulator(baselines={}, sims=2)
        acc.observe("m", [("R", "FWD", 0, 0, 30, False, 0, 0, 0, 1, 0)], 0)
        acc.observe("m", [("R", "FWD", 0, 0, 30, False, 0, 0, 0, 0, 0)], 1)
        hist = acc.histogram("R")
        self.assertEqual(sum(hist.values()), 2)
        self.assertEqual(hist, {1: 1, 4: 1})


class TestDistributionStats(unittest.TestCase):
    """The six derived columns, over hand-built PMFs with known answers."""

    # 10 sims: 0,0,2,4,4,4,7,10,12,20 -> cumulative
    #   0:2 (0.2) 2:1 (0.3) 4:3 (0.6) 7:1 (0.7) 10:1 (0.8) 12:1 (0.9) 20:1 (1.0)
    PMF = {0: 2, 2: 1, 4: 3, 7: 1, 10: 1, 12: 1, 20: 1}

    def test_percentile_lower_bound_convention(self):
        # smallest x with cumulative >= q
        self.assertEqual(model._pmf_percentile(self.PMF, 0.10), 0)
        self.assertEqual(model._pmf_percentile(self.PMF, 0.20), 0)
        self.assertEqual(model._pmf_percentile(self.PMF, 0.25), 2)
        self.assertEqual(model._pmf_percentile(self.PMF, 0.50), 4)
        self.assertEqual(model._pmf_percentile(self.PMF, 0.60), 4)
        self.assertEqual(model._pmf_percentile(self.PMF, 0.90), 12)
        self.assertEqual(model._pmf_percentile(self.PMF, 1.00), 20)

    def test_percentile_of_an_empty_pmf_is_zero(self):
        self.assertEqual(model._pmf_percentile({}, 0.5), 0)

    def test_mode_is_the_highest_count(self):
        self.assertEqual(model._pmf_mode(self.PMF), 4)

    def test_mode_ties_break_to_the_lowest_value(self):
        self.assertEqual(model._pmf_mode({9: 5, 2: 5, 30: 1}), 2)

    def test_mode_of_an_empty_pmf_is_zero(self):
        self.assertEqual(model._pmf_mode({}), 0)

    def test_p_haul_is_inclusive_of_exactly_ten(self):
        # mass at 10, 12, 20 -> 3/10
        self.assertAlmostEqual(model._pmf_tail_prob(self.PMF, 10), 0.3)
        # a PMF whose ONLY mass sits exactly on the threshold is p_haul 1.0
        self.assertAlmostEqual(model._pmf_tail_prob({10: 7}, 10), 1.0)

    def test_p_blank_is_inclusive_of_exactly_two(self):
        # mass at 0 (x2) and 2 -> 3/10
        self.assertAlmostEqual(model._pmf_head_prob(self.PMF, 2), 0.3)
        self.assertAlmostEqual(model._pmf_head_prob({2: 4}, 2), 1.0)

    def _row(self, distribution):
        return model._derive_row(
            name="Dist", means={"team": "ARS", "position": "MID",
                                "clean_sheet": 0.0},
            x_points=6.3, ceiling=14.0, bonus=0.4, defcon_pts=0.0,
            p_defcon=0.0, price=7.0, ownership=10.0, kickoff=None,
            distribution=distribution)

    def test_derive_row_carries_all_six_fields(self):
        row = self._row(dict(self.PMF))
        self.assertEqual(row["p10"], 0)
        self.assertEqual(row["median"], 4)
        self.assertEqual(row["p90"], 12)
        self.assertEqual(row["mode"], 4)
        self.assertAlmostEqual(row["p_haul"], 0.3)
        self.assertAlmostEqual(row["p_blank"], 0.3)

    def test_percentiles_are_ints_and_probabilities_are_4dp(self):
        row = self._row({0: 1, 3: 1, 7: 1})
        for key in ("p10", "median", "p90", "mode"):
            self.assertIsInstance(row[key], int, key)
        # 1/3 rounded to 4dp
        self.assertEqual(row["p_blank"], 0.3333)

    def test_a_row_without_a_distribution_has_none_of_the_six(self):
        """An artifact written before histograms existed degrades — it does
        not carry a fabricated floor of zero."""
        row = model._derive_row(
            name="Old", means={"team": "ARS", "position": "MID",
                               "clean_sheet": 0.0},
            x_points=6.3, ceiling=14.0, bonus=0.4, defcon_pts=0.0,
            p_defcon=0.0, price=7.0, ownership=10.0, kickoff=None)
        for key in ("distribution", "p10", "median", "p90", "mode",
                    "p_haul", "p_blank"):
            self.assertNotIn(key, row)

    def test_real_rows_carry_the_six_fields(self):
        rows = _tiny_build_rows(sims=200, gameweek=94)
        self.assertTrue(rows)
        for r in rows:
            for key in ("p10", "median", "p90", "mode", "p_haul", "p_blank"):
                self.assertIn(key, r, f"{key} missing from {r['name']}")
            self.assertLessEqual(r["p10"], r["median"])
            self.assertLessEqual(r["median"], r["p90"])
            self.assertGreaterEqual(r["p_haul"], 0.0)
            self.assertLessEqual(r["p_haul"], 1.0)


class TestBuildRowsCarriesTheDistribution(unittest.TestCase):
    def test_every_row_has_a_histogram_summing_to_sims(self):
        rows = _tiny_build_rows(sims=200, gameweek=97)
        self.assertTrue(rows)
        for r in rows:
            self.assertIn("distribution", r)
            dist = r["distribution"]
            self.assertIsInstance(dist, dict)
            self.assertEqual(sum(dist.values()), 200)
            for k in dist:
                self.assertIsInstance(k, int)

    def test_distribution_mean_agrees_with_x_points(self):
        rows = _tiny_build_rows(sims=200, gameweek=96)
        for r in rows:
            dist = r["distribution"]
            mean = sum(p * n for p, n in dist.items()) / 200.0
            # x_points is the same quantity rounded to 2dp by _derive_row.
            self.assertAlmostEqual(mean, r["x_points"], delta=0.006)


class TestNeverFeaturingPlayerHasZeroMeanAndTailMean(unittest.TestCase):
    def test_zero_start_prob_yields_zero_for_both_statistics(self):
        fx = fixtures.Fixture(
            "NEVER1", "H", "A",
            kickoff=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc),
            stage="GW", fantasy_round=960, neutral=False,
            lam_home=1.5, lam_away=1.2)
        fixtures.SCHEDULE.append(fx)
        self.addCleanup(lambda: fixtures.SCHEDULE.remove(fx))
        squads = {
            "H": [ratings.PlayerPrior("Bench", "H", "FWD", start_prob=0.0,
                                      exp_minutes=90, goal_share=0.4)],
            "A": [ratings.PlayerPrior("Opp", "A", "FWD", start_prob=1.0,
                                      exp_minutes=90, goal_share=0.4)],
        }
        points = model.SimPointsAccumulator(baselines={}, sims=2000)
        engine_events.simulate_round(
            960, sims=2000, priors=lambda t: squads.get(t, []),
            per_match_hook=points.observe)
        self.assertAlmostEqual(points.mean("Bench"), 0.0)
        self.assertAlmostEqual(points.tail_mean("Bench"), 0.0)


class TestTailMeanSmoothnessAcrossAppearanceProbability(unittest.TestCase):
    """The statistic this replaces (an unconditional percentile over a discrete
    goal count) was a CLIFF in appearance probability -- see the RETIRED
    ceiling_points note in games/fpl/model.py for the measured numbers
    (ceiling/xPts 1.84-2.72 above ~55% start probability, exactly 1.00 flat
    below it). The tail mean must instead be smooth: strictly decreasing as
    appearance probability falls, with no jump between adjacent points larger
    than ~2x."""

    SIMS = 20000

    def _tail_mean_for_start_prob(self, fantasy_round, start_prob):
        fx = fixtures.Fixture(
            f"SMOOTH{fantasy_round}", "H", "A",
            kickoff=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc),
            stage="GW", fantasy_round=fantasy_round, neutral=False,
            lam_home=1.6, lam_away=1.2)
        fixtures.SCHEDULE.append(fx)
        self.addCleanup(lambda: fixtures.SCHEDULE.remove(fx))
        squads = {
            "H": [ratings.PlayerPrior("Subject", "H", "FWD", start_prob=start_prob,
                                      exp_minutes=90, goal_share=0.35)],
            "A": [ratings.PlayerPrior("Opp", "A", "FWD", start_prob=1.0,
                                      exp_minutes=90, goal_share=0.4)],
        }
        points = model.SimPointsAccumulator(baselines={}, sims=self.SIMS)
        engine_events.simulate_round(
            fantasy_round, sims=self.SIMS, priors=lambda t: squads.get(t, []),
            per_match_hook=points.observe)
        return points.mean("Subject"), points.tail_mean("Subject")

    def test_ceiling_is_smooth_across_the_old_cliff_region(self):
        start_probs = [1.0, 0.8, 0.6, 0.4, 0.2]
        ceilings = [self._tail_mean_for_start_prob(940 + i, sp)[1]
                   for i, sp in enumerate(start_probs)]

        for a, b in zip(ceilings, ceilings[1:]):
            self.assertGreater(a, b, f"ceiling must strictly decrease: {ceilings}")
        for a, b in zip(ceilings, ceilings[1:]):
            self.assertLess(a / b, 2.0,
                            f"adjacent step is a cliff, not a gradient: {ceilings}")

    def test_tail_mean_never_below_the_mean(self):
        for i, sp in enumerate([1.0, 0.6, 0.2]):
            mean, tail = self._tail_mean_for_start_prob(950 + i, sp)
            self.assertGreaterEqual(tail, mean)


class TestDoubleGameweekPointsSumBothMatches(unittest.TestCase):
    """A double-gameweek player's per-sim total must be the SUM across both of
    that sim's matches -- the reason the hook now carries a sim_index at all."""

    SIMS = 15000

    def test_doubled_players_mean_exceeds_a_single_fixture_equivalent(self):
        fantasy_round = 970
        fixtures_to_add = [
            fixtures.Fixture(
                "DGW1", "DoubleTeam", "Opp1",
                kickoff=datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc),
                stage="GW", fantasy_round=fantasy_round, neutral=False,
                lam_home=1.5, lam_away=1.1),
            fixtures.Fixture(
                "DGW2", "DoubleTeam", "Opp2",
                kickoff=datetime(2026, 8, 22, 18, 0, tzinfo=timezone.utc),
                stage="GW", fantasy_round=fantasy_round, neutral=False,
                lam_home=1.5, lam_away=1.1),
            fixtures.Fixture(
                "SGW1", "SingleTeam", "Opp3",
                kickoff=datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc),
                stage="GW", fantasy_round=fantasy_round, neutral=False,
                lam_home=1.5, lam_away=1.1),
        ]
        for fx in fixtures_to_add:
            fixtures.SCHEDULE.append(fx)
            self.addCleanup(lambda fx=fx: fixtures.SCHEDULE.remove(fx))

        squads = {
            "DoubleTeam": [ratings.PlayerPrior("Doubled", "DoubleTeam", "FWD",
                                               start_prob=1.0, exp_minutes=90,
                                               goal_share=0.4)],
            "SingleTeam": [ratings.PlayerPrior("Single", "SingleTeam", "FWD",
                                               start_prob=1.0, exp_minutes=90,
                                               goal_share=0.4)],
            "Opp1": [ratings.PlayerPrior("O1", "Opp1", "MID",
                                        start_prob=1.0, exp_minutes=90)],
            "Opp2": [ratings.PlayerPrior("O2", "Opp2", "MID",
                                        start_prob=1.0, exp_minutes=90)],
            "Opp3": [ratings.PlayerPrior("O3", "Opp3", "MID",
                                        start_prob=1.0, exp_minutes=90)],
        }

        points = model.SimPointsAccumulator(baselines={}, sims=self.SIMS)
        engine_events.simulate_round(
            fantasy_round, sims=self.SIMS, priors=lambda t: squads.get(t, []),
            per_match_hook=points.observe)

        doubled_mean = points.mean("Doubled")
        single_mean = points.mean("Single")
        # Both players are identical (same goal_share, start_prob, opponent
        # strength) except that Doubled has TWO fixtures this gameweek. If the
        # accumulator failed to distinguish "two matches, one sim" from "two
        # matches, two different sims" -- i.e. did not use sim_index -- his
        # mean would come out roughly equal to Single's, not close to double it.
        self.assertGreater(doubled_mean, single_mean * 1.7)


class TestDistributionMeanAgreesWithTotalPoints(unittest.TestCase):
    """mean() must reproduce total_points() -- an end-to-end cross-check of the
    per-sim scoring path (SimPointsAccumulator) against the mean/threshold path
    (total_points) that is already well tested on its own. A MID subject with
    no DefCon rate is used so neither side has to go through the goals-conceded
    or DefCon threshold APPROXIMATIONS (_conceded_series, defcon_points'
    per-sim counts) -- those are exact per-sim quantities on both sides here,
    so the two paths should agree almost exactly, not just approximately."""

    SIMS = 20000

    def _run(self, fantasy_round, start_prob):
        fx = fixtures.Fixture(
            f"MEANCHK{fantasy_round}", "H", "A",
            kickoff=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc),
            stage="GW", fantasy_round=fantasy_round, neutral=False,
            lam_home=1.6, lam_away=1.2)
        fixtures.SCHEDULE.append(fx)
        self.addCleanup(lambda: fixtures.SCHEDULE.remove(fx))
        squads = {
            "H": [ratings.PlayerPrior("Subject", "H", "MID", start_prob=start_prob,
                                      exp_minutes=90, goal_share=0.3,
                                      assist_share=0.2)],
            "A": [ratings.PlayerPrior("Opp", "A", "FWD", start_prob=1.0,
                                      exp_minutes=90, goal_share=0.4)],
        }
        baselines = {"Subject": 20.0, "Opp": 25.0}
        bonus = model.BonusAccumulator(baselines)
        points = model.SimPointsAccumulator(baselines, sims=self.SIMS)

        def hook(match_id, rows, sim_index):
            bonus.observe(match_id, rows, sim_index)
            points.observe(match_id, rows, sim_index)

        players, _ = engine_events.simulate_round(
            fantasy_round, sims=self.SIMS, priors=lambda t: squads.get(t, []),
            per_match_hook=hook)
        means = engine_events.event_means(players)
        ps = players["Subject"]
        player_bonus = bonus.expected("Subject")
        # MID is exempt from the conceded penalty regardless of the samples
        # passed, so an empty list sidesteps the _conceded_series approximation
        # entirely rather than needing it to agree with the per-sim path too.
        total = model.total_points(means["Subject"], ps, conceded_samples=[],
                                   bonus=player_bonus)
        return total, points.mean("Subject")

    def test_agrees_for_a_nailed_starter(self):
        total, dist_mean = self._run(980, 1.0)
        self.assertAlmostEqual(total, dist_mean, delta=0.03)

    def test_agrees_at_moderate_appearance_probability(self):
        total, dist_mean = self._run(981, 0.6)
        self.assertAlmostEqual(total, dist_mean, delta=0.03)

    def test_agrees_at_low_appearance_probability(self):
        total, dist_mean = self._run(982, 0.3)
        self.assertAlmostEqual(total, dist_mean, delta=0.03)


class TestDoubleGameweekTotalPoints(unittest.TestCase):
    """The carried Phase 3 question: does total_points sum bonus across a double?

    SimPointsAccumulator.mean() sums each sim's matches explicitly and has its own
    double-gameweek coverage, so it is the reference. total_points goes through the
    older assembly path (expected_points + conditional components scaled by
    played/sims) and is the one in question.
    """

    def _double_gameweek_samples(self, sims=4000):
        """Simulate a synthetic gameweek where one team plays TWICE."""
        from core import fixtures
        from core.ratings import PlayerPrior

        squads = {
            "Alpha": [PlayerPrior(name="A-Striker", team="Alpha", position="FWD",
                                  start_prob=1.0, exp_minutes=90, goal_share=0.4,
                                  assist_share=0.2),
                      PlayerPrior(name="A-Keeper", team="Alpha", position="GK",
                                  start_prob=1.0, exp_minutes=90, saves_per90=3.0)],
            "Beta": [PlayerPrior(name="B-Striker", team="Beta", position="FWD",
                                 start_prob=1.0, exp_minutes=90, goal_share=0.4,
                                 assist_share=0.2)],
            "Gamma": [PlayerPrior(name="G-Striker", team="Gamma", position="FWD",
                                  start_prob=1.0, exp_minutes=90, goal_share=0.4,
                                  assist_share=0.2)],
        }
        saved = list(fixtures.SCHEDULE)
        try:
            fixtures.SCHEDULE.clear()
            for mid, home, away in (("dgw-1", "Alpha", "Beta"),
                                    ("dgw-2", "Gamma", "Alpha")):
                fixtures.SCHEDULE.append(fixtures.Fixture(
                    match_id=mid, home=home, away=away,
                    kickoff=datetime(2026, 8, 21, 17, 30, tzinfo=timezone.utc),
                    stage="GW", fantasy_round=99, neutral=False,
                    lam_home=1.5, lam_away=1.2))
            baselines = {}
            bonus = fpl_model.BonusAccumulator(baselines)
            points = fpl_model.SimPointsAccumulator(baselines, sims)

            def hook(match_id, rows, sim_index):
                bonus.observe(match_id, rows, sim_index)
                points.observe(match_id, rows, sim_index)

            samples, _ = engine_events.simulate_round(
                99, sims=sims, seed=4242,
                priors=lambda team: squads.get(team, []),
                per_match_hook=hook)
            return samples, engine_events.event_means(samples), bonus, points
        finally:
            fixtures.SCHEDULE.clear()
            fixtures.SCHEDULE.extend(saved)

    def test_double_gameweek_assembly_path_is_per_match_not_per_gameweek(self):
        """ANSWERED 2026-08-19, and the answer is NO: the assembled path does
        NOT reconstruct the sum across a double.

        As first drafted this asserted assembled == per-sim reference; it
        failed at exactly a factor of two (7.149 vs 14.298). The Phase 3
        note's premise was wrong: ps.sims increments once per MATCH appearance
        (twice per outer sim for a doubled player), so played/sims stays ~1.0
        — it never approaches 2.0 — and every component of total_points
        (event_means division included) comes out as a per-MATCH average, half
        the gameweek total. Pinned at 2x so the answer stays settled; the
        order book therefore reads x_points off SimPointsAccumulator.mean(),
        which sums a player's matches within each sim.
        """
        samples, means, bonus, points = self._double_gameweek_samples()
        ps = samples["A-Striker"]          # Alpha plays twice
        assembled = fpl_model.total_points(
            means["A-Striker"], ps, fpl_model._conceded_series(ps),
            bonus=bonus.expected("A-Striker"))
        reference = points.mean("A-Striker")
        self.assertAlmostEqual(assembled * 2, reference, delta=0.35,
                               msg=f"double-GW characterisation drifted: "
                                   f"assembled={assembled:.3f} (expected per-match, "
                                   f"i.e. half) per-sim={reference:.3f}")

    def test_single_fixture_player_still_agrees(self):
        """Control: a single-fixture player must agree just as closely, so a
        failure above is attributable to the double and not to general drift."""
        samples, means, bonus, points = self._double_gameweek_samples()
        ps = samples["B-Striker"]          # Beta plays once
        assembled = fpl_model.total_points(
            means["B-Striker"], ps, fpl_model._conceded_series(ps),
            bonus=bonus.expected("B-Striker"))
        self.assertAlmostEqual(assembled, points.mean("B-Striker"), delta=0.35)


class TestSimCacheKeyKickoffs(unittest.TestCase):
    """Review finding 2: a fixture re-slotted for TV with unchanged odds must
    MISS the sim cache — the artifact's rows and match summaries carry the
    kickoff, so a key blind to it would serve stale kickoffs."""

    def _fixture(self, kickoff):
        return fixtures.Fixture(
            "KEY1", "Home", "Away", kickoff=kickoff,
            stage="GW", fantasy_round=1, neutral=False,
            lam_home=1.4, lam_away=1.1)

    def test_projection_carries_lambdas_and_kickoff(self):
        fx = self._fixture(datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc))
        proj = fpl_model._match_projection([fx])
        self.assertEqual(proj["KEY1"]["lambdas"], (1.4, 1.1))
        self.assertEqual(proj["KEY1"]["kickoff"],
                         "2026-08-22T15:00:00+00:00")

    def test_reslotted_kickoff_changes_the_cache_key(self):
        from core import simcache

        def key_for(kickoff):
            return simcache.cache_key(
                gameweek=1, sims=100, seed=7,
                lambdas=fpl_model._match_projection([self._fixture(kickoff)]),
                priors={}, research={}, config={})

        saturday = key_for(datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc))
        monday = key_for(datetime(2026, 8, 24, 19, 0, tzinfo=timezone.utc))
        self.assertNotEqual(saturday, monday)
