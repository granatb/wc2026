#!/usr/bin/env python3
"""Turn the owner's hand-written lineup shorthand into research/players/ notes.

THIS SCRIPT MAKES NO NETWORK CALL AND FETCHES NO TEAM NEWS. That is the point.
The owner reads Discord, Fantasy Football Scout and the press conferences himself
and trusts his own filtering over an automated pass that might weight a bad
source (owner decision, 2026-08-03). This is the ingestion path only: make the
notes cheap to write, safe to consume, and loud when a name is wrong.

Usage:
    python3 scripts/fpl_notes.py --gw 1 <<'EOF'
    Jacquet nailed 0.9   # Slot presser
    Gomez out
    Bradley rotation
    EOF

    python3 scripts/fpl_notes.py --gw 1 --file notes.txt
    python3 scripts/fpl_notes.py --gw 1 --check       # parse + match, write nothing

Shorthand, one player per line:

    <name> [status] [start_prob] [# source]

  status      nailed | rotation (= rotation_risk) | doubtful | out | suspended
  start_prob  a float in [0, 1]; pins start probability ABSOLUTELY
  # source    everything after a `#` becomes the note's single `sources` entry;
              a line that starts with `#` is a comment, blank lines are skipped

At least one of status / start_prob is required — a bare name is a typo, not a
note, and is rejected rather than silently dropped. So is an unrecognised word.

Names are matched against the FPL feed's own `web_name` ("Virgil", not
"Van Dijk"; "B.Fernandes", not "Bruno Fernandes"), after the same collision
rename core/fpl_priors applies before the engine sees a name. Matching is
case-, punctuation- and diacritic-insensitive and accepts a UNIQUE prefix or
substring; it never guesses between two candidates. An unmatched name aborts the
whole batch: core.research.load_entries would key it under a name nobody looks
up, which is exactly how the World Cup site once published an article about a
ruled-out player.

What the statuses do to the model (core/blend.py, core/research.py):
  out, suspended        HARD — zero the player outright, ignoring the game's
                        research weight entirely.
  start_prob_override   HARD — pins start probability absolutely, ignoring w.
  nailed, rotation_risk, doubtful
                        SOFT — carried into the overlay and scaled by the game's
                        research weight (FPL: config.weight("fpl") = 0.30).
                        They mainly drive the site's public flag; pair one with
                        an explicit start_prob when you want the minutes moved.

Notes are pinned to the gameweek (`round: <gw>`), so they expire on their own
rather than leaking into next week's projections.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import os
import re
import sys
import unicodedata

# Allow running as `python3 scripts/fpl_notes.py` from anywhere: put the repo
# root (which holds core/ and evmax/) on the path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import research  # noqa: E402

# The overlay's vocabulary (core/research.py), plus the words an owner actually
# types for them. Anything not in here is rejected, never dropped.
STATUS_WORDS = {
    "nailed": "nailed",
    "starter": "nailed",
    "starts": "nailed",
    "rotation": "rotation_risk",
    "rotation_risk": "rotation_risk",
    "risk": "rotation_risk",
    "doubt": "doubtful",
    "doubtful": "doubtful",
    "out": "out",
    "injured": "out",
    "susp": "suspended",
    "suspended": "suspended",
    "banned": "suspended",
}

_MAX_SUGGESTIONS = 8


class UnmatchedName(ValueError):
    """One or more note names match no player in the feed.

    Carries `unmatched` as [(typed_name, [suggestion, ...]), ...] so the caller
    can print something the owner can act on instead of a bare failure.
    """

    def __init__(self, unmatched: list):
        self.unmatched = unmatched
        detail = "; ".join(
            f"{name!r} (did you mean: {', '.join(sugg) or 'no close match'})"
            for name, sugg in unmatched)
        super().__init__(f"unmatched player name(s): {detail}")


# ---------------------------------------------------------------------------
# Parsing the shorthand
# ---------------------------------------------------------------------------

def _as_probability(token: str):
    """The token as a start probability, or None if it is not numeric at all.

    Raises for a numeric token outside [0, 1]: `Jacquet 1.4` is a mistake worth
    stopping on, not a name fragment.
    """
    try:
        value = float(token)
    except ValueError:
        return None
    if not 0.0 <= value <= 1.0:
        raise ValueError(
            f"start probability {token!r} is outside [0, 1] — start_prob_override "
            f"is a probability, not a multiplier")
    return value


def parse(text: str) -> dict:
    """Parse the shorthand into {name: {status, start_prob_override, sources}}.

    `name` is exactly what was typed; matching it to the feed is match_name's job,
    deliberately kept separate so parsing can be tested without a player list.
    """
    out: dict[str, dict] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        body, _, comment = line.partition("#")
        sources = [comment.strip()] if comment.strip() else []

        tokens = body.split()
        if not tokens:
            raise ValueError(f"line {lineno}: {raw.strip()!r} has no player name")

        status = None
        start_prob = None
        # Consume trailing status words / probabilities from the right; whatever
        # is left in front is the (possibly multi-word) name.
        while len(tokens) > 1:
            token = tokens[-1]
            prob = _as_probability(token)
            if prob is not None:
                if start_prob is not None:
                    raise ValueError(
                        f"line {lineno}: two start probabilities in {line!r}")
                start_prob = prob
            elif token.lower() in STATUS_WORDS:
                if status is not None:
                    raise ValueError(f"line {lineno}: two status words in {line!r}")
                status = STATUS_WORDS[token.lower()]
            else:
                break
            tokens.pop()

        name = " ".join(tokens).strip()
        if not name:
            raise ValueError(f"line {lineno}: {raw.strip()!r} has no player name")
        if status is None and start_prob is None:
            raise ValueError(
                f"line {lineno}: {line!r} says nothing the model can use. Expected "
                f"a status ({', '.join(sorted(set(STATUS_WORDS.values())))}) and/or "
                f"a start probability in [0, 1]. Unrecognised: {tokens[-1]!r}")
        if name in out:
            raise ValueError(
                f"line {lineno}: {name!r} already has a note in this batch — two "
                f"lines for one player is a contradiction, not a merge")

        out[name] = {"status": status, "start_prob_override": start_prob,
                     "sources": sources}
    return out


# ---------------------------------------------------------------------------
# Matching a typed name to the feed
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    """Casefold, strip diacritics and punctuation. `B.Fernandes` -> `bfernandes`."""
    s = "".join(c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn")
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _suggestions(note_name: str, feed_names) -> list:
    """The closest feed names, best first — a shortlist, never the whole squad."""
    key = _norm(note_name)
    scored = sorted(
        feed_names,
        key=lambda n: difflib.SequenceMatcher(None, key, _norm(n)).ratio(),
        reverse=True)
    return scored[:5]


def match_name_verbose(note_name: str, feed_names) -> tuple:
    """(matched feed name or None, suggestions).

    Case-insensitive exact, then unique prefix, then unique substring. Ambiguity
    is never resolved by coin flip: two plausible targets return None and hand
    both back as suggestions.
    """
    feed_names = list(feed_names)
    key = _norm(note_name)
    if not key:
        return None, []

    for candidates in (
        [n for n in feed_names if _norm(n) == key],
        [n for n in feed_names if _norm(n).startswith(key)],
        [n for n in feed_names if key in _norm(n)],
    ):
        if len(candidates) == 1:
            return candidates[0], []
        if len(candidates) > 1:
            return None, sorted(candidates)[:_MAX_SUGGESTIONS]
    return None, _suggestions(note_name, feed_names)


def match_name(note_name: str, feed_names):
    """The matched feed name, or None when there is no unambiguous match."""
    return match_name_verbose(note_name, feed_names)[0]


def feed_names(players: list) -> list:
    """The names the SIM keys on, for a parsed bootstrap player list.

    Not simply `web_name`: core.fpl_priors renames colliding web_names (Cole
    Palmer / Alex Palmer both arrive as "Palmer") before the engine ever sees
    them, and the overlay is looked up with the post-rename name. Matching
    against raw web_names would happily accept "Palmer" and then key a note
    nobody looks up.
    """
    from core import fpl_priors

    copies = [dict(p) for p in players]      # _disambiguate_names mutates in place
    fpl_priors._disambiguate_names(copies)
    return [p["name"] for p in copies]


def load_feed_names() -> list:
    """Feed names from the cached bootstrap. Reads data/, never the network."""
    from core import fpl_api

    boot = fpl_api.read_cache("bootstrap")
    if boot is None:
        raise SystemExit(
            "data/fpl/bootstrap.json is missing — populate the cache with\n"
            "    python3 manage.py fpl --round 1\n"
            "  (this script never fetches anything itself)")
    return feed_names(fpl_api.parse_players(boot))


# ---------------------------------------------------------------------------
# Writing the notes
# ---------------------------------------------------------------------------

def _slug(name: str) -> str:
    slug = unicodedata.normalize("NFD", name)
    slug = "".join(c for c in slug if unicodedata.category(c) != "Mn")
    slug = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")
    return slug or "unnamed"


def note_path(research_dir: str, feed_name: str) -> str:
    """research/players/fpl-<slug>.md.

    The `fpl-` prefix keeps these clear of the hand-written World Cup notes
    sharing the directory (there is already a `kane.md`), and one file per player
    — overwritten, not appended to — keeps core.research.find_duplicate_names
    quiet: the 2026-07-19 Nico Williams collision was four files for one name
    where which one was live came down to directory listing order.
    """
    return os.path.join(research_dir, "players", f"fpl-{_slug(feed_name)}.md")


def render_note(feed_name: str, entry: dict, gameweek: int,
                updated: str | None = None) -> str:
    """The markdown note, in the frontmatter dialect core/research.py parses."""
    updated = updated or dt.date.today().isoformat()
    prob = entry.get("start_prob_override")
    lines = [
        "---",
        "entity: player",
        f"name: {feed_name}",
        f"status: {entry.get('status') or 'null'}",
        f"start_prob_override: {'null' if prob is None else prob}",
        "lambda_multiplier: 1.0",
        f"round: {gameweek}",
        "sources:",
    ]
    lines += [f"  - {s}" for s in entry.get("sources") or []]
    lines += [
        f"updated: {updated}",
        "---",
        "",
        f"Owner lineup note for gameweek {gameweek}, written with "
        f"scripts/fpl_notes.py.",
        "",
        "Hand-filtered team news (Discord / Fantasy Football Scout / press "
        "conferences), not scraped. Pinned to this gameweek, so it expires on its "
        "own rather than leaking into a later round.",
        "",
    ]
    return "\n".join(lines)


def write_notes(entries: dict, gameweek: int, feed_names: list,
                research_dir: str | None = None,
                updated: str | None = None) -> list:
    """Write one note per entry. Returns [(feed_name, path), ...].

    Every name is resolved BEFORE anything is written: one unmatched name aborts
    the whole batch with UnmatchedName, because a half-applied batch is the state
    nobody can reason about, and a silently-ignored note is the failure this whole
    path exists to prevent.
    """
    research_dir = research_dir or research.RESEARCH_DIR

    resolved, unmatched = [], []
    for name, entry in entries.items():
        match, suggestions = match_name_verbose(name, feed_names)
        if match is None:
            unmatched.append((name, suggestions))
        else:
            resolved.append((name, match, entry))
    if unmatched:
        raise UnmatchedName(unmatched)

    collisions: dict[str, str] = {}
    for typed, match, _entry in resolved:
        if match in collisions:
            raise ValueError(
                f"{typed!r} and {collisions[match]!r} both resolve to {match!r} — "
                f"two notes for one player is a contradiction, not a merge")
        collisions[match] = typed

    os.makedirs(os.path.join(research_dir, "players"), exist_ok=True)
    written = []
    for _typed, match, entry in resolved:
        path = note_path(research_dir, match)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render_note(match, entry, gameweek, updated=updated))
        written.append((match, path))
    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _describe(entry: dict) -> str:
    bits = []
    if entry.get("status"):
        bits.append(entry["status"])
    if entry.get("start_prob_override") is not None:
        bits.append(f"start={entry['start_prob_override']:.2f}")
    for source in entry.get("sources") or []:
        bits.append(f"src={source}")
    return ", ".join(bits)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Write the owner's lineup notes into research/players/.",
        epilog="Reads the shorthand from --file or stdin. Never fetches team news.")
    ap.add_argument("--gw", type=int, required=True,
                    help="gameweek the notes are pinned to")
    ap.add_argument("--file", help="read the shorthand from this file (default stdin)")
    ap.add_argument("--check", action="store_true",
                    help="parse and name-match only; write nothing")
    ap.add_argument("--research-dir", default=None,
                    help=f"override the research root (default {research.RESEARCH_DIR})")
    args = ap.parse_args(argv)

    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()

    try:
        entries = parse(text)
    except ValueError as exc:
        print(f"!!! {exc}", file=sys.stderr)
        return 1
    if not entries:
        print("no notes in input — nothing written")
        return 0

    names = load_feed_names()

    if args.check:
        bad = False
        for name, entry in entries.items():
            match, suggestions = match_name_verbose(name, names)
            if match is None:
                bad = True
                hint = ", ".join(suggestions) or "no close match"
                print(f"!!! UNMATCHED {name!r} — did you mean: {hint}",
                      file=sys.stderr)
            else:
                print(f"  ok  {name!r} -> {match}: {_describe(entry)}")
        return 1 if bad else 0

    try:
        written = write_notes(entries, args.gw, names,
                              research_dir=args.research_dir)
    except UnmatchedName as exc:
        # Loud and non-zero on purpose: an unmatched note is looked up by nobody,
        # so a typo would otherwise be a silent no-op that reads as done.
        for name, suggestions in exc.unmatched:
            hint = ", ".join(suggestions) or "no close match"
            print(f"!!! UNMATCHED PLAYER NAME {name!r} — did you mean: {hint}",
                  file=sys.stderr)
        print("!!! NOTHING WAS WRITTEN. The feed uses FPL's web_name — "
              "'Virgil', not 'Van Dijk'.", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"!!! {exc}", file=sys.stderr)
        return 1

    by_name = {}
    for typed, entry in entries.items():
        match = match_name(typed, names)
        by_name[match] = entry
    for name, path in written:
        rel = os.path.relpath(path, os.path.dirname(research.RESEARCH_DIR))
        print(f"  {name:<20} {_describe(by_name[name]):<40} -> {rel}")
    print(f"Wrote {len(written)} lineup note(s) pinned to gameweek {args.gw}. "
          f"Rebuild to apply: python3 -m evmax.build --gw {args.gw}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
