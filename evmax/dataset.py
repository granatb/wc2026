"""The public CC BY dataset — per-gameweek JSON + CSV emitters (phase 2B, P2).

Pure emitters, no I/O (same bar as evmax/render.py and evmax/fpl_players.py):
the build hands in the artifact rows it already holds in memory and writes
whatever comes back. Spec decision D3 — the dataset is emitted BY THE BUILD
from artifacts already in memory. No new pipeline, no scraping, no database.

WHY CC BY AND NOT PUBLIC DOMAIN. Attribution is the growth strategy: every
lawful reuse of these numbers has to name evmax, so the dataset seeds
citations rather than anonymous copies. The licence line is emitted into every
payload and every tool response, never assumed to be known.

DEFENSIVE DISTRIBUTION COLUMNS. The per-player point distributions (spec P1)
land on a parallel branch. This module must produce a complete, correctly
shaped record BOTH before and after that merge, so:
  * JSON — a distribution key is emitted only when the row carries it. A row
    without one has no such key at all (never a null that reads as "we
    simulated a distribution and it was empty").
  * CSV — the distribution summary columns are ALWAYS in the header and are
    empty for a row that has none. A CSV whose header changed shape between
    gameweeks would break every downstream consumer that reads it by index,
    which is exactly the audience this dataset is for.
The raw PMF (`distribution`, a sparse {points: count} dict) is JSON-only: a
nested object has no honest flat-CSV representation.
"""

from __future__ import annotations

import csv as _csv
import io as _io

from evmax import render

# The dataset's own URL namespace. index.json lists what exists; all.json|.csv
# is the cumulative file, rebuilt from every gw*.json on disk (so a gameweek
# published months ago survives without being re-simulated).
DATASET_BASE = "/api/fpl/dataset"
DATA_PAGE = "/data/"

LICENSE = "CC BY 4.0"
LICENSE_URL = render.DATA_LICENSE_URL
# The exact string a reuser should paste. Quoted verbatim on /data/, in
# docs/DATASET.md and on every MCP tool response — one canonical wording.
ATTRIBUTION = "evmax (https://evmax.ai)"
ATTRIBUTION_LINE = ("Data: evmax (https://evmax.ai), CC BY 4.0 — "
                    "https://creativecommons.org/licenses/by/4.0/")

METHOD = ("Market odds (de-vigged) to Dixon-Coles scorelines to 50,000 "
          "Monte-Carlo simulations per gameweek, scored on the official "
          "Fantasy Premier League points table. Projections are frozen "
          "before the deadline and graded publicly afterwards.")

# Columns straight off the artifact row (games/fpl/model._derive_row) plus the
# two verdict columns this module derives. Order here IS the CSV order.
_ROW_FIELDS = ("name", "team", "position", "price", "ownership_pct",
               "x_points", "captain_ev", "ceiling", "value", "bonus",
               "defcon", "p_defcon", "cs_points", "start_prob", "kickoff")

# Distribution summary scalars (spec P1). Present on a row only after the
# parallel branch lands; the CSV header carries them either way.
DISTRIBUTION_FIELDS = ("p10", "median", "mode", "p90", "p_haul", "p_blank")

# The raw sparse PMF — JSON only, never a CSV column.
PMF_FIELD = "distribution"

CSV_COLUMNS = (("gameweek", "id") + _ROW_FIELDS
               + ("verdict_tier", "verdict_call") + DISTRIBUTION_FIELDS)

# Every CSV column defined once. /data/'s glossary table and docs/DATASET.md
# both render from THIS dict, so a column can never ship undocumented (pinned
# by tests/test_dataset.py).
COLUMN_GLOSSARY = {
    "gameweek": ("integer", "Premier League gameweek the projection is for."),
    "id": ("integer", "The official FPL element id — the stable join key "
                      "against the FPL API. Empty if we could not match the "
                      "player to the bootstrap feed."),
    "name": ("string", "Player name as our model carries it, disambiguated "
                       "when two players share a surname."),
    "team": ("string", "Three-letter club code (ARS, MUN, ...)."),
    "position": ("string", "GK, DEF, MID or FWD."),
    "price": ("float", "FPL price in millions at the time of the build."),
    "ownership_pct": ("float", "Percent of FPL managers owning the player at "
                               "build time."),
    "x_points": ("float", "Our projection: mean FPL points across 50,000 "
                          "simulations of this gameweek. The headline number."),
    "captain_ev": ("float", "Expected points if captained (2 x x_points)."),
    "ceiling": ("float", "Tail mean — the average of the player's best 15% of "
                         "simulations. The realistic good week, not a cap."),
    "value": ("float", "x_points per million of price."),
    "bonus": ("float", "Expected bonus points, per match."),
    "defcon": ("float", "Expected defensive-contribution points, per match."),
    "p_defcon": ("float", "Probability of hitting the defensive-contribution "
                          "threshold, per match (defcon = 2 x p_defcon)."),
    "cs_points": ("float", "Expected clean-sheet points, per match."),
    "start_prob": ("float", "Probability the player starts, from the priors "
                            "(research notes can override it)."),
    "kickoff": ("string", "ISO-8601 UTC kickoff of the player's fixture."),
    "verdict_tier": ("string", "S / A / B / C / D — the player's band this "
                               "gameweek by projected points."),
    "verdict_call": ("string", "buy / hold / pass — the tier read as a call."),
    "p10": ("float", "10th-percentile outcome (the floor). Empty for "
                     "gameweeks published before we stored distributions."),
    "median": ("float", "Median simulated points. Empty for gameweeks "
                        "published before we stored distributions."),
    "mode": ("float", "Most likely single point total. Empty for gameweeks "
                      "published before we stored distributions."),
    "p90": ("float", "90th-percentile outcome. Empty for gameweeks published "
                     "before we stored distributions."),
    "p_haul": ("float", "Probability of 10 or more points. Empty for "
                        "gameweeks published before we stored distributions."),
    "p_blank": ("float", "Probability of 2 or fewer points. Empty for "
                         "gameweeks published before we stored distributions."),
}


def _meta(generated_at: str = None, has_distributions: bool = False) -> dict:
    """The licence/provenance block every dataset file carries.

    `license` is the short human name the plan pins ("CC BY 4.0") and
    `license_url` the machine one — deliberately NOT the site's other
    envelopes' convention (where `license` is the URL), because a bulk dataset
    is read by people first and its terms have to be legible without a fetch.
    """
    return {
        "license": LICENSE,
        "license_url": LICENSE_URL,
        "attribution": ATTRIBUTION,
        "attribution_line": ATTRIBUTION_LINE,
        "source": f"{render.SITE_URL}{DATA_PAGE}",
        "method": METHOD,
        "generated_at": generated_at,
        "has_distributions": bool(has_distributions),
    }


def _verdicts(rows: list) -> tuple:
    """({name: letter}, {letter: call}) for the rows, via the same cut points
    the player cards use — imported rather than reimplemented so the dataset
    and the site can never disagree about a player's tier.

    Imported lazily: fpl_players is a large emitter module and the dataset
    emitters are used (by the MCP smoke path and by tests) without it.
    """
    from evmax import fpl_players

    return fpl_players.verdict_letters(rows), fpl_players._CALL_BY_LETTER


# Columns the model rounds at derivation (games/fpl/model._derive_row) arrive
# already clean. start_prob does not — the build threads it straight off the
# priors, so it lands as 0.9210526315789473. Fourteen significant figures of a
# probability is not information, and a published dataset that carries them
# invites a reader to believe in a precision the model does not have.
_ROUNDING = {"start_prob": 3}


def _record(row: dict, gameweek: int, pid, letter: str, call: str) -> dict:
    """One player's dataset record. Distribution keys appear only if the row
    has them (see the module docstring)."""
    rec = {"gameweek": gameweek, "id": pid}
    for field in _ROW_FIELDS:
        value = row.get(field)
        digits = _ROUNDING.get(field)
        if digits is not None and isinstance(value, float):
            value = round(value, digits)
        rec[field] = value
    rec["verdict_tier"] = letter
    rec["verdict_call"] = call
    for field in DISTRIBUTION_FIELDS:
        if field in row and row[field] is not None:
            rec[field] = row[field]
    if row.get(PMF_FIELD):
        rec[PMF_FIELD] = row[PMF_FIELD]
    return rec


def gameweek_payload(gameweek: int, rows: list, generated_at: str,
                     ids: dict = None) -> dict:
    """One gameweek's bulk record: meta block + every simulated player.

    rows: the gameweek artifact rows (games/fpl/model.build_rows output, with
      start_prob threaded in by the build). Never a filtered subset — the
      dataset's whole promise is that it is EVERY player we simulated, not the
      ones we wrote about.
    ids: {name: FPL element id} where the build could match the bootstrap.
      A name with no match gets id null — the dataset says "we could not join
      this one" rather than guessing an id that would poison a downstream join.
    """
    ids = ids or {}
    letters, calls = _verdicts(rows)
    ordered = sorted(rows, key=lambda r: (-(r.get("x_points") or 0.0),
                                          r.get("name") or ""))
    players = [_record(r, gameweek, ids.get(r["name"]),
                       letters.get(r["name"]),
                       calls.get(letters.get(r["name"])))
               for r in ordered]
    has_dist = any(any(f in p for f in DISTRIBUTION_FIELDS) for p in players)
    return {
        "gameweek": gameweek,
        "count": len(players),
        "meta": _meta(generated_at, has_dist),
        "players": players,
    }


def _cell(value) -> str:
    """CSV cell text. None is an EMPTY cell, never the string "None" — the
    single most common way a hand-rolled CSV writer poisons a consumer's
    numeric column."""
    if value is None:
        return ""
    if value is True or value is False:
        return "true" if value else "false"
    return str(value)


def to_csv(payload: dict) -> str:
    """RFC4180 CSV of a gameweek or merged payload: header row, CRLF line
    endings, minimal quoting (a name with a comma or a quote is quoted and
    doubled by the stdlib writer), UTF-8 text, no index column."""
    buf = _io.StringIO()
    writer = _csv.writer(buf, lineterminator="\r\n",
                         quoting=_csv.QUOTE_MINIMAL)
    writer.writerow(CSV_COLUMNS)
    for rec in payload.get("players", []):
        writer.writerow([_cell(rec.get(col)) for col in CSV_COLUMNS])
    return buf.getvalue()


def json_name(gameweek: int) -> str:
    return f"gw{gameweek}.json"


def csv_name(gameweek: int) -> str:
    return f"gw{gameweek}.csv"


def gameweek_paths(gameweek: int) -> dict:
    return {"gameweek": gameweek,
            "json": f"{DATASET_BASE}/{json_name(gameweek)}",
            "csv": f"{DATASET_BASE}/{csv_name(gameweek)}"}


ALL_PATHS = {"json": f"{DATASET_BASE}/all.json",
             "csv": f"{DATASET_BASE}/all.csv"}


def index_payload(gameweeks, generated_at: str = None) -> dict:
    """`/api/fpl/dataset/index.json` — what exists right now. This is the file
    an agent or a scraper reads FIRST, so it must be complete and cheap: no
    player rows, just the manifest."""
    gws = sorted(set(int(g) for g in gameweeks))
    return {
        "meta": _meta(generated_at),
        "gameweeks": [gameweek_paths(g) for g in gws],
        "all": dict(ALL_PATHS),
        "columns": {col: {"type": typ, "description": desc}
                    for col, (typ, desc) in COLUMN_GLOSSARY.items()},
    }


def merge_all(payloads: list) -> dict:
    """The cumulative dataset: every gameweek's players in one file, ordered by
    gameweek ascending then x_points descending (name breaks ties, so the file
    is byte-stable across rebuilds).

    The build feeds this every gw*.json ALREADY ON DISK, not just the gameweek
    it is building — old gameweeks survive a rebuild without being re-simulated.
    """
    players = []
    gws, generated = set(), None
    has_dist = False
    for payload in payloads:
        for rec in payload.get("players", []):
            players.append(rec)
            gws.add(rec.get("gameweek"))
            if any(f in rec for f in DISTRIBUTION_FIELDS):
                has_dist = True
        stamp = (payload.get("meta") or {}).get("generated_at")
        if stamp and (generated is None or stamp > generated):
            generated = stamp
    players.sort(key=lambda r: (r.get("gameweek") or 0,
                                -(r.get("x_points") or 0.0),
                                r.get("name") or ""))
    return {
        "gameweeks": sorted(g for g in gws if g is not None),
        "count": len(players),
        "meta": _meta(generated, has_dist),
        "players": players,
    }
