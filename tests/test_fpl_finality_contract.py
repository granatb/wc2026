"""Regression: finished fixtures alone do not establish checked event results."""
import copy
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from core import forecast_archive, fpl_api, fpl_live


def checked_result(payload):
    """Add explicit final event evidence to a synthetic result fixture."""
    payload = copy.deepcopy(payload)
    gw = payload['gameweek']
    event = {'id': gw, 'finished': True, 'data_checked': True}
    payload['event'] = event
    payload['event_receipt'] = {
        'source': fpl_api.BOOTSTRAP,
        'recorded_at': payload['fetched_at'],
        'payload_sha256': forecast_archive.digest(event),
    }
    return payload


class EventFinalityTests(unittest.TestCase):
    def final(self):
        return checked_result({'gameweek': 6, 'fetched_at': '2026-10-13T12:00:00Z',
            'fixtures': [{'id': 51, 'event': 6, 'finished': True}],
            'live': {'elements': [{'id': 1, 'stats': {'minutes': 90, 'total_points': 2}}]}})

    def test_finished_fixtures_do_not_allow_an_unchecked_event(self):
        for field in ('finished', 'data_checked'):
            payload = self.final()
            payload['event'][field] = False
            payload['event_receipt']['payload_sha256'] = forecast_archive.digest(payload['event'])
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'event'):
                forecast_archive.require_final(payload)

    def test_missing_event_evidence_fails_closed(self):
        for key in ('event', 'event_receipt'):
            payload = self.final()
            del payload[key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'event'):
                forecast_archive.require_final(payload)

    def test_wrong_event_and_tampered_receipt_are_rejected(self):
        payload = self.final()
        payload['event']['id'] = 5
        payload['event_receipt']['payload_sha256'] = forecast_archive.digest(payload['event'])
        with self.assertRaisesRegex(ValueError, 'gameweek'):
            forecast_archive.require_final(payload)
        payload = self.final()
        payload['event_receipt']['payload_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'receipt'):
            forecast_archive.require_final(payload)

    def test_fully_checked_matching_event_is_accepted(self):
        forecast_archive.require_final(self.final())

    def test_refresh_retains_event_evidence_without_refreshing_forecast_inputs(self):
        event = {'id': 6, 'finished': False, 'data_checked': False}
        with tempfile.TemporaryDirectory() as tmp, patch.object(fpl_api, 'DATA_DIR', tmp), \
             patch.object(fpl_api, 'fetch_bootstrap', return_value={'events': [event]}):
            fpl_api.write_cache('bootstrap', {'preserved': 'forecast inputs'})
            payload = fpl_live.refresh_live(6,
                fetch_live_fn=lambda gw: {'elements': [{'id': 1}]},
                fetch_fixtures_fn=lambda gw: [{'event': 6, 'finished': True}],
                now=datetime(2026, 10, 13, 12, tzinfo=timezone.utc))
            self.assertIn('event', payload)
            self.assertEqual(payload['event'], event)
            self.assertEqual(payload['event_receipt']['payload_sha256'], forecast_archive.digest(event))
            self.assertEqual(fpl_api.read_cache('bootstrap'), {'preserved': 'forecast inputs'})


if __name__ == '__main__':
    unittest.main()


class LegacyReplayTests(unittest.TestCase):
    def test_retained_legacy_grade_replays_but_cannot_be_banked_again(self):
        import json
        from pathlib import Path
        from games.fpl import experiments as lab
        root = Path(lab.__file__).resolve().parents[2]/'experiments/fpl-2026-27'
        protocol = json.loads((root/'protocol.json').read_text())
        report = lab.report_from_directory(protocol, root/'records')
        self.assertIn(4, report['legacy_finality_gameweeks'])
        grade = json.loads((root/'records/grades/gw4.json').read_text())
        results = json.loads((root/'records/results'/f"{grade['results_sha256']}.json").read_text())
        record = lab.read_week(root/'records/gw4.json')
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(ValueError, 'event'):
            lab.bank_grade(tmp, record, results)
