import unittest

from core.odds_math import (
    american_to_decimal, dc_tau, score_matrix_dc, outcome_from_matrix,
    prob_over, solve_dc, poisson_1x2,
)


class TestAmerican(unittest.TestCase):
    def test_conversion(self):
        self.assertAlmostEqual(american_to_decimal(160), 2.6)
        self.assertAlmostEqual(american_to_decimal(-125), 1.8)
        self.assertAlmostEqual(american_to_decimal(100), 2.0)


class TestDixonColes(unittest.TestCase):
    def test_tau_cells(self):
        self.assertAlmostEqual(dc_tau(1, 1, 1.5, 1.0, 0.1), 0.9)
        self.assertAlmostEqual(dc_tau(0, 0, 1.5, 1.0, 0.1), 1 - 1.5 * 1.0 * 0.1)
        self.assertEqual(dc_tau(2, 3, 1.5, 1.0, 0.1), 1.0)  # untouched cell

    def test_matrix_normalised(self):
        grid = score_matrix_dc(1.6, 1.1, 0.08)
        self.assertAlmostEqual(sum(grid.values()), 1.0, places=9)

    def test_rho_zero_matches_independent(self):
        gridH, gridD, gridA = outcome_from_matrix(score_matrix_dc(1.7, 0.9, 0.0))
        pH, pD, pA = poisson_1x2(1.7, 0.9)
        self.assertAlmostEqual(gridH, pH, places=3)
        self.assertAlmostEqual(gridD, pD, places=3)

    def test_negative_rho_inflates_draw(self):
        # Standard Dixon-Coles: rho<0 lifts low-score draws (0-0/1-1) vs independent,
        # matching real football's draw inflation. rho>0 suppresses them.
        pD_indep = outcome_from_matrix(score_matrix_dc(1.4, 1.2, 0.0))[1]
        pD_dc = outcome_from_matrix(score_matrix_dc(1.4, 1.2, -0.10))[1]
        self.assertGreater(pD_dc, pD_indep)

    def test_solve_dc_recovers_targets(self):
        true = score_matrix_dc(1.5, 0.9, 0.07)
        pH, pD, pA = outcome_from_matrix(true)
        p_over = prob_over(true, 2.5)
        lh, la, rho = solve_dc(pH, pD, pA, p_over=p_over, line=2.5)
        got = score_matrix_dc(lh, la, rho)
        gH, gD, gA = outcome_from_matrix(got)
        self.assertLess(abs(gH - pH), 0.02)
        self.assertLess(abs(gD - pD), 0.02)
        self.assertLess(abs(prob_over(got, 2.5) - p_over), 0.03)


if __name__ == "__main__":
    unittest.main()
