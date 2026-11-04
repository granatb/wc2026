"""Recovered early forecasts and assumed teams must not become final predictions."""
import copy
import json
import unittest
from evmax import render
from core import forecast_archive
from games.fpl import continuity


class ContinuityDisplayTests(unittest.TestCase):
    def test_missing_model_week_still_shows_separate_account_and_consensus(self):
        rows = [dict(gw=9, model_realized=None, model_projected=None,
                     consensus_realized=36, consensus_projected=None,
                     account_realized=69, comparison_only=True,
                     model_label='Not published', consensus_label='Reconstructed',
                     duel_model=2, duel_consensus=5, json_path='/api/fpl/comparisons/gw8-gw9.json')]
        page = render._duel_table_html(None, rows, 10, section=render.FPL)
        self.assertIn('GW9', page)
        self.assertIn('Account', page)
        self.assertIn('69', page)
        self.assertIn('36', page)
        self.assertIn('Not published', page)
        self.assertNotIn('dl-win', page)
        self.assertNotIn('proj 0', page)

    def test_early_model_and_account_are_distinct_even_when_scores_match(self):
        rows = [dict(gw=8, model_realized=42, model_projected=64.1,
                     consensus_realized=32, consensus_projected=None,
                     account_realized=42, comparison_only=True,
                     model_label='21 Oct early', consensus_label='Reconstructed',
                     duel_model=2, duel_consensus=5, json_path='/api/fpl/comparisons/gw8-gw9.json')]
        page = render._duel_table_html(None, rows, 10, section=render.FPL)
        self.assertIn('21 Oct early', page)
        self.assertIn('Reconstructed', page)
        self.assertIn('proj 64.1', page)
        self.assertIn('Account', page)
        self.assertNotIn('dl-win', page)


class ContinuityEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.record = json.loads(continuity.PATH.read_text())
        self.board = json.loads(continuity.BOARD.read_text())
        self.plan = json.loads(continuity.PLAN.read_text())
        self.baseline = forecast_archive.load(7)

    def evaluate(self, record):
        return continuity.evaluate(record, self.board, self.plan, self.baseline)

    def test_captain_fallback_and_formation_legal_autosubs(self):
        result = self.evaluate(self.record)
        gw8, gw9 = result['comparisons']
        self.assertEqual(gw8['model_scoring']['total_so_far'], 42)
        self.assertEqual(gw8['model_scoring']['captain_effective'], 'Cole Palmer')
        self.assertEqual(gw8['model_scoring']['autosubs_applied'], [{'out':'Saka','in':'De Cuyper'}])
        palmer = next(p for p in gw8['model_scoring']['rows'] if p['name']=='Cole Palmer')
        self.assertEqual((palmer['points'],palmer['multiplier']), (-1,2))
        self.assertEqual(gw8['consensus_scoring']['total_so_far'],32)
        self.assertEqual(gw8['consensus_scoring']['autosubs_applied'],[{"out":"O'Reilly","in":"Diop"}])
        self.assertEqual(gw9['consensus_scoring']['total_so_far'],36)
        self.assertEqual(gw9['consensus_scoring']['autosubs_applied'],
                         [{'out':'João Pedro','in':'Diop'},{'out':'Guéhi','in':'Tzolis'}])
        self.assertIsNone(gw9['model_scoring'])
        self.assertIsNone(gw9['model_projected'])
        self.assertEqual((gw8['account']['points'],gw9['account']['points']),(42,69))
        self.assertEqual(result['early_forecast_grade']['n'],668)

    def test_uses_published_lineup_not_older_raw_squad_template(self):
        byname={p['name']:p for p in self.record['consensus_state']['squad']}
        self.assertTrue(byname['Guéhi']['is_starter'])
        self.assertTrue(byname['Slater']['is_starter'])
        self.assertTrue(byname['Calvert-Lewin']['is_vice'])
        self.assertFalse(byname['Shaw']['is_starter'])
        changed=copy.deepcopy(self.record);changed['consensus_state']['squad'][0]['is_starter']=False
        with self.assertRaisesRegex(ValueError,'last published selection'):self.evaluate(changed)

    def test_incomplete_or_unchecked_results_cannot_be_banked(self):
        changed=copy.deepcopy(self.record);changed['results']['8']['event']['data_checked']=False
        with self.assertRaisesRegex(ValueError,'finished and data_checked'):self.evaluate(changed)
        changed=copy.deepcopy(self.record);changed['results']['8']['live']['elements'].pop(0)
        with self.assertRaisesRegex(ValueError,'missing official'):self.evaluate(changed)

    def test_postdeadline_publication_or_tampered_grade_rejected(self):
        changed=copy.deepcopy(self.record);changed['early_publication']['checked_at']='2026-10-24T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'precede'):self.evaluate(changed)
        changed=copy.deepcopy(self.record);changed['evaluation']['comparisons'][1]['model_projected']=60
        with self.assertRaisesRegex(ValueError,'replay'):continuity.validate(changed)
        changed=copy.deepcopy(self.record);changed['early_publication']['sha256']['players']='bad'
        with self.assertRaisesRegex(ValueError,'hash'):continuity.validate(changed)

    def test_reconstruction_does_not_change_original_accuracy_or_duel(self):
        from evmax.fpl_build import fpl_track_ledger
        ledger=fpl_track_ledger()
        self.assertEqual([r['gw'] for r in ledger],list(range(1,8)))
        self.assertEqual((ledger[-1]['duel_model'],ledger[-1]['duel_consensus']),(2,5))
        self.assertEqual([r['gw'] for r in continuity.rows(self.record)],[8,9])


if __name__ == '__main__':
    unittest.main()
