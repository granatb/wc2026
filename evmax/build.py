"""Build the evmax static site for one round into dist/.

Usage:
    python3 -m evmax.build --round 3 [--sims 50000] [--out dist]
                           [--url https://evmax.ai] [--no-llm]
Run from the repo root.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from core import engine_events, espn, fixtures, research
from evmax import articles, backtest, reddit, render, writer

# Google Search Console site-verification file (HTML-file method). Regenerated on
# every build so it survives a dist/ wipe rather than relying on a one-off manual
# file. Format fixed by Google: https://support.google.com/webmasters/answer/9008080
_GSC_VERIFICATION_FILE = "google8d25fd2122a8aadd.html"
_GSC_VERIFICATION_CONTENT = "google-site-verification: google8d25fd2122a8aadd.html"

# Where the reddit kit lands (cwd-relative, gitignored). Module-level so tests
# can patch it and keep smoke builds from overwriting the live operator kit.
_REDDIT_DIR = os.path.join("data", "reddit")

# ---------------------------------------------------------------------------
# Per-article column specs (primary metric first, then richer set)
# ---------------------------------------------------------------------------
_COLUMNS = {
    "captains":          ["captain_ev", "x_points", "ceiling", "price", "value", "ownership_pct"],
    "matches":           [],  # no player table; fixture cards rendered by match_predictions_html
    "transfers":         ["priority_score", "vor", "x_points", "p_advance", "price", "ownership_pct"],
    "fixtures":          ["p_clean_sheet", "exp_goals_against", "exp_goals_for", "top_def", "top_gk"],
    "wildcard":          ["x_points", "price", "captain_ev", "ceiling", "ownership_pct"],
    "defenders":         ["x_points", "price", "value", "ceiling", "ownership_pct"],
    "risky":             ["ceiling", "x_points", "captain_ev", "price", "ownership_pct"],
    "efficiency":        ["value", "x_points", "price", "captain_ev", "ownership_pct", "ceiling"],
    "blowout-transfers": ["x_points", "captain_ev", "ceiling", "price", "ownership_pct"],
    # Legacy columns kept for back-compat but not featured in ARTICLES. best-xi was
    # merged into wildcard (2026-07) -- select_xi() and this column spec are kept
    # for the retrospective backtest, which still grades older published snapshots
    # that contain a best-xi article.
    "best-xi":           ["x_points", "captain_ev", "ceiling", "price", "value", "ownership_pct"],
    "high-ceiling-xi":   ["ceiling", "x_points", "captain_ev", "price", "ownership_pct"],
    "differentials":     ["x_points", "ceiling", "captain_ev", "price", "value", "ownership_pct"],
}

# Articles whose chart metric is points-denominated get a floor+ceiling reach
# bar (solid = the metric, faint = ceiling) so the boom/bust range reads at a
# glance -- "value" (pts/million), "priority_score" (composite VOR) and
# "p_clean_sheet" (a probability) are different units, so mixing in raw
# ceiling points would be dimensionally wrong; those keep a single-metric bar.
# captains charts captain_ev (2x a single appearance), so its ceiling
# companion needs the same doubling to land on the same scale.
_CEILING_PAIRED_METRIC = {
    "captains":           ("captain_ev", 2.0),
    "defenders":          ("x_points", 1.0),
    "risky":              ("x_points", 1.0),  # floor+reach instead of ceiling-only
    "blowout-transfers":  ("x_points", 1.0),
}

# XI articles get pitch SVG; others get an EV bar. best-xi is kept in this set for
# back-compat (in case some future code re-derives a viz for an old snapshot);
# wildcard is the only one actually published now that best-xi is merged into it.
_XI_ARTICLES = {"best-xi", "wildcard"}

# In-article ev_bar charts are a captioned summary, not the full data (the table
# below has everything) -- cap rows so the chart never reads as "ridiculous" size.
_ARTICLE_VIZ_MAX_ROWS = 10


def _kickoffs_for_round(fantasy_round: int) -> dict:
    out = {}
    for f in fixtures.by_round(fantasy_round):
        for team in (f.home, f.away):
            iso = f.kickoff.isoformat()
            if team not in out or iso < out[team]:
                out[team] = iso
    return out


_BACK_TO_LATEST_MARKER = 'id="back-to-latest"'


def _backfill_latest_round_link(out: str, round_root: str, current_round: int) -> None:
    """Articles are frozen at lock (see build()'s snapshot guard) -- an old
    round's pages never get rebuilt, so they never pick up new nav/UI
    features like the round switcher. That leaves a real dead end: someone
    landing on an old round via search or a shared link has no obvious way
    back to the live one. Rather than rebuild old rounds (which would re-run
    the engine and risk changing a published round's numbers), patch ONLY a
    small "back to the latest round" link into their already-built HTML --
    mechanical, idempotent, touches no data/prose/numbers. Uses only the
    `.wrap` class and `--green` CSS var, both present since the original v2
    editorial redesign, so it renders correctly even on the oldest builds."""
    if not os.path.isdir(round_root):
        return
    link_html = (
        f'<div class="wrap" style="padding-top:10px">'
        f'<a {_BACK_TO_LATEST_MARKER} href="/" style="color:var(--green);'
        f'font-weight:600;font-size:13px">&larr; Back to the latest round</a></div>'
    )
    for entry in os.listdir(round_root):
        if not entry.isdigit() or int(entry) == current_round:
            continue
        for dirpath, _dirs, filenames in os.walk(os.path.join(round_root, entry)):
            if "index.html" not in filenames:
                continue
            path = os.path.join(dirpath, "index.html")
            with open(path, encoding="utf-8") as fh:
                html = fh.read()
            if _BACK_TO_LATEST_MARKER in html or "</header>" not in html:
                continue  # already patched, or a shape we don't recognize -- skip rather than guess
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html.replace("</header>", "</header>" + link_html, 1))


def _article_entries(rows: list, fantasy_round: int) -> dict[str, list]:
    """Return {slug: entries_list} for the v2 article set.

    Published articles are frozen claims at lock: every article is always built
    from the full player pool exactly as it stood pre-lock. The only element
    that reflects reality as the round plays out is the predicted-vs-actual
    panel on the matches article (see articles.finished_results_map /
    match_predictions(..., results=...)).

    wildcard's entries are the 15-man squad list only; its squad-level meta
    (total_cost, xi_xpoints, formation, ...) is attached separately in build()
    since this function's contract is a flat {slug: entries_list} map.
    """
    blow = articles.blowout_teams(fantasy_round)
    wildcard_entries, _wildcard_meta = articles.wildcard_squad(rows)
    return {
        "captains":          articles.rank_captains(rows)[:20],
        "wildcard":          wildcard_entries,
        "best-xi":           articles.select_xi(rows, "x_points"),
        "defenders":         articles.by_position(rows, "DEF")[:15],
        "risky":             articles.risky(rows)[:20],
        "efficiency":        articles.efficiency(rows)[:20],
        "blowout-transfers": articles.blowout_transfers(rows, blow)[:20],
    }


def expired_risk_flags(entries_map: dict, notes: dict, fantasy_round: int,
                       top_n: int = 20) -> list:
    """Names of published picks carrying an out/doubtful/suspended note pinned to a
    PAST round. Round-pinned notes expire silently by design (core/research.py), which
    is right for tactical reads but dangerous for injuries with no return date — the
    2026-07-04 Raphinha near-miss shipped a whole article on a ruled-out player this
    way. The build can't know current fitness, so it flags loudly for operator review
    instead of guessing."""
    expired = {n: e for n, e in notes.items()
               if getattr(e, "status", None) in ("out", "doubtful", "suspended")
               and getattr(e, "round", None) is not None and e.round < fantasy_round}
    flags = []
    for slug, entries in entries_map.items():
        for e in entries[:top_n]:
            name = e.get("name") if isinstance(e, dict) else None
            if name in expired:
                note = expired[name]
                flags.append(f"{name} ({note.status}, round {note.round}) -> {slug} #{e.get('rank')}")
    return sorted(set(flags))


def _format_date(generated_at: str) -> str:
    """Format an ISO-8601 timestamp as a human date, e.g. '24 June 2026'."""
    dt = datetime.fromisoformat(generated_at)
    try:
        return dt.strftime("%-d %B %Y")
    except ValueError:
        # Windows / some platforms don't support %-d — strip leading zero manually
        return dt.strftime("%d %B %Y").lstrip("0")


def _preflight(fantasy_round: int) -> None:
    """Fail fast when the local data/ cache can't support a build.

    data/ is gitignored — a clean checkout has no schedule, odds or player
    data until it's refreshed from the live APIs. Without this check the
    build dies much later with a misleading error (FileNotFoundError deep in
    articles.load_player_meta, or an empty player pool surfacing as
    "insufficient GK pool" in wildcard_squad).
    """
    problems = []
    if not os.path.exists(fixtures._SCHEDULE_JSON):
        problems.append(
            "data/schedule.json is missing — populate the data/ cache with\n"
            f"    python3 manage.py fifa --round {fantasy_round} --refresh --props\n"
            "  (data/ is gitignored: a fresh checkout has no cached schedule/odds;"
            " see README 'Setup' or scripts/morning-update.sh)")
    elif not fixtures.by_round(fantasy_round):
        problems.append(
            f"data/schedule.json has no fixtures for round {fantasy_round} — "
            "refresh it with\n"
            f"    python3 manage.py fifa --round {fantasy_round} --refresh --props")
    if not os.path.exists(articles._PLAYERS_JSON):
        problems.append(
            "data/players.json is missing — regenerate it from the FIFA + Holdet "
            "APIs with\n    python3 build_players.py")
    if problems:
        raise SystemExit("evmax.build preflight failed:\n- " +
                         "\n- ".join(problems))


def _check_rows(rows: list, means: dict, meta: dict) -> None:
    """Diagnose an empty enriched-row set before it corrupts every article.

    rows == [] has exactly two causes, and the generic downstream failure
    ("insufficient GK pool") points at neither:
      - means empty: the simulation produced no players (schedule/odds caches
        missing or the round has no fixtures);
      - join failure: simulated names matched nothing in data/players.json
        (stale or foreign players.json — the file is machine-specific,
        regenerated by build_players.py).
    """
    if rows:
        return
    if not means:
        raise SystemExit(
            "evmax.build: the simulation produced no players — data/schedule.json "
            "and data/odds/ are likely missing or stale for this round; refresh "
            "with `python3 manage.py fifa --round <N> --refresh --props`.")
    raise SystemExit(
        f"evmax.build: none of the {len(means)} simulated player names matched "
        "data/players.json — the file is stale or from another checkout; "
        "regenerate it with `python3 build_players.py`.")


def build(fantasy_round: int, sims: int, out: str, url: str,
          use_llm: bool = True) -> None:
    _preflight(fantasy_round)
    render.SITE_URL = url
    generated_at = datetime.now(timezone.utc).isoformat()
    date_str = _format_date(generated_at)

    # Rounds don't get overwritten -- build() never clears `out`, so every
    # round's /round/{N}/ pages built into this same output dir persist across
    # runs and get re-uploaded on every deploy. The round switcher (landing +
    # article pages) is generated from what's actually on disk, so it never
    # links to a round that isn't there.
    round_root = os.path.join(out, "round")
    available_rounds = sorted(
        {int(d) for d in os.listdir(round_root) if d.isdigit()} | {fantasy_round}
    ) if os.path.isdir(round_root) else [fantasy_round]

    # --- Simulate ---
    players, match_samples = engine_events.simulate_round(
        fantasy_round, sims=sims,
        market_rates=espn.load_player_rates(fantasy_round),
        research=research.load_entries("players", fantasy_round),
        research_weight=0.30)
    means = engine_events.event_means(players)
    samples = {name: ps.goal_samples for name, ps in players.items()}
    meta = articles.load_player_meta()
    kickoffs = _kickoffs_for_round(fantasy_round)
    rows = articles.build_rows(means, samples, meta, kickoffs)
    _check_rows(rows, means, meta)

    # --- Build per-article data ---
    # Published articles are FROZEN claims at lock: every article (including
    # transfers) is always built from the full pre-lock player pool. The only
    # thing that reflects reality as the round plays out is the matches
    # article's predicted-vs-actual panel (finished_results_map below), which
    # simply returns an empty map before any fixture has finished.
    entries_map = _article_entries(rows, fantasy_round)
    # wildcard's squad-level meta (total_cost, xi_xpoints, formation, ...) isn't part
    # of the flat entries list _article_entries returns, so recompute it here for the
    # JSON envelope + prose. wildcard_squad is deterministic, so this reproduces the
    # exact same 15 already sitting in entries_map["wildcard"].
    _wildcard_entries, wildcard_meta = articles.wildcard_squad(rows)
    results_map = articles.finished_results_map(fantasy_round)
    entries_map["matches"] = articles.match_predictions(
        match_samples, fantasy_round, results=results_map)
    entries_map["fixtures"] = articles.fixture_guide(entries_map["matches"], rows)
    # Transfer priorities need each team's advancement probability from the matches
    # article, so it's computed after — and only knockout rounds populate adv_map,
    # so transfer_priorities degrades gracefully to pure value-over-replacement
    # ranking during the group stage.
    adv_map = articles.advancement_map(entries_map["matches"])
    entries_map["transfers"] = articles.transfer_priorities(rows, adv_map)

    # --- Expired-risk-note guard (Raphinha near-miss, 2026-07-04) ---
    flags = expired_risk_flags(entries_map,
                               research.load_entries("players", None), fantasy_round)
    if flags:
        print("\n!!! EXPIRED INJURY/RISK NOTES on published picks — VERIFY before lock:")
        for f in flags:
            print("    " + f)
        print("!!! Update research/players/<name>.md (re-pin round or clear status) to silence.\n")
    nav = [(slug, articles.ARTICLE_TITLES[slug]) for slug in articles.ARTICLES]

    def w(path: str, text: str) -> None:
        full = os.path.join(out, path.lstrip("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)

    # --- Bulk players feed (/api/round/{N}/players.json) -- powers the /rate/
    # client-side tool. Guardrail: derived model outputs + name/team/position
    # ONLY. No price, no ownership -- those stay per-player context columns in
    # articles, never in this public bulk feed (see /rate/ build note).
    # kickoff is included so /rate/ can flag "sub chain" options: a bench
    # player whose match kicks off later than a same-position starter's can
    # be manually swapped in after seeing the starter's actual result -- FIFA
    # allows manual subs up to the round's last kickoff (autosubs are DNP-only
    # and only fire at round end, so they're not how serious managers play
    # the bench). See memory/fifa-manual-sub-chains for the full mechanic.
    player_notes = research.load_entries("players", fantasy_round)
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
    w(f"/api/round/{fantasy_round}/players.json", json.dumps({
        "round": fantasy_round,
        "generated_at": generated_at,
        "methodology": render.METHODOLOGY,
        "license": render.DATA_LICENSE_URL,
        "players": players_feed,
    }, ensure_ascii=False, indent=2))

    # --- Render each article ---
    prose_map: dict[str, dict] = {}
    latest_index: dict[str, str] = {}
    used_leads: set = set()

    for slug in articles.ARTICLES:
        entries = entries_map[slug]
        columns = _COLUMNS[slug]
        title = f"{articles.ARTICLE_TITLES[slug]} — Round {fantasy_round}"
        json_url = f"/api/round/{fantasy_round}/{slug}.json"

        # Matches article: no player subject, no player table
        is_matches = (slug == "matches")

        # Determine the subject (lead player) for prose focus. wildcard (now also
        # the site's "best XI" piece), matches and fixtures are team/match-framed,
        # with no single player centred.
        if slug in ("wildcard", "matches", "fixtures"):
            subject = None
        else:
            subject = next(
                (e["name"] for e in entries if e["name"] not in used_leads),
                entries[0]["name"] if entries else None,
            )
            if subject:
                used_leads.add(subject)

        prose = writer.article_prose(slug, fantasy_round, entries, columns,
                                     cache_dir="data/articles",
                                     use_llm=use_llm, subject=subject)
        prose_map[slug] = prose

        # Viz
        if is_matches:
            viz_html = render.match_predictions_html(entries)
        elif slug == "wildcard":
            # entries is the full 15 (XI + bench); the pitch only draws a starting XI.
            viz_html = render.pitch_svg([e for e in entries if e.get("role") == "XI"])
        elif slug in _XI_ARTICLES:
            viz_html = render.pitch_svg(entries)
        elif slug == "fixtures":
            # p_clean_sheet is a 0-1 fraction; ev_bar's "{v:.2f}" label reads
            # oddly for a percent metric ("0.42" vs "42%"), so pass a
            # percent-scaled copy for the viz only -- the table/JSON keep the
            # raw 0-1 fraction.
            viz_entries = [dict(e, p_clean_sheet=(e.get("p_clean_sheet") or 0.0) * 100)
                          for e in entries]
            viz_html = render.ev_bar(viz_entries, "p_clean_sheet",
                                     max_rows=_ARTICLE_VIZ_MAX_ROWS)
        else:
            # In-article charts are a captioned SUMMARY of the top slice -- the
            # table below has everything -- so cap at 10 rows and keep the
            # default (denser) sizing; the landing page's featured chart below
            # gets its own bigger, easier-to-read sizing.
            pair = _CEILING_PAIRED_METRIC.get(slug)
            if pair:
                pair_metric, pair_scale = pair
                viz_html = render.ev_bar(entries, pair_metric, max_rows=_ARTICLE_VIZ_MAX_ROWS,
                                         reach_metric="ceiling", reach_scale=pair_scale)
            else:
                viz_html = render.ev_bar(entries, columns[0], max_rows=_ARTICLE_VIZ_MAX_ROWS)

        # JSON
        extra_fields = {"squad": wildcard_meta} if slug == "wildcard" else None
        env = render.article_json("fifa_world_cup_fantasy", fantasy_round, slug,
                                  title, generated_at, sims, entries,
                                  extra_fields=extra_fields)
        env_json = json.dumps(env, ensure_ascii=False, indent=2)
        w(json_url, env_json)
        latest_index[slug] = json_url

        # Point-in-time projection archive (track-record ground truth). Two guards:
        # (1) production builds only (out == "dist") — test/verification builds to
        #     /tmp must never touch the published record (a subagent caught a real
        #     overwrite this way); (2) round still open — once the first match kicks
        #     off, the snapshot freezes so post-hoc rebuilds can't contaminate it.
        lock = fixtures.round_lock_time(fantasy_round)
        is_production = os.path.basename(os.path.normpath(out)) == "dist"
        if is_production and (lock is None or datetime.now(timezone.utc) < lock):
            snap_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "assets", "projections", f"round-{fantasy_round}")
            os.makedirs(snap_dir, exist_ok=True)
            with open(os.path.join(snap_dir, f"{slug}.json"), "w",
                      encoding="utf-8") as fh:
                fh.write(env_json)

        # HTML
        w(f"/round/{fantasy_round}/{slug}/index.html",
          render.article_page(fantasy_round, slug, title, prose, entries,
                              columns, json_url, viz_html,
                              generated_at=generated_at, date_str=date_str,
                              show_table=not is_matches,
                              available_rounds=available_rounds))

        # Markdown twin (agent-facing content-only article, llms.txt convention)
        w(f"/round/{fantasy_round}/{slug}.md",
          render.article_md(fantasy_round, slug, title, prose, entries, columns,
                            generated_at, date_str,
                            canonical_path=f"/round/{fantasy_round}/{slug}/"))

    # --- Reddit kit (operator posting material — NOT published to the site) ---
    # data/ is gitignored; this never lands in dist/. Written after articles/prose
    # are built so the kit can pull real captain EV / close-game numbers.
    reddit_kit_text = reddit.reddit_kit(fantasy_round, entries_map, prose_map, date_str)
    os.makedirs(_REDDIT_DIR, exist_ok=True)
    reddit_kit_path = os.path.join(_REDDIT_DIR, f"round-{fantasy_round}.md")
    with open(reddit_kit_path, "w", encoding="utf-8") as fh:
        fh.write(reddit_kit_text)

    # --- About + Privacy pages ---
    w("/about/index.html", render.about_page())
    w("/privacy/index.html", render.privacy_page())
    w("/thanks/index.html", render.thanks_page())
    w("/confirmed/index.html", render.confirmed_page())

    # --- Track record (backtest our own published predictions vs reality) ---
    record = backtest.build_track_record()
    w("/track-record/index.html", render.track_record_page(record))
    w("/api/track-record.json", json.dumps(
        render.track_record_json(record), ensure_ascii=False, indent=2))

    # --- Brand assets + self-hosted fonts (no third-party requests, GDPR) ---
    import shutil
    brand_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "brand")
    brand_dst = os.path.join(out, "brand")
    os.makedirs(brand_dst, exist_ok=True)
    for fname in os.listdir(brand_src):
        if fname.endswith((".png", ".svg")):
            shutil.copy2(os.path.join(brand_src, fname), os.path.join(brand_dst, fname))
    fonts_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
    fonts_dst = os.path.join(out, "fonts")
    os.makedirs(fonts_dst, exist_ok=True)
    for fname in os.listdir(fonts_src):
        if fname.endswith(".woff2"):
            shutil.copy2(os.path.join(fonts_src, fname), os.path.join(fonts_dst, fname))

    # --- Self-hosted JS (the site's first first-party JavaScript -- see
    # evmax/assets/js/rate.js header comment for the no-tracking/no-external-
    # request policy this asset must satisfy) --------------------------------
    js_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "js")
    js_dst = os.path.join(out, "js")
    os.makedirs(js_dst, exist_ok=True)
    for fname in os.listdir(js_src):
        if fname.endswith(".js"):
            shutil.copy2(os.path.join(js_src, fname), os.path.join(js_dst, fname))

    # --- /rate/ -- client-side team rater ------------------------------------
    w("/rate/index.html", render.rate_page(fantasy_round))

    # --- Landing page ---
    # Featured = captains article (first in ARTICLES). The article page itself
    # shows all 20 captain entries, but the landing's featured chart is above
    # the fold -- a 20-bar chart pushes the whole feed below the fold, so cap
    # the featured viz to the top 8 (ev_bar also has a belt-and-braces max_rows
    # for the same cap, in case a future call site forgets to slice).
    _FEATURED_VIZ_MAX_ROWS = 8
    captains_entries = entries_map["captains"]
    captains_cols = _COLUMNS["captains"]
    captains_prose = prose_map["captains"]
    # Featured chart on the landing page: bigger and easier to read than the
    # denser in-article default -- it's the first thing a visitor sees.
    captains_viz = render.ev_bar(
        captains_entries[:_FEATURED_VIZ_MAX_ROWS], captains_cols[0],
        width=400, row_h=40, label_size=15, value_size=14, bar_h=22,
        reach_metric="ceiling", reach_scale=2.0)

    featured = {
        "slug": "captains",
        "prose": captains_prose,
        "viz_html": captains_viz,
    }

    # Feed = the other articles (not captains, which is featured)
    feed = []
    for slug in articles.ARTICLES:
        if slug == "captains":
            continue
        entries = entries_map[slug]
        columns = _COLUMNS[slug]
        prose = prose_map[slug]
        if slug == "matches":
            close_count = sum(1 for e in entries if e.get("close"))
            stat_value = f"{len(entries)}"
            stat_label = f"fixtures · {close_count} to watch"
        else:
            primary_col = columns[0]
            top_entry = entries[0] if entries else {}
            stat_value = render._fmt(primary_col, top_entry)
            stat_label = render._COL_LABEL.get(primary_col, primary_col)
        feed.append({
            "slug": slug,
            "headline": prose["headline"],
            "teaser": prose["standfirst"],
            "stat_value": stat_value,
            "stat_label": stat_label,
        })

    # Sidebar quick picks: one-glance answers, each linking into its article.
    quick_picks = []
    if entries_map.get("captains"):
        c = entries_map["captains"][0]
        quick_picks.append({"label": "Captain", "name": c["name"],
                            "stat": f"{c['captain_ev']:.1f} EV",
                            "href": f"/round/{fantasy_round}/captains/"})
    diffs = articles.differentials(rows)
    if diffs:
        d = diffs[0]
        quick_picks.append({"label": "Differential", "name": d["name"],
                            "stat": f"{d['x_points']:.1f} xPts · {d['ownership_pct']:.0f}%",
                            "href": f"/round/{fantasy_round}/risky/"})
    budget = [e for e in entries_map.get("efficiency", []) if e.get("tier") == "Budget"]
    if budget:
        b = budget[0]
        quick_picks.append({"label": "Cheap win", "name": b["name"],
                            "stat": f"{b['price']:.1f}m · {b['value']:.2f}/m",
                            "href": f"/round/{fantasy_round}/efficiency/"})
    if entries_map.get("fixtures"):
        f0 = entries_map["fixtures"][0]
        quick_picks.append({"label": "Clean sheet", "name": f0["name"],
                            "stat": f"{f0['p_clean_sheet']*100:.0f}% CS",
                            "href": f"/round/{fantasy_round}/fixtures/"})

    # Live "our XI so far" strip: realized vs expected vs ceiling for the
    # PUBLISHED (frozen) XI's already-played players. None pre-lock / with a
    # stale feed -- the landing simply omits the strip then.
    live_xi = backtest.live_xi_progress(fantasy_round)

    landing_html = render.landing_page(fantasy_round, featured, feed, date_str=date_str,
                                       fixtures=entries_map["matches"], quick_picks=quick_picks,
                                       available_rounds=available_rounds, live_xi=live_xi)
    w("/index.html", landing_html)
    w(f"/round/{fantasy_round}/index.html", landing_html)

    # Old rounds are frozen and never get this build's nav/switcher -- patch
    # in a minimal way back to the current round (see docstring).
    _backfill_latest_round_link(out, round_root, fantasy_round)

    # --- Agent / meta files ---
    w("/api/latest.json", json.dumps(
        {"round": fantasy_round, "generated_at": generated_at,
         "articles": latest_index},
        ensure_ascii=False, indent=2))
    w("/llms.txt", render.llms_txt(fantasy_round, nav))
    w("/robots.txt", render.robots_txt())
    w("/sitemap.xml", render.sitemap_xml(fantasy_round, nav, lastmod=generated_at[:10]))
    w(f"/{_GSC_VERIFICATION_FILE}", _GSC_VERIFICATION_CONTENT)
    # Cloudflare Pages redirects /foo.html -> /foo by default, which breaks Google's
    # exact-path verification check. Force this one path to serve as-is.
    w("/_redirects", f"/{_GSC_VERIFICATION_FILE} /{_GSC_VERIFICATION_FILE} 200\n")

    # --- IndexNow key file (see scripts/deploy.sh) ---
    # IndexNow requires a plaintext file at /<key>.txt containing exactly the key,
    # proving control of the domain before search engines accept push notifications.
    indexnow_key_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "indexnow_key.txt")
    with open(indexnow_key_path, encoding="utf-8") as fh:
        indexnow_key = fh.read().strip()
    w(f"/{indexnow_key}.txt", indexnow_key + "\n")

    print(f"Built round {fantasy_round} → {out}/ "
          f"({len(rows)} players, {len(articles.ARTICLES)} articles) "
          f"| reddit kit → {reddit_kit_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Build the evmax static site for one fantasy round.")
    ap.add_argument("--round", type=int, required=True,
                    help="Fantasy round number")
    ap.add_argument("--sims", type=int, default=50_000,
                    help="Monte-Carlo simulation count (default 50 000)")
    ap.add_argument("--out", default="dist",
                    help="Output directory (default dist/)")
    ap.add_argument("--url", default="https://evmax.ai",
                    help="Canonical site URL (default https://evmax.ai)")
    ap.add_argument("--no-llm", dest="no_llm", action="store_true",
                    help="Skip the LLM tier; use cache-or-template only")
    a = ap.parse_args()
    build(a.round, a.sims, a.out, a.url, use_llm=not a.no_llm)


if __name__ == "__main__":
    main()
