"""Current previews retain the evaluation ledger, fixtures and this week's dots."""
import copy
import unittest
from unittest.mock import patch
from evmax import fpl_players, render
from scripts.publish_fpl_preview import render_homepage
from scripts.restore_fpl_homepage import current_matches
from tests.test_preview_cards import _preview_payloads


class HomepageRestoreTests(unittest.TestCase):
    def test_preview_homepage_keeps_history_and_upcoming_fixture_panel(self):
        payloads=_preview_payloads()
        meta={'gameweek':10,'as_of':'2026-11-03T10:23:45+00:00','deadline':'2026-11-06T18:30:00Z'}
        for p in payloads:
            p['gameweek']=10;p['preview']=meta
        rows=[dict(p['projection'],name=p['name'],team=p['team'],position=p['position']) for p in payloads]
        history=[{'gw':7,'model_realized':59,'consensus_realized':67,'model_projected':61.8,
                  'consensus_projected':56.7,'duel_model':2,'duel_consensus':5}]
        matches=[{'home':'ARS','away':'HUL','kickoff':'2026-11-07T15:00:00+00:00','p_home':.8,'p_draw':.1,'p_away':.1}]
        with patch('evmax.fpl_build.fpl_track_ledger',return_value=history):
            page=render_homepage(payloads,rows,meta,matches,'2026-11-04T10:00:00+00:00')
        self.assertIn('duel-ledger',page)
        self.assertIn('proj 61.8',page)
        self.assertIn('<aside class="rail">',page)
        self.assertIn('ARS vs HUL',page)
        self.assertIn('GW10 fixtures · UTC',page)
        self.assertNotIn('<tr class="dl-live">',page)
        self.assertNotIn('Gameweek 10 graded',page)

    def test_single_week_projection_restores_dot_and_opponent_without_inventing_horizon(self):
        p={'gameweek':10,'name':'Evanilson','form_history':[{'round':9,'total_points':9,'minutes':90}],
           'six_week_xpts':None,'projection':{'x_points':4.68},
           'fixtures':[{'gw':10,'opponent':'IPS','venue':'A','difficulty':2}]}
        dots=fpl_players.form_dots(p)
        self.assertEqual([(d['gw'],d['mode']) for d in dots],[(9,'played'),(10,'projected')])
        self.assertEqual(dots[-1]['display'],'4.7')
        self.assertIn('IPS',fpl_players._dots_html(p))
        p['form_history'].append({'round':10,'total_points':3,'minutes':90})
        self.assertEqual([d for d in fpl_players.form_dots(p) if d['mode']=='projected'],[])

    def test_historical_ledger_does_not_require_a_new_squad_or_invent_live_points(self):
        history=[{'gw':7,'model_realized':59,'consensus_realized':67,'model_projected':61.8,
                  'consensus_projected':66.5,'duel_model':2,'duel_consensus':5}]
        html=render._duel_table_html(None,history,10,section=render.FPL)
        self.assertIn('duel-ledger',html)
        self.assertIn('59',html)
        self.assertIn('proj 61.8',html)
        self.assertNotIn('dl-live',html)
        self.assertNotIn('GW10',html)
        self.assertNotIn('Thursday',html)

    def test_fixture_refresh_preserves_published_match_forecast(self):
        forecast=[{'match_id':'91','home':'ARS','away':'HUL','kickoff':'old','p_home':.821}]
        fixtures=[{'match_id':'91','fantasy_round':10,'home':'ARS','away':'HUL','kickoff_utc':'2026-11-07T15:00:00+00:00'}]
        result=current_matches(forecast,fixtures,10)
        self.assertEqual(result[0]['kickoff'],fixtures[0]['kickoff_utc'])
        self.assertEqual(result[0]['p_home'],.821)
        self.assertEqual(forecast[0]['kickoff'],'old')
        fixtures[0]['away']='NEW'
        with self.assertRaisesRegex(ValueError,'fixture identity'):
            current_matches(forecast,fixtures,10)


if __name__=='__main__':
    unittest.main()
