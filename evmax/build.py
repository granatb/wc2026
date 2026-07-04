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

# ---------------------------------------------------------------------------
# Per-article column specs (primary metric first, then richer set)
# ---------------------------------------------------------------------------
_COLUMNS = {
    "captains":          ["captain_ev", "x_points", "ceiling", "price", "value", "ownership_pct"],
    "matches":           [],  # no player table; fixture cards rendered by match_predictions_html
    "transfers":         ["priority_score", "vor", "x_points", "p_advance", "price", "ownership_pct"],
    "best-xi":           ["x_points", "captain_ev", "ceiling", "price", "value", "ownership_pct"],
    "defenders":         ["x_points", "price", "value", "ceiling", "ownership_pct"],
    "risky":             ["ceiling", "x_points", "captain_ev", "price", "ownership_pct"],
    "efficiency":        ["value", "x_points", "price", "captain_ev", "ownership_pct"],
    "blowout-transfers": ["x_points", "captain_ev", "ceiling", "price", "ownership_pct"],
    # Legacy columns kept for back-compat but not featured in ARTICLES
    "high-ceiling-xi":   ["ceiling", "x_points", "captain_ev", "price", "ownership_pct"],
    "differentials":     ["x_points", "ceiling", "captain_ev", "price", "value", "ownership_pct"],
}

# XI articles get pitch SVG; others get an EV bar
_XI_ARTICLES = {"best-xi"}


def _kickoffs_for_round(fantasy_round: int) -> dict:
    out = {}
    for f in fixtures.by_round(fantasy_round):
        for team in (f.home, f.away):
            iso = f.kickoff.isoformat()
            if team not in out or iso < out[team]:
                out[team] = iso
    return out


# Articles built from a pickable-player pool that, in live mode, gets filtered
# down to remaining (not-yet-kicked-off) fixtures. best-xi is deliberately
# excluded: it's the round's pre-round optimal-XI artifact and is never filtered.
_MIN_LIVE_POOL = 5

FILTERED_ARTICLE_SLUGS = ("captains", "transfers", "risky", "efficiency",
                          "defenders", "blowout-transfers")


def _live_pool(rows: list, now_iso: str) -> tuple[list, bool]:
    """Return (pool, used_fallback) for the filtered live-mode article set.

    Filters to upcoming (not-yet-kicked-off) rows; if that leaves fewer than
    _MIN_LIVE_POOL players (round nearly over), falls back to the full pool
    rather than publishing a near-empty list.
    """
    upcoming = articles.upcoming_rows(rows, now_iso)
    if len(upcoming) < _MIN_LIVE_POOL:
        return rows, True
    return upcoming, False


def _article_entries(rows: list, fantasy_round: int, live_pool: list | None = None) -> dict[str, list]:
    """Return {slug: entries_list} for the v2 article set.

    rows:      the FULL player pool -- always used for best-xi (a pre-round
               optimal-XI artifact that must never be filtered).
    live_pool: the pool to use for the filtered ranked-list articles (captains,
               transfers-adjacent, risky, efficiency, defenders, blowout-transfers).
               Defaults to `rows` (pre-round / non-live behaviour) when omitted.
    """
    pool = rows if live_pool is None else live_pool
    blow = articles.blowout_teams(fantasy_round)
    return {
        "captains":          articles.rank_captains(pool)[:20],
        "best-xi":           articles.select_xi(rows, "x_points"),
        "defenders":         articles.by_position(pool, "DEF")[:15],
        "risky":             articles.risky(pool)[:20],
        "efficiency":        articles.efficiency(pool)[:20],
        "blowout-transfers": articles.blowout_transfers(pool, blow)[:20],
    }


def _format_date(generated_at: str) -> str:
    """Format an ISO-8601 timestamp as a human date, e.g. '24 June 2026'."""
    dt = datetime.fromisoformat(generated_at)
    try:
        return dt.strftime("%-d %B %Y")
    except ValueError:
        # Windows / some platforms don't support %-d — strip leading zero manually
        return dt.strftime("%d %B %Y").lstrip("0")


def build(fantasy_round: int, sims: int, out: str, url: str,
          use_llm: bool = True) -> None:
    render.SITE_URL = url
    generated_at = datetime.now(timezone.utc).isoformat()
    date_str = _format_date(generated_at)
    now = datetime.now(timezone.utc)

    # --- Live round mode ---
    # Once a round's first kickoff has passed, matches finish overnight and a
    # rebuild should reflect reality: players who already played can't be newly
    # captained (FIFA's live captain chain only allows the armband to move to
    # someone whose match hasn't started), and finished fixtures should show
    # their actual score rather than a stale pre-match prediction.
    lock_time = fixtures.round_lock_time(fantasy_round)
    live = lock_time is not None and now > lock_time

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

    # --- Build per-article data ---
    live_pool_rows, live_fallback = (rows, False)
    if live:
        live_pool_rows, live_fallback = _live_pool(rows, now.isoformat())
        if live_fallback:
            print(f"Live mode: fewer than {_MIN_LIVE_POOL} upcoming players for "
                  f"round {fantasy_round} — falling back to the full player pool "
                  f"for the filtered articles.")
    entries_map = _article_entries(rows, fantasy_round,
                                   live_pool=live_pool_rows if live else None)
    results_map = articles.finished_results_map(fantasy_round) if live else None
    entries_map["matches"] = articles.match_predictions(
        match_samples, fantasy_round, results=results_map)
    # Transfer priorities need each team's advancement probability from the matches
    # article, so it's computed after — and only knockout rounds populate adv_map,
    # so transfer_priorities degrades gracefully to pure value-over-replacement
    # ranking during the group stage.
    adv_map = articles.advancement_map(entries_map["matches"])
    transfer_pool = live_pool_rows if live else rows
    entries_map["transfers"] = articles.transfer_priorities(transfer_pool, adv_map)
    nav = [(slug, articles.ARTICLE_TITLES[slug]) for slug in articles.ARTICLES]

    def w(path: str, text: str) -> None:
        full = os.path.join(out, path.lstrip("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)

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

        # Determine the subject (lead player) for prose focus
        if slug in ("best-xi", "matches"):
            subject = None  # team/match-framed, no single player centred
        else:
            subject = next(
                (e["name"] for e in entries if e["name"] not in used_leads),
                entries[0]["name"] if entries else None,
            )
            if subject:
                used_leads.add(subject)

        # Prose. In live mode, the filtered (remaining-fixtures) articles use a
        # fresh per-round cache namespace so the writer's cache doesn't keep
        # serving stale pre-round prose for entries that live filtering has
        # already changed; best-xi/matches keep the normal cache (their content
        # isn't filtered, so the ordinary cache is still valid).
        is_live_filtered = live and slug in FILTERED_ARTICLE_SLUGS
        cache_dir = (f"data/articles/round-{fantasy_round}-live" if is_live_filtered
                    else "data/articles")
        prose = writer.article_prose(slug, fantasy_round, entries, columns,
                                     cache_dir=cache_dir,
                                     use_llm=use_llm, subject=subject)
        prose_map[slug] = prose

        # Viz
        if is_matches:
            viz_html = render.match_predictions_html(entries)
        elif slug in _XI_ARTICLES:
            viz_html = render.pitch_svg(entries)
        else:
            viz_html = render.ev_bar(entries, columns[0])

        # JSON
        env = render.article_json("fifa_world_cup_fantasy", fantasy_round, slug,
                                  title, generated_at, sims, entries)
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
                              show_table=not is_matches, live=is_live_filtered))

    # --- Reddit kit (operator posting material — NOT published to the site) ---
    # data/ is gitignored; this never lands in dist/. Written after articles/prose
    # are built so the kit can pull real captain EV / close-game numbers.
    reddit_kit_text = reddit.reddit_kit(fantasy_round, entries_map, prose_map, date_str)
    reddit_dir = os.path.join("data", "reddit")
    os.makedirs(reddit_dir, exist_ok=True)
    reddit_kit_path = os.path.join(reddit_dir, f"round-{fantasy_round}.md")
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

    # --- Landing page ---
    # Featured = captains article (first in ARTICLES)
    captains_entries = entries_map["captains"]
    captains_cols = _COLUMNS["captains"]
    captains_prose = prose_map["captains"]
    captains_viz = render.ev_bar(captains_entries, captains_cols[0])

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

    landing_html = render.landing_page(fantasy_round, featured, feed, date_str=date_str,
                                       live=live)
    w("/index.html", landing_html)
    w(f"/round/{fantasy_round}/index.html", landing_html)

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

    live_note = (f" | LIVE mode (locked {lock_time.isoformat()}, "
                f"{len(live_pool_rows)} upcoming players)" if live else "")
    print(f"Built round {fantasy_round} → {out}/ "
          f"({len(rows)} players, {len(articles.ARTICLES)} articles) "
          f"| reddit kit → {reddit_kit_path}{live_note}")


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
