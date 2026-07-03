# evmax Competitive Landscape — Synthesis Report
*Research sweep synthesized 2026-07-03. World Cup R16 imminent; FPL pivot August.*

## 1. Landscape Map

The competitive field splits into **four strategic groups**, and no player in any group combines evmax's stack (de-vigged odds → 50k Monte Carlo → fantasy xPts/captain EV/ceilings + transparent methodology + free JSON API + llms.txt).

**A. Fantasy content incumbents** — audience and SEO authority, opaque or nonexistent models.
[Fantasy Football Scout](https://www.fantasyfootballscout.co.uk/) (~2.1M visits/mo), [Fantasy Football Hub](https://www.fantasyfootballhub.co.uk/) (~1.8M), [Fantasy Football Fix](https://www.fantasyfootballfix.com/) (~970K), AllAboutFPL and RotoWire (dominant in retrieval), [Fantasy Football Pundit](https://www.fantasyfootballpundit.com/) (odds-based, no de-vigging). Monetize £4–10/mo subs + ads/affiliate. All paywalled numbers, zero API, zero agent surface.

**B. Quant/tool niche** — real or claimed models, tiny reach or no product.
[FPL Review](https://fplreview.com/) (the benchmark model, ~24K visits, Patreon-gated), [FPL Optimized](https://fploptimized.com/) (open MILP solver, no projections of its own), [AIrsenal](https://github.com/alan-turing-institute/AIrsenal) (open-source, not a product), [OpenFPL](https://arxiv.org/html/2508.09992v1) (academic validation that open models match paywalled ones), [FPL Form](https://fplform.com/), fplcopilot.com, [fpl.team](https://fpl.team/), and the closest direct competitor: [FantaLens](https://fantalens.com/) (WC xPts, Poisson+odds, €9.99 pass, ~880 users).

**C. Prediction-model & simulator brands** — credible sims, **no fantasy layer**.
[Opta Analyst](https://theanalyst.com/) (25k sims, dominant media/LLM citation share), [Nate Silver's PELE](https://www.natesilver.net/p/world-cup-2026-odds-predictions) (100k sims, $10/mo Substack), [Football Meets Data](https://football-md.com/) (Elo+market blend sims, 126K X followers), [WC2026Sim](https://wc2026sim.com/) + ~10 thin simulator clones, We Global Football.

**D. Betting-stats/odds ecosystem** — traffic monsters or honest math, never both, never fantasy.
Free-opaque: [Forebet](https://www.forebet.com/) (10–18M visits/mo), WinDrawWin, [SofaScore](https://www.sofascore.com/) (105M), [FootyStats](https://footystats.org) (paid API). Media: [Action Network](https://www.actionnetwork.com), Covers, Pickswise, [Dimers](https://www.dimers.com) (closest structural analogue: sims → free content → $29.99/mo Pro, plus the only llms.txt in the audit). Pro EV tools: OddsJam, Unabated ($99–999/mo — proof that de-vigged fair value sells, delivered as paywalled bet-lists).

Utility wildcard: [LiveFPL](https://www.livefpl.net/) (~3.5M visits/mo, free, one-man, no model) — and the FPL Statistics death proves free single-utility incumbents can lose their entire audience in one season.

## 2. Comparison Matrix

| Competitor | Model transparency | Pricing | Event coverage | Agent surface (API / llms.txt / bots) | Key weakness |
|---|---|---|---|---|---|
| **FF Scout** | None — licensed Opta/StatsBomb display, no model | Free + £10/mo / £50/yr | FPL + WC vertical, daily | None; permissive robots, paywalled numbers | Opinion-driven; nothing to publish as methodology |
| **FF Hub** | Opaque "Hub AI"; odds inputs undisclosed | Annual tiers ~£30–70/yr, hidden pricing | FPL-first; WC bolt-on (stale R32 guide ranking for R16) | None | Annual billing misfits a 5-week event; marketing-label AI |
| **FF Fix** | Black-box ML + ChatFPL | £3.95–7.95/mo; £295 lifetime | FPL only | None; no robots.txt at all | Point estimates only; 3.19★ app; unverifiable claims |
| **FPL Review** | Partial docs, closed model — attacked by OpenFPL paper | Patreon ~$4.50+/mo | FPL only | None; Patreon-gated, dark to agents | ~24K visits; means not distributions; no content/SEO |
| **LiveFPL** | N/A (descriptive tool) | Free + ads | FPL live only | None; robots/llms 404, JS-rendered = invisible to LLMs | No projections; keyperson risk; zero agent surface |
| **FF Pundit** | Low — raw odds→%, no de-vig, no sims | Free (affiliate) | FPL + UCL + **WC now** | None | evmax's pipeline is a strict superset of its top-ranking format |
| **FantaLens** | Medium — Poisson+odds, undocumented | €9.99 one-time WC pass | WC fantasy only | No API, no content layer | ~880 users, no distribution, dies after the final |
| **Opta Analyst** | "Supercomputer says" — authority, not math | Free (B2B marketing) | Every WC match daily | **Blocks** GPTBot/ClaudeBot/CCBot etc.; no llms.txt/API | No fantasy layer; opted OUT of LLM ingestion |
| **Football Meets Data** | Medium-high — publishes Elo+market blend rationale | Free | WC + 54 leagues sims | No API/llms.txt | No fantasy/xPts; product is really the X account |
| **Silver Bulletin (PELE)** | High — methodology posts, closed data | $10/mo / $95/yr | WC, per-match updates | Paywalled; no API/data downloads | No fantasy, no tools; one-man brand |
| **Dimers** | Claims 10k sims; no method doc/calibration | Free + Pro $29.99/mo | US sports; soccer shallow | **Only llms.txt in audit**; open robots; no API | Black-box; no fantasy layer; US-centric |
| **Forebet** | Admits Poisson; no weights/backtests; audited ~62% vs claimed 75% | Free + heavy ads | All soccer incl. WC | Permissive robots; no API (third parties scrape it) | Accuracy claims contradicted; brutal UX; most attackable incumbent |

## 3. The Agent-Traffic Gap

The robots/llms audit (11 domains, 2026-07-03) found the agent surface **essentially unclaimed**:

- **Only 1/11 has an llms.txt**: [dimers.com/llms.txt](https://www.dimers.com/llms.txt) — a US-betting affiliate site, not fantasy. It validates the strategy and shows the endgame, but doesn't compete in evmax's category.
- **Only 1/11 actively blocks AI crawlers**: [theanalyst.com/robots.txt](https://theanalyst.com/robots.txt) disallows GPTBot, ClaudeBot, Claude-Web, anthropic-ai, CCBot, Google-Extended. The highest-authority stats brand — today's default "supercomputer" citation — has **opted out of LLM ingestion**, creating a citation vacuum during the exact WC window.
- **Only 1/11 has a public documented API**: [footystats.org/api](https://footystats.org/api/documentations/) — paid, data-only, and it firewalls /api/* from crawlers (while welcoming ClaudeBot at Crawl-delay 1 for HTML). Proof of paid-JSON demand; no free tier.
- **The entire FPL vertical (fplreview, Scout, Hub, Fix, LiveFPL) has zero agent surface**: generic/absent robots.txt, llms.txt 404s, numbers behind paywalls or JS. Fix has no robots.txt at all; LiveFPL's redirect target 404s on both files.
- Corroborating demand signals: Apify sells third-party Forebet scrapers (people want machine-readable prediction feeds Forebet won't serve); Action Network hardens its unofficial API with DataDome/Cloudflare.

**evmax's head start**: its combination — llms.txt + free per-article JSON + AI-crawler allow-list + published methodology — has **no direct competitor in fantasy football at all**, and only Dimers anywhere adjacent. When agents answer "who wins X vs Y" or "best WC captain," there is almost no citable quantitative source: Opta blocks them, Silver and FPL Review paywall the numbers, LiveFPL renders nothing. This is a structural, not incremental, advantage — but it only pays if evmax gets indexed (see §4).

## 4. Retrieval Reality

Across 15 live queries (July 2026), **evmax appeared in zero result sets** — including a brand search, where "evmax" resolves entirely to EV-charger entities (evmax.maxlite.com, evmax.us, parked evmax.com). Two urgent fixes: verify Google/Bing indexing and submit sitemaps **now**, and disambiguate the entity (use "evmax fantasy simulations"-style phrasing in titles/llms.txt/structured data).

**Winnable now (low-authority or non-commercial incumbents):**
- *"world cup fantasy expected points simulation"* — evmax's exact product query; top slots held by two small young sites: [thefantasytool.com](https://thefantasytool.com/fifa-world-cup-fantasy) and [fantalens.com](https://fantalens.com/). Clearest near-term target.
- *"world cup 2026 simulation odds"* — substacks (natesilver.net, neilpaine) and throwaway hobby domains (wc2026sim.com) hold top-6 slots.
- *"monte carlo simulation fantasy football captain"* — top 8 are GitHub repos, SSRN, personal blogs; **zero commercial products**. This is the query shape LLM agents emit for simulation-based advice.
- *"fpl expected points model"* — fplcopilot.com ranks #1 with an explainer + table; a third of the top 10 is arXiv/Medium filler. Proof low-authority sites win here. August battleground.
- *"football match predictions statistical model"* — academic PDFs and literal parasite-SEO spam (cherwellcricketleague.com) in the top 5. A transparent methodology page wins this and is prime LLM-citation material.
- *"fpl points projection tool free"*, *"expected goals predictions this week"* — fragmented indie fields, no dominant player.

**Owned by incumbents (don't attack head-on):**
- *"best fpl captain this gameweek"* — premierleague.com holds **9/9 slots**. Target modifier variants ("captain EV", "data-driven captain pick") instead.
- Round-of-16 predictions / best-bets — Yahoo/Fox/ESPN/sportsbooks lockout.
- WC captain/differentials/best-team — RotoWire + AllAboutFPL duopoly (AllAboutFPL wins on **cadence**: 5/9 slots via weekly templated posts; Hub ranks a stale R32 guide for an R16 query — a freshness gap evmax can exploit this week).

**Aggregate leaderboard**: allaboutfpl.com (6 queries), rotowire.com (5), Scout (5), Hub (4), premierleague.com (captain monopoly), big media (all betting queries). The simulation/model/methodology cluster is the beachhead — it matches the product exactly and has the weakest defenders.

## 5. Biggest Potential — Ranked Wedges

**#1. Own the "simulation → fantasy EV" query-and-citation cluster, this round.**
*Audience*: the R16→final window is peak global search; the cluster (Q4/Q6/Q9/Q11/Q13/Q14) is exactly what agents emit for data-driven picks. *Weakness*: incumbents are hobby domains, substacks, GitHub repos and an 880-user FantaLens; the only citation authority (Opta) blocks AI crawlers; nobody publishes captain EV, ceilings, or distributions — everyone ships point estimates. *Capability*: this is literally evmax's engine output plus its existing llms.txt/JSON surface. *Actions*: fix indexing + brand entity immediately; ship per-match R16 pages daily (matching Opta/FFS tempo) with de-vigged win probs + fantasy xPts + captain EV; publish a methodology page (de-vig method, sim count, calibration) — no content site anywhere publishes calibration, and whatthef.pl's existence proves users want accuracy receipts. *Evidence*: thefantasytool/fantalens rank #1–2 on the exact product query; theanalyst.com robots.txt blocks; OpenFPL paper's anti-paywall critique.

**#2. Pre-build the August FPL beachhead: templated xPts/captain-EV pages + free JSON.**
*Audience*: FPL is the year-round 2–3.5M-visits/mo market. *Weakness*: FPL Review (the only serious model) is paywalled, ~24K visits, and academically criticized for irreproducibility; Scout/Hub/Fix are opaque £30–70/yr black boxes; LiveFPL and fplreview have **zero** agent surface; AllAboutFPL's moat is cadence, not quality; fplcopilot proves a young site can rank #1 for "fpl expected points model." *Capability*: same engine, repointed; templated per-gameweek URLs on a fixed schedule replicate AllAboutFPL's cadence with strictly better math. *Actions*: build GW-templated pages (xPts table, captain EV, EV-per-price — the format fantasyfootballpundit ranks #1 with, upgraded), free tier genuinely useful (LiveFPL sets that norm), premium anchored £4–8/mo. *Evidence*: Q6/Q12/Q14 retrieval findings; FPL Statistics' death shows incumbent audiences are capturable.

**#3. Clone the Football Meets Data social flywheel — with fantasy-EV graphics nobody posts.**
*Audience*: FMD went 0→126K X followers in ~2.5 years on daily probability graphics; graphics get screenshot-syndicated into group chats and media. *Weakness*: no sim-graphics account posts captain-EV tables, xPts-per-price scatters, or ceiling distributions — the format is explicitly unclaimed; most accounts have no product behind the link, so their conversion ladders are weak; the data-sim lane on TikTok is nearly empty. *Capability*: evmax's engine already produces the numbers; each graphic links back to the article + JSON, feeding both the email ladder and the citation surface (unlike competitors' un-linkable images). *Evidence*: FMD 126K X / 91K IG; tourn-audit finding "(c) proven growth channel"; social-ecosystem entry: "nobody in the sim-graphics niche posts FANTASY-EV graphics."

## 6. Threats & Defenses

**Fastest copiers:**
- **Dimers/Cipher Sports** — the only competitor already thinking about LLM optimization (live llms.txt); if it extends sims + agent surface to soccer/fantasy, it replicates evmax's positioning with more traffic (~1M visits/mo) and funding. *Watch closely.*
- **Fantasy Football Fix** — ChatFPL shows LLM-product instinct plus apps, funnel and 970K visits; adding an llms.txt and a JSON feed is a weekend's work for them. Hub/fpl.team "AI" features signal the same drift.
- **FantaLens / TheFantasyTool** — already rank #1–2 on evmax's core query with the right product shape; either could add an API or content layer.
- **FootyStats** — already ClaudeBot-friendly (Crawl-delay 1) with a working paid JSON API; adding llms.txt + a fantasy layer is cheap for them.
- **Opta** — could simply unblock AI crawlers and reclaim the citation default on domain authority alone.

**What defends evmax:**
1. **Transparency is culturally hard to copy** — Fix/Hub/Dimers monetize opacity; publishing methodology and calibration would expose their marketing claims (Forebet's audited 62% vs claimed 75% shows the downside they face). evmax has no legacy claims to protect.
2. **Calibration track record compounds** — publish per-round accuracy receipts now; a verified ledger (the whatthef.pl demand signal) cannot be retro-created by a late copier.
3. **Citation incumbency** — LLM answer-surfaces have their own inertia; being the machine-readable source *during* the WC window and *before* the August FPL start builds reference-status before anyone reacts.
4. **The full-stack combination** — sims + fantasy translation + articles + free JSON + llms.txt; each piece is copyable, the assembled ladder (email→premium→affiliate→API, with FootyStats proving the API rung and OddsJam/Unabated proving $99–199/mo EV-math willingness-to-pay) is not copyable quickly.

**Single biggest risk is self-inflicted**: evmax is currently invisible — zero retrieval presence and a colliding brand entity. Every wedge above is gated on fixing indexing and entity disambiguation this week, while the R16 traffic peak is live.

*~1,950 words.*