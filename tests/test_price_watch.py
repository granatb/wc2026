"""The daily price watch — see scripts/price_watch.py.

Prices move nightly and the Thursday feed diff is weekly, so between sessions
nobody saw a move until it showed up in the app. These pin the two things that
make the watcher safe to run every morning: it must not disturb the publish
gate's snapshot, and it must say plainly which moves touch a published squad.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import price_watch


def _boot(*rows):
    return {"teams": [{"id": 1, "short_name": "LIV"}],
            "elements": [{"id": i, "web_name": n, "team": 1,
                          "now_cost": int(round(p * 10))}
                         for i, (n, p) in enumerate(rows, start=1)]}


class TestPrices(unittest.TestCase):
    def test_projection_carries_name_team_and_price(self):
        out = price_watch.prices(_boot(("Gakpo", 7.0)))
        self.assertEqual(out["1"], {"name": "Gakpo", "team": "LIV",
                                    "price": 7.0})

    def test_price_is_pounds_not_tenths(self):
        out = price_watch.prices(_boot(("Haaland", 15.5)))
        self.assertEqual(out["1"]["price"], 15.5)


class TestChanges(unittest.TestCase):
    def test_no_move_reports_nothing(self):
        a = price_watch.prices(_boot(("Gakpo", 7.0)))
        self.assertEqual(price_watch.changes(a, dict(a)), [])

    def test_a_fall_is_reported_with_a_negative_delta(self):
        old = price_watch.prices(_boot(("Watkins", 8.0)))
        new = price_watch.prices(_boot(("Watkins", 7.9)))
        (row,) = price_watch.changes(old, new)
        self.assertAlmostEqual(row["delta"], -0.1)
        self.assertEqual((row["old"], row["new"]), (8.0, 7.9))

    def test_falls_sort_before_rises(self):
        old = price_watch.prices(_boot(("Faller", 8.0), ("Riser", 5.0)))
        new = price_watch.prices(_boot(("Faller", 7.9), ("Riser", 5.1)))
        rows = price_watch.changes(old, new)
        self.assertEqual([r["name"] for r in rows], ["Faller", "Riser"])

    def test_a_new_player_is_not_a_price_change(self):
        old = price_watch.prices(_boot(("Gakpo", 7.0)))
        new = price_watch.prices(_boot(("Gakpo", 7.0), ("Newboy", 4.5)))
        self.assertEqual(price_watch.changes(old, new), [])

    def test_floating_point_noise_does_not_invent_a_move(self):
        old = price_watch.prices(_boot(("Gakpo", 7.1)))
        new = price_watch.prices(_boot(("Gakpo", 7.1)))
        self.assertEqual(price_watch.changes(old, new), [])


class TestReport(unittest.TestCase):
    def test_squad_members_are_separated_from_everyone_else(self):
        rows = [{"name": "Watkins", "team": "AVL", "old": 8.0, "new": 7.9,
                 "delta": -0.1, "id": "1"},
                {"name": "Stranger", "team": "LIV", "old": 5.0, "new": 5.1,
                 "delta": 0.1, "id": "2"}]
        text = price_watch.report(rows, {"Watkins": ["The Model XI"]})
        self.assertIn("OURS:", text)
        self.assertIn("The Model XI", text)
        self.assertIn("EVERYONE ELSE:", text)
        self.assertLess(text.index("Watkins"), text.index("Stranger"))

    def test_quiet_night_says_so(self):
        self.assertIn("nothing moved", price_watch.report([], {}))


class TestGateIsolation(unittest.TestCase):
    """The reason this is not just `python3 -m core.fpl_diff` on a timer."""

    def test_the_watch_does_not_use_the_feed_snapshot(self):
        # feed_snapshot.json's timestamp is what the publish gate measures
        # research notes against. Rotating it daily would push that date
        # forward every morning and invalidate the previous day's notes.
        from core import fpl_diff
        self.assertNotEqual(price_watch.WATCH_CACHE, fpl_diff.SNAPSHOT_CACHE)

    def test_both_published_squads_are_watched(self):
        self.assertEqual(set(price_watch.STATE_FILES),
                         {"state.json", "state_consensus.json"})

    def test_squad_names_maps_players_to_the_squads_holding_them(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "games", "fpl"))
            for fname, team, who in (
                    ("state.json", "The Model XI", "Gakpo"),
                    ("state_consensus.json", "The Consensus XI", "Gakpo")):
                with open(os.path.join(root, "games", "fpl", fname), "w") as fh:
                    json.dump({"team_name": team,
                               "squad": [{"name": who}]}, fh)
            held = price_watch.squad_names(root)
        self.assertEqual(held["Gakpo"], ["The Model XI", "The Consensus XI"])

    def test_a_missing_state_file_is_not_fatal(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(price_watch.squad_names(root), {})


if __name__ == "__main__":
    unittest.main()
