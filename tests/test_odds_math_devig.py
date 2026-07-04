"""De-vig method bake-off building blocks: proportional (existing), Shin, power.

Research (Strumbelj 2014; Hegarty & Whelan 2025) finds proportional normalisation is
the worst mainstream de-vig method: it understates favourites (favourite-longshot
bias). Shin's method (models informed/insider trading share z) and the power method
(probs = raw^k, normalised) are the leading challengers. These tests pin down the
maths in isolation before the engine ever consumes them (see config.DEVIG_METHOD).
"""

import unittest

from core.odds_math import (
    implied_probs, devig, devig_proportional, devig_shin, devig_power, devig_by_method,
)


class TestDevigProportional(unittest.TestCase):
    """devig_proportional must be the existing `devig` behaviour, bit-identical."""

    def test_sums_to_one(self):
        p = devig_proportional([2.0, 4.0, 4.0])
        self.assertAlmostEqual(sum(p), 1.0)

    def test_matches_old_devig_function_exactly(self):
        odds = [1.5, 4.2, 6.0]
        self.assertEqual(devig_proportional(odds), devig(odds))

    def test_old_devig_still_callable_unchanged(self):
        # Old call paths (core/espn.py etc.) call odds_math.devig(...) directly —
        # this must keep working, bit-identical to before the refactor.
        p = devig([2.0, 4.0, 4.0])
        self.assertAlmostEqual(sum(p), 1.0)
        self.assertGreater(p[0], p[1])


class TestDevigShin(unittest.TestCase):
    def test_sums_to_one_three_way(self):
        implied = implied_probs([1.5, 4.2, 6.0])  # booksum > 1
        p = devig_shin(implied)
        self.assertAlmostEqual(sum(p), 1.0, places=6)

    def test_all_in_unit_interval(self):
        implied = implied_probs([1.5, 4.2, 6.0])
        p = devig_shin(implied)
        for x in p:
            self.assertGreater(x, 0.0)
            self.assertLess(x, 1.0)

    def test_two_way_market_sanity(self):
        implied = implied_probs([1.80, 2.10])  # booksum ~1.032
        p = devig_shin(implied)
        self.assertAlmostEqual(sum(p), 1.0, places=6)
        self.assertGreater(p[0], p[1])  # order preserved (favourite still favourite)

    def test_zero_overround_reduces_to_normalisation(self):
        # No margin (booksum == 1) -> z should be ~0 and Shin collapses to
        # proportional normalisation (which here is a no-op, already sums to 1).
        implied = [0.5, 0.3, 0.2]
        p = devig_shin(implied)
        for a, b in zip(p, implied):
            self.assertAlmostEqual(a, b, places=4)

    def test_favourite_longshot_correction_vs_proportional(self):
        # Lopsided 3-way market, considerable overround (booksum 1.10).
        # Shin's FLB correction should give the favourite (index 0) MORE probability
        # than plain proportional normalisation, and the longshot (index 2) less.
        raw = [0.70, 0.25, 0.15]  # sums to 1.10
        prop = devig_proportional_from_implied(raw)
        shin = devig_shin(raw)
        self.assertGreater(shin[0], prop[0])
        self.assertLess(shin[2], prop[2])
        self.assertAlmostEqual(sum(shin), 1.0, places=6)

    def test_z_recovered_in_sensible_range(self):
        # booksum 1.10 is a realistic overround; z (insider fraction) should land
        # in a small-but-nonzero band, not degenerate to 0 or blow past ~0.3.
        from core.odds_math import solve_shin_z
        raw = [0.70, 0.25, 0.15]
        z = solve_shin_z(raw)
        self.assertGreater(z, 0.0)
        self.assertLess(z, 0.3)


class TestDevigPower(unittest.TestCase):
    def test_sums_to_one_three_way(self):
        implied = implied_probs([1.5, 4.2, 6.0])
        p = devig_power(implied)
        self.assertAlmostEqual(sum(p), 1.0, places=6)

    def test_all_in_unit_interval(self):
        implied = implied_probs([1.5, 4.2, 6.0])
        p = devig_power(implied)
        for x in p:
            self.assertGreater(x, 0.0)
            self.assertLess(x, 1.0)

    def test_two_way_market_sanity(self):
        implied = implied_probs([1.80, 2.10])
        p = devig_power(implied)
        self.assertAlmostEqual(sum(p), 1.0, places=6)
        self.assertGreater(p[0], p[1])

    def test_zero_overround_gives_k_near_one(self):
        from core.odds_math import solve_power_k
        implied = [0.5, 0.3, 0.2]  # booksum already 1
        k = solve_power_k(implied)
        self.assertAlmostEqual(k, 1.0, places=3)

    def test_k_recovered_in_sensible_range(self):
        from core.odds_math import solve_power_k
        raw = [0.70, 0.25, 0.15]  # booksum 1.10, favourite-heavy overround
        k = solve_power_k(raw)
        # sum(imp_i^k) is decreasing in k, so removing a ~10% overround (booksum
        # 1.10 at k=1) needs k modestly above 1 — not degenerate to 1 or blown out.
        self.assertGreater(k, 1.0)
        self.assertLess(k, 1.5)

    def test_favourite_longshot_correction_vs_proportional(self):
        raw = [0.70, 0.25, 0.15]
        prop = devig_proportional_from_implied(raw)
        power = devig_power(raw)
        self.assertGreater(power[0], prop[0])
        self.assertLess(power[2], prop[2])


class TestDevigByMethod(unittest.TestCase):
    """Dispatch used at the 1X2-to-lambda call site, keyed by config.DEVIG_METHOD."""

    def test_proportional_dispatch_matches_direct_call(self):
        odds = [1.5, 4.2, 6.0]
        self.assertEqual(devig_by_method(odds, "proportional"), devig_proportional(odds))

    def test_shin_dispatch_matches_direct_call(self):
        odds = [1.5, 4.2, 6.0]
        implied = implied_probs(odds)
        self.assertEqual(devig_by_method(odds, "shin"), devig_shin(implied))

    def test_power_dispatch_matches_direct_call(self):
        odds = [1.5, 4.2, 6.0]
        implied = implied_probs(odds)
        self.assertEqual(devig_by_method(odds, "power"), devig_power(implied))

    def test_unknown_method_raises(self):
        with self.assertRaises(ValueError):
            devig_by_method([1.5, 4.2, 6.0], "quantum")

    def test_default_method_is_proportional(self):
        odds = [1.5, 4.2, 6.0]
        self.assertEqual(devig_by_method(odds), devig_proportional(odds))


def devig_proportional_from_implied(implied: list) -> list:
    """Proportional normalisation applied directly to already-implied probs
    (test helper — devig_proportional takes decimal odds, not implied probs)."""
    s = sum(implied)
    return [p / s for p in implied]


if __name__ == "__main__":
    unittest.main()
