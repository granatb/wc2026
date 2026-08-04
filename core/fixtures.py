"""Single source of truth: the schedule + per-match team lambdas.

No game script may hardcode fixtures, kickoff times, or lambdas. They all import
from here. Kickoff datetimes are timezone-aware (UTC) so that lock logic
(holdet first-kickoff, malspillet bamse lock, FIFA captain-chain ordering) is
unambiguous across the engine and every game.

The 2026 FIFA World Cup runs 11 Jun -> 19 Jul 2026 across USA / Canada / Mexico:
48 teams, 12 groups of 4, then R32 -> R16 -> QF -> SF -> 3rd-place -> Final.

This file ships with the STRUCTURE and a couple of example rows. The full 104-match
schedule + odds-derived lambdas get populated from screenshots (kickoff times and
team lambdas confirmed against the official schedule / bookmaker odds).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import ratings


def utc(y: int, mo: int, d: int, h: int, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


# The stage every Fantasy Premier League fixture carries. Defined here, once, and
# imported by core.fpl_api (which stamps it onto parsed rows), games.fpl.model
# (which registers the Fixture objects) and evmax.fpl_build. It doubles as the
# competition discriminator for by_round() below, so the literal must not be
# written in two places that could drift apart.
FPL_STAGE = "GW"

# Round / stage identifiers. "round" is the fantasy-game round grouping (matchday),
# which is how the games batch fixtures and apply locks. Stages map onto it.
STAGES = [
    "GROUP_MD1", "GROUP_MD2", "GROUP_MD3",
    "R32", "R16", "QF", "SF", "BRONZE", "FINAL",
    FPL_STAGE,   # FPL gameweek
]


@dataclass
class Fixture:
    match_id: str
    home: str
    away: str
    kickoff: datetime          # UTC, timezone-aware
    stage: str                 # one of STAGES
    fantasy_round: int         # game-round bucket (1..N) the games use for locking
    neutral: bool = True       # host nations at home -> set False (HOME_ADV applies)
    venue: str = ""
    # Cached / overridden lambdas. If left None, computed from ratings on demand.
    lam_home: float | None = None
    lam_away: float | None = None
    # FPL's own Fixture Difficulty Rating (1-5, one per side). Editorial, not
    # model output -- displayed alongside our own ratings for a sanity check,
    # never fed into lambdas. See games/fpl/model.load_gameweek.
    home_difficulty: int | None = None
    away_difficulty: int | None = None

    def lambdas(self) -> tuple[float, float]:
        if self.lam_home is not None and self.lam_away is not None:
            return self.lam_home, self.lam_away
        return ratings.match_lambdas(self.home, self.away, neutral=self.neutral)


# ---------------------------------------------------------------------------
# The schedule. Populated from the official schedule + odds screenshots.
# Example rows show the intended shape (teams TBD until the draw/odds are in).
# ---------------------------------------------------------------------------

import json as _json
import os as _os
from datetime import datetime as _dt

_SCHEDULE_JSON = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "data", "schedule.json")

# Host nations — these play "at home" (home advantage applies).
HOST_NATIONS = {"USA", "United States", "Canada", "Mexico"}


def _parse_iso(s: str) -> datetime:
    """Parse an ISO-8601 kickoff string to a UTC-aware datetime (py3.9-safe)."""
    s = s.replace("Z", "+00:00")
    d = _dt.fromisoformat(s)
    return d.astimezone(timezone.utc) if d.tzinfo else d.replace(tzinfo=timezone.utc)


def load_from_json(path: str = _SCHEDULE_JSON) -> list:
    """Build Fixture objects from a schedule.json written by schedule_api."""
    with open(path, encoding="utf-8") as fh:
        rows = _json.load(fh)
    out = []
    for r in rows:
        home, away = r["home"], r["away"]
        out.append(Fixture(
            match_id=r["match_id"], home=home, away=away,
            kickoff=_parse_iso(r["kickoff_utc"]), stage=r["stage"],
            fantasy_round=r["fantasy_round"],
            neutral=(home not in HOST_NATIONS),
            lam_home=r.get("lam_home"), lam_away=r.get("lam_away"),
        ))
    return out


# The schedule. Auto-loaded from data/schedule.json when present (written by
# schedule_api.fetch_and_write); otherwise this in-file list (populated manually).
SCHEDULE: list[Fixture] = []
if _os.path.exists(_SCHEDULE_JSON):
    SCHEDULE = load_from_json()


def by_round(fantasy_round: int, stage: str | None = None) -> list[Fixture]:
    """Fixtures in a fantasy round, optionally narrowed to one stage.

    SCHEDULE holds every competition's fixtures in one list and buckets on
    fantasy_round alone, so World Cup round 1 and FPL gameweek 1 collide. `stage`
    is the competition discriminator: FPL registers its fixtures as FPL_STAGE
    ("GW", see games.fpl.model.load_gameweek) and no World Cup fixture ever
    carries that value — they hold ESPN status strings (STATUS_FULL_TIME,
    STATUS_SCHEDULED, ...).

    Defaults to None (no filter) so every existing World Cup call site is
    unchanged.
    """
    out = [f for f in SCHEDULE if f.fantasy_round == fantasy_round]
    if stage is not None:
        out = [f for f in out if f.stage == stage]
    return out


def by_stage(stage: str) -> list[Fixture]:
    return [f for f in SCHEDULE if f.stage == stage]


def get(match_id: str) -> Fixture | None:
    return next((f for f in SCHEDULE if f.match_id == match_id), None)


# Registered gameweek deadlines, {fantasy_round: UTC-aware datetime}. FPL locks on a
# published deadline that PRECEDES the first kickoff (GW1: 17:30Z deadline, evening
# kickoff), so lock logic must prefer this over min(kickoff). Populated from
# core.fpl_api.parse_events — never scraped from the rules page, which localises times.
DEADLINES: dict = {}


def set_deadline(fantasy_round: int, when: datetime) -> None:
    DEADLINES[fantasy_round] = when


def round_lock_time(fantasy_round: int) -> datetime | None:
    """When a round locks: the registered deadline if known, else first kickoff.

    The WC had no separate deadline, so first kickoff was the lock. FPL publishes
    one, and the frozen-at-lock rule depends on using it.
    """
    if fantasy_round in DEADLINES:
        return DEADLINES[fantasy_round]
    fx = by_round(fantasy_round)
    return min((f.kickoff for f in fx), default=None)


def fixtures_for_team(team: str, fantasy_round: int | None = None) -> list[Fixture]:
    pool = SCHEDULE if fantasy_round is None else by_round(fantasy_round)
    return [f for f in pool if team in (f.home, f.away)]


def is_single_match_round(fantasy_round: int) -> bool:
    """True for rounds with exactly one match (bronze final, final) -- used by
    malspillet to auto-assign Chance Bamse."""
    return len(by_round(fantasy_round)) == 1


def fixture_count_by_team(fantasy_round: int) -> dict:
    """{team: number of fixtures} for a round. Absent teams have a blank."""
    counts: dict = {}
    for f in by_round(fantasy_round):
        counts[f.home] = counts.get(f.home, 0) + 1
        counts[f.away] = counts.get(f.away, 0) + 1
    return counts


def teams_with_double(fantasy_round: int) -> set:
    """Teams playing more than once — a 'double gameweek'."""
    return {t for t, c in fixture_count_by_team(fantasy_round).items() if c > 1}


def teams_with_blank(fantasy_round: int, all_teams) -> set:
    """Teams in `all_teams` with no fixture — a 'blank gameweek'.

    Requires the league's full team set, because a team with no fixture is by
    definition absent from the schedule rows and cannot be inferred from them.
    """
    return set(all_teams) - set(fixture_count_by_team(fantasy_round))
