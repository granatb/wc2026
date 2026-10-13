#!/usr/bin/env python3
"""Accept one reviewed dry-build FPL decision for publication, never for an account.

Build to a scratch output directory first. Review fpl-decision-gwN.json, then
pass its proposal_id and a rationale here. Changing the squad or forecast
requires a new review. Acceptance records are immutable and stored by ID.
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from games.fpl import publication_decision as decision


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--proposal',required=True)
    ap.add_argument('--accept-id',required=True,help='Exact proposal_id reviewed by the operator')
    ap.add_argument('--operator',required=True)
    ap.add_argument('--rationale',required=True,help='Why this squad/captain/bench and hold or transfer choice was accepted')
    ap.add_argument('--root',type=Path,default=decision.ROOT)
    args=ap.parse_args(argv)
    proposal=json.loads(Path(args.proposal).read_text())
    receipt=decision.accept(proposal,args.accept_id,args.operator,args.rationale)
    path=decision.receipt_path(proposal,args.root)
    decision.save_accepted(path,receipt)
    print(f'Accepted publication decision: {path}\nAccount submission: unverified (separate user action).')


if __name__=='__main__':
    main()
