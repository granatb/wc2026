#!/usr/bin/env python3
"""Fail deployment when a forecast export disagrees with its evidence."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import forecast_archive
from scripts.grade_gw import load_snapshots
from evmax import dataset as datasets


def validate_preview_week(out, gameweek):
    for path in (Path(out)/'api/fpl/preview').rglob('*.json'):
        if json.loads(path.read_text()).get('gameweek') != gameweek:
            raise ValueError(f'stale current-preview file: {path.name}')


def validate(out):
    out = Path(out)
    errors = []
    for required in ('index.html', '_headers', 'api/latest.json'):
        if not (out / required).is_file():
            errors.append(f'missing {required}')
    gameweeks = {int(p.name[2:]) for p in (out / 'api/fpl').glob('gw*')
                 if p.is_dir() and p.name[2:].isdigit()}
    gameweeks.update(int(p.stem[2:]) for p in (out / 'api/fpl/dataset').glob('gw*.json')
                     if p.stem[2:].isdigit())
    latest_file = out / 'api/latest.json'
    if latest_file.exists():
        latest = json.loads(latest_file.read_text())
        current = latest.get('gameweek')
        early = latest.get('publication_type') == 'early_preview'
        if current is not None and latest.get('publication_type') not in ('status_update', 'early_preview'):
            gameweeks.add(int(current))
        if early:
            try:
                from scripts.publish_fpl_preview import validate_preview_record
                expected_path = Path(__file__).resolve().parents[1]/f'evmax/assets/previews/gw{current}/2026-11-03.json'
                if latest['preview_evidence'] != str(expected_path.relative_to(Path(__file__).resolve().parents[1])):
                    raise ValueError('unexpected early-preview evidence path')
                evidence = json.loads(expected_path.read_text())
                public = json.loads((out/latest['articles']['preview'].lstrip('/')).read_text())
                validate_preview_record(public, evidence)
                if public['gameweek'] != current or public['generated_at'] != latest['generated_at']:
                    raise ValueError('early-preview identity or timestamp differs from latest')
                cards = json.loads((out/'api/fpl/preview/players.json').read_text())
                if cards['players'] != public['players'] or cards['preview'] != public['preview']:
                    raise ValueError('current player board differs from early-preview evidence')
                validate_preview_week(out, current)
                for player in public['players']:
                    card = json.loads((out/f'api/fpl/preview/players/{player["player_id"]}.json').read_text())
                    if (card['name'] != player['name'] or card['preview'] != public['preview'] or
                            any(card['projection'][key] != player[key] for key in ('x_points','captain_ev','ceiling'))):
                        raise ValueError('player card differs from early-preview evidence')
                    if not (out/player['page'].lstrip('/')/'index.html').is_file():
                        raise ValueError('player card page missing')
            except (KeyError, ValueError, OSError, TypeError) as exc:
                errors.append(f'invalid early preview: {exc}')
        if latest.get('publication_type') == 'status_update' or early:
            try:
                status = json.loads((out/'api/fpl/status.json').read_text())
                if (status['publication_type'] != 'status_update' or
                        (not early and (status['current']['gameweek'] != current or
                         status['captured_at'] != latest['generated_at']))):
                    raise ValueError('status feed identity or timestamp differs from latest')
                for key in ('current', 'previous'):
                    week = status[key]
                    final = (bool(week['fixtures']) and week['event']['finished'] is True
                             and week['event']['data_checked'] is True
                             and all(f['finished'] for f in week['fixtures']))
                    if (week['status'] == 'final') != final:
                        raise ValueError('status publication disagrees with official finality evidence')
                prior = latest['last_frozen_forecast']
                archived = forecast_archive.load(prior['gameweek'])
                if not archived or prior['forecast_artifact_id'] != archived['artifact_id']:
                    raise ValueError('last frozen forecast pointer differs from archive')
            except (KeyError, ValueError, OSError, TypeError) as exc:
                errors.append(f'invalid status publication: {exc}')
    for gw in sorted(gameweeks):
        path = out / 'api/fpl' / f'gw{gw}' / 'captains.json'
        archive = forecast_archive.load(gw)
        if gw >= 7:
            from games.fpl import publication_decision as decision
            receipt_path = out/'api/fpl'/f'gw{gw}'/'decision.json'
            receipt = archive.get('publication_decision') if archive else None
            try:
                if not receipt or not receipt_path.exists() or json.loads(receipt_path.read_text()) != receipt:
                    raise ValueError('accepted publication decision missing or differs from archive')
                decision.verify_forecast(receipt, archive)
                proposal = receipt['proposal']
                decision.require_accepted(receipt, proposal, now=archive['captured_at'])
                if proposal['gameweek'] != gw or proposal['states'] != archive['states']:
                    raise ValueError('accepted decision disagrees with archived squad')
                decision.verify_entries(proposal['states'], {key:archive['envelopes'][slug]['entries']
                    for key,slug in [('model','our-squad'),('consensus','consensus-squad')]})
            except (ValueError,KeyError,TypeError,OSError) as exc:
                errors.append(f'GW{gw}: invalid publication decision: {exc}')
        evidence = archive['envelopes'] if archive else load_snapshots(gw)
        for slug, expected in evidence.items():
            actual_path = path.parent / (slug + '.json')
            if not actual_path.exists():
                errors.append(f'GW{gw}: missing {slug}')
                continue
            actual = json.loads(actual_path.read_text())
            # ep_next is an extra field in the evidence copy, not the public API.
            public = lambda entries: [{k:v for k,v in e.items() if k != 'ep_next'} for e in entries]
            if public(actual.get('entries', [])) != public(expected.get('entries', [])):
                errors.append(f'GW{gw}: {slug} differs from frozen evidence')
            if actual.get('generated_at') != expected.get('generated_at'):
                errors.append(f'GW{gw}: {slug} has a different forecast timestamp')
        dataset = out / 'api/fpl/dataset' / f'gw{gw}.json'
        if not dataset.exists():
            errors.append(f'GW{gw}: dataset availability declaration missing')
        else:
            data = json.loads(dataset.read_text())
            if not archive and data.get('status') != 'unavailable':
                errors.append(f'GW{gw}: full dataset has no pre-deadline archive')
            elif archive:
                expected = datasets.gameweek_payload(gw, archive['rows'],
                    next(iter(evidence.values()))['generated_at'],
                    ids={r['name']: r['player_id'] for r in archive['rows']})
                if data.get('players') != expected['players']:
                    errors.append(f'GW{gw}: dataset differs from frozen full board')
    latest_path = out / 'api/latest.json'
    if latest_path.exists():
        latest = json.loads(latest_path.read_text())
        if latest.get('gameweek'):
            archive = forecast_archive.load(latest['gameweek'])
            if archive and latest.get('forecast_artifact_id') != archive['artifact_id']:
                errors.append('latest feed does not identify the archived forecast')
    if gameweeks:
        from evmax import experiments
        summary = out/experiments.API_PATH.lstrip('/')
        if not summary.exists() or not (out/experiments.PATH.lstrip('/')/'index.html').exists():
            errors.append('experiment page or summary missing')
        else:
            try:
                if json.loads(summary.read_text()) != experiments.report():
                    errors.append('experiment summary differs from retained evidence')
            except (ValueError, KeyError, OSError) as exc:
                errors.append(f'experiment evidence invalid: {exc}')
    return errors


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', default='dist')
    args = ap.parse_args()
    errors = validate(args.out)
    if errors:
        raise SystemExit('Publication blocked:\n- ' + '\n- '.join(errors))
    print('Site evidence and publication checks passed.')
