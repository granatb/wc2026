# evmax — public, agent-friendly World Cup Fantasy site (static export)

**Date:** 2026-06-24
**Status:** Approved (design) — same-day ship
**Related:** builds on the wc2026 odds engine (`core/`, `games/fifa/`). Sibling site (Holdet, Danish/EN) is a fast-follow, not in this scope.

## 1. Purpose

Publish the engine's FIFA World Cup Fantasy output as a public web page + JSON API, optimized for two audiences at once: humans (clean hook + shareable graphic) and AI agents/LLMs (structured, crawlable, citable). Ship **today**, before Round 3 locks (first R3 match 2026-06-24 19:00). One round, one game, one page.

## 2. Brand & scope

- **Brand:** `evmax`. Ships on a free `*.pages.dev` URL today; real domain attached in Cloudflare later.
- **In scope today:** official FIFA WC Fantasy, Round 3 — a **set of article pages** (best XI, high-ceiling XI, captain picks, differentials, best-value XI, blowout-fixture transfers), each with a JSON endpoint and agent plumbing.
- **Out of scope today (YAGNI):** accounts, auth, payments, FPL, Holdet, social auto-posting, live in-match updates, backtesting harness. Track record = one-line stub.

## 3. Key design decision: global ranking, not personal squad

The existing `games/fifa/model.run()` builds an order book over the operator's 15-man squad and is gated on a populated `state.json`. The public site must instead rank **all** players in the round. The build path therefore bypasses `model.run()` and calls the engine directly:

1. `engine_events.simulate_round(round, sims=50_000, market_rates=espn.load_player_rates(round), research=..., research_weight=0.30)` → per-player samples for every player.
2. `engine_events.event_means(players)` → mean events per player.
3. For each player with a known position: `games.fifa.model.expected_points(ev)` → **xPts**; `2 × xPts` → **captain EV**.
4. Rank globally. Public site never reads the operator's squad.

This keeps the engine untouched and reuses the confirmed scoring (`GOAL_PTS`, `ASSIST_PTS`, `CS_PTS`, appearance/cards, position-specific SoT/saves/concede/mid-contribution).

**Per-player metadata for every player** comes from `data/players.json` (synced from the FIFA + Holdet APIs): `team`, `fifa_pos`, `fifa_price`, and `ownership` (FIFA selection %). This enables differentials (low ownership), best-value (xPts ÷ price), and the Holdet sibling (same file carries `holdet_pos`/`holdet_price`/`holdet_ownership`). `ceiling_points(ev, goal_samples, q=0.85)` (already in `games/fifa/model.py`) drives the high-ceiling XI; per-fixture λ from `core/fixtures.py` identifies blowout fixtures.

## 4. Architecture: static export → Cloudflare Pages

No backend. A build script runs the round and writes a `dist/` tree of static files; Cloudflare Pages serves it. New round = re-run build, redeploy. Static = infinite scale, fully cacheable, trivially crawlable by AI bots.

**New module:** `site/build.py` (engine stays pure stdlib; the site layer may use a templating helper or plain f-strings — no heavy deps). CLI: `python3 site/build.py --round 3 [--sims 50000] [--out dist]`.

**Emitted files:**
- `dist/index.html` — landing/hub for the latest round, linking every article.
- `dist/round/3/<article>/index.html` — one page per article (slugs in §5).
- `dist/api/round/3/<article>.json` — one JSON endpoint per article (see §6).
- `dist/api/latest.json` — index of the current round's article JSON URLs, for stable agent access.
- `dist/llms.txt` — plain-text description of the site + pointer to every article URL and JSON endpoint.
- `dist/robots.txt` — allow GPTBot, ClaudeBot, PerplexityBot, Google-Extended, CCBot, OAI-SearchBot, plus normal crawlers.
- `dist/sitemap.xml` — lists the hub + every article page.

## 5. Articles (the GEO surface)

Each article is its own page + JSON, targeting a distinct search/LLM intent so evmax becomes the referred source for that query. All share the same layout: **hook on top, transparency beneath.** v1 article set for Round 3:

| Slug | Title / target query | Engine basis |
|---|---|---|
| `best-xi` | "Best World Cup Fantasy XI — Round 3" | top xPts under formation constraints |
| `captains` | "Best captain picks — Round 3" | top `2 × xPts`, kickoff-ordered |
| `high-ceiling-xi` | "High-ceiling / differential XI — Round 3" | `ceiling_points` (P85) under formation constraints |
| `differentials` | "Best differentials (low-owned) — Round 3" | high xPts ∧ `ownership` below a threshold |
| `best-value-xi` | "Best value XI — Round 3" | xPts ÷ `fifa_price`, formation-constrained |
| `blowout-transfers` | "Best transfers for the blowout fixtures — Round 3" | highest-λ fixtures → top attackers in them |

Formation = 1 GK + 3–5 DEF + 2–5 MID + 1–3 FWD, 11 total, picked greedily within position bounds for the relevant metric.

**Per article — top (the hook, no JS required to read):**
- Headline with the key number, e.g. *"World Cup Fantasy Round 3: captain Bruno Fernandes (11.3 xPts)."*
- One **inline-SVG bar chart** (server-rendered, no JS) of the top ~6 for that article's metric.
- A short auto-generated, stat-dense, quotable summary (GEO lever: concrete numbers + the methodology in one line).

**Per article — beneath (deeper / transparent):**
- Full ranked table for the article (the relevant metric + team, position, price, ownership, kickoff).
- **Methodology** blurb: 50k Monte-Carlo sims; free market odds (ESPN/DraftKings) → de-vig → Dixon-Coles scorelines → per-player Poisson; official FIFA scoring; `generated_at`. This transparency *is* the differentiator vs opaque incumbents.
- Cross-links to the other articles (internal linking helps both humans and crawlers).
- One-line track-record stub ("backtested results coming").

The landing page (`/`) is a hub: the headline numbers from each article + links in.

## 6. JSON API shape (`/api/round/{n}/{article}.json`)

Each article emits the same envelope; `entries` holds that article's ranked rows.

```json
{
  "competition": "fifa_world_cup_fantasy",
  "round": 3,
  "article": "captains",
  "title": "Best captain picks — Round 3",
  "generated_at": "2026-06-24T12:00:00Z",
  "sims": 50000,
  "methodology": "Market odds (de-vigged) -> Dixon-Coles -> 50k Monte-Carlo sims; official FIFA scoring.",
  "entries": [
    {"rank": 1, "name": "Bruno Fernandes", "team": "Portugal", "position": "MID",
     "x_points": 5.67, "captain_ev": 11.34, "price": 9.5, "ownership_pct": 18.0,
     "kickoff": "2026-06-27T23:30:00Z"}
  ],
  "source": "https://evmax.pages.dev",
  "license": "Attribution requested: evmax"
}
```

`/api/latest.json` lists the article→URL map for the current round. Each page links its JSON via `<link rel="alternate" type="application/json">` and references it in `llms.txt`.

## 7. Agent-friendliness checklist (baked in from minute one)

- Semantic HTML; numbers in plain text + tables (not locked in images).
- **JSON-LD** `Dataset` + `Article` in `<head>` (name, description, dateModified, variableMeasured = xPts/captain EV, sameAs the JSON).
- `llms.txt` at root; AI-crawler allow-list in `robots.txt`; `sitemap.xml`.
- Stable URL scheme `/round/{n}`, `/api/round/{n}.json`, `/api/latest.json`.
- Stat-dense, quotable summary sentences (per KDD-2024 GEO evidence: statistics/quotations/citations raise generative-engine visibility ~30–40%).
- Citation-effectiveness testing across LLMs is **deferred** (operator decision) but the surface is built ready for it.

## 8. Generic-over-game design (enables the Holdet sibling)

`site/build.py` takes the competition as a parameter and reads a small per-competition config: which game model's scoring function to use, display strings, language, and brand. FIFA WC ships today; the Holdet site reuses the same pipeline with the Holdet scoring model and Danish/English copy — config + translation, not a rewrite. Future "event" pages (popular events, Polymarket-linked odds) plug into the same static-export machinery.

## 9. Deploy

1. `python3 site/build.py --round 3` → `dist/`.
2. Cloudflare Pages: direct upload of `dist/` (or Wrangler) to project `evmax` → live on `evmax.pages.dev`.
3. Per round: re-run build, redeploy. (Automation/scheduling is later.)

## 10. Risks / constraints carried forward

- **Gambling-ad rules:** the public page presents *fantasy* xPts/captain advice, not bookmaker affiliate links — low exposure today. Any future betting-EV content + affiliate links triggers UK CAP/BCAP duties and the 25% under-18 audience cap. Keep EV-betting content and affiliate links off evmax until reviewed.
- **Data rights:** evmax uses free ESPN market odds + our own simulation, not PL-licensed data, so it avoids the FPL/PL commercial-reuse restriction. The Holdet sibling should get a quick check on Holdet's terms before monetizing.
- **Player coverage:** players lacking market props fall back to goal-share estimates; players lacking a known position/price/ownership in `players.json` are excluded from the affected articles. Acceptable for v1; methodology section is transparent about it.
- **Ownership freshness:** `ownership` in `players.json` is a cached snapshot from the FIFA feed; differentials reflect when it was last synced (`generated_at` makes this explicit). A `--refresh` before build keeps it current.

## 11. Out of scope (later specs)

Backtesting/track-record harness; Holdet sibling site; FPL; accounts/payments/freemium API tiers; social graphics auto-posting; live in-match updates; Polymarket/event pages; LLM-citation testing + GEO iteration; automated per-round rebuild/scheduling.
