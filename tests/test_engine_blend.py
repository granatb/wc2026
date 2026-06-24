import unittest
from datetime import datetime, timezone

from core import engine_events, fixtures, ratings
from core.research import ResearchEntry


class TestEffectiveWeight(unittest.TestCase):
    def test_market_only(self):
        w, s = engine_events.effective_goal_weight(None, 0.6, None, 0.3, base_start=0.8)
        self.assertEqual(w, 0.6)
        self.assertEqual(s, 0.8)

    def test_w_zero_is_market(self):
        w, _ = engine_events.effective_goal_weight(0.2, 0.6, None, 0.0)
        self.assertAlmostEqual(w, 0.6)

    def test_w_one_is_prior(self):
        w, _ = engine_events.effective_goal_weight(0.2, 0.6, None, 1.0)
        self.assertAlmostEqual(w, 0.2)

    def test_hard_out_zeroes(self):
        e = ResearchEntry(name="X", status="out")
        w, s = engine_events.effective_goal_weight(0.2, 0.6, e, 0.5)
        self.assertEqual((w, s), (0.0, 0.0))


class TestSimIntegration(unittest.TestCase):
    """End-to-end: a hard-out player scores ~0 goals across sims."""

    def setUp(self):
        ratings.TEAM_RATINGS["Testland"] = ratings.TeamRating("Testland", attack=2.0)
        ratings.TEAM_RATINGS["Foeland"] = ratings.TeamRating("Foeland", attack=0.5)
        self.star = ratings.PlayerPrior("Star", "Testland", "FWD",
                                        start_prob=1.0, goal_share=0.5)
        self.benched = ratings.PlayerPrior("Ghost", "Testland", "FWD",
                                           start_prob=1.0, goal_share=0.5)
        ratings.PLAYER_PRIORS["Star"] = self.star
        ratings.PLAYER_PRIORS["Ghost"] = self.benched
        self.fx = fixtures.Fixture("TEST99", "Testland", "Foeland",
                                   datetime(2026, 6, 20, 18, tzinfo=timezone.utc),
                                   "GROUP_MD1", 99, lam_home=2.5, lam_away=0.5)
        fixtures.SCHEDULE.append(self.fx)

    def tearDown(self):
        fixtures.SCHEDULE.remove(self.fx)
        for k in ("Star", "Ghost"):
            ratings.PLAYER_PRIORS.pop(k, None)
        for k in ("Testland", "Foeland"):
            ratings.TEAM_RATINGS.pop(k, None)

    def test_hard_out_player_scores_zero(self):
        research = {"Ghost": ResearchEntry(name="Ghost", status="out")}
        players, _ = engine_events.simulate_round(
            99, sims=3000, research=research, research_weight=0.3)
        self.assertEqual(players["Ghost"].goals, 0.0)
        self.assertGreater(players["Star"].goals, 0.0)


class TestConcentration(unittest.TestCase):
    """γ sharpens the within-team split while preserving the known players' mass."""

    def _alloc(self, gamma, draws=40000):
        import random
        rng = random.Random(7)
        pool = [ratings.PlayerPrior("A", "T", "FWD", goal_share=0.4),
                ratings.PlayerPrior("B", "T", "FWD", goal_share=0.1)]
        on = {"A": True, "B": True}
        wof = {"A": 0.4, "B": 0.1}            # wsum 0.5 -> 50% leaks to unmodeled
        a = b = 0
        for _ in range(draws):
            out = engine_events._distribute(1, pool, on, rng, wof, gamma)
            a += out.get("A", 0)
            b += out.get("B", 0)
        return a / draws, b / draws

    def test_mass_preserved_but_split_sharpens(self):
        a1, b1 = self._alloc(1.0)
        a2, b2 = self._alloc(2.0)
        # Known players' COMBINED share ~0.5 (the leak) under both gammas.
        self.assertAlmostEqual(a1 + b1, 0.5, delta=0.03)
        self.assertAlmostEqual(a2 + b2, 0.5, delta=0.03)
        # The high-share player takes a strictly larger slice when concentrated.
        self.assertGreater(a2 / (a2 + b2), a1 / (a1 + b1))


if __name__ == "__main__":
    unittest.main()
