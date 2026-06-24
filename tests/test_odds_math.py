import unittest

from core.odds_math import (
    implied_probs, devig, poisson_1x2, solve_lambdas, scorer_prob_to_goal_rate,
)


class TestOddsMath(unittest.TestCase):
    def test_implied_prob_is_inverse_decimal(self):
        self.assertAlmostEqual(implied_probs([2.0, 4.0, 4.0])[0], 0.5)

    def test_devig_sums_to_one(self):
        p = devig([2.0, 4.0, 4.0])
        self.assertAlmostEqual(sum(p), 1.0)
        self.assertGreater(p[0], p[1])

    def test_poisson_1x2_normalised_and_ordered(self):
        pH, pD, pA = poisson_1x2(1.6, 1.1)
        self.assertAlmostEqual(pH + pD + pA, 1.0, places=4)  # ~goal-grid truncation
        self.assertGreater(pH, pA)

    def test_solve_recovers_lambdas(self):
        pH, pD, pA = poisson_1x2(1.7, 0.9)
        lh, la = solve_lambdas(pH, pD, pA)
        self.assertLess(abs(lh - 1.7), 0.08)
        self.assertLess(abs(la - 0.9), 0.08)

    def test_anytime_scorer_to_rate(self):
        self.assertAlmostEqual(scorer_prob_to_goal_rate(0.5), 0.6931, places=3)
        self.assertEqual(scorer_prob_to_goal_rate(0.0), 0.0)


if __name__ == "__main__":
    unittest.main()
