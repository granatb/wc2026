"""Build the evmax static site for one round into dist/.

Usage: python3 evmax/build.py --round 3 [--sims 50000] [--out dist] [--url https://evmax.pages.dev]
Run from the repo root.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from core import engine_events, espn, fixtures, research
from evmax import articles, render


def _kickoffs_for_round(fantasy_round: int) -> dict:
    out = {}
    for f in fixtures.by_round(fantasy_round):
        for team in (f.home, f.away):
            iso = f.kickoff.isoformat()
            if team not in out or iso < out[team]:
                out[team] = iso
    return out


# article slug -> (table columns, chart metric, builder(rows, round) -> entries)
def _article_entries(rows, fantasy_round):
    blow = articles.blowout_teams(fantasy_round)
    return {
        "best-xi":          (["x_points", "price", "ownership_pct"], articles.select_xi(rows, "x_points")),
        "captains":         (["captain_ev", "x_points", "ownership_pct"], articles.rank_captains(rows)[:20]),
        "high-ceiling-xi":  (["ceiling", "x_points", "ownership_pct"], articles.select_xi(rows, "ceiling")),
        "differentials":    (["x_points", "ownership_pct", "price"], articles.differentials(rows)[:20]),
        "best-value-xi":    (["value", "x_points", "price"], articles.select_xi(articles.rank_value(rows), "value")),
        "blowout-transfers":(["x_points", "captain_ev", "price"], articles.blowout_transfers(rows, blow)[:20]),
    }


def build(fantasy_round: int, sims: int, out: str, url: str) -> None:
    render.SITE_URL = url
    generated_at = datetime.now(timezone.utc).isoformat()

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

    built = _article_entries(rows, fantasy_round)
    nav = [(slug, articles.ARTICLE_TITLES[slug]) for slug in articles.ARTICLES]

    def w(path, text):
        full = os.path.join(out, path.lstrip("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)

    highlights, latest_index = {}, {}
    for slug, (columns, entries) in built.items():
        title = f"{articles.ARTICLE_TITLES[slug]} — Round {fantasy_round}"
        json_url = f"/api/round/{fantasy_round}/{slug}.json"
        env = render.article_json("fifa_world_cup_fantasy", fantasy_round, slug, title,
                                  generated_at, sims, entries)
        w(json_url, json.dumps(env, ensure_ascii=False, indent=2))
        w(f"/round/{fantasy_round}/{slug}/index.html",
          render.article_page(fantasy_round, slug, title, entries, columns, nav, json_url))
        highlights[slug] = render.summary_sentence(slug, entries)
        latest_index[slug] = json_url

    w(f"/round/{fantasy_round}/index.html", render.hub_page(fantasy_round, nav, highlights))
    w("/index.html", render.hub_page(fantasy_round, nav, highlights))
    w("/api/latest.json", json.dumps(
        {"round": fantasy_round, "generated_at": generated_at, "articles": latest_index},
        ensure_ascii=False, indent=2))
    w("/llms.txt", render.llms_txt(fantasy_round, nav))
    w("/robots.txt", render.robots_txt())
    w("/sitemap.xml", render.sitemap_xml(fantasy_round, nav))
    print(f"Built round {fantasy_round} → {out}/ ({len(rows)} players, {len(built)} articles)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--sims", type=int, default=50_000)
    ap.add_argument("--out", default="dist")
    ap.add_argument("--url", default="https://evmax.pages.dev")
    a = ap.parse_args()
    build(a.round, a.sims, a.out, a.url)


if __name__ == "__main__":
    main()
