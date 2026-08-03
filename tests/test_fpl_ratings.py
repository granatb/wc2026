"""Phase 5: Premier League team ratings derived from published club strength."""
from __future__ import annotations

import unittest

from core import fpl_ratings


def _fill(partial: dict) -> dict:
    """Pad a partial strength dict with the None attack/defence keys."""
    out = {}
    for club, vals in partial.items():
        row = {"attack_home": None, "attack_away": None,
               "defence_home": None, "defence_away": None}
        row.update(vals)
        out[club] = row
    return out


class TestStrengthToRating(unittest.TestCase):
    def test_league_average_club_is_neutral(self):
        """The calibration anchor: an average club must not move the goal level."""
        r = fpl_ratings.derive(_fill({c: {"overall_home": 3, "overall_away": 3}
                                      for c in ("A", "B", "C")}))
        self.assertAlmostEqual(r["A"].attack, 1.0, places=6)
        self.assertAlmostEqual(r["A"].defence, 1.0, places=6)

    def test_stronger_club_attacks_more_and_concedes_less(self):
        r = fpl_ratings.derive(_fill({
            "STRONG": {"overall_home": 5, "overall_away": 5},
            "WEAK": {"overall_home": 2, "overall_away": 2},
            "MID": {"overall_home": 3, "overall_away": 3}}))
        self.assertGreater(r["STRONG"].attack, r["WEAK"].attack)
        self.assertLess(r["STRONG"].defence, r["WEAK"].defence)

    def test_spread_is_config_controlled(self):
        s = _fill({"S": {"overall_home": 5, "overall_away": 5},
                   "W": {"overall_home": 2, "overall_away": 2}})
        self.assertLess(fpl_ratings.derive(s, spread=0.05)["S"].attack,
                        fpl_ratings.derive(s, spread=0.40)["S"].attack)

    def test_zero_spread_reproduces_todays_uniform_behaviour(self):
        """The escape hatch: spread=0 must give back exactly what we have now, so a
        regression can be isolated to the ratings rather than the plumbing."""
        r = fpl_ratings.derive(_fill({"S": {"overall_home": 5, "overall_away": 5},
                                      "W": {"overall_home": 2, "overall_away": 2}}),
                               spread=0.0)
        self.assertAlmostEqual(r["S"].attack, r["W"].attack, places=6)
        self.assertAlmostEqual(r["S"].defence, r["W"].defence, places=6)

    def test_factors_stay_positive_at_extreme_spread(self):
        """A defence factor at or below zero would produce a zero/negative lambda."""
        r = fpl_ratings.derive(_fill({"S": {"overall_home": 5, "overall_away": 5},
                                      "W": {"overall_home": 2, "overall_away": 2}}),
                               spread=5.0)
        for rating in r.values():
            self.assertGreater(rating.attack, 0.0)
            self.assertGreater(rating.defence, 0.0)

    def test_single_club_does_not_divide_by_zero(self):
        r = fpl_ratings.derive(_fill({"ONLY": {"overall_home": 4, "overall_away": 4}}))
        self.assertAlmostEqual(r["ONLY"].attack, 1.0, places=6)

    def test_prefers_published_attack_defence_when_available(self):
        """In-season FPL populates these; once it does, the symmetry assumption in
        the overall-only path is strictly worse and must not be used.

        A is the strong club on BOTH sides of the ball. Note the direction of
        FPL's published defence figure: `strength_defence_*` is defensive
        STRENGTH, so the bigger number (1400) is the better defence and must map
        to the LOWER goals-conceded multiplier. Handing A the big attack number
        and the small defence number would describe an attacking side with a leaky
        back line, whose conceded multiplier should be the higher of the two.
        """
        r = fpl_ratings.derive({
            "A": {"overall_home": 3, "overall_away": 3, "attack_home": 1400,
                  "attack_away": 1400, "defence_home": 1400, "defence_away": 1400},
            "B": {"overall_home": 3, "overall_away": 3, "attack_home": 1000,
                  "attack_away": 1000, "defence_home": 1000, "defence_away": 1000}})
        self.assertGreater(r["A"].attack, r["B"].attack)
        self.assertLess(r["A"].defence, r["B"].defence)

    def test_published_path_ignores_overall(self):
        """Guards that the published branch is actually taken: `overall` here says
        B is the stronger club and the published figures say the opposite."""
        r = fpl_ratings.derive({
            "A": {"overall_home": 2, "overall_away": 2, "attack_home": 1400,
                  "attack_away": 1400, "defence_home": 1400, "defence_away": 1400},
            "B": {"overall_home": 5, "overall_away": 5, "attack_home": 1000,
                  "attack_away": 1000, "defence_home": 1000, "defence_away": 1000}})
        self.assertGreater(r["A"].attack, r["B"].attack)

    def test_partial_attack_data_falls_back_to_overall(self):
        """One club published and nineteen not is not a usable league scale."""
        r = fpl_ratings.derive({
            "A": {"overall_home": 5, "overall_away": 5, "attack_home": 1400,
                  "attack_away": 1400, "defence_home": 1000, "defence_away": 1000},
            "B": {"overall_home": 2, "overall_away": 2, "attack_home": None,
                  "attack_away": None, "defence_home": None, "defence_away": None}})
        self.assertGreater(r["A"].attack, r["B"].attack)   # from overall, not attack


class TestRegistration(unittest.TestCase):
    def setUp(self):
        from core import ratings
        self._saved = dict(ratings.TEAM_RATINGS)

    def tearDown(self):
        from core import ratings
        ratings.TEAM_RATINGS.clear()
        ratings.TEAM_RATINGS.update(self._saved)

    def test_registering_changes_match_lambdas(self):
        """The whole point: two different fixtures must stop returning the same
        numbers."""
        from core import ratings
        fpl_ratings.register(_fill({
            "LIV": {"overall_home": 5, "overall_away": 5},
            "COV": {"overall_home": 2, "overall_away": 2},
            "MID": {"overall_home": 3, "overall_away": 3}}))
        strong = ratings.match_lambdas("LIV", "COV", neutral=False)
        weak = ratings.match_lambdas("COV", "LIV", neutral=False)
        self.assertNotAlmostEqual(strong[0], weak[0], places=3)
        self.assertGreater(strong[0], weak[0])   # LIV at home outscores COV at home
        self.assertLess(strong[1], weak[1])      # and concedes less

    def test_registration_only_adds_keys(self):
        """TEAM_RATINGS is shared with the World Cup, whose track record grades off
        unchanged numbers. Registering FPL clubs must not touch existing entries."""
        from core import ratings
        before = {k: (v.attack, v.defence) for k, v in ratings.TEAM_RATINGS.items()}
        fpl_ratings.register(_fill({"LIV": {"overall_home": 5, "overall_away": 5}}))
        after = {k: (v.attack, v.defence) for k, v in ratings.TEAM_RATINGS.items()
                 if k in before}
        self.assertEqual(before, after)

    def test_registration_does_not_overwrite_an_existing_name(self):
        """Explicit collision case: a World Cup entry under a name an FPL club also
        uses keeps its odds-derived numbers."""
        from core import ratings
        ratings.TEAM_RATINGS["LIV"] = ratings.TeamRating("LIV", attack=1.9, defence=0.4)
        fpl_ratings.register(_fill({"LIV": {"overall_home": 2, "overall_away": 2},
                                    "COV": {"overall_home": 5, "overall_away": 5}}))
        self.assertEqual(ratings.TEAM_RATINGS["LIV"].attack, 1.9)
        self.assertEqual(ratings.TEAM_RATINGS["LIV"].defence, 0.4)

    def test_world_cup_lambdas_are_unchanged_after_registration(self):
        """Stronger form of the above: an actual World Cup fixture's numbers."""
        from core import ratings
        wc_teams = [k for k in ratings.TEAM_RATINGS][:2]
        if len(wc_teams) < 2:
            self.skipTest("no World Cup ratings to compare")
        before = ratings.match_lambdas(wc_teams[0], wc_teams[1])
        fpl_ratings.register(_fill({"LIV": {"overall_home": 5, "overall_away": 5}}))
        self.assertEqual(before, ratings.match_lambdas(wc_teams[0], wc_teams[1]))


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
