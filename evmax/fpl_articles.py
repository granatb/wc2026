"""Ranking and squad selection for the FPL articles.

Pure: no I/O, no HTTP, no simulation. Input is the enriched order-book rows from
games.fpl.model.build_artifact; output is ranked entry lists the site renders.

Separate from evmax/articles.py on purpose. That module is a frozen dependency of
the World Cup track record — /track-record/ grades published WC predictions off
snapshots built with it, and the existing suite passing is the regression gate for
this whole port (spec §4 "Untouched"). FPL-specific rules (goalkeepers belong in
the defenders article; DefCon exists at all; a three-per-club squad cap) go here.

Reused from articles.py where the rule is genuinely identical, not merely similar:
XI formation limits and price tiers.
"""

from __future__ import annotations

from evmax.articles import (POS_MAX, POS_MIN, SQUAD_QUOTA, XI_SIZE,
                            formation_of, legal_xi_formations, price_tier)
from games.fpl.model import DEFCON_THRESHOLD

# FPL squad rules (2026/27 official, games/fpl/rules.md).
SQUAD_BUDGET = 100.0
MAX_PER_CLUB = 3
# Positions the defenders article covers. FPL pays goalkeepers a 4-point clean
# sheet and a 10-point goal, so they belong with defenders rather than in an
# article of their own — the reader's decision is "which end of the pitch do I
# spend on", and one article answers it.
DEFENSIVE_POSITIONS = ("DEF", "GK")


def _ranked(rows: list, key: str, reverse: bool = True) -> list:
    out = [dict(r) for r in sorted(rows, key=lambda r: r[key], reverse=reverse)]
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


def captains(rows: list) -> list:
    """Captain candidates by captain EV, annotated with their kickoff order.

    kickoff_order exists because the captain and the VICE are two different
    decisions. The captain is picked against the deadline; the vice matters only
    if the captain does not play, so a manager wants to know whether their vice
    kicks off before or after their captain. 1 is the earliest kickoff among the
    candidates.

    A row with no kickoff (a blank gameweek for that club) sorts last rather than
    raising — `None` is not comparable to a string, so it needs an explicit key.
    """
    ranked = _ranked(rows, "captain_ev")
    by_kickoff = sorted(ranked, key=lambda r: (r.get("kickoff") is None,
                                               r.get("kickoff") or ""))
    order = {id(r): i for i, r in enumerate(by_kickoff, 1)}
    for r in ranked:
        r["kickoff_order"] = order[id(r)]
    return ranked


def defenders(rows: list) -> list:
    """Defenders and goalkeepers by expected points.

    The rows carry cs_points, defcon and bonus as separate columns, so the article
    can show a reader WHERE a defender's points come from — a 6.0 built on clean
    sheets is a different bet from a 6.0 built on DefCon.
    """
    return _ranked([r for r in rows if r.get("position") in DEFENSIVE_POSITIONS],
                   "x_points")


def efficiency(rows: list) -> list:
    """Points per million, tagged with a price tier.

    Rows with no price are dropped: value is undefined without one, and a null in
    the primary sort column would order arbitrarily.
    """
    ranked = _ranked([r for r in rows if r.get("value") is not None], "value")
    for r in ranked:
        r["tier"] = price_tier(r.get("price"))
    return ranked


def defcon_leaders(rows: list) -> list:
    """Players by P(defensive contribution >= their position's threshold).

    Ranked on the PROBABILITY, not the points: the points column is exactly
    2 x the probability, so the ordering is identical, but the probability is the
    number the article is about — "Gabriel hits 10 CBIT in 71% of simulations" is
    the claim, and "1.42 DefCon points" is its consequence.

    Goalkeepers are excluded because they are not DefCon-eligible at all, and
    players projecting exactly zero are excluded because they pad the list with
    names that cannot earn the points.
    """
    pool = [r for r in rows
            if DEFCON_THRESHOLD.get(r.get("position")) is not None
            and (r.get("p_defcon") or 0.0) > 0.0]
    ranked = _ranked(pool, "p_defcon")
    for r in ranked:
        r["defcon_threshold"] = DEFCON_THRESHOLD[r["position"]]
    return ranked
