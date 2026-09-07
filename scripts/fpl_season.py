#!/usr/bin/env python3
"""Operate one prospective FPL week, with explicit rehearse/freeze/grade states."""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import fpl_api, fpl_live
from games.fpl import season_ops as ops, experiments as ledger
from scripts import fpl_providers


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['status', 'rehearse', 'freeze', 'run', 'grade', 'verify-backup'])
    ap.add_argument('--gw', type=int)
    ap.add_argument('--protocol', type=Path, default=REPO/'experiments/fpl-2026-27/protocol.json')
    ap.add_argument('--root', type=Path, default=REPO/'experiments/fpl-2026-27/records')
    ap.add_argument('--work', type=Path, default=REPO/'data/experiments/season-2026-27')
    ap.add_argument('--model', type=Path, default=REPO/'experiments/fpl-2026-27/statistical-model.json')
    ap.add_argument('--seed-state', type=Path, default=REPO/'games/fpl/state.json')
    ap.add_argument('--context', type=Path, help='rehearse from retained inputs without fetching')
    ap.add_argument('--run-file', type=Path)
    ap.add_argument('--backup', type=Path)
    ap.add_argument('--sims', type=int, default=5000)
    args = ap.parse_args(argv)
    if args.command == 'verify-backup':
        if not args.backup: ap.error('--backup is required')
        print(json.dumps(ops.verify_backup(args.backup), indent=2)); return
    protocol = ops.read(args.protocol)
    if args.command == 'freeze':
        if not args.run_file: ap.error('--run-file is required')
        with ops.operation_lock(args.root):
            result = ops.freeze_run(protocol, args.run_file, args.root, args.work)
    else:
        if not args.gw or not 1 <= args.gw <= 38: ap.error('--gw must be 1–38')
        if args.command == 'status':
            result = ops.status(protocol, fpl_api.read_cache('bootstrap') or fpl_api.fetch_bootstrap(), args.root, args.gw)
        else:
            with ops.operation_lock(args.root):
                if args.command == 'grade':
                    record = ledger.read_week(args.root/f'gw{args.gw}.json')
                    results = fpl_live.refresh_live(args.gw)
                    grade = ledger.bank_grade(args.root, record, results)
                    result = dict(state='graded', gameweek=args.gw, arms=grade['arms'])
                else:
                    if args.sims < 1000: ap.error('at least 1000 simulations required')
                    if args.command == 'run':
                        snapshot = ops.status(protocol, fpl_api.fetch_bootstrap(), args.root, args.gw)
                        if snapshot['state'] in ('missed_deadline', 'history_gap'):
                            raise ValueError(snapshot['state']+'; investigate without backfilling history')
                        if snapshot['state'] != 'ready_to_refresh_and_freeze':
                            print(json.dumps(snapshot, indent=2)); return
                    if args.context and args.command == 'run':
                        ap.error('run always refreshes; use rehearse for retained context')
                    context = ops.read(args.context) if args.context else fpl_providers.refresh(args.gw)
                    if context['gameweek'] != args.gw: raise ValueError('context gameweek mismatch')
                    result = ops.rehearse(protocol, context, ops.read(args.model), ops.read(args.seed_state),
                                           args.root, args.work, sims=args.sims)
                    if args.command == 'run':
                        result = ops.freeze_run(protocol, result['run'], args.root, args.work)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(f'Season operation refused: {exc}')
