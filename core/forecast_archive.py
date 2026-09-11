"""Versioned pre-deadline evidence. No simulation and no network access."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "evmax/assets/forecasts"
MODEL_VERSION = "2026-09-07.1"


def utc(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if dt is None or dt.tzinfo is None:
        raise ValueError("a timezone-aware timestamp is required")
    return dt.astimezone(timezone.utc)


def deadline(bootstrap, gw):
    event = next((e for e in bootstrap.get("events", []) if e["id"] == gw), None)
    if not event or not event.get("deadline_time"):
        raise ValueError(f"GW{gw}: deadline unavailable; cannot prove forecast eligibility")
    return utc(event["deadline_time"])


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", delete=False) as fh:
            tmp = Path(fh.name)
            json.dump(payload, fh, ensure_ascii=False, indent=2, allow_nan=False)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def freeze(gw, payload, bootstrap, now=None):
    now = utc(now or datetime.now(timezone.utc))
    lock = deadline(bootstrap, gw)
    if now >= lock:
        raise ValueError(f"GW{gw}: forecast deadline passed")
    body = dict(payload, gameweek=gw, captured_at=now.isoformat(),
                deadline=lock.isoformat(), model_version=MODEL_VERSION,
                schema_version=1)
    # Canonicalise through a JSON round trip BEFORE digesting. The rows carry
    # integer-keyed dicts (the points distributions); json sorts those keys
    # numerically on the way out and as strings on the way back in, so a
    # digest of the live objects never matched the digest of the file and
    # load() rejected every real freeze (found on the first production
    # freeze, GW4, 2026-09-11).
    body = json.loads(json.dumps(body, ensure_ascii=False, allow_nan=False))
    key = digest(body)
    record = dict(body, artifact_id=key)
    folder = ROOT / f"gw{gw}"
    atomic_json(folder / f"{key}.json", record)
    atomic_json(folder / "latest.json", {"artifact_id": key})
    return record


def load(gw):
    folder = ROOT / f"gw{gw}"
    if not (folder / "latest.json").exists():
        return None
    key = json.loads((folder / "latest.json").read_text())["artifact_id"]
    if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        raise ValueError("invalid artifact ID")
    record = json.loads((folder / f"{key}.json").read_text())
    body = {k: v for k, v in record.items() if k != "artifact_id"}
    if record.get("artifact_id") != key or digest(body) != key or record["gameweek"] != gw:
        raise ValueError("forecast archive checksum/gameweek mismatch")
    if utc(record["captured_at"]) >= utc(record["deadline"]):
        raise ValueError("late forecast is ineligible")
    return record


def state_from_envelope(envelope):
    """Legacy migration: reconstruct only facts actually present in the article."""
    entries = envelope.get("entries", [])
    if len(entries) != 15 or not all(e.get("role") in ("XI", "Bench") for e in entries):
        raise ValueError("a complete frozen squad is required for official grading")
    entries = [dict(e) for e in entries]
    for entry in entries:
        if envelope.get("gameweek") == 1 and (entry.get("name"), entry.get("team")) == ("Sangaré", "NFO"):
            entry["player_id"] = 488  # audited GW1 identity amendment; Ibrahim Sangaré
    return {
        "team_name": envelope.get("squad", {}).get("team_name", "Archived squad"),
        "squad": [dict(e, is_starter=e["role"] == "XI",
                       is_captain=bool(e.get("is_captain")),
                       is_vice=bool(e.get("is_vice"))) for e in entries],
        "aliases": {},
    }


def require_final(payload):
    fixtures = payload.get("fixtures") or []
    if not fixtures or not all(f.get("finished") for f in fixtures):
        raise ValueError("all gameweek fixtures must be final before banking grades")
    if not (payload.get("live") or {}).get("elements"):
        raise ValueError("final player results are missing")


def require_fresh(payload, metadata, now=None, max_age_hours=24):
    """A cache write date alone is insufficient: bind its receipt to its bytes."""
    now = utc(now or datetime.now(timezone.utc))
    if not metadata or metadata.get("payload_sha256") != digest(payload):
        raise ValueError("input observation missing or mismatched; refresh before publication")
    age = (now - utc(metadata["recorded_at"])).total_seconds()
    if not 0 <= age <= max_age_hours * 3600:
        raise ValueError(f"input older than {max_age_hours}h or dated in the future; refresh before publication")
