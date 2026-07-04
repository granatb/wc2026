# evmax — strategy & roadmap

*Canonical strategy file. Site launched 2026-06-24; strategy consolidated 2026-07-03. Update as decisions land.*

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
| 07-03 | Focus: turn odds into stat analysis for betting-minded people at popular events |
| 07-03 | Odds source: ESPN free feed; The Odds API (~$30/mo) as fallback only if ESPN breaks and revenue justifies |
| 07-03 | Comparison content: reference pundit/site picks vs our EVs (citation bait + accountability) |
| 07-03 | Backtesting: build now — trust layer, premium unlock, comparison-article fuel |
| 07-03 | Reddit: disclosed human-in-the-loop account, model-generated content, 90/10 rule; NO covert automation |
| 07-03 | FPL pivot in August (empirically de-risked: decade of tolerated commercial FPL tooling); Holdet gated on ToS check |
| 07-04 | Domain: evmax.ai bought (rename options rejected — collision judged minor vs. momentum; entity-qualified titles instead) |
| 07-04 | Data license: CC BY 4.0 (reuse-with-attribution = the growth strategy, formalized) |
| 07-04 | Zero-cookie/zero-third-party posture locked in (self-hosted fonts; no analytics until a cookieless one is chosen) |
| 07-04 | Policy clarified after owner challenge: the commitment is zero-TRACKING and zero-THIRD-PARTY code, NOT zero-JavaScript. First-party, self-hosted, no-data-collection JS is allowed as progressive enhancement (pages must fully work without it — that is what crawlers/agents read). CI added (GitHub Actions, unit tests on push). Known accepted debt: hand-rolled f-string templating + CSS-in-Python — refactor trigger is the FPL-season transition, not before |
| 07-04 | Newsletter: Buttondown, no-JS form (account registration pending) |
| 07-04 | Engine changes are evidence-gated: Shin/power de-vig implemented but default held (bake-off n=0 — cache bug found+fixed; gate opens with accumulated closing lines, realistically FPL season) |
| 07-04 | **Articles are FROZEN at lock** — no mid-round mutation of published lists (owner decision: readers must see what we said and how it worked). The only live element is predicted-vs-actual (matches scoreboard, track record). Live-list filtering built then deliberately reverted same day |
| 07-04 | Fixture-guide article added (clean-sheet probabilities per tie, blowout targets, low-goal forward fades) — from the R16 content-scan gaps |
| 07-03 | Competitor landscape done: agent surface unclaimed (1/11 has llms.txt, Opta BLOCKS AI crawlers = citation vacuum); beachhead = simulation/methodology query cluster; wedges = R16-now, FPL-templated-Aug, fantasy-EV social graphics |

## 4. Legal / ToU guardrails (standing policy)

1. **Derived-only rule:** public pages + API expose *model outputs* (xPts, EV, probabilities, scorelines). Raw upstream numbers (bookmaker prices) never appear. Prices/ownership% appear only as per-player context columns, never as a standalone feed/endpoint.
2. **Never name upstream sources** on the public site (generic "market odds"). No bookmaker names, no endpoint names.
3. **No FIFA/PL trademarks in branding**; game names as plain description only. DONE 07-03: site-wide footer disclaimer (independence, model-estimates, not-betting-advice, 18+/gamble-responsibly) + About "Independence & disclaimer" section + /privacy/ page. Site is zero-cookie/zero-third-party (fonts self-hosted after LG München GDPR ruling on remote Google Fonts) so NO consent banner needed. Data licensed CC BY 4.0 (attribution = the growth strategy, formalized).
4. **News = model-delta journalism only:** write "what changed in our projections and why," link outlets, never reproduce their text.
5. **Polite fetching:** cached, a handful of requests per round (de minimis).
6. **Holdet ToS review before monetizing the Danish site.**
7. **Bookmaker affiliate = last monetization rung**, only after jurisdiction-scoped compliance review (UK CAP/BCAP, 25% under-18 audience rule).
8. Legal posture (researched 07-03): scraping public unauthenticated endpoints ≠ CFAA violation (hiQ); facts/odds not copyrightable (Feist, NBA v. Motorola); EU sui generis database right fails for single-source *created* sports data (BHB v. William Hill, Fixtures Marketing). Residual risk = contract (ToU) + technical blocking; zero observed enforcement in the ESPN-API and commercial-FPL-tool ecosystems. Derived analytics ≈ safest position in the industry.

## 5. GEO playbook

**Mechanics:** answer engines retrieve from Google/Bing indexes, then synthesize → search position ≈ citation probability. GEO = SEO + citability formatting (stat-dense, quotable, structured — KDD'24: ~30–40% visibility lift). Freshness dominates for event queries (QDF).

**Done:** per-intent article pages, JSON per article, `llms.txt`, robots allow-list (GPTBot/ClaudeBot/PerplexityBot/…), schema.org Dataset+Article, stat-dense LLM prose, dates.

**To do (priority order):** *(competitor landscape 07-03: `docs/research/2026-07-03-competitor-landscape.md` — evmax had ZERO retrieval presence across 15 target queries and the "evmax" entity collides with EV-charger brands; items 1-2 gate everything else)*
1. **Buy real domain + entity disambiguation** — evmax.com is parked (EV-charger collision on the name); attach owned domain, and phrase titles/llms.txt/schema as "evmax fantasy simulations"-style to disambiguate the entity.
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
- Deep-research program completed 2026-07-03: 99 methods / 9 domains → roadmap at `docs/research/2026-07-03-engine-improvement-roadmap.md` (corpus JSON alongside). Headline: the −2.3 xPts gap likely traces to proportional de-vig + 1X2-only λ inversion (documented −0.10–0.15 goals/team under-recovery; AH probabilities are unbiased). Domains covered: score models beyond Dixon-Coles, de-vig methods (Shin), minutes projection, player event rates (xG/xA-based), joint simulation/correlation, portfolio+ownership game theory, Bayesian in-tournament updating, ML benchmarks, validation/calibration.
- Known weaknesses to attack: xPts run low vs Rotowire (~2.3 pts, R2 audit); minutes model is crude (starters=60'); MID defensive contribution is an estimate; blend weights hand-set; no ownership/rank game theory in public picks.

### §9 status — research → action (as of 07-04)
| Roadmap item (research) | Status |
|---|---|
| Phase 0: measurement first (backtest harness, frozen snapshots) | ✅ SHIPPED — /track-record/ live, R3 graded (captain regret 16, XI 72.8→72.0), snapshots freeze at lock |
| Quick win #1: Shin/power de-vig | ✅ code + tests + bake-off script; ⏸ default held by n≥40 evidence gate (n=0) |
| Closing-line preservation (enables CLV/bake-offs) | ✅ FIXED — raw h2h/totals were being clobbered post-kickoff; now frozen |
| AH-anchored λ (quick win #2) | ❌ blocked — ESPN feed has no Asian handicap; needs multi-book source (The Odds API/Betfair) |
| Minutes model (quick win, highest impact) | ⬜ not started — top engine priority |
| Scenario-matrix export (portfolio layer) | ⬜ not started |
| ET/pens knockout correction | 🟡 lightweight version only (p_advance λ-share split in match predictions/transfers) |
| Distributions-over-rankings philosophy | 🟡 partial — ceiling_ratio/"Safe floor" chips; validated by R3 grades (aggregates calibrated, rankings noisy) |
| Bayesian in-tournament updating / hierarchical player priors / DR minute-sim | ⬜ backlog (L-sized) |

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

### Parked: draft-game simulator (the 38-0 opportunity)
*Logged 07-04.* 38-0 (38-0.app) is a viral draft game (wheel → real club-season → pick player → fill XI → simulate a season; 3.5M players, 50M impressions, hobbyist-built in days) and its fast-follower 38-0-0 ALSO hit the UK App Store top ten — proof that (a) draft+simulate mechanics are currently viral, (b) the improved clone captures the market, (c) build-time is days not months. Our angle if/when we build: **"draft your XI, a real 50k-sim Monte-Carlo engine plays it out"** — their sims are toys, ours is the genuine article, and the share-card ("my XI survived to the semis, 12% of sims won it all") feeds the social flywheel. Blockers: needs client-side interactivity (JS or a JS port of a slim sim core) — breaks our zero-JS posture on the main site, so it should live on a subpath/subdomain as the first Tools-tab entry. Natural window: post-World-Cup lull or FPL launch. Revisit then; don't build during the tournament.

## 11. Metrics

- AI-bot hits on `/llms.txt` + `/api/*` (Cloudflare analytics), AI referral sessions (chatgpt.com/perplexity referrers), citation-test wins/week, email signups per round, premium conversions (later), per-round model calibration (RPS/Brier, xPts MAE) from §7.
