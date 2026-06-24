import unittest

from core.blend import blend_lambda, blend_rate, apply_status


class TestBlend(unittest.TestCase):
    def test_w_zero_is_pure_odds(self):
        self.assertEqual(blend_lambda(1.5, multiplier=2.0, w=0.0), 1.5)
        self.assertEqual(blend_rate(0.4, expert=0.9, w=0.0), 0.4)

    def test_w_one_is_full_expert(self):
        self.assertEqual(blend_lambda(1.5, multiplier=2.0, w=1.0), 3.0)
        self.assertEqual(blend_rate(0.4, expert=0.9, w=1.0), 0.9)

    def test_partial_blend_is_linear(self):
        self.assertAlmostEqual(blend_lambda(2.0, multiplier=1.5, w=0.5), 2.5)
        self.assertAlmostEqual(blend_rate(0.2, expert=0.6, w=0.25), 0.75 * 0.2 + 0.25 * 0.6)

    def test_hard_out_zeroes_regardless_of_w(self):
        rate, start = apply_status("out", base_rate=0.8, base_start=0.9, w=0.99)
        self.assertEqual(rate, 0.0)
        self.assertEqual(start, 0.0)

    def test_soft_status_passes_through(self):
        rate, start = apply_status("rotation_risk", base_rate=0.8, base_start=0.9, w=0.5)
        self.assertEqual(rate, 0.8)
        self.assertEqual(start, 0.9)


if __name__ == "__main__":
    unittest.main()
