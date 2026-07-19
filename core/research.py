"""Research / memory layer loader.

Reads markdown notes under research/{teams,players,matches}/ that carry a YAML-ish
frontmatter block, and applies them to the engine's base numbers via the blend rules
in core/blend.py. Hard facts (out/suspended, or an absolute start_prob_override) bypass
the weight; soft `lambda_multiplier` adjustments scale with the active game's `w`.

A deliberately small frontmatter parser is used so the project needs no third-party
YAML dependency. Supported frontmatter:

    ---
    entity: player
    name: Erling Haaland
    status: nailed            # nailed | rotation_risk | doubtful | out | suspended
    start_prob_override: null # float to pin start prob absolutely, else null
    lambda_multiplier: 1.0    # soft attack nudge (1.0 = neutral)
    sources:
      - https://...
    updated: 2026-06-18
    ---
    prose...
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

from . import blend

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESEARCH_DIR = os.path.join(_HERE, "research")


def _coerce(v: str):
    v = v.strip()
    if v in ("null", "~", ""):
        return None
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    try:
        return float(v) if ("." in v or "e" in v.lower()) else int(v)
    except ValueError:
        return v.strip().strip('"').strip("'")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (meta, body). Supports scalars and simple `- ` lists."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta: dict = {}
    i, cur_list_key = 1, None
    while i < len(lines) and lines[i].strip() != "---":
        line = lines[i]
        if line.strip().startswith("- ") and cur_list_key:
            meta[cur_list_key].append(_coerce(line.strip()[2:]))
        elif ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            if val.strip() == "":
                meta[key], cur_list_key = [], key
            else:
                meta[key], cur_list_key = _coerce(val), None
        i += 1
    body = "\n".join(lines[i + 1:]) if i < len(lines) else ""
    return meta, body


@dataclass
class ResearchEntry:
    name: str
    entity: str = "player"
    status: str | None = None
    start_prob_override: float | None = None
    lambda_multiplier: float = 1.0
    sources: list = field(default_factory=list)
    updated: str | None = None
    round: int | None = None      # None = applies to every round; else only that round

    @classmethod
    def from_meta(cls, meta: dict) -> "ResearchEntry":
        rnd = meta.get("round")
        return cls(
            name=meta.get("name", ""),
            entity=meta.get("entity", "player"),
            status=meta.get("status"),
            start_prob_override=meta.get("start_prob_override"),
            lambda_multiplier=meta.get("lambda_multiplier", 1.0) or 1.0,
            sources=meta.get("sources", []) or [],
            updated=meta.get("updated"),
            round=int(rnd) if rnd is not None else None,
        )

    def adjust(self, base_rate: float, base_start: float, w: float) -> tuple[float, float]:
        """Apply this entry to a player's base (goal rate, start prob) under weight w."""
        # Hard facts first — absolute, ignore w.
        rate, start = blend.apply_status(self.status, base_rate=base_rate,
                                         base_start=base_start, w=w)
        if self.status in blend.HARD_OUT_STATUSES:
            return rate, start
        if self.start_prob_override is not None:
            start = self.start_prob_override
        # Soft attack nudge scales with w.
        rate = blend.blend_lambda(rate, multiplier=self.lambda_multiplier, w=w)
        return rate, start


def load_entries(kind: str = "players", fantasy_round: int | None = None) -> dict:
    """Load research/<kind>/*.md keyed by `name`. Skips files starting with `_`.

    If `fantasy_round` is given, notes pinned to a *different* round are dropped, so
    an R3-specific rotation flag never leaks into an R2 (or knockout) simulation.
    Notes with no `round:` field apply to every round.

    Sorted glob so the winner of a same-name collision (see find_duplicate_names)
    is at least stable across machines/runs -- filesystem enumeration order is
    otherwise arbitrary, which previously meant which of several round-pinned
    Nico Williams notes was "active" depended on directory listing order.
    """
    out: dict[str, ResearchEntry] = {}
    pattern = os.path.join(RESEARCH_DIR, kind, "*.md")
    for path in sorted(glob.glob(pattern)):
        if os.path.basename(path).startswith("_"):
            continue
        with open(path, encoding="utf-8") as fh:
            meta, _ = parse_frontmatter(fh.read())
        if not meta.get("name"):
            continue
        entry = ResearchEntry.from_meta(meta)
        if fantasy_round is not None and entry.round is not None \
                and entry.round != fantasy_round:
            continue
        out[meta["name"]] = entry
    return out


def find_duplicate_names(kind: str = "players") -> dict:
    """{name: [file paths]} for every name backed by more than one active
    (non-underscore) note file. load_entries() silently lets the LAST file
    in sorted order win a same-name collision -- fine for an intentional
    "supersedes" pair that agrees, dangerous when the files disagree (found
    2026-07-19: 4 separate Nico Williams files pinned to rounds 4/6/6/7 with
    different status/start_prob -- only one was ever actually live, and
    which one was down to which file the OS listed last)."""
    by_name: dict[str, list] = {}
    pattern = os.path.join(RESEARCH_DIR, kind, "*.md")
    for path in sorted(glob.glob(pattern)):
        if os.path.basename(path).startswith("_"):
            continue
        with open(path, encoding="utf-8") as fh:
            meta, _ = parse_frontmatter(fh.read())
        name = meta.get("name")
        if not name:
            continue
        by_name.setdefault(name, []).append(path)
    return {name: paths for name, paths in by_name.items() if len(paths) > 1}
