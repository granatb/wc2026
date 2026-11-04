"""Publish dated GW8–9 comparisons without changing historical predictions."""
import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import forecast_archive
from evmax import render, writer
from games.fpl import continuity
from scripts.publish_fpl_preview import read, dump, render_homepage
from scripts.publish_fpl_status import render_pages
from scripts.validate_site import validate


def recover(source, out):
    prior = REPO/'data/reviews/gw8/2026-10-21-preview'
    receipt = read(prior/'live-check.json')
    hashes = {name: next(c['sha256'] for c in receipt['checks']
                        if c['url']==f'https://evmax.ai/api/fpl/preview/{name}.json')
              for name in ('players','plan')}
    board_bytes = (out/'api/fpl/previews/gw8/2026-10-21/players.json').read_bytes()
    if hashlib.sha256(board_bytes).hexdigest() != hashes['players']:
        raise ValueError('surviving preview differs from the pre-deadline live receipt')
    continuity.BOARD.parent.mkdir(parents=True, exist_ok=True)
    if continuity.BOARD.exists() and continuity.BOARD.read_bytes()!=board_bytes:
        raise ValueError('cannot overwrite recovered forecast')
    continuity.BOARD.write_bytes(board_bytes)
    board, plan = json.loads(board_bytes), read(continuity.PLAN)
    boot, fixtures = read(source/'official/bootstrap.json'), read(source/'official/fixtures.json')
    receipts = {n: read(source/f'official/{n}.receipt.json') for n in ('bootstrap','fixtures','live-gw8','live-gw9')}
    captured = max(r['captured_at'] for r in receipts.values())
    results = {}
    for gw in (8,9):
        event = next(e for e in boot['events'] if e['id']==gw)
        live = read(source/f'official/live-gw{gw}.json')
        results[str(gw)] = dict(gameweek=gw, fetched_at=captured, event=event,
            event_receipt=dict(source=receipts['bootstrap']['url'],recorded_at=receipts['bootstrap']['captured_at'],
                               payload_sha256=forecast_archive.digest(event)),
            fixtures=[f for f in fixtures if f['event']==gw],
            live={'elements':[dict(id=p['id'], stats={k:p['stats'][k] for k in ('minutes','total_points')})
                              for p in live['elements']]})
        forecast_archive.require_final(results[str(gw)])
    baseline = forecast_archive.load(7)
    record = dict(schema_version=1, recorded_at=datetime.now(timezone.utc).isoformat(),
        publication_type='dated_comparison_recovery',
        baseline_gameweek=7, baseline_captured_at=baseline['captured_at'],
        baseline_forecast_sha256=baseline['artifact_id'],
        assumptions=['Consensus keeps the GW7 published XV, XI, captain, vice and bench order in GW8 and GW9.',
                     'No consensus transfers, hits or active chips; ordinary captain and automatic-substitution rules.',
                     'Reconstructed consensus is not a newly observed expert selection; comparison rows are excluded from the duel tally.',
                     'GW8 model scores the published 21 October early recommendation, not a final deadline selection.',
                     'GW9 has no published model selection; no model score or projection is reconstructed.'],
        early_publication=dict(checked_at=receipt['checked_at'],sha256=hashes,
            source_commit='e9a4f15',article='/fpl/gw8/preview/',forecast='/api/fpl/previews/gw8/2026-10-21/players.json',
            plan='/api/fpl/previews/gw8/2026-10-21/plan.json'),
        official_sources={n:{k:r[k] for k in ('url','captured_at','status','sha256')} for n,r in receipts.items()},
        bootstrap={'teams':boot['teams'],'elements':[{k:p[k] for k in ('id','web_name','first_name','second_name','element_type','team')} for p in boot['elements']]},
        consensus_state=continuity.selection(baseline['states']['consensus']),model_state=continuity.model_state(plan,board),
        account={str(gw):dict(points=points,transfers=0,hit_cost=0,
                 source='Owner-supplied Points screenshots, reported and authorized for publication on 4 November 2026')
                 for gw,points in ((8,42),(9,69))},results=results)
    record['evaluation']=continuity.evaluate(record,board,plan,baseline)
    continuity.validate(record)
    dump(continuity.PATH,record)
    return record


def review_body(record):
    from games.fpl.continuity import rows
    body=render._duel_table_html(None,rows(record),10,section=render.FPL)
    body+='<h2>How the comparison was recovered</h2><p>Recorded 4 November 2026, after official FPL final checks. '
    body+='The account column contains the owner’s actual Points-screen scores, with no transfers or hits in either week. '
    body+='Matching GW8 scores do not mean the account and model used the same team.</p>'
    st=record['consensus_state']['squad']
    xi=', '.join(html.escape(p['name'])+(' (C)' if p['is_captain'] else ' (VC)' if p['is_vice'] else '') for p in st if p['is_starter'])
    bench=', '.join(html.escape(p['name']) for p in sorted((p for p in st if not p['is_starter']),key=lambda p:p['bench_order']))
    body+=f'<h2>Stable consensus assumption</h2><p>We reused the published GW7 selection dated 14 October: {xi}. '
    body+=f'Bench: {bench} (goalkeeper first, then outfield priority). No transfers, hits or chips.</p>'
    body+='<p>This is the project’s saved ownership-based consensus team, not the average FPL manager and not a newly collected expert poll. '
    body+='Official field averages were 45 in GW8 and 47 in GW9; these are separate context.</p>'
    for c in record['evaluation']['comparisons']:
        for label,key in [('Reconstructed consensus','consensus_scoring'),('21 October early model','model_scoring')]:
            scoring=c[key]
            if scoring is None:continue
            body+=f'<h2>GW{c["gameweek"]}: {label} — {scoring["total_so_far"]} points</h2>'
            body+='<div class="table-wrap" style="overflow-x:auto"><table class="rank"><thead><tr><th>Player</th><th>Points</th><th>Multiplier</th><th>Counted</th><th>Note</th></tr></thead><tbody>'
            for p in scoring['rows']:
                body+=f'<tr><td>{html.escape(p["name"])}</td><td>{p["points"]}</td><td>{p["multiplier"]}</td><td>{p["points"]*p["multiplier"]}</td><td>{html.escape(p["note"])}</td></tr>'
            body+='</tbody></table></div>'
    g=record['evaluation']['early_forecast_grade']
    body+=f'<h2>GW8 early forecast accuracy</h2><p>All {g["n"]} published player projections from 21 October were matched to final official points. '
    body+=f'Mean absolute error: {g["mae_ours"]:.3f} points. This early-preview grade is kept separate from the frozen-deadline accuracy series. '
    body+='No FPL ep_next benchmark was present in the published preview feed. No GW9 model grade has been created.</p>'
    body+=f'<p><a style="text-decoration:underline" href="{continuity.API}">Scoring, selections, finality and publication provenance</a> · '
    body+='<a style="text-decoration:underline" href="/api/fpl/previews/gw8/2026-10-21/players.json">Original GW8 early forecast</a> · '
    body+='<a style="text-decoration:underline" href="/fpl/gw8/preview/">Original recommendation</a></p>'
    return body


def publish(source,out):
    record=recover(source,out)
    dump(out/continuity.API.lstrip('/'),record)
    meta=read(out/'api/latest.json')['preview'];board=read(out/'api/fpl/preview/players.json')
    payloads=[read(out/f'api/fpl/preview/players/{p["player_id"]}.json') for p in board['players']]
    for p in payloads:
        p['slug']=p['page'].rstrip('/').split('/')[-1]
    fixture_record=read(out/'api/fpl/fixtures/gw10.json')
    home=render_homepage(payloads,board['players'],meta,fixture_record['matches'],fixture_record['schedule_checked_at'])
    for path in ('index.html','fpl/gw10/index.html'):(out/path).write_text(home)
    body=review_body(record)
    prose={'headline':'GW8–9: results and recovered comparisons','standfirst':'GW8 early model 42; stable-consensus reconstruction 32 and 36; account results 42 and 69.',
           'body_html':body,'body_md':writer._html_to_md(body)}
    page=render.article_page(9,'review',prose['headline'],prose,[],[],continuity.API,'',generated_at=record['recorded_at'],
                            date_str='4 November 2026',show_table=False,available_rounds=list(range(1,11)),section=render.FPL)
    from scripts.publish_fpl_preview import clean_page
    page=clean_page(page).replace('/fpl/gw9/review/','/fpl/gw8-9/review/').replace('</style>',render._DUEL_CSS+'</style>',1)
    target=out/'fpl/gw8-9/review/index.html';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(page)
    from evmax.fpl_build import fpl_track_ledger
    from evmax import backtest
    ledger=fpl_track_ledger()
    (out/'track-record/index.html').write_text(render.track_record_page(backtest.build_track_record(),fpl=ledger,comparisons=continuity.rows(record)))
    (out/'fpl/accuracy/index.html').write_text(render.accuracy_page(ledger,date_str='4 November 2026',comparisons=continuity.rows(record)))
    status=read(REPO/'evmax/assets/editorial/fpl-gw9/status.json')
    status_home,status_article=render_pages(status)
    (out/'fpl/gw9/index.html').write_text(status_home);(out/'fpl/gw9/update/index.html').write_text(status_article)
    # Correct only the results cross-reference; preserve the November 3 predictions.
    article=out/'fpl/gw10/preview/index.html'
    article.write_text(article.read_text().replace('No retrospective forecast or model-team score has been created for GW8 or GW9.',
        'The original GW8 early recommendation has now been scored. GW9 has no published model selection. '
        '<a style="text-decoration:underline" href="/fpl/gw8-9/review/">See the recovered comparisons</a>.'))
    sitemap=out/'sitemap.xml';text=sitemap.read_text();url='https://evmax.ai/fpl/gw8-9/review/'
    if url not in text:sitemap.write_text(text.replace('</urlset>',f'<url><loc>{url}</loc></url></urlset>'))
    errors=validate(out)
    if errors:raise ValueError(errors)
    print(json.dumps({'recorded_at':record['recorded_at'],'rows':continuity.rows(record),
                      'early_forecast_n':record['evaluation']['early_forecast_grade']['n'],
                      'early_forecast_mae':record['evaluation']['early_forecast_grade']['mae_ours']},indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--out',type=Path,default=REPO/'dist')
    args=ap.parse_args();publish(args.source,args.out)
