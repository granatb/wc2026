import unittest

import config
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


class TestColdStartFallback(unittest.TestCase):
    def test_player_with_history_does_not_use_the_fallback(self):
        p = _player(minutes=2700, xg_per90=0.55)
        self.assertFalse(fpl_priors.needs_cold_start(p))

    def test_player_with_no_minutes_uses_the_fallback(self):
        self.assertTrue(fpl_priors.needs_cold_start(_player(minutes=0, starts=0)))

    def test_fallback_rate_scales_with_price(self):
        cheap = fpl_priors.price_prior_xg(_player(price=4.5, position="FWD"))
        dear = fpl_priors.price_prior_xg(_player(price=11.0, position="FWD"))
        self.assertGreater(dear, cheap)

    def test_fallback_rate_respects_position(self):
        fwd = fpl_priors.price_prior_xg(_player(price=7.0, position="FWD"))
        dfn = fpl_priors.price_prior_xg(_player(price=7.0, position="DEF"))
        self.assertGreater(fwd, dfn)

    def test_goalkeeper_fallback_expects_no_goals(self):
        self.assertEqual(fpl_priors.price_prior_xg(_player(price=5.5, position="GK")), 0.0)


class TestBuildPriors(unittest.TestCase):
    def setUp(self):
        self.players = [
            _player(id=1, name="Striker", position="FWD", team="LIV",
                    xg_per90=0.8, xa_per90=0.2, minutes=2700, starts=30),
            _player(id=2, name="Winger", position="MID", team="LIV",
                    xg_per90=0.3, xa_per90=0.4, minutes=2400, starts=27),
            _player(id=3, name="Keeper", position="GK", team="LIV",
                    xg_per90=0.0, xa_per90=0.0, saves_per90=2.8,
                    minutes=3420, starts=38),
            _player(id=4, name="Newboy", position="FWD", team="COV",
                    xg_per90=0.0, xa_per90=0.0, minutes=0, starts=0, price=6.0),
        ]

    def test_returns_player_prior_objects_keyed_by_team(self):
        by_team = fpl_priors.build(self.players, team_matches=38)
        self.assertIn("LIV", by_team)
        self.assertEqual(len(by_team["LIV"]), 3)
        self.assertIsInstance(by_team["LIV"][0], ratings.PlayerPrior)

    def test_goal_share_is_normalised_within_the_club(self):
        by_team = fpl_priors.build(self.players, team_matches=38)
        shares = {p.name: p.goal_share for p in by_team["LIV"]}
        # the striker out-shoots the winger, and both are fractions
        self.assertGreater(shares["Striker"], shares["Winger"])
        self.assertLess(shares["Striker"], 1.0)

    def test_goalkeeper_carries_saves_rate_and_no_goal_share(self):
        by_team = fpl_priors.build(self.players, team_matches=38)
        gk = next(p for p in by_team["LIV"] if p.position == "GK")
        self.assertAlmostEqual(gk.saves_per90, 2.8)
        self.assertEqual(gk.goal_share, 0.0)

    def test_defcon_rate_carried_onto_the_prior(self):
        by_team = fpl_priors.build(self.players, team_matches=38)
        mid = next(p for p in by_team["LIV"] if p.name == "Winger")
        self.assertAlmostEqual(mid.defcon_per90, 4.0)

    def test_cold_start_player_still_gets_a_usable_prior(self):
        by_team = fpl_priors.build(self.players, team_matches=38)
        newboy = by_team["COV"][0]
        self.assertGreater(newboy.goal_share, 0.0)

    def test_cold_start_players_are_reported_for_preflight(self):
        _by_team, flagged = fpl_priors.build_with_flags(self.players, team_matches=38)
        self.assertEqual([f["name"] for f in flagged], ["Newboy"])
        self.assertEqual(flagged[0]["reason"], "no_pl_history")


class TestNameDisambiguation(unittest.TestCase):
    """FPL's web_name collides across clubs (14 collisions in the real GW1 pool,
    the worst being Cole Palmer/CHE/MID vs Alex Palmer/IPS/GK both keying the
    engine's accumulator as "Palmer"). build_with_flags must hand every player a
    name that is unique across the whole pool, escalating only as far as needed.
    """

    def test_unique_web_name_is_left_untouched(self):
        players = [
            _player(id=1, name="Salah", full_name="Mohamed Salah", team="LIV"),
            _player(id=2, name="Watkins", full_name="Ollie Watkins", team="AVL"),
        ]
        fpl_priors.build_with_flags(players, team_matches=38)
        by_id = {p["id"]: p["name"] for p in players}
        self.assertEqual(by_id[1], "Salah")
        self.assertEqual(by_id[2], "Watkins")

    def test_palmer_collision_resolved_and_recoverable_by_name(self):
        # The real GW1 collision: both survive, both are recoverable to the
        # correct club/position via the mutated player dicts.
        players = [
            _player(id=1, name="Palmer", full_name="Cole Palmer", team="CHE",
                    position="MID", price=9.5, minutes=1954),
            _player(id=2, name="Palmer", full_name="Alex Palmer", team="IPS",
                    position="GK", price=4.0, minutes=0, starts=0),
        ]
        fpl_priors.build_with_flags(players, team_matches=38)
        by_name = {p["name"]: p for p in players}

        self.assertEqual(len(by_name), 2)
        self.assertEqual(by_name["Cole Palmer"]["position"], "MID")
        self.assertEqual(by_name["Cole Palmer"]["team"], "CHE")
        self.assertEqual(by_name["Alex Palmer"]["position"], "GK")
        self.assertEqual(by_name["Alex Palmer"]["team"], "IPS")

        # ... and the priors built from those same players carry the same names.
        by_team, _flags = fpl_priors.build_with_flags(players, team_matches=38)
        prior_names = {p.position: p.name for squad in by_team.values() for p in squad}
        self.assertEqual(prior_names["MID"], "Cole Palmer")
        self.assertEqual(prior_names["GK"], "Alex Palmer")

    def test_three_way_collision_produces_three_distinct_names(self):
        players = [
            _player(id=1, name="Phillips", full_name="Kalvin Phillips", team="WHU"),
            _player(id=2, name="Phillips", full_name="Nathan Phillips", team="BOU"),
            _player(id=3, name="Phillips", full_name="Matty Phillips", team="WBA"),
        ]
        by_team, _flags = fpl_priors.build_with_flags(players, team_matches=38)
        resolved = [p.name for squad in by_team.values() for p in squad]
        self.assertEqual(len(resolved), 3)
        self.assertEqual(len(set(resolved)), 3)

    def test_collision_sharing_both_names_falls_back_to_team_qualified(self):
        players = [
            _player(id=1, name="King", full_name="Josh King", team="FUL"),
            _player(id=2, name="King", full_name="Josh King", team="EVE"),
        ]
        by_team, _flags = fpl_priors.build_with_flags(players, team_matches=38)
        self.assertEqual(by_team["FUL"][0].name, "King (FUL)")
        self.assertEqual(by_team["EVE"][0].name, "King (EVE)")
        self.assertNotEqual(by_team["FUL"][0].name, by_team["EVE"][0].name)


class TestDefconBackfill(unittest.TestCase):
    """bootstrap-static zeroes every DefCon field preseason; core.fpl_api's
    element-summary backfill supplies last season's rate instead. Live bootstrap
    data must always win when it is actually non-zero.
    """

    def test_zero_bootstrap_defcon_picks_up_the_backfilled_rate(self):
        players = [_player(id=1, name="Gabriel", team="ARS", position="DEF",
                           defcon_per90=0.0)]
        backfill = {1: {"defcon_per90": 9.07, "minutes": 2750}}
        by_team = fpl_priors.build(players, team_matches=38, defcon_backfill=backfill)
        # Shrunk toward the DEF prior, not the raw 9.07 -- see TestDefconShrinkage.
        # 2750 minutes is a real season though, so it should stay close to 9.07.
        expected = fpl_priors.shrink_defcon_rate("DEF", 9.07, 2750)
        self.assertAlmostEqual(by_team["ARS"][0].defcon_per90, expected, places=2)
        self.assertAlmostEqual(by_team["ARS"][0].defcon_per90, 9.07, delta=0.5)

    def test_nonzero_bootstrap_defcon_wins_over_the_backfill(self):
        # in-season live data must never be overridden by last season's history
        players = [_player(id=1, name="Live", team="ARS", position="DEF",
                           defcon_per90=5.0)]
        backfill = {1: {"defcon_per90": 9.07, "minutes": 2750}}
        by_team = fpl_priors.build(players, team_matches=38, defcon_backfill=backfill)
        self.assertAlmostEqual(by_team["ARS"][0].defcon_per90, 5.0)

    def test_player_absent_from_backfill_gets_zero_without_raising(self):
        players = [_player(id=99, name="Nobody", team="ARS", position="DEF",
                           defcon_per90=0.0)]
        backfill = {1: {"defcon_per90": 9.07, "minutes": 2750}}
        by_team = fpl_priors.build(players, team_matches=38, defcon_backfill=backfill)
        self.assertEqual(by_team["ARS"][0].defcon_per90, 0.0)

    def test_backfill_argument_is_optional(self):
        # existing callers of build()/build_with_flags() must keep working unmodified
        players = [_player(id=1, name="X", team="ARS", position="DEF",
                           defcon_per90=0.0)]
        by_team = fpl_priors.build(players, team_matches=38)
        self.assertEqual(by_team["ARS"][0].defcon_per90, 0.0)

    def test_build_with_flags_also_accepts_the_backfill(self):
        players = [_player(id=1, name="Gabriel", team="ARS", position="DEF",
                           defcon_per90=0.0)]
        backfill = {1: {"defcon_per90": 9.07, "minutes": 2750}}
        by_team, _flags = fpl_priors.build_with_flags(
            players, team_matches=38, defcon_backfill=backfill)
        # Shrunk toward the DEF prior, not the raw 9.07 -- see TestDefconShrinkage.
        expected = fpl_priors.shrink_defcon_rate("DEF", 9.07, 2750)
        self.assertAlmostEqual(by_team["ARS"][0].defcon_per90, expected, places=2)

    def test_goalkeeper_never_gets_a_nonzero_defcon_rate(self):
        # Defect D self-review question: can a keeper ever get a non-zero rate?
        # Answer must be no, even if bootstrap's live field or the backfill cache
        # somehow carries a stray non-zero value for one.
        players = [_player(id=1, name="Keeper", team="ARS", position="GK",
                           defcon_per90=4.0)]
        backfill = {1: {"defcon_per90": 12.0, "minutes": 3000}}
        by_team = fpl_priors.build(players, team_matches=38, defcon_backfill=backfill)
        self.assertEqual(by_team["ARS"][0].defcon_per90, 0.0)


class TestDefconShrinkage(unittest.TestCase):
    """Empirical-Bayes shrinkage of the raw per-90 DefCon rate toward the
    position prior, in units of 90-minute appearances (config.FPL_DEFCON_PRIOR /
    config.FPL_DEFCON_SHRINKAGE_K). Fixes defect D: a raw rate from a handful of
    minutes is noise (a 1-minute cameo with one CBIT action prints 90.0 per 90)
    that would otherwise top the DefCon leaderboard ahead of genuine defensive
    midfielders with thousands of minutes of real signal.
    """

    def test_one_minute_sample_lands_on_the_prior(self):
        # One minute of history (0.011 90-minute appearances) is essentially no
        # signal at all -- the shrunk rate must land close to the MID prior
        # regardless of how extreme the single-minute observed rate is.
        rate = fpl_priors.shrink_defcon_rate("MID", observed=90.0, minutes=1)
        self.assertAlmostEqual(rate, config.FPL_DEFCON_PRIOR["MID"], delta=0.5)

    def test_high_minutes_sample_stays_close_to_observed(self):
        # 3000+ minutes (33+ appearances) is a real season's worth of signal --
        # the prior should barely move it.
        observed = 13.91  # measured rate for a real >=900-minute MID
        rate = fpl_priors.shrink_defcon_rate("MID", observed=observed, minutes=3000)
        self.assertAlmostEqual(rate, observed, delta=1.0)
        # and it must have moved meaningfully less than a barely-sampled player would
        self.assertGreater(rate, config.FPL_DEFCON_PRIOR["MID"] + 3.0)

    def test_mid_sample_falls_strictly_between_observed_and_prior(self):
        # 450 minutes (5 appearances) is neither noise nor a full sample -- the
        # 200-900 minute band the task calls out as needing a meaningful, not total,
        # pull toward the prior.
        prior = config.FPL_DEFCON_PRIOR["DEF"]
        observed = 15.0
        rate = fpl_priors.shrink_defcon_rate("DEF", observed=observed, minutes=450)
        self.assertGreater(rate, prior)
        self.assertLess(rate, observed)

    def test_goalkeeper_gets_zero_regardless_of_history(self):
        self.assertEqual(
            fpl_priors.shrink_defcon_rate("GK", observed=999.0, minutes=5000), 0.0)
        self.assertEqual(
            fpl_priors.shrink_defcon_rate("GK", observed=0.0, minutes=1), 0.0)

    def test_shrunk_rate_is_never_negative_or_above_the_larger_input(self):
        cases = [
            ("DEF", 0.0, 5), ("DEF", 20.0, 10), ("MID", 5.0, 3000),
            ("FWD", 0.0, 0), ("FWD", 25.0, 1), ("MID", 0.0, 3000),
        ]
        for position, observed, minutes in cases:
            prior = config.FPL_DEFCON_PRIOR[position]
            rate = fpl_priors.shrink_defcon_rate(position, observed, minutes)
            with self.subTest(position=position, observed=observed, minutes=minutes):
                self.assertGreaterEqual(rate, 0.0)
                self.assertLessEqual(rate, max(observed, prior) + 1e-9)

    def test_monotonic_in_sample_size_at_a_fixed_observed_rate(self):
        # More minutes at the same observed rate must pull the estimate steadily
        # closer to that observed rate, never further away.
        position, observed = "MID", 20.0
        prev_gap = abs(observed - config.FPL_DEFCON_PRIOR[position])
        for minutes in (90, 450, 900, 1800, 3000, 6000):
            rate = fpl_priors.shrink_defcon_rate(position, observed, minutes)
            gap = abs(observed - rate)
            self.assertLessEqual(gap, prev_gap + 1e-9)
            prev_gap = gap
