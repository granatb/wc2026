"""Growth measurement: peak-over-peak snapshots."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from core.growth import snapshot


class TestSnapshot(unittest.TestCase):
    def test_round_trips(self):
        payload = {"cloudflare_total": 690, "cloudflare_paths": 2}
        with tempfile.TemporaryDirectory() as tmp:
            path = snapshot.write(1, payload, directory=tmp)
            self.assertTrue(os.path.exists(path))
            record = snapshot.read(1, directory=tmp)
        self.assertEqual(record["gameweek"], 1)
        self.assertEqual(record["data"], payload)
        self.assertIn("written_at", record)

    def test_read_of_a_missing_gameweek_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(snapshot.read(7, directory=tmp))

    def test_delta_against_the_previous_snapshot(self):
        out = snapshot.delta({"total": 150}, {"total": 100})
        self.assertEqual(out["total"]["current"], 150)
        self.assertEqual(out["total"]["previous"], 100)
        self.assertEqual(out["total"]["delta"], 50)
        self.assertEqual(out["total"]["pct"], 50.0)

    def test_delta_with_no_previous_snapshot_is_none_not_zero(self):
        """The first run has no baseline. Reporting 0% growth would be a lie; the
        report must say 'no previous peak' instead."""
        self.assertIsNone(snapshot.delta({"total": 150}, None))

    def test_delta_pct_is_none_when_the_baseline_was_zero(self):
        """Growth from nothing has no percentage; 0 -> 40 must not divide."""
        out = snapshot.delta({"total": 40}, {"total": 0})
        self.assertEqual(out["total"]["delta"], 40)
        self.assertIsNone(out["total"]["pct"])

    def test_previous_is_the_highest_gameweek_below_this_one(self):
        """Not the newest file on disk, and not filename order -- gw10 must compare
        against gw9, and gw2 against gw1 even if gw10 was written later."""
        with tempfile.TemporaryDirectory() as tmp:
            snapshot.write(1, {"total": 10}, directory=tmp)
            snapshot.write(2, {"total": 20}, directory=tmp)
            snapshot.write(9, {"total": 90}, directory=tmp)
            snapshot.write(10, {"total": 100}, directory=tmp)
            self.assertEqual(snapshot.previous(10, directory=tmp)["gameweek"], 9)
            self.assertEqual(snapshot.previous(2, directory=tmp)["gameweek"], 1)
            # "gw10" sorts before "gw2" as a string; 10 must not be read as
            # the highest gameweek below 9.
            self.assertEqual(snapshot.previous(9, directory=tmp)["gameweek"], 2)
            self.assertIsNone(snapshot.previous(1, directory=tmp))

    def test_a_corrupt_snapshot_is_skipped_not_raised(self):
        """Diagnostics must never be the reason a report dies."""
        with tempfile.TemporaryDirectory() as tmp:
            snapshot.write(1, {"total": 10}, directory=tmp)
            with open(os.path.join(tmp, "gw3.json"), "w", encoding="utf-8") as fh:
                fh.write("{not json at all")
            self.assertIsNone(snapshot.read(3, directory=tmp))
            self.assertEqual(snapshot.previous(4, directory=tmp)["gameweek"], 1)

    def test_a_missing_directory_is_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "never-created")
            self.assertIsNone(snapshot.read(1, directory=missing))
            self.assertIsNone(snapshot.previous(5, directory=missing))

    def test_written_file_is_readable_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = snapshot.write(4, {"total": 1}, directory=tmp)
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["gameweek"], 4)


if __name__ == "__main__":
    unittest.main()
