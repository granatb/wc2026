"""Build the evmax static site for one round into dist/.

Usage:
    python3 -m evmax.build --round 3 [--sims 50000] [--out dist]
                           [--url https://evmax.pages.dev] [--no-llm]
Run from the repo root.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from core import engine_events, espn, fixtures, research
from evmax import articles, render, writer

# ---------------------------------------------------------------------------
# Per-article column specs (primary metric first, then richer set)
# ---------------------------------------------------------------------------
_COLUMNS = {
    "captains":          ["captain_ev", "x_points", "ceiling", "price", "value", "ownership_pct"],
    "best-xi":           ["x_points", "captain_ev", "ceiling", "price", "value", "ownership_pct"],
    "high-ceiling-xi":   ["ceiling", "x_points", "captain_ev", "price", "ownership_pct"],
    "differentials":     ["x_points", "ceiling", "captain_ev", "price", "value", "ownership_pct"],
    "efficiency":        ["value", "x_points", "price", "captain_ev", "ownership_pct"],
    "blowout-transfers": ["x_points", "captain_ev", "ceiling", "price", "ownership_pct"],
}

# XI articles get pitch SVG; others get an EV bar
_XI_ARTICLES = {"best-xi", "high-ceiling-xi"}


def _kickoffs_for_round(fantasy_round: int) -> dict:
    out = {}
    for f in fixtures.by_round(fantasy_round):
        for team in (f.home, f.away):
            iso = f.kickoff.isoformat()
            if team not in out or iso < out[team]:
                out[team] = iso
    return out


def _article_entries(rows: list, fantasy_round: int) -> dict[str, list]:
    """Return {slug: entries_list} for the v2 article set."""
    blow = articles.blowout_teams(fantasy_round)
    return {
        "captains":          articles.rank_captains(rows)[:20],
        "best-xi":           articles.select_xi(rows, "x_points"),
        "differentials":     articles.differentials(rows)[:20],
        "efficiency":        articles.efficiency(rows)[:20],
        "high-ceiling-xi":   articles.select_xi(rows, "ceiling"),
        "blowout-transfers": articles.blowout_transfers(rows, blow)[:20],
    }


def build(fantasy_round: int, sims: int, out: str, url: str,
          use_llm: bool = True) -> None:
    render.SITE_URL = url
    generated_at = datetime.now(timezone.utc).isoformat()

    # --- Simulate ---
    players, _matches = engine_events.simulate_round(
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
    entries_map = _article_entries(rows, fantasy_round)
    nav = [(slug, articles.ARTICLE_TITLES[slug]) for slug in articles.ARTICLES]

    def w(path: str, text: str) -> None:
        full = os.path.join(out, path.lstrip("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)

    # --- Render each article ---
    prose_map: dict[str, dict] = {}
    latest_index: dict[str, str] = {}

    for slug in articles.ARTICLES:
        entries = entries_map[slug]
        columns = _COLUMNS[slug]
        title = f"{articles.ARTICLE_TITLES[slug]} — Round {fantasy_round}"
        json_url = f"/api/round/{fantasy_round}/{slug}.json"

        # Prose
        prose = writer.article_prose(slug, fantasy_round, entries, columns,
                                     use_llm=use_llm)
        prose_map[slug] = prose

        # Viz
        if slug in _XI_ARTICLES:
            viz_html = render.pitch_svg(entries)
        else:
            viz_html = render.ev_bar(entries, columns[0])

        # JSON
        env = render.article_json("fifa_world_cup_fantasy", fantasy_round, slug,
                                  title, generated_at, sims, entries)
        w(json_url, json.dumps(env, ensure_ascii=False, indent=2))
        latest_index[slug] = json_url

        # HTML
        w(f"/round/{fantasy_round}/{slug}/index.html",
          render.article_page(fantasy_round, slug, title, prose, entries,
                              columns, nav, json_url, viz_html,
                              generated_at=generated_at))

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

    # Feed = the other five articles
    feed = []
    for slug in articles.ARTICLES:
        if slug == "captains":
            continue
        entries = entries_map[slug]
        columns = _COLUMNS[slug]
        prose = prose_map[slug]
        primary_col = columns[0]
        top_entry = entries[0] if entries else {}
        # stat_value: formatted primary metric of top entry
        stat_value = render._fmt(primary_col, top_entry)
        stat_label = render._COL_LABEL.get(primary_col, primary_col)
        feed.append({
            "slug": slug,
            "headline": prose["headline"],
            "teaser": prose["standfirst"],
            "stat_value": stat_value,
            "stat_label": stat_label,
        })

    landing_html = render.landing_page(fantasy_round, featured, feed, nav)
    w("/index.html", landing_html)
    w(f"/round/{fantasy_round}/index.html", landing_html)

    # --- Agent / meta files ---
    w("/api/latest.json", json.dumps(
        {"round": fantasy_round, "generated_at": generated_at,
         "articles": latest_index},
        ensure_ascii=False, indent=2))
    w("/llms.txt", render.llms_txt(fantasy_round, nav))
    w("/robots.txt", render.robots_txt())
    w("/sitemap.xml", render.sitemap_xml(fantasy_round, nav))

    print(f"Built round {fantasy_round} → {out}/ "
          f"({len(rows)} players, {len(articles.ARTICLES)} articles)")


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
    ap.add_argument("--url", default="https://evmax.pages.dev",
                    help="Canonical site URL (default https://evmax.pages.dev)")
    ap.add_argument("--no-llm", dest="no_llm", action="store_true",
                    help="Skip the LLM tier; use cache-or-template only")
    a = ap.parse_args()
    build(a.round, a.sims, a.out, a.url, use_llm=not a.no_llm)


if __name__ == "__main__":
    main()
