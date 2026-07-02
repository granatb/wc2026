# evmax — strategy & roadmap

*Canonical strategy file. Started 2026-06-24 (day of launch). Update as decisions land.*

## 1. Thesis

One odds/simulation engine feeding two flywheels:
- **Human flywheel:** shareable simulation stats/graphics → social + search traffic → brand.
- **Agent flywheel:** structured, citable, transparent pages + free JSON API → LLM/agent citations → high-intent referrals.

**Transparency is the differentiator.** Incumbents hide their models ("our AI says…"); we publish methodology, numbers, and a track record. The same asset wins both flywheels. Content is **explicitly LLM-written from the model's numbers** — honesty about this is on-brand, not a liability.

**Event-ratchet traffic model.** We optimize for event peaks (World Cup rounds, knockouts, later FPL gameweeks, "popular events"), not steady-state traffic. For event queries, *freshness beats authority* — every event resets the leaderboard, which neutralizes our cold start. Each peak deposits permanent residue (backlinks, brand searches, citations, email signups) that raises the floor for the next peak. Quiet valleys are expected and fine.

**Traction requires the engine to actually be good.** Marketing multiplies engine quality; it cannot replace it. Backtesting + continuous model improvement is a first-class workstream, not a nice-to-have.

## 2. Current state (shipped 2026-06-24)

- **Live:** https://evmax.pages.dev (Cloudflare Pages, project `evmax`).
- 7 auto-generated articles per round (captains, match predictions/close games, best XI, defenders, risky ceilings, EV-per-price, blowout targets), LLM prose grounded+validated against engine numbers (cache→API→template tiers), editorial design, pitch SVG, per-article JSON API, `llms.txt`, AI-crawler allow-list, sitemap, About page.
- **Update routine:** `python3 -m evmax.build --round N --out dist` → `npx wrangler pages deploy dist --project-name evmax --branch main --commit-dirty=true`. `ANTHROPIC_API_KEY` in git-ignored `.env`.
- Engine: ESPN market odds (1X2/totals/scorer props) → de-vig → Dixon-Coles λ → 50k Monte-Carlo → per-player events → FIFA/Holdet scoring → EV/ceiling order books. Research overlay (markdown notes, per-game blend weight).

## 3. Decisions log

| Date | Decision |
|---|---|
| 06-24 | Two separate sites: evmax (global/EN, FIFA WC now, events later) + Holdet sibling (DA/EN) — not tabs |
| 06-24 | Editorial identity ("The Athletic" style), light; rejected generic dark-dashboard and broadsheet pastiche |
| 06-24 | Articles are the product (one query intent per page); landing = featured + feed |
| 06-24 | LLM-written prose at build time, grounded in engine numbers; authorship stated openly |
| 06-24 | No player headlines >1 article per round (subject de-dup) |
| 06-24 | Focus: turn odds into stat analysis for betting-minded people at popular events |
| 06-24 | Odds source: ESPN free feed; The Odds API (~$30/mo) as fallback only if ESPN breaks and revenue justifies |
| 06-24 | Comparison content: reference pundit/site picks vs our EVs (citation bait + accountability) |
| 06-24 | Backtesting: build now — trust layer, premium unlock, comparison-article fuel |
| 06-24 | Reddit: disclosed human-in-the-loop account, model-generated content, 90/10 rule; NO covert automation |
| 06-24 | FPL pivot in August (empirically de-risked: decade of tolerated commercial FPL tooling); Holdet gated on ToS check |

## 4. Legal / ToU guardrails (standing policy)

1. **Derived-only rule:** public pages + API expose *model outputs* (xPts, EV, probabilities, scorelines). Raw upstream numbers (bookmaker prices) never appear. Prices/ownership% appear only as per-player context columns, never as a standalone feed/endpoint.
2. **Never name upstream sources** on the public site (generic "market odds"). No bookmaker names, no endpoint names.
3. **No FIFA/PL trademarks in branding**; game names as plain description only. About page carries: *"evmax is not affiliated with or endorsed by FIFA or any fantasy game operator. All projections are our own model output."* (TODO: add.)
4. **News = model-delta journalism only:** write "what changed in our projections and why," link outlets, never reproduce their text.
5. **Polite fetching:** cached, a handful of requests per round (de minimis).
6. **Holdet ToS review before monetizing the Danish site.**
7. **Bookmaker affiliate = last monetization rung**, only after jurisdiction-scoped compliance review (UK CAP/BCAP, 25% under-18 audience rule).
8. Legal posture (researched 06-24): scraping public unauthenticated endpoints ≠ CFAA violation (hiQ); facts/odds not copyrightable (Feist, NBA v. Motorola); EU sui generis database right fails for single-source *created* sports data (BHB v. William Hill, Fixtures Marketing). Residual risk = contract (ToU) + technical blocking; zero observed enforcement in the ESPN-API and commercial-FPL-tool ecosystems. Derived analytics ≈ safest position in the industry.

## 5. GEO playbook

**Mechanics:** answer engines retrieve from Google/Bing indexes, then synthesize → search position ≈ citation probability. GEO = SEO + citability formatting (stat-dense, quotable, structured — KDD'24: ~30–40% visibility lift). Freshness dominates for event queries (QDF).

**Done:** per-intent article pages, JSON per article, `llms.txt`, robots allow-list (GPTBot/ClaudeBot/PerplexityBot/…), schema.org Dataset+Article, stat-dense LLM prose, dates.

**To do (priority order):**
1. **Buy real domain** (evmax.com/.io) and attach — `*.pages.dev` subdomain caps trust/brand equity. ~$10/yr.
2. **Bing Webmaster + IndexNow** (Perplexity/Copilot ride Bing; near-zero competition) + **Google Search Console**.
3. **Track-record page** (see §7) — the authority asset.
4. **Comparison articles** ("our EV vs consensus picks; who was right") each round.
5. **Reddit presence** (§8) — Reddit is over-weighted in LLM training data and Google.
6. **Stable archive URLs** (`/round/N/...` already stable; keep old rounds live forever).
7. **Weekly citation test loop:** ask ChatGPT/Claude/Perplexity the target queries, log who gets cited, tune.
8. Expectation setting: ChatGPT cites ~3% of answers; crawl-to-referral ratios brutal (~10⁴:1); but AI referrals convert ~7% (paid-search quality). Volume comes from event peaks.

## 6. Monetization ladder (risk-ordered; don't skip rungs)

1. **Email list (now).** "Get next round's sims the moment odds drop" capture on every article. Purpose: *store the peak* — reactivate at the next event for free; day-1 email surge doubles as a ranking signal during the window that matters; the list is the conversion pool and the only owned channel. Monetizes via premium conversion (2–5% norms), sponsorships (~$20–40 CPM at scale), affiliate-in-email.
2. **Premium tier** (post track-record): free full rankings → paid deeper stats/tools (~€4–5/mo; FFS-proven).
3. **Fantasy-adjacent affiliate** (fantasy platforms/tools, not bookmakers).
4. **API freemium:** free tier stays free forever (it *is* the GEO distribution); paid = volume/history/live.
5. **Bookmaker affiliate** — last, post legal review.
- Watchlist: Cloudflare pay-per-answer / x402 small-publisher onboarding (join when open; never the strategy). Publisher programs (Perplexity/OpenAI) are big-media-only today.

## 7. Backtesting / track record (build next)

- Compare our pre-round xPts/captain EV vs realized FIFA points per round (realized data exists: `data/fifa/stats_rN.json`, event IDs decoded; `core/realized.py`).
- Publish per-round: projection vs actual (players + captains + scorelines), calibration stats, honest misses.
- Page: `/track-record/` + JSON endpoint. Feeds comparison articles and premium credibility. Also becomes the engine-improvement measurement harness (§9).

## 8. Reddit playbook (disclosed, human-in-the-loop)

- One account, run by Bartek, bio: "I run evmax.com — Monte-Carlo sims on market odds; posts are generated from my model."
- **Never covert automation** (Reddit content-manipulation rules + Zurich-incident sensitivity + FTC disclosure; failure mode is brand-fatal for a transparency brand).
- 90/10 rule: mostly useful comments with numbers; 1–2 OC posts per round max; native image posts, methodology in comments, links sparingly.
- Start account now (age + karma before links). Subs: r/FantasyPL, r/soccer (OC stats), r/SoccerBetting, r/sportsbook.
- **Build addition:** per-round `reddit.md` kit (post title options, body text, sim graphic sized for Reddit) generated next to the articles.

## 9. Engine quality program

Principle: **the engine is the product; everything else is distribution.**
- Measurement first: backtesting harness (§7) + proper scoring rules, so every model change is judged on evidence.
- Deep-research program into state-of-the-art improvements launched 2026-06-24 (results → `docs/research/`): score models beyond Dixon-Coles, de-vig methods (Shin), minutes projection, player event rates (xG/xA-based), joint simulation/correlation, portfolio+ownership game theory, Bayesian in-tournament updating, ML benchmarks, validation/calibration.
- Known weaknesses to attack: xPts run low vs Rotowire (~2.3 pts, R2 audit); minutes model is crude (starters=60'); MID defensive contribution is an estimate; blend weights hand-set; no ownership/rank game theory in public picks.

## 10. Build backlog (priority order)

1. Backtesting harness + `/track-record/` page (§7)
2. Domain purchase + attach; Bing Webmaster + IndexNow + GSC (§5)
3. Email capture on articles + provider setup (§6.1)
4. About-page disclaimer + derived-only policy line (§4.3)
5. Reddit kit in build (`reddit.md`) (§8)
6. Comparison article type ("our EV vs consensus") (§5.4)
7. Engine improvements per research roadmap (§9)
8. Writer polish: allow aggregate sums in grounding (best-xi/risky currently fall back to template); fix "risky" prose tone
9. R32 rebuild + per-knockout-round content cadence
10. Tools tab phase 2 (build-a-team, sub analyser — engine's probe-a-change EV)
11. FPL engine port (August); Holdet sibling after ToS check
12. Citation test loop as a repeatable script

## 11. Metrics

- AI-bot hits on `/llms.txt` + `/api/*` (Cloudflare analytics), AI referral sessions (chatgpt.com/perplexity referrers), citation-test wins/week, email signups per round, premium conversions (later), per-round model calibration (RPS/Brier, xPts MAE) from §7.
