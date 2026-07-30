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


class TestPerMatchHook(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.Fixture(
            "PRIORS3", "Alphaland", "Betaland",
            kickoff=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc),
            stage="GW", fantasy_round=903, neutral=False,
            lam_home=1.4, lam_away=1.2,
        )
        fixtures.SCHEDULE.append(self.fx)
        self.addCleanup(lambda: fixtures.SCHEDULE.remove(self.fx))
        self.squads = {
            "Alphaland": [ratings.PlayerPrior("A1", "Alphaland", "FWD",
                                              start_prob=1.0, exp_minutes=90,
                                              goal_share=0.4)],
            "Betaland": [ratings.PlayerPrior("B1", "Betaland", "DEF",
                                             start_prob=1.0, exp_minutes=90)],
        }

    def test_hook_fires_once_per_match_per_sim(self):
        calls = []
        engine_events.simulate_round(
            903, sims=50, priors=lambda t: self.squads.get(t, []),
            per_match_hook=lambda match_id, rows, sim_index: calls.append(
                (match_id, len(rows))))
        self.assertEqual(len(calls), 50)
        self.assertEqual({c[0] for c in calls}, {"PRIORS3"})

    def test_hook_receives_both_sides_in_one_call(self):
        seen = []
        engine_events.simulate_round(
            903, sims=20, priors=lambda t: self.squads.get(t, []),
            per_match_hook=lambda _mid, rows, _sim_index: seen.append(
                {r[0] for r in rows}))
        # every call carries players from both teams
        self.assertTrue(all(names == {"A1", "B1"} for names in seen))

    def test_hook_rows_carry_the_documented_field_order(self):
        captured = []
        engine_events.simulate_round(
            903, sims=5, priors=lambda t: self.squads.get(t, []),
            per_match_hook=lambda _mid, rows, _sim_index: captured.extend(rows))
        (name, position, goals, assists, minutes, clean_sheet, conceded, saves,
         yellow, red, defcon) = captured[0]
        self.assertIn(name, {"A1", "B1"})
        self.assertIn(position, {"FWD", "DEF"})
        self.assertIsInstance(goals, int)
        self.assertIsInstance(clean_sheet, bool)
        self.assertGreaterEqual(minutes, 0)
        # Neither prior sets defcon_per90, so the passed-through count is 0.
        self.assertEqual(defcon, 0)

    def test_hook_receives_the_sim_index_as_a_third_argument(self):
        seen = []
        engine_events.simulate_round(
            903, sims=10, priors=lambda t: self.squads.get(t, []),
            per_match_hook=lambda _mid, _rows, sim_index: seen.append(sim_index))
        self.assertEqual(seen, list(range(10)))

    def test_sim_index_is_shared_across_two_matches_in_the_same_sim(self):
        # A double-gameweek proxy: two independent fixtures in the SAME round.
        # A hook that groups by sim_index must see both matches land on the
        # same index for a given sim, not on two different ones.
        fx2 = fixtures.Fixture(
            "PRIORS3B", "Gammaland", "Deltaland",
            kickoff=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc),
            stage="GW", fantasy_round=903, neutral=False,
            lam_home=1.3, lam_away=1.0,
        )
        fixtures.SCHEDULE.append(fx2)
        self.addCleanup(lambda: fixtures.SCHEDULE.remove(fx2))
        squads = dict(self.squads)
        squads["Gammaland"] = [ratings.PlayerPrior(
            "C1", "Gammaland", "FWD", start_prob=1.0, exp_minutes=90)]
        squads["Deltaland"] = [ratings.PlayerPrior(
            "D1", "Deltaland", "DEF", start_prob=1.0, exp_minutes=90)]

        seen: dict = {}
        engine_events.simulate_round(
            903, sims=15, priors=lambda t: squads.get(t, []),
            per_match_hook=lambda match_id, _rows, sim_index: seen.setdefault(
                sim_index, set()).add(match_id))
        self.assertEqual(len(seen), 15)
        self.assertTrue(all(v == {"PRIORS3", "PRIORS3B"} for v in seen.values()))

    def test_no_hook_is_the_default_and_changes_nothing(self):
        players, _ = engine_events.simulate_round(
            903, sims=50, priors=lambda t: self.squads.get(t, []))
        self.assertIn("A1", players)
