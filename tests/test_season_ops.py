import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import forecast_archive as evidence
from games.fpl import season_ops as ops, experiments as ledger, forecast_providers as providers
from test_forecast_providers import context, trained, fake_market
from test_fpl_experiments import PROTOCOL

NOW = '2026-09-12T12:00:00Z'
AFTER = '2026-09-14T12:00:00Z'


def current():
    c = context()
    c['captured_at'] = c['odds']['captured_at'] = c['ffiq']['generated_at'] = NOW
    for receipt in c['receipts'].values(): receipt['recorded_at'] = NOW
    return c


def build(c, t, sims, now):
    return providers.build_boards(c, t, sims=sims, now=now, market_fn=fake_market)


def rehearsal(root, work):
    c = current()
    seed = dict(squad=[dict(name=p['web_name'], player_id=p['id'],
                    position=ledger.POSITIONS[p['element_type']]) for p in c['bootstrap']['elements'][:15]])
    return ops.rehearse(PROTOCOL, c, trained(), seed, root, work, now=NOW, build_fn=build)


def results():
    c = current()
    return dict(gameweek=4, fetched_at=AFTER, fixtures=[dict(f, finished=True) for f in c['fixtures']],
        live=dict(elements=[dict(id=p['id'], stats=dict(minutes=90, total_points=2)) for p in c['bootstrap']['elements']]))


class SeasonOpsTests(unittest.TestCase):
    def test_rehearsal_freeze_retry_grade_and_report_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, work = Path(tmp)/'records', Path(tmp)/'work'
            draft = rehearsal(root, work)
            self.assertEqual(ledger.load_history(root), [])
            self.assertEqual(draft['state'], 'rehearsal_not_frozen')
            frozen = ops.freeze_run(PROTOCOL, draft['run'], root, work, now=NOW)
            backup = work/'backups'/f"{frozen['forecast_artifact_id']}.json"
            self.assertEqual(ops.verify_backup(backup)['forecast_artifact_id'], frozen['forecast_artifact_id'])
            self.assertEqual(ops.freeze_run(PROTOCOL, draft['run'], root, work, now=AFTER)['state'], 'already_frozen')
            record = ledger.read_week(root/'gw4.json')
            grade = ledger.bank_grade(root, record, results(), now=AFTER)
            self.assertEqual(grade['arms']['market']['net_points'], 24)
            report = ledger.report_from_directory(PROTOCOL, root)
            self.assertEqual(report['gameweeks'], [4])
            self.assertEqual(report['receipts'][0]['forecast_artifact_id'], frozen['forecast_artifact_id'])
            self.assertNotIn('predictions', json.dumps(report['receipts']))
            # A fresh fetch of unchanged results is not a correction.
            newer = dict(results(), fetched_at='2026-09-14T13:00:00Z')
            self.assertEqual(ledger.bank_grade(root, record, newer, now=newer['fetched_at']), grade)
            self.assertFalse((root/'grades/revisions').exists())
            newer['live']['elements'][0]['stats']['total_points'] = 3
            ledger.bank_grade(root, record, newer, now=newer['fetched_at'])
            self.assertEqual(len(list((root/'grades/revisions').glob('*.json'))), 1)
            ledger.report_from_directory(PROTOCOL, root)

    def test_grade_tampering_or_missing_outcomes_blocks_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, work = Path(tmp)/'records', Path(tmp)/'work'
            draft = rehearsal(root, work); ops.freeze_run(PROTOCOL, draft['run'], root, work, now=NOW)
            record = ledger.read_week(root/'gw4.json')
            grade = ledger.bank_grade(root, record, results(), now=AFTER)
            grade['arms']['market']['net_points'] = 999
            evidence.atomic_json(root/'grades/gw4.json', grade)
            with self.assertRaisesRegex(ValueError, 'retained official outcomes'):
                ledger.report_from_directory(PROTOCOL, root)

    def test_clock_and_expired_draft_do_not_enroll(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, work = Path(tmp)/'records', Path(tmp)/'work'
            draft = rehearsal(root, work)
            for now in ('2026-09-10T12:00:00Z', '2026-09-12T12:30:00Z'):
                with self.subTest(now=now), self.assertRaises(ValueError):
                    ops.freeze_run(PROTOCOL, draft['run'], root, work, now=now)
            self.assertFalse((root/'gw4.json').exists())
            boot = current()['bootstrap']
            self.assertEqual(ops.status(PROTOCOL, boot, root, 4, now='2026-09-10T12:00:00Z')['state'], 'rehearsal_only')
            self.assertEqual(ops.status(PROTOCOL, boot, root, 4, now=NOW)['state'], 'ready_to_refresh_and_freeze')
            self.assertEqual(ops.status(PROTOCOL, boot, root, 4, now=AFTER)['state'], 'missed_deadline')

    def test_backup_written_before_enrollment_and_bad_run_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, work = Path(tmp)/'records', Path(tmp)/'work'
            draft = rehearsal(root, work)
            with patch.object(ledger, 'write_week', side_effect=OSError('crash before enrollment')):
                with self.assertRaises(OSError): ops.freeze_run(PROTOCOL, draft['run'], root, work, now=NOW)
            self.assertFalse((root/'gw4.json').exists())
            self.assertEqual(len(list((work/'backups').glob('*.json'))), 1)
            ops.freeze_run(PROTOCOL, draft['run'], root, work, now=NOW)
            run = ops.read(draft['run']); run['submissions']['market']['captain_id'] = 999
            evidence.atomic_json(draft['run'], run)
            with self.assertRaisesRegex(ValueError, 'checksum'): ops.load_run(draft['run'])

    def test_lock_and_invalid_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, work = Path(tmp)/'records', Path(tmp)/'work'
            with ops.operation_lock(root):
                with self.assertRaisesRegex(ValueError, 'another season operation'):
                    with ops.operation_lock(root): pass
            draft = rehearsal(root, work); ops.freeze_run(PROTOCOL, draft['run'], root, work, now=NOW)
            record = ledger.read_week(root/'gw4.json')
            for mutation in ('duplicate', 'nan', 'negative_minutes', 'missing', 'duplicate_fixture'):
                value = results()
                if mutation == 'duplicate': value['live']['elements'].append(value['live']['elements'][0])
                if mutation == 'nan': value['live']['elements'][0]['stats']['total_points'] = float('nan')
                if mutation == 'negative_minutes': value['live']['elements'][0]['stats']['minutes'] = -1
                if mutation == 'missing': value['live']['elements'].pop()
                if mutation == 'duplicate_fixture': value['fixtures'] *= 2
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    ledger.bank_grade(root, record, value, now=AFTER)
            self.assertFalse((root/'grades/gw4.json').exists())
