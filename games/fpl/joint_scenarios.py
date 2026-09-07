"""Validate and decode retained engine draws without destroying their alignment."""
from collections import Counter
import math


def decode(joint, positions, prediction_rows):
    sims = joint['sims']
    if type(sims) is not int or not 1 <= sims <= 20000:
        raise ValueError('invalid retained simulation count')
    if type(joint['seed']) is not int or joint.get('schema_version') != 1:
        raise ValueError('invalid joint sample version or seed')
    players = {r['player_id']:r for r in joint['players']}
    if len(players) != len(joint['players']) or set(players) != set(positions):
        raise ValueError('complete unique retained squad required')
    predictions = {r['player_id']:r['x_points'] for r in prediction_rows}
    if len(predictions) != len(prediction_rows) or not set(positions) <= set(predictions):
        raise ValueError('prediction population mismatch')
    diagnostics = {}
    for pid,r in players.items():
        if len(r['points']) != sims or len(r['played']) != sims:
            raise ValueError('joint columns lost simulation alignment')
        if any(type(v) is not int for v in r['points']) or any(type(v) is not bool for v in r['played']):
            raise ValueError('integer points and explicit boolean appearance required')
        if any(not played and points != 0 for played,points in zip(r['played'],r['points'])):
            raise ValueError('non-appearance with nonzero points')
        mean = sum(r['points'])/sims
        if not math.isfinite(predictions[pid]) or round(mean,2) != predictions[pid]:
            raise ValueError('sample mean does not reproduce forecast')
        diagnostics[str(pid)] = dict(mean=mean, forecast=predictions[pid],
            appearance_probability=sum(r['played'])/sims,
            played_zero_points=sum(played and pts == 0 for played,pts in zip(r['played'],r['points'])),
            points_histogram=dict(sorted(Counter(r['points']).items())))
    scenarios = [dict(weight=1/sims,players={pid:dict(points=r['points'][i],played=r['played'][i])
                 for pid,r in players.items()}) for i in range(sims)]
    return scenarios, diagnostics


def paired_precision(positions, scenarios, candidate, baseline):
    """Monte Carlo error conditional on this simulator; not performance uncertainty."""
    import statistics
    from games.fpl import lineup_decisions
    n = len(scenarios)
    if n < 2 or any(not math.isclose(s['weight'],1/n) for s in scenarios):
        raise ValueError('at least two equally weighted audit draws required')
    differences = []
    for s in scenarios:
        single = [dict(s,weight=1)]
        differences.append(lineup_decisions.evaluate(positions,single,candidate)['total']-
                           lineup_decisions.evaluate(positions,single,baseline)['total'])
    mean = statistics.mean(differences)
    se = statistics.stdev(differences)/math.sqrt(n)
    return dict(mean=mean,standard_error=se,normal_interval95=[mean-1.96*se,mean+1.96*se],
        note='Monte Carlo precision conditional on this simulator, not a confidence interval for real-world improvement.')
