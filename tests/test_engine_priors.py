import unittest
from datetime import datetime, timezone

from core import engine_events, fixtures, ratings


class TestPriorsInjection(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.Fixture(
            "PRIORS1", "Alphaland", "Betaland",
            kickoff=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc),
            stage="GW", fantasy_round=901, neutral=False,
            lam_home=1.6, lam_away=1.1,
        )
        fixtures.SCHEDULE.append(self.fx)
        self.addCleanup(lambda: fixtures.SCHEDULE.remove(self.fx))

        self.squads = {
            "Alphaland": [
                ratings.PlayerPrior("A-Striker", "Alphaland", "FWD",
                                    start_prob=1.0, exp_minutes=90, goal_share=0.5),
                ratings.PlayerPrior("A-Keeper", "Alphaland", "GK",
                                    start_prob=1.0, exp_minutes=90),
            ],
            "Betaland": [
                ratings.PlayerPrior("B-Striker", "Betaland", "FWD",
                                    start_prob=1.0, exp_minutes=90, goal_share=0.5),
            ],
        }

    def test_injected_priors_are_used_instead_of_the_ratings_registry(self):
        players, _matches = engine_events.simulate_round(
            901, sims=500, priors=lambda team: self.squads.get(team, []))
        self.assertEqual(set(players), {"A-Striker", "A-Keeper", "B-Striker"})

    def test_injected_priors_produce_goals_for_the_favourite(self):
        players, _matches = engine_events.simulate_round(
            901, sims=2000, priors=lambda team: self.squads.get(team, []))
        # Alphaland has the higher lambda, so its striker should out-score Betaland's
        self.assertGreater(players["A-Striker"].mean("goals"),
                           players["B-Striker"].mean("goals"))

    def test_default_priors_come_from_the_registry_not_the_injection(self):
        # With no priors= argument the engine must consult ratings.players_for_team.
        # Assert the call happens rather than asserting on registry CONTENTS, which
        # depend on data/players.json (gitignored, so absent on a fresh clone).
        from unittest import mock
        with mock.patch.object(ratings, "players_for_team",
                               return_value=[]) as spy:
            engine_events.simulate_round(901, sims=10)
        spy.assert_any_call("Alphaland")
        spy.assert_any_call("Betaland")


class TestAdditiveSampleFields(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.Fixture(
            "PRIORS2", "Alphaland", "Betaland",
            kickoff=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc),
            stage="GW", fantasy_round=902, neutral=False,
            lam_home=1.5, lam_away=1.5,
        )
        fixtures.SCHEDULE.append(self.fx)
        self.addCleanup(lambda: fixtures.SCHEDULE.remove(self.fx))

        self.squads = {
            "Alphaland": [
                ratings.PlayerPrior("A-Keeper", "Alphaland", "GK",
                                    start_prob=1.0, exp_minutes=90, saves_per90=3.0),
                ratings.PlayerPrior("A-Back", "Alphaland", "DEF",
                                    start_prob=1.0, exp_minutes=90, defcon_per90=9.0),
            ],
            "Betaland": [
                ratings.PlayerPrior("B-Striker", "Betaland", "FWD",
                                    start_prob=1.0, exp_minutes=90, goal_share=0.5),
            ],
        }
        self.players, _ = engine_events.simulate_round(
            902, sims=1500, priors=lambda t: self.squads.get(t, []))

    def test_raw_conceded_is_recorded_separately_from_conc_beyond(self):
        back = self.players["A-Back"]
        # conc_beyond is max(0, ga-1) (FIFA); conceded is the raw count (FPL needs ga/2)
        self.assertGreater(back.conceded, back.conc_beyond)

    def test_played_60_is_tracked_and_never_exceeds_played(self):
        back = self.players["A-Back"]
        self.assertGreater(back.played_60, 0)
        self.assertLessEqual(back.played_60, back.played)

    def test_save_samples_collected_for_goalkeepers_only(self):
        self.assertTrue(self.players["A-Keeper"].save_samples)
        self.assertFalse(self.players["B-Striker"].save_samples)

    def test_defcon_samples_collected_only_when_a_rate_is_set(self):
        self.assertTrue(self.players["A-Back"].defcon_samples)
        self.assertFalse(self.players["B-Striker"].defcon_samples)

    def test_defcon_samples_centre_on_the_configured_rate(self):
        counts = self.players["A-Back"].defcon_samples
        mean = sum(counts) / len(counts)
        self.assertGreater(mean, 6.0)    # rate 9.0/90 over ~90 minutes
        self.assertLess(mean, 12.0)

    def test_event_means_exposes_the_new_fields(self):
        means = engine_events.event_means(self.players)
        row = means["A-Back"]
        self.assertIn("conceded", row)
        self.assertIn("played_60", row)
