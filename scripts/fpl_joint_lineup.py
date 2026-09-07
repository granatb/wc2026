#!/usr/bin/env python3
"""Retain actual engine draws and rehearse lineup choices on separate seeds."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import fpl_api, fpl_live, forecast_archive as evidence
from games.fpl import forecast_providers as providers, lineup_decisions as policy, joint_scenarios, experiments


def code_hashes():
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
            for p in map(Path,(__file__,policy.__file__,joint_scenarios.__file__))}


def analyze(bundle):
    """Offline replay of retained draws; never refetch data or rerun historical simulations."""
    providers.verify(bundle)
    source = bundle['source']
    providers.verify(source)
    boot = source['context']['bootstrap']
    resolved = fpl_live.resolve_squad(bundle['state'],boot)
    ids = [resolved[p['name']]['id'] for p in bundle['state']['squad']]
    elements = {p['id']:p for p in boot['elements']}
    positions = {pid:fpl_api.POSITIONS[elements[pid]['element_type']] for pid in ids}
    optimization, diagnostics = joint_scenarios.decode(source['market']['joint'],positions,source['predictions']['market'])
    audit, audit_diagnostics = joint_scenarios.decode(bundle['audit']['details']['joint'],positions,bundle['audit']['predictions'])
    if source['market']['joint']['seed'] == bundle['audit']['details']['joint']['seed']:
        raise ValueError('audit seed must differ from optimization seed')
    baseline = experiments.choose_decision(ids,source['predictions']['market'],boot)
    candidate = policy.optimize(positions,optimization)
    audit_candidate = policy.evaluate(positions,audit,candidate['decision'])
    audit_baseline = policy.evaluate(positions,audit,baseline)
    precision = joint_scenarios.paired_precision(positions,audit,candidate['decision'],baseline)
    return providers.seal(dict(status='joint_engine_rehearsal_not_enrolled',gameweek=source['context']['gameweek'],
        generated_at=bundle['generated_at'],source_artifact_id=bundle['artifact_id'],
        market_model_identity_sha256=bundle['market_model_identity_sha256'],
        code_sha256=code_hashes(), sims_per_seed=source['market']['joint']['sims'],
        optimization_seed=source['market']['joint']['seed'],audit_seed=bundle['audit']['details']['joint']['seed'],
        candidate=candidate,baseline=baseline,audit_candidate=audit_candidate,audit_baseline=audit_baseline,
        audit_delta=audit_candidate['total']-audit_baseline['total'],monte_carlo_precision=precision,
        diagnostics=diagnostics,audit_diagnostics=audit_diagnostics,
        names={str(pid):elements[pid]['web_name'] for pid in ids},
        limitations=['Engine simulations, not observed performance or demonstrated calibration.',
            'Joint draws retain the engine\'s dependence; between-fixture and availability assumptions remain model limitations.',
            'Market model only: these samples are not statistical, hybrid or external forecast distributions.',
            'Separate audit seed reduces simulation-selection optimism, not modeling error.',
            'No transfers, chips, frozen enrollment or changes to the controlled squad policy.']))


def run(context, trained, state, work, sims=5000):
    if not 1000 <= sims <= 20000:
        raise ValueError('1000 to 20000 simulations required')
    boot = context['bootstrap']
    resolved = fpl_live.resolve_squad(state,boot)
    ids = [resolved[p['name']]['id'] for p in state['squad']]
    def retained_market(boot,fixtures,odds,backfill,count):
        return providers.market_predictions(boot,fixtures,odds,backfill,count,retain_ids=ids,seed=12345)
    boards, source = providers.build_boards(context,trained,sims=sims,market_fn=retained_market)
    providers.verify_board_source('market',boards['market'],source)
    audit_predictions, audit_detail = providers.market_predictions(boot,context['fixtures'],context['odds'],
        context['backfill'],sims,retain_ids=ids,seed=12346)
    audit_rows = [dict(player_id=pid,x_points=score) for pid,score in sorted(audit_predictions.items())]
    finished = datetime.now(timezone.utc)
    if finished >= evidence.deadline(boot,context['gameweek']):
        raise ValueError('deadline passed while producing joint rehearsal')
    for key in ('bootstrap','all_fixtures'):
        evidence.require_fresh(context[key],context['receipts'][key],now=finished)
    bundle = providers.seal(dict(schema_version=1,kind='joint_lineup_rehearsal',
        generated_at=finished.isoformat(),source=source,audit=dict(predictions=audit_rows,details=audit_detail),
        state=state,code_sha256=code_hashes(),market_model_identity_sha256=boards['market']['model_identity_sha256']))
    result = analyze(bundle)
    if datetime.now(timezone.utc) >= evidence.deadline(boot,context['gameweek']):
        raise ValueError('deadline passed during decision analysis')
    path = Path(work)/(bundle['artifact_id']+'.json')
    evidence.atomic_json(path,bundle)
    print(f'Retained complete private sample bundle: {path}',flush=True)
    return result


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    inputs=ap.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--context',type=Path)
    inputs.add_argument('--replay',type=Path)
    ap.add_argument('--model',type=Path,default=Path('experiments/fpl-2026-27/statistical-model.json'))
    ap.add_argument('--state',type=Path,default=Path('games/fpl/state.json'))
    ap.add_argument('--work',type=Path,default=Path('data/experiments/joint-lineup'))
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    read=lambda p:json.loads(p.read_text())
    result=analyze(read(args.replay)) if args.replay else run(read(args.context),read(args.model),read(args.state),args.work)
    evidence.atomic_json(args.out,result)
    print(json.dumps(dict(audit_delta=result['audit_delta'],precision=result['monte_carlo_precision']),indent=2))
