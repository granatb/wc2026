import copy
import random
import unittest
from core import fpl_live
from games.fpl import lineup_decisions as policy, experiments
from scripts.fpl_lineup_rehearsal import scenarios

POSITIONS={i:pos for i,pos in enumerate(['GK']*2+['DEF']*5+['MID']*5+['FWD']*3,1)}
XI=[1,3,4,5,8,9,10,11,13,14,15]
DECISION=dict(xi_ids=XI,bench_ids=[2,12,6,7],captain_id=8,vice_id=9)


def scenario(missing=(),points=None,weight=1):
    return dict(weight=weight,players={pid:dict(played=pid not in missing,
        points=0 if pid in missing else (points or {}).get(pid,1)) for pid in POSITIONS})


class LineupDecisionTests(unittest.TestCase):
    def test_all_play_reduces_to_mean_lineup_and_captain(self):
        s=scenario(points={i:i for i in POSITIONS})
        boot=dict(elements=[dict(id=i,team=(i-1)//3+1,element_type=['GK','DEF','MID','FWD'].index(p)+1,
                                 now_cost=50) for i,p in POSITIONS.items()])
        baseline=experiments.choose_decision(list(POSITIONS),
            [dict(player_id=i,x_points=i) for i in POSITIONS],boot)
        result=policy.optimize(POSITIONS,[s])
        self.assertEqual(result['lineups_and_bench_orders'],3300)
        self.assertEqual(result['expected']['total'],policy.evaluate(POSITIONS,[s],baseline)['total'])
        self.assertEqual(result['expected']['total'],119)

    def test_vice_uses_conditional_value_not_second_highest_mean(self):
        ss=[scenario(points={8:20,9:18,10:8},weight=.5),
            scenario(missing=(8,9),points={10:8},weight=.5)]
        r=policy.optimize(POSITIONS,ss)
        self.assertEqual((r['decision']['captain_id'],r['decision']['vice_id']),(8,10))
        self.assertEqual(r['expected']['vice_bonus'],4)

    def test_substitute_does_not_inherit_armband(self):
        s=scenario(missing=(8,),points={9:3,12:10})
        r=policy.evaluate(POSITIONS,[s],DECISION)
        self.assertEqual(r['autosub_points'],10)
        self.assertEqual(r['captain_bonus'],0)
        self.assertEqual(r['vice_bonus'],3)
        self.assertEqual(r['total'],25)

    def test_played_zero_or_negative_is_not_dnp(self):
        s=scenario(points={8:0,9:-2,12:10})
        r=policy.evaluate(POSITIONS,[s],DECISION)
        self.assertEqual(r['autosub_points'],0)
        self.assertEqual(r['captain_bonus'],0)
        self.assertEqual(r['vice_bonus'],0)
        s['players'][8]['points']=-1
        self.assertEqual(policy.evaluate(POSITIONS,[s],DECISION)['captain_bonus'],-1)

    def test_keeper_only_and_minimum_defenders(self):
        s=scenario(missing=(1,3),points={2:4,12:20,6:6})
        r=policy.evaluate(POSITIONS,[s],DECISION)
        self.assertEqual(r['autosub_points'],10)
        self.assertEqual(policy.substitutes(XI,DECISION['bench_ids'],POSITIONS,
                                          set(POSITIONS)-{1,3}),{1:2,3:6})

    def test_random_scenarios_match_official_final_grader(self):
        rng=random.Random(817)
        boot=dict(teams=[dict(id=1,short_name='A')],elements=[dict(id=i,web_name=str(i),team=1,
            element_type=['GK','DEF','MID','FWD'].index(pos)+1) for i,pos in POSITIONS.items()])
        for _ in range(100):
            bench=list(DECISION['bench_ids']); rng.shuffle(bench)
            decision=dict(DECISION,bench_ids=bench)
            missing=[i for i in POSITIONS if rng.random()<.4]
            s=scenario(missing,points={i:rng.randint(-3,15) for i in POSITIONS})
            state=dict(squad=[dict(name=str(i),player_id=i,position=POSITIONS[i],
                is_starter=i in XI,is_captain=i==8,is_vice=i==9,
                bench_order=bench.index(i)+1 if i in bench else None) for i in XI+bench])
            live=dict(elements=[dict(id=i,stats=dict(minutes=1 if r['played'] else 0,total_points=r['points']))
                                for i,r in s['players'].items()])
            actual=fpl_live.grade_squad(state,live,[dict(team_h=1,team_a=2,finished=True)],boot)
            self.assertAlmostEqual(policy.evaluate(POSITIONS,[s],decision)['total'],actual['total_so_far'])

    def test_invalid_population_probabilities_and_roles_rejected(self):
        for change in ('missing','nan','negative_weight','sum','dnp_points'):
            s=scenario()
            if change=='missing': s['players'].pop(1)
            elif change=='nan': s['players'][1]['points']=float('nan')
            elif change=='negative_weight': s['weight']=-1
            elif change=='sum': s['weight']=.9
            else: s['players'][1]['played']=False
            with self.subTest(change=change), self.assertRaises(ValueError):
                policy.optimize(POSITIONS,[s])
        with self.assertRaises(ValueError):
            policy.evaluate(POSITIONS,[scenario()],dict(DECISION,vice_id=12))

    def test_grouping_preserves_correlated_weighted_scores(self):
        ss=[scenario(missing=(8,),points={9:3,12:10},weight=.2),
            scenario(missing=(8,),points={9:8,12:0},weight=.8)]
        r=policy.optimize(POSITIONS,ss)
        self.assertEqual(r['appearance_patterns'],1)
        self.assertAlmostEqual(r['expected']['total'],sum(s['weight']*policy.evaluate(
            POSITIONS,[dict(s,weight=1)],r['decision'])['total'] for s in ss))

    def test_sensitivity_sampler_preserves_explicit_appearance_and_seed(self):
        means={i:2 for i in POSITIONS}; chances={i:.5 for i in POSITIONS}; clubs={i:1 for i in POSITIONS}
        r=scenarios(means,chances,clubs,100,10,'shared_club')
        self.assertEqual(r,scenarios(means,chances,clubs,100,10,'shared_club'))
        for s in r:
            self.assertEqual(len({p['played'] for p in s['players'].values()}),1)
        with self.assertRaises(ValueError):
            scenarios(means,{i:0 for i in POSITIONS},clubs,100,10,'independent')
