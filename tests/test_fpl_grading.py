"""games/fpl/grading.py — accuracy grading v1 (task 6).

Offline: hand-built snapshot rows and realized-points mappings; every MAE
below is checkable on paper.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from games.fpl import grading


def _row(name, xp, ep=None):
    row = {"name": name, "x_points": xp}
    if ep is not None:
        row["ep_next"] = ep
    return row


class TestGrade(unittest.TestCase):
    def test_mae_math_on_hand_built_rows(self):
        rows = [_row("A", 6.0, ep=5.0), _row("B", 2.0, ep=4.0)]
        realized = {"A": 8, "B": 2}
        out = grading.grade(rows, realized)
        self.assertEqual(out["n"], 2)
        self.assertAlmostEqual(out["mae_ours"], (2.0 + 0.0) / 2)
        self.assertAlmostEqual(out["mae_ep_next"], (3.0 + 2.0) / 2)
        self.assertTrue(out["beat_ep_next"])

    def test_ep_next_missing_means_none_not_zero(self):
        """GW1's frozen snapshots predate the ep_next capture — grading them
        must say 'no benchmark', never fabricate one."""
        rows = [_row("A", 6.0), _row("B", 2.0)]
        out = grading.grade(rows, {"A": 8, "B": 2})
        self.assertIsNone(out["mae_ep_next"])
        self.assertIsNone(out["beat_ep_next"])
        self.assertAlmostEqual(out["mae_ours"], 1.0)

    def test_players_without_realized_points_are_skipped_not_zeroed(self):
        rows = [_row("A", 6.0), _row("Ghost", 4.0)]
        out = grading.grade(rows, {"A": 6})
        self.assertEqual(out["n"], 1)
        self.assertAlmostEqual(out["mae_ours"], 0.0)

    def test_per_player_lines_carry_both_errors(self):
        rows = [_row("A", 6.0, ep=5.0)]
        out = grading.grade(rows, {"A": 8})
        line = out["players"][0]
        self.assertEqual(line["name"], "A")
        self.assertEqual(line["realized"], 8)
        self.assertAlmostEqual(line["err_ours"], 2.0)
        self.assertAlmostEqual(line["err_ep_next"], 3.0)


class TestSquadLine(unittest.TestCase):
    def test_projected_comes_from_the_snapshot_meta(self):
        """The squad-level line reads the FROZEN projected_total out of the
        committed envelope's squad meta — the published claim, not a rerun."""
        envelope = {"squad": {"projected_total": 65.92},
                    "entries": [
                        {"name": "A", "role": "XI", "is_captain": True},
                        {"name": "B", "role": "XI", "is_captain": False},
                        {"name": "C", "role": "Bench", "is_captain": False},
                    ]}
        line = grading.squad_line(envelope, {"A": 6, "B": 3, "C": 9})
        self.assertEqual(line["projected"], 65.92)
        # XI only, captain doubled, bench excluded: 6*2 + 3
        self.assertEqual(line["realized"], 15)


class TestStampEpNext(unittest.TestCase):
    def test_snapshot_copy_gains_ep_next_per_entry(self):
        env = {"entries": [{"name": "A", "x_points": 5.0},
                           {"name": "B", "x_points": 3.0}]}
        out = grading.stamp_ep_next(env, {"A": 4.5, "B": None})
        self.assertEqual(out["entries"][0]["ep_next"], 4.5)
        self.assertNotIn("ep_next", out["entries"][1])
        # the original envelope (the public JSON) is untouched
        self.assertNotIn("ep_next", env["entries"][0])


class TestWriter(unittest.TestCase):
    def test_accuracy_json_lands_in_the_out_dir(self):
        payload = {"gameweek": 2, "n": 30, "mae_ours": 2.1,
                   "mae_ep_next": 2.4, "beat_ep_next": True}
        with tempfile.TemporaryDirectory() as tmp:
            path = grading.write_accuracy(2, payload, out_dir=tmp)
            self.assertEqual(os.path.basename(path), "gw2.json")
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["mae_ours"], 2.1)


class TestFormatReport(unittest.TestCase):
    def test_monday_table_prints_the_verdict(self):
        payload = {"gameweek": 2, "n": 2, "mae_ours": 1.0,
                   "mae_ep_next": 2.5, "beat_ep_next": True,
                   "squads": {"our-squad": {"projected": 65.9,
                                            "realized": 58}},
                   "players": [{"name": "A", "x_points": 6.0, "ep_next": 5.0,
                                "realized": 8, "err_ours": 2.0,
                                "err_ep_next": 3.0}]}
        text = grading.format_report(payload)
        self.assertIn("beat ep_next", text)
        self.assertIn("our-squad", text)
        self.assertIn("65.9", text)

    def test_no_benchmark_says_so(self):
        payload = {"gameweek": 1, "n": 2, "mae_ours": 1.0,
                   "mae_ep_next": None, "beat_ep_next": None,
                   "squads": {}, "players": []}
        text = grading.format_report(payload)
        self.assertIn("no ep_next benchmark", text)


if __name__ == "__main__":
    unittest.main()
