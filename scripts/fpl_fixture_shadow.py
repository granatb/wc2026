#!/usr/bin/env python3
"""Collect fixture histories and build an independent, non-promoting shadow forecast."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import fpl_fixture_history, forecast_archive as evidence


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['collect', 'build', 'freeze', 'grade'])
    ap.add_argument('--context', type=Path)
    ap.add_argument('--record', type=Path)
    ap.add_argument('--results', type=Path)
    ap.add_argument('--summary', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--histories', type=Path)
    ap.add_argument('--cache', type=Path, default=Path('data/experiments/fixture-history-cache'))
    ap.add_argument('--model', type=Path, default=Path('docs/research/2026-09-07-fixtures-validation.json'))
    ap.add_argument('--production-model', type=Path, default=Path('experiments/fpl-2026-27/statistical-model.json'))
    args = ap.parse_args()
    read = lambda p: json.loads(p.read_text())
    if args.command in ('freeze', 'grade'):
        if not args.record:
            ap.error('freeze/grade requires --record')
        from games.fpl.fixture_shadow import freeze, grade
        if args.command == 'freeze':
            result = freeze(read(args.record), args.out)
        else:
            if not args.results:
                ap.error('grade requires retained --results')
            result = grade(read(args.record), read(args.results))
            evidence.atomic_json(args.out/(result['artifact_id']+'.json'), result)
            result = {k:v for k,v in result.items() if k != 'results'}
        if args.summary:
            evidence.atomic_json(args.summary, result)
        print(json.dumps(result, indent=2))
        return
    if not args.context:
        ap.error('collect/build requires --context')
    ctx = read(args.context)
    if args.command == 'collect':
        for key in ('bootstrap', 'all_fixtures'):
            evidence.require_fresh(ctx[key], ctx['receipts'][key])
        result = fpl_fixture_history.collect(ctx['bootstrap'], ctx['gameweek'], args.cache,
            progress=lambda n,total: print(f'Retained {n}/{total} player histories', flush=True))
        evidence.atomic_json(args.out, result)
        print(f'Complete receipt-backed collection: {len(result["players"])} players')
    else:
        if not args.histories:
            ap.error('build requires --histories')
        from games.fpl.fixture_shadow import build, retain
        result = build(ctx, read(args.histories), read(args.model), read(args.production_model))
        retained = retain(args.out, result)
        if args.summary:
            evidence.atomic_json(args.summary, {k:v for k,v in retained.items() if k != 'evidence_path'})
        print(json.dumps(retained, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(f'Fixture shadow refused: {exc}')
