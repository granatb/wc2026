"""games/fpl/transfers.py — the single-swap transfer optimizer (task 5).

Offline and pure: hand-built squad states and a hand-built 3-GW horizon
matrix; every delta below is checkable on paper.
"""

from __future__ import annotations

import unittest

from games.fpl import transfers

_D = transfers.DISCOUNT


def _entry(name, position="FWD", team="AVL", price=9.0):
    return {"name": name, "position": position, "team": team, "price": price,
            "is_starter": True, "bench_order": None,
            "is_captain": False, "is_vice": False}


def _state(entries):
    return {"team_name": "The Model XI", "strategy": "model",
            "squad": entries, "free_transfers": 1}


def _horizon(per_player):
    """{gw: {name: row}} from {name: (team, pos, price, [xp1, xp2, xp3])}."""
    out: dict = {}
    for name, (team, pos, price, xps) in per_player.items():
        for i, xp in enumerate(xps):
            out.setdefault(i + 1, {})[name] = {
                "name": name, "team": team, "position": pos,
                "price": price, "x_points": xp}
    return out


class TestRecommend(unittest.TestCase):
    _SQUAD = [_entry("Watkins", "FWD", "AVL", 9.0),
              _entry("CheapFwd", "FWD", "BOU", 6.0),
              _entry("Mid", "MID", "ARS", 8.0)]

    def _rows(self, extra=None):
        base = {
            "Watkins":  ("AVL", "FWD", 9.0, [2.0, 2.0, 2.0]),
            "CheapFwd": ("BOU", "FWD", 6.0, [4.0, 4.0, 4.0]),
            "Mid":      ("ARS", "MID", 8.0, [5.0, 5.0, 5.0]),
            "Isak":     ("LIV", "FWD", 10.5, [6.0, 5.0, 7.0]),
            "Budget":   ("SUN", "FWD", 8.0, [3.0, 3.0, 3.0]),
        }
        base.update(extra or {})
        return _horizon(base)

    def test_delta_math_over_a_three_gw_horizon(self):
        """Watkins → Isak with 1.5 in the bank: delta is the discounted sum
        of the per-GW xPts differences, nothing else."""
        recs = transfers.recommend(_state(self._SQUAD), self._rows(),
                                   free_transfers=1, bank=1.5)
        swap = next(r for r in recs
                    if r["out"] == "Watkins" and r["in"] == "Isak")
        expected = (6.0 - 2.0) + _D * (5.0 - 2.0) + _D ** 2 * (7.0 - 2.0)
        self.assertAlmostEqual(swap["delta"], round(expected, 2), places=2)
        self.assertEqual(swap["hit_adjusted_delta"], swap["delta"])

    def test_budget_feasibility_uses_bank_plus_selling_price(self):
        """Isak (10.5) needs bank >= 1.5 on a 9.0 sale — with an empty bank
        he is not a legal swap for Watkins, but stays one for nobody else."""
        recs = transfers.recommend(_state(self._SQUAD), self._rows(),
                                   free_transfers=1, bank=0.0)
        self.assertNotIn(("Watkins", "Isak"),
                         [(r["out"], r["in"]) for r in recs])
        recs = transfers.recommend(_state(self._SQUAD), self._rows(),
                                   free_transfers=1, bank=1.5)
        self.assertIn(("Watkins", "Isak"),
                      [(r["out"], r["in"]) for r in recs])

    def test_club_cap_is_enforced_post_swap(self):
        squad = [_entry("A1", "MID", "ARS", 5.0),
                 _entry("A2", "MID", "ARS", 5.0),
                 _entry("A3", "DEF", "ARS", 5.0),
                 _entry("Out", "FWD", "BOU", 9.0)]
        rows = self._rows(extra={
            "A1": ("ARS", "MID", 5.0, [3.0, 3.0, 3.0]),
            "A2": ("ARS", "MID", 5.0, [3.0, 3.0, 3.0]),
            "A3": ("ARS", "DEF", 5.0, [3.0, 3.0, 3.0]),
            "Out": ("BOU", "FWD", 9.0, [2.0, 2.0, 2.0]),
            "Gyokeres": ("ARS", "FWD", 9.0, [9.0, 9.0, 9.0]),
        })
        recs = transfers.recommend(_state(squad), rows,
                                   free_transfers=1, bank=0.0)
        self.assertNotIn("Gyokeres", [r["in"] for r in recs])

    def test_swapping_within_the_same_club_frees_a_slot(self):
        squad = [_entry("A1", "MID", "ARS", 5.0),
                 _entry("A2", "MID", "ARS", 5.0),
                 _entry("A3", "FWD", "ARS", 9.0)]
        rows = self._rows(extra={
            "A1": ("ARS", "MID", 5.0, [3.0, 3.0, 3.0]),
            "A2": ("ARS", "MID", 5.0, [3.0, 3.0, 3.0]),
            "A3": ("ARS", "FWD", 9.0, [2.0, 2.0, 2.0]),
            "Gyokeres": ("ARS", "FWD", 9.0, [9.0, 9.0, 9.0]),
        })
        recs = transfers.recommend(_state(squad), rows,
                                   free_transfers=1, bank=0.0)
        self.assertIn(("A3", "Gyokeres"),
                      [(r["out"], r["in"]) for r in recs])

    def test_flagged_player_surfaces_first_even_at_negative_delta(self):
        """Watkins red-flagged: selling him leads the table even though his
        best swap loses xPts and an unflagged positive swap exists."""
        rows = self._rows(extra={
            "Watkins": ("AVL", "FWD", 9.0, [5.0, 5.0, 5.0]),
            "Downgrade": ("SUN", "FWD", 7.0, [4.0, 4.0, 4.0]),
            "BetterMid": ("MCI", "MID", 8.0, [7.0, 7.0, 7.0]),
        })
        recs = transfers.recommend(_state(self._SQUAD), rows,
                                   free_transfers=1, bank=0.0,
                                   flagged={"Watkins"})
        self.assertEqual(recs[0]["out"], "Watkins")
        self.assertLess(recs[0]["delta"], 0)
        self.assertTrue(any("flag" in reason.lower()
                            for reason in recs[0]["reasons"]))

    def test_hit_adjustment_applies_only_at_zero_free_transfers(self):
        with_ft = transfers.recommend(_state(self._SQUAD), self._rows(),
                                      free_transfers=1, bank=1.5)
        without = transfers.recommend(_state(self._SQUAD), self._rows(),
                                      free_transfers=0, bank=1.5)
        swap_ft = next(r for r in with_ft if r["in"] == "Isak")
        swap_no = next(r for r in without if r["in"] == "Isak")
        self.assertEqual(swap_ft["hit_adjusted_delta"], swap_ft["delta"])
        self.assertAlmostEqual(swap_no["hit_adjusted_delta"],
                               round(swap_no["delta"] - transfers.HIT_COST, 2),
                               places=2)

    def test_minutes_floor_excludes_low_start_candidates(self):
        rows = self._rows()
        for gw_rows in rows.values():
            gw_rows["Isak"]["start_prob"] = 0.5
        recs = transfers.recommend(_state(self._SQUAD), rows,
                                   free_transfers=1, bank=1.5)
        self.assertNotIn("Isak", [r["in"] for r in recs])
        recs = transfers.recommend(_state(self._SQUAD), rows,
                                   free_transfers=1, bank=1.5,
                                   notes={"Isak"})
        self.assertIn("Isak", [r["in"] for r in recs])

    def test_top_five_only(self):
        extra = {f"F{i}": ("SUN", "FWD", 5.0, [4.0 + i * 0.1] * 3)
                 for i in range(9)}
        recs = transfers.recommend(_state(self._SQUAD), self._rows(extra),
                                   free_transfers=1, bank=2.0)
        self.assertLessEqual(len(recs), 5)
        deltas = [r["delta"] for r in recs]
        self.assertEqual(deltas, sorted(deltas, reverse=True))


if __name__ == "__main__":
    unittest.main()
