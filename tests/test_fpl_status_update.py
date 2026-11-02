"""A status publication must not imply a newly computed forecast or final grade."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import publish_fpl_status as status
from scripts.validate_site import validate


class StatusUpdateTests(unittest.TestCase):
    def setUp(self):
        self.boot = {'events': [
            {'id': 8, 'finished': True, 'data_checked': True, 'average_entry_score': 45},
            {'id': 9, 'is_current': True, 'finished': False, 'data_checked': False,
             'average_entry_score': 42},
            {'id': 10, 'is_next': True, 'deadline_time': '2026-11-06T18:30:00Z'}],
            'teams': [{'id': 1, 'name': 'Newcastle'}, {'id': 2, 'name': 'Everton'}]}
        self.fixtures = [dict(id=8, event=8, team_h=1, team_a=2, finished=True,
                             team_h_score=1, team_a_score=0, kickoff_time='2026-10-26T20:00:00Z'),
                         dict(id=9, event=9, team_h=1, team_a=2, finished=False,
                              finished_provisional=False, team_h_score=None,
                              team_a_score=None, kickoff_time='2026-11-02T20:00:00Z')]
        self.record = status.make_status(self.boot, self.fixtures, '2026-11-02T10:00:00Z')

    def test_official_finality_and_next_deadline(self):
        self.assertEqual(self.record['current']['status'], 'provisional')
        self.assertEqual(self.record['previous']['status'], 'final')
        self.assertEqual(self.record['next']['deadline_time'], '2026-11-06T18:30:00Z')
        changed = copy.deepcopy(self.boot)
        changed['events'][0]['data_checked'] = False
        self.assertEqual(status.make_status(changed, self.fixtures,
            self.record['captured_at'])['previous']['status'], 'provisional')
        self.fixtures[0]['finished'] = False
        self.assertEqual(status.make_status(self.boot, self.fixtures,
            self.record['captured_at'])['previous']['status'], 'provisional')

    def test_played_is_distinct_from_final(self):
        self.fixtures[1]['finished_provisional'] = True
        r = status.make_status(self.boot, self.fixtures, self.record['captured_at'])
        self.assertEqual(r['current']['played'], 1)
        self.assertEqual(r['current']['status'], 'provisional')

    def test_current_page_is_a_status_article(self):
        page, article = status.render_pages(self.record)
        for html in (page, article):
            self.assertIn('GW9', html)
            self.assertIn('6 November', html)
            self.assertIn('18:30 UTC', html)
            self.assertNotIn('Top 10 by .', html)
            self.assertNotIn('<h2>Bottom line</h2>', html)
        self.assertNotIn('GW8 plan: Mbeumo', page)
        self.assertNotIn('Gameweek 7 graded', page)
        self.assertNotIn('from 50,000 Monte-Carlo simulations', page)
        self.assertIn('/fpl/gw9/update/', page)
        self.assertIn('21 October', page)

    def test_existing_card_note_is_dated_archive_without_changing_projection(self):
        old='<p class="pc-preview"><b>Preview</b> old news</p><b>7.35</b>'
        new=status.archive_card_note(old, {'gameweek':8,'as_of':'2026-10-21T12:00:00Z'})
        self.assertIn('Archived preview', new)
        self.assertIn('21 October', new)
        self.assertTrue(new.endswith('<b>7.35</b>'))

    def test_status_feed_needs_no_retrospective_forecast_and_rejects_false_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'api/fpl').mkdir(parents=True)
            for file in ['index.html', '_headers']:
                (root/file).write_text('')
            latest = {'publication_type':'status_update', 'gameweek':9,
                      'generated_at':self.record['captured_at'],
                      'last_frozen_forecast':{'gameweek':7, 'forecast_artifact_id':'original'}}
            (root/'api/latest.json').write_text(json.dumps(latest))
            (root/'api/fpl/status.json').write_text(json.dumps(self.record))
            with patch('scripts.validate_site.forecast_archive.load',
                       side_effect=lambda gw: {'artifact_id':'original'} if gw==7 else None):
                self.assertEqual(validate(root), [])
                self.record['current']['status']='final'
                (root/'api/fpl/status.json').write_text(json.dumps(self.record))
                self.assertTrue(any('finality' in error for error in validate(root)))


if __name__ == '__main__':
    unittest.main()
