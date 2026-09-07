#!/usr/bin/env python3
"""Sensitivity rehearsal for lineup decisions, never an enrolled squad change."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import fpl_api, fpl_live, fpl_priors, forecast_archive as evidence
from games.fpl import lineup_decisions as policy, experiments, fixture_shadow, forecast_providers as providers


def scenarios(means, chances, clubs, count, seed, correlation):
    """Conditional points fixed at mean/P(appear); appearance is explicit.

    Same-club shared uniform is a deliberately extreme dependence stress case,
    not an estimated football correlation. Marginal probabilities are unchanged.
    """
    rng = random.Random(seed)
    if correlation not in ('independent', 'shared_club'):
        raise ValueError('unknown sensitivity assumption')
    if set(means) != set(chances) or set(means) != set(clubs):
        raise ValueError('scenario input populations differ')
    for pid,p in chances.items():
        if not 0 <= p <= 1 or (p == 0 and means[pid] != 0):
            raise ValueError('appearance and point means inconsistent')
    out = []
    for _ in range(count):
        common = {club:rng.random() for club in sorted(set(clubs.values()))}
        rows = {}
        for pid in sorted(means):
            u = rng.random() if correlation == 'independent' else common[clubs[pid]]
            played = u < chances[pid]
            rows[pid] = dict(played=played, points=means[pid]/chances[pid] if played else 0)
        out.append(dict(weight=1/count, players=rows))
    return out


def run(source_record, state, now=None, optimization_draws=256, audit_draws=4096):
    now = evidence.utc(now or datetime.now(timezone.utc))
    providers.verify(source_record)
    source = source_record['source']
    live = fixture_shadow.build(source['context'], source['collection'], source['research'], source['trained'], now=now)
    ctx, boot = source['context'], source['context']['bootstrap']
    resolved = fpl_live.resolve_squad(state,boot)
    ids = [resolved[p['name']]['id'] for p in state['squad']]
    elements = {p['id']:p for p in boot['elements']}
    positions = {pid:fpl_api.POSITIONS[elements[pid]['element_type']] for pid in ids}
    clubs = {pid:elements[pid]['team'] for pid in ids}
    parsed = fpl_api.parse_players(boot)
    for p in parsed:
        p['season_started'] = any(e.get('finished') for e in boot['events'])
    priors,_ = fpl_priors.build_with_flags(parsed,sum(bool(e.get('finished')) for e in boot['events']),
        defcon_backfill={int(k):v for k,v in ctx['backfill'].items()})
    by_name = {p.name:p for group in priors.values() for p in group}
    counts = Counter(t for f in ctx['fixtures'] for t in (f['team_h'],f['team_a']))
    chances = {}
    for p in parsed:
        if p['id'] in positions:
            prior = by_name[p['name']]
            per_fixture = (prior.start_prob+(1-prior.start_prob)*prior.cameo_prob) if prior.start_prob > 0 else 0
            chances[p['id']] = 1-(1-per_fixture)**counts[clubs[p['id']]]
    rows = {r['player_id']:r for r in live['predictions']}
    results = {}
    for arm in ('production','fixture'):
        means = {pid:rows[pid][arm+'_points'] for pid in ids}
        baseline = experiments.choose_decision(ids,
            [dict(player_id=pid,x_points=mean) for pid,mean in means.items()],boot)
        modes = {}
        for mode in ('independent','shared_club'):
            train = scenarios(means,chances,clubs,optimization_draws,20260907,mode)
            candidate = policy.optimize(positions,train)
            audit = scenarios(means,chances,clubs,audit_draws,20260908,mode)
            baseline_score = policy.evaluate(positions,audit,baseline)
            candidate_score = policy.evaluate(positions,audit,candidate['decision'])
            modes[mode] = dict(candidate=candidate, baseline=baseline,
                audit_candidate=candidate_score,audit_baseline=baseline_score,
                audit_delta=candidate_score['total']-baseline_score['total'])
            print(f'{arm}/{mode}: independent-seed audit delta {modes[mode]["audit_delta"]:+.3f}',flush=True)
        results[arm] = modes
    body = dict(status='decision_rehearsal_not_enrolled', generated_at=now.isoformat(), gameweek=ctx['gameweek'],
        deadline=evidence.deadline(boot,ctx['gameweek']).isoformat(), policy_version=policy.VERSION,
        source_forecast_artifact_id=source_record['artifact_id'], source_sha256=evidence.digest(source),
        scenario_policy='prior_marginals_constant_conditional_points_v1',
        optimization_draws=optimization_draws,audit_draws=audit_draws,seeds=[20260907,20260908],
        scenario_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        optimizer_code_sha256=hashlib.sha256(Path(policy.__file__).read_bytes()).hexdigest(),
        squad_ids=ids, appearance_probabilities={str(k):v for k,v in chances.items()},
        names={str(pid):elements[pid]['web_name'] for pid in ids}, results=results,
        limitations=['Scenario expectations are not observed performance or evidence of a points gain.',
            'Appearance marginals approximate raw production priors, not simulated joint team lineups.',
            'Constant points given appearance omit role/points dependence and opponent correlations.',
            'Shared-club dependence is an extreme sensitivity assumption, not an estimated model.',
            'Separate random-seed audit reduces scenario-selection optimism but does not validate assumptions.',
            'No transfers, chips or policy changes to the four-arm experiment.'])
    return providers.seal(body)


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--state',type=Path,default=Path('games/fpl/state.json'))
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    result=run(json.loads(args.source.read_text()),json.loads(args.state.read_text()))
    evidence.atomic_json(args.out,result)
    print(f'Retained decision rehearsal: {args.out}')
