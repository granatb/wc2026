"""Dated release of the reviewed 14 October rehearsal through the normal builder.

Does not fetch, simulate, change account/state files, accept decisions or deploy.
Run --out PATH for review, accept its proposal with scripts/fpl_decision.py,
then run --out dist. The normal freshness, dossier and decision gates remain.
Retained private inputs are required; this is intentionally not a generic runner.
"""
import argparse
import copy
import hashlib
import html
import json
import pathlib
import shutil
import socket
import sys
from unittest.mock import patch

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core import forecast_archive, fpl_api, fpl_live, research, simcache
from games.fpl import model, state
from evmax import fpl_build, render, writer

EVIDENCE = REPO / 'data/reviews/gw7/2026-10-14-provisional'
RELEASE = REPO / 'data/releases/2026-10-14-gw7'
CONTENT = REPO / 'evmax/assets/editorial/fpl-gw7'
NOTICE = ('Provisional GW7 · inputs 14 October 2026. Website held rosters are not '
          'a verified account. Only 3 free transfers are confirmed; account squad, '
          'bank, selling prices and chips remain unconfirmed. No proposed transfer '
          'has been recorded as completed. Friday news may change the shortlist.')

def read(path):
    return json.loads(path.read_text())

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def blocked(*args, **kwargs):
    raise RuntimeError('This release uses saved evidence only; network disabled')

def setup():
    RELEASE.mkdir(parents=True, exist_ok=True)
    inputs = RELEASE / 'inputs'
    inputs.mkdir(exist_ok=True)
    for p in (EVIDENCE / 'inputs').glob('*.json'):
        shutil.copy2(p, inputs / p.name)
    for p in (REPO / 'data/fpl').glob('live_gw*.json'):
        shutil.copy2(p, inputs / p.name)
    snapshot = REPO / 'data/fpl/feed_snapshot.json'
    if snapshot.exists():
        shutil.copy2(snapshot, inputs / snapshot.name)
    shutil.copy2(REPO / 'data/reviews/gw6/2026-10-14-final/results.json', inputs / 'live_gw6.json')
    for name in ('bootstrap', 'fixtures'):
        receipt = read(EVIDENCE / 'official' / f'{name}.receipt.json')
        original = EVIDENCE / 'official' / f'{name}.json'
        assert hashlib.sha256(original.read_bytes()).hexdigest() == receipt['sha256']
        assert read(inputs / f'{name}.json') == read(original)
        write(inputs / f'{name}.meta.json', {'recorded_at': receipt['captured_at'],
            'payload_sha256': forecast_archive.digest(read(original)), 'source': receipt['url']})
    fpl_api.DATA_DIR = str(inputs)
    simcache.CACHE_DIR = str(RELEASE / 'simcache')
    research.RESEARCH_DIR = str(RELEASE / 'research')
    manifest = read(EVIDENCE / 'simulation-manifest.json')
    assert manifest['source_fingerprint'] == simcache.source_fingerprint()
    assert manifest['sims'] == 10000 and manifest['editorial_entries'] == {}
    boot = read(inputs / 'bootstrap.json')
    parsed = fpl_api.parse_players(boot)
    board = read(EVIDENCE / 'artifact-gw7.json')
    players = read(EVIDENCE / 'players-gw7.json')
    rows = {r['name']: r for r in board['rows']}
    by_id = {p['id']: p for p in players.values()}
    states = {}
    for key, source in fpl_build.STATE_FILES.items():
        raw = read(pathlib.Path(source))
        validated = state.validate_state(raw, parsed)
        # Held holdings, not executed transfers. Re-select only the website XI.
        names = [by_id[p['id']]['name'] for p in validated['squad']]
        groups = {pos: sorted((n for n in names if players[n]['position'] == pos),
            key=lambda n: (rows[n]['x_points'], n), reverse=True) for pos in ('GK','DEF','MID','FWD')}
        options = []
        for d in range(3,6):
            for m in range(2,6):
                f = 10-d-m
                if 1 <= f <= 3:
                    xi = groups['GK'][:1] + groups['DEF'][:d] + groups['MID'][:m] + groups['FWD'][:f]
                    cap = max(xi, key=lambda n: rows[n]['x_points'])
                    options.append((sum(rows[n]['x_points'] for n in xi)+rows[cap]['x_points'], xi, cap))
        _, xi, cap = max(options)
        vice = max((n for n in xi if n != cap), key=lambda n: rows[n]['x_points'])
        bench = [n for n in names if n not in xi and players[n]['position']=='GK']
        bench += sorted((n for n in names if n not in xi and players[n]['position']!='GK'), key=lambda n: rows[n]['x_points'], reverse=True)
        for p, v in zip(raw['squad'], validated['squad']):
            name = by_id[v['id']]['name']
            p.update(is_starter=name in xi, is_captain=name==cap, is_vice=name==vice,
                     bench_order=None if name in xi else bench.index(name)+1)
        if key == 'model':
            raw['free_transfers'] = 3
        raw['active_chip'] = None
        raw['publication_status'] = 'provisional_held_website_roster_not_verified_account'
        raw['account_submission'] = 'unverified'
        target = RELEASE / f'state-{key}.json'
        write(target, raw)
        states[key] = str(target)
    fpl_build.STATE_FILES = states
    # Neutral sourced dossiers document flags without changing the saved model.
    notes = RELEASE / 'research/players'
    notes.mkdir(parents=True, exist_ok=True)
    for p in players.values():
        if p['name'] not in {by_id[v['id']]['name'] for path in states.values()
                for v in state.validate_state(read(pathlib.Path(path)), parsed)['squad']}:
            continue
        note = ('---\nentity: player\nname: '+p['name']+'\nplayer_id: '+str(p['id'])+
                '\nround: 7\nlambda_multiplier: 1.0\nsources:\n'
                '  - https://fantasy.premierleague.com/api/bootstrap-static/\n'
                'updated: 2026-10-14\n---\n\n'
                f"Official capture 14 October 14:05 UTC: status {p['status']}; "
                f"news: {p.get('news') or 'no availability warning in feed'}. "
                'Held website roster only. No availability or minutes override. '
                'Not a confirmed starting XI; review Friday before account moves.\n')
        (notes / f"{p['id']}.md").write_text(note)
    horizon = {}
    for gw in range(7,12):
        for r in read(EVIDENCE / f'artifact-gw{gw}.json')['rows']:
            horizon.setdefault(r['name'], {'gw': {}})['gw'][str(gw)] = r['x_points']
    return manifest, horizon

def saved_artifact(priors, players, gameweek, sims, **kwargs):
    manifest = read(EVIDENCE / 'simulation-manifest.json')
    assert gameweek == 7 and sims == manifest['sims']
    assert json.loads(json.dumps(model._priors_projection(priors))) == manifest['weeks']['7']['prior_projection']
    assert players == read(EVIDENCE / 'players-gw7.json')
    artifact = copy.deepcopy(read(EVIDENCE / 'artifact-gw7.json'))
    artifact['rows'] = model._int_keyed_distributions(artifact['rows'])
    return artifact, True

def additional_pages(out):
    stamp = read(EVIDENCE / 'simulation-manifest.json')['captured_at']
    for slug, title in [('transfer-plan','GW7: provisional transfer plan'), ('gw6-review','GW6: final results and lessons')]:
        prose = writer._parse_cache_md(CONTENT / f'{slug}.md')
        # Dated editorial HTML is checked in; it can contain real tables and links.
        prose['body_html'] = (CONTENT / f'{slug}.html').read_text()
        prose['body_md'] = writer._html_to_md(prose['body_html'])
        path = out / f'fpl/gw7/{slug}/index.html'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render.article_page(7,slug,title,prose,[],[],
            '/api/fpl/gw7/research.json','',generated_at=stamp,date_str='14 October 2026',
            available_rounds=list(range(1,8)),section=render.FPL))
        (out / render.FPL.md_path(7,slug).lstrip('/')).write_text(render.article_md(
            7,slug,title,prose,[],[],stamp,'14 October 2026',
            canonical_path=render.FPL.article_path(7,slug),section=render.FPL))
        write(out / f'api/fpl/gw7/{slug}.json', {'gameweek':7,'title':title,
            'generated_at':stamp,'url':f'https://evmax.ai/fpl/gw7/{slug}/',
            'body_html':prose['body_html'],'body_md':prose['body_md']})
    comparison = read(EVIDENCE / 'comparison.json')
    write(out / 'api/fpl/gw7/research.json', {'status':'provisional','account_submission':'unverified',
        'confirmed_free_transfers':3, 'assumptions':comparison['scope'], 'method':comparison['method'],
        'news_checked_through':'2026-10-14T14:27:00Z', 'pending':'Friday news and actual account inputs',
        'comparisons':comparison['manual'], 'sensitivity':comparison['sensitivity'],
        'recovery_sensitivity':comparison['szobo_recovery_sensitivity'],
        'price_sensitivity':comparison['price_sensitivity']})
    for path in (out/'api/fpl/gw7').rglob('*.json'):
        if path.name == 'decision.json':
            continue  # The immutable acceptance receipt must stay exact.
        payload = read(path)
        if isinstance(payload,dict):
            payload['publication_status'] = 'provisional'
            payload['inputs_captured_at'] = read(EVIDENCE/'official/bootstrap.receipt.json')['captured_at']
            payload['account_submission'] = 'unverified'
            write(path,payload)
    latest = read(out/'api/latest.json')
    latest['publication_status'] = 'provisional'
    latest['account_submission'] = 'unverified'
    for slug in ('transfer-plan','gw6-review','experts'):
        latest['articles'][slug] = f'/api/fpl/gw7/{slug}.json'
    write(out/'api/latest.json',latest)
    banner = ('<aside id="gw7-provisional" class="wrap" style="padding:18px;border:1px solid #d0d9cc">'
        '<strong>'+html.escape(NOTICE)+'</strong><p>'
        '<a href="/fpl/gw7/transfer-plan/">Joint transfer plans and confidence</a> · '
        '<a href="/fpl/gw7/gw6-review/">Final GW6 review: Model 41, Consensus 71</a> · '
        '<a href="/fpl/gw7/experts/">Dated expert review</a></p></aside>')
    pages = [out/'index.html', * (out/'fpl/gw7').rglob('index.html'), *(out/'fpl/players').rglob('index.html')]
    for path in pages:
        body = path.read_text()
        if 'id="gw7-provisional"' not in body:
            body = body.replace('</header>', '</header>'+banner, 1)
        path.write_text(body)
    # Additional editorial URLs use the existing sitemap and machine discovery.
    sitemap = out / 'sitemap.xml'
    body = sitemap.read_text()
    for slug in ('transfer-plan','gw6-review'):
        url = f'https://evmax.ai/fpl/gw7/{slug}/'
        if url not in body:
            body = body.replace('</urlset>', f'<url><loc>{url}</loc></url></urlset>')
    sitemap.write_text(body)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    if not (out/'api/latest.json').exists():
        raise ValueError('Start from a copy of cumulative dist; never an empty export')
    manifest, horizon = setup()
    backfill = fpl_api.read_cache('defcon_backfill')
    # All gates remain in fpl_build.build; only data providers are isolated.
    with patch.object(socket,'create_connection',blocked), patch.object(socket,'getaddrinfo',blocked), \
         patch.object(fpl_api,'fetch_defcon_backfill',lambda players: {int(k):v for k,v in backfill.items()}), \
         patch.object(fpl_live,'refresh_live',lambda gw: fpl_live.read_live_cache(gw)), \
         patch.object(model,'build_artifact',saved_artifact), \
         patch.object(fpl_build,'_load_horizon_matrix',lambda: horizon):
        for gw in range(1,7):
            fpl_build.build(gw,out=str(out),sims=10000,use_llm=False,live=True if gw==6 else None,preview=False)
        fpl_build.build(7,out=str(out),sims=10000,use_llm=False,live=False,
                        cache_dir=str(CONTENT.parent),preview=False)
    additional_pages(out)
    print('Provisional release built; account submission unverified; publication acceptance and deployment are separate.')

if __name__ == '__main__':
    main()
