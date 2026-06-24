import unittest

from core.engine_events import percentile


class TestPercentile(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(percentile([], 0.9), 0.0)
        self.assertEqual(percentile([5], 0.9), 5)
        self.assertAlmostEqual(percentile([0, 1, 2, 3, 4], 0.5), 2.0)
        self.assertAlmostEqual(percentile([0, 10], 0.85), 8.5)

    def test_ceiling_favours_variance(self):
        # Same mean (1.0), different variance. At the 85th percentile the
        # high-variance player should rank higher — the YOLO objective.
        low_var = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
        high_var = [0, 0, 0, 0, 0, 0, 0, 0, 5, 5]
        self.assertEqual(sum(low_var), sum(high_var))  # equal mean
        self.assertGreater(percentile(high_var, 0.85), percentile(low_var, 0.85))


if __name__ == "__main__":
    unittest.main()
