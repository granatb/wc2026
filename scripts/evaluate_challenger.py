#!/usr/bin/env python3
"""Chronological odds-free reference model. Stdlib, deterministic, no current stats.

Train on one complete season; evaluate once on a later season. Features use only
previous gameweeks. Same-week doubles are aggregated before feature construction.
Historical CSVs are retrospective extracts, NOT independently timestamped forecasts.
"""
import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

FEATURES = ['intercept', 'last4_points', 'last4_minutes_90', 'last4_xg', 'last4_xa',
            'season_points_per_gw', 'GK', 'DEF', 'MID']


def feature_vector(past, position):
    """One shared training/inference transform; each item is one prior GW."""
    if not past:
        raise ValueError('at least one prior gameweek is required')
    last = past[-4:]
    avg = lambda k: sum(r.get(k, 0) for r in last) / len(last)
    return [1, avg('total_points'), avg('minutes') / 90, avg('expected_goals'),
            avg('expected_assists'), sum(r.get('total_points', 0) for r in past)/len(past),
            int(position == 'GK'), int(position == 'DEF'), int(position == 'MID')]


def examples(path, min_prior=6):
    players = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    positions = {}
    with open(path, newline='', encoding='utf-8-sig') as fh:
        for r in csv.DictReader(fh):
            if r['position'] not in ('GK', 'DEF', 'MID', 'FWD'):
                continue  # 2024/25 Assistant Manager entries are not players.
            pid, gw = r['element'], int(r.get('GW') or r['round'])
            positions[pid, gw] = r['position']
            for key in ['total_points', 'minutes', 'expected_goals', 'expected_assists']:
                players[pid][gw][key] += float(r.get(key) or 0)
    out = []
    for pid, history in players.items():
        for gw in sorted(history):
            past_gws = sorted(g for g in history if g < gw)
            if len(past_gws) < min_prior:
                continue
            # Include blank/DNP weeks as zeros within the player's known history.
            start = past_gws[0]
            past = [history.get(g, {}) for g in range(start, gw)]
            pos = positions[pid, gw]
            x = feature_vector(past, pos)
            out.append({'gw': gw, 'player_id': pid, 'x': x,
                        'y': history[gw]['total_points'], 'minutes': history[gw]['minutes']})
    return sorted(out, key=lambda r: (r['gw'], r['player_id']))


def fit(train, ridge=100):
    n = len(FEATURES)
    a = [[sum(r['x'][i] * r['x'][j] for r in train) + (ridge if i == j and i else 0)
          for j in range(n)] + [sum(r['x'][i] * r['y'] for r in train)] for i in range(n)]
    for i in range(n):
        pivot = max(range(i, n), key=lambda j: abs(a[j][i]))
        a[i], a[pivot] = a[pivot], a[i]
        if abs(a[i][i]) < 1e-10:
            raise ValueError('singular training matrix')
        scale = a[i][i]
        a[i] = [v / scale for v in a[i]]
        for j in range(n):
            if j != i:
                scale = a[j][i]
                a[j] = [v - scale * w for v, w in zip(a[j], a[i])]
    return [a[i][-1] for i in range(n)]


def metrics(rows, predictions):
    errors = [p - r['y'] for r, p in zip(rows, predictions)]
    return {'n': len(errors), 'mae': statistics.mean(abs(e) for e in errors),
            'rmse': math.sqrt(statistics.mean(e * e for e in errors)),
            'bias': statistics.mean(errors)}


def season_window(path):
    with open(path, newline='', encoding='utf-8-sig') as fh:
        times = [datetime.fromisoformat(r['kickoff_time'].replace('Z', '+00:00'))
                 for r in csv.DictReader(fh) if r.get('kickoff_time')]
    if not times or any(t.tzinfo is None for t in times):
        raise ValueError('dated, timezone-aware matches are required')
    return min(times), max(times)


def run(train_path, test_path):
    train_window, test_window = season_window(train_path), season_window(test_path)
    if train_window[1] >= test_window[0]:
        raise ValueError('training must end before the held-out season begins')
    train, test = examples(train_path), examples(test_path)
    if not train or not test:
        raise ValueError('insufficient historical rows')
    weights = fit(train)  # fixed penalty; no tuning against the held-out season
    predictions = {'ridge': [sum(a*b for a,b in zip(weights, r['x'])) for r in test],
                   'last4': [r['x'][1] for r in test], 'season_ppg': [r['x'][5] for r in test]}
    scores = {name: metrics(test, preds) for name, preds in predictions.items()}
    cohorts = {}
    for name, eligible in [('played_60plus', lambda r: r['minutes'] >= 60),
                           ('prior_last4_60plus', lambda r: r['x'][2] >= 2/3)]:
        indices = [i for i, r in enumerate(test) if eligible(r)]
        cohorts[name] = {model: metrics([test[i] for i in indices], [ps[i] for i in indices])
                         for model, ps in predictions.items()}
    by_gw = defaultdict(list)
    for i, r in enumerate(test):
        by_gw[r['gw']].append((predictions['ridge'][i]-r['y'])**2 - (predictions['last4'][i]-r['y'])**2)
    # Block bootstrap gameweeks, not falsely independent player rows.
    rng = random.Random(731)
    blocks = list(by_gw.values())
    draws = []
    for _ in range(2000):
        selected = rng.choices(blocks, k=len(blocks))
        draws.append(sum(sum(b) for b in selected) / sum(len(b) for b in selected))
    draws.sort()
    sources = []
    for p in [train_path, test_path]:
        sources.append({'path': str(p), 'sha256': hashlib.sha256(Path(p).read_bytes()).hexdigest()})
    return {'generated_at': datetime.now(timezone.utc).isoformat(), 'model': 'odds-free-ridge-v1',
            'train_n': len(train), 'cohorts': cohorts, 'test_gameweeks': sorted(by_gw), 'scores': scores,
            'ridge_minus_last4_mse_block95': [draws[50], draws[1949]],
            'weights': dict(zip(FEATURES, weights)), 'ridge_penalty': 100,
            'sources': sources, 'train_end': train_window[1].isoformat(), 'test_start': test_window[0].isoformat(),
            'limitations': ['Retrospective extracts; not a point-in-time production forecast record.',
                           'Population: recorded player-gameweeks with at least six prior recorded gameweeks.',
                           'No odds comparison: historical pre-deadline odds are absent.',
                           'No current-season statistics, FC27 ratings, injuries, prices or ownership used.',
                           'Position is from the historical row; scoring rules differ from 2026/27.',
                           'No holdout hyperparameter search; independent prospective validation still required.']}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--train', type=Path, required=True)
    ap.add_argument('--test', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if args.train.resolve() == args.test.resolve():
        ap.error('training and held-out files must differ')
    report = run(args.train, args.test)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['scores'], indent=2))
