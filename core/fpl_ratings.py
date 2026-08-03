"""Premier League team ratings, derived from FPL's own published club strength.

`core.ratings.TEAM_RATINGS` holds odds-derived World Cup national teams only, so
every Premier League pairing fell through to the neutral `TeamRating(name)`
default and `match_lambdas` returned the identical `(1.445, 1.35)` for ARS-COV
and MCI-BOU alike. The published fixture ticker consequently showed all twenty
clubs on the same clean-sheet number and was ranking on rounding noise. This
module turns `core.fpl_api.parse_team_strength`'s per-club figures into the
multiplicative attack/defence factors that model expects, and registers them.

CALIBRATION ANCHOR. Factors are normalised around the LEAGUE MEAN, so a
league-average club scores exactly 1.0 on both and reproduces today's baseline
goal level unchanged. Total goals across the gameweek stay where they were; only
their distribution across clubs changes. We are redistributing goals, not
inventing them. `spread=0.0` collapses every club back onto 1.0/1.0 — the escape
hatch that isolates a regression to the ratings rather than the plumbing.

THE SYMMETRY APPROXIMATION (and its upgrade path). Preseason, FPL publishes only
`strength_overall_home/away`; the attack and defence splits are zeroed until
results start rolling in (see `parse_team_strength`). A single "overall" number
cannot be decomposed into attack and defence — there is no information in it
about which half of a strong club's strength is which. The overall-only path
therefore assumes the two are SYMMETRIC: a club that is one unit above the mean
gets its attack raised and its goals-conceded multiplier lowered by the same
amount. That is plainly wrong for the real league — a side can be great going
forward and porous at the back — and it is a deliberate approximation, taken
because a coarse two-sided estimate beats the uniform default it replaces.

The upgrade path is already wired: as soon as FPL populates
`strength_attack_*` / `strength_defence_*` for EVERY club, `derive` prefers them
and drops the symmetry assumption entirely, normalising attack and defence to
their own separate league means. It requires every club because one published
club among nineteen unpublished ones is not a league scale to normalise against.

HOW MUCH SPREAD is a calibration question, not a modelling one: the raw strength
scale is a coarse 2-5 and the right multiplier on it can only be settled by
realized results. It lives in `config.FPL_RATING_SPREAD` rather than as a
constant here so it can be retuned without touching this file.
"""

from __future__ import annotations

import config

from . import ratings

# Floor on both factors. A defence factor at or below zero would drive a lambda
# to zero or negative and hand the opponent an impossible scoreline distribution;
# at a large enough `spread` the linear form below crosses zero for the weakest
# club, so it is clamped rather than left to the operator's choice of dial.
MIN_FACTOR = 0.05

_PUBLISHED_FIELDS = ("attack_home", "attack_away", "defence_home", "defence_away")


def _mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _has_published(strengths: dict) -> bool:
    """True iff EVERY club carries all four attack/defence splits.

    All-or-nothing: the figures are only meaningful relative to a league mean, and
    a mean taken over the one club FPL happened to publish first is not one.
    """
    if not strengths:
        return False
    return all(s.get(f) is not None for s in strengths.values()
               for f in _PUBLISHED_FIELDS)


def _deviations(values: dict) -> dict:
    """{club: (own - league mean) / league mean} — the normalised deviation `z`.

    Zero for every club when the league mean is zero or there is a single club,
    which is what makes a one-club input (and a degenerate all-zero feed) land on
    a neutral 1.0 instead of dividing by zero.
    """
    mean = _mean(values.values())
    if not mean:
        return {club: 0.0 for club in values}
    return {club: (v - mean) / mean for club, v in values.items()}


def _clamp(value: float) -> float:
    return max(MIN_FACTOR, value)


def derive(strengths: dict, spread: float | None = None) -> dict:
    """{club: TeamRating} from `fpl_api.parse_team_strength`'s output.

    `spread` defaults to `config.FPL_RATING_SPREAD`; it is how far a club one
    whole league-mean above average moves from 1.0. `spread=0.0` returns a
    uniform 1.0/1.0 for every club.
    """
    if spread is None:
        spread = config.FPL_RATING_SPREAD
    if not strengths:
        return {}

    if _has_published(strengths):
        # In-season: attack and defence are measured separately, so use them
        # separately. `strength_defence_*` is defensive STRENGTH — a bigger number
        # is a better defence — so a positive deviation LOWERS the club's
        # goals-conceded multiplier, exactly as a positive attack deviation raises
        # its goals-scored one.
        att = _deviations({c: _mean((s["attack_home"], s["attack_away"]))
                           for c, s in strengths.items()})
        dfc = _deviations({c: _mean((s["defence_home"], s["defence_away"]))
                           for c, s in strengths.items()})
    else:
        # Preseason: one overall figure per club, split symmetrically. See the
        # module docstring — this is the approximation, not the intended model.
        overall = _deviations({c: _mean((s["overall_home"], s["overall_away"]))
                               for c, s in strengths.items()})
        att, dfc = overall, overall

    return {
        club: ratings.TeamRating(
            name=club,
            attack=_clamp(1.0 + spread * att[club]),
            defence=_clamp(1.0 - spread * dfc[club]),
        )
        for club in strengths
    }


def register(strengths: dict, spread: float | None = None) -> None:
    """Derive and write into `core.ratings.TEAM_RATINGS`, ADDING KEYS ONLY.

    That registry is shared with the World Cup, whose published claims are graded
    on /track-record/ against the numbers that produced them. An existing entry is
    never overwritten: if a World Cup team and a Premier League club ever collide
    on a name, the odds-derived World Cup rating wins and the FPL club silently
    keeps the neutral default rather than a retroactively-changed World Cup
    fixture appearing on the track record.
    """
    for club, rating in derive(strengths, spread=spread).items():
        ratings.TEAM_RATINGS.setdefault(club, rating)
