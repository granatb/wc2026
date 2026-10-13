"""Reviewable publication decisions. No account access, transfers or model fitting.

A proposal binds validated squad states and the exact forecast context. Acceptance
is an explicit local operator step, never a side effect of building a site.
"""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from core import forecast_archive as evidence
from games.fpl import transfers

ROOT = Path(__file__).resolve().parent/'decisions'
START_GAMEWEEK = 7


def _now(now):
    return evidence.utc(now or datetime.now(timezone.utc))


def context_digest(context):
    # Live PMFs have integer keys; JSON archives have strings. Match freeze's
    # JSON roundtrip before hashing so dry/production/archive agree exactly.
    return evidence.digest(json.loads(json.dumps(context,allow_nan=False)))


def forecast_context(rows,matches,sims,bootstrap,fixtures,odds,source_fingerprint):
    return dict(rows=rows,matches=matches,sims=sims,
        bootstrap_sha256=evidence.digest(bootstrap),fixtures_sha256=evidence.digest(fixtures),
        odds_sha256=evidence.digest(odds),source_fingerprint=source_fingerprint)


def verify_forecast(receipt,archive):
    context=forecast_context(archive['rows'],archive['matches'],archive['sims'],archive['bootstrap'],
        archive['inputs']['fixtures'],archive['inputs']['odds'],archive['source_fingerprint'])
    if receipt['proposal']['forecast_sha256']!=context_digest(context):
        raise ValueError('accepted decision disagrees with archived forecast context')


def proposal_id(proposal):
    return evidence.digest({k:v for k,v in proposal.items() if k != 'proposal_id'})


def _selection(entries, state=False):
    result=[]
    for p in entries:
        pid=p.get('player_id',p.get('id'))
        if not isinstance(pid,int):
            raise ValueError('published squad requires stable player IDs')
        starter=p.get('is_starter') if state else p.get('role')=='XI'
        result.append((pid,bool(starter),bool(p.get('is_captain')),bool(p.get('is_vice')),p.get('bench_order')))
    if (len(result)!=15 or len({r[0] for r in result})!=15 or
        sum(r[1] for r in result)!=11 or sum(r[2] for r in result)!=1 or
        sum(r[3] for r in result)!=1 or any((r[2] or r[3]) and not r[1] for r in result) or
        any(r[2] and r[3] for r in result) or
        sorted(r[4] for r in result if not r[1])!=[1,2,3,4]):
        raise ValueError('published squad roles are invalid')
    return sorted(result)


def verify_entries(states, entries):
    if set(states)!=set(entries):
        raise ValueError('published squad coverage differs from decision')
    for key,state in states.items():
        if _selection(state['squad'],True)!=_selection(entries[key]):
            raise ValueError(f'{key}: published squad differs from decision')


def _review(states, rows):
    by_id={r['player_id']:r for r in rows}
    pool={r['name']:r for r in rows}
    review={}
    for key,state in states.items():
        # Resolve disambiguated simulation names by stable ID, never surname.
        squad=[dict(p,**{k:by_id[p.get('player_id',p.get('id'))][k]
                         for k in ('name','position','team','price')}) for p in state['squad']]
        scope='One gameweek, best legal XI plus ordinary captain; excludes autosubs, vice option value, future weeks and chips.'
        if state.get('active_chip'):
            review[key]=dict(scope=scope, unavailable='Active chip: ordinary-captain comparison is inapplicable.')
            continue
        selected=sum(pool[p['name']]['x_points']*(1+int(p['is_captain'])) for p in squad if p['is_starter'])
        best=transfers.weekly_utility(squad,pool)
        options=[]
        if state.get('bank') is not None and state.get('free_transfers') is not None:
            options=transfers.recommend(dict(state,squad=squad),{0:pool},
                state['free_transfers'],state['bank'],top=5)
        review[key]=dict(scope=scope,selected_points=round(selected,2),
            current_squad_best_xi_points=round(best,2),selection_gap=round(best-selected,2),
            affordable_single_swap_options=options,
            funds_note='Uses recorded bank, purchase and market prices; options compare best XI before and after, not the selected XI.'
                if state.get('bank') is not None else 'Bank not recorded: affordable transfer alternatives unavailable.')
    return review


def prepare(gameweek, states, entries, context, bootstrap, now=None):
    if _now(now)>=evidence.deadline(bootstrap,gameweek):
        raise ValueError('decision must be prepared before the deadline')
    verify_entries(states,entries)
    body=dict(schema_version=1,gameweek=gameweek,deadline=evidence.deadline(bootstrap,gameweek).isoformat(),
        states=copy.deepcopy(states),forecast_sha256=context_digest(context),
        review=_review(states,context['rows']),account_submission='unverified')
    return dict(body,proposal_id=proposal_id(body))


def accept(proposal, expected_id, accepted_by, rationale, now=None):
    if (proposal.get('proposal_id')!=proposal_id(proposal) or expected_id!=proposal['proposal_id']):
        raise ValueError('reviewed proposal ID does not match')
    if _now(now)>=evidence.utc(proposal['deadline']):
        raise ValueError('acceptance must precede the deadline')
    if not accepted_by.strip() or not rationale.strip():
        raise ValueError('operator and decision rationale are required')
    if proposal.get('account_submission')!='unverified':
        raise ValueError('publication acceptance cannot confirm account submission')
    return dict(schema_version=1,status='accepted_for_publication',proposal=copy.deepcopy(proposal),
        accepted_at=_now(now).isoformat(),accepted_by=accepted_by.strip(),rationale=rationale.strip(),
        account_submission='unverified')


def require_accepted(receipt, current, now=None):
    if not receipt or receipt.get('status')!='accepted_for_publication':
        raise ValueError('accepted publication decision missing; review the dry-build proposal first')
    saved=receipt.get('proposal') or {}
    if (saved.get('proposal_id')!=proposal_id(saved) or current.get('proposal_id')!=proposal_id(current)
        or saved!=current):
        raise ValueError('accepted decision differs from current squad or forecast; review again')
    stamp=evidence.utc(receipt['accepted_at'])
    if not stamp<=_now(now)<evidence.utc(saved['deadline']):
        raise ValueError('decision acceptance is late or future-dated')
    if not receipt.get('accepted_by','').strip() or not receipt.get('rationale','').strip():
        raise ValueError('decision acceptance lacks an operator or rationale')
    if receipt.get('account_submission')!='unverified' or saved.get('account_submission')!='unverified':
        raise ValueError('account submission must remain separate and unverified')


def receipt_path(proposal, root=ROOT):
    return Path(root)/f"gw{proposal['gameweek']}"/f"{proposal['proposal_id']}.json"


def save_accepted(path, receipt):
    require_accepted(receipt,receipt['proposal'],now=receipt['accepted_at'])
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive creation preserves every earlier acceptance, including revisions.
    with path.open('x',encoding='utf-8') as handle:
        json.dump(receipt,handle,ensure_ascii=False,indent=2,allow_nan=False)
        handle.write('\n')


def load_accepted(proposal):
    path=receipt_path(proposal)
    receipt=json.loads(path.read_text()) if path.exists() else None
    require_accepted(receipt,proposal)
    return receipt
