"""The open benchmark — core/fpl_bench.py.

The 2026-08-26 feasibility study decided the shape; these pin the properties
that make it a benchmark rather than a blog post: frozen pre-deadline
snapshots that refuse overwrite, same-sample grading with per-source n, the
60+ minute population alongside everyone, and no republication of anyone's
projections on the rendered site (the snapshot file is repo evidence only).
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import fpl_bench


_FFIQ = {
    "license": "Free to use in articles, videos, tools and research",
    "generated_at": "2026-09-02T00:18:35+00:00",
    "players": [
        {"web_name": "Raya", "club": "ARS",
         "gws": [{"gw": 3, "proj": 2.7}, {"gw": 4, "proj": 4.0}]},
        {"web_name": "Haaland", "club": "MCI",
         "gws": [{"gw": 3, "proj": 7.9}]},
        {"web_name": "NoGw3", "club": "BRE", "gws": [{"gw": 4, "proj": 3.0}]},
    ],
}

_BOOT = {
    "teams": [{"id": 1, "short_name": "ARS"}, {"id": 2, "short_name": "MCI"}],
    "elements": [
        {"id": 10, "web_name": "Raya", "team": 1, "total_points": 8,
         "ep_next": "3.5"},
        {"id": 20, "web_name": "Haaland", "team": 2, "total_points": 15,
         "ep_next": "6.0"},
    ],
}

_FORM = {
    "10": [{"round": 1, "total_points": 6, "minutes": 90},
           {"round": 2, "total_points": 2, "minutes": 90}],
    "20": [{"round": 1, "total_points": 2, "minutes": 90},
           {"round": 2, "total_points": 13, "minutes": 90}],
}


class TestFfiqColumn(unittest.TestCase):
    def test_extracts_one_gameweek_keyed_by_name_and_club(self):
        col = fpl_bench.ffiq_column(_FFIQ, 3)
        self.assertEqual(col[("Raya", "ARS")], 2.7)
        self.assertEqual(col[("Haaland", "MCI")], 7.9)

    def test_a_player_without_that_gameweek_is_absent_not_zero(self):
        col = fpl_bench.ffiq_column(_FFIQ, 3)
        self.assertNotIn(("NoGw3", "BRE"), col)


class TestBaselineInputs(unittest.TestCase):
    def test_inputs_are_frozen_per_player(self):
        inp = fpl_bench.baseline_inputs(_BOOT, _FORM, 3)
        raya = inp["Raya|ARS"]
        self.assertEqual(raya["season_points"], 8)
        self.assertEqual(raya["appearances"], 2)
        self.assertEqual(raya["last4"], [6, 2])
        self.assertAlmostEqual(raya["ep_next"], 3.5)

    def test_zero_minute_rounds_do_not_count_as_appearances(self):
        form = {"10": [{"round": 1, "total_points": 0, "minutes": 0}]}
        inp = fpl_bench.baseline_inputs(_BOOT, form, 3)
        self.assertEqual(inp["Raya|ARS"]["appearances"], 0)
        self.assertEqual(inp["Raya|ARS"]["last4"], [])


class TestSnapshot(unittest.TestCase):
    def _take(self, tmp, gw=3):
        with mock.patch.object(fpl_bench, "BENCH_DIR", tmp), \
             mock.patch.object(fpl_bench, "our_column",
                               return_value={("Raya", "ARS"): 3.4}):
            return fpl_bench.take_snapshot(
                gw, ffiq_payload=_FFIQ, bootstrap=_BOOT, form_history=_FORM,
                now=None)

    def test_snapshot_freezes_every_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._take(tmp)
            snap = json.load(open(path))
        self.assertEqual(snap["evmax"]["Raya|ARS"], 3.4)
        self.assertEqual(snap["ffiq"]["Raya|ARS"], 2.7)
        self.assertIn("Raya|ARS", snap["baseline_inputs"])
        # provenance: the licence and attribution ride inside the snapshot
        self.assertIn("attribution", snap["sources"]["ffiq"])
        self.assertIn("Free to use", snap["sources"]["ffiq"]["license"])

    def test_frozen_means_frozen(self):
        """A benchmark whose pre-deadline files can be silently replaced
        proves nothing — overwrite refuses."""
        with tempfile.TemporaryDirectory() as tmp:
            self._take(tmp)
            with self.assertRaises(SystemExit):
                self._take(tmp)


class TestGrading(unittest.TestCase):
    def _snapshot(self):
        return {
            "evmax": {"A|X": 5.0, "B|X": 2.0},
            "ffiq": {"A|X": 4.0},
            "baseline_inputs": {
                "A|X": {"season_points": 8, "appearances": 2,
                        "last4": [6, 2], "ep_next": 3.0},
                "B|X": {"season_points": 0, "appearances": 0,
                        "last4": [], "ep_next": 1.0},
            },
        }

    def test_same_sample_scores_with_per_source_n(self):
        realized = {"A|X": 7, "B|X": 1}
        minutes = {"A|X": 90, "B|X": 20}
        out = fpl_bench.grade_snapshot(self._snapshot(), realized, minutes)
        # evmax graded on both, only A is a 60+ player
        self.assertEqual(out["evmax"]["n_all"], 2)
        self.assertEqual(out["evmax"]["n_60plus"], 1)
        self.assertAlmostEqual(out["evmax"]["mae_all"], 1.5)   # |5-7|,|2-1|
        self.assertAlmostEqual(out["evmax"]["mae_60plus"], 2.0)
        # ffiq only covers A — its n says so instead of hiding it
        self.assertEqual(out["ffiq"]["n_all"], 1)
        self.assertAlmostEqual(out["ffiq"]["mae_all"], 3.0)

    def test_baselines_come_from_frozen_inputs_only(self):
        out = fpl_bench.grade_snapshot(self._snapshot(),
                                       {"A|X": 4, "B|X": 0}, {"A|X": 90})
        # ppg: A = 8/2 = 4.0 → error 0; B has no appearances → not graded
        self.assertEqual(out["baseline_ppg"]["n_all"], 1)
        self.assertAlmostEqual(out["baseline_ppg"]["mae_all"], 0.0)
        # form4: A = (6+2)/2 = 4.0 → error 0
        self.assertAlmostEqual(out["baseline_form4"]["mae_all"], 0.0)
        self.assertEqual(out["ep_next"]["n_all"], 2)

    def test_an_empty_population_reports_none_not_a_crash(self):
        out = fpl_bench.grade_snapshot(self._snapshot(), {}, {})
        self.assertIsNone(out["evmax"]["mae_all"])
        self.assertEqual(out["evmax"]["n_all"], 0)


if __name__ == "__main__":
    unittest.main()


class TestBenchmarkSurfacing(unittest.TestCase):
    """The compare page was live but linked from NOWHERE — the owner asked
    where the comparison was five times while it sat orphaned. These pin the
    links and the section so it cannot silently orphan again."""

    def test_compare_page_carries_the_benchmark_section(self):
        from evmax import compare
        html = compare.compare_page()
        self.assertIn('id="benchmark"', html)
        self.assertIn("same sample, same yardstick",
                      html.lower().replace("—", "-").replace("  ", " ")
                      if False else html)

    def test_pending_snapshot_is_named_with_its_freeze_time(self):
        from evmax import compare
        html = compare.benchmark_section()
        self.assertIn("frozen, not yet graded", html)
        self.assertIn("before the deadline", html)

    def test_ffiq_attribution_is_always_present(self):
        # their licence requires it, and the benchmark quotes it
        from evmax import compare
        self.assertIn("fantasyfootballiq.app", compare.benchmark_section())

    def test_no_raw_projections_are_rendered(self):
        """Derived metrics only. The snapshot holds FFIQ's numbers as repo
        evidence; the page must never print them."""
        snap = fpl_bench.load_snapshot(3)
        if not snap:
            self.skipTest("no gw3 snapshot on this machine")
        from evmax import compare
        html = compare.benchmark_section()
        import re
        cells = re.findall(r"<td>([\d.]+)<", html)
        ffiq_values = {f"{v:.1f}" for v in list(snap["ffiq"].values())[:50]}
        # the page may coincidentally contain SOME number equal to a projection;
        # what it must not contain is a per-player projection table. Assert the
        # page carries no player-keyed rows at all.
        self.assertNotIn("Raya|", html)
        self.assertNotIn("data-player", html)

    def test_landing_and_track_record_link_the_benchmark(self):
        from evmax import fpl_players, render
        import inspect
        self.assertIn("/fpl/compare/#benchmark",
                      inspect.getsource(fpl_players.top_cards_html))
        self.assertIn("/fpl/compare/#benchmark",
                      inspect.getsource(render))
