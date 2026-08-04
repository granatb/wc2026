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


class TestHistoryProfile(unittest.TestCase):
    def test_profile_from_a_full_season(self):
        """A defender who kept 10 clean sheets in 38 starts carries a different
        defensive profile from one who kept 2 — bootstrap's per-90s do not say so."""
        hist = [{"season_name": "2025/26", "minutes": 3420, "starts": 38,
                 "clean_sheets": 10, "goals_conceded": 53, "bps": 593,
                 "expected_goals_conceded": 48.0, "total_points": 175}]
        p = fpl_priors.history_profile(hist)
        self.assertAlmostEqual(p["clean_sheet_rate"], 10 / 38, places=3)
        self.assertAlmostEqual(p["conceded_per90"], 53 * 90 / 3420, places=3)
        self.assertAlmostEqual(p["bps_per90"], 593 * 90 / 3420, places=3)

    def test_most_recent_season_wins(self):
        hist = [{"season_name": "2024/25", "minutes": 900, "starts": 10,
                 "clean_sheets": 1, "goals_conceded": 20, "bps": 100,
                 "expected_goals_conceded": 18.0, "total_points": 40},
                {"season_name": "2025/26", "minutes": 3420, "starts": 38,
                 "clean_sheets": 10, "goals_conceded": 53, "bps": 593,
                 "expected_goals_conceded": 48.0, "total_points": 175}]
        self.assertAlmostEqual(fpl_priors.history_profile(hist)["clean_sheet_rate"],
                               10 / 38, places=3)

    def test_thin_season_is_ignored(self):
        """A 90-minute cameo is not a season. Below the minutes floor the profile
        must report no data rather than an estimate from one appearance."""
        hist = [{"season_name": "2025/26", "minutes": 90, "starts": 1,
                 "clean_sheets": 1, "goals_conceded": 0, "bps": 12,
                 "expected_goals_conceded": 0.9, "total_points": 6}]
        self.assertIsNone(fpl_priors.history_profile(hist))

    def test_falls_back_to_an_earlier_full_season(self):
        """Injured last year, played the year before — the older season is real
        data and better than nothing."""
        hist = [{"season_name": "2024/25", "minutes": 3000, "starts": 34,
                 "clean_sheets": 9, "goals_conceded": 40, "bps": 500,
                 "expected_goals_conceded": 38.0, "total_points": 150},
                {"season_name": "2025/26", "minutes": 45, "starts": 0,
                 "clean_sheets": 0, "goals_conceded": 1, "bps": 3,
                 "expected_goals_conceded": 0.8, "total_points": 1}]
        p = fpl_priors.history_profile(hist)
        self.assertIsNotNone(p)
        self.assertEqual(p["season_name"], "2024/25")

    def test_no_history_is_none(self):
        """The cold-start case — must return None, never a fabricated profile."""
        self.assertIsNone(fpl_priors.history_profile([]))
        self.assertIsNone(fpl_priors.history_profile(None))

    def test_zero_starts_does_not_divide_by_zero(self):
        hist = [{"season_name": "2025/26", "minutes": 1200, "starts": 0,
                 "clean_sheets": 2, "goals_conceded": 18, "bps": 150,
                 "expected_goals_conceded": 16.0, "total_points": 60}]
        p = fpl_priors.history_profile(hist)
        self.assertIsNotNone(p)
        self.assertIsNone(p["clean_sheet_rate"])

    def test_the_minutes_floor_is_the_configured_one(self):
        def season(minutes):
            return [{"season_name": "2025/26", "minutes": minutes, "starts": 8,
                     "clean_sheets": 2, "goals_conceded": 10, "bps": 90,
                     "expected_goals_conceded": 9.0, "total_points": 30}]
        floor = config.FPL_HISTORY_MIN_MINUTES
        self.assertIsNotNone(fpl_priors.history_profile(season(floor)))
        self.assertIsNone(fpl_priors.history_profile(season(floor - 1)))

    def test_xgc_and_points_per_start(self):
        hist = [{"season_name": "2025/26", "minutes": 1800, "starts": 20,
                 "clean_sheets": 5, "goals_conceded": 24, "bps": 300,
                 "expected_goals_conceded": 26.0, "total_points": 80}]
        p = fpl_priors.history_profile(hist)
        self.assertAlmostEqual(p["xgc_per90"], 26.0 * 90 / 1800, places=4)
        self.assertAlmostEqual(p["points_per_start"], 4.0, places=4)


def _history(**kw):
    row = {"season_name": "2025/26", "minutes": 3060, "starts": 34,
           "clean_sheets": 12, "goals_conceded": 34, "bps": 680,
           "expected_goals_conceded": 33.0, "total_points": 160,
           "defensive_contribution": 340}
    row.update(kw)
    return row


class TestHistoryReachesThePriors(unittest.TestCase):
    """Which prior inputs the profile is allowed to move, and which it is not."""

    @staticmethod
    def _backfill(pid, history, defcon_per90=0.0, minutes=0):
        return {pid: {"defcon_per90": defcon_per90, "minutes": minutes,
                      "history_past": history}}

    def _build(self, player, backfill=None, team_matches=38):
        by_team = fpl_priors.build([player], team_matches=team_matches,
                                   defcon_backfill=backfill)
        return by_team[player["team"]][0]

    def test_a_zero_minute_player_with_history_is_not_a_blind_default(self):
        """Injured all last season: bootstrap says nothing, history says starter."""
        player = _player(id=5, minutes=0, starts=0, position="DEF",
                         defcon_per90=0.0)
        blind = self._build(dict(player))
        sharpened = self._build(dict(player),
                                self._backfill(5, [_history()]))
        self.assertAlmostEqual(blind.start_prob, fpl_priors._DEFAULT_START_PROB)
        self.assertAlmostEqual(sharpened.start_prob, 34 / 38, places=3)
        self.assertAlmostEqual(sharpened.exp_minutes, 3060 / 34, places=3)

    def test_a_zero_minute_player_with_no_history_keeps_the_blind_default(self):
        """The summer signing. No fabricated profile, no change at all."""
        player = _player(id=5, minutes=0, starts=0, position="DEF")
        got = self._build(dict(player), self._backfill(5, []))
        self.assertAlmostEqual(got.start_prob, fpl_priors._DEFAULT_START_PROB)
        self.assertAlmostEqual(got.exp_minutes, fpl_priors._DEFAULT_EXP_MINUTES)

    def test_history_never_overrides_a_real_bootstrap_sample(self):
        """Bootstrap minutes exist -> they win; the profile must not touch them."""
        player = _player(id=5, minutes=900, starts=10, position="DEF")
        plain = self._build(dict(player))
        withhist = self._build(dict(player), self._backfill(5, [_history()]))
        self.assertAlmostEqual(withhist.start_prob, plain.start_prob)
        self.assertAlmostEqual(withhist.exp_minutes, plain.exp_minutes)

    def test_history_does_not_touch_the_xg_derived_shares(self):
        """goal_share/assist_share stay bootstrap-xG derived (or the price prior
        for a cold start) -- the profile carries points, which are contaminated
        by scoring and must never become an attacking rate.

        Asserted as a RATIO between two team-mates, because shares are normalised
        within a club by start_prob: sharpening one player's minutes legitimately
        rescales everyone's share. What must not change is the relative ordering,
        which is exactly the xG-derived part."""
        mate = _player(id=6, name="Mate", full_name="Team Mate", minutes=2700,
                       starts=30, xg_per90=0.5, xa_per90=0.3)
        for minutes, starts in ((2700, 30), (0, 0)):
            player = _player(id=5, minutes=minutes, starts=starts)
            plain = fpl_priors.build([dict(player), dict(mate)], 38)["LIV"]
            hist = fpl_priors.build([dict(player), dict(mate)], 38,
                                    defcon_backfill=self._backfill(
                                        5, [_history()]))["LIV"]
            with self.subTest(minutes=minutes):
                self.assertAlmostEqual(hist[0].goal_share / hist[1].goal_share,
                                       plain[0].goal_share / plain[1].goal_share)
                self.assertAlmostEqual(hist[0].assist_share / hist[1].assist_share,
                                       plain[0].assist_share / plain[1].assist_share)

    def test_defcon_prefers_the_last_full_season_over_a_cameo(self):
        """The cached entry's rate comes off a 45-minute cameo; the profile's off
        the last real season. The profile's is the one that reaches the prior."""
        history = [_history(season_name="2024/25"),
                   _history(season_name="2025/26", minutes=45, starts=0,
                            defensive_contribution=5)]
        cameo_rate = 5 * 90 / 45.0
        got = self._build(_player(id=5, position="DEF", minutes=0, starts=0,
                                  defcon_per90=0.0),
                          self._backfill(5, history, defcon_per90=cameo_rate,
                                         minutes=45))
        expected = fpl_priors.shrink_defcon_rate("DEF", 340 * 90 / 3060.0, 3060)
        self.assertAlmostEqual(got.defcon_per90, expected, places=6)

    def test_live_bootstrap_defcon_still_beats_history(self):
        got = self._build(_player(id=5, position="DEF", defcon_per90=6.5),
                          self._backfill(5, [_history()]))
        self.assertAlmostEqual(got.defcon_per90, 6.5)

    def test_goalkeepers_stay_defcon_zero_with_history(self):
        got = self._build(_player(id=5, position="GK", defcon_per90=0.0),
                          self._backfill(5, [_history()]))
        self.assertEqual(got.defcon_per90, 0.0)

    def test_cold_start_flag_is_unchanged_by_history(self):
        """The flag tracks bootstrap history and stays exactly as it was."""
        player = _player(id=5, minutes=0, starts=0)
        _by_team, flags = fpl_priors.build_with_flags(
            [player], team_matches=38,
            defcon_backfill=self._backfill(5, [_history()]))
        self.assertEqual([f["reason"] for f in flags], ["no_pl_history"])

    def test_history_start_rate_ignores_this_seasons_match_count(self):
        """Mid-season, team_matches counts THIS season. A past season is always
        38 matches -- rating 34 starts over 3 would print a nonsense 1.0."""
        got = self._build(_player(id=5, minutes=0, starts=0),
                          self._backfill(5, [_history()]), team_matches=3)
        self.assertAlmostEqual(got.start_prob, 34 / 38, places=3)

    def test_an_unavailable_player_is_still_gated_to_zero(self):
        got = self._build(_player(id=5, minutes=0, starts=0, status="i"),
                          self._backfill(5, [_history()]))
        self.assertEqual(got.start_prob, 0.0)

    def test_a_stale_season_does_not_promote_a_backup_to_a_starter(self):
        """A keeper whose last real season was three years ago is not evidence
        about his role today. Real case: Meslier, 34 starts in 2022/23, now a
        squad keeper -- the minutes model must leave him on the default."""
        backfill = {5: {"defcon_per90": 0.0, "minutes": 0,
                        "history_past": [_history(season_name="2022/23")]},
                    6: {"defcon_per90": 0.0, "minutes": 0,
                        "history_past": [_history(season_name="2025/26")]}}
        got = self._build(_player(id=5, minutes=0, starts=0), backfill)
        self.assertAlmostEqual(got.start_prob, fpl_priors._DEFAULT_START_PROB)

    def test_the_season_before_last_still_counts(self):
        """A promoted club's regulars last played in the Premier League a season
        early -- that IS evidence, and is the main population this helps."""
        backfill = {5: {"defcon_per90": 0.0, "minutes": 0,
                        "history_past": [_history(season_name="2024/25")]},
                    6: {"defcon_per90": 0.0, "minutes": 0,
                        "history_past": [_history(season_name="2025/26")]}}
        got = self._build(_player(id=5, minutes=0, starts=0), backfill)
        self.assertAlmostEqual(got.start_prob, 34 / 38, places=3)

    def test_a_season_with_no_starts_column_is_declined(self):
        """FPL published no `starts` before 2022/23, so a 3000-minute season
        reads 0 there. Zero must not become a zero start probability."""
        got = self._build(
            _player(id=5, minutes=0, starts=0),
            self._backfill(5, [_history(starts=0, minutes=3000)]))
        self.assertAlmostEqual(got.start_prob, fpl_priors._DEFAULT_START_PROB)
        self.assertAlmostEqual(got.exp_minutes, fpl_priors._DEFAULT_EXP_MINUTES)


class TestSeasonRecency(unittest.TestCase):
    def test_season_start_year(self):
        self.assertEqual(fpl_priors.season_start_year("2024/25"), 2024)
        self.assertIsNone(fpl_priors.season_start_year(None))
        self.assertIsNone(fpl_priors.season_start_year("not a season"))

    def test_latest_season_year_reads_the_feed_not_a_constant(self):
        backfill = {1: {"history_past": [_history(season_name="2019/20")]},
                    2: {"history_past": [_history(season_name="2025/26")]}}
        self.assertEqual(fpl_priors.latest_season_year(backfill), 2025)

    def test_latest_season_year_of_nothing_is_none(self):
        self.assertIsNone(fpl_priors.latest_season_year(None))
        self.assertIsNone(fpl_priors.latest_season_year({}))
        self.assertIsNone(fpl_priors.latest_season_year({1: {"history_past": []}}))

    def test_recency_window(self):
        back = config.FPL_HISTORY_MAX_SEASONS_BACK
        latest = 2025
        for offset, expected in ((0, True), (back, True), (back + 1, False)):
            profile = {"season_name": f"{latest - offset}/xx"}
            with self.subTest(offset=offset):
                self.assertEqual(
                    fpl_priors.profile_is_recent(profile, latest), expected)

    def test_no_profile_or_no_latest_is_never_recent(self):
        self.assertFalse(fpl_priors.profile_is_recent(None, 2025))
        self.assertFalse(fpl_priors.profile_is_recent({"season_name": "2025/26"},
                                                      None))


class TestDefconIgnoresUnrecordedHistory(unittest.TestCase):
    """FPL published no `defensive_contribution` before 2024/25, so an older
    season reads 0 for everyone. Believing that zero demotes real defensive
    midfielders (Endo: 9.59 -> 1.08 before this guard)."""

    def _rate(self, history, entry_rate, entry_minutes, position="MID"):
        pid = 5
        backfill = {pid: {"defcon_per90": entry_rate, "minutes": entry_minutes,
                          "history_past": history}}
        prior = fpl_priors.build(
            [_player(id=pid, position=position, minutes=0, starts=0,
                     defcon_per90=0.0)],
            team_matches=38, defcon_backfill=backfill)["LIV"][0]
        return prior.defcon_per90

    def test_a_zero_defcon_season_falls_back_to_the_cached_rate(self):
        history = [_history(season_name="2023/24", minutes=1714, starts=20,
                            defensive_contribution=0),
                   _history(season_name="2025/26", minutes=170, starts=1,
                            defensive_contribution=23)]
        cached = fpl_priors.shrink_defcon_rate("MID", 23 * 90 / 170.0, 170)
        self.assertAlmostEqual(self._rate(history, 23 * 90 / 170.0, 170), cached,
                               places=6)

    def test_a_recorded_full_season_still_wins_over_a_cameo(self):
        history = [_history(season_name="2024/25", minutes=3060, starts=34,
                            defensive_contribution=340),
                   _history(season_name="2025/26", minutes=45, starts=0,
                            defensive_contribution=5)]
        expected = fpl_priors.shrink_defcon_rate("MID", 340 * 90 / 3060.0, 3060)
        self.assertAlmostEqual(self._rate(history, 5 * 90 / 45.0, 45), expected,
                               places=6)
