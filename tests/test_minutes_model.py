import csv
import tempfile
import unittest
from pathlib import Path
from games.fpl import minutes_model as model
from scripts import evaluate_challenger


class MinutesTests(unittest.TestCase):
    def csv(self,path,last_minutes=90):
        fields=['element','fixture','GW','round','position','minutes','kickoff_time','total_points','expected_goals','expected_assists']
        with path.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
            for pid,pos in enumerate(['GK','DEF','MID','FWD','AM'],1):
                for gw in range(1,9):
                    w.writerow(dict(element=pid,fixture=gw,GW=gw,round=gw,position=pos,
                        minutes=last_minutes if gw==8 else (90 if gw%2 else 0),
                        kickoff_time=f'2024-01-{gw:02d}T12:00:00Z',total_points=2,expected_goals=0,expected_assists=0))

    def test_future_minutes_do_not_change_prior_features_and_managers_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'a.csv',Path(tmp)/'b.csv'; self.csv(a); self.csv(b,0)
            rows,ex=model.examples(a); changed,_=model.examples(b)
            self.assertEqual([r['prior'] for r in rows],[r['prior'] for r in changed])
            self.assertNotEqual([r['target'] for r in rows],[r['target'] for r in changed])
            self.assertEqual(ex['non_player_rows'],8)
            self.assertEqual(len(rows),32)
            self.assertNotIn('5',{r['player_id'] for r in evaluate_challenger.examples(a,min_prior=1)})

    def test_postponed_prior_gameweek_and_within_double_cannot_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.csv'; self.csv(p)
            with p.open() as handle:
                rows=list(csv.DictReader(handle))
            for r in rows:
                if r['GW']=='1': r['kickoff_time']='2024-01-20T12:00:00Z'
            fields=list(rows[0])
            with p.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
            examples,_=model.examples(p)
            second=next(r for r in examples if r['player_id']=='1' and r['gw']==2)
            self.assertEqual(second['prior'],[])
            duplicate=dict(rows[2],fixture='100'); rows.append(duplicate)
            with p.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
            examples,excluded=model.examples(p)
            self.assertEqual(excluded['double_gameweek_rows'],2)
            self.assertFalse(any(r['player_id']==duplicate['element'] and r['gw']==3 for r in examples))

    def test_fitted_probabilities_normalize_and_expected_minutes_are_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.csv'; self.csv(p); rows,_=model.examples(p); fitted=model.fit(rows)
            for pos in model.POSITIONS:
                for prior in ([],[0],[10,90],[90]*4):
                    for method in ('transition','last4','season'):
                        pred=model.predict(fitted,pos,prior,method)
                        self.assertAlmostEqual(sum(pred['probabilities']),1)
                        self.assertTrue(all(0<p<1 for p in pred['probabilities']))
                        self.assertTrue(0<=pred['expected_minutes']<=90)
            self.assertEqual(model.predict(fitted,'MID',[90,90],'last4')['expected_minutes'],90)
            with self.assertRaises(ValueError): model.predict(fitted,'MID',[float('nan')])
            with self.assertRaisesRegex(ValueError,'heldout'): model.evaluate(p,p)

    def test_calibration_and_scoring_use_matching_populations(self):
        rows=[dict(target=0,minutes=0),dict(target=2,minutes=90)]
        perfect=[dict(probabilities=[1,0,0],expected_minutes=0),dict(probabilities=[0,0,1],expected_minutes=90)]
        score=model.score(rows,perfect)
        self.assertEqual(score['multiclass_brier'],0)
        self.assertEqual(score['minutes_mae'],0)
        self.assertEqual(score['log_loss'],0)
        self.assertEqual(sum(r['n'] for r in score['calibration']),6)
        self.assertIsNone(model.score([],[])['minutes_mae'])
        with self.assertRaises(ValueError): model.score(rows,perfect[:1])
