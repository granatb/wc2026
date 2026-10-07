import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core import forecast_archive as evidence
from games.fpl import experiments as lab
from scripts import fpl_experiment, validate_site

PROTOCOL = json.loads((Path(__file__).resolve().parents[1]/'experiments/fpl-2026-27/protocol.json').read_text())
NOW = '2026-09-10T12:00:00Z'
LATER = '2026-09-17T12:00:00Z'
GAP_NOW = '2026-09-20T12:00:00Z'


def bootstrap():
    return {'events': [{'id': 4, 'deadline_time': '2026-09-12T12:30:00Z'},
                       {'id': 5, 'deadline_time': '2026-09-19T12:30:00Z'}],
            'teams': [{'id': i, 'short_name': f'T{i}'} for i in range(1, 11)],
            'elements': [{'id': i, 'web_name': f'P{i}', 'element_type': pos,
                          'team': (i-1)%10+1, 'now_cost': 50}
                         for i, pos in enumerate([1]*2+[2]*5+[3]*5+[4]*3+[2,2,3,4,1], 1)]}


def fixtures(gw=4):
    return [{'id': gw*10+i, 'event': gw, 'team_h': i*2+1, 'team_a': i*2+2,
             'finished': False} for i in range(5)]


def submissions(boot, now=NOW, previous=None):
    result = {}
    for arm in PROTOCOL['arms']:
        preds = [{'player_id': e['id'], 'x_points': 2+e['id']%5} for e in boot['elements']]
        old = previous['arms'][arm] if previous else None
        decision = lab.choose_decision(old['squad_ids'] if old else list(range(1,16)), preds, boot,
                                       old['portfolio'] if old else None)
        result[arm] = dict(decision, predictions=preds, model_version=arm+'-v1', generated_at=now,
                           trained_through='2026-08-01T00:00:00Z', source_artifact_id='a'*64,
                           bootstrap_sha256=evidence.digest(boot),
                           fixtures_sha256=evidence.digest(fixtures(5 if previous else 4)), interventions=[])
    return result


def first():
    boot = bootstrap()
    body = lab.prepare_week(PROTOCOL, 4, boot, submissions(boot), now=NOW, fixtures=fixtures())
    return dict(body, artifact_id=evidence.digest(body))


class ExperimentTests(unittest.TestCase):
    def test_common_seed_and_immutable_roundtrip(self):
        record = first()
        self.assertEqual(len(record['arms']), 4)
        for sub in record['arms'].values():
            self.assertEqual(sub['portfolio']['bank_tenths'], 250)
            self.assertEqual(sub['portfolio']['free_transfers_next'], 1)
        with tempfile.TemporaryDirectory() as tmp:
            body = {k:v for k,v in record.items() if k != 'artifact_id'}
            written = lab.write_week(tmp, body, now=NOW)
            self.assertEqual(lab.read_week(Path(tmp)/'gw4.json'), written)
            with self.assertRaises(ValueError):
                lab.write_week(tmp, body, now=NOW)

    def test_changed_population_missing_arm_and_context_are_rejected(self):
        for mutation in ('population', 'arm', 'context', 'nan'):
            boot = bootstrap(); subs = submissions(boot)
            if mutation == 'population': subs['market']['predictions'].pop()
            if mutation == 'arm': subs.pop('hybrid')
            if mutation == 'context': subs['market']['bootstrap_sha256'] = 'bad'
            if mutation == 'nan': subs['market']['predictions'][0]['x_points'] = float('nan')
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                lab.prepare_week(PROTOCOL, 4, boot, subs, now=NOW, fixtures=fixtures())

    def test_deadline_future_training_and_different_seed_are_rejected(self):
        boot = bootstrap(); subs = submissions(boot)
        with self.assertRaisesRegex(ValueError, 'deadline'):
            lab.prepare_week(PROTOCOL, 4, boot, subs, now='2026-09-12T12:30:00Z', fixtures=fixtures())
        subs['market']['trained_through'] = '2026-09-11T00:00:00Z'
        with self.assertRaisesRegex(ValueError, 'training cutoff'):
            lab.prepare_week(PROTOCOL, 4, boot, subs, now=NOW, fixtures=fixtures())
        subs = submissions(boot)
        ids = list(range(1,16)); ids.remove(3); ids.append(16)
        subs['statistical'].update(lab.choose_decision(ids, subs['statistical']['predictions'], boot))
        with self.assertRaisesRegex(ValueError, 'seed roster'):
            lab.prepare_week(PROTOCOL, 4, boot, subs, now=NOW, fixtures=fixtures())

    def test_human_captain_override_cannot_be_hidden(self):
        boot = bootstrap(); subs = submissions(boot)
        sub = subs['market']
        sub['captain_id'], sub['vice_id'] = sub['vice_id'], sub['captain_id']
        with self.assertRaisesRegex(ValueError, 'human intervention'):
            lab.prepare_week(PROTOCOL, 4, boot, subs, now=NOW, fixtures=fixtures())
        sub['interventions'] = [{'reason': 'minutes concern', 'source': 'https://club.example/news', 'recorded_at': NOW}]
        lab.prepare_week(PROTOCOL, 4, boot, subs, now=NOW, fixtures=fixtures())

    def test_profit_deductions_hits_and_free_transfers(self):
        old = first(); boot = bootstrap()
        boot['elements'][2]['now_cost'] = 53  # sold: +0.3m, keep +0.1m
        boot['elements'][15]['now_cost'] = 60
        squad = list(range(1,16)); squad.remove(3); squad.append(16)
        p = lab._portfolio(PROTOCOL, squad, {e['id']: e for e in boot['elements']}, old['arms']['market'])
        self.assertEqual(p['bank_tenths'], 241)
        self.assertEqual(p['free_transfers_next'], 1)
        squad.remove(4); squad.append(17)
        p = lab._portfolio(PROTOCOL, squad, {e['id']: e for e in boot['elements']}, old['arms']['market'])
        self.assertEqual(p['hit_points'], 4)
        self.assertEqual(p['free_transfers_next'], 1)

    def test_continuation_and_protocol_changes(self):
        previous = first(); boot = bootstrap(); subs = submissions(boot, LATER, previous)
        week = lab.prepare_week(PROTOCOL, 5, boot, subs, previous, now=LATER, fixtures=fixtures(5))
        self.assertEqual(week['previous_artifact_id'], previous['artifact_id'])
        changed = dict(PROTOCOL, starting_budget_tenths=1100)
        with self.assertRaisesRegex(ValueError, 'protocol changed'):
            lab.prepare_week(changed, 5, boot, subs, previous, now=LATER, fixtures=fixtures(5))

    def test_wrong_week_partial_results_and_scores(self):
        record = first()
        results = {'gameweek': 4, 'fetched_at': '2026-09-13T20:00:00Z', 'fixtures': [dict(f, finished=True) for f in fixtures()],
                   'live': {'elements': [{'id': i, 'stats': {'minutes': 90, 'total_points': 2}} for i in range(1,21)]}}
        grade = lab.grade_week(record, results)
        for arm in grade['arms'].values():
            self.assertEqual(arm['net_points'], 24)  # 11 players + doubled captain
            self.assertEqual(arm['captain_points'], 2)
        with self.assertRaisesRegex(ValueError, 'wrong gameweek'):
            lab.grade_week(record, dict(results, gameweek=3))
        results['live']['elements'].pop()
        with self.assertRaisesRegex(ValueError, 'missing outcomes'):
            lab.grade_week(record, results)
        report = lab.season_report([grade])
        self.assertEqual(report['gameweeks'], [4])
        self.assertNotIn('winner', report)
        with self.assertRaises(ValueError):
            lab.season_report([grade, grade])

    def test_no_chip_and_no_unlabelled_policy_switch(self):
        boot = bootstrap(); subs = submissions(boot)
        subs['hybrid']['chip'] = 'wildcard'
        with self.assertRaisesRegex(ValueError, 'chips disabled'):
            lab.prepare_week(PROTOCOL, 4, boot, subs, now=NOW, fixtures=fixtures())
        subs['hybrid']['chip'] = None
        subs['hybrid']['decision_policy_id'] = 'another-policy'
        with self.assertRaisesRegex(ValueError, 'unregistered decision'):
            lab.prepare_week(PROTOCOL, 4, boot, subs, now=NOW, fixtures=fixtures())


class MergeGateTests(unittest.TestCase):
    def test_public_report_distinguishes_registration_and_pending_results(self):
        from evmax import experiments as public
        with tempfile.TemporaryDirectory() as tmp:
            report = lab.report_from_directory(PROTOCOL, tmp)
            self.assertEqual(report['status'], 'registered_not_started')
            self.assertEqual(len(report['registered_arms']), 4)
            self.assertEqual(report['arms'], {})
            self.assertIn('Awaiting frozen weekly results', public.page(report))
            lab.write_week(tmp, first(), now=NOW)
            report = lab.report_from_directory(PROTOCOL, tmp)
            self.assertEqual(report['pending_gameweeks'], [4])
            self.assertEqual(report['status'], 'forecasts_frozen_awaiting_results')
            report['registered_arms']['market'] = '<script>bad</script>'
            self.assertNotIn('<script>bad</script>', public.page(report))

    def test_missing_captain_file_cannot_evade_deployment_validation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(evidence, 'load', return_value=None), \
             patch.object(validate_site, 'load_snapshots', return_value={'captains': {'generated_at': NOW, 'entries': []}}):
            root = Path(tmp)
            (root/'api').mkdir()
            (root/'api/latest.json').write_text(json.dumps({'gameweek': 4}))
            (root/'index.html').write_text('test'); (root/'_headers').write_text('test')
            errors = validate_site.validate(root)
            self.assertTrue(any('missing captains' in e for e in errors))

    def test_artifact_id_tampering_is_rejected(self):
        boot = bootstrap()
        with tempfile.TemporaryDirectory() as tmp, patch.object(evidence, 'ROOT', Path(tmp)):
            record = evidence.freeze(4, {'rows': []}, boot, now=NOW)
            path = Path(tmp)/'gw4'/(record['artifact_id']+'.json')
            record['artifact_id'] = 'b'*64
            path.write_text(json.dumps(record))
            with self.assertRaises(ValueError): evidence.load(4)


class GapRecordTests(unittest.TestCase):
    """A week that was never enrolled is recorded as a dated gap, after its deadline.

    The gap keeps the chain intact: squads and purchase prices carry forward,
    one free transfer accrues, nothing is forecast and nothing is graded.
    """
    def _frozen(self, tmp):
        record = first()
        body = {k: v for k, v in record.items() if k != 'artifact_id'}
        return lab.write_week(tmp, body, now=NOW)

    def test_gap_carries_portfolio_and_keeps_the_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            frozen = self._frozen(tmp)
            gap = lab.record_gap(PROTOCOL, tmp, 5, bootstrap(), reason='owner away',
                                 source='docs/research/season-learnings.md 2026-09-30', now=GAP_NOW)
            self.assertEqual(gap['record_type'], 'gap')
            self.assertEqual(gap['previous_artifact_id'], frozen['artifact_id'])
            for arm, sub in gap['arms'].items():
                old = frozen['arms'][arm]
                self.assertEqual(sub['squad_ids'], old['squad_ids'])
                self.assertEqual(sub['portfolio']['purchase_prices'], old['portfolio']['purchase_prices'])
                self.assertEqual(sub['portfolio']['bank_tenths'], old['portfolio']['bank_tenths'])
                self.assertEqual(sub['portfolio']['free_transfers_before'], 1)
                self.assertEqual(sub['portfolio']['free_transfers_next'], 2)
                self.assertEqual(sub['portfolio']['transfers_in'], [])
            history = lab.load_history(tmp)
            self.assertEqual([r['gameweek'] for r in history], [4, 5])
            self.assertEqual(lab.read_week(Path(tmp)/'gw5.json'), gap)
            # The next enrolled week continues from the gap's carried portfolio.
            boot = bootstrap()
            boot['events'].append({'id': 6, 'deadline_time': '2026-09-26T12:30:00Z'})
            subs = submissions(boot, GAP_NOW, gap)
            for sub in subs.values():
                sub['fixtures_sha256'] = evidence.digest(fixtures(6))
            week = lab.prepare_week(PROTOCOL, 6, boot, subs, previous=gap, now=GAP_NOW, fixtures=fixtures(6))
            self.assertEqual(week['previous_artifact_id'], gap['artifact_id'])
            self.assertEqual(week['arms']['market']['portfolio']['free_transfers_before'], 2)

    def test_gap_is_refused_before_its_deadline_out_of_sequence_or_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._frozen(tmp)
            with self.assertRaisesRegex(ValueError, 'deadline'):
                lab.record_gap(PROTOCOL, tmp, 5, bootstrap(), reason='r', source='s', now=NOW)
            with self.assertRaisesRegex(ValueError, 'consecutive'):
                lab.record_gap(PROTOCOL, tmp, 6, bootstrap(), reason='r', source='s', now=GAP_NOW)
            with self.assertRaisesRegex(ValueError, 'reason'):
                lab.record_gap(PROTOCOL, tmp, 5, bootstrap(), reason='', source='s', now=GAP_NOW)
            lab.record_gap(PROTOCOL, tmp, 5, bootstrap(), reason='r', source='s', now=GAP_NOW)
            with self.assertRaises(ValueError):
                lab.record_gap(PROTOCOL, tmp, 5, bootstrap(), reason='r', source='s', now=GAP_NOW)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'no enrolled history'):
                lab.record_gap(PROTOCOL, tmp, 5, bootstrap(), reason='r', source='s', now=GAP_NOW)

    def test_gap_is_never_graded_and_the_report_names_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._frozen(tmp)
            gap = lab.record_gap(PROTOCOL, tmp, 5, bootstrap(), reason='owner away', source='s', now=GAP_NOW)
            with self.assertRaisesRegex(ValueError, 'gap'):
                lab.grade_week(gap, {})
            report = lab.report_from_directory(PROTOCOL, tmp)
            self.assertEqual(report['frozen_gameweeks'], [4])
            self.assertEqual(report['pending_gameweeks'], [4])
            self.assertEqual(report['gap_gameweeks'], [{'gameweek': 5, 'reason': 'owner away'}])
            self.assertEqual([r['gameweek'] for r in report['receipts']], [4])
