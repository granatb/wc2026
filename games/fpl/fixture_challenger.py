"""Research-only fixture ridge. Fixed configuration; no odds or FC ratings."""
import csv
import hashlib
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from games.fpl.experiment_analysis import block_interval
from scripts.evaluate_challenger import feature_vector, metrics, season_window

BASE_FEATURES = ['intercept', 'last4_points_per_fixture', 'last4_minutes_90',
                 'last4_xg', 'last4_xa', 'season_points_per_fixture', 'GK', 'DEF', 'MID']
FEATURES = BASE_FEATURES + ['home_minutes', 'own_attack_minutes', 'own_defence_minutes',
                           'opponent_attack_minutes', 'opponent_defence_minutes']
CONFIG = dict(ridge=100, goal_prior=1.4, prior_matches=5, cutoff_hours=2, finish_hours=3,
              min_prior_fixtures=1)


def stamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timezone-aware kickoff required')
    return result


def read_rows(path):
    rows, seen = [], {}
    with open(path, newline='', encoding='utf-8-sig') as fh:
        for raw in csv.DictReader(fh):
            if raw['position'] not in ('GK', 'DEF', 'MID', 'FWD'):
                continue
            key = raw['element'], raw['fixture']
            if key in seen:
                if seen[key] == raw:
                    continue  # Exact source duplicates carry no additional evidence.
                raise ValueError('conflicting duplicate player-fixture')
            seen[key] = raw
            if raw['was_home'] not in ('True', 'False'):
                raise ValueError('invalid home flag')
            r = dict(player_id=raw['element'], fixture=raw['fixture'],
                     gw=int(raw.get('GW') or raw['round']), team=raw['team'],
                     position=raw['position'], home=raw['was_home'] == 'True',
                     kickoff=stamp(raw['kickoff_time']))
            for k in ('total_points', 'minutes', 'expected_goals', 'expected_assists',
                      'team_h_score', 'team_a_score'):
                r[k] = float(raw[k])
                if not math.isfinite(r[k]):
                    raise ValueError('nonfinite historical value')
            rows.append(r)
    return rows


def fixture_index(rows):
    fixtures = {}
    for r in rows:
        signature = (r['gw'], r['kickoff'], r['team_h_score'], r['team_a_score'])
        f = fixtures.setdefault(r['fixture'], dict(signature=signature, teams={}))
        if f['signature'] != signature:
            raise ValueError('conflicting fixture metadata')
        side = r['home']
        if side in f['teams'] and f['teams'][side] != r['team']:
            raise ValueError('conflicting fixture team')
        f['teams'][side] = r['team']
    if any(set(f['teams']) != {True, False} for f in fixtures.values()):
        raise ValueError('both fixture teams required')
    return fixtures


def strengths(fixtures, gw, cutoff):
    totals = defaultdict(lambda: [0, 0, 0])
    for f in fixtures.values():
        week, kickoff, home_score, away_score = f['signature']
        if week >= gw or kickoff + timedelta(hours=CONFIG['finish_hours']) >= cutoff:
            continue
        for side, gf, ga in ((True, home_score, away_score), (False, away_score, home_score)):
            a = totals[f['teams'][side]]
            a[0] += gf
            a[1] += ga
            a[2] += 1
    def rate(team):
        gf, ga, n = totals[team]
        p, prior = CONFIG['prior_matches'], CONFIG['goal_prior']
        return ((gf+p*prior)/(n+p)-prior, (ga+p*prior)/(n+p)-prior)
    return rate


def vector(past, position, home, own_strength, opponent_strength):
    base = feature_vector(past, position)
    minutes = base[2]
    return base + [minutes*int(home)] + [minutes*v for v in own_strength+opponent_strength]


def predict_week(weights, vectors):
    """Sum separately described fixtures; an explicitly empty schedule is a blank."""
    if any(len(v) != len(weights) for v in vectors):
        raise ValueError('feature dimension mismatch')
    return sum(sum(a*b for a,b in zip(weights, v)) for v in vectors)


def examples(rows):
    fixtures = fixture_index(rows)
    deadlines = {}
    histories = defaultdict(list)
    targets = defaultdict(list)
    for r in rows:
        gw = r['gw']
        deadlines[gw] = min(deadlines.get(gw, r['kickoff']), r['kickoff'])
        histories[r['player_id']].append(r)
        targets[gw, r['player_id']].append(r)
    rates = {gw: strengths(fixtures, gw, start-timedelta(hours=CONFIG['cutoff_hours']))
             for gw, start in deadlines.items()}
    out = []
    for (gw, pid), legs in sorted(targets.items()):
        cutoff = deadlines[gw]-timedelta(hours=CONFIG['cutoff_hours'])
        past = sorted((r for r in histories[pid] if r['gw'] < gw and
                       r['kickoff']+timedelta(hours=CONFIG['finish_hours']) < cutoff),
                      key=lambda r: (r['kickoff'], r['fixture']))
        if len(past) < CONFIG['min_prior_fixtures']:
            continue
        xs = []
        for r in sorted(legs, key=lambda r: (r['kickoff'], r['fixture'])):
            opponent = fixtures[r['fixture']]['teams'][not r['home']]
            xs.append(vector(past, r['position'], r['home'], rates[gw](r['team']), rates[gw](opponent)))
        out.append(dict(gw=gw, player_id=pid, xs=xs, ys=[r['total_points'] for r in sorted(
            legs, key=lambda r: (r['kickoff'], r['fixture']))],
            y=sum(r['total_points'] for r in legs), prior_minutes=xs[0][2]*90))
    return out


def fit(rows, size):
    a = [[0.0]*(size+1) for _ in range(size)]
    for r in rows:
        for x, y in zip(r['xs'], r['ys']):
            for i in range(size):
                a[i][-1] += x[i]*y
                for j in range(size):
                    a[i][j] += x[i]*x[j]
    for i in range(1, size):
        a[i][i] += CONFIG['ridge']
    for i in range(size):
        pivot = max(range(i, size), key=lambda j: abs(a[j][i]))
        a[i], a[pivot] = a[pivot], a[i]
        if abs(a[i][i]) < 1e-10:
            raise ValueError('singular training matrix')
        scale = a[i][i]
        a[i] = [v/scale for v in a[i]]
        for j in range(size):
            if i != j:
                scale = a[j][i]
                a[j] = [v-scale*w for v,w in zip(a[j], a[i])]
    return [row[-1] for row in a]


def evaluate(train_path, test_path):
    if season_window(train_path)[1] >= season_window(test_path)[0]:
        raise ValueError('training must precede evaluation')
    train, test = examples(read_rows(train_path)), examples(read_rows(test_path))
    weights = dict(fixture=fit(train, len(FEATURES)), ablation=fit(train, len(BASE_FEATURES)))
    predictions = {name: [predict_week(w, [x[:len(w)] for x in r['xs']]) for r in test]
                   for name,w in weights.items()}
    predictions['last4_per_fixture'] = [sum(x[1] for x in r['xs']) for r in test]
    scores = {}
    for cohort, eligible in [('all_recorded', lambda r: True),
                             ('prior_60plus', lambda r: r['prior_minutes'] >= 60),
                             ('double', lambda r: len(r['xs']) > 1)]:
        ids = [i for i,r in enumerate(test) if eligible(r)]
        scores[cohort] = {name: metrics([test[i] for i in ids], [ps[i] for i in ids])
                          for name,ps in predictions.items()} if ids else {}
    by_gw = defaultdict(list)
    for i,r in enumerate(test):
        by_gw[r['gw']].append((predictions['fixture'][i]-r['y'])**2 -
                             (predictions['ablation'][i]-r['y'])**2)
    weeks = sorted(by_gw)
    differences = [sum(by_gw[g])/len(by_gw[g]) for g in weeks]
    return dict(model='fixture-ridge-research-v1', status='research_only', config=CONFIG,
        features=FEATURES, weights=weights, train_player_gameweeks=len(train), scores=scores,
        test_gameweeks=weeks, fixture_minus_ablation_equal_gw_mse=sum(differences)/len(differences),
        exploratory_block95=(block_interval(differences) if all(b == a+1 for a,b in zip(weeks,weeks[1:])) else None),
        sources=[dict(path=str(p),sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest())
                 for p in (train_path,test_path)],
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitations=['Retrospective fixtures and positions, not archived deadline snapshots.',
            'Cutoff proxy: first GW kickoff minus two hours; prior kickoff plus three hours must precede it.',
            'Only recorded player-gameweeks with prior fixtures; no validated blank or cold-start cohort.',
            'Doubles summed by fixture with identical pre-GW player history; no first-leg outcome leakage.',
            'Ablation isolates fixture features; not a head-to-head comparison with the production GW ridge.',
            'No odds, FC27, injury or historical availability inputs; scoring rules can change between seasons.',
            'Intervals are exploratory, unadjusted and do not establish a prospective edge.'])
