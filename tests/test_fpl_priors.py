import unittest

from core import fpl_priors, ratings


def _player(**kw):
    base = {
        "id": 1, "name": "Test", "full_name": "Test Player", "team": "LIV",
        "position": "MID", "price": 7.0, "ownership": 5.0, "status": "a",
        "chance_of_playing": None, "news": "", "minutes": 2700, "starts": 30,
        "xg_per90": 0.4, "xa_per90": 0.2, "saves_per90": 0.0,
        "defcon_per90": 4.0, "bps": 600, "ep_next": 5.0, "pen_taker": False,
    }
    base.update(kw)
    return base


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


class TestAvailabilityGating(unittest.TestCase):
    def test_injured_player_cannot_start(self):
        self.assertEqual(fpl_priors.availability_factor(_player(status="i")), 0.0)

    def test_suspended_player_cannot_start(self):
        self.assertEqual(fpl_priors.availability_factor(_player(status="s")), 0.0)

    def test_unavailable_player_cannot_start(self):
        self.assertEqual(fpl_priors.availability_factor(_player(status="u")), 0.0)

    def test_available_player_is_ungated(self):
        self.assertEqual(fpl_priors.availability_factor(_player(status="a")), 1.0)

    def test_doubtful_player_is_scaled_by_chance_of_playing(self):
        p = _player(status="d", chance_of_playing=25)
        self.assertAlmostEqual(fpl_priors.availability_factor(p), 0.25)

    def test_doubtful_without_a_percentage_is_treated_as_a_coin_flip(self):
        p = _player(status="d", chance_of_playing=None)
        self.assertAlmostEqual(fpl_priors.availability_factor(p), 0.5)

    def test_chance_of_playing_zero_gates_even_an_available_status(self):
        # FPL sometimes leaves status 'a' while chance_of_playing is 0
        p = _player(status="a", chance_of_playing=0)
        self.assertEqual(fpl_priors.availability_factor(p), 0.0)


class TestMinutesModel(unittest.TestCase):
    def test_nailed_starter_has_high_start_probability(self):
        # 34 starts from a 38-game season
        p = _player(minutes=3000, starts=34)
        sp, _mins = fpl_priors.minutes_model(p, team_matches=38)
        self.assertGreater(sp, 0.85)

    def test_rotation_player_has_middling_start_probability(self):
        p = _player(minutes=1400, starts=15)
        sp, _mins = fpl_priors.minutes_model(p, team_matches=38)
        self.assertGreater(sp, 0.3)
        self.assertLess(sp, 0.6)

    def test_expected_minutes_reflect_minutes_per_start(self):
        p = _player(minutes=2700, starts=30)   # 90 per start
        _sp, mins = fpl_priors.minutes_model(p, team_matches=38)
        self.assertGreater(mins, 80)
        self.assertLessEqual(mins, 90)

    def test_substitute_gets_low_expected_minutes(self):
        # A pure substitute: real minutes, zero starts. This is the shape the feed
        # actually produces for bench players, and it exercises the starts == 0
        # branch. (minutes=450 with starts=1 would be impossible — 450 minutes in
        # one match — and would take the minutes-per-start path to 90.)
        p = _player(minutes=450, starts=0)
        _sp, mins = fpl_priors.minutes_model(p, team_matches=38)
        self.assertLess(mins, 60)

    def test_injury_gates_start_probability_to_zero(self):
        p = _player(minutes=3000, starts=34, status="i")
        sp, _mins = fpl_priors.minutes_model(p, team_matches=38)
        self.assertEqual(sp, 0.0)

    def test_no_history_falls_back_without_dividing_by_zero(self):
        p = _player(minutes=0, starts=0)
        sp, mins = fpl_priors.minutes_model(p, team_matches=38)
        self.assertGreaterEqual(sp, 0.0)
        self.assertGreater(mins, 0.0)

    def test_start_probability_never_exceeds_one(self):
        p = _player(minutes=3420, starts=38)
        sp, _mins = fpl_priors.minutes_model(p, team_matches=38)
        self.assertLessEqual(sp, 1.0)
