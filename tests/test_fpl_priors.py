import unittest

import config
from core import fpl_priors, ratings


def setUpModule():
    """Synthetic fixtures must not inherit real players' careers.

    `_player` hands out `id: 1`, which is a real footballer in the preseason
    snapshot. Once minutes_model started blending that snapshot in, three tests
    began asserting against a stranger's 38-game season instead of the numbers
    written into the fixture. Tests that want history install it explicitly.
    """
    global _no_history
    _no_history = fpl_priors.preseason_rates_override({})
    _no_history.__enter__()


def tearDownModule():
    _no_history.__exit__(None, None, None)


_no_history = None


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

    def test_nailed_starter_survives_the_season_rollover(self):
        """The GW2 bug: one start out of a 38-match divisor read as 2.6%.

        At the rollover the feed's `starts`/`minutes` reset to this season, so a
        nailed starter looked like a fringe player and no forward cleared the
        0.75 minutes floor -- the squad builder could not fill an XI, and the
        order book quietly ranked by "has a research note" instead of football.
        """
        p = _player(minutes=90, starts=1, id=4242)
        history = {"4242": {"starts": 34, "minutes": 3000}}
        with fpl_priors.preseason_rates_override(history):
            sp, mins = fpl_priors.minutes_model(p, team_matches=1)
        self.assertGreater(sp, 0.75)
        self.assertGreater(mins, 80)

    def test_live_sample_outweighs_history_as_it_accumulates(self):
        """A dropped starter must not hide behind last season forever."""
        history = {"4242": {"starts": 34, "minutes": 3000}}
        benched = _player(minutes=0, starts=0, id=4242)
        with fpl_priors.preseason_rates_override(history):
            early, _ = fpl_priors.minutes_model(benched, team_matches=2)
            late, _ = fpl_priors.minutes_model(
                _player(minutes=200, starts=1, id=4242), team_matches=20)
        self.assertGreater(early, 0.8)      # two blanks barely move a full season
        self.assertLess(late, early)        # 20 matches of evidence does

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


class TestHistoryBlend(unittest.TestCase):
    """Once the season starts, bootstrap's per-90 fields describe the CURRENT
    season only. After gameweek 1 that is a one-game sample: read literally it
    projected De Cuyper at 11.97 xPts off a single goal while B.Fernandes, on
    3,065 minutes of elite history, fell to 5.83. Rates are therefore blended
    with the committed preseason snapshot, weighted by minutes."""

    def test_blend_is_minutes_weighted(self):
        # 3000 historical minutes at 0.50, 90 live minutes at 2.00
        out = fpl_priors.blend_rate(0.50, 3000, 2.00, 90)
        self.assertAlmostEqual(out, (0.50 * 3000 + 2.00 * 90) / 3090, places=9)
        self.assertLess(out, 0.60)      # history dominates in August

    def test_live_sample_takes_over_as_it_grows(self):
        early = fpl_priors.blend_rate(0.50, 3000, 2.00, 90)
        late = fpl_priors.blend_rate(0.50, 3000, 2.00, 3000)
        self.assertGreater(late, early)
        self.assertAlmostEqual(late, 1.25, places=9)

    def test_no_history_and_no_live_returns_the_live_value(self):
        self.assertEqual(fpl_priors.blend_rate(None, 0, 0.4, 0), 0.4)

    def test_rates_blend_when_the_snapshot_has_the_player(self):
        from unittest import mock
        snapshot = {"426": {"expected_goals_per_90": 0.30,
                            "expected_assists_per_90": 0.40, "minutes": 3000}}
        player = {"id": 426, "minutes": 90, "xg_per90": 3.0, "xa_per90": 0.0,
                  "now_cost": 120, "element_type": 3, "starts": 1}
        with mock.patch.object(fpl_priors, "_preseason_cache", snapshot):
            xg, xa = fpl_priors._rates(player)
        self.assertLess(xg, 0.4)        # the one-game spike is damped, not obeyed
        self.assertGreater(xg, 0.29)
        # History still dominates: 3000 minutes of 0.40 xA against 90 minutes of
        # 0.0 lands near 0.36, not near zero. It is not exactly 0.40 because the
        # price prior is a permanent pseudo-sample (PRIOR_MINUTES) rather than a
        # fallback, which is what stops a 65-minute cameo from defining a rate.
        self.assertGreater(xa, 0.34)
        self.assertLess(xa, 0.40)

    def test_one_hot_cameo_cannot_define_a_rate(self):
        """Emersonn, 2026-08-27: promoted with Ipswich, so no history at all.

        65 minutes of gameweek 1 at 1.14 xG/90 -- a higher rate than Haaland has
        ever sustained -- made him the top forward in the order book and the
        transfer optimizer's first choice over every alternative. One substitute
        appearance is not evidence of a rate.
        """
        from unittest import mock
        player = {"id": 77777, "minutes": 65, "xg_per90": 1.14, "xa_per90": 0.08,
                  "now_cost": 55, "element_type": 4, "starts": 1}
        with mock.patch.object(fpl_priors, "_preseason_cache", {"_missing": True}):
            xg, _ = fpl_priors._rates(player)
            sp, _mins = fpl_priors.minutes_model(player, team_matches=1)
        self.assertLess(xg, 0.6)        # nowhere near the raw 1.14
        self.assertGreater(xg, 0.2)     # but the cameo is not ignored either
        self.assertLess(sp, 0.75)       # one start out of one is not "nailed"
        self.assertGreater(sp, 0.35)

    def test_genuine_cold_start_still_uses_the_price_prior(self):
        from unittest import mock
        player = {"id": 99999, "minutes": 0, "xg_per90": 0.0, "xa_per90": 0.0,
                  "now_cost": 100, "element_type": 4, "starts": 0}
        with mock.patch.object(fpl_priors, "_preseason_cache", {"_missing": True}):
            xg, _ = fpl_priors._rates(player)
        self.assertGreater(xg, 0.0)     # priced prior, not a zero
