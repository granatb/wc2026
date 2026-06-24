import os
import tempfile
import unittest

from evmax import writer

ENTRIES = [{"rank": 1, "name": "Kane", "team": "England", "position": "FWD", "x_points": 9.16,
            "captain_ev": 18.31, "ceiling": 13.55, "price": 10.5, "value": 0.872,
            "ownership_pct": 38.6}]


class WriterTest(unittest.TestCase):
    def test_template_fallback_is_grounded_and_safe(self):
        p = writer.article_prose("captains", 3, ENTRIES, ["captain_ev", "x_points", "ownership_pct"],
                                 cache_dir="/nonexistent", use_llm=False)
        self.assertEqual(p["source"], "template")
        self.assertIn("Kane", p["headline"] + p["standfirst"] + p["body_html"])
        self.assertIn("18.3", p["body_html"])               # real number woven in
        self.assertTrue(p["bottom_line"])

    def test_cache_tier_wins_when_present(self):
        d = tempfile.mkdtemp()
        os.makedirs(f"{d}/round-3", exist_ok=True)
        open(f"{d}/round-3/captains.md", "w").write(
            "# Back Kane\n\n> Safe armband.\n\nKane leads at 18.31.\n\n**Bottom line:** hold Kane.\n")
        p = writer.article_prose("captains", 3, ENTRIES, ["captain_ev"], cache_dir=d, use_llm=False)
        self.assertEqual(p["source"], "cache")
        self.assertEqual(p["headline"], "Back Kane")
        self.assertIn("Bottom line", p["body_html"] + p["bottom_line"])

    def test_no_api_key_falls_to_template_cleanly(self):
        """With use_llm=True but ANTHROPIC_API_KEY unset, fall through to template (no crash)."""
        saved = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            p = writer.article_prose("captains", 3, ENTRIES, ["captain_ev", "x_points"],
                                     cache_dir="/nonexistent", use_llm=True)
            self.assertEqual(p["source"], "template")
            self.assertTrue(p["headline"])
            self.assertTrue(p["bottom_line"])
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved


if __name__ == "__main__":
    unittest.main()
