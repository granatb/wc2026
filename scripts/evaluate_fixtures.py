#!/usr/bin/env python3
"""Evaluate fixed fixture-aware ridge against a matching per-fixture ablation."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.forecast_archive import atomic_json
from games.fpl.fixture_challenger import evaluate

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('train', 'test', 'out'):
        ap.add_argument('--'+name, type=Path, required=True)
    args = ap.parse_args()
    report = evaluate(args.train, args.test)
    atomic_json(args.out, report)
    print(json.dumps(report['scores'], indent=2))
