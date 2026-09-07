"""Receipt-backed official player fixture histories; bounded, resumable collection."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from core import fpl_api, forecast_archive as evidence


def collect(bootstrap, gameweek, cache, fetch=fpl_api.fetch_element_summary,
            clock=lambda: datetime.now(timezone.utc), workers=3, delay=.4, progress=None):
    """Reuse only fresh receipts for this season. A failed fetch leaves reusable successes."""
    if not 1 <= workers <= 3:
        raise ValueError('one to three collection workers required')
    season = evidence.deadline(bootstrap, 1).isoformat()
    lock = evidence.deadline(bootstrap, gameweek)
    if evidence.utc(clock()) >= lock:
        raise ValueError('deadline passed before history collection')
    ids = [p['id'] for p in bootstrap['elements']]
    if any(type(pid) is not int or pid <= 0 for pid in ids):
        raise ValueError('positive integer player IDs required')
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate player IDs')
    folder = Path(cache)/evidence.digest(season)
    folder.mkdir(parents=True, exist_ok=True)
    def get(pid):
        path = folder/f'{pid}.json'
        if path.exists():
            record = json.loads(path.read_text())
            try:
                validate(record, pid, season, clock())
                return record
            except (ValueError, KeyError):
                pass
        time.sleep(delay)
        payload = fetch(pid)
        if not isinstance(payload, dict) or not isinstance(payload.get('history'), list):
            raise ValueError(f'player {pid}: missing fixture history')
        record = dict(player_id=pid, season=season, url=fpl_api.ELEMENT_SUMMARY.format(element_id=pid),
            payload=payload, receipt=dict(recorded_at=evidence.utc(clock()).isoformat(),
                                         payload_sha256=evidence.digest(payload)))
        validate(record, pid, season, clock())
        evidence.atomic_json(path, record)
        return record
    records = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending = [executor.submit(get, pid) for pid in ids]
        try:
            for future in as_completed(pending):
                records.append(future.result())
                if progress and (len(records) % 50 == 0 or len(records) == len(ids)):
                    progress(len(records), len(ids))
        except Exception:
            for future in pending:
                future.cancel()
            raise
    now = evidence.utc(clock())
    if now >= lock:
        raise ValueError('deadline passed during history collection')
    for record in records:
        validate(record, record['player_id'], season, now)
    return dict(schema_version=1, gameweek=gameweek, season=season, captured_at=now.isoformat(),
                bootstrap_sha256=evidence.digest(bootstrap),
                players=sorted(records, key=lambda r:r['player_id']))


def validate(record, pid, season, now):
    if (record['player_id'] != pid or record['season'] != season or
        record['url'] != fpl_api.ELEMENT_SUMMARY.format(element_id=pid)):
        raise ValueError('history receipt identity mismatch')
    evidence.require_fresh(record['payload'], record['receipt'], now=now)
    if any(r.get('element') != pid for r in record['payload']['history']):
        raise ValueError('history contains a different player')
