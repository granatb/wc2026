import unittest

from core.research import parse_frontmatter, ResearchEntry


class TestResearch(unittest.TestCase):
    def test_parse_frontmatter_scalars_and_list(self):
        text = (
            "---\n"
            "entity: player\n"
            "name: Erling Haaland\n"
            "status: rotation_risk\n"
            "start_prob_override: null\n"
            "lambda_multiplier: 1.4\n"
            "sources:\n"
            "  - https://a.com\n"
            "  - https://b.com\n"
            "updated: 2026-06-18\n"
            "---\n"
            "prose body here\n"
        )
        meta, body = parse_frontmatter(text)
        self.assertEqual(meta["name"], "Erling Haaland")
        self.assertEqual(meta["lambda_multiplier"], 1.4)
        self.assertIsNone(meta["start_prob_override"])
        self.assertEqual(meta["sources"], ["https://a.com", "https://b.com"])
        self.assertIn("prose body", body)

    def test_hard_out_zeroes_regardless_of_w(self):
        e = ResearchEntry(name="X", status="out", lambda_multiplier=2.0)
        rate, start = e.adjust(base_rate=0.8, base_start=0.9, w=0.99)
        self.assertEqual((rate, start), (0.0, 0.0))

    def test_soft_multiplier_blends_with_w(self):
        e = ResearchEntry(name="X", status="rotation_risk", lambda_multiplier=1.4)
        rate, start = e.adjust(base_rate=0.5, base_start=0.8, w=0.5)
        self.assertAlmostEqual(rate, 0.5 * (1 + 0.5 * 0.4))  # 0.6
        self.assertEqual(start, 0.8)

    def test_start_prob_override_is_absolute(self):
        e = ResearchEntry(name="X", start_prob_override=0.3, lambda_multiplier=1.0)
        rate, start = e.adjust(base_rate=0.5, base_start=0.9, w=0.0)
        self.assertEqual(start, 0.3)

    def test_w_zero_ignores_soft_multiplier(self):
        e = ResearchEntry(name="X", lambda_multiplier=5.0)
        rate, _ = e.adjust(base_rate=0.5, base_start=0.9, w=0.0)
        self.assertEqual(rate, 0.5)


if __name__ == "__main__":
    unittest.main()
