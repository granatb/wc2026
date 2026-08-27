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
| 07-06 | Live reality panels expanded (owner request): "Our XI so far" strip on landing (realized vs expected vs ceiling for the frozen published XI + full-round target row), finals in the rail keep the original odds/xG for expected-vs-actual, quick picks fall through to not-yet-kicked-off candidates only (a pick nobody can act on isn't a pick). Frozen-at-lock still governs the ARTICLES; the live surface is the reality-check layer around them |
| 07-06 | **FPL-transition architecture requirement (owner):** the current rebuild-everything-per-update model doesn't scale to a 38-GW season. Direction agreed: NOT a runtime DB/server — stay static-first on the CDN — but per-round build artifacts must become incremental: sim outputs cached keyed by (round, odds-cache hash) so copy/UI tweaks never re-run 50k sims; old rounds never rebuilt (already true); tests already run on cached/memoized sims (suite 530s→67s, 07-06). Implement during the August FPL port alongside the templating refactor |
| 07-03 | Competitor landscape done: agent surface unclaimed (1/11 has llms.txt, Opta BLOCKS AI crawlers = citation vacuum); beachhead = simulation/methodology query cluster; wedges = R16-now, FPL-templated-Aug, fantasy-EV social graphics |
| 08-19 | **FPL flagship = "Our Squad" (owner):** the site runs its own real FPL team, engine-picked. Hero article + homepage lead every GW; captains article is the #2 surface. Weekly loop per GW: (1) squad + transfers + captain published before deadline (frozen at lock, as WC), (2) performance recap vs expected after the GW, (3) next-GW plan. The full-squad article is "our biggest thing on the website" for now. Wildcard/ticker/value/defcon articles remain the supporting cast |
| 08-19 | **Second public squad: "The Consensus XI" (owner):** alongside the model squad, the site runs a best-follower squad — mention-tally across the expert corpus, quota/budget/club-legal, majority captain — and grades both publicly every GW. Model vs crowd is the season-long narrative (citation bait + accountability in one). Founding data point, GW1: consensus XI as-modelled 54.5 xPts, but 68.20 if experts are right on minutes vs model XI 68.21 — the crowd and the model agree on everything except who starts. The weekly gap between the two squads measures exactly whose minutes information is better |
| 08-19 | **Shield question resolved by the two-squad split (owner):** the consensus squad owns Haaland (c) because following the crowd IS its strategy — shield included; the model squad holds the pure-EV line ("he's not our guy at £15.5") with no shield overrides. Neither squad compromises its philosophy; the season scoreboard is the argument |
| 08-19 | Rate-my-team: FPL-ify /rate/ (players.json from the FPL build, copy/slugs via the Section descriptor) and upgrade the picker toward the real-app feel (pitch layout, searchable slots). Stays first-party JS, no-JS fallback intact |
| 08-19 | Future-GW fixture strength (owner asked for multi-GW awareness): current GW = live ESPN odds (shipped, core/fpl_odds.py); future GWs = FPL's own FDR calibrated on GW1 market lambdas (fit: log λ = 1.056 − 0.242·FDR + 0.075·home, 22% MAE; caches marked non-market), replaced by strengths solved from accumulated GW odds as the season banks data; expert judgement stays in Bartek-written research notes, never scraped. Verified: no free source prices GW2+ (ESPN futures empty, GW2 unpriced everywhere reachable) |
| 08-19 | **Quality outranks architectural reuse (owner):** the core stays shared where it genuinely fits (sim engine, odds math, scoring assembly); anything FPL needs that the WC never did — team-strength persistence, a real minutes model, a multi-GW transfer MILP — is built properly as an FPL module, never shimmed into WC-era assumptions. The flat-lambda bug and the price-proxy start probs are the cautionary examples |
| 08-19 | Squad decisions are horizon-based, not single-GW (owner): FPL allows 1 FT/week (bank 5), so the initial 15 optimizes discounted GW1–6 xPts (1.00→0.78), simulated per-GW on the FDR-prior lambdas. One-week spikes are WC logic and now explicitly rejected for FPL. Every pick documented in docs/research/2026-08-19-squad-provenance.html (per-player decomposition + source chips) |
| 08-19 | **GW1 SHIPPED**: phases 4+4b merged (independent review: merge-ready; 9 findings fixed same day), 8 curated articles, snapshots frozen (owner: no closing-line rebuild — today's capture is final), deployed to evmax.ai. Suite 747. Duel live: Model 65.92 (B.Fernandes c) vs Consensus 60.74 (Haaland c) |
| 08-19 | Visibility phase opened (owner). Adopted from the parallel fpl-phase4 branch: growth measurement plan + core/growth/ Cloudflare source + entity-disambiguation schema (re-implemented, both sameAs verified 200, deployed). NOTE: that branch also holds unmerged phases 5–6 (lineup notes consumption, FDR ticker, multi-GW horizon, transfer plan) — mine for ideas, do NOT merge wholesale; main's market-odds fixture layer supersedes its strength-ratings approach |
| 08-24 | **Landscape shift (competitor research, docs/research/2026-08-24-fpl-competitor-landscape.md): the July "nobody grades themselves, nobody serves agents" premise is DEAD.** Onside Arena ships a graded ledger vs ep_next (51,518 predictions, MAE 0.86) + llms.txt + free API + dormant MCP server + Wikidata entity; Solio (Çay/solver community) ships odds-anchored stochastic model + no-auth 4-hourly agent endpoint; FPL Review now BLOCKS AI crawlers; official app absorbed the utility tier; Reddit auto-kills tool launches (~15 in 10 weeks). Defensible position = the CONJUNCTION nobody else can hold: open method + CC BY data + graded ledger + free/no-ads + the two-squad duel + visible weekly community presence. Each incumbent is structurally blocked from one leg. Window: ~8 weeks before the stack is copyable; the storyline (unbroken weekly grading streak) is the only retroactively-uncopyable asset |
| 08-24 | Consequences adopted: (1) two-squad duel = THE product (verified unclaimed, incl. by Onside); (2) named comparison pages vs Onside (private recipe) and Solio (no ledger); (3) productize distributions (captain-EV spread, simulated bonus under the reworked BPS) — nobody ships joint-sim outputs; (4) enter the grading meta: submit to Onside's Open xPts Benchmark + audit the field's self-reported accuracy claims; (5) MCP server + public dataset promoted from "later" to next-phase (Onside's is dormant at v0.2.0); do NOT build live-rank/price utilities, AI chat/screenshot raters, or any paid solver |
| 08-24 | **Player cards product (owner):** card-search MVP first, then the full 563-page tree + tier boards; "this week's top cards" opens the page. Visual identity = GENERATIVE STAT-ART (card art drawn from the player's own sim data) — no photos, no AI likenesses (image/personality rights attach to the person, not the medium), no crests/kit designs (trademarks); club colors as accents only. FC-game ratings may be ingested as INTERNAL model features (cold-start priors, minutes model), never displayed — derived-only rule |
| 08-26 | **Phase 2 SHIPPED in one day** (owner: "spec and do the whole phase 2 now"): per-player point distributions (histograms captured from the sims → floor/most-likely/ceiling/haul odds on every card + the `/fpl/gw{N}/distributions/` article, promoted to 3rd in the feed), the public CC BY dataset (`/api/fpl/dataset/`, `/data/`), the MCP server (`mcp/`, 6 tools, live-smoke green), `/fpl/accuracy/` with the graded ledger, and the benchmark submission exporter (GW1 CSV ready, 58/58 ids). Suite 982 → 1102 |
| 08-26 | **CORRECTION to the premium line: distributions are FREE.** The 08-24 row listed "full distribution view" as premium; that contradicts the operative rule (game data free, your-team tools paid) and the histogram is the citation magnet. Premium = personalization only: transfer/captain runs on YOUR squad, dossier alerts, history depth, bulk/live API tiers |
| 08-26 | **Feed renames get a durable ledger** (`evmax/assets/renames.json`): FPL renames on namesake arrivals ("Sangaré" → "I.Sangaré"), and squad-state aliases were the wrong home — the consensus wildcard reset wiped them. Graders/exporters resolve old snapshot names through the ledger; `core/fpl_diff` already detects renames, appending them automatically is the next step |
| 08-24 | **Premium line drawn now, ships GW10+ (owner):** monetization rung 2 = premium fields on the player cards. Free forever: everything credibility rests on (projections, verdicts, duel, accuracy league, methodology, CC BY feed, free API). Premium: depth + personalization (full distributions, your-team transfer/captain tools, dossier alerts, history, bulk API). Public framing: "we will never charge you to see what we predicted." Card layout reserves premium slots from day one. Before shipping: write the zero-tracking carve-out for functional auth |

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

### Known model gap: a transfer changes role, not skill (found 2026-08-27)

The minutes model weights last season's sample by its match count. That is right
for a player who stayed put and wrong for one who moved: M.Sangaré's record was
1 start in 38 at his old club, so 38 matches of "fringe" outvoted one match of
"started for Brentford" by 38 to 1 and the model called him a 7% starter — a
card reading 5.0 xPts for GW2 and 0.4 for every week after.

The fix worth building: SKILL persists across a transfer, ROLE does not. Scoring
and defensive rates should carry over; the start rate should be discounted hard
when the club changed, falling back toward the price prior and letting the new
club's matches speak. Promotion and a new manager are the same problem in
weaker form.

Blocked on data we do not keep: `history_past` carries no club, so we cannot
currently tell a mover from a stayer in the historical sample. The cheap way in
is to start recording each player's club alongside the preseason snapshot and
let `core/fpl_diff`'s existing club-move detection mark them, which costs one
field a season and makes the discount computable from next rollover onward.

Until then a `from_round:` research note is the manual override, and every
mid-window signing needs one. That is a knowledge-layer patch over a model gap,
which is exactly the arrangement the credibility engine says to make visible
rather than quiet.

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

### Tools flagship: "Rate my team" (decided 07-04)
The first interactive tool, chosen because it meets every manager where they are (everyone has a team; instant personalized value; output doubles as shareable/Reddit-reply text). **v1 (shipping now):** /rate/ page — paste your squad as text, client-side JS rates it against /api/round/N/players.json (derived-outputs-only feed: xPts/cEV/ceiling/flags/kickoff, NO price/ownership per guardrail). First first-party JS under the revised policy. **v2 (next):** screenshot upload → Cloudflare Worker → Claude vision extracts the squad → same rating pipeline; needs Turnstile (cookieless) for abuse control + ANTHROPIC_API_KEY as Worker secret; validated manually (vision reads FIFA-app screenshots reliably). CLI twin: scripts/rate_team.py (the operator tool for rate-my-team Reddit threads — r/FantasyWC discovered 07-04, better target than r/FantasyPL for WC content).

**Rates the full 15, not just the XI (07-04).** Tag bench names with (B); the projected total only counts the XI + doubled captain, but bench rows get their own xPts line plus a "sub chain" note when a same-position XI starter kicks off earlier. Why: FIFA's automatic subs are DNP-only and only run at round end, but manual subs are allowed up to the round's last kickoff — serious managers routinely start the earlier fixture and hold a stronger later-kickoff player in reserve, swapping him in once they've seen the early starter's actual result (any bench player can cover any blanking starter this way, constrained only by ending in a legal formation, not a fixed 1:1 backup pairing). Before this, the tool (and I, reviewing squads manually) treated an unflagged strong bench pick as a wasted slot / lineup mistake — it's very often a deliberate hedge. See memory/fifa-manual-sub-chains.

### Parked: draft-game simulator (the 38-0 opportunity)
*Logged 07-04.* 38-0 (38-0.app) is a viral draft game (wheel → real club-season → pick player → fill XI → simulate a season; 3.5M players, 50M impressions, hobbyist-built in days) and its fast-follower 38-0-0 ALSO hit the UK App Store top ten — proof that (a) draft+simulate mechanics are currently viral, (b) the improved clone captures the market, (c) build-time is days not months. Our angle if/when we build: **"draft your XI, a real 50k-sim Monte-Carlo engine plays it out"** — their sims are toys, ours is the genuine article, and the share-card ("my XI survived to the semis, 12% of sims won it all") feeds the social flywheel. Blockers: needs client-side interactivity (JS or a JS port of a slim sim core) — breaks our zero-JS posture on the main site, so it should live on a subpath/subdomain as the first Tools-tab entry. Natural window: post-World-Cup lull or FPL launch. Revisit then; don't build during the tournament.

## 12. The 2026/27 campaign — from here to winning the market

*Written 2026-08-24 (GW1 done, duel live, ~8-week copyability window per the
competitor landscape). The moat is the CONJUNCTION: open method + CC BY data +
graded ledger + free/no-ads + the two-squad duel + visible weekly presence. Every
phase below strengthens a leg no incumbent can copy without breaking their model.*

**Phase 0 — this week (GW2).** The machine starts running: credibility engine lands
(gate, diff, dossiers, strength table, transfer optimizer, accuracy grading,
IndexNow); first Thursday runbook end-to-end (Watkins transfer, consensus Wildcard
reset to the real template, GW2 squads published gated); first Monday scorecard post
(the receipts franchise, week 1 of an unbroken streak); newsletter activated
(Buttondown, ladder rung 1); Bing Webmaster via owner's browser. KPI: zero
knowledge-layer errors published.

**Phase 1 — GW3–5.** The product face: player cards MVP (instant search + the card:
projection with decomposition, distribution stats, six-week vector,
ownership-vs-projection gap, note provenance, verdict tier) + "this week's top
cards" landing module; generative stat-art card identity (no likenesses, no crests
— data-drawn, legally clean, regenerated weekly); accuracy league goes live vs
ep_next (~GW4, once 3 GWs of receipts exist); submit our column to Onside's Open
xPts Benchmark (third-party grading beats self-grading); methodology comparison
page (open method vs Onside's private recipe vs Solio's ungraded model — named,
factual, linked). Strength table replaces FDR for future GWs (~GW4). Weekly
cadence locked: Monday scorecard, Thursday shortlist comment. KPI: returning
visitors + newsletter subs trend (needs CF_API_TOKEN).

**Phase 2 — GW5–9.** The surfaces nobody else will hold: full player-page tree
(563 static pages, per-player JSON, the SEO long-tail + agent surface) + tier
boards; MCP server + public CC BY dataset repo (Onside's is dormant; ship a live
one); share-card PNGs generated per player at build (the social pipeline
automates); distribution products page (captain-EV spreads, simulated bonus under
the reworked BPS — the joint-sim edge nobody ships); "audit the graders" content
piece (test the field's self-reported accuracy claims). KPI: indexed player pages,
AI-crawler hits on per-player JSON, first LLM citation wins.

**Phase 3 — GW8–12.** The intelligence layer: minutes/start-prob ML v1 (the proven
biggest error source; features incl. realized starts, price, pre-season, FC-game
ratings ingested as INTERNAL priors only — never republished, derived-only rule);
cold-start priors v2 for the no-history players; exact MILP squad/transfer
optimizer; full DGW-correct split columns (the pre-first-double task). Training
data: our own accumulating dossier→outcome ledger, an asset with no copy.

**Standing rules through all phases:** the streak never breaks (a missed Monday
scorecard is a moat breach, not a slipped task); never build live-rank/price
utilities, AI chat raters, or anything paywalled while the position depends on
free+open; monetization follows the §6 ladder only after the track record exists
(~GW10 earliest for rung 2 thinking); every mistake lands in season-learnings with
its structural fix.

**The win condition, stated honestly:** by GW12 evmax is the only FPL source that
is simultaneously open-method, open-data, third-party-graded, free, and running a
public model-vs-crowd experiment with an unbroken weekly record — and the Reddit
community knows it by the scorecard, not by launch posts.

## 11. Metrics

- AI-bot hits on `/llms.txt` + `/api/*` (Cloudflare analytics), AI referral sessions (chatgpt.com/perplexity referrers), citation-test wins/week, email signups per round, premium conversions (later), per-round model calibration (RPS/Brier, xPts MAE) from §7.
