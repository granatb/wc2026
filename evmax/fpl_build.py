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

import json
import os
import shutil
from datetime import datetime, timezone

from core import fixtures, fpl_api, fpl_live, research, simcache
from evmax import fpl_articles, fpl_players, render, writer
from games.fpl import model as fpl_model

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
    # GW-stage only: World Cup fixtures share fantasy_round numbers with FPL
    # gameweeks in the shared SCHEDULE, and warning about an unpriced June
    # World Cup fixture on an FPL build is noise that trains the operator to
    # ignore the warning that matters.
    fx = [f for f in fixtures.by_round(gameweek) if getattr(f, "stage", "GW") == "GW"]
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


def dossier_gate(gameweek: int, states: dict, all_players: list,
                 priors_by_team: dict, boot: dict) -> None:
    """The publish gate (spec D1): abort unless every red-flagged player in
    BOTH published squads is covered by a sourced, dated research note.

    Applies to OPEN gameweeks only: once a gameweek is graded (its accuracy
    record exists under evmax/assets/accuracy/), it is frozen history and a
    rebuild must not be re-judged against a LATER feed snapshot — round-scoped
    notes cannot answer for events that happened after the deadline. The gate
    protects new claims, not archives.

    Assembles a dossier for every squad member (games/fpl/dossier) from the
    live bootstrap, the priors' start probabilities and the feed-snapshot
    flags (core/fpl_diff), then refuses the build listing every failing
    dossier verbatim. There is deliberately NO --force-publish escape hatch:
    the GW1 failures happened precisely because validation was skippable
    under deadline pressure. The fix is a note under research/players/ with
    non-empty sources (or changing the squad), never a flag.
    """
    from core import fpl_diff
    from games.fpl import dossier

    notes = research.load_entries("players", gameweek)
    start_probs = {}
    for squad in priors_by_team.values():
        for p in squad:
            start_probs[p.name] = p.start_prob

    prev = fpl_diff.load_previous()
    captured_teams = ({pid: row["team_short"] for pid, row in prev.items()
                       if pid != "taken_at"} if prev else None)
    snapshot_date = ((prev or {}).get("taken_at") or "")[:10] or None
    outflow_ids = {s["id"]
                   for s in fpl_diff.outflow_spikes(fpl_diff.snapshot(boot))}

    problems = []
    for key, state in states.items():
        dossiers = dossier.assemble(state, all_players, start_probs, notes,
                                    captured_teams=captured_teams,
                                    outflow_ids=outflow_ids)
        _ok, failures = dossier.gate(dossiers, notes,
                                     snapshot_date=snapshot_date)
        for f in failures:
            problems.append(f"{state.get('team_name', key)}: {f['name']} — "
                            + "; ".join(f["reasons"]))
    if problems:
        raise SystemExit(
            "evmax fpl build preflight failed — the publish gate refuses "
            "red-flagged players without an overriding note (a file under "
            "research/players/ with non-empty sources: and updated: on/after "
            "the feed snapshot). Research each player, write the note or "
            "change the squad, re-run:\n- " + "\n- ".join(problems))


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


# ---------------------------------------------------------------------------
# The gameweek build pipeline
# ---------------------------------------------------------------------------

# Order is load-bearing: it is the /api/latest.json + llms.txt + sitemap nav
# order AND the landing feed order (minus the hero). our-squad leads (the hero,
# owner decision 2026-08-19), captains is the #2 surface, the consensus squad
# sits beside them, then the supporting cast.
ARTICLES = ["our-squad", "captains", "consensus-squad", "wildcard", "ticker",
            "defenders", "efficiency", "defcon"]

# The two slugs whose entries come from a published squad state rather than a
# ranking over the full player pool.
SQUAD_SLUGS = ("our-squad", "consensus-squad")

# slug -> the state/grade key its live panel reads.
SQUAD_LIVE_KEYS = {"our-squad": "model", "consensus-squad": "consensus"}

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILES = {
    "model": os.path.join(_ROOT, "games", "fpl", "state.json"),
    "consensus": os.path.join(_ROOT, "games", "fpl", "state_consensus.json"),
}

ARTICLE_TITLES = {
    # Short: the <title> becomes "{title} — Gameweek N | evmax" and Bing errors
    # above ~65 characters.
    "our-squad": "Our squad",
    "consensus-squad": "The consensus XI",
    "captains": "Best captain picks",
    "wildcard": "Draft squad & wildcard XI",
    "ticker": "Fixture ticker — clean sheets",
    "defenders": "Best defenders & keepers",
    "efficiency": "Best value — points per million",
    "defcon": "DefCon leaders",
}

_COLUMNS = {
    "our-squad":       ["x_points", "ceiling", "captain_ev", "value"],
    "consensus-squad": ["x_points", "ceiling", "captain_ev", "value"],
    "captains":   ["captain_ev", "x_points", "ceiling", "price", "ownership_pct"],
    "wildcard":   ["x_points", "price", "captain_ev", "ceiling", "ownership_pct"],
    "ticker":     ["exp_clean_sheets", "exp_goals_for", "exp_goals_against",
                   "fixtures", "basis"],
    "defenders":  ["x_points", "cs_points", "defcon", "bonus", "price"],
    "efficiency": ["value", "x_points", "price", "ownership_pct", "ceiling"],
    "defcon":     ["p_defcon", "defcon", "x_points", "price", "ownership_pct"],
}

# Articles whose chart metric is points-denominated get the floor+ceiling reach
# bar. value (pts/million), p_defcon (a probability) and exp_clean_sheets (a
# count) are different units — mixing raw ceiling points into those bars would be
# dimensionally wrong. captains charts captain_ev, so its ceiling companion needs
# the same doubling to land on the same scale.
_CEILING_PAIRED_METRIC = {
    "captains":  ("captain_ev", 2.0),
    "defenders": ("x_points", 1.0),
}

_ARTICLE_VIZ_MAX_ROWS = 10
_FEATURED_VIZ_MAX_ROWS = 8


def load_states(players: list) -> dict:
    """Both published squad states, validated against the live bootstrap.

    Part of preflight in spirit: an illegal, misspelled or ambiguous published
    squad aborts the build — the two state files are frozen public claims, and
    a squad page must never degrade into a partial team.
    """
    from games.fpl import state as fpl_state

    out = {}
    problems = []
    for key, path in STATE_FILES.items():
        try:
            out[key] = fpl_state.load_squad(path, players)
        except (OSError, ValueError, KeyError) as e:
            problems.append(f"{os.path.relpath(path, _ROOT)}: {e}")
    if problems:
        raise SystemExit("evmax fpl build preflight failed:\n- " +
                         "\n- ".join(problems))
    return out


def _live_default(gameweek: int, boot, now=None) -> bool:
    """--live's auto mode: on mid-gameweek, off otherwise.

    "Mid-gameweek" means the bootstrap marks this gameweek current AND the
    fixtures cache shows at least one started fixture. Reads the caches only,
    never the network — a plain `--gw N` build stays offline-reproducible, and
    the tests stay offline with it. The pre-season/pre-deadline case (is_next,
    nothing kicked off) is correctly False on both counts.
    """
    event = next((e for e in (boot or {}).get("events", [])
                  if e.get("id") == gameweek), None)
    if not event or not event.get("is_current"):
        return False
    fx = [f for f in (fpl_api.read_cache("fixtures") or [])
          if f.get("event") == gameweek]
    return fpl_live.any_fixture_started(fx, now=now)


def live_layer(gameweek: int, states: dict, boot: dict,
               refresh: bool) -> tuple:
    """Grade both published squads against the live feed.

    refresh=True (an explicit --live) fetches both live endpoints and
    OVERWRITES data/fpl/live_gw{N}.json, falling back to the cached payload
    with a loud warning if the network fails; refresh=False (auto mode) reads
    the cache only. Returns ({"model": grade, "consensus": grade,
    "fetched_at": iso} | None, warnings) — None means the layer is skipped
    (no data at all in auto mode), and the landing/panels simply omit the
    live surfaces.

    A state name that no longer resolves against the bootstrap ABORTS the
    build in preflight's voice: grade_squad already fails loudly listing every
    unresolved name, and publishing a 14-man "so far" total would be a wrong
    public claim, not a degraded one.
    """
    warnings = []
    payload = None
    if refresh:
        try:
            payload = fpl_live.refresh_live(gameweek)
        except Exception as exc:  # noqa: BLE001 — any network failure, same fallback
            warnings.append(
                f"LIVE REFRESH FAILED ({exc}) — falling back to the cached "
                f"live payload; the panel timestamp shows how stale it is.")
    if payload is None:
        payload = fpl_live.read_live_cache(gameweek)
    if payload is None:
        message = (f"no live payload for gameweek {gameweek} — refresh with\n"
                   f"    python3 -m evmax.build --gw {gameweek} --live")
        if refresh:
            raise SystemExit(f"evmax fpl build --live failed:\n- {message}")
        warnings.append(f"LIVE LAYER SKIPPED: {message}")
        return None, warnings

    out = {"fetched_at": payload.get("fetched_at", "")}
    try:
        for key in ("model", "consensus"):
            out[key] = fpl_live.grade_squad(states[key], payload.get("live", {}),
                                            payload.get("fixtures", []), boot)
    except ValueError as e:
        raise SystemExit(f"evmax fpl build live layer failed:\n- {e}")
    return out, warnings


def _article_entries(rows: list, matches: list, clubs: list,
                     states: dict, note_names=frozenset()) -> tuple:
    """({slug: entries}, {slug: squad meta}) — the meta dicts (wildcard's draft
    squad plus the two published squads) are not flat lists, so they travel
    separately into the JSON envelopes and the landing duel."""
    # Per-club fixture counts from the match summaries, stamped on every
    # player row: bonus/defcon/cs_points are per-MATCH quantities while
    # x_points is per-WEEK (games/fpl/model._derive_row), and the prose may
    # frame the former as components of the latter only for a single-fixture
    # player. TODO(pre-first-DGW): retire with the per-sim column rework
    # (review 2026-08-19, finding 7).
    fixture_counts: dict = {}
    for m in matches:
        for team in (m["home"], m["away"]):
            fixture_counts[team] = fixture_counts.get(team, 0) + 1
    rows = [dict(r, fixtures=fixture_counts.get(r.get("team"), 0))
            for r in rows]
    our_entries, our_meta = fpl_articles.squad_article(states["model"], rows)
    cons_entries, cons_meta = fpl_articles.squad_article(states["consensus"],
                                                         rows)
    # Stamped here because only the build holds BOTH squads: the our-squad
    # prose may say "the consensus XI on this site owns him" about Haaland
    # only while that is checkably true (review 2026-08-19, finding 5).
    owns_haaland = any(e["name"] == "Haaland" for e in cons_entries)
    for e in our_entries:
        e["consensus_owns_haaland"] = owns_haaland
    # Optimizer v2 (spec D6): the wildcard/draft builder honours the minutes
    # floor via the rows' start_prob, overridable only by a sourced note.
    squad_entries, squad_meta = fpl_articles.fpl_squad(rows, notes=note_names)
    entries_map = {
        "our-squad":       our_entries,
        "consensus-squad": cons_entries,
        # captains slices to its published top-20 itself: kickoff_order is a
        # dense rank over the published slice's distinct kickoff instants, so
        # the slice and the ranking must happen together.
        "captains":   fpl_articles.captains(rows, top=20),
        "wildcard":   squad_entries,
        "ticker":     fpl_articles.ticker(matches, clubs),
        "defenders":  fpl_articles.defenders(rows)[:20],
        "efficiency": fpl_articles.efficiency(rows)[:20],
        "defcon":     fpl_articles.defcon_leaders(rows)[:20],
    }
    metas = {"wildcard": squad_meta, "our-squad": our_meta,
             "consensus-squad": cons_meta}
    return entries_map, metas


def entries_or_abort(rows: list, matches: list, clubs: list,
                     states: dict, note_names=frozenset()) -> tuple:
    """_article_entries, converting article-layer ValueErrors into the same
    clean SystemExit the rest of preflight speaks. The main offender is a state
    name with no artifact row (name drift / stale bootstrap) — spec-level
    preflight: "every state name matches the artifact rows"."""
    try:
        return _article_entries(rows, matches, clubs, states, note_names)
    except ValueError as e:
        raise SystemExit(f"evmax fpl build preflight failed:\n- {e}")


def squad_preflight(metas: dict) -> None:
    """Abort unless both published squads' projected totals are finite numbers.

    A NaN or infinity here means a poisoned artifact row (a price of 0 turned
    into an infinite value, a broken simulation mean) and would otherwise
    publish "nan" into the hero, the duel strip and two JSON feeds at once.
    """
    import math

    problems = []
    for slug in SQUAD_SLUGS:
        meta = metas.get(slug)
        if meta is None:
            problems.append(f"{slug}: no squad meta was produced")
            continue
        for key in ("xi_xpoints", "projected_total"):
            v = meta.get(key)
            if not isinstance(v, (int, float)) or isinstance(v, bool) \
                    or not math.isfinite(v):
                problems.append(f"{slug}: {key} is {v!r} — not a finite number")
    if problems:
        raise SystemExit("evmax fpl build preflight failed:\n- " +
                         "\n- ".join(problems))


def build(gameweek: int, sims: int = 50_000, out: str = "dist",
          url: str = "https://evmax.ai", use_llm: bool = True,
          use_cache: bool = True, cache_dir: str = "data/articles",
          live=None, player_pages_cap=None) -> None:
    """live: True = refresh the live feed and render the so-far layer;
    False = force it off; None (default) = auto — on mid-gameweek from the
    cached payload only (see _live_default / live_layer).

    player_pages_cap: TESTS ONLY — cap how many per-player pages/JSONs are
    written (the top N by x_points), so the end-to-end smoke build never pays
    for 563 pages. None (production) writes every player. The index and tier
    boards list the same capped set, so a capped build never links a page it
    did not write."""
    render.SITE_URL = url
    section = render.FPL
    generated_at = datetime.now(timezone.utc).isoformat()
    date_str = _format_date(generated_at)

    priors_by_team, players_by_name, cold_start = fpl_model.load_gameweek(gameweek)
    boot = fpl_api.read_cache("bootstrap")
    all_players = fpl_api.parse_players(boot) if boot else []

    warnings = preflight(gameweek, all_players, cold_start)
    states = load_states(all_players)
    # The publish gate (spec D1): no red-flagged player ships without a
    # sourced note. Runs on BOTH squads before any simulation is spent.
    _acc = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "evmax", "assets", "accuracy", f"gw{gameweek}.json")
    if os.path.exists(_acc):
        print(f"  [fpl] gameweek {gameweek} is graded history — publish gate "
              f"applies to open gameweeks only, skipping")
    else:
        dossier_gate(gameweek, states, all_players, priors_by_team, boot)

    # The live "so far" layer (phase 4c): realized points NEXT TO the frozen
    # projections. Article bodies stay frozen — live data reaches exactly two
    # surfaces, the landing duel strip and the squad pages' panel block.
    live_on = live if live is not None else _live_default(gameweek, boot)
    live_data = None
    if live_on:
        live_data, live_warnings = live_layer(gameweek, states, boot,
                                              refresh=(live is True))
        warnings += live_warnings

    artifact, cache_hit = fpl_model.build_artifact(
        priors_by_team, players_by_name, gameweek, sims, use_cache=use_cache)
    warnings += cache_warnings(gameweek, cache_hit)
    rows, matches = artifact["rows"], artifact["matches"]
    if not rows:
        raise SystemExit(
            f"evmax fpl build: the simulation produced no players for gameweek "
            f"{gameweek} — the priors are empty, which usually means the bootstrap "
            f"cache is stale. Refresh with `python3 manage.py fpl --round "
            f"{gameweek} --refresh`.")

    # Thread each row's start probability in from the priors (optimizer v2's
    # minutes floor reads it) — rows are keyed by the same disambiguated
    # names the priors carry, whether they came fresh from the sim or from
    # the artifact cache (which predates this column).
    start_probs = {p.name: p.start_prob
                   for squad in priors_by_team.values() for p in squad}
    rows = [dict(r, start_prob=start_probs.get(r["name"])) for r in rows]
    # Names with a SOURCED research note may override the optimizer's floor —
    # the same bar the publish gate holds (a source-less note vouches for
    # nothing).
    note_names = {name for name, e
                  in research.load_entries("players", gameweek).items()
                  if e.sources}

    clubs = sorted({p["team"] for p in all_players}) or sorted(priors_by_team)
    entries_map, metas = entries_or_abort(rows, matches, clubs, states,
                                          note_names)
    squad_preflight(metas)

    # /fpl/gw{N}/ pages accumulate the same way the WC's /round/{N}/ ones do:
    # build() never clears `out`, so past gameweeks persist and the switcher is
    # generated from what is actually on disk.
    gw_root = os.path.join(out, "fpl")
    available = sorted(
        {int(d[2:]) for d in os.listdir(gw_root)
         if d.startswith("gw") and d[2:].isdigit()} | {gameweek}
    ) if os.path.isdir(gw_root) else [gameweek]

    def w(path: str, text: str) -> None:
        full = os.path.join(out, path.lstrip("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)

    # --- Player cards (STRATEGY §12 phase 1): assemble every player's payload
    # from the artifact + bootstrap + notes + horizon matrix + odds caches.
    # Assembled BEFORE the bulk feed so the feed can carry each player's page.
    notes = research.load_entries("players", gameweek)
    squad_names = {key: {e["name"] for e in entries_map[slug]}
                   for slug, key in SQUAD_LIVE_KEYS.items()}
    fx_rows_all = fpl_api.parse_fixtures(fpl_api.read_cache("fixtures") or [],
                                         fpl_api.parse_teams(boot or {}))
    payloads, unmatched = fpl_players.assemble_payloads(
        rows, players_by_name, {e["id"]: e for e in (boot or {}).get("elements", [])},
        notes, squad_names, _load_horizon_matrix(), fx_rows_all,
        _odds_caches(gameweek), gameweek, generated_at)
    if unmatched:
        names = ", ".join(unmatched[:6]) + (" ..." if len(unmatched) > 6 else "")
        warnings.append(
            f"{len(unmatched)} ARTIFACT ROW(S) WITHOUT A BOOTSTRAP MATCH — no "
            f"player page/JSON for: {names}. A cached artifact predating a "
            f"rename usually explains it; refresh and rebuild.")
    if player_pages_cap is not None:
        payloads = payloads[:player_pages_cap]
    page_by_name = {p["name"]: p["page"] for p in payloads}

    # --- Bulk players feed. Same guardrail as the World Cup's: derived model
    # outputs and name/team/position ONLY. No price, no ownership — those stay
    # per-player context inside articles, never in the public bulk feed.
    # `page` is each player's card page (the /fpl/players/ search links it).
    w(section.players_json_path(gameweek), json.dumps({
        "gameweek": gameweek,
        "generated_at": generated_at,
        "methodology": section.methodology,
        "license": render.DATA_LICENSE_URL,
        "players": [
            {"name": r["name"], "team": r.get("team"),
             "position": r.get("position"), "x_points": r["x_points"],
             "captain_ev": r["captain_ev"], "ceiling": r["ceiling"],
             "kickoff": r.get("kickoff"),
             "flag": _player_flag(r["name"], notes),
             "page": page_by_name.get(r["name"])}
            for r in rows
        ],
    }, ensure_ascii=False, indent=2))

    # --- Player pages + per-player JSON + index + tier boards. Living
    # surfaces like the landing: regenerated every gameweek, never frozen.
    for p in payloads:
        w(fpl_players.json_path(gameweek, p["id"]), json.dumps(
            fpl_players.player_json(p, section.methodology, url,
                                    render.DATA_LICENSE_URL,
                                    render.DATA_LICENSE_TEXT),
            ensure_ascii=False, indent=2))
        w(f"{fpl_players.page_path(p['slug'])}index.html",
          fpl_players.player_page_html(p, gameweek, date_str=date_str,
                                       methodology=section.methodology))
    w(f"{fpl_players.PLAYERS_BASE}/index.html",
      fpl_players.index_page_html(payloads, gameweek,
                                  section.players_json_path(gameweek),
                                  date_str=date_str))
    for pos, _seg in fpl_players.TIER_SEGMENTS:
        w(f"{fpl_players.tier_path(pos)}index.html",
          fpl_players.tier_page_html(pos, payloads, gameweek,
                                     date_str=date_str))

    prose_map: dict = {}
    used_leads: set = set()
    is_production = os.path.basename(os.path.normpath(out)) == "dist"
    # FPL's own pre-deadline projection, frozen into the snapshot archive so
    # the Monday grading (scripts/grade_gw.py) has its benchmark. Keyed by
    # the DISAMBIGUATED names the rows carry (players_by_name is the
    # load_gameweek parse, post-disambiguation).
    ep_by_name = {name: p.get("ep_next")
                  for name, p in players_by_name.items()}

    for slug in ARTICLES:
        entries = entries_map[slug]
        columns = _COLUMNS[slug]
        title = f"{ARTICLE_TITLES[slug]} — Gameweek {gameweek}"
        json_url = section.json_path(gameweek, slug)

        if slug in ("wildcard", "ticker") or slug in SQUAD_SLUGS:
            subject = None            # squad- and club-framed, no lead player
        else:
            subject = next((e["name"] for e in entries
                            if e["name"] not in used_leads),
                           entries[0]["name"] if entries else None)
            if subject:
                used_leads.add(subject)

        prose = writer.article_prose(slug, gameweek, entries, columns,
                                     cache_dir=cache_dir, use_llm=use_llm,
                                     subject=subject,
                                     cache_name=f"fpl-gw{gameweek}",
                                     unit="Gameweek")
        prose_map[slug] = prose

        if slug == "wildcard" or slug in SQUAD_SLUGS:
            viz_html = render.pitch_svg_fpl([e for e in entries
                                         if e.get("role") == "XI"])
        else:
            pair = _CEILING_PAIRED_METRIC.get(slug)
            if pair:
                metric, scale = pair
                viz_html = render.ev_bar(entries, metric,
                                         max_rows=_ARTICLE_VIZ_MAX_ROWS,
                                         reach_metric="ceiling", reach_scale=scale)
            else:
                viz_html = render.ev_bar(entries, columns[0],
                                         max_rows=_ARTICLE_VIZ_MAX_ROWS)

        extra = {"squad": metas[slug]} if slug in metas else None
        env = render.article_json("fantasy_premier_league", gameweek, slug, title,
                                  generated_at, sims, entries,
                                  extra_fields=extra, section=section)
        env_json = json.dumps(env, ensure_ascii=False, indent=2)
        w(json_url, env_json)

        # Point-in-time projection archive — the ground truth the backtest harness
        # will grade from GW1 forward (spec §7.4). Two guards, same as the World
        # Cup's: production builds only, and only while the gameweek is still open,
        # so a post-hoc rebuild cannot contaminate a published claim.
        lock = fixtures.round_lock_time(gameweek)
        if is_production and (lock is None or datetime.now(timezone.utc) < lock):
            snap_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "assets", "projections", f"fpl-gw{gameweek}")
            os.makedirs(snap_dir, exist_ok=True)
            # The SNAPSHOT copy additionally freezes FPL's own ep_next per
            # player (task 6) — the accuracy grading's benchmark. The public
            # /api envelope above stays exactly as rendered; GW1's committed
            # snapshots predate this and are frozen history (never
            # regenerated — the open-gameweek guard on this branch is what
            # makes that mechanical).
            from games.fpl import grading
            env_snap = grading.stamp_ep_next(env, ep_by_name)
            with open(os.path.join(snap_dir, f"{slug}.json"), "w",
                      encoding="utf-8") as fh:
                fh.write(json.dumps(env_snap, ensure_ascii=False, indent=2))

        # Squad pages get the realized-points panel ABOVE the frozen prose when
        # live data is in play; every other byte of every article stays frozen
        # (live_html="" renders byte-identical pages — tested).
        live_html = ""
        if live_data and slug in SQUAD_LIVE_KEYS:
            live_html = render.squad_live_panel_html(
                live_data[SQUAD_LIVE_KEYS[slug]], live_data["fetched_at"])
        w(f"{section.base.format(r=gameweek)}/{slug}/index.html",
          render.article_page(gameweek, slug, title, prose, entries, columns,
                              json_url, viz_html, generated_at=generated_at,
                              date_str=date_str, available_rounds=available,
                              section=section, live_html=live_html))
        w(section.md_path(gameweek, slug),
          render.article_md(gameweek, slug, title, prose, entries, columns,
                            generated_at, date_str,
                            canonical_path=section.article_path(gameweek, slug),
                            section=section))

    # --- Static pages and assets (shared with the World Cup section) ----------
    w("/about/index.html", render.about_page())
    w("/privacy/index.html", render.privacy_page())
    w("/thanks/index.html", render.thanks_page())
    w("/confirmed/index.html", render.confirmed_page())
    # /rate/ serves whichever section built last; a gameweek build gives it FPL
    # copy and points it at this gameweek's players feed (the JS is shared).
    w("/rate/index.html", render.rate_page(gameweek, section=section))
    # Root-level shared chrome (GSC verification, /_redirects, /track-record/):
    # a deploy replaces the whole tree, and this build's own nav and sitemap
    # point at /track-record/, so omitting these would strip them from the live
    # site on every gameweek publish. Imported lazily — evmax.build imports
    # this module at load time, so a module-level import back would be a cycle.
    from evmax.build import write_site_chrome
    write_site_chrome(w, fpl_ledger=fpl_track_ledger())
    _publish_accuracy(w)
    _copy_assets(out)

    # --- Landing -------------------------------------------------------------
    # Owner decision 2026-08-19: our-squad is the hero, captains the #2 surface
    # (first feed card, via ARTICLES order), the rest the supporting feed.
    featured = {
        "slug": "our-squad",
        "prose": prose_map["our-squad"],
        "viz_html": render.pitch_svg_fpl([e for e in entries_map["our-squad"]
                                      if e.get("role") == "XI"]),
    }
    feed = []
    for slug in ARTICLES:
        if slug == "our-squad":
            continue
        entries, columns = entries_map[slug], _COLUMNS[slug]
        if slug in SQUAD_SLUGS:
            # A squad card's number is the team's projected total (captain
            # doubled), not the first table column of its first player.
            stat_value = f"{metas[slug]['projected_total']:.2f}"
            stat_label = "Projected XI, captain doubled"
        else:
            top = entries[0] if entries else {}
            stat_value = render._fmt(columns[0], top)
            stat_label = render._COL_LABEL.get(columns[0], columns[0])
        feed.append({
            "slug": slug,
            "headline": prose_map[slug]["headline"],
            "teaser": prose_map[slug]["standfirst"],
            "stat_value": stat_value,
            "stat_label": stat_label,
        })

    # The model-vs-consensus duel strip: the two squads' own article meta, no
    # new simulation — plus, mid-gameweek, each side's REALIZED total so far
    # from the live layer, rendered next to (never instead of) the projection.
    duel = {"model": metas["our-squad"], "consensus": metas["consensus-squad"]}
    if live_data:
        duel["live"] = live_data
    landing = render.landing_page(gameweek, featured, feed, date_str=date_str,
                                  fixtures=matches, available_rounds=available,
                                  duel=duel, section=section,
                                  pre_content_html=fpl_players.top_cards_html(
                                      payloads),
                                  extra_style=(fpl_players.CARD_CSS +
                                               fpl_players.TOP_CARDS_CSS +
                                               render._NAV_SCROLL_CSS))
    w(f"{section.base.format(r=gameweek)}/index.html", landing)
    # Owner decision 2026-07-30: FPL takes the root. The World Cup tree under
    # /round/N/ is untouched and stays live (spec D5) — its landing survives at
    # /round/8/ — but GW1 is the year's largest FPL search peak and the root
    # belongs to the live competition.
    w("/index.html", landing)

    # --- Agent / meta files --------------------------------------------------
    nav = [(slug, ARTICLE_TITLES[slug]) for slug in ARTICLES]
    w("/api/latest.json", json.dumps(
        {"gameweek": gameweek, "generated_at": generated_at,
         "articles": {s: section.json_path(gameweek, s) for s in ARTICLES}},
        ensure_ascii=False, indent=2))
    w("/llms.txt", render.llms_txt(gameweek, nav, section=section,
                                   extra_lines=_llms_player_lines(
                                       gameweek, len(payloads), url)))
    w("/robots.txt", render.robots_txt())
    w("/sitemap.xml", render.sitemap_xml(gameweek, nav, lastmod=generated_at[:10],
                                         section=section,
                                         extra_urls=_persisted_urls(out,
                                                                    gameweek)))

    for line in warnings:
        print(f"\n!!! {line}\n")
    suffix = (f" | !!! {len(warnings)} WARNING(S) — see above / rerun without "
              f"filters" if warnings else "")
    print(f"Built FPL gameweek {gameweek} → {out}/ "
          f"({len(rows)} players, {len(ARTICLES)} articles, "
          f"{len(payloads)} player pages, "
          f"sim cache {'HIT' if cache_hit else 'MISS'}){suffix}")


def format_state(state: dict) -> str:
    """games/fpl/*.json house style: top-level keys one per line, each squad
    entry on its own line, diacritics unescaped — the files are hand-reviewed
    published claims, and a review diff must read player-per-line."""
    lines = ["{"]
    for key in (k for k in state if k != "squad"):
        lines.append(f'  {json.dumps(key)}: '
                     f'{json.dumps(state[key], ensure_ascii=False)},')
    lines.append('  "squad": [')
    lines.append(",\n".join(f'    {json.dumps(e, ensure_ascii=False)}'
                            for e in state["squad"]))
    lines.append("  ]")
    lines.append("}")
    return "\n".join(lines) + "\n"


def reset_consensus(gameweek: int, out_path: str = None) -> str:
    """Rebuild state_consensus.json as the most-owned legal template — the
    squad's declared Wildcard (owner decision 2026-08-24, from GW2).

    Owner-triggered before the deadline via
        python3 -m evmax.build --gw N --reset-consensus
    NEVER run by the site build: it rewrites a published state file, and that
    is an editorial act, not a rendering one. Validates the rebuilt squad via
    games/fpl/state.py against the same bootstrap before writing — an illegal
    template aborts and leaves the current file untouched.
    """
    from games.fpl import consensus
    from games.fpl import state as fpl_state

    boot = fpl_api.read_cache("bootstrap")
    if boot is None:
        raise SystemExit(
            "consensus reset failed:\n- data/fpl/bootstrap.json is missing — "
            "populate the cache with\n"
            f"    python3 manage.py fpl --round {gameweek} --refresh\n"
            "  (the reset needs CURRENT ownership, so refresh right before "
            "running it)")
    players = fpl_api.parse_players(boot)
    try:
        state = consensus.build_consensus_state(players, gameweek)
        fpl_state.validate_state(state, players)
    except ValueError as e:
        raise SystemExit(f"consensus reset failed:\n- {e}")
    path = out_path or STATE_FILES["consensus"]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(format_state(state))
    captain = next(e["name"] for e in state["squad"] if e["is_captain"])
    print(f"Consensus XI reset for gameweek {gameweek} → {path} "
          f"({captain} (c), wildcard declared). Review the diff, then rebuild "
          f"with `python3 -m evmax.build --gw {gameweek}` before the deadline.")
    return path


def _persisted_urls(out: str, current_gameweek: int) -> list:
    """Every page already on disk that this build does not re-list itself: the
    World Cup tree AND previously built FPL gameweeks.

    Those URLs are still live and still indexed (spec D5 for the WC tree; past
    gameweeks accumulate the same way past rounds do). A sitemap that drops
    them reads to a crawler as a request to deindex them — building GW2 must
    not take every GW1 page (or the track record's own evidence) out of search.

    The gameweek being built is excluded here because sitemap_xml adds its
    pages explicitly via nav; listing it again would duplicate every URL. The
    exclusion matches the exact gw path segment so a gw2 build keeps gw20.
    """
    current_segment = f"gw{current_gameweek}"
    urls = []
    for sub in ("round", "fpl"):
        root = os.path.join(out, sub)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, filenames in os.walk(root):
            if "index.html" not in filenames:
                continue
            rel = os.path.relpath(dirpath, out).replace(os.sep, "/")
            parts = rel.split("/")
            if parts[0] == "fpl" and (len(parts) < 2
                                      or parts[1] == current_segment):
                continue
            urls.append(f"/{rel}/")
    return sorted(urls)


def _player_flag(name: str, notes: dict):
    """out / doubtful / None — the same small public vocabulary the World Cup feed
    exposes. Imported rather than reimplemented so the two never drift."""
    from evmax.articles import player_flag
    return player_flag(name, notes)


def _llms_player_lines(gameweek: int, count: int, url: str) -> list:
    """The llms.txt player-cards section (render.llms_txt extra_lines)."""
    tiers = " · ".join(
        f"[{pos}]({url}{fpl_players.tier_path(pos)})"
        for pos, _seg in fpl_players.TIER_SEGMENTS)
    return [
        "## Player cards",
        f"- [Check your player — all {count} cards]"
        f"({url}{fpl_players.PLAYERS_BASE}/) — one living page per player "
        "(projection with decomposition, season so far, fixtures, verdict "
        "tier), regenerated every gameweek.",
        f"- Tier boards (S–D by position): {tiers}",
        f"- Per-player JSON: {url}/api/fpl/gw{gameweek}/players/"
        "{element_id}.json — element ids and page URLs are in the players "
        "feed below.",
    ]


def _load_horizon_matrix():
    """The newest six-week horizon matrix (data/fpl/xpts_gw*.json), or None.

    Same discovery rule as manage.py's fpl_transfers: the lexicographically
    last file wins. The matrix is regenerated by the weekly session; a fresh
    checkout has none (data/ is gitignored), and the player cards degrade
    gracefully — six_week_xpts renders null, never a guess."""
    import glob

    paths = sorted(glob.glob(os.path.join(_ROOT, "data", "fpl",
                                          "xpts_gw*.json")))
    if not paths:
        return None
    try:
        with open(paths[-1], encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _odds_caches(gameweek: int, horizon: int = 6) -> dict:
    """{gw: cached odds payload} for the fixture strips — cache reads only,
    NEVER the network (a plain build stays offline-reproducible). A missing
    gameweek cache simply prices that strip entry as "unpriced"."""
    from core import fpl_odds

    out = {}
    for gw in range(gameweek, gameweek + horizon):
        cached = fpl_odds.read_cached(gw)
        if cached:
            out[gw] = cached
    return out


def _format_date(generated_at: str) -> str:
    dt = datetime.fromisoformat(generated_at)
    try:
        return dt.strftime("%-d %B %Y")
    except ValueError:
        return dt.strftime("%d %B %Y").lstrip("0")


def _accuracy_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "assets", "accuracy")


def fpl_track_ledger() -> list:
    """The graded FPL ledger for /track-record/ (task 2026-08-25): one row per
    graded gameweek, straight from evmax/assets/accuracy/gw{N}.json — our MAE,
    ep_next's MAE where captured, both frozen squad projections against
    realized OFFICIAL points, and the running model-vs-crowd duel score (a
    gameweek goes to whichever squad realized more official points; a tie
    moves neither column). Rows also carry the public JSON path each grading
    file is published at (_publish_accuracy)."""
    acc_dir = _accuracy_dir()
    if not os.path.isdir(acc_dir):
        return []
    graded = []
    for fname in sorted(os.listdir(acc_dir)):
        if not (fname.startswith("gw") and fname.endswith(".json")
                and fname[2:-5].isdigit()):
            continue
        with open(os.path.join(acc_dir, fname), encoding="utf-8") as fh:
            graded.append((int(fname[2:-5]), json.load(fh)))
    graded.sort(key=lambda kv: kv[0])

    rows, model_wins, cons_wins = [], 0, 0
    for gw, acc in graded:
        squads = acc.get("squads", {})
        ours = squads.get("our-squad", {})
        cons = squads.get("consensus-squad", {})
        our_real = ours.get("realized_official")
        cons_real = cons.get("realized_official")
        if our_real is not None and cons_real is not None:
            if our_real > cons_real:
                model_wins += 1
            elif cons_real > our_real:
                cons_wins += 1
        if model_wins > cons_wins:
            label = "model leads"
        elif cons_wins > model_wins:
            label = "crowd leads"
        else:
            label = "level"
        rows.append({
            "gw": gw,
            "mae_ours": acc.get("mae_ours"),
            "mae_ep_next": acc.get("mae_ep_next"),
            "model_projected": ours.get("projected"),
            "model_realized": our_real,
            "consensus_projected": cons.get("projected"),
            "consensus_realized": cons_real,
            "duel_model": model_wins,
            "duel_consensus": cons_wins,
            "duel_label": label,
            "json_path": f"/api/fpl/accuracy/gw{gw}.json",
        })
    return rows


def _publish_accuracy(w) -> None:
    """Publish the committed grading JSONs verbatim — the ledger's method note
    says "grading JSONs public", so the FPL build ships every gw{N}.json at
    /api/fpl/accuracy/gw{N}.json, byte-for-byte what the repo grades against."""
    acc_dir = _accuracy_dir()
    if not os.path.isdir(acc_dir):
        return
    for fname in sorted(os.listdir(acc_dir)):
        if not (fname.startswith("gw") and fname.endswith(".json")
                and fname[2:-5].isdigit()):
            continue
        with open(os.path.join(acc_dir, fname), encoding="utf-8") as fh:
            w(f"/api/fpl/accuracy/{fname}", fh.read())


def _copy_assets(out: str) -> None:
    """Brand images, self-hosted fonts and the first-party JS. No third-party
    requests on load — the site's GDPR posture depends on it."""
    here = os.path.dirname(os.path.abspath(__file__))
    for src_name, dst_name, exts in (("brand", "brand", (".png", ".svg")),
                                     ("fonts", "fonts", (".woff2",)),
                                     ("js", "js", (".js",))):
        src = os.path.join(here, "assets", src_name)
        dst = os.path.join(out, dst_name)
        if not os.path.isdir(src):
            continue
        os.makedirs(dst, exist_ok=True)
        for fname in os.listdir(src):
            if fname.endswith(exts):
                shutil.copy2(os.path.join(src, fname), os.path.join(dst, fname))
