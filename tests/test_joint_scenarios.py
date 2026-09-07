import copy
import unittest
from collections import Counter
from datetime import datetime, timezone
from unittest.mock import patch
from core import fixtures, ratings
from games.fpl import model, joint_scenarios


class JointScenarioTests(unittest.TestCase):
    def build(self, **kwargs):
        priors={'H':[ratings.PlayerPrior(name='H',team='H',position='FWD',start_prob=.8,
                                        exp_minutes=80,goal_share=.7,assist_share=.2)],
                'A':[ratings.PlayerPrior(name='A',team='A',position='GK',start_prob=.8,
                                        exp_minutes=90,saves_per90=3)]}
        fx=[fixtures.Fixture(match_id=str(i),home='H',away='A',stage='GW',fantasy_round=97,
            kickoff=datetime(2026,9,12+i,15,tzinfo=timezone.utc),neutral=False,lam_home=1.5,lam_away=1.0)
            for i in range(2)]
        with patch('core.fixtures.by_round',return_value=fx):
            return model.build_artifact(priors,{},97,100,research_entries={},**kwargs)

    def test_retention_preserves_forecasts_and_exact_histograms(self):
        plain,_=self.build(use_cache=False)
        retained,hit=self.build(use_cache=True,retain_joint_for=['H','A'])
        self.assertFalse(hit)
        self.assertEqual(plain['rows'],retained['rows'])
        self.assertEqual(plain['matches'],retained['matches'])
        rows={r['name']:r for r in retained['rows']}
        for name,draws in retained['joint']['players'].items():
            self.assertEqual(len(draws['played']),100)
            self.assertEqual(Counter(draws['points']),rows[name]['distribution'])
            self.assertEqual(round(sum(draws['points'])/100,2),rows[name]['x_points'])

    def test_joint_export_bypasses_public_cache_and_seed_is_explicit(self):
        with patch('core.simcache.load') as load, patch('core.simcache.store') as store:
            first,_=self.build(use_cache=True,retain_joint_for=['H'],seed=12345)
            second,_=self.build(use_cache=True,retain_joint_for=['H'],seed=12346)
            load.assert_not_called(); store.assert_not_called()
        self.assertNotEqual(first['joint']['players']['H']['points'],second['joint']['players']['H']['points'])
        with self.assertRaises(ValueError): self.build(retain_joint_for=['unknown'])
        with self.assertRaises(ValueError): self.build(retain_joint_for=['H','H'])

    def test_double_sums_by_index_and_dnp_is_not_zero_points(self):
        acc=model.SimPointsAccumulator({},3)
        row=('P','FWD',0,0,90,False,0,0,0,0,0)
        acc.observe('first',[row],0)
        acc.observe('second',[row],0)
        with patch.object(model,'_row_points',return_value=0): acc.observe('second',[row],1)
        values=acc.joint(['P','never'])
        self.assertEqual(values['P'],dict(points=[10,0,0],played=[True,True,False]))
        self.assertEqual(values['never'],dict(points=[0,0,0],played=[False]*3))

    def test_decode_keeps_cross_player_alignment_and_negative_appearance(self):
        joint=dict(schema_version=1,sims=3,seed=1,players=[
            dict(player_id=1,points=[0,8,-2],played=[False,True,True]),
            dict(player_id=2,points=[4,0,0],played=[True,True,False])])
        rows=[dict(player_id=1,x_points=2),dict(player_id=2,x_points=1.33)]
        scenarios,diagnostics=joint_scenarios.decode(joint,{1:'MID',2:'DEF'},rows)
        self.assertEqual(scenarios[1]['players'][2],dict(points=0,played=True))
        self.assertEqual(scenarios[2]['players'][1],dict(points=-2,played=True))
        self.assertEqual(diagnostics['2']['played_zero_points'],1)
        for change in ('length','mean','duplicate','dnp','boolean'):
            altered=copy.deepcopy(joint)
            if change=='length': altered['players'][0]['points'].pop()
            elif change=='mean': altered['players'][0]['points'][1]=10
            elif change=='duplicate': altered['players'][1]['player_id']=1
            elif change=='dnp': altered['players'][0]['played'][1]=False
            else: altered['players'][0]['played'][1]=1
            with self.subTest(change=change),self.assertRaises(ValueError):
                joint_scenarios.decode(altered,{1:'MID',2:'DEF'},rows)

    def test_precision_is_paired_and_not_a_performance_claim(self):
        from test_lineup_decisions import POSITIONS, DECISION, scenario
        other=dict(DECISION,bench_ids=[2,6,12,7])
        samples=[scenario(missing=(8,),points={12:10,6:1},weight=.5),
                 scenario(missing=(8,),points={12:0,6:4},weight=.5)]
        result=joint_scenarios.paired_precision(POSITIONS,samples,other,DECISION)
        self.assertEqual(result['mean'],-2.5)
        self.assertAlmostEqual(result['standard_error'],6.5)
        self.assertIn('not a confidence interval for real-world',result['note'])

    def test_provider_retains_explicit_blank_without_fabricating_appearance(self):
        from test_forecast_providers import context
        from games.fpl import forecast_providers
        ctx=context()
        ctx['fixtures'][0]['kickoff_time']='2026-09-12T15:00:00Z'
        fid=ctx['fixtures'][0]['id']
        odds=dict(matches={str(fid):dict(h2h={'home':2},source='test-market',home='T1',away='T2',
                                       lam_home=1.5,lam_away=1,rho=0)})
        pred,detail=forecast_providers.market_predictions(ctx['bootstrap'],ctx['fixtures'],odds,{},100,
                                                        retain_ids=[1,3])
        rows={r['player_id']:r for r in detail['joint']['players']}
        self.assertEqual(pred[3],0)
        self.assertEqual(rows[3]['played'],[False]*100)
        self.assertEqual(rows[3]['points'],[0]*100)
