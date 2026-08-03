import unittest
from datetime import datetime, timezone

from core import fixtures


def _fx(match_id, home, away, gw, hour=15):
    return fixtures.Fixture(
        match_id=match_id, home=home, away=away,
        kickoff=datetime(2026, 8, 22, hour, 0, tzinfo=timezone.utc),
        stage="GW", fantasy_round=gw, neutral=False,
    )


class TestBlanksAndDoubles(unittest.TestCase):
    """A team can play 0 or 2 times in one gameweek. Callers must not assume 1."""

    def setUp(self):
        # GW7: LIV plays twice (double), TOT plays not at all (blank).
        self.added = [
            _fx("m1", "LIV", "ARS", 7, 12),
            _fx("m2", "LIV", "CHE", 7, 17),
            _fx("m3", "MCI", "NEW", 7, 15),
        ]
        fixtures.SCHEDULE.extend(self.added)
        self.addCleanup(lambda: [fixtures.SCHEDULE.remove(f) for f in self.added])

    def test_double_gameweek_returns_both_fixtures(self):
        self.assertEqual(len(fixtures.fixtures_for_team("LIV", 7)), 2)

    def test_blank_gameweek_returns_empty_list(self):
        self.assertEqual(fixtures.fixtures_for_team("TOT", 7), [])

    def test_teams_with_blank_lists_the_non_players(self):
        playing = {"LIV", "ARS", "CHE", "MCI", "NEW"}
        blanks = fixtures.teams_with_blank(7, all_teams=playing | {"TOT", "EVE"})
        self.assertEqual(blanks, {"TOT", "EVE"})

    def test_teams_with_double_lists_the_twice_players(self):
        self.assertEqual(fixtures.teams_with_double(7), {"LIV"})

    def test_fixture_count_by_team(self):
        counts = fixtures.fixture_count_by_team(7)
        self.assertEqual(counts["LIV"], 2)
        self.assertEqual(counts["MCI"], 1)
        self.assertNotIn("TOT", counts)


class TestGameweekDeadline(unittest.TestCase):
    def tearDown(self):
        fixtures.DEADLINES.clear()

    def test_lock_time_prefers_the_registered_deadline_over_first_kickoff(self):
        added = [_fx("m9", "LIV", "ARS", 9, 18)]
        fixtures.SCHEDULE.extend(added)
        self.addCleanup(lambda: [fixtures.SCHEDULE.remove(f) for f in added])

        deadline = datetime(2026, 8, 21, 17, 30, tzinfo=timezone.utc)
        fixtures.set_deadline(9, deadline)
        # first kickoff is 18:00 the next day; the deadline is what locks the round
        self.assertEqual(fixtures.round_lock_time(9), deadline)

    def test_lock_time_falls_back_to_first_kickoff_when_no_deadline_known(self):
        added = [_fx("m10", "LIV", "ARS", 10, 13)]
        fixtures.SCHEDULE.extend(added)
        self.addCleanup(lambda: [fixtures.SCHEDULE.remove(f) for f in added])
        self.assertEqual(fixtures.round_lock_time(10).hour, 13)


class TestByRoundStageFilter(unittest.TestCase):
    """SCHEDULE holds both competitions in one list and buckets on fantasy_round
    alone, so World Cup round 1 and FPL gameweek 1 collide. `stage` is the
    competition discriminator."""

    def setUp(self):
        # A WC-style tie and an FPL fixture sharing one fantasy_round. World Cup
        # rows carry ESPN status strings for their stage; FPL rows carry "GW".
        self.saved = list(fixtures.SCHEDULE)
        fixtures.SCHEDULE.clear()
        fixtures.SCHEDULE.extend([
            _fx("gw-1", "LIV", "ARS", 1),
            fixtures.Fixture(
                match_id="wc-1", home="Mexico", away="South Africa",
                kickoff=datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc),
                stage="STATUS_FULL_TIME", fantasy_round=1, neutral=False),
        ])

    def tearDown(self):
        fixtures.SCHEDULE.clear()
        fixtures.SCHEDULE.extend(self.saved)

    def test_unfiltered_returns_every_competition(self):
        """The default must not change: World Cup call sites rely on it."""
        ids = sorted(f.match_id for f in fixtures.by_round(1))
        self.assertEqual(ids, ["gw-1", "wc-1"])

    def test_stage_filter_narrows_to_one_competition(self):
        got = fixtures.by_round(1, stage=fixtures.FPL_STAGE)
        self.assertEqual([f.match_id for f in got], ["gw-1"])

    def test_stage_filter_selects_the_world_cup_side_too(self):
        """Not FPL-specific: the parameter is a plain stage filter."""
        got = fixtures.by_round(1, stage="STATUS_FULL_TIME")
        self.assertEqual([f.match_id for f in got], ["wc-1"])

    def test_stage_filter_on_an_absent_stage_is_empty(self):
        self.assertEqual(fixtures.by_round(1, stage="NOPE"), [])

    def test_stage_filter_does_not_cross_rounds(self):
        self.assertEqual(fixtures.by_round(2, stage=fixtures.FPL_STAGE), [])
