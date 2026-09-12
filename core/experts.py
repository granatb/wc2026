"""The weekly expert scan: what the public FPL sources recommended, with links.

One JSON file per gameweek under research/experts/gw{N}.json, written by hand
in the pre-deadline session (owner decision 2026-09-12: a weekly step and a
published article). Derived-only: we record WHO each source picked and link
to them. We never republish their projections or paywalled content.

    python3 -m core.experts --gw 4        # validate and print the table
"""
from __future__ import annotations

import argparse
import json
import os
import unicodedata
from collections import Counter

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "research", "experts")
REQUIRED = ("key", "name", "url", "published")
LIST_FIELDS = ("transfers_in", "transfers_out")


def path_for(gameweek: int) -> str:
    return os.path.join(ROOT, f"gw{gameweek}.json")


def validate(data: dict) -> dict:
    """Raise ValueError on a malformed scan; return it unchanged otherwise."""
    if not isinstance(data, dict) or not isinstance(data.get("gameweek"), int):
        raise ValueError("expert scan needs an integer 'gameweek'")
    if not data.get("checked_at"):
        raise ValueError("expert scan needs 'checked_at' (when the sources were read)")
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("expert scan needs a non-empty 'sources' list")
    keys = set()
    for s in sources:
        missing = [k for k in REQUIRED if not s.get(k)]
        if missing:
            raise ValueError(f"source {s.get('key') or s.get('name')!r} lacks {missing}")
        if not str(s["url"]).startswith("http"):
            raise ValueError(f"source {s['key']!r}: url must be a link")
        if s["key"] in keys:
            raise ValueError(f"duplicate source key {s['key']!r}")
        keys.add(s["key"])
        for f in LIST_FIELDS:
            if s.get(f) is not None and not isinstance(s[f], list):
                raise ValueError(f"source {s['key']!r}: {f} must be a list")
    return data


def load(gameweek: int) -> dict | None:
    """The validated scan for `gameweek`, or None when no file exists."""
    p = path_for(gameweek)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return validate(json.load(fh))


def _norm(name: str) -> str:
    return unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()


def same_player(a: str, b: str) -> bool:
    """Loose name match across the sources' spellings and our disambiguated
    names: 'Palmer' matches 'Cole Palmer', 'Bruno Fernandes' matches
    'B.Fernandes' on the surname."""
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    return a.split(".")[-1].split()[-1] == b.split(".")[-1].split()[-1]


def tallies(data: dict) -> dict:
    """Counts across sources: captain votes, transfers in, transfers out, and
    which sources named a chip."""
    captains, ins, outs = Counter(), Counter(), Counter()
    chips = []
    for s in data["sources"]:
        if s.get("captain"):
            captains[s["captain"]] += 1
        for n in s.get("transfers_in") or []:
            ins[n] += 1
        for n in s.get("transfers_out") or []:
            outs[n] += 1
        if s.get("chip"):
            chips.append((s["name"], s["chip"]))
    return {"captains": captains.most_common(), "transfers_in": ins.most_common(),
            "transfers_out": outs.most_common(), "chips": chips,
            "n_sources": len(data["sources"])}


def compare_with_model(data: dict, our: dict) -> dict:
    """Where the sources and our squad agree and split.

    our: {"captain": name, "squad": [names], "chip": {...}|None}.
    Returns {"captain_agreement": bool|None, "top_captain": name|None,
             "they_buy_we_lack": [...], "they_sell_we_hold": [...]}"""
    t = tallies(data)
    squad = our.get("squad") or []
    top_captain = t["captains"][0][0] if t["captains"] else None
    agreement = (same_player(top_captain, our.get("captain", "")) if top_captain else None)
    they_buy = [n for n, _ in t["transfers_in"] if not any(same_player(n, q) for q in squad)]
    they_sell = [n for n, _ in t["transfers_out"] if any(same_player(n, q) for q in squad)]
    return {"captain_agreement": agreement, "top_captain": top_captain,
            "they_buy_we_lack": they_buy, "they_sell_we_hold": they_sell}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gw", type=int, required=True)
    args = ap.parse_args(argv)
    data = load(args.gw)
    if data is None:
        print(f"no scan: {path_for(args.gw)}")
        return 1
    t = tallies(data)
    print(f"GW{args.gw} expert scan — {t['n_sources']} sources, checked {data['checked_at']}")
    for s in data["sources"]:
        print(f"  {s['name']:44} C {s.get('captain') or '—':14} "
              f"in {', '.join(s.get('transfers_in') or []) or '—'}")
    print("captain votes:", t["captains"])
    print("transfers in:", t["transfers_in"][:6])
    print("transfers out:", t["transfers_out"][:6])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
