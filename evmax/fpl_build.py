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

import glob
import json
import os
import shutil
from datetime import datetime, timezone

from core import fixtures, fpl_api, fpl_horizon, research, simcache
from evmax import articles, fpl_articles, render, writer
from games.fpl import model

# ---------------------------------------------------------------------------
# The six FPL articles
# ---------------------------------------------------------------------------
# "runs" sits next to "ticker": both are planning views over the fixture list,
# one for this Saturday and one for the next six weeks, and a reader who lands
# on either should see the other one step away.
ARTICLES = ["captains", "wildcard", "ticker", "runs", "defenders", "efficiency",
            "defcon"]

ARTICLE_TITLES = {
    # Short: the <title> becomes "{title} — Gameweek N | evmax" and Bing errors
    # above ~65 characters.
    "captains": "Best captain picks",
    "wildcard": "Draft squad & wildcard XI",
    "ticker": "Fixture ticker — clean sheets",
    "runs": "Fixture ticker — the next six",
    "defenders": "Best defenders & keepers",
    "efficiency": "Best value — points per million",
    "defcon": "DefCon leaders",
}

_COLUMNS = {
    "captains":   ["captain_ev", "x_points", "ceiling", "price", "ownership_pct"],
    "wildcard":   ["x_points", "price", "captain_ev", "ceiling", "ownership_pct"],
    "ticker":     ["exp_clean_sheets", "exp_goals_for", "exp_goals_against",
                   "difficulty", "fixtures", "basis"],
    # Deliberately narrower than ticker's: the grid above the table already
    # carries the per-gameweek detail, so the flat table is the summary only.
    "runs":       ["exp_clean_sheets", "difficulty", "fixtures", "basis"],
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

# Articles that are squad- or club-framed rather than centred on one player. The
# prose layer takes subject=None for these: ticker's rows are clubs, so its
# "lead" is a three-letter abbreviation where a player's name belongs, and the
# wildcard piece is about the 15, not about whoever tops it.
_TEAM_FRAMED = {"wildcard", "ticker", "runs"}


def _gameweek_fixtures(gameweek: int) -> list:
    """This gameweek's PREMIER LEAGUE fixtures.

    core.fixtures.SCHEDULE is shared by both competitions and buckets purely on
    fantasy_round, so an unnarrowed by_round(1) returns World Cup round 1 AND FPL
    gameweek 1 — 24 finished World Cup ties alongside the 10 Premier League ones.
    `stage` is what separates them: games.fpl.model.load_gameweek registers every
    FPL fixture as model.FPL_STAGE.

    Without the narrowing the preflight reports two dozen long-finished World Cup
    matches as "unpriced". The artifact's own fixture list is scoped inside
    games.fpl.model.build_artifact, so nothing downstream of the model needs to
    re-filter.
    """
    return fixtures.by_round(gameweek, stage=model.FPL_STAGE)


def note_files(kind: str = "players") -> list:
    """(name, path, ResearchEntry) for every ACTIVE note file on disk.

    research.load_entries returns entries keyed by name and throws the path away,
    which is fine for the overlay and useless for an operator warning: "a note
    matches no player" is only actionable if it says WHICH FILE. Same skip rules
    as load_entries (leading `_` retires a note), no round filtering — the
    expiry check below is precisely about notes load_entries would have dropped.
    """
    out = []
    for path in sorted(glob.glob(os.path.join(research.RESEARCH_DIR, kind, "*.md"))):
        if os.path.basename(path).startswith("_"):
            continue
        with open(path, encoding="utf-8") as fh:
            meta, _ = research.parse_frontmatter(fh.read())
        if not meta.get("name"):
            continue
        out.append((meta["name"], path, research.ResearchEntry.from_meta(meta)))
    return out


def is_fpl_note(path: str) -> bool:
    """Whether a note file is an FPL lineup note rather than a World Cup one.

    research/players/ is shared by both competitions and the two number their
    rounds in the same integer space, so "pinned to a past round" is only a
    meaningful question within one competition — without this, an FPL gameweek 5
    build would report forty World Cup notes pinned to rounds 1-4 as expired
    lineup notes and bury the one that matters. The `fpl-` prefix is the naming
    convention scripts/fpl_notes.py writes (see fpl_notes.note_path), which also
    keeps an FPL note for `Kane` clear of the hand-written kane.md next to it.
    """
    return os.path.basename(path).startswith("fpl-")


def lineup_note_warnings(gameweek: int, feed_names: list, notes: list) -> list:
    """The three owner-lineup-note guards.

    The first is the dangerous one. The overlay is keyed on the literal `name:`
    string and looked up with `==` against FPL's `web_name` ("Virgil", not "Van
    Dijk"), so a note whose name matches nothing is read by nobody and changes
    nothing — it just sits there reading as done. scripts/fpl_notes.py refuses to
    WRITE one; this catches a hand-edited file, a renamed player, and any note
    that predates a feed change. It is checked over every note this gameweek's
    overlay would actually load, World Cup or FPL — a note that is live and
    matches nothing is inert whoever wrote it — but NOT over notes pinned to
    another round, which this build was never going to read anyway.

    Expiry is checked here rather than through evmax.build.expired_risk_flags:
    that function grades PUBLISHED PICKS (it takes the per-article entries_map and
    reports rank positions), which do not exist yet at preflight time, and it only
    looks at out/doubtful/suspended. This one covers every FPL note pinned to a
    past gameweek, before a single simulation has run. Both still earn their keep
    — the World Cup build keeps calling the other one where entries exist.
    """
    warnings = []

    live = [(n, p, e) for n, p, e in notes
            if e.round is None or e.round == gameweek]
    fpl_notes_on_disk = [(n, p, e) for n, p, e in notes if is_fpl_note(p)]

    if feed_names:
        known = set(feed_names)
        unmatched = [(n, p) for n, p, _e in live if n not in known]
        if unmatched:
            from scripts import fpl_notes
            lines = []
            for name, path in unmatched:
                _m, suggestions = fpl_notes.match_name_verbose(name, feed_names)
                hint = ", ".join(suggestions[:4]) or "no close match"
                lines.append(f"{name!r} ({os.path.basename(path)}) "
                             f"-> closest FPL names: {hint}")
            warnings.append(
                f"{len(unmatched)} NOTE(S) MATCH NO FPL PLAYER and therefore have "
                f"NO EFFECT on this build: " + "; ".join(lines) + ". research/"
                f"players/ is shared with the World Cup, so a World Cup note with "
                f"no `round:` pin lands here legitimately — nothing is wrong with "
                f"the note, it just has no FPL player to attach to. If that is what "
                f"this is, pin it to its World Cup round or retire it with a leading "
                f"`_`, and leave the name alone. If it was meant to be an FPL note, "
                f"the closest FPL names are listed above (the feed uses FPL's "
                f"web_name): fix the `name:` field or rewrite the note with "
                f"`python3 scripts/fpl_notes.py --gw {gameweek}`.")

    expired = [(n, p, e) for n, p, e in fpl_notes_on_disk
               if e.round is not None and e.round < gameweek]
    if expired:
        detail = ", ".join(f"{n} ({e.status or 'no status'}, gw{e.round}, "
                           f"{os.path.basename(p)})" for n, p, e in expired)
        warnings.append(
            f"{len(expired)} EXPIRED LINEUP NOTE(S) pinned to a past gameweek — "
            f"already ignored by the overlay, so these players are running on "
            f"bootstrap availability alone: {detail}. Re-pin to gameweek "
            f"{gameweek} if the read still holds, or retire the file with a "
            f"leading `_`.")

    if not any(e.round is None or e.round == gameweek
               for _n, _p, e in fpl_notes_on_disk):
        warnings.append(
            f"NO LINEUP NOTES for gameweek {gameweek} — the model is running on "
            f"the bootstrap `status` field alone, with no owner read on rotation "
            f"or minutes. Informational, not an error: write some with "
            f"`python3 scripts/fpl_notes.py --gw {gameweek}` if you have any.")

    return warnings


def preflight(gameweek: int, players: list, cold_start: list,
              notes: list | None = None) -> list:
    """Abort on anything that makes a build impossible; return warnings for the rest.

    Warnings are RETURNED rather than printed so the caller controls where they
    land and tests can assert on them. The caller must also repeat a one-line
    summary on its final line of output: the World Cup site once shipped an
    article about a ruled-out player because a correctly-firing guard was hidden
    by the operator's `| tail -1` pipe.

    `players` and `cold_start` come from games.fpl.model.load_gameweek's second
    and third return values — this function does not call load_gameweek itself,
    so it can be exercised (and its abort paths tested) without a network call.
    `players` must be the POST-disambiguation pool (load_gameweek's
    players_by_name.values()): the lineup-note check compares note names against
    the names the sim actually keys on, and raw web_names would let a note for a
    colliding name look matched when the engine will never find it.

    `notes` is note_files()' triples, loaded from disk when not supplied.
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
    fx = _gameweek_fixtures(gameweek)
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

    warnings += lineup_note_warnings(
        gameweek,
        [p["name"] for p in players if p.get("name")],
        note_files() if notes is None else list(notes))

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


def _format_date(generated_at: str) -> str:
    """Format an ISO-8601 timestamp as a human date, e.g. '24 June 2026'."""
    dt = datetime.fromisoformat(generated_at)
    try:
        return dt.strftime("%-d %B %Y")
    except ValueError:
        # Windows / some platforms don't support %-d — strip leading zero manually
        return dt.strftime("%d %B %Y").lstrip("0")


def _available_gameweeks(out: str, gameweek: int) -> list:
    """Gameweeks with a page already on disk, unioned with this one.

    Mirrors how the World Cup build derives available_rounds from dist/round/:
    build() never clears `out`, so previously built gameweeks persist, and the
    switcher is generated from what is actually there rather than from a range —
    it must never link to a page that is not on disk.
    """
    root = os.path.join(out, "fpl")
    if not os.path.isdir(root):
        return [gameweek]
    return sorted({int(d[2:]) for d in os.listdir(root)
                   if d.startswith("gw") and d[2:].isdigit()} | {gameweek})


def _world_cup_urls(out: str) -> list:
    """Site-absolute paths of every World Cup page already on disk.

    Handed to render.sitemap_xml as extra_urls. This build never writes anything
    under {out}/round/, but those pages are still live and still indexed, and a
    sitemap that silently drops them reads to a crawler as a request to deindex
    them — the FPL takeover of / must not cost the World Cup tree its indexing.
    """
    root = os.path.join(out, "round")
    if not os.path.isdir(root):
        return []
    urls = []
    for dirpath, _dirs, filenames in os.walk(root):
        if "index.html" not in filenames:
            continue
        rel = os.path.relpath(dirpath, out).replace(os.sep, "/")
        urls.append(f"/{rel}/")
    return sorted(urls)


def _copy_assets(out: str) -> None:
    """Brand images, self-hosted fonts and first-party JS.

    Fonts are self-hosted and the JS is first-party for one reason: the site
    makes NO third-party request on load, which is what keeps it zero-cookie and
    consent-banner-free. Copying from a CDN here would quietly undo that.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    for sub, suffixes in (("brand", (".png", ".svg")),
                          ("fonts", (".woff2",)),
                          ("js", (".js",))):
        src = os.path.join(here, "assets", sub)
        dst = os.path.join(out, sub)
        os.makedirs(dst, exist_ok=True)
        for fname in os.listdir(src):
            if fname.endswith(suffixes):
                shutil.copy2(os.path.join(src, fname), os.path.join(dst, fname))


def build(gameweek: int, sims: int = 50_000, out: str = "dist",
          url: str = "https://evmax.ai", use_llm: bool = True,
          use_cache: bool = True) -> None:
    """Build the FPL section for one gameweek into `out`.

    Mirrors evmax.build.build()'s order and its operational guards. Nothing under
    {out}/round/ is created or modified: those are frozen published claims that
    /track-record/ grades against reality.
    """
    render.SITE_URL = url
    section = render.FPL
    generated_at = datetime.now(timezone.utc).isoformat()
    date_str = _format_date(generated_at)

    # --- Load + preflight ---------------------------------------------------
    priors_by_team, players_by_name, cold_start = model.load_gameweek(gameweek)
    boot = fpl_api.read_cache("bootstrap")
    clubs = sorted(fpl_api.parse_teams(boot).values()) if boot else []

    # players_by_name.values(), not a fresh fpl_api.parse_players(boot): those two
    # lists carry the same players but NOT the same names. load_gameweek's pool has
    # been through core.fpl_priors._disambiguate_names (Cole Palmer / Alex Palmer
    # both arrive from the feed as "Palmer"), and that post-rename name is what the
    # engine and the research overlay key on — so it is the only list against which
    # "does this lineup note match a real player?" is a meaningful question.
    warnings = preflight(gameweek, list(players_by_name.values()), cold_start)

    # --- Simulate -----------------------------------------------------------
    artifact, cache_hit = model.build_artifact(priors_by_team, players_by_name,
                                              gameweek, sims, use_cache=use_cache)
    warnings += cache_warnings(gameweek, cache_hit)

    rows = artifact["rows"]
    if not rows:
        raise SystemExit(
            f"evmax fpl build: the simulation produced no players for gameweek "
            f"{gameweek}. The usual cause is a stale data/fpl/bootstrap.json — "
            f"the priors are built from it, and a cache from before the squad "
            f"registration deadline has no players attached to this season's "
            f"clubs. Force a hard refetch with\n"
            f"    rm -f data/fpl/bootstrap.json data/fpl/fixtures.json && "
            f"python3 manage.py fpl --round {gameweek}")

    # Already scoped to this gameweek's Premier League fixtures: build_artifact
    # narrows by_round with stage=FPL_STAGE, so the World Cup ties that share a
    # round number never reach the sim or the match summaries.
    matches = artifact["matches"]

    horizon_window = fpl_horizon.window(gameweek)

    available = _available_gameweeks(out, gameweek)

    # --- Per-article entries ------------------------------------------------
    squad_entries, squad_meta = fpl_articles.fpl_squad(rows)
    entries_map = {
        "captains":   fpl_articles.captains(rows)[:20],
        "wildcard":   squad_entries,
        "ticker":     fpl_articles.ticker(matches, clubs),
        # The horizon is aggregated inside build_artifact (and cached with it);
        # the window is recomputed here because the grid needs the same
        # gameweek list for its column headers.
        "runs":       fpl_articles.fixture_runs(artifact.get("horizon", {}),
                                                horizon_window),
        "defenders":  fpl_articles.defenders(rows)[:20],
        "efficiency": fpl_articles.efficiency(rows)[:20],
        "defcon":     fpl_articles.defcon_leaders(rows)[:20],
    }

    nav = [(slug, ARTICLE_TITLES[slug]) for slug in ARTICLES]

    def w(path: str, text: str) -> None:
        full = os.path.join(out, path.lstrip("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)

    # --- Bulk players feed --------------------------------------------------
    # Same guardrail as the World Cup feed: derived model outputs plus
    # name/team/position ONLY. Price and ownership stay per-player context inside
    # the articles and never go into this public bulk feed.
    # kickoff is included (and may be None — a club with a blank gameweek has no
    # fixture at all) so a consumer can order picks against the deadline.
    player_notes = research.load_entries("players", gameweek)
    players_feed = [
        {
            "name": r["name"],
            "team": r.get("team"),
            "position": r.get("position"),
            "x_points": r["x_points"],
            "captain_ev": r["captain_ev"],
            "ceiling": r["ceiling"],
            "kickoff": r.get("kickoff"),
            "flag": articles.player_flag(r["name"], player_notes),
        }
        for r in rows
    ]
    w(section.players_json_path(gameweek), json.dumps({
        "gameweek": gameweek,
        "generated_at": generated_at,
        "methodology": section.methodology,
        "license": render.DATA_LICENSE_URL,
        "players": players_feed,
    }, ensure_ascii=False, indent=2))

    # --- Render each article ------------------------------------------------
    prose_map: dict = {}
    latest_index: dict = {}
    used_leads: set = set()

    lock = fixtures.round_lock_time(gameweek)
    is_production = os.path.basename(os.path.normpath(out)) == "dist"
    gameweek_open = lock is None or datetime.now(timezone.utc) < lock

    for slug in ARTICLES:
        entries = entries_map[slug]
        columns = _COLUMNS[slug]
        title = f"{ARTICLE_TITLES[slug]} — {section.kicker(gameweek)}"
        json_url = section.json_path(gameweek, slug)

        # Lead player for the prose, de-duplicated across articles so six pieces
        # do not all open on the same name. The squad/club-framed pieces take no
        # subject at all.
        if slug in _TEAM_FRAMED:
            subject = None
        else:
            subject = next(
                (e["name"] for e in entries if e["name"] not in used_leads),
                entries[0]["name"] if entries else None,
            )
            if subject:
                used_leads.add(subject)

        # cache_name and unit are load-bearing: without them FPL gameweek N and
        # World Cup round N share a prose cache entry, and the template tier
        # falls through to the World Cup wording.
        prose = writer.article_prose(slug, gameweek, entries, columns,
                                     cache_dir="data/articles", use_llm=use_llm,
                                     subject=subject,
                                     cache_name=f"fpl-gw{gameweek}",
                                     unit="Gameweek")
        prose_map[slug] = prose

        # Viz
        if slug == "wildcard":
            # entries is the full 15 (XI + bench); the pitch only draws the XI.
            viz_html = render.pitch_svg([e for e in entries if e.get("role") == "XI"])
        elif slug == "runs":
            # A grid, not a bar chart: the article's whole point is the SHAPE of
            # a club's next six, which a single aggregated bar would flatten away.
            viz_html = render.run_grid_html(entries)
        else:
            pair = _CEILING_PAIRED_METRIC.get(slug)
            if pair:
                pair_metric, pair_scale = pair
                viz_html = render.ev_bar(entries, pair_metric,
                                         max_rows=_ARTICLE_VIZ_MAX_ROWS,
                                         reach_metric="ceiling",
                                         reach_scale=pair_scale)
            else:
                viz_html = render.ev_bar(entries, columns[0],
                                         max_rows=_ARTICLE_VIZ_MAX_ROWS)

        # JSON
        extra_fields = {"squad": squad_meta} if slug == "wildcard" else None
        env = render.article_json("fantasy_premier_league", gameweek, slug, title,
                                  generated_at, sims, entries,
                                  extra_fields=extra_fields, section=section)
        env_json = json.dumps(env, ensure_ascii=False, indent=2)
        w(json_url, env_json)
        latest_index[slug] = json_url

        # Point-in-time projection archive — the ground truth the backtest
        # harness grades from GW1 forward. Two guards, same as the World Cup
        # build: (1) production builds only, so a verification build into a temp
        # dir can never touch the published record; (2) the gameweek still open,
        # so once the deadline passes the snapshot freezes and a post-hoc rebuild
        # cannot contaminate it.
        if is_production and gameweek_open:
            snap_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "assets", "projections", f"fpl-gw{gameweek}")
            os.makedirs(snap_dir, exist_ok=True)
            with open(os.path.join(snap_dir, f"{slug}.json"), "w",
                      encoding="utf-8") as fh:
                fh.write(env_json)

        # HTML
        w(section.article_path(gameweek, slug) + "index.html",
          render.article_page(gameweek, slug, title, prose, entries, columns,
                              json_url, viz_html, generated_at=generated_at,
                              date_str=date_str, available_rounds=available,
                              section=section))

        # Markdown twin (agent-facing content-only article, llms.txt convention)
        w(section.md_path(gameweek, slug),
          render.article_md(gameweek, slug, title, prose, entries, columns,
                            generated_at, date_str,
                            canonical_path=section.article_path(gameweek, slug),
                            section=section))

    # --- Static pages + assets ----------------------------------------------
    w("/about/index.html", render.about_page())
    w("/privacy/index.html", render.privacy_page())
    w("/thanks/index.html", render.thanks_page())
    w("/confirmed/index.html", render.confirmed_page())
    _copy_assets(out)

    # --- Landing page -------------------------------------------------------
    captains_entries = entries_map["captains"]
    captains_viz = render.ev_bar(
        captains_entries[:_FEATURED_VIZ_MAX_ROWS], _COLUMNS["captains"][0],
        width=400, row_h=40, label_size=15, value_size=14, bar_h=22,
        reach_metric="ceiling", reach_scale=2.0)
    featured = {
        "slug": "captains",
        "prose": prose_map["captains"],
        "viz_html": captains_viz,
    }

    feed = []
    for slug in ARTICLES:
        if slug == "captains":
            continue
        entries = entries_map[slug]
        primary_col = _COLUMNS[slug][0]
        top_entry = entries[0] if entries else {}
        feed.append({
            "slug": slug,
            "headline": prose_map[slug]["headline"],
            "teaser": prose_map[slug]["standfirst"],
            "stat_value": render._fmt(primary_col, top_entry),
            "stat_label": render._COL_LABEL.get(primary_col, primary_col),
        })

    landing_html = render.landing_page(gameweek, featured, feed, date_str=date_str,
                                       available_rounds=available, section=section)
    w(section.landing_path(gameweek) + "index.html", landing_html)
    # The root takeover is a deliberate owner decision (2026-07-30): GW1 is the
    # year's largest FPL search peak and / belongs to the live competition. The
    # World Cup tree under /round/N/ is untouched and stays live — its landing
    # survives at /round/8/ — so nothing published is lost, only the front door
    # moves.
    w("/index.html", landing_html)

    # --- Agent / meta files -------------------------------------------------
    w("/api/latest.json", json.dumps(
        {"gameweek": gameweek, "generated_at": generated_at,
         "articles": latest_index},
        ensure_ascii=False, indent=2))
    w("/llms.txt", render.llms_txt(gameweek, nav, section=section))
    w("/robots.txt", render.robots_txt())
    w("/sitemap.xml", render.sitemap_xml(gameweek, nav, lastmod=generated_at[:10],
                                         section=section,
                                         extra_urls=_world_cup_urls(out)))

    # --- Operator output ----------------------------------------------------
    for warning in warnings:
        print(f"!!! {warning}")
    # The warning COUNT rides on the final line on purpose: a correctly-firing
    # guard was once hidden entirely by an operator's `| tail -1` pipe.
    warn_suffix = (f" | !!! {len(warnings)} WARNING(S) — see above / rerun "
                   f"without filters" if warnings else " | 0 warnings")
    print(f"Built gameweek {gameweek} → {out}/ "
          f"({len(rows)} players, {len(matches)} fixtures, {len(ARTICLES)} articles) "
          f"| sim cache {'HIT' if cache_hit else 'MISS'}{warn_suffix}")
