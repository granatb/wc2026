"""Dated recovery of a published early forecast and explicitly assumed teams.

These comparisons never enter the frozen-forecast ledger or its duel tally.
"""
import hashlib
import json
from pathlib import Path

from core import forecast_archive, fpl_live
from games.fpl import grading, publication_decision

REPO = Path(__file__).resolve().parents[2]
PATH = REPO / 'evmax/assets/comparisons/gw8-gw9.json'
BOARD = REPO / 'evmax/assets/previews/gw8/2026-10-21.json'
PLAN = REPO / 'evmax/assets/editorial/fpl-gw8/plan.json'
API = '/api/fpl/comparisons/gw8-gw9.json'


def selection(state):
    """Keep only the previously selected identities, positions and armbands."""
    keys = ('name', 'player_id', 'position', 'is_starter', 'is_captain', 'is_vice', 'bench_order')
    return {'active_chip': None, 'squad': [{k: p[k] for k in keys} for p in state['squad']]}


def model_state(plan, board):
    players = {p['name']: p for p in board['players']}
    lineup = plan['lineup']
    bench = [lineup['reserve_goalkeeper']] + lineup['outfield_bench_order']
    squad = []
    for name in lineup['xi'] + bench:
        row = players[name]
        squad.append(dict(name=name, player_id=int(row['page'].split('/')[-2].split('-')[0]),
                          position=row['position'], is_starter=name in lineup['xi'],
                          is_captain=name == lineup['captain'], is_vice=name == lineup['vice'],
                          bench_order=bench.index(name)+1 if name in bench else None))
    return {'active_chip': None, 'squad': squad}


def score(state, result, bootstrap):
    forecast_archive.require_final(result)
    publication_decision._selection(state['squad'], state=True)
    resolved = fpl_live.resolve_squad(state, bootstrap)
    stats = {p['id']: p['stats'] for p in result['live']['elements']}
    if any(p['id'] not in stats or not {'minutes', 'total_points'} <= stats[p['id']].keys()
           for p in resolved.values()):
        raise ValueError('missing official squad outcome')
    scored = fpl_live.grade_squad(state, result['live'], result['fixtures'], bootstrap)
    if scored['players_pending']:
        raise ValueError('squad results are pending')
    return scored


def evaluate(record, board, plan, baseline):
    """Recompute all numeric results from retained evidence, with no simulation."""
    deadline = forecast_archive.utc(board['preview']['deadline'])
    published = forecast_archive.utc(record['early_publication']['checked_at'])
    if (board['gameweek'] != 8 or plan['gameweek'] != 8 or
            not forecast_archive.utc(board['generated_at']) < published < deadline <
            forecast_archive.utc(record['recorded_at'])):
        raise ValueError('early forecast publication must precede its deadline')
    if record['consensus_state'] != selection(baseline['states']['consensus']):
        raise ValueError('stable consensus differs from the last published selection')
    if record['baseline_forecast_sha256'] != baseline['artifact_id']:
        raise ValueError('consensus baseline archive changed')
    if record['model_state'] != model_state(plan, board):
        raise ValueError('early model selection differs from published plan')
    stats = {p['id']: p['stats'] for p in record['results']['8']['live']['elements']}
    outcomes = {}
    for p in board['players']:
        pid = int(p['page'].split('/')[-2].split('-')[0])
        if pid not in stats or 'total_points' not in stats[pid]:
            raise ValueError('missing official forecast outcome')
        outcomes[p['name']] = stats[pid]['total_points']
    grade = grading.grade(board['players'], outcomes)
    if grade['missing']:
        raise ValueError('unresolved early forecast outcomes')
    projections = {p['name']: p['x_points'] for p in board['players']}
    projected = round(sum(projections[p['name']] * (1+int(p['is_captain']))
                          for p in record['model_state']['squad'] if p['is_starter']), 2)
    if abs(projected - plan['expected_points']) > 0.02:
        raise ValueError('published team projection does not match the early board')
    comparisons = []
    for gw in (8, 9):
        result = record['results'][str(gw)]
        if result['gameweek'] != gw or any(f['event'] != gw for f in result['fixtures']):
            raise ValueError('results belong to a different gameweek')
        cons = score(record['consensus_state'], result, record['bootstrap'])
        model = score(record['model_state'], result, record['bootstrap']) if gw == 8 else None
        comparisons.append(dict(gameweek=gw, model_scoring=model, consensus_scoring=cons,
                                model_projected=plan['expected_points'] if gw == 8 else None,
                                account=record['account'][str(gw)],
                                field_average=result['event']['average_entry_score']))
    return {'comparisons': comparisons, 'early_forecast_grade': grade}


def validate(record):
    board_bytes, plan_bytes = BOARD.read_bytes(), PLAN.read_bytes()
    for name, raw in [('players', board_bytes), ('plan', plan_bytes)]:
        actual = hashlib.sha256(raw).hexdigest()
        if actual != record['early_publication']['sha256'][name]:
            raise ValueError('published early evidence hash changed')
    computed = evaluate(record, json.loads(board_bytes), json.loads(plan_bytes), forecast_archive.load(7))
    if computed != record['evaluation']:
        raise ValueError('recorded comparison disagrees with official replay')
    return record


def load():
    return validate(json.loads(PATH.read_text())) if PATH.exists() else None


def rows(record=None):
    record = load() if record is None else record
    if not record:
        return []
    return [dict(gw=c['gameweek'], comparison_only=True,
                 model_realized=c['model_scoring']['total_so_far'] if c['model_scoring'] else None,
                 model_projected=c['model_projected'], model_label='21 Oct early' if c['gameweek']==8 else 'Not published',
                 consensus_realized=c['consensus_scoring']['total_so_far'], consensus_projected=None,
                 consensus_label='Reconstructed', account_realized=c['account']['points'],
                 json_path=API)
            for c in record['evaluation']['comparisons']]
