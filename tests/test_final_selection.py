"""The team result can follow a later publication without changing forecasts."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from core import forecast_archive
from evmax import fpl_build
from games.fpl import final_selection


class FinalSelectionTests(unittest.TestCase):
    def setUp(self):
        self.archive = forecast_archive.load(7)
        self.grade = json.loads(Path('evmax/assets/accuracy/gw7.json').read_text())
        self.record = json.loads((final_selection.ROOT / 'gw7.json').read_text())

    def test_later_predeadline_selection_scores_captain_and_autosub(self):
        result = final_selection.validate(self.record, self.grade, self.archive)
        self.assertEqual(result['projected'], 61.80)
        self.assertEqual(result['realized_official'], 59)
        self.assertEqual(result['scoring']['captain_effective'], 'Saka')
        self.assertEqual(result['scoring']['autosubs_applied'],
                         [{'out': 'Gibbs-White', 'in': 'Thomas'}])
        rows = {row['name']: row for row in result['scoring']['rows']}
        self.assertEqual((rows['Saka']['points'], rows['Saka']['multiplier']), (3, 2))
        self.assertEqual(rows['Thiago']['multiplier'], 1)
        self.assertEqual(rows['Thomas']['multiplier'], 1)

    def test_ledger_uses_final_selection_and_retains_original_grade(self):
        before = copy.deepcopy(self.grade)
        row = next(row for row in fpl_build.fpl_track_ledger() if row['gw'] == 7)
        self.assertEqual((row['model_projected'], row['model_realized']), (61.8, 59))
        self.assertEqual(row['baseline_model_realized'], 53)
        self.assertEqual(row['baseline_model_projected'], 57.28)
        self.assertEqual(row['mae_ours'], 1.08)
        self.assertEqual(self.grade, before)
        self.assertEqual(self.grade['squads']['our-squad']['realized_official'], 53)
        with patch.object(final_selection, 'ROOT', Path('/nonexistent-selection-records')):
            old = next(row for row in fpl_build.fpl_track_ledger() if row['gw'] == 7)
        self.assertEqual((old['model_projected'], old['model_realized']), (57.28, 53))

    def test_rejects_postdeadline_selection_and_backdated_correction(self):
        for key, value in [('published_at', '2026-10-18T12:00:00Z'),
                           ('recorded_at', '2026-10-14T12:00:00Z')]:
            with self.subTest(key=key):
                record = copy.deepcopy(self.record)
                record[key] = value
                with self.assertRaises(ValueError):
                    final_selection.validate(record, self.grade, self.archive)

    def test_rejects_score_forecast_or_finality_tampering(self):
        mutations = [lambda r: r.update(realized_official=60),
                     lambda r: r.update(projected=62),
                     lambda r: r.update(forecast_sha256='0' * 64),
                     lambda r: r['results']['event'].update(data_checked=False),
                     lambda r: r['state']['squad'][0].update(player_id=999999)]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                record = copy.deepcopy(self.record)
                mutate(record)
                with self.assertRaises(ValueError):
                    final_selection.validate(record, self.grade, self.archive)

    def test_replay_uses_vice_if_captain_does_not_play(self):
        results = copy.deepcopy(self.record['results'])
        saka = next(p for p in self.record['state']['squad'] if p['name'] == 'Saka')
        stats = next(p['stats'] for p in results['live']['elements']
                     if p['id'] == saka['player_id'])
        stats.update(minutes=0, total_points=0)
        result = final_selection.replay(self.record['state'], results, self.archive)
        self.assertEqual(result['captain_effective'], 'Thiago')
        rows = {row['name']: row for row in result['rows']}
        self.assertEqual(rows['Thiago']['multiplier'], 2)
        self.assertEqual(rows['Saka']['multiplier'], 0)


if __name__ == '__main__':
    unittest.main()
