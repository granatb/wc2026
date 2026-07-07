"""slot_life / advance_prob / concentration_flags (games.holdet_common)."""

import unittest

from games import holdet_common as hc

# Synthetic knockout context: {team: (lam_for, lam_against, pW, pD, pL)}
CTX = {
    "France":  (2.5, 0.5, 0.80, 0.15, 0.05),   # heavy favourite
    "USA":     (1.4, 1.4, 0.36, 0.28, 0.36),   # coin flip
    "Egypt":   (0.6, 2.0, 0.10, 0.20, 0.70),   # heavy dog
}
R16 = 5


class SlotLife(unittest.TestCase):
    def test_advance_prob_orders_by_strength(self):
        pf = hc.advance_prob("France", R16, CTX)
        pu = hc.advance_prob("USA", R16, CTX)
        pe = hc.advance_prob("Egypt", R16, CTX)
        self.assertGreater(pf, pu)
        self.assertGreater(pu, pe)
        self.assertAlmostEqual(pu, 0.36 + 0.5 * 0.28)   # win + half the draws

    def test_unknown_team_is_dead(self):
        self.assertEqual(hc.advance_prob("Germany", R16, CTX), 0.0)
        self.assertEqual(hc.slot_life("Germany", R16, CTX), 1.0)

    def test_slot_life_monotone_and_bounded(self):
        lf = hc.slot_life("France", R16, CTX)
        lu = hc.slot_life("USA", R16, CTX)
        le = hc.slot_life("Egypt", R16, CTX)
        self.assertGreater(lf, lu)
        self.assertGreater(lu, le)
        self.assertGreaterEqual(le, 1.0)
        # R16 -> QF/SF/F remain: life = 1 + p*(1 + .5 + .25)
        p = hc.advance_prob("USA", R16, CTX)
        self.assertAlmostEqual(lu, 1 + p * 1.75)

    def test_group_stage_is_neutral(self):
        self.assertEqual(hc.slot_life("France", 2, CTX), 1.0)

    def test_final_has_no_future_rounds(self):
        self.assertAlmostEqual(hc.slot_life("France", hc.KNOCKOUT_FINAL_ROUND, CTX), 1.0)

    def test_concentration_flags_coinflip_stack(self):
        squad = ([{"name": f"usa{i}", "team": "USA"} for i in range(3)]
                 + [{"name": f"fra{i}", "team": "France"} for i in range(3)]
                 + [{"name": "egy", "team": "Egypt"}])
        flags = hc.concentration_flags(squad, R16, CTX)
        teams = [t for t, _n, _p in flags]
        self.assertIn("USA", teams)          # 3 on a coin flip -> flagged
        self.assertNotIn("France", teams)    # 3 on a heavy favourite -> fine
        self.assertNotIn("Egypt", teams)     # only 1 slot -> fine

    def test_two_on_a_coinflip_is_allowed(self):
        squad = [{"name": f"usa{i}", "team": "USA"} for i in range(hc.CONCENTRATION_LIMIT)]
        self.assertEqual(hc.concentration_flags(squad, R16, CTX), [])


if __name__ == "__main__":
    unittest.main()
