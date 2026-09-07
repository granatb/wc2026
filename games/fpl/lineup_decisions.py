"""Finite-scenario lineup optimization; no implicit independence or transfer policy."""
from collections import Counter, defaultdict
from itertools import combinations, permutations, product
import math

QUOTA = {'GK':2, 'DEF':5, 'MID':5, 'FWD':3}
MIN = {'GK':1, 'DEF':3, 'MID':2, 'FWD':1}
MAX = {'GK':1, 'DEF':5, 'MID':5, 'FWD':3}
VERSION = 'joint-scenario-lineup-v1'


def validate(positions, scenarios):
    if len(positions) != 15 or Counter(positions.values()) != QUOTA:
        raise ValueError('a complete 2/5/5/3 squad is required')
    if any(type(pid) is not int or pid <= 0 for pid in positions):
        raise ValueError('positive integer player IDs required')
    if not scenarios or len(scenarios) > 20000:
        raise ValueError('one to 20000 weighted scenarios required')
    for scenario in scenarios:
        weight = scenario['weight']
        if isinstance(weight, bool) or not isinstance(weight, (int,float)) or not math.isfinite(weight) or weight <= 0:
            raise ValueError('positive finite scenario weight required')
        if set(scenario['players']) != set(positions):
            raise ValueError('scenario population differs from squad')
        for row in scenario['players'].values():
            value = row['points']
            if (type(row['played']) is not bool or isinstance(value,bool) or
                not isinstance(value,(float,int)) or not math.isfinite(value) or
                (not row['played'] and value != 0)):
                raise ValueError('finite points and explicit appearance required; DNP must have zero points')
    if not math.isclose(sum(s['weight'] for s in scenarios), 1, abs_tol=1e-9):
        raise ValueError('scenario weights must sum to one')


def legal(xi, positions):
    counts = Counter(positions[pid] for pid in xi)
    return len(xi) == 11 and len(set(xi)) == 11 and all(MIN[p] <= counts[p] <= MAX[p] for p in QUOTA)


def validate_decision(decision, positions):
    xi, bench = decision['xi_ids'], decision['bench_ids']
    if (not set(xi+bench) <= set(positions) or not legal(xi, positions) or len(bench) != 4 or
        len(set(xi+bench)) != 15 or set(xi+bench) != set(positions)):
        raise ValueError('legal XI and complete ordered bench required')
    if decision['captain_id'] == decision['vice_id'] or any(decision[k] not in xi for k in ('captain_id','vice_id')):
        raise ValueError('distinct captain and vice must start')


def substitutes(xi, bench, positions, played):
    """Same bench-priority/formation semantics as the finalized official grader."""
    counts = Counter(positions[pid] for pid in xi)
    missing = [pid for pid in xi if pid not in played]
    replacements = {}
    for incoming in bench:
        if incoming not in played:
            continue
        pos = positions[incoming]
        for outgoing in missing:
            old = positions[outgoing]
            if outgoing in replacements or (pos == 'GK') != (old == 'GK'):
                continue
            if old != pos and (counts[old] <= MIN[old] or counts[pos] >= MAX[pos]):
                continue
            counts[old] -= 1
            counts[pos] += 1
            replacements[outgoing] = incoming
            break
    return replacements


def evaluate(positions, scenarios, decision):
    validate(positions, scenarios)
    validate_decision(decision, positions)
    xi, bench = decision['xi_ids'], decision['bench_ids']
    cap, vice = decision['captain_id'], decision['vice_id']
    totals = dict(starter_points=0.0, autosub_points=0.0, captain_bonus=0.0, vice_bonus=0.0)
    for scenario in scenarios:
        rows, weight = scenario['players'], scenario['weight']
        played = {pid for pid,r in rows.items() if r['played']}
        subs = substitutes(xi, bench, positions, played)
        totals['starter_points'] += weight*sum(rows[pid]['points'] for pid in xi)
        totals['autosub_points'] += weight*sum(rows[pid]['points'] for pid in subs.values())
        if cap in played:
            totals['captain_bonus'] += weight*rows[cap]['points']
        elif vice in played:
            totals['vice_bonus'] += weight*rows[vice]['points']
    return dict(totals, total=sum(totals.values()))


def optimize(positions, scenarios):
    """Enumerate every legal XI, outfield bench order and captain/vice pair.

    Exact for the supplied finite scenarios. Captains are scored independently
    of bench order; group identical appearance masks without losing their
    probability-weighted point totals. No population/scenario subsampling here.
    """
    validate(positions, scenarios)
    ids = sorted(positions)
    means = {pid:sum(s['weight']*s['players'][pid]['points'] for s in scenarios) for pid in ids}
    bonus = {(cap,vice):means[cap]+sum(s['weight']*s['players'][vice]['points'] for s in scenarios
                  if not s['players'][cap]['played']) for cap in ids for vice in ids if cap != vice}
    masks = defaultdict(lambda: defaultdict(float))
    for s in scenarios:
        played = frozenset(pid for pid,r in s['players'].items() if r['played'])
        for pid,r in s['players'].items():
            masks[played][pid] += s['weight']*r['points']
    groups = {pos:sorted(pid for pid in ids if positions[pid] == pos) for pos in QUOTA}
    best, best_score, candidates = None, -math.inf, 0
    for defenders in range(3,6):
        for mids in range(2,6):
            fwds = 10-defenders-mids
            if not 1 <= fwds <= 3:
                continue
            for pieces in product(combinations(groups['GK'],1), combinations(groups['DEF'],defenders),
                                  combinations(groups['MID'],mids), combinations(groups['FWD'],fwds)):
                xi = [pid for group in pieces for pid in group]
                base = sum(means[pid] for pid in xi)
                cap,vice = min(((c,v) for c in xi for v in xi if c != v),
                               key=lambda pair:(-bonus[pair], pair))
                unused = set(ids)-set(xi)
                keeper = next(pid for pid in unused if positions[pid]=='GK')
                for order in permutations(sorted(unused-{keeper})):
                    bench = [keeper]+list(order)
                    score = base+bonus[cap,vice]
                    for played, weighted in masks.items():
                        score += sum(weighted[pid] for pid in substitutes(xi,bench,positions,played).values())
                    candidates += 1
                    key = (tuple(xi),tuple(bench),cap,vice)
                    if score > best_score+1e-10 or (abs(score-best_score) <= 1e-10 and key < best[0]):
                        best_score = score
                        best = (key, dict(xi_ids=xi,bench_ids=bench,captain_id=cap,vice_id=vice,
                                          decision_policy_id=VERSION))
    decision = best[1]
    return dict(decision=decision, expected=evaluate(positions,scenarios,decision),
                lineups_and_bench_orders=candidates, appearance_patterns=len(masks),
                note='Optimal for these finite scenarios; not proof of calibrated real-world value.')
