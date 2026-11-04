"""Restore current preview presentation using retained forecasts and checked fixtures."""
import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from core import fpl_api
from evmax import fpl_players, render
from scripts.publish_fpl_preview import read, dump, dt, render_homepage
from scripts.validate_site import validate


def current_matches(forecasts, fixtures, gameweek):
    """Refresh kickoff times while retaining every forecast probability/value."""
    by_id={str(m['match_id']):m for m in forecasts}
    current=[f for f in fixtures if f['fantasy_round']==gameweek]
    if {str(f['match_id']) for f in current} != set(by_id):
        raise ValueError('fixture identity changed; a reviewed forecast is required')
    result=[]
    for f in sorted(current,key=lambda f:f.get('kickoff_utc') or ''):
        m=copy.deepcopy(by_id[str(f['match_id'])])
        if (m['home'],m['away']) != (f['home'],f['away']):
            raise ValueError('fixture identity differs from retained forecast')
        m['kickoff']=f['kickoff_utc']
        result.append(m)
    return result


def restore(source, forecasts, out):
    latest=read(out/'api/latest.json')
    if latest['publication_type']!='early_preview':
        raise ValueError('expected an existing early preview')
    gw=latest['gameweek'];meta=latest['preview']
    boot=read(source/'official/bootstrap.json')
    fixture_receipt=read(source/'official/fixtures.receipt.json')
    captured=fixture_receipt['captured_at']
    if not 0 <= (datetime.now(timezone.utc)-dt(captured)).total_seconds() <= 86400:
        raise ValueError('fresh official fixtures required')
    fx=fpl_api.parse_fixtures(read(source/'official/fixtures.json'),fpl_api.parse_teams(boot))
    artifact=read(forecasts/f'artifact-gw{gw}.json')
    matches=current_matches(artifact['matches'],fx,gw)
    board=read(out/'api/fpl/preview/players.json')
    payloads=[]
    for row in board['players']:
        p=read(out/f'api/fpl/preview/players/{row["player_id"]}.json')
        p['slug']=p['page'].rstrip('/').split('/')[-1]
        payloads.append(p)
    date=f'{dt(meta["as_of"]).day} {dt(meta["as_of"]):%B %Y}'
    def write(path,html):
        target=out/path.lstrip('/');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(html)
    home=render_homepage(payloads,board['players'],meta,matches,captured)
    write('/index.html',home);write(f'/fpl/gw{gw}/index.html',home)
    for p in payloads:
        write(p['page']+'index.html',fpl_players.player_page_html(p,gw,date_str=date,methodology=render.FPL.methodology))
    write('/fpl/players/index.html',fpl_players.index_page_html(payloads,gw,fpl_players.PREVIEW_FEED_PATH,date_str=date,preview=meta))
    for pos,_ in fpl_players.TIER_SEGMENTS:
        write(fpl_players.tier_path(pos)+'index.html',fpl_players.tier_page_html(pos,payloads,gw,date_str=date,preview=meta))
    receipt={'gameweek':gw,'schedule_checked_at':captured,'forecast_generated_at':meta['as_of'],
             'source':'https://fantasy.premierleague.com/api/fixtures/',
             'official_fixtures_sha256':fixture_receipt['sha256'],'matches':matches}
    dump(REPO/f'evmax/assets/editorial/fpl-gw{gw}/fixtures.json',receipt)
    dump(out/f'api/fpl/fixtures/gw{gw}.json',receipt)
    errors=validate(out)
    if errors:raise ValueError(errors)
    print(json.dumps({'players':len(payloads),'fixtures':len(matches),'schedule_checked_at':captured,
                      'forecast_generated_at':meta['as_of']},indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--forecasts',type=Path,required=True)
    ap.add_argument('--out',type=Path,default=REPO/'dist')
    args=ap.parse_args();restore(args.source,args.forecasts,args.out)
