"""Verify this dated release's evidence, visible copy, APIs and optional HTTP bytes."""
import argparse
import hashlib
import json
import pathlib
import sys
import urllib.request
from html.parser import HTMLParser

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from core import experts
from scripts.validate_site import validate

class Cells(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=[]; self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr': self.row=[]
        if tag=='td': self.cell=''
    def handle_data(self,data):
        if self.cell is not None: self.cell+=data
    def handle_endtag(self,tag):
        if tag=='td': self.row.append(self.cell); self.cell=None
        if tag=='tr' and self.row: self.rows.append(self.row)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',default='dist')
    ap.add_argument('--base-url')
    ap.add_argument('--receipt',required=True)
    args=ap.parse_args()
    out=pathlib.Path(args.out)
    evidence=REPO/'data/reviews/gw7/2026-10-14-provisional'
    read=lambda p: json.loads(p.read_text())
    errors=validate(out)
    assert not errors,errors
    experts.validate(read(REPO/'research/experts/gw7.json'))
    comparison=read(evidence/'comparison.json')
    body=(out/'fpl/gw7/transfer-plan/index.html').read_text()
    table=Cells(); table.feed(body)
    labels=['hold','bruno_saka','saka_gonzalo','bruno_saka_szobo_tavernier','saka_gonzalo_decuyper','saka_tavernier_decuyper']
    assert len(table.rows)==len(labels)
    for cells,label in zip(table.rows,labels):
        p=comparison['manual'][label]
        assert int(cells[0])==p['transfers']
        for ix,h in ((2,'1'),(3,'3'),(4,'5')):
            assert cells[ix]==f"{p['delta'][h]:+.2f}" if label!='hold' else cells[ix]=='0.00'
        assert cells[5]==f"£{p['bank']:.1f}m" and int(cells[6])==p['ft_next_gw']
    pages=['/','/fpl/gw7/','/fpl/gw7/our-squad/','/fpl/gw7/captains/',
           '/fpl/gw7/experts/','/fpl/gw7/transfer-plan/','/fpl/gw7/gw6-review/',
           '/fpl/accuracy/','/track-record/']
    for url in pages[:7]:
        text=(out/url.lstrip('/')/'index.html').read_text()
        assert 'id="gw7-provisional"' in text,url
        assert 'account' in text and 'Friday' in text,url
    assert 'saved-transfer option value' in body and 'not confidence intervals' in body
    assert '8.63' in body and '7.02' in body and '£0.3m short' in body
    assert 'Model 41, Consensus 71' in (out/'fpl/gw7/gw6-review/index.html').read_text()
    latest=read(out/'api/latest.json')
    assert latest['gameweek']==7 and latest['forecast_artifact_id']
    assert latest['publication_status']=='provisional'
    for slug in ('transfer-plan','gw6-review','experts'):
        assert latest['articles'][slug]==f'/api/fpl/gw7/{slug}.json'
    rows=read(evidence/'artifact-gw7.json')['rows']
    public=read(out/'api/fpl/gw7/captains.json')
    assert public['publication_status']=='provisional'
    xp={r['name']:r['x_points'] for r in public['entries']}
    assert xp['Haaland']==8.63 and xp['Saka']==7.02
    model=read(out/'api/fpl/gw7/our-squad.json')
    assert model['squad']['projected_total']==comparison['baseline']['weekly_utilities'][0]
    assert model['squad']['captain']=='Thiago' and model['squad']['free_transfers']==3
    assert set(e['name'] for e in model['entries'])==set(comparison['baseline']['names'])
    decision=read(out/'api/fpl/gw7/decision.json')
    assert decision['account_submission']=='unverified'
    assert decision['proposal']['states']['consensus'].get('bank') is None
    grade=read(out/'api/fpl/accuracy/gw6.json')
    assert grade==read(REPO/'evmax/assets/accuracy/gw6.json')
    assert grade['squads']['our-squad']['realized_official']==41
    assert grade['squads']['consensus-squad']['realized_official']==71
    protected=read(evidence/'protected-before.json')
    changed=[name for name,digest in protected.items() if hashlib.sha256((REPO/name).read_bytes()).hexdigest()!=digest]
    assert not changed,changed
    urls=pages+['/api/latest.json','/api/fpl/gw7/our-squad.json','/api/fpl/gw7/captains.json',
        '/api/fpl/gw7/experts.json','/api/fpl/gw7/research.json','/api/fpl/gw7/decision.json',
        '/api/fpl/accuracy/gw6.json','/api/fpl/dataset/gw7.json']
    served=[]
    if args.base_url:
        for url in urls:
            local=out/url.lstrip('/')
            if url.endswith('/'): local=local/'index.html'
            request=urllib.request.Request(args.base_url.rstrip('/')+url+'?release=gw7-20261014',headers={'User-Agent':'evmax-release-verification/1.0','Cache-Control':'no-cache'})
            with urllib.request.urlopen(request,timeout=30) as response:
                payload=response.read(); status=response.status
            assert status==200 and payload==local.read_bytes(),url
            served.append(url)
    result={'result':'PASS','gameweeks_validated':list(range(1,8)),
        'table_rows_checked':len(labels),'protected_files_checked':len(protected),
        'changed':changed,'forecast_artifact_id':latest['forecast_artifact_id'],
        'proposal_id':decision['proposal']['proposal_id'],'http_base':args.base_url,
        'http_paths_verified':served}
    pathlib.Path(args.receipt).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__': main()
