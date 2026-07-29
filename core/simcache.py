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
    os.path.join(_HERE, "games", "fpl", "model.py"),
]


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
