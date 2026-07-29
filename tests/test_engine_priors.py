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
