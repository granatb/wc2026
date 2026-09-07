"""Weekly experiment operations: rehearsals, guarded freezes and retained evidence."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import fcntl
import json
from pathlib import Path

from core import forecast_archive as evidence, fpl_live
from games.fpl import experiments as ledger, forecast_providers as providers


def read(path):
    return json.loads(Path(path).read_text())


def sha_key(key):
    if not isinstance(key, str) or len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
        raise ValueError('invalid evidence filename')
    return key


@contextmanager
def operation_lock(root):
    """Kernel releases the lock after crashes; no stale PID lock to bypass."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root/'.fpl-season.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('another season operation is running')
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def status(protocol, bootstrap, root, gw, now=None):
    now = evidence.utc(now or datetime.now(timezone.utc))
    records = ledger.load_history(root)
    report = ledger.report_from_directory(protocol, root)
    lock = evidence.deadline(bootstrap, gw)
    opens = lock-timedelta(hours=24)
    frozen = next((r for r in records if r['gameweek'] == gw), None)
    if frozen:
        state = 'graded' if gw in report['gameweeks'] else 'awaiting_final_results'
    elif records and gw != records[-1]['gameweek']+1:
        state = 'history_gap'
    elif now >= lock:
        state = 'missed_deadline'
    elif now < opens:
        state = 'rehearsal_only'
    else:
        state = 'ready_to_refresh_and_freeze'
    return dict(gameweek=gw, state=state, observed_at=now.isoformat(),
                deadline=lock.isoformat(), freeze_window_opens=opens.isoformat(),
                forecast_artifact_id=frozen['artifact_id'] if frozen else None,
                note='Read-only status from supplied bootstrap; refresh official data before freezing.')


def rehearse(protocol, context, trained, seed_state, root, work, sims=5000, now=None,
             build_fn=providers.build_boards):
    now = evidence.utc(now or datetime.now(timezone.utc))
    records = ledger.load_history(root)
    previous = records[-1] if records else None
    boot, gw = context['bootstrap'], context['gameweek']
    if previous and gw != previous['gameweek']+1:
        raise ValueError('cannot rehearse an enrolled week or skip a gameweek')
    boards, source = build_fn(context, trained, sims=sims, now=now)
    if previous:
        seed = None
    else:
        resolved = fpl_live.resolve_squad(seed_state, boot)
        seed = [resolved[p['name']]['id'] for p in seed_state['squad']]
    submissions = {}
    for arm in protocol['arms']:
        providers.verify_board_source(arm, boards[arm], source)
        old = previous['arms'][arm] if previous else None
        decision = ledger.choose_decision(old['squad_ids'] if old else seed,
            boards[arm]['predictions'], boot, old['portfolio'] if old else None)
        submissions[arm] = dict(boards[arm], **decision, interventions=[])
    draft = ledger.prepare_week(protocol, gw, boot, submissions, previous, now=now, fixtures=context['fixtures'])
    run = providers.seal(dict(schema_version=1, gameweek=gw, created_at=now.isoformat(),
        protocol_sha256=evidence.digest(protocol), previous_artifact_id=draft['previous_artifact_id'],
        source_artifact_id=source['artifact_id'], submissions=submissions))
    folder = Path(work)/'runs'/f'gw{gw}'/run['artifact_id']
    evidence.atomic_json(folder/'sources'/f"{source['artifact_id']}.json", source)
    evidence.atomic_json(folder/'run.json', run)
    names = {p['id']:p['web_name'] for p in boot['elements']}
    summary = dict(state='rehearsal_not_frozen', gameweek=gw, run=str(folder/'run.json'),
        source_artifact_id=source['artifact_id'], players=len(boot['elements']),
        captains={arm:names[sub['captain_id']] for arm,sub in submissions.items()})
    evidence.atomic_json(folder/'summary.json', summary)
    return summary


def load_run(path):
    path = Path(path)
    run = read(path)
    providers.verify(run)
    source = read(path.parent/'sources'/f"{sha_key(run['source_artifact_id'])}.json")
    providers.verify(source)
    if source['context']['gameweek'] != run['gameweek']:
        raise ValueError('run gameweek differs from source')
    for arm, board in run['submissions'].items():
        providers.verify_board_source(arm, board, source)
    return run, source


def freeze_run(protocol, run_path, root, work, now=None):
    """Retry-safe enrollment in the last 24h. Backup is complete before enrollment."""
    now = evidence.utc(now or datetime.now(timezone.utc))
    run, source = load_run(run_path)
    if run['protocol_sha256'] != evidence.digest(protocol):
        raise ValueError('run protocol changed; regenerate')
    ctx, gw = source['context'], run['gameweek']
    path = Path(root)/f'gw{gw}.json'
    if path.exists():
        existing = ledger.read_week(path)
        if (existing['protocol_sha256'] != run['protocol_sha256'] or
            any({k:v for k,v in sub.items() if k != 'portfolio'} != run['submissions'].get(arm)
                for arm,sub in existing['arms'].items())):
            raise ValueError('different run already frozen; cannot replace it')
        return dict(state='already_frozen', **ledger.public_receipt(existing))
    lock = evidence.deadline(ctx['bootstrap'], gw)
    if not lock-timedelta(hours=24) <= now < lock:
        raise ValueError('freeze only in the final 24 hours before the official deadline')
    for key in ('bootstrap', 'all_fixtures'):
        evidence.require_fresh(ctx[key], ctx['receipts'][key], now=now)
    for captured in (ctx['captured_at'], ctx['odds']['captured_at'], ctx['ffiq']['generated_at']):
        if not 0 <= (now-evidence.utc(captured)).total_seconds() <= 86400:
            raise ValueError('provider source expired since rehearsal; refresh')
    records = ledger.load_history(root)
    previous = records[-1] if records else None
    if run['previous_artifact_id'] != (previous['artifact_id'] if previous else None):
        raise ValueError('history changed since rehearsal; regenerate')
    record = ledger.prepare_week(protocol, gw, ctx['bootstrap'], run['submissions'], previous,
                                  now=now, fixtures=ctx['fixtures'])
    record = providers.seal(record)
    bundle = providers.seal(dict(schema_version=1, forecast=record, source=source, run=run))
    evidence.atomic_json(Path(work)/'backups'/f"{record['artifact_id']}.json", bundle)
    evidence.atomic_json(Path(root)/'sources'/f"{source['artifact_id']}.json", source)
    frozen = ledger.write_week(root, record, now=now)
    return dict(state='frozen', **ledger.public_receipt(frozen))


def verify_backup(path):
    bundle = read(path)
    providers.verify(bundle)
    for key in ('forecast', 'source', 'run'):
        providers.verify(bundle[key])
    record, run, source = bundle['forecast'], bundle['run'], bundle['source']
    if evidence.utc(record['captured_at']) >= evidence.utc(record['deadline']):
        raise ValueError('late backup is not an eligible forecast')
    if (record['gameweek'] != run['gameweek'] or
        record['protocol_sha256'] != run['protocol_sha256']):
        raise ValueError('backup contains different runs')
    for arm, sub in record['arms'].items():
        providers.verify_board_source(arm, sub, source)
        if {k:v for k,v in sub.items() if k != 'portfolio'} != run['submissions'][arm]:
            raise ValueError('backup squad differs from run')
    return dict(state='backup_verified', **ledger.public_receipt(record))
