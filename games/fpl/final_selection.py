"""Dated team-result corrections backed by a published pre-deadline selection.

Player forecasts and their original grading receipts remain immutable. Each
correction binds that archive, the earlier selection article and final results.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path

from core import forecast_archive, fpl_live
from games.fpl import publication_decision

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / 'evmax/assets/final-selections'


def replay(state: dict, results: dict, archive: dict) -> dict:
    """Apply official captain and automatic-substitution rules to the selection."""
    forecast_archive.require_final(results)
    return fpl_live.grade_squad(state, results['live'], results['fixtures'],
                               archive['bootstrap'])


def validate(record: dict, grade: dict, archive: dict) -> dict:
    """Validate provenance and independently replay both projection and result."""
    if (record['gameweek'] != grade['gameweek'] or
            record['gameweek'] != archive['gameweek'] or
            record['forecast_sha256'] != archive['artifact_id'] or
            record['forecast_sha256'] != grade['forecast_sha256'] or
            record['baseline_grade_sha256'] != forecast_archive.digest(grade) or
            record['results_sha256'] != grade['results_sha256']):
        raise ValueError('final selection does not match the original forecast and grade')
    published = forecast_archive.utc(record['published_at'])
    if not (forecast_archive.utc(archive['captured_at']) < published <
            forecast_archive.utc(archive['deadline']) <
            forecast_archive.utc(record['recorded_at'])):
        raise ValueError('selection must precede the deadline and correction must be dated later')
    source = (REPO / record['source_path']).resolve()
    if (not source.is_relative_to(REPO) or
            hashlib.sha256(source.read_bytes()).hexdigest() != record['source_sha256']):
        raise ValueError('pre-deadline selection source changed')
    state = record['state']
    publication_decision._selection(state['squad'], state=True)
    if state.get('active_chip'):
        raise ValueError('this selection correction supports ordinary captain scoring only')
    rows = {row['player_id']: row for row in archive['rows']}
    counts = Counter()
    squad_counts = Counter()
    clubs = Counter()
    projected = 0.0
    graded = {row['name']: row['realized'] for row in grade['players']}
    stats = {row['id']: row['stats'] for row in record['results']['live']['elements']}
    for player in state['squad']:
        row = rows.get(player['player_id'])
        if row is None or row['position'] != player['position']:
            raise ValueError('selection player is absent or has the wrong position')
        squad_counts[row['position']] += 1
        clubs[row['team']] += 1
        if player['is_starter']:
            counts[row['position']] += 1
            projected += row['x_points'] * (1 + int(player['is_captain']))
        if (player['player_id'] not in stats or
                stats[player['player_id']]['total_points'] != graded[row['name']]):
            raise ValueError('selection results disagree with original player grades')
    if (squad_counts != {'GK': 2, 'DEF': 5, 'MID': 5, 'FWD': 3} or
            max(clubs.values()) > 3 or
            any(not fpl_live.XI_MIN[p] <= counts[p] <= fpl_live.XI_MAX[p]
                for p in fpl_live.XI_MIN)):
        raise ValueError('illegal final squad or formation')
    results = record['results']
    if (results['gameweek'] != record['gameweek'] or
            results['fetched_at'] != grade['results_fetched_at'] or
            forecast_archive.digest(results) != record['results_extract_sha256']):
        raise ValueError('final results extract does not match its receipt')
    scoring = replay(state, results, archive)
    if (round(projected, 2) != record['projected'] or
            scoring['total_so_far'] != record['realized_official'] or
            scoring != record['scoring']):
        raise ValueError('final selection projection or scoring replay disagrees')
    return record


def load(gameweek: int, grade: dict) -> dict | None:
    """Read an optional result correction while retaining the original grade."""
    path = ROOT / f'gw{gameweek}.json'
    if not path.exists():
        return None
    return validate(json.loads(path.read_text()), grade, forecast_archive.load(gameweek))
