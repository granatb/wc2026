import os
import tempfile
import unittest
from unittest import mock

from evmax import build


def _row(name, pos, xp, kickoff=None):
    # price=5.0 keeps a 15-man squad (75.0m) comfortably inside wildcard_squad's
    # default 100.0m budget.
    return {"name": name, "team": name + "land", "position": pos, "x_points": xp,
            "captain_ev": 2 * xp, "ceiling": xp, "price": 5.0, "ownership_pct": 20.0,
            "value": xp / 5.0, "kickoff": kickoff}


class ArticleEntriesTest(unittest.TestCase):
    """build._article_entries: published articles are frozen claims -- every
    article is always built from the full pre-lock player pool, with no
    round-progress-based filtering."""

    def _pool(self, kickoff=None):
        rows = []
        rows += [_row(f"GK{i}", "GK", 5 - i * 0.1, kickoff) for i in range(3)]
        rows += [_row(f"DEF{i}", "DEF", 6 - i * 0.1, kickoff) for i in range(8)]
        rows += [_row(f"MID{i}", "MID", 7 - i * 0.1, kickoff) for i in range(8)]
        rows += [_row(f"FWD{i}", "FWD", 8 - i * 0.1, kickoff) for i in range(6)]
        return rows

    def test_best_xi_uses_full_pool(self):
        pool = self._pool("2026-07-04T08:00:00+00:00")  # all already kicked off
        entries = build._article_entries(pool, fantasy_round=5)
        self.assertEqual(len(entries["best-xi"]), 11)

    def test_captains_reflects_full_pool_regardless_of_kickoff(self):
        pool = self._pool("2026-07-04T08:00:00+00:00")  # all already kicked off
        entries = build._article_entries(pool, fantasy_round=5)
        # captains is capped to top 20, but every row comes from the full pool --
        # none are excluded just because their fixture already kicked off.
        self.assertEqual(len(entries["captains"]), min(20, len(pool)))

    def test_wildcard_returns_a_legal_15_with_roles(self):
        pool = self._pool("2026-07-04T08:00:00+00:00")
        entries = build._article_entries(pool, fantasy_round=5)
        wildcard = entries["wildcard"]
        self.assertEqual(len(wildcard), 15)
        self.assertEqual(sum(1 for e in wildcard if e["role"] == "XI"), 11)
        self.assertEqual(sum(1 for e in wildcard if e["role"] == "Bench"), 4)


if __name__ == "__main__":
    unittest.main()


class ExpiredRiskFlagsTest(unittest.TestCase):
    class _Note:
        def __init__(self, status, rnd):
            self.status, self.round = status, rnd

    def test_flags_expired_out_note_on_published_pick(self):
        from evmax.build import expired_risk_flags
        entries_map = {"captains": [{"name": "Raphinha", "rank": 3}]}
        notes = {"Raphinha": self._Note("out", 3)}
        flags = expired_risk_flags(entries_map, notes, fantasy_round=5)
        self.assertEqual(len(flags), 1)
        self.assertIn("Raphinha", flags[0])
        self.assertIn("captains", flags[0])

    def test_current_round_and_clean_players_not_flagged(self):
        from evmax.build import expired_risk_flags
        entries_map = {"captains": [{"name": "Kane", "rank": 1},
                                    {"name": "Doubt", "rank": 2}]}
        notes = {"Doubt": self._Note("doubtful", 5),      # current round: fine
                 "Kane": self._Note("nailed", 3)}          # non-risk status: fine
        self.assertEqual(expired_risk_flags(entries_map, notes, fantasy_round=5), [])


class PreflightTest(unittest.TestCase):
    """build._preflight: data/ is gitignored, so a clean checkout has no
    schedule/odds/player data. The build must fail fast with the refresh
    commands, not die deep in the stack (FileNotFoundError on players.json,
    or an empty player pool surfacing as 'insufficient GK pool')."""

    def test_missing_schedule_names_the_refresh_command(self):
        with mock.patch.object(build.fixtures, "_SCHEDULE_JSON",
                               "/nonexistent/schedule.json"):
            with self.assertRaises(SystemExit) as cm:
                build._preflight(5)
        msg = str(cm.exception)
        self.assertIn("data/schedule.json", msg)
        self.assertIn("--refresh", msg)

    def test_round_absent_from_schedule_is_reported(self):
        with mock.patch.object(build.fixtures, "_SCHEDULE_JSON", __file__), \
             mock.patch.object(build.fixtures, "by_round", return_value=[]):
            with self.assertRaises(SystemExit) as cm:
                build._preflight(99)
        self.assertIn("round 99", str(cm.exception))

    def test_missing_players_json_names_the_sync_script(self):
        with mock.patch.object(build.fixtures, "_SCHEDULE_JSON", __file__), \
             mock.patch.object(build.fixtures, "by_round",
                               return_value=[object()]), \
             mock.patch.object(build.articles, "_PLAYERS_JSON",
                               "/nonexistent/players.json"):
            with self.assertRaises(SystemExit) as cm:
                build._preflight(5)
        msg = str(cm.exception)
        self.assertIn("data/players.json", msg)
        self.assertIn("build_players.py", msg)

    def test_all_data_present_passes(self):
        with mock.patch.object(build.fixtures, "_SCHEDULE_JSON", __file__), \
             mock.patch.object(build.fixtures, "by_round",
                               return_value=[object()]), \
             mock.patch.object(build.articles, "_PLAYERS_JSON", __file__):
            build._preflight(5)  # must not raise


class CheckRowsTest(unittest.TestCase):
    """build._check_rows: zero enriched rows means either the simulation
    produced no players (missing odds/schedule caches) or the name-join
    against data/players.json matched nothing — the error must say which."""

    def test_empty_means_points_at_simulation_inputs(self):
        with self.assertRaises(SystemExit) as cm:
            build._check_rows([], means={}, meta={"Kane": {}})
        self.assertIn("no players", str(cm.exception))

    def test_join_failure_points_at_players_json(self):
        with self.assertRaises(SystemExit) as cm:
            build._check_rows([], means={"Kane": {}}, meta={"Someone Else": {}})
        self.assertIn("players.json", str(cm.exception))

    def test_nonempty_rows_pass(self):
        build._check_rows([{"name": "Kane"}], means={"Kane": {}},
                          meta={"Kane": {}})  # must not raise


class BackfillLatestRoundLinkTest(unittest.TestCase):
    """build._backfill_latest_round_link: old rounds are frozen and never
    rebuilt, so they never pick up new nav features -- this patches ONLY a
    "back to the latest round" link into their already-built HTML, without
    touching any data/prose/numbers."""

    _PAGE = ('<html><head></head><body><header><div class="wrap">nav here</div>'
            '</header><div class="wrap"><h1>Old content -- must not change</h1>'
            '</div></body></html>')

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="evmax_backfill_test_")
        self.addCleanup(__import__("shutil").rmtree, self.tmp, ignore_errors=True)
        self.round_root = os.path.join(self.tmp, "round")

    def _write(self, round_no, slug="captains"):
        d = os.path.join(self.round_root, str(round_no), slug)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "index.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self._PAGE)
        return path

    def test_patches_old_round_not_current_round(self):
        old_path = self._write(3)
        current_path = self._write(5)
        build._backfill_latest_round_link(self.tmp, self.round_root, current_round=5)
        with open(old_path, encoding="utf-8") as fh:
            old_html = fh.read()
        with open(current_path, encoding="utf-8") as fh:
            current_html = fh.read()
        self.assertIn("back-to-latest", old_html)
        self.assertIn('href="/"', old_html)
        self.assertNotIn("back-to-latest", current_html)  # current round untouched

    def test_does_not_alter_existing_content(self):
        path = self._write(3)
        build._backfill_latest_round_link(self.tmp, self.round_root, current_round=5)
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        self.assertIn("Old content -- must not change", html)

    def test_idempotent_on_second_build(self):
        path = self._write(3)
        build._backfill_latest_round_link(self.tmp, self.round_root, current_round=5)
        build._backfill_latest_round_link(self.tmp, self.round_root, current_round=5)
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        self.assertEqual(html.count("back-to-latest"), 1)

    def test_missing_round_root_is_a_noop(self):
        build._backfill_latest_round_link(self.tmp, os.path.join(self.tmp, "nope"),
                                          current_round=5)  # must not raise


class RefreshOldRoundDynamicBitsTest(unittest.TestCase):
    """Old rounds keep frozen articles, but their round-switcher must gain
    later rounds and their landing live-XI strip must show the round's FINAL
    numbers (or vanish) instead of fossilizing mid-round."""

    _LANDING = ('<html><body><div class="round-switcher"><span class="rs-label">Rounds'
               '</span><a class="round-tab" href="/round/3/">R3</a>'
               '<a class="round-tab active" href="/round/5/">R5</a></div>'
               '<div class="live-xi"><div class="lx-row">old 9/11 played</div>'
               '<div class="lx-row lx-target">old target</div></div>'
               '<section class="feat"><h1>Frozen headline — must not change</h1>'
               '</section></body></html>')

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="evmax_refresh_test_")
        self.addCleanup(__import__("shutil").rmtree, self.tmp, ignore_errors=True)
        self.round_root = os.path.join(self.tmp, "round")
        d = os.path.join(self.round_root, "5")
        os.makedirs(d)
        self.landing = os.path.join(d, "index.html")
        with open(self.landing, "w", encoding="utf-8") as fh:
            fh.write(self._LANDING)

    def test_switcher_gains_new_round_and_strip_goes_final(self):
        panel = {"played": 11, "total": 11, "realized": 55.0, "expected": 59.4,
                 "ceiling": 91.2, "expected_total": 59.4, "ceiling_total": 91.2}
        build._refresh_old_round_dynamic_bits(
            self.round_root, current_round=6, available_rounds=[3, 5, 6],
            live_xi_by_round={5: panel})
        with open(self.landing, encoding="utf-8") as fh:
            html = fh.read()
        self.assertIn('href="/round/6/"', html)          # switcher gained R6
        self.assertNotIn("9/11 played", html)            # stale strip gone
        self.assertIn("round complete", html)            # final variant
        self.assertIn("55", html)                        # final realized total
        self.assertIn("Frozen headline — must not change", html)

    def test_strip_removed_when_no_data(self):
        build._refresh_old_round_dynamic_bits(
            self.round_root, current_round=6, available_rounds=[3, 5, 6],
            live_xi_by_round={})
        with open(self.landing, encoding="utf-8") as fh:
            html = fh.read()
        self.assertNotIn("live-xi", html)
        self.assertIn("Frozen headline — must not change", html)

