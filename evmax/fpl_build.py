"""Build the evmax FPL section for one gameweek.

Usage:
    python3 -m evmax.build --gw 1 [--sims 50000] [--out dist]
                           [--url https://evmax.ai] [--no-llm]
Run from the repo root.

The World Cup tree under /round/N/ is never written by this module. Those pages
are frozen published claims that /track-record/ grades against reality, and the
FPL build has no business touching them (spec D5).
"""
from __future__ import annotations

import os

from core import fpl_api, simcache

# A gameweek with no availability flags at all. FPL's bootstrap always carries
# some — injuries, suspensions, doubts — so an all-clear feed means a stale cache,
# not a miraculously healthy league.
_STALE_IF_NO_FLAGS = True


def preflight(gameweek: int, players: list, cold_start: list) -> list:
    """Abort on anything that makes a build impossible; return warnings for the rest.

    Returns the warning strings rather than printing them, so the caller controls
    where they land and the tests can assert on them. The caller prints them, and
    repeats a one-line summary on the FINAL line of output — the World Cup site
    shipped an expired injury note because the operator's `| tail -1` hid a
    correctly-firing guard (07-08).
    """
    from core import fixtures

    problems = []
    if fpl_api.read_cache("bootstrap") is None:
        problems.append(
            "data/fpl/bootstrap.json is missing — populate the cache with\n"
            f"    python3 manage.py fpl --round {gameweek} --refresh\n"
            "  (data/ is gitignored: a fresh checkout has no cached FPL feed)")
    fx = fixtures.by_round(gameweek)
    if not fx:
        problems.append(
            f"no fixtures registered for gameweek {gameweek} — the FPL fixtures "
            f"feed is missing or stale; refresh it with\n"
            f"    python3 manage.py fpl --round {gameweek} --refresh")
    if problems:
        raise SystemExit("evmax fpl build preflight failed:\n- " +
                         "\n- ".join(problems))

    warnings = []

    unpriced = [f for f in fx if f.lam_home is None or f.lam_away is None]
    if unpriced:
        names = ", ".join(f"{f.home} vs {f.away}" for f in unpriced)
        warnings.append(
            f"UNPRICED FIXTURE(S) — team-ratings fallback in effect: {names}. "
            f"Those clubs' rows are model-derived, not market-derived; the ticker "
            f"labels them, but check the odds feed before publishing.")

    if cold_start:
        names = ", ".join(f.get("name", "?") for f in cold_start[:6])
        more = " ..." if len(cold_start) > 6 else ""
        warnings.append(
            f"{len(cold_start)} PLAYER(S) ON THE PRICE-BASED COLD-START PRIOR (no "
            f"Premier League history): {names}{more}. Their projections lean on "
            f"price alone — verify before featuring one.")

    if _STALE_IF_NO_FLAGS and players:
        flagged = sum(1 for p in players if p.get("status", "a") != "a")
        if flagged == 0:
            warnings.append(
                f"STALE AVAILABILITY DATA — 0 of {len(players)} players carry a "
                f"non-available status. A real gameweek always has injuries and "
                f"suspensions, so the bootstrap cache is almost certainly old. "
                f"Refresh before publishing or the site will present ruled-out "
                f"players as nailed starters.")

    return warnings


def cache_warnings(gameweek: int, cache_hit: bool) -> list:
    """Spec §9's "the sim cache missed unexpectedly".

    A miss on the FIRST build of a gameweek is expected and silent. A miss when
    artifacts for this gameweek already exist means an input changed — priors,
    odds, research, config, or the model source fingerprint. That is usually
    intended, but it is worth saying out loud: it explains why a build that should
    have been instant just ran 50,000 simulations, and it is the one signal that
    would catch an accidental edit to a scoring constant.
    """
    if cache_hit:
        return []
    stale = simcache.artifacts_for(gameweek)
    if not stale:
        return []
    return [f"SIM CACHE MISS with {len(stale)} stale artifact(s) for gameweek "
            f"{gameweek} ({', '.join(k[:8] for k in stale[:4])}) — an input or a "
            f"model source changed since the last build. Expected after a code or "
            f"data change; investigate if you changed neither."]
