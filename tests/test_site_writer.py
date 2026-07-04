import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from evmax import writer

ENTRIES = [{"rank": 1, "name": "Kane", "team": "England", "position": "FWD", "x_points": 9.16,
            "captain_ev": 18.31, "ceiling": 13.55, "price": 10.5, "value": 0.872,
            "ownership_pct": 38.6}]


class WriterTest(unittest.TestCase):
    def test_template_fallback_is_grounded_and_safe(self):
        p = writer.article_prose("captains", 3, ENTRIES, ["captain_ev", "x_points", "ownership_pct"],
                                 cache_dir="/nonexistent", use_llm=False, subject="Kane")
        self.assertEqual(p["source"], "template")
        self.assertIn("Kane", p["headline"] + p["standfirst"] + p["body_html"])
        self.assertIn("18.31", p["body_html"])               # real number woven in (2dp)
        self.assertTrue(p["bottom_line"])

    def test_template_round_no_in_headline(self):
        """round_no must appear in the headline, not render as blank."""
        p = writer.article_prose("captains", 7, ENTRIES, ["captain_ev"],
                                 cache_dir="/nonexistent", use_llm=False, subject="Kane")
        self.assertIn("Round 7", p["headline"])

    def test_subject_appears_in_prose(self):
        """When subject is set, the subject name should appear in headline/body."""
        p = writer.article_prose("captains", 3, ENTRIES, ["captain_ev"],
                                 cache_dir="/nonexistent", use_llm=False, subject="Kane")
        combined = p["headline"] + p["standfirst"] + p["body_html"]
        self.assertIn("Kane", combined)

    def test_best_xi_is_team_framed(self):
        """best-xi with subject=None should not centre on a single player in headline."""
        entries = [
            {"rank": i+1, "name": f"Player{i}", "team": "ENG", "position": pos,
             "x_points": 5.0 - i*0.1, "captain_ev": 10.0, "ceiling": 8.0,
             "price": 7.0, "value": 0.7, "ownership_pct": 20.0}
            for i, pos in enumerate(
                ["GK", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD"]
            )
        ]
        p = writer.article_prose("best-xi", 3, entries, ["x_points"],
                                 cache_dir="/nonexistent", use_llm=False, subject=None)
        self.assertEqual(p["source"], "template")
        # Team-framed: headline should mention "XI" or "Round", not a single player name
        self.assertIn("XI", p["headline"])

    def test_wildcard_is_team_framed_and_covers_budget_and_bench(self):
        """wildcard with subject=None should be squad-framed: cost, XI xPts,
        formation, bench philosophy, priciest picks and the best value pick."""
        xi = [
            {"rank": i + 1, "name": f"XI{i}", "team": "BRA", "position": pos,
             "x_points": 8.0 - i * 0.3, "captain_ev": 16.0, "ceiling": 10.0,
             "price": 10.0 - i * 0.5, "value": round((8.0 - i * 0.3) / (10.0 - i * 0.5), 2),
             "ownership_pct": 30.0, "role": "XI"}
            for i, pos in enumerate(
                ["GK", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD"])
        ]
        bench = [
            {"rank": 12 + i, "name": f"Bench{i}", "team": "BRA", "position": pos,
             "x_points": 2.0, "captain_ev": 4.0, "ceiling": 2.5, "price": 4.0,
             "value": 0.5, "ownership_pct": 3.0, "role": "Bench"}
            for i, pos in enumerate(["GK", "DEF", "DEF", "DEF"])
        ]
        entries = xi + bench
        p = writer.article_prose("wildcard", 5, entries, ["x_points", "price"],
                                 cache_dir="/nonexistent", use_llm=False, subject=None)
        self.assertEqual(p["source"], "template")
        combined = p["headline"] + p["standfirst"] + p["body_html"] + p["bottom_line"]
        # Team-framed: no bench filler should be the headline subject
        self.assertNotIn("Bench0", p["headline"])
        self.assertIn("Wildcard", p["headline"])
        # Squad totals show up somewhere in the prose
        self.assertIn("100.0m", combined)  # budget mentioned
        # The priciest XI pick (XI0, price 10.0) should be named
        self.assertIn("XI0", combined)
        # Bench philosophy is mentioned without overselling bench numbers
        self.assertIn("Bench0", combined)

    def test_defenders_template(self):
        """defenders template should work and include subject in headline."""
        entries = [
            {"rank": 1, "name": "Trippier", "team": "ENG", "position": "DEF",
             "x_points": 6.0, "captain_ev": 12.0, "ceiling": 9.0,
             "price": 6.5, "value": 0.92, "ownership_pct": 14.0},
            {"rank": 2, "name": "Mazraoui", "team": "MAR", "position": "DEF",
             "x_points": 5.5, "captain_ev": 11.0, "ceiling": 8.0,
             "price": 6.0, "value": 0.92, "ownership_pct": 8.0},
        ]
        p = writer.article_prose("defenders", 3, entries, ["x_points"],
                                 cache_dir="/nonexistent", use_llm=False, subject="Trippier")
        self.assertEqual(p["source"], "template")
        self.assertIn("Trippier", p["headline"])

    def test_risky_template(self):
        """risky template should mention ceiling and subject."""
        entries = [
            {"rank": 1, "name": "Diallo", "team": "CIV", "position": "FWD",
             "x_points": 5.0, "captain_ev": 10.0, "ceiling": 18.0,
             "price": 5.5, "value": 0.91, "ownership_pct": 1.2},
        ]
        p = writer.article_prose("risky", 3, entries, ["ceiling"],
                                 cache_dir="/nonexistent", use_llm=False, subject="Diallo")
        self.assertEqual(p["source"], "template")
        self.assertIn("Diallo", p["headline"])
        self.assertIn("18.00", p["body_html"])

    def test_cache_tier_wins_when_present(self):
        d = tempfile.mkdtemp()
        os.makedirs(f"{d}/round-3", exist_ok=True)
        with open(f"{d}/round-3/captains.md", "w") as fh:
            fh.write(
                "# Back Kane\n\n> Safe armband.\n\nKane leads at 18.31.\n\n**Bottom line:** hold Kane.\n"
            )
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

    # -----------------------------------------------------------------------
    # Grounding validation tests — network-free via mock
    # -----------------------------------------------------------------------

    def _make_fake_message(self, payload: dict) -> MagicMock:
        """Wrap a dict as a fake anthropic Message object."""
        msg = MagicMock()
        msg.content = [MagicMock()]
        msg.content[0].text = json.dumps(payload)
        return msg

    def test_llm_fabricated_number_falls_to_template(self):
        """LLM output containing a number not in entries must be rejected → source='template'."""
        fabricated_payload = {
            "headline": "Kane leads in Round 3",
            "standfirst": "Kane tops captain EV at 99.99 pts",   # 99.99 not in entries
            "body_markdown": "Kane has a captain EV of 99.99.",
            "bottom_line": "Back Kane — 99.99 captain EV.",
        }
        fake_msg = self._make_fake_message(fabricated_payload)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake-key"}):
            with patch("evmax.writer._anthropic") as mock_anthropic:
                mock_anthropic.Anthropic.return_value.messages.create.return_value = fake_msg
                # _ANTHROPIC_AVAILABLE must be True for the LLM path to run
                with patch.object(writer, "_ANTHROPIC_AVAILABLE", True):
                    with patch("evmax.prompts.build_prompt", return_value="prompt"):
                        p = writer.article_prose(
                            "captains", 3, ENTRIES,
                            ["captain_ev", "x_points"],
                            cache_dir="/nonexistent",
                            use_llm=True,
                            subject="Kane",
                        )
        self.assertEqual(p["source"], "template",
                         "Fabricated number should cause grounding rejection")

    def test_llm_grounded_output_accepted(self):
        """LLM output using only real numbers and real names must be accepted → source='llm'."""
        # All numbers here are produced by the canonical formatters from ENTRIES:
        # x_points=9.16 → "9.16", captain_ev=18.31 → "18.31", ownership=38.6 → "38.6"
        # ceiling=13.55 → "13.55", price=10.5 → "10.5"
        grounded_payload = {
            "headline": "Kane leads the armband race in Round 3",
            "standfirst": "Kane tops captain EV at 18.31 pts.",
            "body_markdown": (
                "Kane is the standout captain this round, "
                "posting a captain EV of 18.31 and xPts of 9.16. "
                "Ownership sits at 38.6%, ceiling 13.55."
            ),
            "bottom_line": "Back Kane — 18.31 captain EV is the best available.",
        }
        fake_msg = self._make_fake_message(grounded_payload)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake-key"}):
            with patch("evmax.writer._anthropic") as mock_anthropic:
                mock_anthropic.Anthropic.return_value.messages.create.return_value = fake_msg
                with patch.object(writer, "_ANTHROPIC_AVAILABLE", True):
                    with patch("evmax.prompts.build_prompt", return_value="prompt"):
                        # Redirect cache writes to a temp dir so they don't fail
                        with tempfile.TemporaryDirectory() as tmpdir:
                            p = writer.article_prose(
                                "captains", 3, ENTRIES,
                                ["captain_ev", "x_points"],
                                cache_dir=tmpdir,
                                use_llm=True,
                                subject="Kane",
                            )
        self.assertEqual(p["source"], "llm",
                         "Fully grounded LLM output should be accepted")
        self.assertIn("Kane", p["headline"])


TRANSFER_ENTRIES = [
    {"rank": 1, "name": "Amad Diallo", "team": "Ivory Coast", "position": "FWD",
     "x_points": 8.55, "vor": 2.5, "p_advance": 15.0, "priority_score": 2.875,
     "price": 5.9, "ownership_pct": 1.3},
    {"rank": 2, "name": "Harry Kane", "team": "England", "position": "FWD",
     "x_points": 9.16, "vor": 1.8, "p_advance": 90.0, "priority_score": 3.42,
     "price": 10.5, "ownership_pct": 38.6},
]


class TransferTemplateTest(unittest.TestCase):
    def test_template_mentions_vor_and_advancement_risk(self):
        p = writer.article_prose("transfers", 5, TRANSFER_ENTRIES, ["priority_score", "vor"],
                                 cache_dir="/nonexistent", use_llm=False, subject="Amad Diallo")
        self.assertEqual(p["source"], "template")
        self.assertIn("Amad Diallo", p["headline"])
        # the +2.50 VOR figure and the 15.0% advance probability must appear grounded
        self.assertIn("2.50", p["body_html"] + p["standfirst"] + p["bottom_line"])
        self.assertIn("15.0%", p["body_html"] + p["standfirst"] + p["bottom_line"])

    def test_template_omits_advancement_mention_when_p_advance_is_neutral_default(self):
        """A group-round transfer entry (p_advance=100, the no-discount default)
        should not falsely claim a 'chance of advancing' caveat."""
        entries = [{"rank": 1, "name": "Someone", "team": "Spain", "position": "MID",
                    "x_points": 6.0, "vor": 1.0, "p_advance": 100.0, "priority_score": 2.0,
                    "price": 7.0, "ownership_pct": 20.0}]
        p = writer.article_prose("transfers", 3, entries, ["priority_score", "vor"],
                                 cache_dir="/nonexistent", use_llm=False, subject="Someone")
        self.assertNotIn("chance of advancing", p["standfirst"])


if __name__ == "__main__":
    unittest.main()
