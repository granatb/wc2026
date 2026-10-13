import copy
import tempfile
import unittest
from pathlib import Path
from core import forecast_archive as evidence
from games.fpl import publication_decision as decision

NOW='2026-10-09T15:00:00Z'
class DecisionTests(unittest.TestCase):
    def setUp(self):
        a=evidence.load(6)
        self.states=copy.deepcopy(a['states'])
        self.rows=copy.deepcopy(a['rows'])
        self.boot=a['bootstrap']
        self.entries={k:a['envelopes'][slug]['entries'] for k,slug in
                      [('model','our-squad'),('consensus','consensus-squad')]}
        self.context=dict(rows=self.rows, bootstrap_sha256=evidence.digest(self.boot), sims=a['sims'])
        self.draft=decision.prepare(6,self.states,self.entries,self.context,self.boot,now=NOW)
    def accepted(self):
        return decision.accept(self.draft, self.draft['proposal_id'], 'Test operator',
            'Reviewed hold, captain and ordered bench; account submission remains separate.',now=NOW)
    def test_accepted_receipt_matches_and_account_submission_is_separate(self):
        receipt=self.accepted()
        decision.require_accepted(receipt,self.draft,now=NOW)
        self.assertEqual(receipt['account_submission'],'unverified')
        self.assertIn('current_squad_best_xi_points',self.draft['review']['model'])
        self.assertEqual(receipt['proposal']['states'],self.states)
    def test_missing_unaccepted_and_changed_inputs_are_blocked(self):
        for receipt in (None,self.draft):
            with self.assertRaises(ValueError):decision.require_accepted(receipt,self.draft,now=NOW)
        for key in ('captain','bench','bank','forecast'):
            s=copy.deepcopy(self.states);c=copy.deepcopy(self.context)
            if key=='bank':s['model']['bank']=1
            if key=='forecast':c['rows'][0]['x_points']+=1
            if key in ('captain','bench'):
                es=s['model']['squad']
                if key=='captain':
                    a=next(x for x in es if x['is_captain']);b=next(x for x in es if x['is_vice'])
                    a['is_captain'],b['is_captain']=False,True
                    a['is_vice'],b['is_vice']=True,False
                else:
                    a,b=[x for x in es if not x['is_starter']][:2]
                    a['bench_order'],b['bench_order']=b['bench_order'],a['bench_order']
            changed=dict(self.draft, states=s,forecast_sha256=evidence.digest(c))
            changed['proposal_id']=decision.proposal_id(changed)
            with self.subTest(key=key),self.assertRaises(ValueError):
                decision.require_accepted(self.accepted(),changed,now=NOW)
    def test_publication_entries_must_equal_state_decisions(self):
        entries=copy.deepcopy(self.entries)
        for e in entries['model']:
            if e['is_captain']:e['is_captain']=False
        with self.assertRaisesRegex(ValueError,'published squad'):
            decision.prepare(6,self.states,entries,self.context,self.boot,now=NOW)
    def test_wrong_review_id_blank_rationale_and_late_acceptance_fail(self):
        for ident,reason,now in [('0'*64,'reviewed',NOW),(self.draft['proposal_id'],'',NOW),
            (self.draft['proposal_id'],'reviewed','2026-10-10T11:00:00Z')]:
            with self.assertRaises(ValueError):decision.accept(self.draft,ident,'Operator',reason,now=now)
        forged=self.accepted();forged['proposal']['states']['model']['bank']=100
        with self.assertRaises(ValueError):decision.require_accepted(forged,self.draft,now=NOW)
    def test_write_never_overwrites_an_accepted_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'gw6.json'
            decision.save_accepted(path,self.accepted())
            with self.assertRaises(FileExistsError):decision.save_accepted(path,self.accepted())


class PublicationGateTests(unittest.TestCase):
    def test_production_build_blocks_before_site_writes_without_acceptance(self):
        from unittest.mock import patch
        from evmax import fpl_build
        from datetime import datetime,timezone,timedelta
        a=evidence.load(6)
        boot=copy.deepcopy(a['bootstrap'])
        event=next(e for e in boot['events'] if e['id']==7)
        event['deadline_time']=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        players={r['name']:dict(id=r['player_id'],ep_next=r.get('ep_next')) for r in a['rows']}
        stamp=datetime.now(timezone.utc).isoformat()
        cache={'bootstrap':boot,'fixtures':[],'odds_gw7':{'captured_at':stamp}}
        for key in ('bootstrap','fixtures'):
            cache[key+'.meta']=dict(recorded_at=stamp,payload_sha256=evidence.digest(cache[key]))
        entries={slug:e['entries'] for slug,e in a['envelopes'].items()}
        metas={slug:e['squad'] for slug,e in a['envelopes'].items() if e.get('squad')}
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(evidence,'load',return_value=None), \
             patch.object(fpl_build.fpl_api,'read_cache',side_effect=lambda k:cache.get(k)), \
             patch.object(fpl_build.fpl_model,'load_gameweek',return_value=({},players,[])), \
             patch.object(fpl_build.fpl_model,'build_artifact',return_value=(a,True)), \
             patch.object(fpl_build,'preflight',return_value=[]), \
             patch.object(fpl_build,'load_states',return_value=copy.deepcopy(a['states'])), \
             patch.object(fpl_build,'dossier_gate'), \
             patch.object(fpl_build,'entries_or_abort',return_value=(copy.deepcopy(entries),metas)), \
             patch.object(decision,'receipt_path',return_value=Path(tmp)/'missing.json'):
            out=Path(tmp)/'dist'
            with self.assertRaisesRegex(ValueError,'accepted publication decision missing'):
                fpl_build.build(7,out=str(out),live=False,preview=False,use_llm=False)
            self.assertFalse(out.exists())


class ForecastBindingTests(unittest.TestCase):
    def test_context_survives_json_roundtrip_but_rejects_changed_forecast(self):
        import json
        a=evidence.load(6)
        context=decision.forecast_context(a['rows'],a['matches'],a['sims'],a['bootstrap'],
            a['inputs']['fixtures'],a['inputs']['odds'],a['source_fingerprint'])
        ints=copy.deepcopy(context)
        for row in ints['rows']:
            if row.get('distribution'):
                row['distribution']={int(k):v for k,v in row['distribution'].items()}
        self.assertEqual(decision.context_digest(ints),decision.context_digest(json.loads(json.dumps(ints))))
        receipt=dict(proposal=dict(forecast_sha256=decision.context_digest(context)))
        decision.verify_forecast(receipt,a)
        changed=copy.deepcopy(a);changed['rows'][0]['x_points']+=1
        with self.assertRaisesRegex(ValueError,'forecast'):
            decision.verify_forecast(receipt,changed)
