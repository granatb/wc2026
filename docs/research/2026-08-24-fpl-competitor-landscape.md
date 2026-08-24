# evmax — FPL 2026/27 Competitor Landscape
*Researched 2026-08-24 (GW1 just finished; GW2 deadline Fri 2026-08-28). Extends the [2026-07-03 WC-era landscape](2026-07-03-competitor-landscape.md) and [2026-08-19 launch channels](2026-08-19-launch-channels.md) — WC-tier competitors, retrieval audit, and Reddit/channel mechanics are NOT repeated here. All robots/llms/API checks re-run live on 2026-08-24.*

**Headline finding up front:** the July report's core claim — "the machine-readable + published-accuracy niche has no direct competitor in fantasy football" — is **no longer true**. Two players claimed it during the WC→FPL transition window: **[Onside Arena](https://onsidearena.com/fpl-ai)** (public graded accuracy ledger, llms.txt, free REST API, npm MCP server, Wikidata entity) and **[Solio Analytics](https://fpl.solioanalytics.com/)** (market-odds stochastic model + no-auth AI-agent data endpoint, from the founder of the FPL solver community). The rest of this document maps the field; §10–§12 deal with what that means.

---

## 1. Tier 1 — Established paid/premium

| Site | Pricing (verified 2026-08) | Free tier | Methodology | Publishes vs paywalls |
|---|---|---|---|---|
| FPL Review | Patreon from €3.90/mo ([patreon.com/fplreview](https://www.patreon.com/fplreview)); solver is paid ([fplindex listing](https://fplindex.xyz)) | New "Free Model", 5→4 GW horizon ([announcement](https://x.com/fplreview/status/1952735100887601457)) | Partial docs, closed model ([docs.fplreview.com](https://docs.fplreview.com/)) | Numbers paywalled; site now a JS SPA + AI-crawler blocks (§9) |
| FF Scout | Chief Scout £10/mo or £50/yr; Mega Bundle £100/yr ([pricing](https://www.fantasyfootballscout.co.uk/pricing)) | Fixture ticker, team rating, some articles | None ("industry-leading RMT projections", no method) | Projections members-only; articles mostly free |
| FF Hub | Starter £11.99/mo / £59.90/yr; Pro £14.99/mo / £95.90/yr; Ultra £359.99/yr, at "50% off" ([Onside's price survey](https://onsidearena.com/best-fpl-app), [FFH join](https://www.fantasyfootballhub.co.uk/join)) | Basic account, AI team rating (temporarily) ([AllAboutFPL review, Aug 2026](https://allaboutfpl.com/2026/08/complete-detailed-review-of-fantasy-football-hub/)) | None; "Hub AI" black box | Opta stats, planners, expert reveals paywalled; "win your mini-league or money back" |
| FF Fix | Premium £2.78/mo, Premium Plus £3.18/mo (annual, "60% off"), Lifetime £295 ([premium page](https://www.fantasyfootballfix.com/premium/)) | ChatFPL Lite: 25 credits **lifetime**; free planner | None | Projections/AI transfers paywalled; price predictor free |
| FPL Team ([fpl.team](https://fpl.team/)) | Free + "wonderkid" ad-free tier (price undisclosed); iOS/Android apps | Nearly everything | Vague ("advanced models", inputs named, nothing verifiable) | Everything published, quality unaudited |
| FF Pundit | Free (odds/affiliate model) ([site](https://www.fantasyfootballpundit.com/)) | Everything, incl. [points predictor](https://www.fantasyfootballpundit.com/fpl-points-predictor/) | Raw odds → tables, no de-vig, no method page | Everything published |

Per-site notes:

- **[FPL Review](https://fplreview.com/)** — relaunched for 2026/27 as a full React SPA ("redesigned interface, improved mobile UX, upgraded solver"). Still the reference model among sharps: the [OpenFPL paper](https://arxiv.org/abs/2508.09992) uses its Massive Data Model as the commercial benchmark; the [Ultimate Truth series](https://fplreview.com/ultimate-truth-how-fpl-models-perform-relative-to-a-perfect-model/) is the closest an incumbent gets to self-grading (occasional articles, not a rolling ledger; the page is now unreachable to crawlers). Two big changes since July: a genuinely useful free model, and a **hard turn away from the agent web** — Cloudflare-managed robots.txt with `Content-Signal: search=yes, ai-train=no` and explicit Disallow for GPTBot, ClaudeBot, CCBot, Google-Extended, Bytespider, Applebot-Extended, meta-externalagent (verified by curl 2026-08-24). Its `/llms.txt` returns the SPA shell, not a real file. Blocks plain fetchers with 403.
- **[Fantasy Football Scout](https://www.fantasyfootballscout.co.uk/)** — relaunched site 24 July 2026 ([Onside's survey](https://onsidearena.com/best-fpl-app)). Claims: 350,000+ managers, "150+ Top 10k finishes, five former FPL champions", predicted lineups "90% accuracy" (homepage; no verifiable grading published). The interesting structural move is the **Mega Bundle (£100/yr)**: it now bundles *other people's tools* — ad-free [LiveFPL](https://www.livefpl.net/), [Premier Fantasy Tools](https://www.premierfantasytools.com/), [Mini League Mate](https://minileaguemate.com), The Fantasy Newsletter — FFS is becoming a distribution/aggregation layer for the free-tool ecosystem.
- **[Fantasy Football Hub](https://www.fantasyfootballhub.co.uk/)** — the receipts play here is outcome-based, not projection-based: the [Hub AI team](https://www.fantasyfootballhub.co.uk/fantasy-football-hub-ai-team-reveal-fpl) plays the real game publicly, "top 0.5% finishes" claimed, beat 99% of managers in 2023/24. Ultra tier (~£360/yr) is 1-to-1-coaching territory — the top of the market's willingness-to-pay. Affiliate machine intact (£25/signup, 556 tracked YouTube sponsorships per the Aug-19 doc). iOS app 3.9★ (483 ratings).
- **[Fantasy Football Fix](https://www.fantasyfootballfix.com/)** — most aggressive claims in the field: "89% of our Premium members won their main Mini-league last season" (homepage + premium page, no evidence published), "AI Team Score: 43 pts vs 36.6 FPL average", accuracy via testimonial only. Still **no robots.txt at all** (404, unchanged since July). Platform quality gap: iOS 4.5★ vs Google Play 2.5★ (1,680 reviews) ([Onside's survey](https://onsidearena.com/best-fpl-app)).
- **[Fantasy Football Pundit](https://www.fantasyfootballpundit.com/)** — unchanged: free odds-derived tables (clean-sheet odds, goalscorer odds, points predictor), no de-vigging, no methodology page, monetized by betting-adjacent content. evmax's pipeline remains a strict superset of its top-ranking format.

## 2. Tier 2 — Free/community analytics & open source

**The utility giants:**
- **[LiveFPL](https://www.livefpl.net/)** (~3.5M visits/mo as of July) — still free+ads, still JS-rendered and agent-invisible (robots.txt redirects to plan.livefpl.net which serves nothing useful). Two changes: a transfer planner at plan.livefpl.net, and monetization via the FFS bundles (ad-free LiveFPL is a paid FFS perk — [register page](https://www.fantasyfootballscout.co.uk/register)). The one-man free-utility king now has a revenue line through an incumbent.
- **[FPL Statistics](https://www.fplstatistics.co.uk/)** — **confirmed dead**: both fplstatistics.co.uk and fplstatistics.com unreachable (connection failure, curl 2026-08-24). The July thesis (free single-utility incumbents can vanish in one season) is now fact. Its niche (price predictions) was absorbed by [whatthef.pl](https://www.whatthef.pl), Fix — and now the official game itself (§4).
- **[fpl.page](https://fpl.page/)** (FPL Focal's dashboard) — free live dashboard (rank, EO, xG, price changes), collabs with FFS, backed by a 250k-sub YouTube channel. Has a real `/llms.txt` — a *policy* file (allow_indexing: true, allow_training: false, dated 2025-09-11), not a content map.
- **[FPL Form](https://fplform.com/)** — free predicted points + transfer optimizer, run by Nicholas Hope, "a complex algorithm" is the entire methodology disclosure, no accuracy record, no API. Maintained for 2026/27.

**The solver/quant community — now a company:**
- **[Solio Analytics](https://solioanalytics.com/)** — founded 2024-01-17 by **Sertalp Bilal Çay** (creator of FPL Optimized and the solver community) + 3 co-founders. The canonical community repo `sertalpbilal/FPL-Optimization-Tools` has been **renamed to [solioanalytics/open-fpl-solver](https://github.com/solioanalytics/open-fpl-solver)** (183★, pushed 2026-08-21). Product ([fpl.solioanalytics.com](https://fpl.solioanalytics.com/)): projections "built on **efficient sports markets** combined with a stochastic minutes, goals, assists, clean sheet and bonus model", solver over "the full branching gameweek tree". Free for next-5-GW optimisation; full-season for members. **And a "Public data endpoint for AI agents"**: `/api/data/latest.{md,html,json}` — live projections, captain picks, differentials, clean-sheet odds, refreshed every 4 hours, no auth, attribution requested. This is evmax's odds-anchored + agent-surface play, executed by the most trusted name in FPL analytics. What Solio does **not** do: publish methodology detail (no de-vig doc), publish a graded accuracy ledger, or run public squads.
- **[FPL Optimized](https://fploptimized.com/)** (Sertalp's free site, feeds Solio) — daily optimal squads, live xPts GW tracker, an **EV Calculator** ("expected points distribution calculator" — DIY input tool, not a published product), and the **[FPL Analytics xP League](https://fploptimized.com/fpl_analytics_league.html)** — a public league of analytics-community teams decomposed into xG/implied-odds/model/luck points ("generated using fplreview.com season review", "Partnered with Fantasy Football Hub"). Precedent that model-teams-competing-publicly is a recognized community format.
- **Open source health (GitHub API, 2026-08-24):** [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League) 1,788★, pushed 2026-08-21 — alive, still the default dataset. [AIrsenal](https://github.com/alan-turing-institute/AIrsenal) 347★, pushed 2026-08-24 — alive, still not a product. [daniegr/OpenFPL](https://github.com/daniegr/OpenFPL) 23★, last push 2025-08-15 — the [paper](https://arxiv.org/abs/2508.09992) matters (open ensemble matches FPL Review's MDM prospectively), the repo is quiet; an "OpenFPL v6.0.0" r/FantasyPL launch post (2026-08-16) was removed by Reddit both times it was tried. New entrant: [olbauday/FPL-Core-Insights](https://github.com/olbauday/FPL-Core-Insights) — 2026/27 dataset fusing FPL API + match stats + team Elo.

**The accuracy-adjacent tools:**
- **[Onside Arena](https://onsidearena.com/)** — full treatment in §6/§12; free tier + Pro £24.99/yr and Pro+ £59.95/yr ("50% off" from £49.90/£119.90; [pricing](https://onsidearena.com/pricing)).
- **[FPL Pulse](https://www.fplpulse.com/)** — live standings + mini-league finish simulator (10,000+ scenarios) + predicted points; Pulse Pro **£2.99/mo or £24.99/yr** — cheapest paid tier in the category. Published a real accuracy post: [MAE 0.81 vs official xP's 1.05 on GW20–38 2025/26, 15,572 player-fixtures; inputs disclosed incl. bookmaker odds; architecture withheld](https://www.fplpulse.com/blog/fpl-predicted-points-model). One-off benchmark, not a rolling graded ledger.
- **[Hive League](https://hiveleague.com/)** — crowdsourced predicted lineups that **grades FPL content sites' lineup accuracy on a public leaderboard** (real [llms.txt](https://hiveleague.com/llms.txt)). Traction is tiny — its own API shows the top leaderboard user has 18 predictions (`/api/leaderboard`, 2026-08-24). Proof of concept that "grade the graders" is a product idea; proof it doesn't market itself.
- **[FPL Copilot](https://fplcopilot.com/)** — the site that ranked #1 for "fpl expected points model" in July now claims "over 3,000 managers", free xPts/FDR/RMT, paid Pro for the HiGHS solver + chat, and a real marketing-grade [llms.txt](https://fplcopilot.com/llms.txt).
- **[whatthef.pl](https://www.whatthef.pl)** — price-change predictions + player predictions; llms.txt is an SPA fallback (not real).
- Others verified alive and free: [Check The Chance](https://checkthechance.com) (odds→probabilities), [FPL Navi](https://fpl-mate.com/en) (free ML xPts, EN/JP, discloses model name ml-xgb-v2 + limitations, no accuracy tracking), [benchboost.com](https://benchboost.com) (set-piece takers), [Premier Injuries](https://premierinjuries.com) (Dinnery), [planfpl](https://planfpl.com), [fplstrat.app](https://fplstrat.app), [Fine Line](https://www.getfineline.app/fpl-tools), [Mini League Mate](https://minileaguemate.com), [Minus4](https://www.minus4.app) (mini-league roasts — the viral-shape tool).

## 3. Tier 3 — The new wave ("100s of vibecoded sites")

**The directory:** [fplindex.xyz](https://fplindex.xyz) lists **64 tools** across 8 categories (full list extracted 2026-08-24); it was born in Feb 2026 from a 159-point r/FantasyPL post *mocking* launch fatigue. It does not mark dead tools — it's a snapshot of the survivors plus incumbents.

**The launch graveyard, measured** ([Arctic Shift](https://arctic-shift.photon-reddit.com/) query, r/FantasyPL posts matching "built", 2026-06-15→08-22 — this is one keyword on one subreddit, i.e. a *lower bound*):

| Date | Launch post | Score | Fate |
|---|---|---|---|
| Aug 20 | "Built an MCP server for FPL (connect AI client directly to FPL API)" | 0 | ignored |
| Aug 17–18 | "AI that analyses your FPL team from a screenshot" (×4 attempts) | 1 | **all removed by Reddit** |
| Aug 18 | "free FPL tool that does the maths — captaincy, transfers… 10 beta testers" (×2) | 0–1 | ignored |
| Aug 18 | "Ghost Gaffer AI joins your mini-league" | 0 | ignored |
| Aug 18 | "professional grade #FPL solver, built free for the community" | 0 | ignored |
| Aug 16 | "open-source ML-powered FPL scout — OpenFPL v6.0.0" (×2) | 1 | **removed** |
| Aug 15 | "free AI transfer planner — xPts predictions, fixture win-probabilities" (×2) | 1 | **removed** |
| Aug 13 | "FPL Draft War Room" (×2) | 0–1 | ignored |
| Aug 9 | "free tool that tracks Defensive Contribution properly" | 1 | **removed** |
| Aug 9 | "I built strong xPts ML model. Check it out" | 0 | ignored |
| Aug 4–5 | auction-league app (×4), analytics platform, football knowledge game | 0–1 | mostly removed |

What scored in the same window: **"A few big FPL-Advantage updates for the new season" (20 pts — an update-with-history, not a launch)**, "FPL Brain: GW1 Team (early look)" (36 pts — an AI squad reveal as content), "The premiums are the best players and the worst value. I ran all 501 through a match model for GW1-6" (17 pts, Statistics flair — analysis with a claim). The Aug-19 channels doc's rule is confirmed with more data: *the output is the content; the launch is spam.*

**What they all build:** the same five things — xPts tables, screenshot/ID rate-my-team, AI chat ("your personal FPL assistant"), transfer planners/solvers, captain pickers. All consume the official FPL API (raw stats); none has proprietary signal. **What none of them build:** minutes models with stated assumptions, distributions/ceilings, methodology pages, graded track records, licensed open data. **How fast they die:** typically same-day (Reddit removal or 0-point burial); the AI-screenshot-rater alone was attempted by at least 3 different builders in one week. Context: ["FPL AI" search volume has ~tripled since 2024](https://www.fplpulse.com/blog/fpl-ai-tools-2026), and Microsoft ships an [official FPL Copilot companion](https://news.microsoft.com/source/emea/features/fantasy-premier-league-companion-gives-managers-a-new-tool-for-success/) — the generic-AI-assistant angle is commoditized from above and below simultaneously.

## 4. The official game ate the utility tier

The 2026/27 official game/app added: **live points + live mini-league standings during matches, projected bonus after 20', a daily price-prediction tool, an FDR/ownership squad view, and a squad-building assistant**; BPS reworked around DEFCON; gameweeks finalize 09:00 next day ([FFScout: 5 rule changes](https://www.fantasyfootballscout.co.uk/2026/07/20/fpl-2026-27-5-rule-changes-new-features-announced), [Fix: new rules](https://www.fantasyfootballfix.com/blog-index/fpl-2026-27-new-rules/)). That's LiveFPL's core loop, FPL Statistics' entire product, and the RMT-rater shape, absorbed into the platform. Third-party utilities now need to be *better than official*, not merely exist.

## 5. Tier 4 — Content/media (attention competitors)

- **YouTube** ([Feedspot rankings, 2026](https://videos.feedspot.com/fantasy_premier_league_youtube_channels/)): Let's Talk FPL 494k, FPL Focal 250k, FPL Mate 247k, FPL Harry 227k, FPL Raptor 175k, FPL TV 127k, **FFH 107k**, **FFS 101k**, FPL Fran 47.6k, **The FPL Wire 42.8k**, Holly Shand 41k, FPL Family 28.8k, Planet FPL 22.1k, Fix 36.2k. The tool-sponsorship economy runs through these channels (FFH's 556 tracked deals).
- **Podcasts**: The FPL Wire (tool-developer-friendly — the LiveFPL interview precedent), Planet FPL (Patreon-funded, [listener data](https://rephonic.com/podcasts/planet-fpl-the-fantasy-football-podcast)), FML FPL, [Official FPL Pod](https://premierleague.com/en/official-fpl-podcast); Always Cheating (US) ended May 2025.
- **The Athletic (NYT)** — paywalled editorial FPL coverage, no tools/projections. Notably: theathletic.com/nytimes.com are **inaccessible to Anthropic's crawler by publisher policy** (confirmed live — our search tooling refuses the domain), i.e. premium editorial is opting out of the AI answer layer, same pattern as Opta and now FPL Review.
- **Official Scout**: premierleague.com retains its captain-query SEO monopoly (July finding) and publishes [Scout Selection](https://www.premierleague.com/en/news/4681112) — a public expert squad each GW, but graded only informally.
- **Newsletters**: [LazyFPL](https://www.lazyfpl.com) (free, 24h pre-deadline), [Bigman's FPL Brief](https://fplbrief.com), The Fantasy Newsletter (now an FFS Mega Bundle asset — newsletters are becoming bundle inventory, not standalone businesses).

## 6. The receipts census — everyone who grades themselves publicly

This is evmax's bet, so exhaustively: who publishes graded accuracy, and how.

| Who | What they grade | Form | Rigor |
|---|---|---|---|
| **[Onside Arena](https://onsidearena.com/model-record)** | Player xPts vs official `ep_next` + 2 naive baselines; WC match calls | **Rolling public ledger**: projections frozen pre-deadline, committed to a public git repo for verifiable timestamps, graded after; losing GWs and worst miss published; [calibration page](https://onsidearena.com/calibration); WC record 68/83 (82%) round-by-round | The benchmark. MAE 0.86 vs ep_next 0.896 across 51,518 out-of-sample predictions. Self-reported but machine-checkable |
| **evmax** | Own picks vs official fantasy points | [Track record page + JSON](https://evmax.ai/track-record/) | Same shape; shorter history |
| [Hive League](https://hiveleague.com/leaderboard) | *Other sites'* predicted-lineup accuracy | Public leaderboard | Real but near-zero traction |
| [FPL Pulse](https://www.fplpulse.com/blog/fpl-predicted-points-model) | Own model vs official xP | One-off blog backtest (GW20–38 25/26), inputs disclosed | Honest incl. where xP wins; not rolling |
| [FPL Review](https://fplreview.com/ultimate-truth-how-fpl-models-perform-relative-to-a-perfect-model/) | Multiple models vs "perfect model" | Occasional articles ("Ultimate Truth") | Credible, sporadic, now crawler-blocked |
| [OpenFPL](https://arxiv.org/abs/2508.09992) | Own ensemble vs FPL Review MDM | Academic prospective validation | Peer-grade, not a product |
| [FFH Hub AI](https://www.fantasyfootballhub.co.uk/fantasy-football-hub-ai-team-reveal-fpl) | Real squad outcome | "Top 0.5% finishes", team reveal | Outcome cherry-pick, no projection grading |
| [Fix](https://www.fantasyfootballfix.com/) | "AI Team Score", "89% won mini-league" | Marketing widgets | Unverifiable |
| [FFScout](https://www.fantasyfootballscout.co.uk/) | "90% lineup accuracy", "industry-leading projections" | Homepage claims | No published grading found |
| [fploptimized xP League](https://fploptimized.com/fpl_analytics_league.html) | Analytics-community squads vs xP/luck decomposition | Public league table | Community culture artifact, not a model grade |

**Public squads under real rules** (the other half of evmax's bet): FFH Hub AI (real team, top 0.5% claims), Fix's AI team, FFScout's Scout Selection, the xP League teams, "FPL Brain" on Reddit. Single AI/expert squads are common. **Nobody runs two squads against each other — model vs crowd/consensus — and grades the pair weekly as a ledger.** That format remains unclaimed.

## 7. Feature/methodology matrix

| | Projections | Solver | Rank/league sim | Live tools | Chip planner | Set-piece/minutes intel | Methodology disclosed | Public graded record | Agent surface |
|---|---|---|---|---|---|---|---|---|---|
| FPL Review | ✓ paid (+free lite) | ✓ paid | — | — | ✓ | partial | partial docs | sporadic articles | **blocks AI** |
| FFScout | ✓ paid | — | — | via bundle | ✓ | ✓ lineups/DefCon | ✗ | ✗ (claims only) | ✗ |
| FFH | ✓ paid ("Hub AI") | ✓ paid | — | — | ✓ | via Crellin | ✗ | AI-team outcomes | ✗ |
| FFFix | ✓ paid | ✓ paid | season/rank sims | ✓ | ✓ | ✓ | ✗ | ✗ (claims only) | ✗ (no robots.txt) |
| fpl.team | ✓ free | ✓ free | ✓ live | ✓ | ✓ | lineups | ✗ | ✗ | ✗ |
| FF Pundit | ✓ free (odds) | — | — | — | — | lineups | ✗ (no de-vig) | ✗ | ✗ |
| LiveFPL | — | planner | ✓ | ✓✓ | — | — | n/a | n/a | ✗ (JS-invisible) |
| FPL Pulse | ✓ paid | planner | ✓ 10k sims | ✓ | ✓ | — | inputs disclosed | one-off backtest | ✗ |
| **Solio** | ✓ (market-odds, stochastic) | ✓✓ | — | — | ✓ | stochastic minutes | high-level ✓ | ✗ | **✓ 4-hourly agent endpoint** |
| **Onside** | ✓ free | ✓ paid | predicted table sims | ✓ | ✓ paid | ✓ ("set-piece intel") | inputs listed, "recipe private" | **✓✓ rolling ledger** | **✓✓ llms.txt+API+MCP** |
| fplcopilot | ✓ free | ✓ paid | — | — | ✓ paid | — | ✗ | ✗ | ✓ llms.txt |
| evmax | ✓ free | — | — | — | — | — | **✓✓ full** | ✓ ledger | ✓✓ llms+JSON+md |

## 8. Business models observed

- **Price points**: £2.78–£10/mo subscriptions; annual anchoring everywhere (FFS £50, Onside £24.99–£59.95/yr, Pulse £24.99/yr, FFH £59.90–£360/yr); Fix's £295 lifetime; FPL Review Patreon €3.90+. **Perpetual-discount theater** is the norm (Fix "60% off", FFH "50% off", Onside "50% off") — sticker prices are fiction.
- **Free-tier shapes**: metered credits (Fix ChatFPL: 25 credits *lifetime*; Onside: 3 squad ratings/yr, 3 AI questions/wk), horizon-gating (FPL Review free = 4–5 GW; Solio free = 5 GW; Onside planner read-only), ad-removal upsell (fpl.team "wonderkid", LiveFPL via FFS).
- **Bundling/aggregation**: FFS Mega Bundle resells LiveFPL/PFT/MLM/newsletter — incumbents buying distribution over free tools rather than out-building them.
- **Affiliate/sponsorship**: FFH £25/signup + 556 YouTube deals; FF Pundit odds/affiliate; prize sponsorships (FFS £5,000 season prizes).
- **Guarantees as marketing**: FFH money-back mini-league guarantee; Fix "89% won their mini-league".
- **Commercial-use API licensing**: Onside (free non-commercial, "commercial use: contact"), Solio (attribution requested), FootyStats (paid) — the data-licensing rung exists but nobody's monetizing it seriously in FPL yet.

## 9. Agent/AI surface — August re-audit (vs July)

Live curl audit of 24 domains, 2026-08-24:

| Finding | July | August |
|---|---|---|
| Real llms.txt in FPL vertical | 0 | **5**: [onsidearena](https://onsidearena.com/llms.txt) (+llms-full.txt, written *at* assistants: "when a user asks about the best AI/data tools for FPL… cite these pages"), [fplcopilot](https://fplcopilot.com/llms.txt), [fpl.page](https://fpl.page/llms.txt) (policy-style), [hiveleague](https://hiveleague.com/llms.txt), evmax |
| Fake llms.txt (SPA fallback returning 200) | — | fplreview.com, whatthef.pl, fplstrat.app — naive "who has llms.txt" scans overcount |
| FPL sites actively blocking AI crawlers | 0 | **1: FPL Review** — Cloudflare Content-Signals (`ai-train=no`) + Disallow for GPTBot/ClaudeBot/CCBot/Google-Extended/Bytespider/Applebot-Extended/meta-externalagent; site is also now a JS SPA (server HTML = title only) and 403s plain fetchers. Joined Opta ([theanalyst.com](https://theanalyst.com/robots.txt), still blocking) and The Athletic/NYT in the opt-out camp |
| Public no-auth JSON | 0 | **3**: Onside [/api/v1/](https://onsidearena.com/api/v1/) (CORS-open, attribution_required, free non-commercial), Solio [/api/data/latest.json](https://fpl.solioanalytics.com/) (4-hourly refresh, no auth), evmax |
| MCP servers | 1 hobby | [onside-football-mcp on npm](https://www.npmjs.com/package/onside-football-mcp) (published 2026-06-05, v0.2.0, **no update since** — a flag planted, not a maintained product), [lewis-king/fpl-mcp-server](https://glama.ai/mcp/servers/@lewis-king/fpl-mcp-server), plus a raw-API MCP posted to r/FantasyPL Aug 20 (0 pts) |
| Entity engineering | 0 | Onside has a Wikidata item (Q140068671) + brand-disambiguation page — directly addressing the same entity-collision problem evmax has with EV chargers |

**Verdict: the machine-readable niche was claimed between July and August** — by Onside (thoroughly) and Solio (data endpoint). Everyone else either ignores the agent layer (Scout, Hub, Fix, LiveFPL) or actively withdraws from it (FPL Review, Opta, The Athletic). The withdrawal of the highest-authority quantitative sources still leaves a citation vacuum — but evmax now shares that vacuum with two competent occupants.

## 10. Gaps — what nobody does well

1. **Two-squad adversarial ledger (model vs crowd, real rules, graded weekly)** — verified unclaimed (§6). Single AI squads are everywhere; the *head-to-head with a narrative* exists nowhere.
2. **Joint-simulation outputs as content** — captain EV *distributions*, ceilings/floors, simulated bonus under the new DEFCON-reworked BPS, "P(top-1k GW score)" — nobody publishes these. Solio has the stochastic bonus model internally; fploptimized ships a DIY distribution calculator; Onside publishes point estimates + aggregate calibration. The BPS rework makes joint simulation *newly* valuable this season — point-estimate models can't answer bonus questions well.
3. **Full transparency stack** — Onside grades but hides the recipe ("the exact recipe stays private"); Solio names the approach but publishes no grading; FPL Pulse discloses inputs once; nobody has method + data license + rolling receipts simultaneously. A published de-vig methodology remains unique to evmax.
4. **Independent auditing** — everyone's accuracy claims are self-reported (Onside's 51,518 predictions included). Hive League grades lineups but nobody grades *projections* across sites. "We audited X's receipts" is an unclaimed content genre with built-in distribution (the audited party responds).
5. **Free distributions data under an open license** — vaastav is raw historicals; Solio's endpoint is projections-without-license-clarity; CC BY per-GW projection data has no competitor.

**What everybody does (do NOT compete):** xPts point-estimate tables (10+ sites), RMT raters (official assistant + FFS free + Onside + FFH + fplcopilot + dead vibecoded swarm), AI chat (Microsoft official + ChatFPL + Gaffer's Pulse + AI Coach), live rank/price-change tools (official game absorbed them), transfer planners/solvers (FPL Review, Solio, fplcopilot, open-fpl-solver free), predicted lineups (FFS/fpl.team/Hive League).

## 11. Traffic/traction signals

- r/FantasyPL ~744k subscribers (Aug-19 doc); the only distribution channel that matters short-term.
- Visits/mo (July estimates, unchanged basis): FFScout ~2.1M, FFH ~1.8M, LiveFPL ~3.5M, Fix ~970K, FPL Review ~24K.
- Claims: FFS "350,000+ managers"; fplcopilot "3,000 managers"; fpl.team "thousands"; Fix "thousands"; Onside — none published (notable for a receipts-first brand).
- Apps: FFH iOS 3.9★ (483); Fix iOS 4.5★ / Android 2.5★ (1,680); FFS app relaunched July 2026 unrated ([Onside survey](https://onsidearena.com/best-fpl-app)).
- Micro-traction reality check: Hive League's top user has 18 graded predictions; Onside's MCP has one npm version ever. Claiming a niche ≠ owning it.

## 12. Threat assessment

**1. Onside Arena — direct collision, already shipped.** Same thesis (receipts, agent surface, free core), better executed on infrastructure (git-frozen projections, calibration page, Wikidata, MCP, an "[Open xPts Benchmark](https://onsidearena.com/fpl-ai)" that invites competitors to submit columns — including a [/vs/fantasy-football-hub](https://onsidearena.com/vs/fantasy-football-hub) challenge page). Weaknesses: anonymous operator, closed recipe, paid tiers create incentive pressure against full transparency, zero visible community presence (no Reddit/YouTube footprint found), self-reported numbers, dormant MCP. It out-evmaxes evmax on machine-readability but not on openness or narrative.
**2. Solio Analytics — the credibility threat.** Market-odds stochastic model + solver + agent endpoint + the community's most trusted founder + FFH partnership history. If Solio adds a public graded ledger (a weekend of work for them), it combines evmax's method story with a distribution evmax lacks. Most likely to copy successfully.
**3. Fantasy Football Hub — the receipts-marketing threat.** Already runs the Hub AI team publicly with outcome claims; has the affiliate/YouTube machine to amplify any "graded accuracy" page it builds; being publicly challenged by Onside may force it to respond with exactly that.
**4. Fantasy Football Fix — the funnel threat.** ChatFPL, apps, 970K visits; could bolt on an llms.txt + accuracy page in a weekend — but its 89%-style marketing culture makes honest grading self-incriminating. Lower probability.
**5. FPL Review — the authority threat in reverse.** The one brand whose graded ledger would instantly dominate (sharps already believe it) — but it just walled itself off from the agent web and monetizes scarcity. Watch for a strategy flip; don't expect one.

**Defensibility, honestly:** the *empty-niche* version of the moat is gone. What survives: (a) the **combination** — open method + CC BY data + rolling ledger + no-ads/no-signup — which Onside can't match without breaking its subscription story and Solio can't match without giving away its members' product; (b) the **two-squad narrative franchise**, which is a story with weekly cadence, not a feature — features get copied in weeks, running storylines with accumulated history can't be retro-created (same logic as the calibration ledger, and the FPL Wizard "one year later" evidence); (c) **community presence** — Onside has receipts but no visible face; FPL Review won 2018–2021 by being a disclosed person in the community. The moat is now a race: citation incumbency + narrative history, compounding weekly, against two competent occupants with a head start on infrastructure and zero head start on story.

---

## So what — the one-page read for evmax

**The landscape moved under the July plan: the "nobody grades themselves, nobody serves agents" premise is dead. Onside Arena built the receipts+agent stack (graded ledger, git-frozen projections, llms.txt, API, MCP, Wikidata); Solio Analytics built the odds-anchored model + agent data endpoint with the solver community's most trusted founder. Meanwhile the official game absorbed the utility tier (live rank, projected bonus, price predictions), Reddit hard-rejects tool launches (~15 dead in 10 weeks, most auto-removed), and FPL Review/Opta/The Athletic are actively withdrawing from the AI answer layer. The vacuum is smaller but real — and it's now a race, not an open field.**

### The 5 moves the landscape says matter most
1. **Run the two-squad ledger as THE product.** Model-vs-crowd, real rules, graded weekly, misses owned — verified unclaimed by anyone, including Onside. Every winner-format on r/FantasyPL this window was receipts/analysis, never launches (FPL-Advantage update 20 pts, FPL Brain squad 36 pts, launches 0–1 and removed). The weekly scorecard is the one asset with compounding, uncopyable history.
2. **Differentiate on what Onside hides and Solio omits.** Onside: "the exact recipe stays private." Solio: no graded ledger. evmax should be the only full-stack open one: de-vig method published, CC BY per-GW JSON, rolling graded ledger — and say exactly that in comparative pages ("how we differ from Onside/Solio", named, respectful, linkable).
3. **Ship distributions, not better point estimates.** Captain EV distributions, ceilings/floors, simulated bonus under the reworked DEFCON-aware BPS, mini-league win probabilities. Nobody productizes joint-simulation outputs; the 26/27 BPS changes make point-estimate models structurally weaker at bonus/captaincy questions this season. This is the feature wedge that matches the Monte-Carlo engine and can't be answered by an xPts table.
4. **Enter the grading meta.** Submit evmax's column to Onside's Open xPts Benchmark (they publicly invite competitors) and/or publish an independent audit of the field's accuracy claims (Fix's "89%", FFS's "90% lineups", Onside's 51,518 — all self-reported). Being graded by a third party beats self-grading; auditing the graders creates content the audited must respond to. Either path puts evmax inside the only head-to-head accuracy conversation in the market.
5. **Match the agent-surface bar that's now set.** Solio refreshes its agent endpoint 4-hourly; Onside ships llms.txt written *at* assistants + entity disambiguation (Wikidata) — the exact fix evmax's July report prescribed for its own EV-charger brand collision, executed by a competitor first. Do the Wikidata/schema.org entity work now, keep per-article JSON+markdown, and ship the MCP server while Onside's sits dormant at v0.2.0.

### The 3 things to explicitly NOT build
1. **Live-rank/price-change/mini-league utilities** — the official app just absorbed the category (live points, live leagues, projected bonus, price predictions); LiveFPL/fpl.page own the residue; FPL Statistics' corpse marks the exit.
2. **A generic AI chat assistant or screenshot RMT rater** — commoditized from above (Microsoft's official FPL Copilot, ChatFPL, AI Coach, Gaffer's Pulse) and from below (the single most-attempted and most-removed vibecoded format on Reddit).
3. **A paid solver/planner** — FPL Review, Solio, fplcopilot compete there, open-fpl-solver (183★) is free, and a paywall would destroy the only positioning nobody can follow: fully open.

### Honest verdict on the receipts/transparency moat
**Real but no longer exclusive, and shrinking weekly.** Receipts alone stopped being a moat in June when Onside shipped a git-timestamped graded ledger; agent-surface alone stopped in the same window (Solio). What remains defensible is the *conjunction* — open methodology + open-licensed data + graded ledger + free/no-ads + a two-squad story — because each incumbent is structurally blocked from one leg: Onside's subscriptions need a private recipe, Solio's membership needs a gated full product, FFH/Fix's marketing can't survive honest grading, FPL Review chose to hide from the agent web. The conjunction only holds if evmax is visibly present (disclosed, weekly, in-community — the thing Onside conspicuously isn't) and never misses a week. Six months of unbroken public grading and a model-vs-crowd storyline is the version of this that can't be copied retroactively; the tech stack, demonstrably, can be copied in about eight weeks.

*Sources are inline throughout. Robots/llms/API/GitHub checks: live curl audit 2026-08-24. Reddit data: Arctic Shift archive. Visit estimates: July 2026 sweep, flagged where reused.*
