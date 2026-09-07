import csv
import random
import tempfile
import unittest
from pathlib import Path
from scripts import evaluate_challenger as challenger


class ChallengerTests(unittest.TestCase):
    def write(self, path, future_points=1):
        fields = ['element','GW','position','total_points','minutes','expected_goals','expected_assists','kickoff_time']
        with path.open('w', newline='') as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for gw in range(1, 10):
                writer.writerow(dict(element=1, GW=gw, position='MID',
                    total_points=future_points if gw == 9 else gw, minutes=90,
                    expected_goals=.2, expected_assists=.1, kickoff_time=f'2024-01-{gw:02d}T12:00:00Z'))

    def test_future_outcomes_cannot_change_prior_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp)/'a.csv', Path(tmp)/'b.csv'
            self.write(first, 1)
            self.write(second, 999)
            a, b = challenger.examples(first), challenger.examples(second)
            self.assertEqual([r['x'] for r in a], [r['x'] for r in b])
            self.assertEqual(a[0]['x'][1], 4.5)  # GW3–6 points; GW7 outcome absent
            self.assertNotEqual(a[-1]['y'], b[-1]['y'])

    def test_overlapping_training_and_test_seasons_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'a.csv'
            self.write(path)
            with self.assertRaisesRegex(ValueError, 'training must end'):
                challenger.run(path, path)

    def test_solver_recovers_known_linear_signal(self):
        rng = random.Random(15)
        train = []
        for _ in range(100):
            x = [1] + [rng.random() for _ in range(8)]
            train.append({'x': x, 'y': 2 + 3*x[1]})
        weights = challenger.fit(train, ridge=0)
        self.assertAlmostEqual(weights[0], 2)
        self.assertAlmostEqual(weights[1], 3)
        for w in weights[2:]:
            self.assertAlmostEqual(w, 0)
