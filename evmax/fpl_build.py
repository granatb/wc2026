"""Build the evmax FPL section for one gameweek.

Usage:
    python3 -m evmax.build --gw 1 [--sims 50000] [--out dist]
                           [--url https://evmax.ai] [--no-llm]
Run from the repo root.

The World Cup tree under /round/N/ is never written by this module. Those pages
are frozen published claims that /track-record/ grades against reality, and the
FPL build has no business touching them.
"""
from __future__ import annotations

from core import fixtures, fpl_api, simcache


def preflight(gameweek: int, players: list, cold_start: list) -> list:
    """Abort on anything that makes a build impossible; return warnings for the rest.

    Warnings are RETURNED rather than printed so the caller controls where they
    land and tests can assert on them. The caller must also repeat a one-line
    summary on its final line of output: the World Cup site once shipped an
    article about a ruled-out player because a correctly-firing guard was hidden
    by the operator's `| tail -1` pipe.

    `players` and `cold_start` come from games.fpl.model.load_gameweek's second
    and third return values — this function does not call load_gameweek itself,
    so it can be exercised (and its abort paths tested) without a network call.
    """
    problems = []
    if fpl_api.read_cache("bootstrap") is None:
        problems.append(
            "data/fpl/bootstrap.json is missing — populate the cache with\n"
            f"    python3 manage.py fpl --round {gameweek}\n"
            "  (data/ is gitignored: a fresh checkout has no cached FPL feed; "
            "games.fpl.model.load_gameweek fetches and caches it automatically "
            "the first time it finds no file there — no --refresh flag needed, "
            "and manage.py's --refresh pulls ESPN World Cup odds, not FPL data, "
            "so passing it here would not help)")
    fx = fixtures.by_round(gameweek)
    if not fx:
        problems.append(
            f"no fixtures registered for gameweek {gameweek} — either this is a "
            f"genuine blank gameweek, or the cached FPL fixtures feed is stale. "
            f"Force a hard refetch with\n"
            f"    rm -f data/fpl/bootstrap.json data/fpl/fixtures.json && "
            f"python3 manage.py fpl --round {gameweek}")
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

    if players:
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
    """The "sim cache missed unexpectedly" check.

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
