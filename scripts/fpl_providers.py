#!/usr/bin/env python3
"""Train, refresh inputs, and build reviewable four-arm experiment forecasts."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import fpl_api, fpl_live, fpl_odds, fpl_bench, forecast_archive as evidence
from games.fpl import forecast_providers as providers


def read(path):
    return json.loads(Path(path).read_text())


def refresh(gameweek):
    boot, all_fixtures = fpl_api.refresh()
    if datetime.now(timezone.utc) >= evidence.deadline(boot, gameweek):
        raise ValueError('deadline passed')
    fixtures = [f for f in all_fixtures if f.get('event') == gameweek]
    if not fixtures:
        raise ValueError('no target fixtures')
    history = [fpl_live.refresh_live(gw) for gw in range(1, gameweek)]
    odds = fpl_odds.fetch_gw_odds(gameweek,
        [r for r in fpl_api.parse_fixtures(all_fixtures, fpl_api.parse_teams(boot))
         if r['fantasy_round'] == gameweek])
    ffiq = fpl_bench.fetch_ffiq()
    return dict(gameweek=gameweek, captured_at=datetime.now(timezone.utc).isoformat(),
        bootstrap=boot, all_fixtures=all_fixtures, fixtures=fixtures,
        receipts={key:read(Path(fpl_api.DATA_DIR)/f'{name}.meta.json')
                  for key,name in [('bootstrap','bootstrap'), ('all_fixtures','fixtures')]},
        history=history, odds=odds, ffiq=ffiq,
        backfill=fpl_api.read_cache(fpl_api.DEFCON_CACHE_NAME) or {})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['train', 'refresh', 'build'])
    ap.add_argument('--gw', type=int)
    ap.add_argument('--train', type=Path, default=REPO/'data/research/fpl-2023-24.csv')
    ap.add_argument('--test', type=Path, default=REPO/'data/research/fpl-2024-25.csv')
    ap.add_argument('--model', type=Path, default=REPO/'experiments/fpl-2026-27/statistical-model.json')
    ap.add_argument('--context', type=Path)
    ap.add_argument('--out', type=Path)
    ap.add_argument('--sims', type=int, default=5000)
    args = ap.parse_args(argv)
    if args.command == 'train':
        result = providers.train_statistical(args.train, args.test)
        evidence.atomic_json(args.model, result)
        print(json.dumps(dict(model=result['model_version'], heldout=result['heldout']), indent=2))
        return
    if args.command == 'refresh':
        if not args.gw or not args.context:
            ap.error('refresh requires --gw and --context')
        context = refresh(args.gw)
        evidence.atomic_json(args.context, context)
        print(f'Observed fresh context for GW{args.gw}: {args.context}')
        return
    if not args.context or not args.out:
        ap.error('build requires --context and --out')
    if args.sims < 1000:
        ap.error('at least 1000 simulations required')
    boards, source = providers.build_boards(read(args.context), read(args.model), sims=args.sims)
    # Persist source evidence before exposing boards. Only private/workspace raw
    # artifacts are written here; the website publishes derived metrics.
    evidence.atomic_json(args.out/'sources'/f"{source['artifact_id']}.json", source)
    for arm, board in boards.items():
        evidence.atomic_json(args.out/f'{arm}.json', board)
    print(json.dumps(dict(status='draft_boards_ready_not_enrolled', output=str(args.out),
        players=len(boards['market']['predictions']), consensus=source['consensus'],
        statistical_cold_starts=len(source['statistical_cold_start_ids']),
        source_artifact_id=source['artifact_id']), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(f'Provider run refused: {exc}')
