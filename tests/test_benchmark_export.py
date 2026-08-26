"""Phase 2B task 3 — scripts/benchmark_export.py (spec P4).

The submission artifact for a third-party xPts benchmark. Everything here runs
against SYNTHETIC snapshot dirs in tempfiles: the committed snapshots under
evmax/assets/projections/ are frozen published claims and no test may depend
on (or touch) them.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import os
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_spec = importlib.util.spec_from_file_location(
    "benchmark_export", os.path.join(_ROOT, "scripts", "benchmark_export.py"))
benchmark_export = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(benchmark_export)


def _envelope(gameweek, entries):
    return {"competition": "fantasy_premier_league", "gameweek": gameweek,
            "entries": entries}


def _snapshot(tmp, gameweek, files):
    """Write a synthetic frozen-snapshot dir; return its ROOT (the dir that
    holds fpl-gw{N}/), which is what the exporter takes."""
    snap = os.path.join(tmp, f"fpl-gw{gameweek}")
    os.makedirs(snap, exist_ok=True)
    for slug, entries in files.items():
        with open(os.path.join(snap, f"{slug}.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(_envelope(gameweek, entries), fh)
    return tmp


class TestCollectRows(unittest.TestCase):
    def test_rows_are_the_union_of_every_snapshot_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _snapshot(tmp, 3, {
                "captains": [{"name": "A", "x_points": 8.5}],
                "defcon": [{"name": "B", "x_points": 4.25}]})
            rows = benchmark_export.collect_rows(3, root)
        self.assertEqual({r["name"] for r in rows}, {"A", "B"})

    def test_a_player_in_two_articles_appears_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _snapshot(tmp, 3, {
                "captains": [{"name": "A", "x_points": 8.5}],
                "defcon": [{"name": "A", "x_points": 8.5},
                           {"name": "B", "x_points": 4.0}]})
            rows = benchmark_export.collect_rows(3, root)
        self.assertEqual(len(rows), 2)

    def test_entries_without_a_projection_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _snapshot(tmp, 3, {
                "ticker": [{"name": "NoNumber"},
                           {"name": "A", "x_points": 8.5}]})
            rows = benchmark_export.collect_rows(3, root)
        self.assertEqual([r["name"] for r in rows], ["A"])

    def test_rows_sort_by_predicted_points_descending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _snapshot(tmp, 3, {
                "captains": [{"name": "Low", "x_points": 2.0},
                             {"name": "High", "x_points": 9.0}]})
            rows = benchmark_export.collect_rows(3, root)
        self.assertEqual([r["name"] for r in rows], ["High", "Low"])


class TestRefusesWithoutAFrozenSnapshot(unittest.TestCase):
    """The whole point of the artifact is that it comes from the FROZEN
    pre-deadline snapshot. No snapshot means no submission — never a rerun."""

    def test_a_missing_snapshot_dir_is_a_hard_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                benchmark_export.collect_rows(9, tmp)
        msg = str(ctx.exception).lower()
        self.assertIn("gameweek 9", msg)
        self.assertIn("snapshot", msg)

    def test_an_empty_snapshot_dir_is_a_hard_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "fpl-gw9"))
            with self.assertRaises(SystemExit):
                benchmark_export.collect_rows(9, tmp)

    def test_the_message_never_suggests_re_simulating(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                benchmark_export.collect_rows(9, tmp)
        self.assertNotIn("rerun", str(ctx.exception).lower())


class TestCsv(unittest.TestCase):
    _ROWS = [{"name": "A", "x_points": 8.5}, {"name": "B", "x_points": 4.25}]

    def test_header_is_the_common_submission_shape(self):
        text = benchmark_export.to_csv(self._ROWS, 3, ids={"A": 11, "B": 22})
        parsed = list(csv.reader(io.StringIO(text)))
        self.assertEqual(parsed[0], ["player_id", "player_name", "gameweek",
                                     "predicted_points"])
        self.assertEqual(len(parsed) - 1, 2)

    def test_rows_carry_the_id_the_gameweek_and_the_projection(self):
        text = benchmark_export.to_csv(self._ROWS, 3, ids={"A": 11, "B": 22})
        rec = list(csv.DictReader(io.StringIO(text)))[0]
        self.assertEqual(rec["player_id"], "11")
        self.assertEqual(rec["player_name"], "A")
        self.assertEqual(rec["gameweek"], "3")
        self.assertEqual(rec["predicted_points"], "8.5")

    def test_an_unmatched_name_gets_an_empty_id_never_a_guess(self):
        text = benchmark_export.to_csv(self._ROWS, 3, ids={"A": 11})
        rec = list(csv.DictReader(io.StringIO(text)))[1]
        self.assertEqual(rec["player_name"], "B")
        self.assertEqual(rec["player_id"], "")

    def test_a_name_with_a_comma_is_quoted(self):
        text = benchmark_export.to_csv([{"name": "Smith, Jr.",
                                         "x_points": 3.0}], 3, ids={})
        self.assertIn('"Smith, Jr."', text)


class TestExport(unittest.TestCase):
    def test_export_writes_the_named_file_and_returns_its_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _snapshot(tmp, 4, {
                "captains": [{"name": "A", "x_points": 8.5},
                             {"name": "B", "x_points": 4.0}]})
            out_dir = os.path.join(tmp, "benchmark")
            path = benchmark_export.export(4, snapshot_root=root,
                                           out_dir=out_dir,
                                           ids={"A": 11, "B": 22})
            self.assertEqual(os.path.basename(path), "gw4-evmax.csv")
            with open(path, encoding="utf-8", newline="") as fh:
                text = fh.read()
        parsed = list(csv.reader(io.StringIO(text)))
        self.assertEqual(parsed[0][0], "player_id")
        self.assertEqual(len(parsed) - 1, 2)

    def test_export_refuses_a_gameweek_with_no_frozen_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                benchmark_export.export(9, snapshot_root=tmp,
                                        out_dir=os.path.join(tmp, "b"),
                                        ids={})
            self.assertFalse(os.path.exists(os.path.join(tmp, "b")))


if __name__ == "__main__":
    unittest.main()


class TestAliasResolution(unittest.TestCase):
    """Frozen snapshots name players as the feed did that week; the feed renames
    on transfer collisions ("Sangaré" -> "I.Sangaré" when M.Sangaré joined).
    The exporter reuses the published states' alias map instead of emitting an
    empty player_id for a name it could otherwise resolve."""

    def test_aliased_snapshot_name_resolves_to_the_current_element_id(self):
        import json as _json
        import tempfile as _tempfile
        from unittest import mock as _mock
        boot = {"elements": [
            {"id": 501, "web_name": "I.Sangaré", "team": 1, "element_type": 3,
             "first_name": "Ibrahim", "second_name": "Sangaré", "now_cost": 50,
             "selected_by_percent": "1.0", "status": "a", "news": "",
             "minutes": 900, "total_points": 40, "bps": 200},
            {"id": 502, "web_name": "M.Sangaré", "team": 2, "element_type": 3,
             "first_name": "Mamadou", "second_name": "Sangaré", "now_cost": 55,
             "selected_by_percent": "4.5", "status": "a", "news": "",
             "minutes": 900, "total_points": 40, "bps": 200}],
            "teams": [{"id": 1, "short_name": "NFO"}, {"id": 2, "short_name": "BRE"}],
            "element_types": [{"id": 3, "singular_name_short": "MID"}]}
        with _tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "games", "fpl")
            os.makedirs(state)
            with open(os.path.join(state, "state.json"), "w") as fh:
                _json.dump({"aliases": {}}, fh)
            with open(os.path.join(state, "state_consensus.json"), "w") as fh:
                _json.dump({"aliases": {"Sangaré": "I.Sangaré"}}, fh)
            from core import fpl_api as _api
            with _mock.patch.object(benchmark_export, "_HERE", tmp), \
                 _mock.patch.object(_api, "read_cache", return_value=boot):
                ids = benchmark_export.element_ids(1)
        self.assertEqual(ids["Sangaré"], 501)
        self.assertEqual(ids["I.Sangaré"], 501)
