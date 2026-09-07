import copy
import unittest

from games.fpl import experiments as ledger, experiment_analysis as analysis
from test_fpl_experiments import first, fixtures


def grade():
    record = first()
    for sub in record['arms'].values():
        sub.update(model_identity_sha256='a'*64, model_identity_disclosed=True)
    record['bootstrap']['events'].insert(0, dict(id=3, finished=True))
    record['bootstrap']['elements'][0]['minutes'] = 90
    record['bootstrap']['elements'][1]['minutes'] = 10
    results = dict(gameweek=4, fetched_at='2026-09-14T12:00:00Z',
        fixtures=[dict(f, finished=True) for f in fixtures()],
        live=dict(elements=[dict(id=i, stats=dict(minutes=90, total_points=2)) for i in range(1,21)]))
    return record, results, ledger.grade_week(record, results)


class AnalysisTests(unittest.TestCase):
    def test_cohort_membership_cannot_follow_realized_minutes(self):
        record, results, before = grade()
        self.assertEqual(before['cohort_ids']['prior_60plus'], [1])
        results['live']['elements'][0]['stats']['minutes'] = 0
        after = ledger.grade_week(record, results)
        self.assertEqual(before['cohort_ids'], after['cohort_ids'])
        for arm in before['arms']:
            self.assertEqual(before['arms'][arm]['cohorts']['prior_60plus']['n'], 1)

    def test_empty_cohorts_are_unavailable_not_zero_accuracy(self):
        record, results, _ = grade()
        record['bootstrap']['events'][0]['finished'] = False
        result = analysis.summarize([ledger.grade_week(record, results)])
        self.assertIsNone(result['cohorts']['prior_60plus']['market']['rmse'])
        self.assertEqual(result['cohorts']['prior_60plus']['market']['player_gameweeks'], 0)

    def test_paired_differences_are_equal_week_not_player_weighted(self):
        _, _, g = grade()
        a, b = copy.deepcopy(g), copy.deepcopy(g)
        b['gameweek'] = 5
        for arm in a['arms']:
            a['arms'][arm]['cohorts']['all_players'].update(n=1, mse=4 if arm == 'market' else 1)
            b['arms'][arm]['cohorts']['all_players'].update(n=1000, mse=1)
        report = analysis.summarize([a,b])
        pair = next(p for p in report['comparisons'] if p['cohort']=='all_players' and p['left']=='market')
        self.assertEqual(pair['mean_mse_difference'], 1.5)
        self.assertIsNone(pair['interval95'])

    def test_intervals_require_consecutive_weeks_and_fixed_versions(self):
        _, _, g = grade()
        grades = [dict(copy.deepcopy(g), gameweek=gw) for gw in range(1,13)]
        result = analysis.summarize(grades)
        pair = result['comparisons'][0]
        self.assertEqual(pair['status'], 'exploratory_interval')
        self.assertEqual(pair['interval95'], [0,0])
        grades[-1]['gameweek'] = 14
        self.assertEqual(analysis.summarize(grades)['comparisons'][0]['status'], 'nonconsecutive_gameweeks')
        grades[-1]['gameweek'] = 12
        grades[-1]['arms'][pair['left']]['model_version'] = 'changed'
        self.assertEqual(analysis.summarize(grades)['comparisons'][0]['status'], 'mixed_model_versions')
        grades[-1]['arms'][pair['left']]['model_version'] = g['arms'][pair['left']]['model_version']
        grades[-1]['arms'][pair['left']]['model_identity_sha256'] = 'b'*64
        self.assertEqual(analysis.summarize(grades)['comparisons'][0]['status'], 'mixed_model_versions')
        grades[-1]['arms'][pair['left']]['model_identity_sha256'] = 'a'*64
        grades[-1]['arms'][pair['left']]['model_identity_disclosed'] = False
        self.assertEqual(analysis.summarize(grades)['comparisons'][0]['status'], 'undisclosed_model_revision')

    def test_deterministic_block_interval_and_unequal_population_rejection(self):
        values = [-3,-3,-3,2,2,2,-1,-1,-1,4,4,4]
        low, high = analysis.block_interval(values)
        self.assertLess(low, high)
        self.assertEqual([low,high], analysis.block_interval(values))
        self.assertIsNone(analysis.block_interval(values[:11]))
        _, _, g = grade()
        g['arms']['market']['cohorts']['all_players']['n'] += 1
        with self.assertRaisesRegex(ValueError, 'unequal cohort'):
            analysis.summarize([g])

    def test_public_page_shows_populations_and_no_early_interval(self):
        from evmax import experiments as public
        from test_fpl_experiments import PROTOCOL
        _, _, g = grade()
        report = ledger.season_report([g])
        report.update(registered_arms=PROTOCOL['arms'], pending_gameweeks=[])
        rendered = public.page(report)
        self.assertIn('Paired forecast differences', rendered)
        self.assertIn('Fewer than 12 eligible weeks', rendered)
        self.assertIn('Prior 60+ minutes per gameweek', rendered)
        self.assertNotIn('nan', rendered.lower())
