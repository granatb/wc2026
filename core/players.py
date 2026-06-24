"""Single source of truth for player DATA — data/players.json.

Holds team, positions, FIFA + Holdet prices, ownership, status (the editable facts).
Model shares (goal/assist/start) stay in core/ratings.py. Everything else (the app,
the probe/optimiser price lookups) resolves player names through here, so a name used
in a game's state.json ("F. Wirtz") maps to the canonical record ("Florian Wirtz").
"""

from __future__ import annotations

import json
import os
import unicodedata

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "data", "players.json")


def _parts(name: str):
    s = "".join(c for c in unicodedata.normalize("NFD", name)
                if unicodedata.category(c) != "Mn")
    toks = [t for t in "".join(ch if ch.isalpha() else " " for ch in s.lower()).split()
            if t not in ("jr", "junior", "jnr")]
    if not toks:
        return ("", "")
    return (toks[0][0] if len(toks) > 1 else "", toks[-1])


def name_match(a: str, b: str) -> bool:
    """(surname + first-initial) match — joins short/full name variants safely."""
    fa, sa = _parts(a)
    fb, sb = _parts(b)
    return sa == sb and (fa == "" or fb == "" or fa == fb)


_CACHE: dict = {}


def load() -> list:
    if "recs" not in _CACHE:
        _CACHE["recs"] = (json.load(open(_PATH, encoding="utf-8"))["players"]
                          if os.path.exists(_PATH) else [])
    return _CACHE["recs"]


def save(records: list) -> None:
    json.dump({"_comment": "Single source of truth for players (DATA only) — "
               "auto-synced from FIFA + Holdet APIs by build_players.py.",
               "players": records}, open(_PATH, "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    _CACHE.clear()


def _index() -> dict:
    if "idx" not in _CACHE:
        idx = {}
        for r in load():
            for n in [r["name"]] + r.get("aliases", []):
                idx.setdefault(n, r)
        _CACHE["idx"] = idx
    return _CACHE["idx"]


def resolve(name: str) -> dict | None:
    """Canonical record for any name/alias. Exact-index first, then fuzzy fallback."""
    hit = _index().get(name)
    if hit:
        return hit
    for r in load():
        if name_match(name, r["name"]) or any(name_match(name, a) for a in r.get("aliases", [])):
            return r
    return None


def holdet_price(name: str):
    r = resolve(name)
    return r["holdet_price"] if r else None


def fifa_price(name: str):
    r = resolve(name)
    return r["fifa_price"] if r else None


def ownership(name: str):
    r = resolve(name)
    return r["ownership"] if r else None


def holdet_ownership(name: str):
    r = resolve(name)
    return r.get("holdet_ownership") if r else None
