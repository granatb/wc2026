"""Prospective experimental providers. Pure adapters; no implicit HTTP or FC ratings."""
import hashlib
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from core import forecast_archive as evidence, fpl_api, fpl_bench, fpl_priors
from scripts import evaluate_challenger as ridge

VERSION = 'providers-v1'
REPO = Path(__file__).resolve().parents[2]
FIELDS = ('total_points', 'minutes', 'expected_goals', 'expected_assists')


def number(value):
    if value is None or isinstance(value, bool):
        raise ValueError('missing numeric provider input')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('nonfinite provider input')
    return result


def seal(payload):
    return dict(payload, artifact_id=evidence.digest(payload))


def verify(payload):
    if payload.get('artifact_id') != evidence.digest({k:v for k,v in payload.items() if k != 'artifact_id'}):
        raise ValueError('provider artifact checksum mismatch')


def train_statistical(train_path, test_path):
    """Fixed ridge penalty; later season is evaluation only. No blend fitting."""
    train_end = ridge.season_window(train_path)[1]
    test_start = ridge.season_window(test_path)[0]
    if train_end >= test_start:
        raise ValueError('training must end before held-out season')
    train = ridge.examples(train_path, min_prior=1)
    test = ridge.examples(test_path, min_prior=1)
    weights = ridge.fit(train, ridge=100)
    predictions = [max(0, sum(a*b for a,b in zip(weights, row['x']))) for row in test]
    # A transparent positional fallback, fitted on the training population only.
    cold = {}
    for pos, slot in [('GK', 6), ('DEF', 7), ('MID', 8), ('FWD', None)]:
        rows = [r for r in train if (r['x'][slot] if slot else not any(r['x'][6:]))]
        if not rows:
            raise ValueError('training lacks a position')
        cold[pos] = sum(r['y'] for r in rows)/len(rows)
    return seal(dict(model_version='odds-free-early-ridge-v1', features=ridge.FEATURES,
        weights=weights, cold_start_points=cold, ridge_penalty=100,
        trained_through=train_end.isoformat(), train_n=len(train),
        feature_source_sha256=hashlib.sha256(Path(ridge.__file__).read_bytes()).hexdigest(),
        sources=[dict(path=Path(p).name, sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest())
                 for p in (train_path, test_path)],
        heldout=dict(start=test_start.isoformat(), scores=ridge.metrics(test, predictions),
                     last4=ridge.metrics(test, [r['x'][1] for r in test])),
        limitations=['Retrospective extracts, not timestamped historical forecasts.',
            'At least one prior recorded GW; differs from the six-week research model.',
            'Cold starts use a training positional mean, not a fitted minutes forecast.',
            'No opponent strength; future doubles scaled by match count, blanks zeroed.',
            'Availability gates are prospective rules, not included in heldout scores.',
            'Historical scoring differs; no demonstrated edge over the market model.']))


def live_histories(bootstrap, gameweek, results, now):
    """Require every completed prior GW, finalized before this capture."""
    expected = set(range(1, gameweek))
    if len(results) != len(expected) or {r['gameweek'] for r in results} != expected:
        raise ValueError('complete prior-gameweek history required')
    events = {e['id']: e for e in bootstrap['events']}
    history = {}
    for record in results:
        gw = record['gameweek']
        if not events[gw].get('finished'):
            raise ValueError('prior gameweek not final')
        evidence.require_final(record)
        if not evidence.deadline(bootstrap, gw) < evidence.utc(record['fetched_at']) <= evidence.utc(now):
            raise ValueError('future or premature history receipt')
        if any(f.get('event') != gw for f in record['fixtures']):
            raise ValueError('history fixture gameweek mismatch')
        seen = set()
        for row in record['live']['elements']:
            pid = row['id']
            if pid in seen:
                raise ValueError('duplicate historical player ID')
            seen.add(pid)
            history.setdefault(pid, {})[gw] = {k:number(row['stats'].get(k)) for k in FIELDS}
    # New registrations may have no early records; an established player must
    # reconcile to the current official totals, preventing partial-history bias.
    for player in bootstrap['elements']:
        past = history.get(player['id'], {})
        if past and set(past) != set(range(min(past), gameweek)):
            raise ValueError('player history has a gap after registration')
        for key in ('minutes', 'total_points'):
            if sum(r[key] for r in past.values()) != number(player.get(key)):
                raise ValueError(f"history does not reconcile for player {player['id']} / {key}")
    return history


def statistical_predictions(bootstrap, fixtures, history, trained):
    verify(trained)
    if trained['features'] != ridge.FEATURES or trained['feature_source_sha256'] != hashlib.sha256(Path(ridge.__file__).read_bytes()).hexdigest():
        raise ValueError('statistical feature implementation changed; retrain/version model')
    counts = Counter(t for f in fixtures for t in (f['team_h'], f['team_a']))
    parsed = {p['id']:p for p in fpl_api.parse_players(bootstrap)}
    predictions, cold_ids = {}, []
    for player in bootstrap['elements']:
        pid = player['id']; pos = fpl_api.POSITIONS[player['element_type']]
        past = history.get(pid, {})
        if past:
            prior = [past.get(gw, {}) for gw in range(min(past), max(past)+1)]
            x = ridge.feature_vector(prior, pos)
            points = max(0, sum(a*b for a,b in zip(trained['weights'], x)))
        else:
            points = trained['cold_start_points'][pos]
            cold_ids.append(pid)
        predictions[pid] = points * counts[player['team']] * fpl_priors.availability_factor(parsed[pid])
    return predictions, cold_ids


def consensus_predictions(bootstrap, fixtures, payload, gameweek, now):
    """Fixed mean of FPL ep_next + FFIQ; uncovered players retain FPL alone."""
    age = (evidence.utc(now)-evidence.utc(payload['generated_at'])).total_seconds()
    if not 0 <= age <= 86400:
        raise ValueError('FFIQ forecast stale or future-dated')
    nxt = [e['id'] for e in bootstrap['events'] if e.get('is_next')]
    if nxt != [gameweek]:
        raise ValueError('ep_next does not identify the target gameweek')
    elements = {e['id']: e for e in bootstrap['elements']}
    teams = fpl_api.parse_teams(bootstrap)
    by_key = {}
    for p in elements.values():
        by_key.setdefault((p['web_name'], teams[p['team']]), []).append(p['id'])
    external = {}
    for row in payload.get('players', []):
        match = [g for g in row.get('gws', []) if g.get('gw') == gameweek]
        if not match:
            continue
        if len(match) != 1:
            raise ValueError('duplicate external gameweek forecast')
        pid = row.get('fpl_id')
        if pid is not None:
            if pid not in elements:
                continue  # departed / not yet registered: never attach to another ID
            if row['club'] != teams[elements[pid]['team']]:
                raise ValueError('FFIQ ID/club mismatch')
        else:
            ids = by_key.get((row['web_name'], row['club']), [])
            if len(ids) != 1:
                continue
            pid = ids[0]
        if pid in external:
            raise ValueError('duplicate external player forecast')
        external[pid] = number(match[0]['proj'])
    if not external:
        raise ValueError('no FFIQ coverage for target gameweek')
    teams_playing = {t for f in fixtures for t in (f['team_h'], f['team_a'])}
    predictions = {}
    for pid, p in elements.items():
        official = number(p.get('ep_next'))
        predictions[pid] = ((official+external[pid])/2 if pid in external else official) if p['team'] in teams_playing else 0
    return predictions, dict(ffiq_matched=len(external), fpl_only_ids=sorted(set(elements)-set(external)),
        attribution=fpl_bench.FFIQ_ATTRIBUTION, source=fpl_bench.FFIQ_URL,
        license=payload.get('license'), generated_at=payload['generated_at'])


def market_predictions(bootstrap, fixtures, odds, backfill, sims):
    """Reuse the corrected engine with explicit fixtures and no editorial overlay."""
    from core import fixtures as schedule
    from games.fpl import model
    gw = fixtures[0]['event']
    teams = fpl_api.parse_teams(bootstrap)
    rows = fpl_api.parse_players(bootstrap)
    for p in rows:
        p['season_started'] = any(e.get('finished') for e in bootstrap['events'])
    priors, flags = fpl_priors.build_with_flags(rows,
        sum(bool(e.get('finished')) for e in bootstrap['events']),
        defcon_backfill={int(k):v for k,v in backfill.items()})
    matches = []
    for f in fixtures:
        price = odds.get('matches', {}).get(str(f['id']))
        if not price or not price.get('h2h') or str(price.get('source', '')).startswith(('fdr', 'strength')):
            raise ValueError('experimental market arm requires real odds for every fixture')
        if price['home'] != teams[f['team_h']] or price['away'] != teams[f['team_a']]:
            raise ValueError('odds fixture clubs mismatch')
        home, away = number(price.get('lam_home')), number(price.get('lam_away'))
        if home <= 0 or away <= 0:
            raise ValueError('positive market lambdas required')
        matches.append(schedule.Fixture(match_id=str(f['id']), home=price['home'], away=price['away'],
            kickoff=evidence.utc(f['kickoff_time']), stage='GW', fantasy_round=gw,
            neutral=False, lam_home=home, lam_away=away, rho=number(price.get('rho', 0))))
    original = schedule.SCHEDULE
    try:
        schedule.SCHEDULE = matches
        artifact, _ = model.build_artifact(priors, {p['name']:p for p in rows}, gw, sims,
                                          use_cache=False, research_entries={})
    finally:
        schedule.SCHEDULE = original
    by_name = {p['name']:p for p in rows}
    predictions = {by_name[r['name']]['id']:r['x_points'] for r in artifact['rows']}
    playing = {t for f in fixtures for t in (f['team_h'], f['team_a'])}
    for p in bootstrap['elements']:
        if p['id'] not in predictions:
            if p['team'] in playing:
                raise ValueError(f"market engine omitted player {p['id']}")
            predictions[p['id']] = 0
    return predictions, dict(sims=sims, seed=model._SEED, cold_start_flags=flags,
                            research_overlay='disabled for controlled experiment')


def build_boards(context, trained, sims=5000, now=None, market_fn=market_predictions):
    now = evidence.utc(now or datetime.now(timezone.utc))
    boot, fixtures, gw = context['bootstrap'], context['fixtures'], context['gameweek']
    for key in ('bootstrap', 'all_fixtures'):
        evidence.require_fresh(context[key], context['receipts'][key], now=now)
    if fixtures != [f for f in context['all_fixtures'] if f.get('event') == gw]:
        raise ValueError('incomplete target fixture context')
    if now >= evidence.deadline(boot, gw):
        raise ValueError('deadline passed')
    if not fixtures or any(f['event'] != gw or f.get('started') for f in fixtures):
        raise ValueError('complete unstarted target fixtures required')
    if not 0 <= (now-evidence.utc(context['captured_at'])).total_seconds() <= 86400:
        raise ValueError('input context stale or future-dated')
    odds = context['odds']
    if odds['gameweek'] != gw or not 0 <= (now-evidence.utc(odds['captured_at'])).total_seconds() <= 86400:
        raise ValueError('market odds stale or wrong gameweek')
    verify(trained)
    if evidence.utc(trained['trained_through']) >= evidence.deadline(boot, 1):
        raise ValueError('statistical training must precede experimental season')
    history = live_histories(boot, gw, context['history'], now)
    stats, cold_ids = statistical_predictions(boot, fixtures, history, trained)
    consensus, coverage = consensus_predictions(boot, fixtures, context['ffiq'], gw, now)
    market, details = market_fn(boot, fixtures, odds, context['backfill'], sims)
    all_ids = {p['id'] for p in boot['elements']}
    if any(set(column) != all_ids for column in (market, stats, consensus)):
        raise ValueError('provider population mismatch')
    hybrid = {pid:(market[pid]+stats[pid])/2 for pid in all_ids}
    versions = dict(market='market-no-editorial-v1', statistical=trained['model_version'],
                    hybrid='fixed-equal-market-statistical-v1', consensus='fpl-ffiq-reference-v1')
    columns = dict(market=market, statistical=stats, hybrid=hybrid, consensus=consensus)
    serialized = {arm:[dict(player_id=pid, x_points=number(column[pid])) for pid in sorted(column)]
                  for arm,column in columns.items()}
    source = seal(dict(schema_version=1, provider_version=VERSION, context=context, trained=trained,
        generated_at=now.isoformat(), model_versions=versions, predictions=serialized,
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        engine_sources={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [REPO/'games/fpl/model.py', REPO/'core/engine_events.py', REPO/'core/fpl_priors.py',
                      REPO/'core/research.py', REPO/'core/blend.py', REPO/'core/odds_math.py', REPO/'config.py',
                      REPO/'games/fpl/experiments.py', REPO/'games/fpl/transfers.py']},
        preseason_rates=fpl_priors.preseason_rates(), market=details,
        statistical_cold_start_ids=cold_ids, consensus=coverage,
        hybrid_policy='fixed 50/50, prespecified without fitting; no claim of optimality'))
    boards = {}
    for arm, column in columns.items():
        boards[arm] = dict(model_version=versions[arm], provider_version=VERSION, generated_at=now.isoformat(),
            model_identity_sha256=model_identity(arm, source),
            model_identity_disclosed=arm != 'consensus',
            trained_through=(None if arm == 'consensus' else
                             now.isoformat() if arm == 'market' else trained['trained_through']),
            training_disclosed=arm != 'consensus', source_artifact_id=source['artifact_id'],
            training_note='Statistical cutoff is historical; market parameters are fixed at capture; external training is undisclosed.',
            bootstrap_sha256=evidence.digest(boot), fixtures_sha256=evidence.digest(fixtures),
            predictions=serialized[arm])
    return boards, source


def model_identity(arm, source):
    """Separate fixed algorithm/parameter changes from normal weekly input changes."""
    identity = dict(version=source['model_versions'][arm], implementation=source['implementation_sha256'])
    if arm in ('market', 'hybrid'):
        identity['engine'] = {k:v for k,v in source['engine_sources'].items()
                              if k not in ('games/fpl/experiments.py', 'games/fpl/transfers.py')}
        identity['preseason'] = evidence.digest(source['preseason_rates'])
    if arm in ('statistical', 'hybrid'):
        identity['trained'] = source['trained']['artifact_id']
    return evidence.digest(identity)


def verify_board_source(arm, board, source):
    verify(source)
    if board['source_artifact_id'] != source['artifact_id']:
        raise ValueError('board source identity mismatch')
    if (board.get('model_identity_sha256') != model_identity(arm, source) or
        board.get('model_identity_disclosed') != (arm != 'consensus')):
        raise ValueError('board model identity differs from source')
    if (board['predictions'] != source['predictions'][arm] or
        board['model_version'] != source['model_versions'][arm] or
        board['generated_at'] != source['generated_at']):
        raise ValueError('board forecasts, version or clock differ from source')
    if (board['bootstrap_sha256'] != evidence.digest(source['context']['bootstrap']) or
        board['fixtures_sha256'] != evidence.digest(source['context']['fixtures'])):
        raise ValueError('board context differs from source')
