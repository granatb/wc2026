"""core/fpl_diff.py — the feed churn detector (phase 5 task 1).

Offline: synthetic bootstrap payloads shaped like the live feed run through the
real snapshot/diff path. No network — the CLI's fetch is injected.
"""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from core import fpl_api, fpl_diff


def _boot(elements):
    return {
        "teams": [{"id": 1, "short_name": "AVL"},
                  {"id": 2, "short_name": "ARS"},
                  {"id": 3, "short_name": "NFO"}],
        "elements": elements,
    }


def _el(pid, web_name, team=1, status="a", now_cost=90, sel="10.0",
        tin=0, tout=0):
    return {"id": pid, "web_name": web_name, "team": team, "status": status,
            "now_cost": now_cost, "selected_by_percent": sel,
            "transfers_in_event": tin, "transfers_out_event": tout}


class TestSnapshot(unittest.TestCase):
    def test_compact_projection_keyed_by_element_id(self):
        snap = fpl_diff.snapshot(_boot([_el(5, "Sangaré", team=3,
                                            now_cost=50, sel="1.2",
                                            tin=100, tout=200)]))
        self.assertIn("taken_at", snap)
        row = snap["5"]
        self.assertEqual(row["web_name"], "Sangaré")
        self.assertEqual(row["team_short"], "NFO")
        self.assertEqual(row["status"], "a")
        self.assertEqual(row["price"], 5.0)
        self.assertEqual(row["selected_pct"], 1.2)
        self.assertEqual(row["tin"], 100)
        self.assertEqual(row["tout"], 200)


class TestDiff(unittest.TestCase):
    def test_first_run_returns_the_flag_only(self):
        new = fpl_diff.snapshot(_boot([_el(1, "Watkins")]))
        self.assertEqual(fpl_diff.diff(None, new), {"first_run": True})

    def test_rename_is_detected_with_old_and_new(self):
        """The wrong-Sangaré shape: same element id, new web_name."""
        old = fpl_diff.snapshot(_boot([_el(5, "Sangaré", team=3)]))
        new = fpl_diff.snapshot(_boot([_el(5, "I.Sangaré", team=3)]))
        d = fpl_diff.diff(old, new)
        self.assertEqual(len(d["renamed"]), 1)
        entry = d["renamed"][0]
        self.assertEqual(entry["old"], "Sangaré")
        self.assertEqual(entry["new"], "I.Sangaré")
        self.assertEqual(d["arrived"], [])
        self.assertEqual(d["departed"], [])

    def test_club_move_is_detected(self):
        """The Konsa shape: same id, same name, new club."""
        old = fpl_diff.snapshot(_boot([_el(7, "Konsa", team=1)]))
        new = fpl_diff.snapshot(_boot([_el(7, "Konsa", team=2)]))
        d = fpl_diff.diff(old, new)
        self.assertEqual(len(d["moved"]), 1)
        self.assertEqual(d["moved"][0]["old"], "AVL")
        self.assertEqual(d["moved"][0]["new"], "ARS")
        self.assertEqual(d["moved"][0]["name"], "Konsa")

    def test_arrival_and_departure(self):
        """The M.Sangaré shape: an id only the new feed carries."""
        old = fpl_diff.snapshot(_boot([_el(5, "Sangaré", team=3)]))
        new = fpl_diff.snapshot(_boot([_el(5, "Sangaré", team=3),
                                       _el(999, "M.Sangaré", team=2)]))
        d = fpl_diff.diff(old, new)
        self.assertEqual([a["name"] for a in d["arrived"]], ["M.Sangaré"])
        back = fpl_diff.diff(new, old)
        self.assertEqual([a["name"] for a in back["departed"]], ["M.Sangaré"])

    def test_status_change_carries_old_and_new(self):
        old = fpl_diff.snapshot(_boot([_el(3, "Isak", status="a")]))
        new = fpl_diff.snapshot(_boot([_el(3, "Isak", status="i")]))
        d = fpl_diff.diff(old, new)
        self.assertEqual(len(d["status_changed"]), 1)
        self.assertEqual(d["status_changed"][0]["old"], "a")
        self.assertEqual(d["status_changed"][0]["new"], "i")

    def test_price_change_is_detected(self):
        old = fpl_diff.snapshot(_boot([_el(4, "Haaland", now_cost=155)]))
        new = fpl_diff.snapshot(_boot([_el(4, "Haaland", now_cost=156)]))
        d = fpl_diff.diff(old, new)
        self.assertEqual(len(d["price_changed"]), 1)
        self.assertEqual(d["price_changed"][0]["old"], 15.5)
        self.assertEqual(d["price_changed"][0]["new"], 15.6)

    def test_outflow_spike_catches_a_watkins_shaped_exodus(self):
        """One player with 50k transfers out among 400 at ~2k must flag, z > 3."""
        elements = [_el(i, f"P{i}", tout=2_000) for i in range(1, 401)]
        elements.append(_el(500, "Watkins", tout=50_000))
        d = fpl_diff.diff(fpl_diff.snapshot(_boot(elements[:1])),
                          fpl_diff.snapshot(_boot(elements)))
        spikes = d["outflow_spikes"]
        self.assertEqual([s["name"] for s in spikes], ["Watkins"])
        self.assertGreater(spikes[0]["z"], 3.0)
        self.assertEqual(spikes[0]["tout"], 50_000)

    def test_no_spike_in_a_flat_population(self):
        elements = [_el(i, f"P{i}", tout=2_000 + i) for i in range(1, 401)]
        d = fpl_diff.diff(fpl_diff.snapshot(_boot(elements)),
                          fpl_diff.snapshot(_boot(elements)))
        self.assertEqual(d["outflow_spikes"], [])


class TestPersistence(unittest.TestCase):
    def test_snapshot_round_trips_through_the_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(fpl_api, "DATA_DIR", tmp):
                snap = fpl_diff.snapshot(_boot([_el(1, "Watkins", tout=7)]))
                fpl_diff.store(snap)
                self.assertTrue(os.path.exists(
                    os.path.join(tmp, "feed_snapshot.json")))
                self.assertEqual(fpl_diff.load_previous(), snap)

    def test_load_previous_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(fpl_api, "DATA_DIR", tmp):
                self.assertIsNone(fpl_diff.load_previous())


class TestCli(unittest.TestCase):
    def _run(self, raw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = fpl_diff.main(fetch=lambda: raw)
        return code, out.getvalue()

    def test_first_run_is_loud_and_stores_the_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(fpl_api, "DATA_DIR", tmp):
                code, text = self._run(_boot([_el(1, "Watkins")]))
                self.assertEqual(code, 0)
                self.assertIn("FIRST RUN", text)
                self.assertIsNotNone(fpl_diff.load_previous())

    def test_second_run_reports_the_churn_and_rotates_the_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(fpl_api, "DATA_DIR", tmp):
                self._run(_boot([_el(5, "Sangaré", team=3)]))
                code, text = self._run(_boot([_el(5, "I.Sangaré", team=3),
                                              _el(9, "M.Sangaré", team=2)]))
                self.assertEqual(code, 0)
                self.assertIn("Sangaré → I.Sangaré", text)
                self.assertIn("M.Sangaré", text)
                # the new snapshot replaced the old one
                stored = fpl_diff.load_previous()
                self.assertIn("9", stored)

    def test_status_changes_point_the_operator_at_the_feed(self):
        """news is NOT in the snapshot; the report says where to look."""
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(fpl_api, "DATA_DIR", tmp):
                self._run(_boot([_el(3, "Isak", status="a")]))
                _code, text = self._run(_boot([_el(3, "Isak", status="i")]))
                self.assertIn("check feed", text)


if __name__ == "__main__":
    unittest.main()
