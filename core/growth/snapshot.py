"""Committed per-gameweek snapshots, so a peak has a previous peak to beat.

docs/STRATEGY.md §1: "Each peak deposits permanent residue that raises the floor
for the next peak." A report that only prints this week's numbers cannot answer
whether the floor rose, so every run writes its metrics to
evmax/assets/growth/gw{N}.json and the next run reads the one below it. These
files are COMMITTED, mirroring evmax/assets/projections/ -- a delta needs the
previous peak to still exist on a fresh checkout, and data/ is gitignored.

Comparisons are peak-over-peak, i.e. gameweek-over-gameweek, never
newest-file-over-file. `previous()` therefore picks the highest gameweek strictly
below the one asked for, by parsed integer: gw10 compares against gw9 even when
gw9 was written first, and a lexical filename sort ("gw10" < "gw2") would get
this wrong.

Every read here tolerates a corrupt or half-written file by skipping it. A growth
report is diagnostics and must never be the reason something dies.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SNAPSHOT_DIR = os.path.join(_HERE, "evmax", "assets", "growth")

FILENAME = "gw{gameweek}.json"
_FILENAME_RE = re.compile(r"^gw(\d+)\.json$")


def _dir(directory: str | None) -> str:
    return SNAPSHOT_DIR if directory is None else directory


def path_for(gameweek: int, directory: str | None = None) -> str:
    return os.path.join(_dir(directory), FILENAME.format(gameweek=int(gameweek)))


def write(gameweek: int, data: dict, directory: str | None = None) -> str:
    """Persist this gameweek's metrics and return the path written.

    `data` is a flat mapping of metric name -> number; `delta` compares two of
    them. Wrapped in a record so a later reader can tell which gameweek and when.
    """
    target = _dir(directory)
    os.makedirs(target, exist_ok=True)
    record = {
        "gameweek": int(gameweek),
        "written_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data": dict(data or {}),
    }
    path = path_for(gameweek, directory)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def read(gameweek: int, directory: str | None = None) -> dict | None:
    """The snapshot record for this gameweek, or None if absent or unreadable."""
    return _load(path_for(gameweek, directory))


def _load(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            record = json.load(fh)
    except (OSError, ValueError):
        # Missing, unreadable, or corrupt -- all the same to a caller that just
        # wants a baseline if one happens to exist.
        return None
    if not isinstance(record, dict) or not isinstance(record.get("data"), dict):
        return None
    return record


def gameweeks(directory: str | None = None) -> list[int]:
    """Every gameweek with a readable snapshot on disk, ascending."""
    target = _dir(directory)
    try:
        names = os.listdir(target)
    except OSError:
        return []
    found = []
    for name in names:
        match = _FILENAME_RE.match(name)
        if match and _load(os.path.join(target, name)) is not None:
            found.append(int(match.group(1)))
    return sorted(found)


def previous(gameweek: int, directory: str | None = None) -> dict | None:
    """The snapshot for the highest gameweek strictly BELOW this one, or None.

    Not the most recently written file and not filename order: gw2's baseline is
    gw1 even if gw10 was written yesterday.
    """
    below = [gw for gw in gameweeks(directory) if gw < int(gameweek)]
    if not below:
        return None
    return read(max(below), directory)


def delta(current: dict, previous: dict | None) -> dict | None:
    """Per-metric change from `previous` to `current`, or None with no baseline.

    None means "there is no previous peak", which the report must say in words.
    Returning zeros instead would claim flat growth, which is a different and
    false statement.

    `pct` is None when the baseline was zero: growth from nothing has no
    percentage, and it must not be rendered as 0% either.
    """
    if previous is None:
        return None
    prev_data, curr_data = _metrics(previous), _metrics(current)
    if prev_data is None or curr_data is None:
        return None

    out: dict = {}
    for key in sorted(set(curr_data) | set(prev_data)):
        now, before = curr_data.get(key), prev_data.get(key)
        if not _is_number(now) or not _is_number(before):
            continue
        change = now - before
        out[key] = {
            "current": now,
            "previous": before,
            "delta": change,
            "pct": round(change / before * 100.0, 1) if before else None,
        }
    return out


def _metrics(value) -> dict | None:
    """Accept either a snapshot record from `read` or a bare metrics mapping."""
    if not isinstance(value, dict):
        return None
    if "gameweek" in value and isinstance(value.get("data"), dict):
        return value["data"]
    return value


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
