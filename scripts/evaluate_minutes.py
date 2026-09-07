#!/usr/bin/env python3
"""Fit and evaluate the historical minutes candidate without altering live forecasts."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.forecast_archive import atomic_json
from games.fpl.minutes_model import evaluate

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--train',type=Path,required=True)
    ap.add_argument('--test',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args = ap.parse_args()
    result = evaluate(args.train,args.test)
    atomic_json(args.out,result)
    print(json.dumps({c:{m:{k:v for k,v in s.items() if k != 'calibration'} for m,s in models.items()}
                      for c,models in result['cohorts'].items()},indent=2))
