"""Early player forecasts retain evidence without inventing an accepted squad."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from scripts import publish_fpl_preview as preview
from scripts.publish_fpl_status import render_pages
from scripts.validate_site import validate_preview_week


class EarlyPreviewTests(unittest.TestCase):
    def test_old_plan_cannot_survive_in_current_preview_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'api/fpl/preview'
            folder.mkdir(parents=True)
            (folder/'players.json').write_text(json.dumps({'gameweek':10}))
            (folder/'plan.json').write_text(json.dumps({'gameweek':8}))
            with self.assertRaisesRegex(ValueError,'stale current-preview file: plan.json'):
                validate_preview_week(tmp,10)
            (folder/'plan.json').unlink()
            validate_preview_week(tmp,10)

    def test_preview_evidence_rejects_changed_board_and_post_deadline_run(self):
        record = {'gameweek': 10, 'publication_type': 'early_preview',
                  'generated_at': '2026-11-03T10:00:00+00:00',
                  'deadline': '2026-11-06T18:30:00Z', 'provisional': True,
                  'players': [{'name': 'Example', 'x_points': 5.1}],
                  'source_times': {'official': '2026-11-03T09:00:00Z',
                                   'markets': '2026-11-03T09:10:00Z',
                                   'histories': '2026-11-03T09:20:00Z'}}
        preview.validate_preview_record(record, copy.deepcopy(record))
        changed = copy.deepcopy(record)
        changed['players'][0]['x_points'] = 9
        with self.assertRaisesRegex(ValueError, 'retained evidence'):
            preview.validate_preview_record(changed, record)
        changed = copy.deepcopy(record)
        changed['generated_at'] = '2026-11-07T10:00:00Z'
        with self.assertRaisesRegex(ValueError, 'deadline'):
            preview.validate_preview_record(changed, changed)

    def test_preview_rejects_stale_inputs(self):
        record = {'gameweek':10, 'publication_type':'early_preview',
                  'generated_at':'2026-11-03T10:00:00Z',
                  'deadline':'2026-11-06T18:30:00Z', 'provisional':True,
                  'players':[{'name':'Example','x_points':5}],
                  'source_times':{'official':'2026-10-23T10:00:00Z'}}
        with self.assertRaisesRegex(ValueError, 'fresh'):
            preview.validate_preview_record(record, record)

    def test_finished_matches_do_not_imply_final_event_or_unpublished_preview(self):
        record = json.loads(Path('evmax/assets/editorial/fpl-gw9/status.json').read_text())
        for f in record['current']['fixtures']:
            f.update(finished=True, team_h_score=0, team_a_score=1)
        record['current']['played'] = len(record['current']['fixtures'])
        record['next'].update(forecast_status='early_preview', preview_path='/fpl/gw10/preview/')
        home, article = render_pages(record)
        for page in (home, article):
            self.assertIn('All 10 matches played', page)
            self.assertIn('provisional', page)
            self.assertIn('/fpl/gw10/preview/', page)
            self.assertNotIn('no new expected-points forecast is published', page)
            self.assertNotIn('0 still to come', page)


if __name__ == '__main__':
    unittest.main()
