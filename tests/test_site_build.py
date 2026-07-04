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

