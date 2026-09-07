#!/usr/bin/env python3
"""Prepare, freeze, grade and report the registered virtual FPL experiment."""
import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import forecast_archive as evidence, fpl_live
from games.fpl import experiments, grading, forecast_providers


def read(path):
    return json.loads(Path(path).read_text())


history = experiments.load_history

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['prepare', 'freeze', 'grade', 'report'])
    ap.add_argument('--protocol', type=Path, default=REPO/'experiments/fpl-2026-27/protocol.json')
    ap.add_argument('--root', type=Path, default=REPO/'experiments/fpl-2026-27/records')
    ap.add_argument('--gw', type=int)
    ap.add_argument('--bootstrap', type=Path, default=REPO/'data/fpl/bootstrap.json')
    ap.add_argument('--fixtures', type=Path, default=REPO/'data/fpl/fixtures.json')
    ap.add_argument('--boards', type=Path, help='directory with one forecast file per registered arm')
    ap.add_argument('--seed-state', type=Path, default=REPO/'games/fpl/state.json')
    ap.add_argument('--submissions', type=Path)
    ap.add_argument('--sources', type=Path, help='provider source directory; defaults beside the boards/submissions')
    ap.add_argument('--results', type=Path)
    ap.add_argument('--out', type=Path)
    args = ap.parse_args(argv)
    protocol = read(args.protocol)
    records = history(args.root)
    previous = records[-1] if records else None
    if args.command == 'report':
        report = experiments.report_from_directory(protocol, args.root)
        if args.out:
            evidence.atomic_json(args.out, report)
        print(json.dumps(report, indent=2))
        return 0
    if args.gw is None:
        ap.error('--gw is required')
    if args.command == 'grade':
        if not args.results:
            ap.error('--results is required')
        record = experiments.read_week(args.root/f'gw{args.gw}.json')
        grade = experiments.grade_week(record, read(args.results))
        path = grading.write_accuracy(args.gw, grade, out_dir=args.root/'grades')
        print(f'Graded virtual squads: {path}')
        return 0
    boot = read(args.bootstrap)
    for path in (args.bootstrap, args.fixtures):
        evidence.require_fresh(read(path), read(path.with_suffix('.meta.json')))
    fx = [f for f in read(args.fixtures) if f.get('event') == args.gw]
    if args.command == 'prepare':
        if not args.boards or not args.out:
            ap.error('--boards and --out are required')
        missing = [arm for arm in protocol['arms'] if not (args.boards/f'{arm}.json').exists()]
        if missing:
            raise ValueError('missing forecast providers: ' + ', '.join(missing))
        seed = None
        if previous is None:
            state = read(args.seed_state)
            resolved = fpl_live.resolve_squad(state, boot)
            seed = [resolved[e['name']]['id'] for e in state['squad']]
        submissions = {}
        for arm in protocol['arms']:
            board = read(args.boards/f'{arm}.json')
            if board.get('provider_version'):
                key = board['source_artifact_id']
                if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
                    raise ValueError('invalid provider source ID')
                forecast_providers.verify_board_source(arm, board,
                    read((args.sources or args.boards/'sources')/f'{key}.json'))
            old = previous['arms'][arm] if previous else None
            decision = experiments.choose_decision(old['squad_ids'] if old else seed,
                                                  board['predictions'], boot,
                                                  old['portfolio'] if old else None)
            submissions[arm] = dict(board, **decision, interventions=board.get("interventions", []))
        # Validate draft without creating a prospective record or resetting clocks.
        experiments.prepare_week(protocol, args.gw, boot, submissions, previous, fixtures=fx)
        evidence.atomic_json(args.out, submissions)
        print(f'Prepared reviewable draft, not frozen: {args.out}')
    else:
        if not args.submissions:
            ap.error('--submissions is required')
        submissions = read(args.submissions)
        for arm, board in submissions.items():
            if board.get('provider_version'):
                key = board['source_artifact_id']
                if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
                    raise ValueError('invalid provider source ID')
                forecast_providers.verify_board_source(arm, board,
                    read((args.sources or args.submissions.parent/'sources')/f'{key}.json'))
        record = experiments.prepare_week(protocol, args.gw, boot, submissions, previous, fixtures=fx)
        result = experiments.write_week(args.root, record)
        print(f"Frozen GW{args.gw}: {result['artifact_id']}. Publish an independent pre-deadline receipt.")
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise SystemExit(f'Experiment refused: {exc}')
