import copy
import hashlib
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from core import fpl_api, forecast_archive as evidence, fpl_fixture_history as collector
from games.fpl import fixture_shadow as shadow, fixture_challenger as model, forecast_providers as providers
from scripts import evaluate_challenger as ridge

NOW = '2026-09-11T13:00:00Z'


def inputs():
    boot = dict(events=[dict(id=g, finished=g < 4, deadline_time=f'2026-09-0{g}T12:30:00Z')
                        for g in range(1,4)]+[dict(id=4,deadline_time='2026-09-12T12:30:00Z')],
        teams=[dict(id=i, short_name=str(i)) for i in range(1,4)],
        elements=[dict(id=i, web_name=str(i), team=1 if i in (1,3) else 2 if i == 2 else 3,
            element_type=3, now_cost=50, total_points=0 if i == 3 else 6,
            minutes=0 if i == 3 else 270, status='a') for i in range(1,5)])
    fixtures = [dict(id=g,event=g,team_h=1,team_a=2,started=g<4,finished=g<4,
        kickoff_time=f'2026-09-0{g}T15:00:00Z' if g < 4 else '2026-09-12T15:00:00Z',
        team_h_score=1 if g<4 else None,team_a_score=0 if g<4 else None) for g in range(1,5)]
    history = []
    for g in range(1,4):
        history.append(dict(gameweek=g,fetched_at=NOW,fixtures=[fixtures[g-1]],live=dict(elements=[
            dict(id=i,stats=dict(total_points=0 if i==3 else 2,minutes=0 if i==3 else 90,
                                expected_goals=0 if i==3 else .1,expected_assists=0)) for i in range(1,5)])))
    ctx = dict(bootstrap=boot,gameweek=4,all_fixtures=fixtures,fixtures=fixtures[-1:],history=history,
        captured_at=NOW,receipts={k:dict(recorded_at=NOW,payload_sha256=evidence.digest(v))
            for k,v in [('bootstrap',boot),('all_fixtures',fixtures)]})
    records = []
    for i in range(1,5):
        payload = dict(history=[] if i==3 else [dict(element=i,fixture=g,round=g,was_home=True,
            opponent_team=2,kickoff_time=fixtures[g-1]['kickoff_time'],team_h_score=1,team_a_score=0,
            total_points=2,minutes=90,expected_goals=.1,expected_assists=0) for g in range(1,4)])
        records.append(dict(player_id=i,season=evidence.deadline(boot,1).isoformat(),
            url=fpl_api.ELEMENT_SUMMARY.format(element_id=i),payload=payload,
            receipt=dict(recorded_at=NOW,payload_sha256=evidence.digest(payload))))
    collection = dict(gameweek=4,season=evidence.deadline(boot,1).isoformat(),captured_at=NOW,
        bootstrap_sha256=evidence.digest(boot),players=records)
    trained = providers.seal(dict(features=ridge.FEATURES,weights=[1]+[0]*8,
        cold_start_points={p:1 for p in ('GK','DEF','MID','FWD')},sources=[dict(sha256='train')],
        trained_through='2024-05-01T00:00:00Z',
        feature_source_sha256=hashlib.sha256(Path(ridge.__file__).read_bytes()).hexdigest()))
    research = dict(features=model.FEATURES,config=model.CONFIG,weights=dict(fixture=[1]+[0]*8+[1]+[0]*4),
        sources=[dict(sha256='train')],implementation_sha256=hashlib.sha256(Path(model.__file__).read_bytes()).hexdigest())
    return ctx,collection,research,trained


def reseal_receipt(record):
    record['receipt']['payload_sha256'] = evidence.digest(record['payload'])


class FixtureShadowTests(unittest.TestCase):
    def test_shared_transform_fallback_blank_and_availability(self):
        args = inputs()
        r = shadow.build(*args, now=NOW)
        self.assertEqual(r['comparison_ids'], [1,2])
        self.assertEqual(r['cold_start_ids'], [3])
        self.assertEqual(r['blank_ids'], [4])
        self.assertEqual([p['fixture_points'] for p in r['predictions']], [2,1,1,0])
        self.assertEqual(r['predictions'][0]['legs'][0]['features'][:9], ridge.feature_vector(
            args[1]['players'][0]['payload']['history'], 'MID'))
        args[0]['bootstrap']['elements'][0]['chance_of_playing_next_round']=50
        args[0]['receipts']['bootstrap']['payload_sha256']=evidence.digest(args[0]['bootstrap'])
        args[1]['bootstrap_sha256']=evidence.digest(args[0]['bootstrap'])
        r=shadow.build(*args,now=NOW)
        self.assertEqual(r['predictions'][0]['fixture_points'],1)
        self.assertEqual(r['predictions'][0]['production_points'],.5)

    def test_duplicate_missing_tampered_and_future_receipts_refused(self):
        for change in ('duplicate','missing','tampered','future'):
            args=inputs()
            if change=='duplicate': args[1]['players'][1]=copy.deepcopy(args[1]['players'][0])
            elif change=='missing': args[1]['players'].pop()
            elif change=='tampered': args[1]['players'][0]['payload']['history'][0]['minutes']=0
            else: args[1]['players'][0]['receipt']['recorded_at']='2026-09-12T12:00:00Z'
            with self.subTest(change=change), self.assertRaises(ValueError):
                shadow.build(*args,now=NOW)

    def test_cross_gw_reconciliation_and_identity_checks(self):
        for key,value in [('round',4),('fixture',999),('opponent_team',3),('minutes',89),('team_h_score',2)]:
            args=inputs(); rec=args[1]['players'][0]
            rec['payload']['history'][0][key]=value
            reseal_receipt(rec)
            with self.subTest(key=key), self.assertRaises(ValueError):
                shadow.build(*args,now=NOW)

    def test_double_separate_legs_and_no_target_results(self):
        args=inputs(); ctx=args[0]
        other=dict(ctx['fixtures'][0],id=5,team_h=2,team_a=1,kickoff_time='2026-09-14T15:00:00Z')
        ctx['all_fixtures'].append(other); ctx['fixtures'].append(other)
        ctx['receipts']['all_fixtures']['payload_sha256']=evidence.digest(ctx['all_fixtures'])
        r=shadow.build(*args,now=NOW)
        self.assertEqual(r['predictions'][0]['fixture_points'],3)
        self.assertEqual(len(r['predictions'][0]['legs']),2)
        self.assertEqual(r['predictions'][0]['production_points'],2)

    def test_freeze_replays_rejects_early_expired_and_overwrite(self):
        record=shadow.build(*inputs(),now=NOW)
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError): shadow.freeze(record,root,now='2026-09-10T13:00:00Z')
            with self.assertRaises(ValueError): shadow.freeze(record,root,now='2026-09-11T14:00:00Z')
            receipt=shadow.freeze(record,root,now=NOW)
            self.assertEqual(receipt['state'],'shadow_frozen')
            self.assertEqual(receipt,shadow.freeze(record,root,now=NOW))
            self.assertEqual(receipt,shadow.freeze(record,root,now='2026-09-13T13:00:00Z'))
            changed=shadow.build(*inputs(),now='2026-09-11T13:01:00Z')
            with self.assertRaises(ValueError): shadow.freeze(changed,root,now='2026-09-11T13:01:00Z')
            forged=copy.deepcopy(record); forged['predictions'][0]['fixture_points']=100
            forged=providers.seal({k:v for k,v in forged.items() if k!='artifact_id'})
            with self.assertRaises(ValueError): shadow.freeze(forged,root,now=NOW)

    def test_research_identity_and_season_must_match(self):
        for change in ('implementation','training','season','weights'):
            args=inputs()
            if change=='implementation': args[2]['implementation_sha256']='changed'
            elif change=='training': args[2]['sources'][0]['sha256']='different'
            elif change=='season': args[1]['season']='2025-08-01T00:00:00Z'
            else: args[2]['weights']['fixture'][0]=float('nan')
            with self.subTest(change=change), self.assertRaises(ValueError):
                shadow.build(*args,now=NOW)

    def test_collection_cannot_write_noninteger_player_paths(self):
        boot=inputs()[0]['bootstrap']
        boot['elements'][0]['id']='../../escape'
        with tempfile.TemporaryDirectory() as root, self.assertRaises(ValueError):
            collector.collect(boot,4,root,clock=lambda:evidence.utc(NOW),delay=0)

    def test_grade_only_frozen_complete_results(self):
        import json
        args=inputs(); record=shadow.build(*args,now=NOW)
        results=dict(gameweek=4,fetched_at='2026-09-13T20:00:00Z',
            fixtures=[dict(args[0]['fixtures'][0],finished=True)],
            live=dict(elements=[dict(id=i,stats=dict(total_points=2,minutes=90)) for i in range(1,5)]))
        with self.assertRaises(ValueError): shadow.grade(record,results,now=results['fetched_at'])
        with tempfile.TemporaryDirectory() as root:
            shadow.freeze(record,root,now=NOW)
            frozen=json.loads((Path(root)/'gw4.json').read_text())
            score=shadow.grade(frozen,results,now=results['fetched_at'])
            self.assertEqual(score['cohorts']['fixture_eligible']['fixture']['n'],2)
            for key in ('fixtures','live'):
                broken=copy.deepcopy(results)
                if key=='fixtures': broken[key][0]['finished']=False
                else: broken[key]['elements'].pop(0)
                with self.assertRaises(ValueError): shadow.grade(frozen,broken,now=results['fetched_at'])

    def test_collector_reuses_fresh_receipts_and_rejects_wrong_player(self):
        ctx,collection,_,_=inputs()
        payloads={r['player_id']:r['payload'] for r in collection['players']}
        calls=[]
        def fetch(pid): calls.append(pid); return payloads[pid]
        with tempfile.TemporaryDirectory() as root:
            for _ in range(2):
                r=collector.collect(ctx['bootstrap'],4,root,fetch=fetch,
                    clock=lambda:evidence.utc(NOW),workers=1,delay=0)
                self.assertEqual(len(r['players']),4)
            self.assertEqual(len(calls),4)
        with tempfile.TemporaryDirectory() as root, self.assertRaises(ValueError):
            collector.collect(ctx['bootstrap'],4,root,fetch=lambda pid:payloads[1],
                              clock=lambda:evidence.utc(NOW),workers=1,delay=0)
