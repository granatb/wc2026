"""Pre-deadline cohorts and paired gameweek analysis; never an automatic winner."""
import itertools
import math
import random

MIN_INTERVAL_WEEKS = 12
BLOCK_LENGTH = 3


def cohorts(record):
    """Use only the frozen record. Realized minutes never select this population."""
    population = set(record['population_ids'])
    players = {p['id']:p for p in record['bootstrap']['elements']}
    completed = sum(bool(e.get('finished')) for e in record['bootstrap']['events']
                    if e['id'] < record['gameweek'])
    regular = sorted(pid for pid in population if completed and
                     players[pid].get('minutes', 0)/completed >= 60)
    return dict(all_players=sorted(population), prior_60plus=regular,
                selected_by_any_arm=sorted({pid for sub in record['arms'].values() for pid in sub['squad_ids']}))


def errors(predictions, stats, ids):
    if not ids:
        return dict(n=0, mse=None, rmse=None, mae=None, bias=None)
    delta = [predictions[pid]-stats[pid]['total_points'] for pid in ids]
    mse = sum(e*e for e in delta)/len(delta)
    return dict(n=len(delta), mse=mse, rmse=math.sqrt(mse),
                mae=sum(abs(e) for e in delta)/len(delta), bias=sum(delta)/len(delta))


def block_interval(values, draws=2000):
    """Moving blocks of consecutive gameweeks preserve short-range dependence.

    Exploratory percentile interval; not a multiple-comparison-adjusted test.
    Fixed seed makes reports reproducible. Fewer than 12 weeks return no interval.
    """
    if len(values) < MIN_INTERVAL_WEEKS:
        return None
    blocks = [values[i:i+BLOCK_LENGTH] for i in range(len(values)-BLOCK_LENGTH+1)]
    rng = random.Random(20260907)
    means = []
    for _ in range(draws):
        sample = []
        while len(sample) < len(values):
            sample.extend(rng.choice(blocks))
        means.append(sum(sample[:len(values)])/len(values))
    means.sort()
    return [means[int(draws*.025)], means[min(draws-1, int(draws*.975))]]


def summarize(grades):
    cohorts_out, comparisons = {}, []
    if not grades:
        return dict(cohorts=cohorts_out, comparisons=comparisons,
                    uncertainty_note='No prospective results; no model comparison is available.')
    grades = sorted(grades, key=lambda g:g['gameweek'])
    names = sorted(grades[0]['arms'])
    cohort_names = sorted(grades[0]['arms'][names[0]]['cohorts'])
    for cohort in cohort_names:
        eligible = []
        for grade in grades:
            counts = {grade['arms'][arm]['cohorts'][cohort]['n'] for arm in names}
            if len(counts) != 1:
                raise ValueError('unequal cohort populations')
            if next(iter(counts)):
                eligible.append(grade)
        rows = {}
        for arm in names:
            scores = [g['arms'][arm]['cohorts'][cohort] for g in eligible]
            rows[arm] = dict(gameweeks=len(scores), player_gameweeks=sum(s['n'] for s in scores),
                rmse=(math.sqrt(sum(s['mse'] for s in scores)/len(scores)) if scores else None),
                mae=(sum(s['mae'] for s in scores)/len(scores) if scores else None),
                bias=(sum(s['bias'] for s in scores)/len(scores) if scores else None))
        cohorts_out[cohort] = rows
        for left, right in itertools.combinations(names, 2):
            diffs = [g['arms'][left]['cohorts'][cohort]['mse']-
                     g['arms'][right]['cohorts'][cohort]['mse'] for g in eligible]
            versions = {arm:sorted({g['arms'][arm]['model_version']+'@'+str(g['arms'][arm].get('model_identity_sha256') or 'legacy')
                                    for g in eligible}) for arm in (left, right)}
            weeks = [g['gameweek'] for g in eligible]
            if len(diffs) < MIN_INTERVAL_WEEKS:
                status = 'insufficient_gameweeks'
            elif any(not g['arms'][arm].get('model_identity_disclosed', True) for g in eligible for arm in (left,right)):
                status = 'undisclosed_model_revision'
            elif any(len(v) != 1 for v in versions.values()):
                status = 'mixed_model_versions'
            elif any(b != a+1 for a,b in zip(weeks, weeks[1:])):
                status = 'nonconsecutive_gameweeks'
            else:
                status = 'exploratory_interval'
            comparisons.append(dict(cohort=cohort, left=left, right=right, gameweeks=weeks,
                mean_mse_difference=sum(diffs)/len(diffs) if diffs else None,
                interval95=block_interval(diffs) if status == 'exploratory_interval' else None,
                status=status, model_versions=versions,
                interpretation='Negative favors the left approach. Descriptive comparison, not a promotion decision.'))
    return dict(cohorts=cohorts_out, comparisons=comparisons,
        uncertainty_note='Equal gameweek weights. Exploratory 95% moving-block intervals use 3-week blocks; '
        'require 12 consecutive eligible weeks with unchanged model versions. Intervals are not adjusted '
        'for multiple comparisons and do not establish next-season performance. Unknown external model revisions suppress intervals.')
