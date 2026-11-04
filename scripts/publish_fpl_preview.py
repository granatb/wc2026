"""Publish a retained early player forecast, separately from accepted squad forecasts."""
import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import fpl_api
from evmax import fpl_players, render, writer
from scripts.publish_fpl_status import make_status, render_pages


def read(path):
    return json.loads(Path(path).read_text())


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')


def dt(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def validate_preview_record(record, evidence):
    if record != evidence:
        raise ValueError('early preview differs from retained evidence')
    if record.get('publication_type') != 'early_preview' or record.get('provisional') is not True or not record.get('players'):
        raise ValueError('early preview needs a provisional full player board')
    generated = dt(record['generated_at'])
    if generated >= dt(record['deadline']):
        raise ValueError('early forecast was generated after its deadline')
    times = record.get('source_times', {})
    if not {'official', 'markets', 'histories'} <= times.keys() or any(
            not 0 <= (generated-dt(value)).total_seconds() <= 86400 for value in times.values()):
        raise ValueError('early preview needs fresh official, history and market inputs')


def clean_page(page):
    page = re.sub(r'<figure class="fig">\s*<figcaption>.*?</figcaption>\s*</figure>', '', page, flags=re.S)
    page = re.sub(r'<h2>Bottom line</h2>\s*<p>\s*</p>', '', page)
    return page.replace('href="/fpl/gw8/"', 'href="/fpl/gw8/preview/"')


def table(rows, payloads):
    lookup = {p['name']: p for p in payloads}
    body = []
    for row in rows:
        p = lookup[row['name']]
        opponents = ', '.join(f'{f["opponent"]} ({f["venue"]})' for f in p['fixtures'] if f['gw']==10)
        # The dated card contains the full fixture strip and probability distribution.
        body.append(f'<tr><td><a style="text-decoration:underline" href="{p["page"]}">{html.escape(row["name"])}</a></td>'
                    f'<td>{html.escape(row["team"])}</td><td>{row["position"]}</td><td>{html.escape(opponents)}</td>'
                    f'<td>{row["x_points"]:.2f}</td><td>{row["captain_ev"]:.2f}</td><td>{row["ceiling"]:.2f}</td></tr>')
    return ('<div class="table-wrap" style="overflow-x:auto"><table class="rank"><thead><tr>'
            '<th>Player</th><th>Club</th><th>Position</th><th>Fixture</th><th>xPts</th><th>Captain xPts</th><th>Ceiling</th>'
            '</tr></thead><tbody>'+''.join(body)+'</tbody></table></div>')


def early_cards(payloads, meta):
    cards = fpl_players.top_cards_html(payloads)
    note = fpl_players.preview_note_html(meta)
    leaders = fpl_players._card_row('Model leaders for gameweek 10 · early preview',
        'The highest expected points in this run. Recheck European minutes and team news before Friday.',
        [fpl_players._card_cell(p) for p in payloads[:3]], lead=True)
    return cards.replace(note, note+leaders, 1)


def render_homepage(payloads, rows, meta, matches, fixtures_checked_at):
    """Keep the normal homepage ledger and fixture rail on an early preview."""
    from evmax.fpl_build import fpl_track_ledger
    from games.fpl import continuity
    comparison_rows = continuity.rows()
    history = sorted(fpl_track_ledger() + comparison_rows, key=lambda r:r['gw'])
    continuity_copy = ('GW8 early-model and GW8–9 reconstructed consensus results are now included. '
                       if comparison_rows else 'GW8 and GW9 have no frozen model forecast to evaluate. ')
    gw=meta['gameweek']
    ranked=sorted(rows,key=lambda r:-r['x_points'])
    lead,second=ranked[:2]
    stamp=dt(meta['as_of'])
    date=f'{stamp.day} {stamp:%B %Y}'
    title=f'GW{gw} early preview: {lead["name"]} leads the model'
    summary=(f'{lead["name"]} leads at {lead["x_points"]:.2f} expected points, followed by '
             f'{second["name"]} at {second["x_points"]:.2f}. Fresh Tuesday projections, provisional ahead of Europe.')
    checked=dt(fixtures_checked_at)
    home=clean_page(render.landing_page(gw,{'slug':'preview',
        'prose':{'headline':title,'standfirst':summary},'viz_html':table(ranked[:10],payloads)},[],
        date_str=date,section=render.FPL,available_rounds=list(range(1,gw+1)),
        cards_html=early_cards(payloads,meta),duel_history=history,
        fixtures=matches,rail_label=f'GW{gw} fixtures · UTC',rail_link=False,
        extra_style=fpl_players.CARD_CSS+fpl_players.TOP_CARDS_CSS+render._NAV_SCROLL_CSS,
        deadline_iso=meta['deadline'],
        pre_feed_html='<p><a style="text-decoration:underline" href="/fpl/gw9/update/">GW9 final results</a> · '
            '<a style="text-decoration:underline" href="/track-record/">Full evaluation record</a> · '
            '<a style="text-decoration:underline" href="/fpl/accuracy/">Forecast accuracy</a></p>'
            f'<p class="method">{continuity_copy}'
            f'Fixture times checked {checked.day} {checked:%B, %H:%M} UTC; '
            f'match projections from {stamp.day} {stamp:%B, %H:%M} UTC.</p>'))
    home=home.replace('<div class="pagelabel">Latest analysis</div>\n<div class="feed"></div>', '')
    return re.sub(r'<p class="hs-what">.*?</p>',
        '<p class="hs-what">Player projections from 50,000 simulations, the results of our published squads, and this week’s fixtures.</p>',home,flags=re.S)


def build(source: Path, out: Path):
    boot, fixtures = read(source/'inputs/bootstrap.json'), read(source/'inputs/fixtures.json')
    artifact, players = read(source/'artifact-gw10.json'), read(source/'players-gw10.json')
    manifest, histories = read(source/'simulation-manifest.json'), read(source/'inputs/form_history.json')
    history_receipt = read(source/'history-refresh.json')
    if history_receipt['failures'] or history_receipt['captured'] != history_receipt['requested']:
        raise ValueError('incomplete player-history refresh')
    odds = read(source/'inputs/odds_gw10.json')
    priced = sum(bool(m.get('lam_home') is not None and m.get('lam_away') is not None) for m in odds['matches'].values())
    if priced != 10:
        raise ValueError('this preview requires market coverage for all ten fixtures')
    generated = manifest['completed_at']
    if not 0 <= (datetime.now(timezone.utc)-dt(generated)).total_seconds() <= 86400:
        raise ValueError('forecast must be freshly simulated before publishing')
    event = next(e for e in boot['events'] if e['id']==10)
    if datetime.now(timezone.utc) >= dt(event['deadline_time']):
        raise ValueError('cannot publish this early preview after the deadline')
    meta = {'gameweek':10, 'as_of':generated, 'deadline':event['deadline_time'], 'provisional':True}
    rows = artifact['rows']
    fx = fpl_api.parse_fixtures(fixtures, fpl_api.parse_teams(boot))
    payloads, unmatched = fpl_players.assemble_payloads(rows, players,
        {e['id']:e for e in boot['elements']}, {}, {}, None, fx, {10:odds}, 10, generated, form_history=histories)
    if unmatched or len(payloads) != len(rows):
        raise ValueError(f'preview identity mismatch: {unmatched}')
    for p in payloads:
        p['preview'] = meta
        # This is a general player forecast, not a statement of account ownership.
        p['verdict']['stance'] = 'GW10 early projection'
        p['flag'] = {'i':'Injured', 's':'Suspended', 'u':'Unavailable', 'd':'Doubtful'}.get(p['status'])
    receipts = [read(p) for p in (source/'official').glob('element-*.receipt.json')]
    source_times = {'official':read(source/'official/bootstrap.receipt.json')['captured_at'],
                    'markets':odds['captured_at'], 'histories':max(r['captured_at'] for r in receipts)}
    api = '/api/fpl/previews/gw10/2026-11-03.json'
    evidence_path = REPO/'evmax/assets/previews/gw10/2026-11-03.json'
    board = [{'player_id':p['id'], 'name':p['name'], 'team':p['team'], 'position':p['position'],
              **{k:p['projection'].get(k) for k in ('x_points','captain_ev','ceiling')},
              'kickoff':p['kickoff'], 'flag':p['flag'], 'page':p['page']} for p in payloads]
    evidence = {'publication_type':'early_preview', 'gameweek':10, 'provisional':True,
        'generated_at':generated, 'deadline':event['deadline_time'], 'preview':meta,
        'model_version':manifest['model_version'], 'simulations':manifest['sims'], 'seed':manifest['seed'],
        'source_times':source_times, 'market_coverage':{'priced':priced,'fixtures':10},
        'history_coverage':history_receipt, 'source_fingerprint':manifest['source_fingerprint'],
        'input_sha256':{str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted((source/'inputs').glob('*.json'))},
        'methodology':render.FPL.methodology, 'license':render.DATA_LICENSE_URL,
        'sources':['https://fantasy.premierleague.com/api/bootstrap-static/',
                   'https://fantasy.premierleague.com/api/fixtures/',
                   'https://fantasy.premierleague.com/api/element-summary/{id}/',
                   'https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard'],
        'players':board}
    validate_preview_record(evidence, evidence)
    if evidence_path.exists() and read(evidence_path) != evidence:
        raise ValueError('dated early-preview evidence already exists; use a new dated revision')
    dump(evidence_path, evidence)
    if not out.exists():
        shutil.copytree(REPO/'dist', out)
    latest = read(out/'api/latest.json')
    old_feed = read(out/'api/fpl/preview/players.json')
    if old_feed['gameweek'] != 10:
        archive = out/'api/fpl/previews/gw8/2026-10-21'
        if not archive.exists():
            shutil.copytree(out/'api/fpl/preview', archive)
        # Old article links retain their original board when the current cards roll forward.
        old_article = out/'fpl/gw8/preview/index.html'
        old_article.write_text(old_article.read_text().replace('/api/fpl/preview/', '/api/fpl/previews/gw8/2026-10-21/'))
    # Current preview is a replaceable surface. The full prior tree is retained
    # above; do not leave its old plan.json beside the new player forecast.
    current_preview = out/'api/fpl/preview'
    if current_preview.exists():
        shutil.rmtree(current_preview)
    def write(path, content):
        target=out/path.lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    dump(out/api.lstrip('/'), evidence)
    dump(out/'api/fpl/preview/players.json', {**evidence, 'coverage':'full'})
    date = f'{dt(generated).day} {dt(generated):%B %Y}'
    for p in payloads:
        dump(out/fpl_players.payload_json_path(p).lstrip('/'), fpl_players.player_json(
            p, render.FPL.methodology, render.SITE_URL, render.DATA_LICENSE_URL, render.DATA_LICENSE_TEXT))
        write(p['page']+'index.html', fpl_players.player_page_html(p,10,date_str=date,methodology=render.FPL.methodology))
    write('/fpl/players/index.html', fpl_players.index_page_html(payloads,10,fpl_players.PREVIEW_FEED_PATH,date_str=date,preview=meta))
    for pos, _ in fpl_players.TIER_SEGMENTS:
        write(fpl_players.tier_path(pos)+'index.html', fpl_players.tier_page_html(pos,payloads,10,date_str=date,preview=meta))
    ranked = sorted(rows,key=lambda r:-r['x_points'])
    top = ranked[:10]
    lead, second = top[:2]
    title = f'GW10 early preview: {lead["name"]} leads the model'
    summary = (f'{lead["name"]} leads at {lead["x_points"]:.2f} expected points, followed by '
               f'{second["name"]} at {second["x_points"]:.2f}. Fresh Tuesday projections, provisional ahead of Europe.')
    stamp = dt(generated)
    top_table = table(top,payloads)
    position_tables = ''.join(f'<h3>{label}</h3>'+table([r for r in ranked if r['position']==pos][:5],payloads)
                              for pos,label in [('GK','Goalkeepers'),('DEF','Defenders'),('MID','Midfielders'),('FWD','Forwards')])
    watch_ids = [12,368,346,154,427,480,115,106]
    by_id = {p['id']:p for p in payloads}
    watch = ''.join(f'<li><strong>{html.escape(by_id[pid]["name"])}</strong>: '
                    f'{html.escape(by_id[pid]["news"] or "Available in the official FPL feed")}. '
                    f'GW10 projection {by_id[pid]["projection"]["x_points"]:.2f} xPts.</li>' for pid in watch_ids if pid in by_id)
    body = (f'<p><strong>Early preview · {date}, {stamp:%H:%M} UTC.</strong> {html.escape(summary)}</p>'
            '<p>The deadline is <strong>Friday 6 November, 18:30 UTC (19:30 Denmark)</strong>. '
            'European fixtures and the final press conferences can still change minutes and availability. '
            'These are early projections, not the final deadline selection.</p>'
            f'<h2>Captain shortlist</h2><p>{html.escape(lead["name"])} is the model captain at '
            f'{lead["captain_ev"]:.2f} expected points with the armband; {html.escape(second["name"])} '
            f'is the next option at {second["captain_ev"]:.2f}. Only {lead["x_points"]-second["x_points"]:.2f} '
            'xPts separates their ordinary projections: a small edge that midweek news could reverse. '
            'These rankings compare individual players; '
            'they are not a budget-constrained squad.</p>'+top_table+
            '<p>xPts is the simulated mean. Captain xPts doubles that player’s points before vice-captain fallback. '
            'Ceiling is the model’s upper-tail average, not a guaranteed return. '
            'Open a player card for the full points distribution and fixture strip.</p>'
            '<h2>Options by position</h2>'+position_tables+
            '<h2>Availability and minutes</h2><ul>'+watch+'</ul>'
            '<p>Liverpool’s <a style="text-decoration:underline" href="https://www.liverpoolfc.com/news/match-report-liverpool-arsenal-premier-league-november-2026">'
            'official Arsenal match report</a> confirms Szoboszlai returned as a substitute. '
            'Being available does not guarantee a start or a full match. Saka remains injured in the fresh FPL feed; '
            'no return date has been assumed. Recheck European minutes and club updates before the deadline.</p>'
            '<h2>GW9 update</h2><p>Newcastle 0–1 Everton completed the scheduled fixtures. '
            '<a style="text-decoration:underline" href="/fpl/gw9/update/">Read the updated results and finality status</a>. '
            'No retrospective forecast or model-team score has been created for GW8 or GW9.</p>'
            '<h2>Inputs and method</h2><p>50,000 simulations, seed 12345, model version '
            f'{manifest["model_version"]}; all ten fixtures have fresh market inputs. No model retuning or editorial availability overrides. '
            'The cards use refreshed player histories through the played GW9 fixtures; future-week xPts are not carried over from October.</p>'
            f'<p>Official FPL capture: {source_times["official"]}. Market capture: {source_times["markets"]}. '
            f'Player-history refresh completed: {source_times["histories"]}. Simulation completed: {generated}.</p>'
            '<p><a style="text-decoration:underline" href="https://fantasy.premierleague.com/api/bootstrap-static/">Official FPL player data</a> · '
            '<a style="text-decoration:underline" href="https://fantasy.premierleague.com/api/fixtures/">Official fixtures</a> · '
            f'<a style="text-decoration:underline" href="{api}">Dated forecast and input provenance</a> · '
            '<a style="text-decoration:underline" href="/fpl/players/">All player cards</a>.</p>')
    prose={'headline':title,'standfirst':summary,'body_html':body,'body_md':writer._html_to_md(body),
           'bottom_line':f'{lead["name"]} leads this early run. Recheck availability and European minutes before Friday’s deadline.'}
    article = clean_page(render.article_page(10,'preview',title,prose,[],[],api,'',generated_at=generated,
        date_str=date,show_table=False,available_rounds=list(range(1,11)),section=render.FPL))
    home = render_homepage(payloads,rows,meta,artifact['matches'],source_times['official'])
    for path,page in [('index.html',home),('fpl/gw10/index.html',home),('fpl/gw10/preview/index.html',article)]:
        write(path,page)
    if (source/'official/bootstrap-release.json').exists():
        status = make_status(read(source/'official/bootstrap-release.json'),
            read(source/'official/fixtures-release.json'),
            read(source/'official/bootstrap-release.receipt.json')['captured_at'])
    else:
        status = make_status(boot,fixtures,source_times['official'])
    status['next'].update(forecast_status='early_preview',preview_path='/fpl/gw10/preview/')
    dump(REPO/'evmax/assets/editorial/fpl-gw9/status.json', status)
    dump(out/'api/fpl/status.json',status)
    status_home,status_article=render_pages(status)
    write('fpl/gw9/index.html',status_home)
    write('fpl/gw9/update/index.html',status_article)
    dump(out/'api/latest.json',{'publication_type':'early_preview','gameweek':10,'generated_at':generated,
        'preview':meta,'articles':{'preview':api},'preview_evidence':str(evidence_path.relative_to(REPO)),
        'current_status':{'data':'/api/fpl/status.json','article':'/fpl/gw9/update/'},
        'last_frozen_forecast':latest['last_frozen_forecast']})
    sitemap=out/'sitemap.xml'
    text=sitemap.read_text()
    for path in ['/fpl/gw10/','/fpl/gw10/preview/']:
        if render.SITE_URL+path not in text:
            text=text.replace('</urlset>',f'<url><loc>{render.SITE_URL+path}</loc><lastmod>{stamp:%Y-%m-%d}</lastmod></url></urlset>')
    sitemap.write_text(text)
    from scripts.validate_site import validate
    errors=validate(out)
    if errors:
        raise ValueError(errors)
    print(json.dumps({'generated_at':generated,'players':len(payloads),'captains':top[:5],'out':str(out)},indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    build(args.source,args.out)
