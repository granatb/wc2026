"""Build the reviewed 21 October GW8 preview from retained model inputs.

Requires the private capture under data/reviews/gw8/2026-10-21-preview.
Reuses the exact saved simulations and preserves frozen forecast records.
"""
import argparse
import copy
import hashlib
import json
import pathlib
import re
import shutil
import socket
import sys
from unittest.mock import patch

REPO = pathlib.Path(__file__).resolve().parents[1]
ROOT = REPO/'data/reviews/gw8/2026-10-21-preview'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', default=str(ROOT/'site-preview'))
args = parser.parse_args()
sys.path.insert(0, str(REPO))
from core import fpl_api, fpl_live, forecast_archive, research, simcache
from evmax import fpl_build, fpl_articles, render, writer
from games.fpl import final_selection, model, state
from scripts.validate_site import validate

def read(path):
    return json.loads(path.read_text())

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')

def blocked(*args, **kwargs):
    raise RuntimeError('The prepared preview build uses retained inputs only')

def preview_navigation(page):
    """Select the current preview while keeping historical gameweeks reachable."""
    switcher=render._round_switcher_html(list(range(1,9)),8,
        base_path=render.FPL.switcher_base(),abbr=render.FPL.unit_abbr)
    switcher=switcher.replace('href="/fpl/gw8/"','href="/fpl/gw8/preview/"')
    return re.sub(r'<div class="round-switcher">.*?</div>',lambda _:switcher,
                  page,count=1,flags=re.S)

boot = read(ROOT/'inputs/bootstrap.json')
manifest = read(ROOT/'simulation-manifest.json')
comparison = read(ROOT/'comparison.json')
assert simcache.source_fingerprint() == manifest['source_fingerprint']
for name in ['bootstrap','fixtures']:
    receipt=read(ROOT/f'official/{name}.receipt.json')
    payload=read(ROOT/f'inputs/{name}.json')
    assert hashlib.sha256((ROOT/f'official/{name}.json').read_bytes()).hexdigest()==receipt['sha256']
    metadata={'recorded_at':receipt['captured_at'],'payload_sha256':forecast_archive.digest(payload),'source':receipt['url']}
    forecast_archive.require_fresh(payload,metadata)
    write(ROOT/f'inputs/{name}.meta.json',metadata)
fpl_api.DATA_DIR = str(ROOT/'inputs')
research.RESEARCH_DIR = str(ROOT/'research')
simcache.CACHE_DIR = str(ROOT/'runtime/simcache')
backfill=read(ROOT/'inputs/defcon_backfill.json')
players=read(ROOT/'players-gw8.json')
by_id={p['id']:p for p in players.values()}
raw=read(ROOT/'state-model-analysis.json')
raw.pop('bank',None)
validated=state.validate_state(raw,fpl_api.parse_players(boot))
lineup=comparison['baseline']['lineup']
bench=[lineup['reserve_goalkeeper']]+lineup['outfield_bench_order']
for entry, resolved in zip(raw['squad'],validated['squad']):
    name=by_id[resolved['id']]['name']
    entry.update(is_starter=name in lineup['xi'],is_captain=name==lineup['captain'],is_vice=name==lineup['vice'],bench_order=bench.index(name)+1 if name in bench else None)
write(ROOT/'state-model-preview.json',raw)
fpl_build.STATE_FILES={'model':str(ROOT/'state-model-preview.json'),'consensus':str(REPO/'games/fpl/state_consensus.json')}
grades=ROOT/'grades'
for path in (REPO/'evmax/assets/accuracy').glob('*.json'):
    if path.name!='gw7.json':shutil.copy2(path,grades/path.name)
horizon={}
for gw in range(8,13):
    for row in read(ROOT/f'artifact-gw{gw}.json')['rows']:
        horizon.setdefault(row['name'],{'gw':{}})['gw'][str(gw)]=row['x_points']

def saved_artifact(priors, player_meta, gameweek, sims, **kwargs):
    assert gameweek==8 and sims==50000
    assert player_meta==players
    assert json.loads(json.dumps(model._priors_projection(priors)))==manifest['weeks']['8']['prior_projection']
    artifact=copy.deepcopy(read(ROOT/'artifact-gw8.json'))
    artifact['rows']=model._int_keyed_distributions(artifact['rows'])
    return artifact,True

original_preview=fpl_build._preview_payloads
original_next_week=fpl_build._preview_gameweek
published_preview=read(REPO/'dist/api/fpl/preview/players.json')
assert published_preview['gameweek']==8
def fresh_preview(gw,sims,use_cache,archived_boot):
    # Current cards need the current player metadata as well as current model inputs.
    return original_preview(gw,sims,use_cache,boot,
                            generated_at=published_preview['generated_at'])

out=pathlib.Path(args.out).resolve()
if not out.exists():shutil.copytree(REPO/'dist',out)
with patch.object(socket,'create_connection',blocked), patch.object(socket,'getaddrinfo',blocked), \
     patch.object(fpl_api,'fetch_defcon_backfill',lambda _: {int(k):v for k,v in backfill.items()}), \
     patch.object(model,'build_artifact',saved_artifact), \
     patch.object(fpl_live,'refresh_live',lambda gw: fpl_live.read_live_cache(gw)), \
     patch.object(fpl_build,'_preview_payloads',fresh_preview), \
     patch.object(fpl_build,'_preview_gameweek',lambda _: original_next_week(boot)), \
     patch.object(fpl_build,'_accuracy_dir',lambda: str(grades)), \
     patch.object(fpl_build,'_load_horizon_matrix',lambda: horizon):
    fpl_build.build(7,sims=50000,out=str(out),use_llm=False,use_cache=False,live=True,preview=True)

# The later selection has its own dated result; the forecast archive stays intact.
selected=final_selection.load(7,read(REPO/'evmax/assets/accuracy/gw7.json'))
if selected:
    result_note=('<h2>GW7 result, recorded 21 October</h2>'
        '<p>The final Model XI scored <strong>59 points</strong> against a '
        '<strong>61.80</strong> projection. Saka captained the side. Thomas '
        'replaced Gibbs-White for three points. The 14 October pre-transfer '
        'selection remains archived at 53 points against 57.28 projected. '
        '<a style="text-decoration:underline" href="/api/fpl/gw7/final-selection.json">'
        'Final selection and scoring record</a> · '
        '<a style="text-decoration:underline" href="/api/fpl/accuracy/gw7.json">'
        'Original forecast grades</a>.</p>')
    pair_body=(REPO/'evmax/assets/editorial/fpl-gw7/confirmed-pair.html').read_text()
    pair_title='GW7: Saka and De Cuyper — lineup and captaincy'
    pair_prose={'headline':pair_title,
        'standfirst':'Saka captains the model lineup after the two transfers, with Thiago vice-captain.',
        'body_html':pair_body+result_note,'body_md':writer._html_to_md(pair_body+result_note)}
    score_panel=render.squad_live_panel_html(selected['scoring'],selected['results']['fetched_at'])
    score_panel=score_panel.replace('>Live</span>','>Final</span>').replace('pts so far','pts').replace('live — updates on rebuild · as of','official results · as of')
    pair_html=render.article_page(7,'confirmed-pair',pair_title,pair_prose,[],[],
        '/api/fpl/gw7/final-selection.json','',generated_at='2026-10-16T11:45:00Z',
        date_str='16 October 2026',show_table=False,available_rounds=list(range(1,9)),
        section=render.FPL,live_html=score_panel)
    pair_html=re.sub(r'<figure class="fig">\s*<figcaption>.*?</figcaption>\s*</figure>','',pair_html,count=1,flags=re.S)
    pair_html=re.sub(r'<h2>Bottom line</h2>\s*<p>\s*</p>','',pair_html,count=1)
    (out/'fpl/gw7/confirmed-pair/index.html').write_text(pair_html)
    (out/render.FPL.md_path(7,'confirmed-pair').lstrip('/')).write_text(render.article_md(
        7,'confirmed-pair',pair_title,pair_prose,[],[],'2026-10-16T11:45:00Z',
        '16 October 2026','/fpl/gw7/confirmed-pair/',section=render.FPL))
    baseline=out/'fpl/gw7/our-squad/index.html'
    baseline.write_text(baseline.read_text().replace('<div class="live-panel">',
        '<p>14 October pre-transfer selection: 53 points. '
        '<a style="text-decoration:underline" href="/fpl/gw7/confirmed-pair/">'
        'The final 16 October selection scored 59</a>. '
        'Result record corrected 21 October; original forecasts preserved.</p>'
        '<div class="live-panel">',1))

# Use the existing article and hero layout for the new research preview.
body=(REPO/'evmax/assets/editorial/fpl-gw8/preview.html').read_text()
title='GW8 plan: Mbeumo, then save the second transfer'
summary='Szoboszlai to Mbeumo projects 64.10 points, up 2.31 on holding. Keep Evanilson, captain Saka and retain the second free transfer.'
prose={'headline':title,'standfirst':summary,'body_html':body,'body_md':writer._html_to_md(body)}
stamp=manifest['captured_at']
article=out/'fpl/gw8/preview/index.html'
article.parent.mkdir(parents=True,exist_ok=True)
article_html=render.article_page(8,'preview',title,prose,[],[],'/api/fpl/preview/review.json','',generated_at=stamp,date_str='21 October 2026',show_table=False,available_rounds=list(range(1,9)),section=render.FPL)
article_html=re.sub(r'<figure class="fig">\s*<figcaption>.*?</figcaption>\s*</figure>','',article_html,count=1,flags=re.S)
article_html=re.sub(r'<h2>Bottom line</h2>\s*<p>\s*</p>','',article_html,count=1)
article.write_text(preview_navigation(article_html.replace('No data available this round.',summary)))
md=out/render.FPL.md_path(8,'preview').lstrip('/')
md.parent.mkdir(parents=True,exist_ok=True)
md.write_text(render.article_md(8,'preview',title,prose,[],[],stamp,'21 October 2026','/fpl/gw8/preview/',section=render.FPL))
write(out/'api/fpl/preview/plan.json',read(REPO/'evmax/assets/editorial/fpl-gw8/plan.json'))
write(out/'api/fpl/preview/review.json',{'gameweek':8,'status':'preview','generated_at':stamp,'model_version':manifest['model_version'],'inputs_captured_at':read(ROOT/'official/bootstrap.receipt.json')['captured_at'],'body_html':body,'body_md':prose['body_md']})
root=(out/'index.html').read_text()
frozen=forecast_archive.load(7)
old=frozen['prose']['our-squad']
import html
root=root.replace(html.escape(old['headline']),html.escape(title)).replace(html.escape(old['standfirst']),html.escape(summary))
pitch_rows=[dict(row,player_id=players[row['name']]['id']) for row in model._int_keyed_distributions(read(ROOT/'artifact-gw8.json')['rows'])]
planned_raw=copy.deepcopy(raw)
for entry in planned_raw['squad']:
    if entry['name']=='Szoboszlai':
        entry.update(name='Mbeumo',bought_at=7.8)
planned_lineup=comparison['manual']['szobo_Mbeumo']['lineup']
planned_bench=[planned_lineup['reserve_goalkeeper']]+planned_lineup['outfield_bench_order']
for entry,resolved in zip(planned_raw['squad'],state.validate_state(planned_raw,fpl_api.parse_players(boot))['squad']):
    name=by_id[resolved['id']]['name']
    entry.update(is_starter=name in planned_lineup['xi'],is_captain=name==planned_lineup['captain'],is_vice=name==planned_lineup['vice'],bench_order=planned_bench.index(name)+1 if name in planned_bench else None)
entries, meta=fpl_articles.squad_article(state.validate_state(planned_raw,fpl_api.parse_players(boot)),pitch_rows)
old_pitch=render.pitch_svg_fpl([entry for entry in frozen['envelopes']['our-squad']['entries'] if entry.get('role')=='XI'])
new_pitch=render.pitch_svg_fpl([entry for entry in entries if entry.get('role')=='XI'])
assert old_pitch in root
root=root.replace(old_pitch,new_pitch,1)
# The hero is the only link within its section that points at our-squad.
root=re.sub(r'(<section class="feat".*?</section>)',lambda match: match.group(0).replace('/fpl/gw7/our-squad/','/fpl/gw8/preview/').replace('Featured · Our Squad','Featured · Planned GW8 XI').replace('14 October 2026','21 October 2026'),root,count=1,flags=re.S)
root=root.replace('<title>Fantasy Premier League Gameweek 7 picks &amp; captains','<title>Fantasy Premier League Gameweek 8 preview')
head,tail=root.split('</head>',1)
root=head.replace('Gameweek 7','Gameweek 8')+'</head>'+tail
root=re.sub(r'<tr class="dl-preview">.*?</tr>',lambda match: match.group(0).replace('preview · frozen Thursday','before planned move',1).replace('preview · frozen Thursday','Wednesday preview'),root,flags=re.S)
(out/'index.html').write_text(preview_navigation(root))
for page in out.rglob('*.html'):
    text=page.read_text()
    if 'id="gw7-provisional"' in text:
        page.write_text(re.sub(r'<aside id="gw7-provisional".*?</aside>','',text,flags=re.S))
latest=read(out/'api/latest.json')
latest['preview']={'gameweek':8,'generated_at':stamp,'players':'/api/fpl/preview/players.json','review':'/api/fpl/preview/review.json','plan':'/api/fpl/preview/plan.json'}
if selected:
    latest['final_selection_result']='/api/fpl/gw7/final-selection.json'
write(out/'api/latest.json',latest)
sitemap=out/'sitemap.xml'
text=sitemap.read_text()
if 'https://evmax.ai/fpl/gw8/preview/' not in text:
    sitemap.write_text(text.replace('</urlset>','<url><loc>https://evmax.ai/fpl/gw8/preview/</loc></url></urlset>'))
errors=validate(out)
assert not errors, errors
feed=read(out/'api/fpl/preview/players.json')
assert feed['gameweek']==8 and len(feed['players'])==len(players)
assert 'Gameweek 7 graded · Gameweek 8 preview' in (out/'index.html').read_text()
assert 'id="gw7-provisional"' not in (out/'index.html').read_text()
assert not (out/'api/fpl/gw8/decision.json').exists()
before=read(ROOT/'protected-before.json')
changes=[name for name,digest in before.items() if hashlib.sha256((REPO/name).read_bytes()).hexdigest()!=digest]
assert not changes,changes
write(ROOT/'preview-validation.json',{'result':'PASS','preview_players':len(players),'protected_files_unchanged':len(before),'no_new_frozen_forecast':True,'site_path':str(out),'production_dist_untouched':out != REPO/'dist'})
print('Validated GW8 preview from retained inputs. No remote publication or account action.')
