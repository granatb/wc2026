"""Add the dated owner confirmation without rebuilding or changing any forecast.

Requires the cumulative 14 October export. No fetch, simulation, account action,
publication-decision substitution or freshness-timestamp rewrite occurs.
"""
import argparse
import collections
import hashlib
import itertools
import json
import pathlib
import re
import sys
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from evmax import render, writer
from scripts.validate_site import validate

EVIDENCE = REPO / 'data/reviews/gw7/2026-10-14-provisional'
RELEASE = REPO / 'data/releases/2026-10-16-gw7'
STAMP = '2026-10-16T11:45:00Z'
SLUG = 'confirmed-pair'
TITLE = 'GW7: Saka and De Cuyper confirmed; conditional starting XI'
NOTICE = ('16 October owner update: Bruno → Saka and Shaw → De Cuyper confirmed. '
          '1 FT remains assuming no other moves. Full account squad and bank are '
          'unverified. Forecast inputs remain 14 October; Friday fitness news is incomplete.')


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def calculate():
    comparison = read(EVIDENCE / 'comparison.json')
    players = read(EVIDENCE / 'players-gw7.json')
    names = sorted((set(comparison['baseline']['names']) - {'B.Fernandes', 'Shaw'}) | {'Saka', 'De Cuyper'})
    assert len(names) == 15
    assert collections.Counter(players[n]['position'] for n in names) == dict(GK=2, DEF=5, MID=5, FWD=3)
    assert max(collections.Counter(players[n]['team'] for n in names).values()) <= 3

    def best(rows):
        options = []
        for xi in itertools.combinations(names, 11):
            pos = collections.Counter(players[n]['position'] for n in xi)
            if pos['GK'] == 1 and 3 <= pos['DEF'] <= 5 and 2 <= pos['MID'] <= 5 and 1 <= pos['FWD'] <= 3:
                cap = max(xi, key=lambda n: rows[n]['x_points'])
                options.append((sum(rows[n]['x_points'] for n in xi) + rows[cap]['x_points'], xi, cap))
        return max(options)

    utilities = []
    for gw in range(7, 12):
        rows = {r['name']: r for r in read(EVIDENCE / f'artifact-gw{gw}.json')['rows']}
        score, xi, cap = best(rows)
        utilities.append(score)
        if gw == 7:
            base_xi, captain = list(xi), cap
            vice = max((n for n in xi if n != cap), key=lambda n: rows[n]['x_points'])
    assert set(base_xi) == {'Raya', 'De Cuyper', 'Tarkowski', 'Virgil', 'Saka', 'Cole Palmer', 'E.Le Fée', 'Gibbs-White', 'Thiago', 'Calvert-Lewin', 'Evanilson'}
    cautious = {r['name']: r for r in read(EVIDENCE / 'artifact-gw7-news_cautious.json')['rows']}
    cautious_score, cautious_xi, cautious_cap = best(cautious)
    bench = sorted((n for n in names if n not in cautious_xi and players[n]['position'] != 'GK'), key=lambda n: cautious[n]['x_points'], reverse=True)
    assert set(cautious_xi) == set(base_xi) and cautious_cap == captain == 'Saka' and vice == 'Thiago'
    assert bench == ['Bobby Thomas', 'N.Williams', 'Szoboszlai']
    delta = {str(h): round(sum(.95**i * (utilities[i] - comparison['baseline']['weekly_utilities'][i]) for i in range(h)), 3) for h in (1, 3, 5)}
    assert round(utilities[0], 2) == 61.80 and delta == {'1': 4.52, '3': 8.358, '5': 10.197}
    return {'gameweek': 7, 'status': 'owner_confirmed_pair_conditional_roster',
            'owner_reported_at': STAMP, 'forecast_inputs_date': '2026-10-14',
            'confirmed_transfers': [{'out': 'B.Fernandes', 'in': 'Saka'}, {'out': 'Shaw', 'in': 'De Cuyper'}],
            'account_roster_verified': False, 'account_bank': None,
            'remaining_free_transfers_if_no_other_moves': 1, 'next_gw_free_transfers_if_roll': 2,
            'recorded_roster_after_pair': names, 'xi': base_xi, 'captain': captain, 'vice': vice,
            'outfield_bench_order': bench, 'reserve_goalkeeper': 'Sánchez',
            'mean_xi_captain': round(utilities[0], 3), 'weekly_utilities': [round(v, 3) for v in utilities],
            'discounted_gain_vs_saved_hold': delta, 'cautious_mean_xi_captain': round(cautious_score, 3),
            'method': 'Exhaustive legal-XI mean plus captain on saved 14 October boards; cautious bench judgment. No autosubs, conditional vice value or refreshed forecast.'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', default='dist')
    ap.add_argument('--base-url', help='Verify already prepared local output against live HTTP; does not build')
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    assert read(out / 'api/latest.json')['forecast_artifact_id'] == '91272d7db80451db2ddac544b124f2e3aba423f43b66a0e105877e15edd41b10'
    result = calculate()
    if args.base_url:
        urls = ['/', '/fpl/gw7/our-squad/', '/fpl/gw7/transfer-plan/', f'/fpl/gw7/{SLUG}/', f'/api/fpl/gw7/{SLUG}.json', '/api/latest.json', '/sitemap.xml']
        for url in urls:
            local = out / url.lstrip('/')
            if url.endswith('/'):
                local = local / 'index.html'
            request = urllib.request.Request(args.base_url.rstrip('/') + url, headers={'Cache-Control': 'no-cache', 'User-Agent': 'evmax-release-verification/1.0'})
            with urllib.request.urlopen(request, timeout=30) as response:
                assert response.status == 200 and response.read() == local.read_bytes(), url
        write(RELEASE / 'live-check.json', {'result': 'PASS', 'urls': urls})
        print('All seven live responses match the local release.')
        return
    before = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}
    body = (REPO / 'evmax/assets/editorial/fpl-gw7/confirmed-pair.html').read_text()
    prose = {'headline': TITLE, 'standfirst': NOTICE, 'body_html': body, 'body_md': writer._html_to_md(body)}
    target = out / f'fpl/gw7/{SLUG}/index.html'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render.article_page(7, SLUG, TITLE, prose, [], [], f'/api/fpl/gw7/{SLUG}.json', '', generated_at=STAMP, date_str='16 October 2026', available_rounds=list(range(1,8)), section=render.FPL, show_table=False))
    md = out / render.FPL.md_path(7, SLUG).lstrip('/')
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(render.article_md(7, SLUG, TITLE, prose, [], [], STAMP, '16 October 2026', canonical_path=render.FPL.article_path(7, SLUG), section=render.FPL))
    write(out / f'api/fpl/gw7/{SLUG}.json', {**result, 'body_html': body, 'body_md': prose['body_md']})
    latest = read(out / 'api/latest.json')
    latest['articles'][SLUG] = f'/api/fpl/gw7/{SLUG}.json'
    latest['owner_update'] = {'reported_at': STAMP, 'url': f'/api/fpl/gw7/{SLUG}.json', 'account_roster_verified': False}
    write(out / 'api/latest.json', latest)
    banner = '<aside id="gw7-provisional" class="wrap" style="padding:18px;border:1px solid #d0d9cc"><strong>' + NOTICE + '</strong><p><a href="/fpl/gw7/confirmed-pair/">Confirmed transfers, starting XI, bench and captain</a></p></aside>'
    pages = [out / 'index.html', *(out / 'fpl/gw7').rglob('index.html'), *(out / 'fpl/players').rglob('index.html')]
    for path in pages:
        text = path.read_text()
        if 'id="gw7-provisional"' in text:
            text, count = re.subn(r'<aside id="gw7-provisional".*?</aside>', lambda _: banner, text, flags=re.S)
            assert count == 1
        else:
            if '</header>' not in text:
                assert 'GW2: incomplete player archive' in text or 'http-equiv="refresh"' in text.lower(), str(path)
                continue  # Retain historical unavailable cards and redirects.
            text = text.replace('</header>', '</header>' + banner, 1)
        path.write_text(text)
    sitemap = out / 'sitemap.xml'
    text = sitemap.read_text()
    url = f'https://evmax.ai/fpl/gw7/{SLUG}/'
    if url not in text:
        sitemap.write_text(text.replace('</urlset>', f'<url><loc>{url}</loc></url></urlset>'))
    allowed = {str(p.relative_to(out)) for p in pages} | {'api/latest.json', 'sitemap.xml'}
    changed = [name for name, digest in before.items() if hashlib.sha256((out/name).read_bytes()).hexdigest() != digest]
    assert set(changed) <= allowed, changed
    errors = validate(out)
    assert not errors, errors
    protected = read(EVIDENCE / 'protected-before.json')
    assert all(hashlib.sha256((REPO/name).read_bytes()).hexdigest() == digest for name, digest in protected.items())
    write(RELEASE / 'calculation.json', result)
    write(RELEASE / 'content-check.json', {'result': 'PASS', 'existing_files_changed': changed, 'protected_files_unchanged': len(protected), 'existing_files_checked': len(before), 'forecast_rebuilt': False})
    print(f'PASS: exact pair and legal XI verified; {len(protected)} protected files unchanged; dated editorial update prepared, not deployed.')


if __name__ == '__main__':
    main()
