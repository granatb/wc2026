import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from evmax import backtest, render

# Integration tests against the REAL local caches (data/ is gitignored, absent in CI).
_HAS_LIVE_DATA = os.path.exists(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "schedule.json"))
_NEEDS_DATA = unittest.skipUnless(_HAS_LIVE_DATA,
                                  "requires local data/ caches (skipped in CI)")


def _env(round_no, slug, entries, generated_at="2026-06-24T12:00:00+00:00"):
    return {
        "competition": "fifa_world_cup_fantasy",
        "round": round_no,
        "article": slug,
        "title": f"{slug} — Round {round_no}",
        "generated_at": generated_at,
        "sims": 1000,
        "methodology": "test",
        "entries": entries,
        "source": "https://evmax.ai",
        "license": "https://creativecommons.org/licenses/by/4.0/",
    }


class LoadSnapshotsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write(self, round_no, slug, env):
        d = os.path.join(self.tmp, f"round-{round_no}")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{slug}.json"), "w", encoding="utf-8") as fh:
            json.dump(env, fh)

    def test_loads_rounds_and_slugs(self):
        self._write(3, "captains", _env(3, "captains", [{"name": "A"}]))
        self._write(3, "best-xi", _env(3, "best-xi", [{"name": "B"}]))
        self._write(5, "captains", _env(5, "captains", [{"name": "C"}]))
        snaps = backtest.load_snapshots(self.tmp)
        self.assertEqual(set(snaps.keys()), {3, 5})
        self.assertEqual(set(snaps[3].keys()), {"captains", "best-xi"})
        self.assertEqual(snaps[3]["captains"]["entries"][0]["name"], "A")

    def test_empty_dir_returns_empty_dict(self):
        empty = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        self.assertEqual(backtest.load_snapshots(empty), {})

    def test_missing_dir_returns_empty_dict(self):
        self.assertEqual(backtest.load_snapshots("/no/such/dir/at/all"), {})


class SpearmanTest(unittest.TestCase):
    def test_perfect_positive_correlation(self):
        rho = backtest.spearman([1, 2, 3, 4, 5], [10, 20, 30, 40, 50])
        self.assertAlmostEqual(rho, 1.0, places=6)

    def test_perfect_negative_correlation(self):
        rho = backtest.spearman([1, 2, 3, 4, 5], [50, 40, 30, 20, 10])
        self.assertAlmostEqual(rho, -1.0, places=6)

    def test_known_example_with_ties(self):
        # Classic worked example: ties get the average rank.
        xs = [1, 2, 2, 4]
        ys = [1, 3, 2, 4]
        rho = backtest.spearman(xs, ys)
        # xs ranks (desc, 1=best): values 4,2,2,1 -> ranks 1,2.5,2.5,4
        # ys ranks (desc): 4,3,2,1 -> ranks 1,2,3,4
        # Compute expected manually via Pearson-on-ranks.
        rx = [4, 2.5, 2.5, 1]  # rank of 1,2,2,4 descending
        ry = [4, 2, 3, 1]      # rank of 1,3,2,4 descending
        n = 4
        mean_rx, mean_ry = sum(rx) / n, sum(ry) / n
        num = sum((a - mean_rx) * (b - mean_ry) for a, b in zip(rx, ry))
        den = (sum((a - mean_rx) ** 2 for a in rx) ** 0.5) * \
              (sum((b - mean_ry) ** 2 for b in ry) ** 0.5)
        expected = num / den
        self.assertAlmostEqual(rho, expected, places=6)

    def test_too_few_points_returns_none(self):
        self.assertIsNone(backtest.spearman([1], [1]))
        self.assertIsNone(backtest.spearman([], []))

    def test_zero_variance_returns_none(self):
        self.assertIsNone(backtest.spearman([1, 1, 1], [1, 2, 3]))


class GradeRoundTest(unittest.TestCase):
    def setUp(self):
        self.snapshots = {
            3: {
                "captains": _env(3, "captains", [
                    {"name": "Top Pick", "x_points": 9.0, "rank": 1},
                    {"name": "Second", "x_points": 7.0, "rank": 2},
                    {"name": "Third", "x_points": 5.0, "rank": 3},
                    {"name": "Unmatched Player", "x_points": 4.0, "rank": 4},
                ]),
                "best-xi": _env(3, "best-xi", [
                    {"name": "Top Pick", "x_points": 9.0, "rank": 1},
                    {"name": "Second", "x_points": 7.0, "rank": 2},
                ]),
                "matches": _env(3, "matches", [{"match": "A vs B"}]),
            }
        }
        # realized: Second actually outscored Top Pick -> captain regret > 0
        self.realized = {
            "points": {"Top Pick": 3.0, "Second": 12.0, "Third": 1.0},
            "matched": 3,
            "total": 4,
            "unmatched": ["Unmatched Player"],
        }

    def test_captains_mae_and_top_pick_and_best_in_list(self):
        grades = backtest.grade_round(3, self.snapshots, self.realized)
        cap = grades["captains"]
        self.assertTrue(cap["graded"])
        self.assertEqual(cap["matched"], 3)
        self.assertEqual(cap["total"], 4)
        self.assertEqual(cap["top_pick"], {"name": "Top Pick", "projected": 9.0, "realized": 3.0})
        self.assertEqual(cap["best_in_list"], {"name": "Second", "realized": 12.0})
        expected_mae = (abs(9.0 - 3.0) + abs(7.0 - 12.0) + abs(5.0 - 1.0)) / 3
        self.assertAlmostEqual(cap["mae"], round(expected_mae, 3))

    def test_captain_regret_positive_when_better_pick_existed(self):
        grades = backtest.grade_round(3, self.snapshots, self.realized)
        cap = grades["captains"]
        self.assertAlmostEqual(cap["captain_regret"], 12.0 - 3.0)

    def test_captain_regret_zero_when_top_pick_is_best(self):
        realized = {"points": {"Top Pick": 15.0, "Second": 12.0, "Third": 1.0},
                    "matched": 3, "total": 4, "unmatched": []}
        grades = backtest.grade_round(3, self.snapshots, realized)
        self.assertEqual(grades["captains"]["captain_regret"], 0.0)

    def test_best_xi_projected_and_realized_totals(self):
        grades = backtest.grade_round(3, self.snapshots, self.realized)
        xi = grades["best-xi"]
        self.assertAlmostEqual(xi["xi_projected_total"], 16.0)
        self.assertAlmostEqual(xi["xi_realized_total"], 15.0)

    def test_matches_article_not_graded(self):
        grades = backtest.grade_round(3, self.snapshots, self.realized)
        self.assertFalse(grades["matches"]["graded"])

    def test_no_matched_entries_marks_not_graded(self):
        snaps = {3: {"captains": _env(3, "captains", [{"name": "Nobody Knows", "x_points": 1.0}])}}
        realized = {"points": {}, "matched": 0, "total": 1, "unmatched": ["Nobody Knows"]}
        grades = backtest.grade_round(3, snaps, realized)
        self.assertFalse(grades["captains"]["graded"])


class RoundStatusTest(unittest.TestCase):
    def test_no_snapshot(self):
        self.assertEqual(backtest.round_status(999999), "no_snapshot")

    @_NEEDS_DATA
    def test_round_3_is_final_in_real_data(self):
        # Real repo data: round 3 fixtures are all STATUS_FULL_TIME and a snapshot exists.
        self.assertEqual(backtest.round_status(3), "final")

    def test_round_5_is_pending_in_real_data(self):
        # Real repo data: round 5 fixtures are all STATUS_SCHEDULED.
        self.assertEqual(backtest.round_status(5), "pending")


class RealizedPointsTest(unittest.TestCase):
    @_NEEDS_DATA
    def test_round_3_coverage_is_high(self):
        realized = backtest.realized_points(3)
        self.assertGreater(realized["total"], 0)
        # Name-matching coverage must be near-total, or the page's numbers are untrustworthy.
        coverage = realized["matched"] / realized["total"]
        self.assertGreater(coverage, 0.7)


class MissesTest(unittest.TestCase):
    def test_bad_captain_pick_is_flagged(self):
        snaps = {3: {"captains": _env(3, "captains", [
            {"name": "Flop", "x_points": 9.0, "rank": 1},
            {"name": "Other", "x_points": 5.0, "rank": 2},
        ])}}
        realized = {"points": {"Flop": 1.0, "Other": 2.0}, "matched": 2, "total": 2, "unmatched": []}
        grades = backtest.grade_round(3, snaps, realized)
        misses = backtest._misses_for_round(3, grades)
        self.assertTrue(any("Flop" in m for m in misses))

    def test_negative_spearman_is_flagged(self):
        snaps = {3: {"efficiency": _env(3, "efficiency", [
            {"name": "A", "x_points": 9.0},
            {"name": "B", "x_points": 7.0},
            {"name": "C", "x_points": 5.0},
        ])}}
        realized = {"points": {"A": 1.0, "B": 5.0, "C": 9.0}, "matched": 3, "total": 3, "unmatched": []}
        grades = backtest.grade_round(3, snaps, realized)
        self.assertLess(grades["efficiency"]["spearman"], 0)
        misses = backtest._misses_for_round(3, grades)
        self.assertTrue(any("efficiency" in m for m in misses))

    def test_no_misses_when_all_good(self):
        snaps = {3: {"captains": _env(3, "captains", [
            {"name": "Good", "x_points": 9.0, "rank": 1},
        ])}}
        realized = {"points": {"Good": 12.0}, "matched": 1, "total": 1, "unmatched": []}
        grades = backtest.grade_round(3, snaps, realized)
        misses = backtest._misses_for_round(3, grades)
        self.assertEqual(misses, [])


class BuildTrackRecordTest(unittest.TestCase):
    @_NEEDS_DATA
    def test_round_3_excluded_from_rounds_list(self):
        # Owner decision 2026-07-04: round 3 hidden from the public track record.
        # Snapshots stay on disk (round_status/realized_points still see them),
        # but build_track_record() must not surface round 3 at all.
        record = backtest.build_track_record()
        rounds = {r["round"] for r in record["rounds"]}
        self.assertNotIn(3, rounds)
        # The underlying data is untouched -- only the display is filtered.
        self.assertEqual(backtest.round_status(3), "final")

    def test_round_3_excluded_from_summary_aggregates(self):
        # A hand-built snapshot set makes this deterministic regardless of
        # whatever real round-3 numbers happen to be on disk right now.
        with mock.patch.object(backtest, "EXCLUDED_DISPLAY_ROUNDS", {3}), \
             mock.patch.object(backtest, "RETROSPECTIVE_ROUNDS", set()):
            record = backtest.build_track_record()
        rounds = {r["round"] for r in record["rounds"]}
        self.assertNotIn(3, rounds)

    def test_round_5_is_published_and_pending(self):
        record = backtest.build_track_record()
        by_round = {r["round"]: r for r in record["rounds"]}
        self.assertEqual(by_round[5]["status"], "pending")
        self.assertEqual(by_round[5]["kind"], "published")

    def test_round_4_present_as_retrospective_with_note(self):
        fake_entries = {
            "captains": [{"name": "Fake Captain", "x_points": 8.0, "rank": 1}],
            "best-xi": [{"name": "Fake Captain", "x_points": 8.0}],
        }
        with mock.patch.object(backtest, "_retrospective_entries", return_value=fake_entries), \
             mock.patch.object(backtest, "round_status_ignoring_snapshot", return_value="final"), \
             mock.patch.object(backtest, "realized_points_for_entries",
                               return_value={"points": {"Fake Captain": 5.0},
                                             "matched": 1, "total": 1, "unmatched": []}):
            record = backtest.build_track_record()
        by_round = {r["round"]: r for r in record["rounds"]}
        self.assertIn(4, by_round)
        r4 = by_round[4]
        self.assertEqual(r4["kind"], "retrospective")
        self.assertEqual(r4["status"], "final")
        self.assertIn("note", r4)
        self.assertIn("Reconstructed after the fact", r4["note"])
        self.assertTrue(r4["grades"]["captains"]["graded"])

    def test_retrospective_round_excluded_from_summary_aggregates(self):
        fake_entries = {
            "captains": [{"name": "Fake Captain", "x_points": 8.0, "rank": 1},
                        {"name": "Second", "x_points": 6.0, "rank": 2}],
            "best-xi": [{"name": "Fake Captain", "x_points": 8.0}],
        }
        with mock.patch.object(backtest, "_retrospective_entries", return_value=fake_entries), \
             mock.patch.object(backtest, "round_status_ignoring_snapshot", return_value="final"), \
             mock.patch.object(backtest, "realized_points_for_entries",
                               return_value={"points": {"Fake Captain": 1.0, "Second": 99.0},
                                             "matched": 2, "total": 2, "unmatched": []}):
            record = backtest.build_track_record()
        by_round = {r["round"]: r for r in record["rounds"]}
        r4 = by_round[4]
        # A deliberately huge captain_regret for the fake round-4 data -- if it
        # leaked into the summary aggregates this would be obvious.
        self.assertGreater(r4["grades"]["captains"]["captain_regret"], 50)
        regretful_rounds = {cr["round"] for cr in record["summary"]["captain_regrets"]}
        self.assertNotIn(4, regretful_rounds)

    def test_retrospective_round_pending_when_fixtures_unfinished(self):
        with mock.patch.object(backtest, "round_status_ignoring_snapshot", return_value="pending"):
            record = backtest.build_track_record()
        by_round = {r["round"]: r for r in record["rounds"]}
        r4 = by_round[4]
        self.assertEqual(r4["status"], "pending")
        self.assertEqual(r4["kind"], "retrospective")
        self.assertEqual(r4["grades"], {})

    def test_rounds_sorted_newest_first(self):
        record = backtest.build_track_record()
        rounds = [r["round"] for r in record["rounds"]]
        self.assertEqual(rounds, sorted(rounds, reverse=True))


class TrackRecordPageTest(unittest.TestCase):
    def test_renders_final_and_pending_rounds(self):
        record = backtest.build_track_record()
        html = render.track_record_page(record)
        self.assertIn("<!doctype html>", html.lower())
        # Round 3 is hidden (owner decision) -- must not appear on the page.
        self.assertNotIn("Round 3</h2>", html)
        self.assertIn("Round 5", html)
        self.assertIn("pending", html.lower())
        self.assertIn('href="/track-record/"', html)
        self.assertIn("Accountability", html)

    def test_published_round_shows_frozen_at_lock_badge(self):
        record = {
            "rounds": [{
                "round": 5, "status": "pending", "kind": "published",
                "generated_at": "2026-06-24T12:00:00+00:00", "grades": {}, "misses": [],
            }],
            "summary": {"rounds_graded": 0, "mean_captain_mae": None,
                       "mean_spearman": None, "captain_regrets": []},
        }
        html = render.track_record_page(record)
        self.assertIn("frozen at lock", html)
        self.assertNotIn("Retrospective backtest", html)

    def test_retrospective_round_shows_badge_and_note(self):
        record = {
            "rounds": [{
                "round": 4, "status": "final", "kind": "retrospective",
                "generated_at": None,
                "note": "Reconstructed after the fact from frozen closing odds "
                        "(research overlay off, fixed seed). NOT published predictions.",
                "grades": {
                    "captains": {
                        "slug": "captains", "graded": True, "matched": 1, "total": 1,
                        "mae": 2.0, "spearman": None,
                        "top_pick": {"name": "A", "projected": 8.0, "realized": 6.0},
                        "best_in_list": {"name": "A", "realized": 6.0},
                        "captain_regret": 0.0,
                    },
                },
                "misses": [],
                "coverage": {"matched": 1, "total": 1},
            }],
            "summary": {"rounds_graded": 0, "mean_captain_mae": None,
                       "mean_spearman": None, "captain_regrets": []},
        }
        html = render.track_record_page(record)
        self.assertIn("Retrospective backtest", html)
        self.assertIn("Reconstructed after the fact", html)
        self.assertIn("tag-retro", html)
        self.assertNotIn("frozen at lock", html)

    def test_standfirst_mentions_retrospective_distinction(self):
        record = backtest.build_track_record()
        html = render.track_record_page(record)
        self.assertIn("reconstructed after results were", html.lower())

    def test_nav_link_present_and_active(self):
        record = backtest.build_track_record()
        html = render.track_record_page(record)
        # Fixed nav still has Home/About
        self.assertIn('href="/"', html)
        self.assertIn('href="/about/"', html)

    def test_misses_rendered_when_present(self):
        record = {
            "rounds": [{
                "round": 3, "status": "final", "generated_at": "2026-06-24T12:00:00+00:00",
                "grades": {
                    "captains": {
                        "slug": "captains", "graded": True, "matched": 2, "total": 2,
                        "mae": 3.5, "spearman": 0.5,
                        "top_pick": {"name": "Flop", "projected": 9.0, "realized": 1.0},
                        "best_in_list": {"name": "Other", "realized": 8.0},
                        "captain_regret": 7.0,
                    },
                },
                "misses": ["Round 3 captains: top pick Flop scored only 1.0 pts (projected 9.0)."],
                "coverage": {"matched": 2, "total": 2},
            }],
            "summary": {"rounds_graded": 1, "mean_captain_mae": 3.5, "mean_spearman": 0.5,
                       "captain_regrets": [{"round": 3, "regret": 7.0}]},
        }
        html = render.track_record_page(record)
        self.assertIn("Honest misses", html)
        self.assertIn("Flop", html)


class TrackRecordJsonTest(unittest.TestCase):
    def test_includes_methodology_and_license(self):
        record = backtest.build_track_record()
        env = render.track_record_json(record)
        self.assertIn("methodology", env)
        self.assertIn("license", env)
        json.dumps(env)  # must be JSON-serializable


class NavTest(unittest.TestCase):
    def test_nav_html_has_track_record_link(self):
        nav = render._nav_html()
        self.assertIn('href="/track-record/"', nav)
        self.assertIn("Track record", nav)

    def test_nav_html_active_track_record(self):
        nav = render._nav_html(active="track-record")
        self.assertIn('class="on"', nav)


if __name__ == "__main__":
    unittest.main()
