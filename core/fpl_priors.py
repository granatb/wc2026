"""Turn FPL API data into engine priors.

This is the ONLY place FPL's field names become `ratings.PlayerPrior`. It owns:
  - the minutes model (start probability + expected minutes)
  - per-90 rate derivation (xG/xA -> goal/assist share, DefCon, saves)
  - the cold-start fallback for players with no Premier League history

It knows nothing about scoring (that is games/fpl/model.py) and nothing about HTTP
(that is core/fpl_api.py).

Why xG-derived rather than market-derived: ESPN carries no player-level props for
eng.1 (verified 2026-07-28), so the World Cup's anytime-goalscorer path is empty at
build time. FPL's own feed ships last season's per-90 rates instead, which slot into
the engine's existing `prior_share` blend slot. If props ever appear, the engine's
`market_rate` path lights up with no change here.
"""

from __future__ import annotations

import collections

import config

from . import ratings

# FPL status codes: a=available, d=doubtful, i=injured, s=suspended, u=unavailable.
_CANNOT_PLAY = {"i", "s", "u"}


def availability_factor(player: dict) -> float:
    """Multiplier on start probability from FPL's own availability fields.

    Hard-gates unavailable players to zero. Scales the doubtful. A `chance_of_playing`
    of 0 gates regardless of status, because FPL sometimes leaves status at 'a' while
    the percentage has already dropped to 0.
    """
    chance = player.get("chance_of_playing")
    if chance is not None:
        return max(0.0, min(1.0, chance / 100.0))
    if player.get("status") in _CANNOT_PLAY:
        return 0.0
    if player.get("status") == "d":
        return 0.5   # doubtful with no published percentage
    return 1.0


# Fallback expected minutes when a player has no history to measure.
_DEFAULT_EXP_MINUTES = 70.0
_DEFAULT_START_PROB = 0.25   # unknown player: assume a squad role, not a starter


_FULL_SEASON_MATCHES = 38   # a past season always covers a full 38-match league


def minutes_model(player: dict, team_matches: int,
                  profile: dict | None = None) -> tuple[float, float]:
    """(start_prob, exp_minutes) for one player.

    start_prob is the observed start rate over `team_matches`, then multiplied by
    FPL's availability signal. exp_minutes is minutes-per-start, which separates a
    90-minute nailed starter from a player who starts but is routinely withdrawn,
    and drops toward a cameo figure for players who mostly come off the bench.

    `team_matches` is how many matches the sample covers — 38 for a full prior
    season, or matches played so far once the new season is under way.

    `profile` is an optional `history_profile` for the player and is consulted
    ONLY when the bootstrap sample is completely empty — i.e. exactly where this
    function would otherwise return the blind _DEFAULT_START_PROB guess. That
    case is not only the summer signing: a player who missed all of last season
    injured, one who spent it on loan abroad, and a promoted club's squad all
    show zero bootstrap minutes while having a real Premier League season behind
    them. Measuring the role off that season beats assuming a 25% squad player.
    The profile's own season is always a full 38-match one (that is what makes it
    a season), so it is rated over _FULL_SEASON_MATCHES rather than
    `team_matches`, which counts THIS season's matches and would wildly overstate
    the rate early in a campaign.

    A profile with no starts recorded is IGNORED here, and that is a data
    quirk rather than a judgement: FPL only began publishing `starts` in 2022/23,
    so every earlier season reads `starts: 0` however many matches the player
    began (verified 2026-08-04: all 316 pre-2022/23 seasons of 1500+ minutes in
    the backfill report zero). Zero there is ambiguous between "never started"
    and "not recorded", and the honest response to an ambiguous field is to
    decline it and keep the default.

    Current fitness is NOT this function's job: a player still injured today is
    gated to zero by `availability_factor` below, exactly as a player with
    bootstrap minutes would be. Staleness is not this function's job either --
    `build_with_flags` withholds a profile that is too many seasons old before it
    ever gets here (config.FPL_HISTORY_MAX_SEASONS_BACK).
    """
    starts = player.get("starts") or 0
    minutes = player.get("minutes") or 0
    gate = availability_factor(player)

    if (team_matches > 0 and starts == 0 and minutes == 0
            and profile and (profile.get("starts") or 0) > 0):
        starts = profile["starts"]
        minutes = profile.get("minutes") or 0
        team_matches = _FULL_SEASON_MATCHES

    if team_matches <= 0 or (starts == 0 and minutes == 0):
        return _DEFAULT_START_PROB * gate, _DEFAULT_EXP_MINUTES

    start_rate = min(1.0, starts / float(team_matches))

    if starts > 0:
        exp_minutes = min(90.0, minutes / float(starts))
    else:
        # Never started in the sample: a substitute. Spread the minutes over the
        # appearances we can infer, floored so the sim still gives him some time.
        exp_minutes = max(15.0, min(59.0, minutes / float(team_matches)))

    return start_rate * gate, exp_minutes


def needs_cold_start(player: dict) -> bool:
    """True when a player has no Premier League minutes to derive rates from."""
    return (player.get("minutes") or 0) <= 0


def _price_scaled(player: dict, table: dict) -> float:
    pos = player.get("position", "MID")
    base = table.get(pos, 0.0)
    if base <= 0.0:
        return 0.0
    median = config.FPL_MEDIAN_PRICE.get(pos, 5.0)
    quality = min(3.0, max(0.3, (player.get("price") or median) / median))
    return base * quality


def price_prior_xg(player: dict) -> float:
    """Cold-start non-penalty xG/90 from price and position."""
    return _price_scaled(player, config.FPL_COLD_START_XG90)


def price_prior_xa(player: dict) -> float:
    """Cold-start xA/90 from price and position."""
    return _price_scaled(player, config.FPL_COLD_START_XA90)


def _rates(player: dict) -> tuple[float, float]:
    """(xg_per90, xa_per90), falling back to the price prior with no history."""
    if needs_cold_start(player):
        return price_prior_xg(player), price_prior_xa(player)
    return player.get("xg_per90") or 0.0, player.get("xa_per90") or 0.0


def _disambiguate_names(players: list[dict]) -> None:
    """Give every player a `name` that is unique across the whole pool, in place.

    FPL's `web_name` collides across clubs -- 14 collisions in the real GW1 pool,
    the worst being Cole Palmer (CHE, MID) and Alex Palmer (IPS, GK) both keying
    the shared engine's per-player accumulator as "Palmer". The engine keys
    strictly by name (core/engine_events.simulate_round), so uniqueness has to be
    established here, at the FPL boundary, before names ever reach it.

    Escalates only as far as needed so the common case (a unique web_name) is left
    completely untouched:

      1. web_name, if it is unique in the pool
      2. otherwise full_name, if THAT disambiguates
      3. otherwise f"{web_name} ({team})" -- guaranteed unique, because a single
         club cannot field two players sharing a web_name.

    Mutates the player dicts' "name" key in place (rather than returning a
    separate mapping) so that every existing caller keying off `p["name"]` --
    `games/fpl/model.py`'s `players_by_name = {p["name"]: p for p in players}`
    chief among them -- keeps working unmodified as long as it reads `name` AFTER
    this runs, which it already does.
    """
    web_counts = collections.Counter(p["name"] for p in players)
    colliding = [p for p in players if web_counts[p["name"]] > 1]
    if not colliding:
        return

    full_counts = collections.Counter(p.get("full_name") or p["name"] for p in players)
    for p in colliding:
        full = p.get("full_name") or p["name"]
        if full_counts[full] == 1:
            p["name"] = full
        else:
            p["name"] = f"{p['name']} ({p['team']})"


def history_profile(history_past: list | None) -> dict | None:
    """Per-90 and per-start rates from the most recent season with real minutes.

    Returns None when there is no season clearing FPL_HISTORY_MIN_MINUTES — a
    summer signing or a player with no Premier League record. Callers must treat
    None as "no data" and fall through to their existing prior, NOT substitute an
    estimate: a fabricated profile is worse than an honest absence, because it
    looks like evidence.

    "Most recent" is the lexicographically greatest `season_name` among the
    seasons clearing the floor ("2025/26" > "2024/25"), not the feed's array
    order, which is not a documented contract. A player who was injured through
    last season therefore profiles off the season before it: older, but real,
    and better than nothing.

    `clean_sheet_rate` and `points_per_start` are None (never 0.0, never a
    fabricated denominator) when the season records no starts — a substitute can
    clear the minutes floor without ever starting, and "0 clean sheets per start"
    would read as a terrible defensive record rather than as no evidence.
    """
    seasons = [s for s in (history_past or [])
               if (s.get("minutes") or 0) >= config.FPL_HISTORY_MIN_MINUTES]
    if not seasons:
        return None

    season = max(seasons, key=lambda s: s.get("season_name") or "")
    minutes = float(season.get("minutes") or 0)
    starts = season.get("starts") or 0
    per90 = 90.0 / minutes

    return {
        "season_name": season.get("season_name"),
        "minutes": season.get("minutes") or 0,
        "starts": starts,
        "clean_sheet_rate": ((season.get("clean_sheets") or 0) / float(starts)
                             if starts else None),
        "conceded_per90": (season.get("goals_conceded") or 0) * per90,
        "xgc_per90": (season.get("expected_goals_conceded") or 0.0) * per90,
        "bps_per90": (season.get("bps") or 0) * per90,
        "defcon_per90": (season.get("defensive_contribution") or 0) * per90,
        "points_per_start": ((season.get("total_points") or 0) / float(starts)
                             if starts else None),
    }


def season_start_year(season_name: str | None) -> int | None:
    """2024 from "2024/25". None for anything that isn't an FPL season name."""
    try:
        return int(str(season_name).split("/")[0])
    except (TypeError, ValueError):
        return None


def latest_season_year(backfill: dict | None) -> int | None:
    """The most recent season year anywhere in a backfill, or None if empty.

    Read off the data rather than from a hard-coded "current season" constant, so
    nothing needs editing every August and a stale cache can't silently make
    every player look ancient -- it is always compared against its own vintage.
    """
    years = [season_start_year(s.get("season_name"))
             for entry in (backfill or {}).values()
             for s in (entry.get("history_past") or [])]
    years = [y for y in years if y is not None]
    return max(years) if years else None


def profile_is_recent(profile: dict | None, latest_year: int | None) -> bool:
    """Is this profile's season within FPL_HISTORY_MAX_SEASONS_BACK of the newest
    season in the feed? See config for why the minutes model insists on it."""
    if not profile or latest_year is None:
        return False
    year = season_start_year(profile.get("season_name"))
    if year is None:
        return False
    return (latest_year - year) <= config.FPL_HISTORY_MAX_SEASONS_BACK


def shrink_defcon_rate(position: str, observed: float, minutes: float) -> float:
    """Empirical-Bayes shrinkage of a raw per-90 DefCon rate toward its position
    prior, in units of 90-minute appearances (defect D).

    `defensive_contribution * 90 / minutes` from a handful of minutes is noise,
    not signal -- a 1-minute cameo with a single alert action prints a 90.0
    per-90 rate. Blending it with `config.FPL_DEFCON_PRIOR` in proportion to how
    much of it is actually measured (`config.FPL_DEFCON_SHRINKAGE_K` pseudo-
    appearances of prior) degrades gracefully as the sample grows, rather than a
    hard minutes cutoff that would zero out real players returning from injury or
    arriving from abroad. See config.py for the K derivation and the measured
    priors.

    Goalkeepers are hard-gated to 0.0 no matter what `observed` says: they do not
    accrue CBIT/CBIRT actions and are not DefCon-eligible at all.
    """
    if position == "GK":
        return 0.0
    prior = config.FPL_DEFCON_PRIOR.get(position, 0.0)
    appearances = max(0.0, minutes) / 90.0
    k = config.FPL_DEFCON_SHRINKAGE_K
    return (observed * appearances + prior * k) / (appearances + k)


def _defcon_rate(player: dict, backfill: dict | None,
                 profile: dict | None = None) -> float:
    """The DefCon per-90 rate to carry onto this player's prior.

    Bootstrap's own `defcon_per90` wins whenever it is non-zero -- in-season,
    live data always beats last season's history. Only when bootstrap has
    nothing (preseason, when bootstrap-static zeroes the field for everyone) do
    we fall back to `backfill`, the core.fpl_api.fetch_defcon_backfill mapping of
    element id -> {"defcon_per90", "minutes"}. A player missing from `backfill`
    (no backfill supplied, or the id wasn't in it) safely falls through to 0.0.

    The backfilled rate is shrunk toward the position prior before it reaches the
    prior (see shrink_defcon_rate) -- raw per-90 rates from the tiny samples
    common in the backfill (61 of 400 real players under 200 minutes) are noise
    that would otherwise dominate the DefCon ranking. Goalkeepers are gated to
    0.0 up front, regardless of what `player["defcon_per90"]` or `backfill` say --
    they are not DefCon-eligible.

    When a `profile` (see history_profile) is available it picks the season, in
    place of the entry's own `defcon_per90`. The two agree for the common case
    and differ in exactly one: a player whose most recent season is a handful of
    minutes. fpl_api.defcon_rate_from_history takes that cameo because it is the
    newest season with any minutes at all, and shrinkage then dissolves it into
    the position prior; the profile skips it for the last full season the player
    actually played, which is real evidence about his defensive role.

    A profile whose DefCon rate is ZERO is not believed, and falls back to the
    entry. FPL only began recording `defensive_contribution` in 2024/25, so every
    earlier season reports 0 for everyone (verified 2026-08-04: all 588 backfill
    seasons of 450+ minutes before 2024/25 are zero) -- and an outfielder who
    truly logged no CBIT action in a 450-minute season does not exist. Taking
    that 0 literally is a real regression, not a hypothetical: it dropped Endo,
    a defensive midfielder, from 9.59 to 1.08 by profiling his 2023/24 season
    instead of his recent, actually-recorded minutes.
    """
    if player.get("position") == "GK":
        return 0.0
    live = player.get("defcon_per90") or 0.0
    if live:
        return live
    position = player.get("position", "MID")
    if profile and (profile.get("defcon_per90") or 0.0) > 0:
        return shrink_defcon_rate(position, profile["defcon_per90"],
                                  profile.get("minutes") or 0)
    if not backfill:
        return 0.0
    entry = backfill.get(player.get("id"))
    if not entry:
        return 0.0
    observed = entry.get("defcon_per90") or 0.0
    minutes = entry.get("minutes") or 0
    return shrink_defcon_rate(position, observed, minutes)


def build_with_flags(players: list[dict], team_matches: int,
                     defcon_backfill: dict[int, dict] | None = None
                     ) -> tuple[dict[str, list], list[dict]]:
    """Build priors grouped by club, plus a list of cold-start flags for preflight.

    Shares are normalised WITHIN a club: the engine allocates a team's simulated
    goals among its own players, so what matters is a player's share of his club's
    attacking output, not an absolute rate. Shares need not sum to 1 — the engine
    treats the remainder as unmodelled teammates.

    `defcon_backfill` is optional -- see `_defcon_rate` for the precedence rule
    (live bootstrap data always wins over it). Existing callers that don't pass it
    are unaffected: they get bootstrap's own defcon_per90 (0.0 preseason) exactly
    as before.

    Each backfill entry also carries that player's `history_past`, from which
    `history_profile` derives one last full season. It reaches exactly two prior
    inputs, both of them where bootstrap has nothing to say:

      - the minutes model, only when bootstrap shows no minutes at all, and only
        from a season recent enough to still describe the player's role (see
        minutes_model and config.FPL_HISTORY_MAX_SEASONS_BACK)
      - the DefCon rate, choosing the season to measure (see _defcon_rate)

    It deliberately does NOT touch goal_share/assist_share: those come from
    bootstrap's xG/xA per-90s, which are this engine's chosen attacking source
    (see the module docstring), and a last-season points-per-start would be a
    worse, scoring-contaminated substitute. The profile's clean_sheet_rate /
    conceded_per90 / xgc_per90 are computed but intentionally unused here: clean
    sheets are simulated from the FIXTURE's team lambdas, so feeding a player's
    old club's defensive record into his prior would double-count the club, and
    be flatly wrong for a player who has since transferred.

    Mutates `players` to disambiguate colliding names before anything else reads
    them -- see `_disambiguate_names`.
    """
    _disambiguate_names(players)

    by_team: dict[str, list] = {}
    flags: list[dict] = []

    grouped: dict[str, list] = {}
    for p in players:
        grouped.setdefault(p["team"], []).append(p)

    latest_year = latest_season_year(defcon_backfill)

    for team, squad in grouped.items():
        weighted = []
        for p in squad:
            entry = (defcon_backfill or {}).get(p.get("id")) or {}
            profile = history_profile(entry.get("history_past"))
            # The minutes model only accepts a RECENT season (see config); the
            # DefCon rate accepts any, being a shrunk, stable trait.
            fresh = profile if profile_is_recent(profile, latest_year) else None
            start_prob, exp_minutes = minutes_model(p, team_matches, fresh)
            xg90, xa90 = _rates(p)
            if needs_cold_start(p):
                flags.append({"name": p["name"], "team": team,
                              "reason": "no_pl_history"})
            weighted.append((p, start_prob, exp_minutes, xg90, xa90, profile))

        # Normalise to shares of the club's expected output, weighting each player's
        # rate by how much of the pitch time he is expected to occupy.
        goal_mass = sum(sp * xg for _p, sp, _m, xg, _xa, _pr in weighted) or 1.0
        assist_mass = sum(sp * xa for _p, sp, _m, _xg, xa, _pr in weighted) or 1.0

        priors = []
        for p, start_prob, exp_minutes, xg90, xa90, profile in weighted:
            priors.append(ratings.PlayerPrior(
                name=p["name"], team=team, position=p["position"],
                start_prob=start_prob, exp_minutes=exp_minutes,
                goal_share=(xg90 / goal_mass) if xg90 else 0.0,
                assist_share=(xa90 / assist_mass) if xa90 else 0.0,
                sot_per90=0.0,          # FPL does not score shots on target
                pen_taker=bool(p.get("pen_taker")),
                defcon_per90=_defcon_rate(p, defcon_backfill, profile),
                saves_per90=p.get("saves_per90") or 0.0,
            ))
        by_team[team] = priors

    return by_team, flags


def build(players: list[dict], team_matches: int,
         defcon_backfill: dict[int, dict] | None = None) -> dict[str, list]:
    """build_with_flags without the flags, for callers that don't need preflight."""
    by_team, _flags = build_with_flags(players, team_matches, defcon_backfill)
    return by_team
