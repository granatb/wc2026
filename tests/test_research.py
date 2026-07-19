import os
import tempfile
import unittest
from unittest import mock

from core import research
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


class FindDuplicateNamesTest(unittest.TestCase):
    """find_duplicate_names(): same-name research files silently overwrite
    each other in load_entries() -- found 2026-07-19 as 4 separate Nico
    Williams files (rounds 4/6/6/7, disagreeing status) where only one was
    ever actually live, and WHICH one was down to filesystem listing order."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="evmax_research_test_")
        self.addCleanup(__import__("shutil").rmtree, self.tmp, ignore_errors=True)
        self.players_dir = os.path.join(self.tmp, "players")
        os.makedirs(self.players_dir)
        self.patcher = mock.patch.object(research, "RESEARCH_DIR", self.tmp)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def _write(self, filename, name, round_no=None):
        with open(os.path.join(self.players_dir, filename), "w", encoding="utf-8") as fh:
            fh.write(f"---\nentity: player\nname: {name}\n"
                     f"status: doubtful\nstart_prob_override: 0.3\n"
                     f"lambda_multiplier: 1.0\n"
                     + (f"round: {round_no}\n" if round_no is not None else "")
                     + "updated: 2026-07-19\n---\nbody\n")

    def test_two_files_same_name_flagged(self):
        self._write("player-r6.md", "Nico Williams", round_no=6)
        self._write("player-r7.md", "Nico Williams", round_no=7)
        self._write("other.md", "Someone Else")
        dupes = research.find_duplicate_names("players")
        self.assertEqual(set(dupes.keys()), {"Nico Williams"})
        self.assertEqual(len(dupes["Nico Williams"]), 2)

    def test_underscore_prefixed_files_excluded(self):
        self._write("player.md", "Nico Williams", round_no=8)
        self._write("_player-r6.md", "Nico Williams", round_no=6)
        dupes = research.find_duplicate_names("players")
        self.assertEqual(dupes, {})

    def test_no_duplicates_returns_empty(self):
        self._write("a.md", "Player A")
        self._write("b.md", "Player B")
        self.assertEqual(research.find_duplicate_names("players"), {})


if __name__ == "__main__":
    unittest.main()
