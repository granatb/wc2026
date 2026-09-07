"""Historical-only candidate: shrunk transitions between DNP, cameo and 60+ roles."""
import csv
import hashlib
import math
from collections import defaultdict
from pathlib import Path

from core import forecast_archive as evidence

POSITIONS = ('GK', 'DEF', 'MID', 'FWD')
STRENGTH = 20  # prespecified; no heldout tuning
CLASSES = ['did_not_play', 'played_under_60', 'played_60plus']


def role(minutes):
    return 0 if minutes == 0 else 1 if minutes < 60 else 2


def examples(path):
    players, first_kickoff, seen = defaultdict(list), {}, set()
    excluded = defaultdict(int)
    with Path(path).open(newline='', encoding='utf-8-sig') as handle:
        for row in csv.DictReader(handle):
            if row['position'] not in POSITIONS:
                excluded['non_player_rows'] += 1
                continue
            key = (row['element'], row['fixture'])
            if key in seen:
                raise ValueError('duplicate player-fixture row')
            seen.add(key)
            gw = int(row.get('GW') or row['round'])
            kickoff = evidence.utc(row['kickoff_time'])
            minutes = float(row['minutes'])
            if not math.isfinite(minutes) or not 0 <= minutes <= 90:
                raise ValueError('invalid historical minutes')
            first_kickoff[gw] = min(first_kickoff.get(gw, kickoff), kickoff)
            players[row['element']].append(dict(gw=gw, kickoff=kickoff,
                minutes=minutes, position=row['position']))
    out = []
    for pid, rows in players.items():
        rows.sort(key=lambda r:r['kickoff'])
        count = defaultdict(int)
        for row in rows: count[row['gw']] += 1
        for row in rows:
            if count[row['gw']] != 1:
                excluded['double_gameweek_rows'] += 1
                continue
            # No within-GW results, including an earlier fixture in a double.
            # A lower GW number played later must not enter the history either.
            past = [r for r in rows if r['gw'] < row['gw'] and r['kickoff'] < first_kickoff[row['gw']]]
            prior = [r['minutes'] for r in past]
            pos = past[-1]['position'] if past else row['position']
            out.append(dict(player_id=pid, gw=row['gw'], kickoff=row['kickoff'].isoformat(),
                            prior=prior, position=pos, minutes=row['minutes'], target=role(row['minutes'])))
    return sorted(out, key=lambda r:(r['kickoff'],r['player_id'])), dict(excluded)


def key(position, prior):
    if not prior:
        return position+'|cold'
    average = sum(prior[-4:])/len(prior[-4:])
    band = 0 if average < 15 else 1 if average < 60 else 2
    return f'{position}|{role(prior[-1])}|{band}'


def fit(rows):
    counts = {pos:[0,0,0] for pos in POSITIONS}
    sums = {pos:[0,0,0] for pos in POSITIONS}
    cells = defaultdict(lambda:[0,0,0])
    for row in rows:
        pos, target = row['position'], row['target']
        counts[pos][target] += 1
        sums[pos][target] += row['minutes']
        cells[key(pos,row['prior'])][target] += 1
    if any(sum(c) == 0 for c in counts.values()):
        raise ValueError('training requires all player positions')
    means = {p:[sums[p][i]/counts[p][i] if counts[p][i] else [0,30,80][i]
                for i in range(3)] for p in POSITIONS}
    return dict(version='minutes-transition-v1', classes=CLASSES, strength=STRENGTH,
                counts=counts, class_minutes=means, cells=dict(cells))


def predict(model, position, prior, method='transition'):
    if position not in POSITIONS or any(not math.isfinite(m) or not 0 <= m <= 90 for m in prior):
        raise ValueError('invalid prediction inputs')
    totals = model['counts'][position]
    base = [(v+1)/(sum(totals)+3) for v in totals]
    if method == 'transition':
        counts = model['cells'].get(key(position,prior), [0,0,0])
        strength = model['strength']
    elif method in ('last4', 'season'):
        observations = prior[-4:] if method == 'last4' else prior
        counts = [sum(role(m)==i for m in observations) for i in range(3)]
        strength = 1 if method == 'last4' else 3
    else:
        raise ValueError('unknown minutes method')
    probabilities = [(counts[i]+strength*base[i])/(sum(counts)+strength) for i in range(3)]
    expected = sum(p*m for p,m in zip(probabilities, model['class_minutes'][position]))
    if method in ('last4','season') and prior:
        observations = prior[-4:] if method == 'last4' else prior
        expected = sum(observations)/len(observations)
    return dict(probabilities=probabilities, expected_minutes=expected)


def score(rows, predictions):
    if len(rows) != len(predictions):
        raise ValueError('prediction/outcome populations differ')
    if not rows:
        return dict(n=0, multiclass_brier=None, log_loss=None, minutes_mae=None, minutes_rmse=None, calibration=[])
    brier, logloss, absolute, squared = [], [], [], []
    buckets = [[[] for _ in range(5)] for _ in range(3)]
    for row, pred in zip(rows,predictions):
        p, target = pred['probabilities'], row['target']
        brier.append(sum((value-int(i==target))**2 for i,value in enumerate(p)))
        logloss.append(-math.log(max(1e-15,p[target])))
        error = pred['expected_minutes']-row['minutes']
        absolute.append(abs(error)); squared.append(error*error)
        for i,value in enumerate(p): buckets[i][min(4,int(value*5))].append((value,int(i==target)))
    calibration = []
    for i, bins in enumerate(buckets):
        for bucket, values in enumerate(bins):
            if values:
                calibration.append(dict(role=CLASSES[i], bucket=bucket, n=len(values),
                    mean_probability=sum(p for p,y in values)/len(values),
                    observed_frequency=sum(y for p,y in values)/len(values)))
    return dict(n=len(rows), multiclass_brier=sum(brier)/len(rows), log_loss=sum(logloss)/len(rows),
        minutes_mae=sum(absolute)/len(rows), minutes_rmse=math.sqrt(sum(squared)/len(rows)), calibration=calibration)


def evaluate(train_path, test_path):
    from scripts.evaluate_challenger import season_window
    end = season_window(train_path)[1]
    start = season_window(test_path)[0]
    if end >= start:
        raise ValueError('training must precede heldout season')
    train, train_excluded = examples(train_path)
    test, test_excluded = examples(test_path)
    model = fit(train)
    predicates = dict(all_single_fixture=lambda r:True, cold_start=lambda r:not r['prior'],
        early_history=lambda r:0 < len(r['prior']) <= 4,
        prior_low_minutes=lambda r:bool(r['prior']) and sum(r['prior'][-4:])/len(r['prior'][-4:]) < 30,
        prior_regular=lambda r:bool(r['prior']) and sum(r['prior'][-4:])/len(r['prior'][-4:]) >= 60)
    metrics = {}
    forecasts = {method:[predict(model,r['position'],r['prior'],method) for r in test]
                 for method in ('transition','last4','season')}
    for cohort, eligible in predicates.items():
        indices = [i for i,r in enumerate(test) if eligible(r)]
        metrics[cohort] = {method:score([test[i] for i in indices], [preds[i] for i in indices])
                          for method,preds in forecasts.items()}
    from games.fpl.experiment_analysis import block_interval
    paired = {}
    for metric in ('multiclass_brier', 'minutes_mae', 'minutes_rmse'):
        differences = []
        weeks = sorted({r['gw'] for r in test})
        for gw in weeks:
            ids = [i for i,r in enumerate(test) if r['gw']==gw]
            values = [score([test[i] for i in ids], [forecasts[m][i] for i in ids])[metric]
                      for m in ('transition','last4')]
            differences.append(values[0]-values[1])
        paired[metric] = dict(gameweeks=weeks, mean_difference=sum(differences)/len(differences),
            exploratory_block95=(block_interval(differences) if all(b==a+1 for a,b in zip(weeks,weeks[1:])) else None),
            note='Transition minus last-four baseline; equal gameweek weights, 3-week blocks, unadjusted exploratory interval.')
    model.update(trained_through=end.isoformat(), training_n=len(train),
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        sources=[dict(path=Path(p).name, sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest())
                 for p in (train_path,test_path)])
    return dict(model=model, heldout_start=start.isoformat(), cohorts=metrics, paired_gameweeks=paired,
        excluded=dict(train=train_excluded,test=test_excluded), status='research_candidate_not_integrated',
        limitations=['Retrospective extracts, not independently timestamped forecasts.',
            'Pre-GW history cutoff is first kickoff; actual historical deadlines unavailable.',
            'Target cohort contains recorded single-fixture player-gameweeks; blanks and doubles are not evaluated.',
            'No injuries, lineup news, club changes or cross-season player joins.',
            'Cold start uses historical position; historical registration-time position not independently verified.',
            'Transition classes describe played minutes, not whether a player started.',
            'Hyperparameters fixed before holdout; no comparison to production heuristic with its historical priors.',
            'Class-conditional minute means approximate the full minutes distribution; no production replacement justified.'])
