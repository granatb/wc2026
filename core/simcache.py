"""Content-addressed cache for per-gameweek simulation output.

A 38-gameweek season means dozens of site builds, and today every one re-runs the
full Monte Carlo. This caches the DERIVED per-player rows and per-match scoreline
distributions keyed by everything that determines them, so a copy or layout change
re-renders with no sim at all — while anything that should change the numbers
invalidates the key automatically.

The model-source fingerprint is the load-bearing part. Without it, editing a
scoring constant would silently reuse a stale artifact and publish a number that
was never recomputed. For a site whose positioning is published methodology, that
is the worst available failure mode.

Knows nothing about FPL scoring or HTTP: callers hand it inputs and an artifact.
"""

from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_HERE, "data", "fpl", "simcache")

# Sources whose CONTENT determines simulated output. Editing any of them must
# invalidate every cached artifact.
FINGERPRINT_SOURCES = [
    os.path.join(_HERE, "core", "engine_events.py"),
    os.path.join(_HERE, "core", "fpl_priors.py"),
    os.path.join(_HERE, "core", "blend.py"),
    os.path.join(_HERE, "core", "research.py"),
    os.path.join(_HERE, "games", "fpl", "model.py"),
]
# blend.py and research.py were added after review. Both are genuinely
# sim-affecting: engine_events.effective_goal_weight calls blend.blend_rate, and
# ResearchEntry.adjust applies the research overlay's hard facts and soft nudges.
# Research ENTRIES are hashed as data by cache_key, but the logic that interprets
# them lives here, so editing either file must invalidate the cache too.
#
# Deliberately NOT fingerprinted: core/odds_math.py and core/ratings.py. They only
# reach the sim through the per-match lambdas, and cache_key hashes those as
# computed VALUES — so any change to how they are derived already shows up.


def _read_source(path: str) -> str:
    """Read a source file for fingerprinting. Missing files hash as empty.

    Separated out so tests can substitute tampered content without touching disk.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def source_fingerprint() -> str:
    """SHA-256 over the concatenated content of FINGERPRINT_SOURCES."""
    h = hashlib.sha256()
    for path in FINGERPRINT_SOURCES:
        h.update(os.path.basename(path).encode())
        h.update(b"\0")
        h.update(_read_source(path).encode())
        h.update(b"\0")
    return h.hexdigest()


def _canonical(value) -> str:
    """Deterministic JSON for hashing.

    `sort_keys` makes dict iteration order irrelevant, so two runs that build the
    same inputs in a different order still hit the same key. Tuples serialise as
    lists, which is fine — we only need determinism, not round-tripping.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def cache_key(*, gameweek: int, sims: int, seed: int, lambdas: dict,
              priors: dict, research: dict, config: dict) -> str:
    """SHA-256 over every input that determines simulated output.

    lambdas:  {match_id: (lam_home, lam_away)} — the match layer.
    priors:   {player_name: tuple of prior fields} — the player layer.
    research: {player_name: whatever the overlay contributes}.
    config:   sim-affecting dials only. Do NOT pass the whole config module —
              unrelated dials (site URL, article copy) would cause spurious misses.
    """
    h = hashlib.sha256()
    for part in (gameweek, sims, seed, lambdas, priors, research, config):
        h.update(_canonical(part).encode())
        h.update(b"\0")
    h.update(source_fingerprint().encode())
    return h.hexdigest()


def _path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")


def load(key: str):
    """The cached artifact for `key`, or None on a miss.

    A corrupt or unreadable artifact is a MISS, not an error: the cost of a miss is
    re-running the sim, whereas raising would break a build over a recoverable
    problem.
    """
    path = _path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def store(key: str, artifact: dict, meta: dict | None = None) -> str:
    """Persist `artifact` under `key`. Returns the path written."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    payload = dict(artifact)
    payload["meta"] = dict(meta or {})
    payload["meta"]["fingerprint"] = source_fingerprint()
    path = _path(key)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    return path


def artifacts_for(gameweek: int) -> list:
    """Cache keys of every stored artifact whose meta says it is this gameweek's.

    Preflight uses this to tell an EXPECTED miss (nothing built for this gameweek
    yet) from an UNEXPECTED one (artifacts exist, but an input or the model source
    changed since) — spec §9's "the sim cache missed unexpectedly" warning.

    Unreadable or meta-less files are skipped, not raised on: this is diagnostics,
    and it must never be the reason a build dies.
    """
    if not os.path.isdir(CACHE_DIR):
        return []
    out = []
    for fname in os.listdir(CACHE_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(CACHE_DIR, fname), encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError):
            continue
        if (payload.get("meta") or {}).get("gameweek") == gameweek:
            out.append(fname[:-len(".json")])
    return out
