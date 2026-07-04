import unittest

from evmax import build


def _row(name, pos, xp, kickoff=None):
    return {"name": name, "team": name + "land", "position": pos, "x_points": xp,
            "captain_ev": 2 * xp, "ceiling": xp, "price": 8.0, "ownership_pct": 20.0,
            "value": xp / 8.0, "kickoff": kickoff}


class LivePoolTest(unittest.TestCase):
    """build._live_pool: the <5-upcoming-players fallback decision that keeps
    live mode from publishing near-empty ranked lists once a round is almost
    entirely finished."""

    NOW = "2026-07-04T18:00:00+00:00"
    FUTURE = "2026-07-05T12:00:00+00:00"
    PAST = "2026-07-04T08:00:00+00:00"

    def test_uses_upcoming_pool_when_enough_players_remain(self):
        rows = [_row(f"P{i}", "MID", 5.0, kickoff=self.FUTURE) for i in range(6)]
        rows += [_row(f"Done{i}", "FWD", 9.0, kickoff=self.PAST) for i in range(10)]
        pool, fallback = build._live_pool(rows, self.NOW)
        self.assertFalse(fallback)
        self.assertEqual(len(pool), 6)
        self.assertTrue(all(r["kickoff"] == self.FUTURE for r in pool))

    def test_falls_back_to_full_pool_when_fewer_than_minimum_upcoming(self):
        rows = [_row(f"P{i}", "MID", 5.0, kickoff=self.FUTURE) for i in range(3)]
        rows += [_row(f"Done{i}", "FWD", 9.0, kickoff=self.PAST) for i in range(10)]
        pool, fallback = build._live_pool(rows, self.NOW)
        self.assertTrue(fallback)
        self.assertEqual(len(pool), len(rows))  # full pool, unfiltered

    def test_exactly_at_the_minimum_threshold_does_not_fall_back(self):
        rows = [_row(f"P{i}", "MID", 5.0, kickoff=self.FUTURE)
               for i in range(build._MIN_LIVE_POOL)]
        pool, fallback = build._live_pool(rows, self.NOW)
        self.assertFalse(fallback)
        self.assertEqual(len(pool), build._MIN_LIVE_POOL)

    def test_empty_rows_falls_back(self):
        pool, fallback = build._live_pool([], self.NOW)
        self.assertTrue(fallback)
        self.assertEqual(pool, [])


class ArticleEntriesLivePoolTest(unittest.TestCase):
    """build._article_entries: best-xi must always be built from the FULL pool,
    even when a live_pool (filtered) is supplied for the other articles."""

    def _pool(self, kickoff):
        rows = []
        rows += [_row(f"GK{i}", "GK", 5 - i * 0.1, kickoff) for i in range(3)]
        rows += [_row(f"DEF{i}", "DEF", 6 - i * 0.1, kickoff) for i in range(8)]
        rows += [_row(f"MID{i}", "MID", 7 - i * 0.1, kickoff) for i in range(8)]
        rows += [_row(f"FWD{i}", "FWD", 8 - i * 0.1, kickoff) for i in range(6)]
        return rows

    def test_best_xi_uses_full_pool_not_live_pool(self):
        full_pool = self._pool("2026-07-04T08:00:00+00:00")   # all already kicked off
        live_pool = []  # simulate an aggressively filtered live pool
        entries = build._article_entries(full_pool, fantasy_round=5, live_pool=live_pool)
        # best-xi must still be a full valid XI built from full_pool, not empty
        self.assertEqual(len(entries["best-xi"]), 11)
        # but captains (a filtered article) reflects the live_pool, i.e. empty
        self.assertEqual(entries["captains"], [])

    def test_default_live_pool_none_uses_full_pool_everywhere(self):
        full_pool = self._pool("2026-07-05T08:00:00+00:00")
        entries = build._article_entries(full_pool, fantasy_round=3)
        self.assertEqual(len(entries["best-xi"]), 11)
        self.assertGreater(len(entries["captains"]), 0)


if __name__ == "__main__":
    unittest.main()
