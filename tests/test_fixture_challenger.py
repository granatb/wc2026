import copy
import csv
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from games.fpl import fixture_challenger as model


def match(fixture, gw, day, home='A', away='B', score=(1, 0)):
    return [dict(player_id=team, fixture=str(fixture), gw=gw, team=team,
                 position='MID', home=side, kickoff=datetime(2024, 1, day, 15, tzinfo=timezone.utc),
                 total_points=points, minutes=90, expected_goals=.3, expected_assists=.1,
                 team_h_score=score[0], team_a_score=score[1])
            for team, side, points in [(home, True, 5), (away, False, 2)]]


class FixtureChallengerTests(unittest.TestCase):
    def setUp(self):
        self.rows = match(1, 1, 1) + match(2, 2, 8) + match(3, 2, 10, 'B', 'A')

    def test_target_and_second_leg_outcomes_never_enter_features(self):
        before = model.examples(self.rows)
        changed = copy.deepcopy(self.rows)
        for row in changed[2:]:
            row.update(total_points=99, minutes=0, expected_goals=10,
                       team_h_score=20, team_a_score=30)
        after = model.examples(changed)
        self.assertEqual([r['xs'] for r in before], [r['xs'] for r in after])
        self.assertNotEqual([r['y'] for r in before], [r['y'] for r in after])

    def test_double_legs_have_separate_home_and_opponent_context(self):
        row = next(r for r in model.examples(self.rows) if r['player_id'] == 'A')
        self.assertEqual(len(row['xs']), 2)
        self.assertEqual(row['xs'][0][:9], row['xs'][1][:9])
        self.assertEqual([x[9] for x in row['xs']], [1, 0])
        weights = [0]*len(model.FEATURES)
        weights[9] = 2
        self.assertEqual(model.predict_week(weights, row['xs']), 2)
        self.assertEqual(model.predict_week(weights, []), 0)
        with self.assertRaises(ValueError):
            model.predict_week(weights, [[1]])

    def test_postponed_lower_week_and_unfinished_matches_excluded(self):
        original = model.examples(self.rows)
        extra = match(4, 1, 12)
        self.assertEqual(original, model.examples(self.rows+extra))
        extra = match(4, 1, 8)
        for row in extra:
            row['kickoff'] -= timedelta(hours=4)  # Not finished before cutoff proxy.
        self.assertEqual(original, model.examples(self.rows+extra))

    def test_team_results_count_once_and_prior_is_shrunk(self):
        fixtures = model.fixture_index(self.rows)
        rate = model.strengths(fixtures, 2, datetime(2024,1,8,tzinfo=timezone.utc))
        self.assertAlmostEqual(rate('A')[0], (1+7)/6-1.4)
        self.assertAlmostEqual(rate('B')[1], (1+7)/6-1.4)
        self.assertEqual(rate('new'), (0, 0))

    def test_conflicting_or_one_sided_fixtures_rejected(self):
        changed = copy.deepcopy(self.rows)
        changed[0]['team_h_score'] = 9
        with self.assertRaises(ValueError):
            model.fixture_index(changed)
        with self.assertRaises(ValueError):
            model.fixture_index(self.rows[:1])

    def test_fit_is_training_only_and_deterministic(self):
        rows = model.examples(self.rows)
        weights = model.fit(rows, len(model.FEATURES))
        self.assertEqual(weights, model.fit(rows, len(model.FEATURES)))
        self.assertEqual(len(weights), len(model.FEATURES))
        self.assertTrue(all(abs(w) < 100 for w in weights))

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            model.stamp('2024-01-01T12:00:00')

    def test_only_identical_source_duplicates_are_removed(self):
        r = self.rows[0]
        raw = dict(r, element=r['player_id'], was_home='True',
                   kickoff_time=r['kickoff'].isoformat(), GW=r['gw'])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'rows.csv'
            def write(rows):
                with path.open('w') as fh:
                    writer = csv.DictWriter(fh, fieldnames=list(raw))
                    writer.writeheader()
                    writer.writerows(rows)
            write([raw, raw])
            self.assertEqual(len(model.read_rows(path)), 1)
            write([raw, dict(raw, total_points=100)])
            with self.assertRaises(ValueError):
                model.read_rows(path)
