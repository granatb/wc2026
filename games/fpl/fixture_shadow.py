"""Receipt-backed fixture shadow. Separate from the four-arm squad experiment."""
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import tempfile

from core import fpl_api, fpl_priors, forecast_archive as evidence, fpl_fixture_history
from games.fpl import fixture_challenger as model, forecast_providers as providers
from scripts import evaluate_challenger as ridge

VERSION = 'fixture-shadow-v1'
POLICY = dict(cold_start='production_fallback_excluded_from_comparison',
              availability='same_official_factor_as_production',
              negative_points='clamp_per_fixture_to_zero', blank='zero',
              freeze='final_24h_fresh_draft_30min', promotion='none')


def code_hashes():
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in map(Path,
        (__file__, model.__file__, ridge.__file__, providers.__file__, fpl_priors.__file__,
         fpl_api.__file__, fpl_fixture_history.__file__))}


def build(context, collection, research, trained, now=None):
    now = evidence.utc(now or datetime.now(timezone.utc))
    boot, gw = context['bootstrap'], context['gameweek']
    lock = evidence.deadline(boot, gw)
    if now >= lock:
        raise ValueError('shadow forecast deadline passed')
    for key in ('bootstrap', 'all_fixtures'):
        evidence.require_fresh(context[key], context['receipts'][key], now=now)
    if not 0 <= (now-evidence.utc(context['captured_at'])).total_seconds() <= 86400:
        raise ValueError('context stale or future-dated')
    if (collection['bootstrap_sha256'] != evidence.digest(boot) or collection['gameweek'] != gw or
        collection['season'] != evidence.deadline(boot, 1).isoformat()):
        raise ValueError('history collection context mismatch')
    if not 0 <= (now-evidence.utc(collection['captured_at'])).total_seconds() <= 86400:
        raise ValueError('collection stale or future-dated')
    expected = {p['id'] for p in boot['elements']}
    records = collection['players']
    if len(records) != len(expected) or {r['player_id'] for r in records} != expected:
        raise ValueError('complete unique history population required')
    providers.verify(trained)
    if (research['features'] != model.FEATURES or research['config'] != model.CONFIG or
        research['implementation_sha256'] != hashlib.sha256(Path(model.__file__).read_bytes()).hexdigest() or
        research['sources'][0]['sha256'] != trained['sources'][0]['sha256'] or
        evidence.utc(trained['trained_through']) >= evidence.deadline(boot, 1)):
        raise ValueError('research transform/training provenance mismatch')
    weights = research['weights']['fixture']
    if len(weights) != len(model.FEATURES):
        raise ValueError('research coefficient dimension mismatch')
    weights = [providers.number(w) for w in weights]
    fixtures = context['all_fixtures']
    fixture_map = {f['id']:f for f in fixtures}
    if len(fixture_map) != len(fixtures):
        raise ValueError('duplicate fixture IDs')
    target = [f for f in fixtures if f.get('event') == gw]
    if target != context['fixtures'] or not target or any(f.get('started') for f in target):
        raise ValueError('complete unstarted target fixtures required')
    if any(not f.get('kickoff_time') or evidence.utc(f['kickoff_time']) <= lock for f in target):
        raise ValueError('target kickoff unavailable or before deadline')
    # The same lower-GW and three-hour completion rule as research; actual capture
    # replaces the retrospective cutoff proxy. Never learn from the target GW.
    index = {}
    for f in fixtures:
        if f.get('event') is not None and f['event'] < gw and f.get('kickoff_time'):
            if not f.get('finished'):
                raise ValueError('prior fixture not final')
            index[f['id']] = dict(signature=(f['event'], evidence.utc(f['kickoff_time']),
                providers.number(f['team_h_score']), providers.number(f['team_a_score'])),
                teams={True:f['team_h'], False:f['team_a']})
    rate = model.strengths(index, gw, now)
    history = providers.live_histories(boot, gw, context['history'], now)
    production, _ = providers.statistical_predictions(boot, target, history, trained)
    parsed = {p['id']:p for p in fpl_api.parse_players(boot)}
    by_id = {r['player_id']:r for r in records}
    predictions, cold_ids, eligible_ids, blank_ids = [], [], [], []
    for player in sorted(boot['elements'], key=lambda p:p['id']):
        pid = player['id']
        record = by_id[pid]
        fpl_fixture_history.validate(record, pid, collection['season'], now)
        receipt_time = evidence.utc(record['receipt']['recorded_at'])
        if receipt_time > evidence.utc(collection['captured_at']):
            raise ValueError('history receipt after collection')
        past, seen = [], set()
        per_gw = defaultdict(lambda: defaultdict(float))
        for r in record['payload']['history']:
            fid = r['fixture']
            if fid in seen or fid not in fixture_map:
                raise ValueError('duplicate or unknown historical fixture')
            seen.add(fid)
            f = fixture_map[fid]
            if (r['round'] != f['event'] or r['round'] >= gw or not f.get('finished') or
                evidence.utc(r['kickoff_time']) != evidence.utc(f['kickoff_time']) or
                evidence.utc(r['kickoff_time'])+timedelta(hours=3) >= min(now, receipt_time)):
                raise ValueError('history date, gameweek or finality mismatch')
            if not isinstance(r['was_home'], bool):
                raise ValueError('invalid history home flag')
            if (r['opponent_team'] != f['team_a' if r['was_home'] else 'team_h'] or
                any(providers.number(r[k]) != providers.number(f[k]) for k in ('team_h_score','team_a_score'))):
                raise ValueError('history fixture identity or score mismatch')
            values = {k:providers.number(r[k]) for k in providers.FIELDS}
            if not 0 <= values['minutes'] <= 90:
                raise ValueError('invalid fixture minutes')
            for k,v in values.items():
                per_gw[r['round']][k] += v
            past.append(dict(values, kickoff=evidence.utc(r['kickoff_time']), fixture=fid))
        # Reconcile each GW, not merely season totals. Missing zero rows are not
        # invented: history endpoints are retained verbatim and this remains a limit.
        for week in set(per_gw) | set(history.get(pid, {})):
            for key in providers.FIELDS:
                if abs(per_gw[week][key]-history.get(pid, {}).get(week, {}).get(key, 0)) > .011:
                    raise ValueError(f'fixture/GW history mismatch: player {pid}, GW{week}, {key}')
        past.sort(key=lambda r:(r['kickoff'], r['fixture']))
        scheduled = [f for f in target if player['team'] in (f['team_h'], f['team_a'])]
        factor = fpl_priors.availability_factor(parsed[pid])
        legs = []
        if not scheduled:
            blank_ids.append(pid)
            predicted, reason = 0.0, 'blank'
        elif not past:
            cold_ids.append(pid)
            predicted, reason = production[pid], 'cold_start_production_fallback'
        else:
            eligible_ids.append(pid)
            for f in scheduled:
                home = player['team'] == f['team_h']
                opponent = f['team_a'] if home else f['team_h']
                x = model.vector(past, fpl_api.POSITIONS[player['element_type']], home,
                                 rate(player['team']), rate(opponent))
                raw = model.predict_week(weights, [x])
                legs.append(dict(fixture_id=f['id'], features=x, raw_points=raw,
                                 x_points=max(0, raw)*factor))
            predicted, reason = sum(r['x_points'] for r in legs), 'fixture_model'
        predictions.append(dict(player_id=pid, fixture_points=predicted, production_points=production[pid],
            method=reason, availability_factor=factor, legs=legs))
    identity = evidence.digest(dict(version=VERSION, policy=POLICY, weights=weights,
        research_sha256=evidence.digest(research), production_model_id=trained['artifact_id'], code=code_hashes()))
    source = dict(context=context, collection=collection, research=research, trained=trained,
                  code=code_hashes())
    return providers.seal(dict(schema_version=1, state='shadow_rehearsal_not_frozen', gameweek=gw,
        generated_at=now.isoformat(), deadline=lock.isoformat(), version=VERSION,
        model_identity_sha256=identity, policy=POLICY, predictions=predictions,
        comparison_ids=eligible_ids, cold_start_ids=cold_ids, blank_ids=blank_ids, source=source,
        limitations=['No prospective result yet; this is separate from the four-arm squad experiment.',
            'Cold starts copy production and are excluded from the fixture comparison; blanks are reported separately.',
            'Official availability scaling and per-fixture clamping were not part of historical evaluation.',
            'Missing zero-history rows cannot be inferred from season totals; API coverage remains a limitation.',
            'Local receipts and hashes are not independent proof of pre-deadline publication.']))


def summary(record):
    providers.verify(record)
    eligible = set(record['comparison_ids'])
    delta = [r['fixture_points']-r['production_points'] for r in record['predictions'] if r['player_id'] in eligible]
    return dict(state=record['state'], gameweek=record['gameweek'], generated_at=record['generated_at'],
        frozen_at=record.get('frozen_at'),
        deadline=record['deadline'], artifact_id=record['artifact_id'], model_identity_sha256=record['model_identity_sha256'],
        players=len(record['predictions']), comparison_players=len(eligible), cold_starts=len(record['cold_start_ids']),
        blanks=len(record['blank_ids']), mean_prediction_difference=sum(delta)/len(delta) if delta else None,
        mean_absolute_prediction_difference=sum(map(abs,delta))/len(delta) if delta else None,
        limitations=record['limitations'])


def retain(root, record):
    providers.verify(record)
    path = Path(root)/f"{record['artifact_id']}.json"
    evidence.atomic_json(path, record)
    return dict(summary(record), evidence_path=str(path))


def freeze(record, root, now=None):
    """One immutable snapshot per GW; rebuilt from retained inputs before enrollment."""
    providers.verify(record)
    path = Path(root)/f"gw{record['gameweek']}.json"
    if path.exists():
        old = json.loads(path.read_text())
        providers.verify(old)
        if old.get('draft_artifact_id') == record['artifact_id']:
            return summary(old)
        raise ValueError('a different shadow snapshot is already frozen')
    now = evidence.utc(now or datetime.now(timezone.utc))
    lock = evidence.utc(record['deadline'])
    if not lock-timedelta(hours=24) <= now < lock:
        raise ValueError('shadow freeze only in final 24 hours')
    if not 0 <= (now-evidence.utc(record['generated_at'])).total_seconds() <= 1800:
        raise ValueError('shadow rehearsal expired; rebuild with fresh sources')
    source = record['source']
    replay = build(source['context'], source['collection'], source['research'], source['trained'],
                   now=record['generated_at'])
    if replay != record:
        raise ValueError('shadow does not replay from retained evidence')
    # Recheck input freshness at enrollment, not only at rehearsal creation.
    build(source['context'], source['collection'], source['research'], source['trained'], now=now)
    frozen = providers.seal(dict({k:v for k,v in record.items() if k != 'artifact_id'},
        state='shadow_frozen', frozen_at=now.isoformat(), draft_artifact_id=record['artifact_id']))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as fh:
            temp = Path(fh.name)
            json.dump(frozen, fh, allow_nan=False)
        os.link(temp, path)  # Atomic create-only: concurrent enrollment cannot overwrite.
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    return summary(frozen)


def grade(record, results, now=None):
    providers.verify(record)
    now = evidence.utc(now or datetime.now(timezone.utc))
    lock = evidence.utc(record['deadline'])
    if (record['state'] != 'shadow_frozen' or
        not lock-timedelta(hours=24) <= evidence.utc(record['frozen_at']) < lock or
        not 0 <= (evidence.utc(record['frozen_at'])-evidence.utc(record['generated_at'])).total_seconds() <= 1800):
        raise ValueError('only a valid pre-deadline frozen shadow can be graded')
    evidence.require_final(results)
    if (results['gameweek'] != record['gameweek'] or
        not lock < evidence.utc(results['fetched_at']) <= now):
        raise ValueError('results gameweek or receipt mismatch')
    fixtures = results['fixtures']
    expected = {f['id']:f for f in record['source']['context']['fixtures']}
    if len(fixtures) != len(expected) or {f['id'] for f in fixtures} != set(expected):
        raise ValueError('final fixture population mismatch')
    if any(f.get('event') != record['gameweek'] or any(f[k] != expected[f['id']][k]
            for k in ('team_h', 'team_a')) for f in fixtures):
        raise ValueError('final fixture identity mismatch')
    stats = {r['id']:r['stats'] for r in results['live']['elements']}
    if len(stats) != len(results['live']['elements']):
        raise ValueError('duplicate final player')
    predictions = {r['player_id']:r for r in record['predictions']}
    population = {p['id'] for p in record['source']['context']['bootstrap']['elements']}
    if (len(predictions) != len(record['predictions']) or set(predictions) != population or
        not set(predictions) <= set(stats)):
        raise ValueError('missing final players or duplicate forecast')
    for field, method in [('comparison_ids', 'fixture_model'),
                          ('cold_start_ids', 'cold_start_production_fallback'), ('blank_ids', 'blank')]:
        if sorted(record[field]) != sorted(pid for pid,r in predictions.items() if r['method'] == method):
            raise ValueError('frozen cohort differs from forecast methods')
    for pid in predictions:
        for key in ('total_points', 'minutes'):
            value = providers.number(stats[pid][key])
            if value != int(value) or (key == 'minutes' and value < 0):
                raise ValueError('invalid final player stats')
    cohorts = {}
    for name, ids in [('fixture_eligible', record['comparison_ids']),
                      ('cold_start_fallback', record['cold_start_ids']), ('blank', record['blank_ids'])]:
        if len(ids) != len(set(ids)) or not set(ids) <= set(predictions):
            raise ValueError('invalid frozen cohort')
        rows = [dict(y=providers.number(stats[pid]['total_points'])) for pid in ids]
        cohorts[name] = {arm:ridge.metrics(rows, [providers.number(predictions[pid][arm+'_points']) for pid in ids])
                         for arm in ('fixture', 'production')} if ids else {}
    return providers.seal(dict(state='shadow_graded', gameweek=record['gameweek'],
        forecast_artifact_id=record['artifact_id'], model_identity_sha256=record['model_identity_sha256'],
        results=results, cohorts=cohorts,
        note='One frozen snapshot, not evidence of a season edge or an automatic promotion.'))
