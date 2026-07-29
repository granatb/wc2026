import unittest

from core import ratings


class TestPlayerPriorNewFields(unittest.TestCase):
    def test_new_fields_default_to_zero(self):
        p = ratings.PlayerPrior(name="X", team="LIV", position="DEF")
        self.assertEqual(p.defcon_per90, 0.0)
        self.assertEqual(p.saves_per90, 0.0)

    def test_new_fields_are_settable(self):
        p = ratings.PlayerPrior(name="X", team="LIV", position="GK", saves_per90=3.1)
        self.assertAlmostEqual(p.saves_per90, 3.1)

    def test_existing_construction_is_unaffected(self):
        # WC code constructs PlayerPrior positionally and by keyword; both must still work
        p = ratings.PlayerPrior("Y", "Spain", "FWD", 0.9, 80, 0.3, 0.2, 1.5, True)
        self.assertTrue(p.pen_taker)
        self.assertAlmostEqual(p.sot_per90, 1.5)
