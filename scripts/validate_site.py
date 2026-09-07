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
        current = json.loads(latest_file.read_text()).get('gameweek')
        if current is not None:
            gameweeks.add(int(current))
    for gw in sorted(gameweeks):
        path = out / 'api/fpl' / f'gw{gw}' / 'captains.json'
        archive = forecast_archive.load(gw)
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
    return errors


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', default='dist')
    args = ap.parse_args()
    errors = validate(args.out)
    if errors:
        raise SystemExit('Publication blocked:\n- ' + '\n- '.join(errors))
    print('Site evidence and publication checks passed.')
