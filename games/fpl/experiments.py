"""Prospective virtual squad ledger. Pure validation/scoring plus atomic evidence I/O.

An experiment begins only when ALL arms submit eligible forecasts and a common
seed roster. No retrospective enrollment, automatic model selection or invented
forecasts. Chips are deliberately disabled under the registered v1 protocol.
"""
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
import tempfile
from pathlib import Path

from core import forecast_archive as evidence, fpl_live

QUOTA = {'GK': 2, 'DEF': 5, 'MID': 5, 'FWD': 3}
POSITIONS = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}


def _integer(value, label):
    if type(value) is not int:
        raise ValueError(f'{label} must be an integer')
    return value


def _ids(values, size, label):
    if not isinstance(values, list) or len(values) != size:
        raise ValueError(f'{label} requires {size} IDs')
    for value in values:
        _integer(value, label)
    if len(set(values)) != size:
        raise ValueError(f'{label} contains duplicate IDs')
    return values


def _predictions(rows):
    result = {}
    for row in rows:
        pid = _integer(row['player_id'], 'player_id')
        xp = row['x_points']
        if isinstance(xp, bool) or not isinstance(xp, (int, float)) or not math.isfinite(xp):
            raise ValueError('forecasts require finite numeric x_points')
        if pid in result:
            raise ValueError('duplicate prediction ID')
        result[pid] = xp
    if not result:
        raise ValueError('forecast population is empty')
    return result


def _roster(submission, elements):
    squad = _ids(submission['squad_ids'], 15, 'squad')
    xi = _ids(submission['xi_ids'], 11, 'XI')
    bench = _ids(submission['bench_ids'], 4, 'ordered bench')
    if set(xi) & set(bench) or set(xi + bench) != set(squad):
        raise ValueError('XI and bench must partition the squad')
    if any(pid not in elements for pid in squad):
        raise ValueError('unknown squad ID')
    positions = Counter(POSITIONS[elements[pid]['element_type']] for pid in squad)
    if positions != QUOTA:
        raise ValueError('illegal squad position quotas')
    clubs = Counter(elements[pid]['team'] for pid in squad)
    if max(clubs.values()) > 3:
        raise ValueError('more than three players from a club')
    counts = Counter(POSITIONS[elements[pid]['element_type']] for pid in xi)
    if counts['GK'] != 1 or not 3 <= counts['DEF'] <= 5 or not 2 <= counts['MID'] <= 5 or not 1 <= counts['FWD'] <= 3:
        raise ValueError('illegal XI formation')
    captain, vice = submission['captain_id'], submission['vice_id']
    if captain == vice or captain not in xi or vice not in xi:
        raise ValueError('distinct captain and vice must be in the XI')
    return squad


def _portfolio(protocol, squad, elements, previous):
    prices = {str(pid): _integer(elements[pid]['now_cost'], 'price') for pid in squad}
    if previous is None:
        bank = protocol['starting_budget_tenths'] - sum(prices.values())
        result = dict(bank_tenths=bank, purchase_prices=prices, transfers_in=[], transfers_out=[],
                      hit_points=0, free_transfers_before=0,
                      free_transfers_next=protocol['initial_free_transfers'])
    else:
        old = set(previous['squad_ids'])
        sold, bought = sorted(old - set(squad)), sorted(set(squad) - old)
        portfolio = previous['portfolio']
        bank = portfolio['bank_tenths']
        purchases = dict(portfolio['purchase_prices'])
        for pid in sold:
            if pid not in elements:
                raise ValueError('sale price unavailable for removed player')
            current, paid = elements[pid]['now_cost'], purchases.pop(str(pid))
            # FPL: keep half of the increase, rounded down to a whole 0.1m.
            bank += paid + (current - paid) // 2 if current > paid else current
        for pid in bought:
            bank -= prices[str(pid)]
            purchases[str(pid)] = prices[str(pid)]
        available = portfolio['free_transfers_next']
        hits = max(0, len(bought) - available) * protocol['hit_cost']
        result = dict(bank_tenths=bank, purchase_prices=purchases,
                      transfers_in=bought, transfers_out=sold, hit_points=hits,
                      free_transfers_before=available,
                      free_transfers_next=min(protocol['max_free_transfers'], max(0, available-len(bought))+1))
    if result['bank_tenths'] < 0:
        raise ValueError('squad exceeds available funds')
    return result


def prepare_week(protocol, gw, bootstrap, submissions, previous=None, now=None, fixtures=None):
    now = evidence.utc(now or datetime.now(timezone.utc))
    lock = evidence.deadline(bootstrap, gw)
    if now >= lock:
        raise ValueError('deadline passed: no retrospective experiment enrollment')
    if set(submissions) != set(protocol['arms']):
        raise ValueError('every registered arm must submit together')
    if previous:
        if previous['protocol_sha256'] != evidence.digest(protocol):
            raise ValueError('protocol changed: start a separate experiment')
        if gw != previous['gameweek'] + 1:
            raise ValueError('gameweek gap or duplicate; do not silently restart the season')
    if not fixtures or any(f.get('event') != gw for f in fixtures):
        raise ValueError('complete current-gameweek fixture context required')
    elements = {e['id']: e for e in bootstrap['elements']}
    population, seed, policies, arms = None, None, set(), {}
    for arm in sorted(submissions):
        sub = submissions[arm]
        if sub.get('chip') is not None:
            raise ValueError('chips disabled under this protocol')
        for key in ('model_version', 'decision_policy_id', 'source_artifact_id'):
            if not isinstance(sub.get(key), str) or not sub[key].strip():
                raise ValueError(f'{arm}: {key} required')
        key = sub['source_artifact_id']
        if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('source_artifact_id must be a SHA-256 digest')
        generated = evidence.utc(sub['generated_at'])
        if not 0 <= (now-generated).total_seconds() <= protocol['forecast_window_minutes']*60:
            raise ValueError('forecasts must share the registered pre-deadline capture window')
        if evidence.utc(sub['trained_through']) >= lock or evidence.utc(sub['trained_through']) > generated:
            raise ValueError('training cutoff must precede this deadline and forecast generation')
        if sub.get('bootstrap_sha256') != evidence.digest(bootstrap):
            raise ValueError('arms must use the same frozen player/price context')
        if sub.get('fixtures_sha256') != evidence.digest(fixtures):
            raise ValueError('arms must use the same frozen fixture context')
        for intervention in sub.get('interventions', []):
            if not intervention.get('reason') or not intervention.get('source'):
                raise ValueError('human intervention requires reason and source')
            if evidence.utc(intervention['recorded_at']) > now:
                raise ValueError('future-dated intervention')
        pred = _predictions(sub['predictions'])
        if population is not None and set(pred) != population:
            raise ValueError('forecast populations differ between arms')
        population = set(pred)
        if population != set(elements):
            raise ValueError('full frozen bootstrap population required; no selective coverage')
        squad = _roster(sub, elements)
        if not set(squad) <= population:
            raise ValueError('squad player has no forecast')
        if not previous:
            if seed is not None and set(squad) != seed:
                raise ValueError('all arms must start from the same seed roster')
            seed = set(squad)
        policies.add(sub['decision_policy_id'])
        old = previous['arms'][arm] if previous else None
        if sub['decision_policy_id'] != 'single_swap_xi_mean_v1':
            raise ValueError('unregistered decision policy')
        expected = choose_decision(old['squad_ids'] if old else squad, sub['predictions'], bootstrap,
                                   old['portfolio'] if old else None)
        keys = ('xi_ids', 'bench_ids', 'captain_id', 'vice_id')
        diverges = set(expected['squad_ids']) != set(squad) or any(expected[k] != sub[k] for k in keys)
        if diverges and not sub.get('interventions'):
            raise ValueError('decision differs from shared policy; record the human intervention')
        arms[arm] = dict(sub, portfolio=_portfolio(protocol, squad, elements, old))
    if len(policies) != 1:
        raise ValueError('different decision policies confound the model comparison')
    return dict(schema_version=1, experiment_id=protocol['experiment_id'],
                protocol=protocol, protocol_sha256=evidence.digest(protocol),
                gameweek=gw, captured_at=now.isoformat(), deadline=lock.isoformat(),
                previous_artifact_id=previous['artifact_id'] if previous else None,
                bootstrap=bootstrap, fixtures=fixtures, population_ids=sorted(population), arms=arms)


def write_week(root, record, now=None):
    now = evidence.utc(now or datetime.now(timezone.utc))
    if not evidence.utc(record['captured_at']) <= now < evidence.utc(record['deadline']):
        raise ValueError('capture is in the future or deadline passed before writing')
    root = Path(root)
    path = root / f"gw{record['gameweek']}.json"
    if path.exists():
        raise ValueError('weekly experiment record already frozen')
    body = {k: v for k, v in record.items() if k != 'artifact_id'}
    key = evidence.digest(body)
    if record.get('artifact_id', key) != key:
        raise ValueError('experiment record checksum mismatch')
    body['artifact_id'] = key
    root.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=root, delete=False) as fh:
            tmp = Path(fh.name)
            json.dump(body, fh, ensure_ascii=False, indent=2, allow_nan=False)
            fh.write('\n')
        # Atomic, exclusive publication. A crash cannot leave a half-written claim.
        os.link(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return body


def read_week(path):
    record = json.loads(Path(path).read_text())
    body = {k:v for k,v in record.items() if k != 'artifact_id'}
    if evidence.digest(body) != record['artifact_id']:
        raise ValueError('experiment record checksum mismatch')
    if evidence.utc(record['captured_at']) >= evidence.utc(record['deadline']):
        raise ValueError('ineligible late experiment record')
    return record


def grade_week(record, results):
    evidence.require_final(results)
    if evidence.utc(results['fetched_at']) < evidence.utc(record['deadline']):
        raise ValueError('results fetched before the forecast deadline')
    if results.get('gameweek') != record['gameweek']:
        raise ValueError('wrong gameweek results')
    if {f['id'] for f in results['fixtures']} != {f['id'] for f in record['fixtures']}:
        raise ValueError('fixture coverage changed; review the evidence before grading')
    if any(f.get('event') != record['gameweek'] for f in results['fixtures']):
        raise ValueError('wrong fixture gameweek')
    stats = {e['id']: e.get('stats', {}) for e in results['live']['elements']}
    if any(not {'total_points', 'minutes'} <= set(stats.get(pid, {})) for pid in record['population_ids']):
        raise ValueError('missing outcomes: do not change the evaluation population')
    boot = record['bootstrap']
    by_id = {e['id']: e for e in boot['elements']}
    arms = {}
    for arm, sub in record['arms'].items():
        predictions = _predictions(sub['predictions'])
        errors = [predictions[pid]-stats[pid]['total_points'] for pid in record['population_ids']]
        squad = []
        # Ordered bench must survive autosub grading; unique ID-based internal names
        # also avoid a renamed player or duplicate surname changing the join.
        for pid in sub['xi_ids'] + sub['bench_ids']:
            squad.append(dict(name=str(pid), player_id=pid,
                position=POSITIONS[by_id[pid]['element_type']],
                is_starter=pid in sub['xi_ids'], is_captain=pid == sub['captain_id'],
                is_vice=pid == sub['vice_id'],
                bench_order=(sub['bench_ids'].index(pid)+1 if pid in sub['bench_ids'] else None)))
        official = fpl_live.grade_squad({'squad': squad}, results['live'], results['fixtures'], boot)
        if official['players_pending']:
            raise ValueError('pending squad outcomes')
        hit = sub['portfolio']['hit_points']
        arms[arm] = dict(n=len(errors), mae=sum(abs(e) for e in errors)/len(errors),
                        mse=sum(e*e for e in errors)/len(errors),
                        rmse=math.sqrt(sum(e*e for e in errors)/len(errors)), bias=sum(errors)/len(errors),
                        official_points=official['total_so_far'], hit_points=hit,
                        net_points=official['total_so_far']-hit,
                        captain_effective=official['captain_effective'],
                        captain_points=(stats[int(official['captain_effective'])]['total_points']
                                        if official['captain_effective'] else 0),
                        autosubs=official['autosubs_applied'], model_version=sub['model_version'],
                        intervention_count=len(sub.get('interventions', [])))
    return dict(gameweek=record['gameweek'], experiment_id=record['experiment_id'],
                forecast_artifact_id=record['artifact_id'], results_sha256=evidence.digest(results), arms=arms)


def season_report(grades):
    """Equal-GW averages for forecast loss; no ranking from incomparable weeks."""
    if not grades:
        return {'status': 'registered_not_started', 'gameweeks': [], 'arms': {}}
    if len({g['experiment_id'] for g in grades}) != 1 or len({g['gameweek'] for g in grades}) != len(grades):
        raise ValueError('mixed experiments or duplicate gameweeks')
    keys = set(grades[0]['arms'])
    if any(set(g['arms']) != keys for g in grades):
        raise ValueError('unequal arm participation')
    out = {}
    for arm in sorted(keys):
        rows = [g['arms'][arm] for g in grades]
        out[arm] = dict(net_points=sum(r['net_points'] for r in rows),
            rmse_equal_gameweek=math.sqrt(sum(r['mse'] for r in rows)/len(rows)),
            mae_equal_gameweek=sum(r['mae'] for r in rows)/len(rows),
            model_versions=sorted({r['model_version'] for r in rows}),
            interventions=sum(r['intervention_count'] for r in rows))
    return dict(status='prospective_results', gameweeks=sorted(g['gameweek'] for g in grades),
                arms=out, note='Separate forecast and squad scores. No automatic promotion or claim of superiority.')


def choose_decision(squad_ids, prediction_rows, bootstrap, portfolio=None):
    """Shared v1 policy: at most one positive-net single swap, then XI/captain.

    One-week means only, no chips or autosub option value. This is a controlled
    baseline policy, not an assertion that this is the optimal season strategy.
    """
    from games.fpl import transfers
    elements = {e['id']: e for e in bootstrap['elements']}
    pred = _predictions(prediction_rows)
    rows = {str(pid): dict(name=str(pid), team=str(e['team']),
                          position=POSITIONS[e['element_type']], price=e['now_cost']/10,
                          x_points=pred[pid]) for pid, e in elements.items() if pid in pred}
    squad_ids = list(squad_ids)
    if portfolio:
        state = {'squad': []}
        for pid in squad_ids:
            entry = dict(rows[str(pid)])
            paid, current = portfolio['purchase_prices'][str(pid)], elements[pid]['now_cost']
            sale = paid + (current-paid)//2 if current > paid else current
            entry['price'] = sale/10
            state['squad'].append(entry)
        options = transfers.recommend(state, {1: rows}, portfolio['free_transfers_next'],
                                      portfolio['bank_tenths']/10, top=1)
        if options and options[0]['hit_adjusted_delta'] > 0:
            swap = options[0]
            squad_ids.remove(int(swap['out']))
            squad_ids.append(int(swap['in']))
    groups = {pos: sorted((pid for pid in squad_ids if POSITIONS[elements[pid]['element_type']] == pos),
                          key=lambda pid: (-pred[pid], pid)) for pos in QUOTA}
    choices = []
    for defenders in range(3, 6):
        for mids in range(2, 6):
            fwds = 10-defenders-mids
            if not 1 <= fwds <= 3:
                continue
            xi = groups['GK'][:1]+groups['DEF'][:defenders]+groups['MID'][:mids]+groups['FWD'][:fwds]
            if len(xi) == 11:
                choices.append((sum(pred[pid] for pid in xi)+max(pred[pid] for pid in xi), xi))
    if not choices:
        raise ValueError('no legal lineup')
    xi = max(choices, key=lambda pair: (pair[0], tuple(-pid for pid in pair[1])))[1]
    ranked = sorted(xi, key=lambda pid: (-pred[pid], pid))
    return dict(squad_ids=squad_ids, xi_ids=xi,
                bench_ids=sorted(set(squad_ids)-set(xi), key=lambda pid: (-pred[pid], pid)),
                captain_id=ranked[0], vice_id=ranked[1], decision_policy_id='single_swap_xi_mean_v1')


def load_history(root):
    paths = sorted(Path(root).glob('gw*.json'), key=lambda p: int(p.stem[2:]))
    records = [read_week(p) for p in paths]
    for i, record in enumerate(records):
        expected = records[i-1]['artifact_id'] if i else None
        if record['previous_artifact_id'] != expected:
            raise ValueError('broken history chain')
        if i and (record['gameweek'] != records[i-1]['gameweek']+1 or
                  record['protocol_sha256'] != records[i-1]['protocol_sha256']):
            raise ValueError('history gap or protocol change')
    return records


def report_from_directory(protocol, root):
    records = load_history(root)
    grades, pending = [], []
    for record in records:
        if record['protocol_sha256'] != evidence.digest(protocol):
            raise ValueError('registered protocol disagrees with frozen history')
        path = Path(root)/'grades'/f"gw{record['gameweek']}.json"
        if not path.exists():
            pending.append(record['gameweek']); continue
        grade = json.loads(path.read_text())
        if grade['forecast_artifact_id'] != record['artifact_id']:
            raise ValueError('grade belongs to a different forecast')
        grades.append(grade)
    report = season_report(grades)
    report.update(registered_arms=dict(protocol['arms']), pending_gameweeks=pending,
                  frozen_gameweeks=[r['gameweek'] for r in records],
                  experiment_id=protocol['experiment_id'], protocol_sha256=evidence.digest(protocol))
    if records and not grades:
        report['status'] = 'forecasts_frozen_awaiting_results'
    return report
