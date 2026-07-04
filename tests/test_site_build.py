import unittest

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
