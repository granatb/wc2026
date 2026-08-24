# evmax.ai — Launch Channels & 72-Hour Plan (GW1 2026/27)

*Researched 2026-08-19/20. GW1 deadline: **Friday 2026-08-21, 18:30 UK** ([SI confirms](https://www.si.com/soccer/2026-27-fpl-gameweek-1-best-players-deadlines-captain)). Constraints honored throughout: owner posts everything manually, always disclosing affiliation — no covert seeding, ever.*

**The asset being launched:** transparent market-odds Monte-Carlo engine, 8 articles/GW, free/no-ads/no-tracking, CC BY 4.0 data + JSON API + llms.txt, interactive rate-my-team tool — and the hook: **two public squads graded against each other weekly all season: the model's squad (no Haaland) vs the expert-consensus squad (captains him)**. With Salah gone from FPL and Haaland heading toward >50% ownership and near-universal GW1 captaincy ([KnightManagers: his captain-EV lead is 0.15 pts](https://knightmanagers.com/theplaybook/fpl-captain-gw1-2026-27/), [Yahoo/FFH consensus](https://sports.yahoo.com/articles/fpl-gw1-captain-picks-captain-085200973.html)), a model that benches him is the single most contrarian legal position in the game. That is the story; the site is the footnote.

---

## 1. r/FantasyPL (~744,300 subscribers)

### Rules / constraints

Verbatim rules pulled via the [Arctic Shift archive](https://arctic-shift.photon-reddit.com/api/subreddits/rules?subreddits=FantasyPL) (snapshot retrieved Jan 2025 — **re-verify in the live sidebar before posting**):

1. **No Rate My Team posts** — "Please post them in the dedicated pinned daily Questions/Advice/RMT thread… Any RMT threads posted outside this thread will be removed."
2. **No Rumours/Unreliable Leaks/Paper Talk** — confirmed news only.
3. Fake goals/injuries → temp ban.
4. **No Personal Performance Posts.**
5. Toxic behaviour ban.
6. **Money Leagues/Transactions** — advertising money leagues strictly prohibited.
7. **Meme/Shitpost/Low Effort Posts removed** — "Please put effort into your threads."
8. Team lineups: screenshot, not Twitter link.

There is **no explicit written self-promotion rule** — but enforcement is real and visible in the data: in the last 10 days alone, at least eight "I built an FPL tool" posts sit frozen at 1 point (removed or buried), including an open-source ML scout (OpenFPL v6), three AI screenshot-analyzer posts, an AI transfer planner, and a "looking for 10 beta testers" post (Arctic Shift, Aug 9–20, 2026). Reddit-wide [self-promo guidelines (90/10)](https://www.conbersa.ai/learn/reddit-self-promotion-rules) apply as the mod fallback.

**Community fatigue is explicit**: ["I got tired of seeing a 'I built an FPL tool' post every week, so I made a directory of all of them"](https://reddit.com/r/FantasyPL/comments/1ra00k1/i_got_tired_of_seeing_a_i_built_an_fpl_tool_post/) — 159 points, Feb 2026, spawning [fplindex.xyz](https://fplindex.xyz) (64 tools listed, submit form available). A generic tool announcement in GW1 week will be either removed or mocked.

### What works (evidence)

| Post | Score | Why it worked |
|---|---|---|
| ["I simulated the season on Football Manager"](https://reddit.com/r/FantasyPL/) (Aug 2021, Analysis) | 488 | Simulation + results in the post |
| ["I simulated DGW25 1 million times — here's which Assistant Manager came out on top"](https://reddit.com/r/FantasyPL/) (Feb 2025, Analysis) | 211 | **The evmax format**: Monte-Carlo + one concrete surprising takeaway in the title |
| "I simulated the upcoming 21/22 season 10,000 times…" (Jul 2021, Analysis) | 156 | Same |
| ["FPLReview has 4.5m Nwaneri as the best captain choice for GW26"](https://reddit.com/r/FantasyPL/) (Feb 2025) | 274 | **A model's shocking output posted as news — by a user, not the creator.** The tool's output became the content |
| ["FPL Wizard: Power-App… (One Year Later)"](https://reddit.com/r/FantasyPL/) (posted GW1 Saturday, Aug 16 2025) | 632 | Tool post that won — because it was an anniversary/update with receipts, not a launch |
| [WC fixture difficulty table — "would love some feedback"](https://reddit.com/r/FantasyPL/comments/1tzlpq2/) (Jun 2026) | 178 | Feedback-ask framing, methodology explained, one link |
| ["Creator of fplreview.com here, the site's ML 'Massive Data' Model is live"](https://reddit.com/r/FantasyPL/) (Aug 2021) | 74 | Disclosed creator post — lands OK **once the tool is already known** |
| [Confirmed-transfers tracker](https://reddit.com/r/FantasyPL/comments/1tzdxkf/) (Jun 2026) | 55 | Humble tone ("sorry to be contributing to yet another 'I built an X' post"), no sign-up, solves a felt need |
| "Gameweek 1 \| Predicted Points \| Captaincy Pick" (Wed before GW1 2025, Statistics flair) | 323 | Predicted-points table posted **two days pre-deadline** |
| "Those of us who chose Haaland over Salah" (Thu before GW1 2025) | 615 | Premium-pick controversy is the sub's highest-engagement debate format |
| "Complete Pre-Season Minutes — [all 20 clubs]" (Aug 15 2026) | 294 | Exhaustive OC data dump, this preseason |
| "New FPL Template Team based on Ownership %" (Aug 14 2026, Statistics) | 99 | Template/ownership analysis, this preseason |

Flairs in productive use: **Analysis, Statistics, Discussion, Blog Post, Community**. The pattern across every winner: **value delivered inside the post (tables/images), a surprising specific claim in the title, at most one link, disclosed authorship, feedback-ask tone, no sign-up wall.** "I built" in the title is now an anti-signal.

### Timing (empirical, from GW1 week 2025 + current preseason)

- High-scoring analysis posts were submitted **Tue–Thu, ~12:00–18:00 UK**, peaking in visibility through UK evening.
- **Deadline day itself (Friday) is a losing slot for analysis** — the feed is owned by lineup leaks, injury news, and the deadline countdown; post-deadline evening and Saturday belong to memes/results/live threads.
- The single best analysis window before a Friday 18:30 deadline: **Wednesday midday → Thursday midday UK.**

### Recommended play for THIS launch

1. **One flagship OC post, Thursday 2026-08-20, ~09:00–12:00 UK**, flair **Analysis**. Title pattern (surprising claim, not tool announcement): *"We simulated GW1 50,000 times from de-vigged market odds — the model refuses to captain Haaland. We're publishing its full squad AND the expert-consensus squad, and grading both publicly every week."* Body: the two 15-man squads as images, the captain-EV distribution (Haaland vs the model's pick), 3–4 paragraphs of methodology in plain English, full disclosure ("I run evmax.ai; everything is free, no ads, no sign-up; methodology and data are CC BY"), one link at the bottom, and an explicit ask: *tell me why the model is wrong.* The wrongness-ask converts the sub's Haaland tribalism into comments, and comments carry the post.
2. **Do not post the rate-my-team tool as its own thread.** Instead, from GW2 onward, answer questions in the pinned daily RMT thread genuinely, occasionally noting (disclosed) that the tool exists. In-thread helpfulness is explicitly rewarded (the sub has a `!thanks` reputation system).
3. **Submit evmax.ai to [fplindex.xyz](https://fplindex.xyz)** via its form (2 minutes, permanent listing).
4. **Book the follow-up now:** the weekly "Model vs Experts — GW\<n\> grading" post is the FPL Wizard "(One Year Later)" trick run weekly; by GW6 it's a franchise the sub recognizes. If either squad tops the other meaningfully by Christmas, the recap post is a near-guaranteed front-pager.

**Effort:** ~3–4 h for the flagship post (graphics matter). **Impact:** highest of any channel — a 200+ score post here reaches more real FPL managers than everything else combined; even a 50-score post seeds the weekly franchise. **Risk:** removal — mitigated by value-first format, single link, disclosure, and posting history (warm the account by commenting helpfully for a day before posting if the account is fresh).

---

## 2. Other subreddits

| Sub | Rules reality | Verdict |
|---|---|---|
| **r/FantasyPremierLeague** (93,426 subs) | Smaller sibling sub, laxer enforcement | Post a variant of the flagship 1 day later (Thu evening). Low effort, small but nonzero reach |
| **r/soccer** | Rules explicitly ban fantasy football threads: *"threads about betting, video games, surveys, fantasy football… are not allowed and will be removed"* | **Dead. Skip.** |
| **r/PremierLeague** | *"No Self-Promotion… generally frowned upon"* + reddit-wide guidelines | Skip for launch; possible later as pure data OC without links |
| **r/dataisbeautiful** | [OC] must link source article; data source + tool in first comment; **plain non-sensational titles** | Viable **weekend** play (not launch-critical): "[OC] Simulated points distribution of Haaland vs. the field over 50,000 GW1 Monte-Carlo runs". Massive general audience; FPL fraction small but absolute numbers can beat FPL subs |
| **r/InternetIsBeautiful** | 90/10 self-promo rule; no sites requiring personal info (evmax passes — no sign-up); **"No AI-Generated Content"** — expect hostility to anything smelling of AI; no business tools | Marginal. Only if the account has 90% non-evmax history. Park it |
| **r/SideProject** | Self-promo is the point | 15 minutes, ~zero FPL users, but backlink + indie feedback. Fine as filler on the weekend |

**Hacker News (Show HN):** FPL tools historically die there — [Show HN: fpl.cool](https://news.ycombinator.com/item?id=29047676) (3 points, 2021), Show HN: FantasyTote (1 point, 2018). What does work is cross-domain novelty and math: [Magnus Carlsen is world FPL #1](https://news.ycombinator.com/item?id=21790060) (204 pts), Liverpool/Fibonacci (112 pts), PL gambling-sponsor ban (328 pts). **Play:** don't burn Show HN during launch week. Save it for a quiet mid-September Tuesday framed as engineering + epistemics, e.g. *"Show HN: A fully transparent Monte-Carlo FPL engine (open methodology, CC BY data) that we're publicly grading against expert consensus every week"* — the falsifiability/we-might-lose angle is the only one HN respects. Expected: modest (30–100 pts if it lands), but HN readers are exactly who consumes the JSON API and reposts to their mini-leagues. **Effort:** 1 h. **Impact:** low-medium, non-time-critical.

---

## 3. FPL Twitter/X ecosystem

### How the ecosystem works (evidence)

- Growth canon from inside the community ([FPL General: "Tips for growing your FPL Twitter account"](https://fplgeneral.com/articles/tips-for-growing-your-fpl-twitter-account/), [socialrails guide](https://socialrails.com/blog/how-to-grow-on-twitter-x-complete-guide)): **native images carry no link penalty** (clean tables/charts as images, link in a reply); weekly preview **threads**; polls; build 1:1 relationships with mid-size accounts; never tag 10+ accounts begging for RTs — tag one or two with a genuine question.
- Hashtags: **#FPL** is the discovery tag; **#FPLCommunity** is the social/reciprocity tag ([sportscasting](https://www.sportscasting.com/uk/the-best-fpl-twitter-accounts-to-follow-in-2024/), [fplfulcrum ranking](https://fplfulcrum.com/docs/community-resources/forums-and-social-media/best-fantasy-premier-league-twitter-accounts/)). Both go on launch tweets; neither substitutes for a shareable graphic.
- Formats that get screenshotted and quote-tweeted, per the [AllAboutFPL account taxonomy](https://allaboutfpl.com/2022/06/recommended-fpl-tools-accounts-channels-podcasts-websites/): planning spreadsheets ([@BenCrellin](https://twitter.com/BenCrellin), 200k+), injury tables ([@BenDinnery](https://twitter.com/BenDinnery)), fixture tickers, deep threads (@FPL_Architect, @FplStrategy), predicted-points tables (FPL Review's EV tables circulate as screenshots — see the 274-point Reddit post above).
- **Controversial takes are the engagement engine**: the Haaland-captaincy question is THE GW1 debate ([KnightManagers](https://knightmanagers.com/theplaybook/fpl-captain-gw1-2026-27/) is already arguing the margin is 0.15 pts). A model that says "don't" with receipts is quote-tweet bait in both directions — and unlike a human hot-take account, evmax can point at open methodology when attacked.

### Recommended play

1. **Launch thread, Wednesday evening (19:00–21:00 UK) or Thursday 08:00 UK**: Tweet 1 = the two-squads graphic + "Our market-odds Monte-Carlo model refuses to pick Haaland. The expert consensus captains him. We're grading both squads publicly every gameweek this season. #FPL #FPLCommunity". Thread: captain-EV distribution chart → why the model says what it says (3 tweets, one chart each) → "everything free, no ads, methodology open" → link **only in the final tweet/reply**. Pin it.
2. **Deadline-day service content, Friday 07:00–17:30 UK**: 2–3 standalone graphics (final captain EV table, biggest EV-vs-ownership gaps, "last-hour differentials by ceiling"). Deadline morning is peak passive consumption (see §4).
3. **Reply strategy (disclosed, additive):** when @FFScout / @LetsTalk_FPL / @FPLFocal / mid-size accounts run captain polls Thursday–Friday, reply with the EV-distribution chart and one sentence. One or two per day, never spammy.
4. **Tag exactly one relevant quant-friendly account per launch asset** (e.g., @BenCrellin on the fixture-EV table; the FPL Wire hosts on the model-vs-experts premise) with a question, not a plug.
5. From GW1 results onward: the **weekly scorecard graphic** ("Model 61 – 58 Experts. Season: 1–0.") every Monday. It is self-renewing, zero-marginal-cost, screenshot-native content.

**Effort:** 2–3 h for launch assets, then ~30 min/day. **Impact:** medium at launch (cold account), compounding — this is where the weekly grading franchise builds a following; X is also where podcast/YouTube people will check you out after outreach. **Risk:** low; worst case is silence.

---

## 4. Timing: the GW1 attention curve

- **Managers act late:** Fantasy Football Fix's study of top-50 managers found transfers are consistently delayed into the **final 0–48 h before deadline** ([FFF 2026/27 tips](https://www.fantasyfootballfix.com/blog-index/fpl-top-50-tips-transfers-2026-27/)); decision-relevant content is consumed Wednesday→Friday-17:30.
- **Empirical subreddit curve (GW1 week 2025, Arctic Shift):** analysis/predicted-points posts peaked when posted Tue–Thu daytime UK (323-point predicted-points post on the Wednesday); Friday pre-deadline is press-conference/lineup-news territory; Friday night and Saturday flip to memes, live threads, and results ("New season, but some things never change" — 4,036 points, posted 21:16 UK on deadline day).
- **GW1 is the peak of peaks:** every mainstream outlet runs GW1 previews ([SI](https://www.si.com/soccer/2026-27-fpl-gameweek-1-best-players-deadlines-captain), [Yahoo](https://sports.yahoo.com/articles/fpl-2026-27-best-players-141758229.html), [RotoWire](https://www.rotowire.com/soccer/article/fpl-gameweek-1-best-players-captain-picks-2026-27-rankings-gw1-127487), BBC); casuals who touch FPL once a year are present this week only. Launching 2 days out is exactly right for decision-support content.
- **Post-deadline is not dead time — it's a second audience:** Saturday–Monday is when "how did everyone do" content wins (LiveFPL's whole ~3.5M visits/mo franchise is live-rank during matches). The model-vs-experts **GW1 scorecard on Sunday night/Monday** catches this wave.

**Practical rule for the launch:** decision content (squads, captain EV, rate-my-team) Wed–Fri 17:30; verdict content (grading, scorecards) Sun–Mon. Nothing analytical between Fri 18:00 and Sat kickoff.

---

## 5. What worked for comparable tools

| Tool | How it actually got traction | Source |
|---|---|---|
| **FPL Review** (2018) | Bookmaker-odds model as a solo project; creator was a visible, disclosed community member (["Creator of fplreview.com here…"](https://reddit.com/r/FantasyPL/) 74 pts, 2021); podcast guest spots (["Corridor of Uncertainty" feat. fplreview](https://reddit.com/r/FantasyPL/), 2020); then **its outputs became community content others posted** (274-pt Nwaneri post). No marketing budget visible | [docs.fplreview.com/about](https://docs.fplreview.com/getting-started/about-fplreview/) |
| **LiveFPL** (2018) | One-man site; won by owning a live moment (rank during matches) + one novel concept (effective ownership) that content creators needed to cite weekly; amplified by [FFS "Meet the Manager" interview](https://www.fantasyfootballscout.co.uk/2022/01/08/meet-the-manager-livefpl-creator-ragabolly-speaks-ahead-of-gameweek-22/) and [The FPL Wire ep. 17](https://www.youtube.com/watch?v=SQvWHLxrtt8) | prior competitor research: ~3.5M visits/mo |
| **FPL Wizard** | Launched quietly; the posts that scored were the **update-with-receipts** posts: "(One Year Later)" 632 pts on GW1 Saturday 2025; feature update 224 pts Oct 2025 | Arctic Shift |
| **Fantasy Football Fix / Hub** | The paid route evmax rejects: [£25-per-signup affiliate program](https://www.fantasyfootballhub.co.uk/become-an-affiliate), [556 YouTube sponsorship deals tracked since Jul 2024](https://sponsorradar.com/brands/fantasy-football-hub/get-sponsored), YouTuber testimonials on the homepage. Proves the podcast/YouTube channel converts — evmax's version is being the free, open, editorially interesting guest instead of the sponsor | sponsorradar, FFF site |
| **vaastav/Fantasy-Premier-League dataset** | Open data quietly became infrastructure: [1.8k GitHub stars](https://github.com/vaastav/Fantasy-Premier-League), cited by academic papers and downstream tools ([FPL-Core-Insights](https://github.com/olbauday/FPL-Core-Insights) credits it) | GitHub |
| **fplindex.xyz** (2026) | Launched by *mocking the launch meta* (159 pts) — meta-awareness of the tool fatigue was itself the hook | Reddit |

**Transferable lessons:** (a) the tool's *output* is the marketing — make every weekly claim screenshotable; (b) creators who show up disclosed and keep shipping get adopted, launch posts don't; (c) one novel named concept (effective ownership, Massive Data Model) gives creators a reason to cite you — for evmax that's **the Model-vs-Experts ledger** and the no-Haaland position; (d) open data compounds silently.

---

## 6. Newsletters, podcasts, YouTube

**The landscape** ([Feedspot's 75 FPL podcasts](https://podcast.feedspot.com/fpl_podcasts/), [AllAboutFPL directory](https://allaboutfpl.com/2022/06/recommended-fpl-tools-accounts-channels-podcasts-websites/)):

- **Tool-friendly podcasts (primary targets):** [The FPL Wire](https://podcasts.apple.com/gm/podcast/the-fpl-wire/id1530847697) — explicitly "interviews with established FPL Managers, Content Creators and **FPL Tool Developers**" (precedent: the Ragabolly/LiveFPL episode); **FPL BlackBox** (Az & Mark, tool-literate); **Corridor of Uncertainty** (stats/modelling guests — hosted fplreview in 2020); **FML FPL**; **Planet FPL** (James & Sujan). *Always Cheating*, the big US one, [ended May 2025](https://podscan.fm/podcasts/always-cheating-a-fantasy-premier-league-podcast-fpl).
- **YouTube:** [Let's Talk FPL](https://www.youtube.com/) (Andy, ~268k subs), FPL Focal (~350k, ex-world-#1), FPL Mate, FPL Harry — these run sponsored tool segments (see FFH's 556 deals), so an *editorially free* data story must be genuinely newsworthy, not a feature list. Data-native smaller channels (**Ted Talks FPL** — "data driven, scatter plots"; **FPL Penguin**) are likelier first yeses and are fine social proof.
- **Newsletters:** [LazyFPL](https://fplunplugged.substack.com/p/the-ultimate-fpl-resources-list) (data-driven, respected), [FPLTips newsletter](https://fpltips.com/best-fpl-tools/) (~7k subs, runs "best FPL tools" lists), Substack scene ([FPL Feed](https://fplfeed.substack.com/) covers free tools/APIs, [FPL Unplugged resource list](https://fplunplugged.substack.com/p/the-ultimate-fpl-resources-list) takes suggestions), [AllAboutFPL tools category](https://allaboutfpl.com/category/fpl-tools/) reviews tools as SEO content and will review anything notable.

**The realistic cold-outreach angle** — pitch the *story*, not the site:

> "A market-odds Monte-Carlo model picked its GW1 squad. It refused Haaland. We're playing it publicly all season against the expert-consensus squad and grading both every week — everything free and the methodology fully open. Happy to walk through why the maths says what it says, and to be held to the result on air."

Precedents that this framing is press-viable: [City AM ran "No Haaland and a 4-5-1 — can ChatGPT beat humans at FPL?"](https://www.cityam.com/fantasy-peremier-league-no-haaland-can-chatgpt-beat-humans-at-fpl/) back in Aug 2023; Microsoft just shipped an [official FPL Copilot companion](https://news.microsoft.com/source/emea/features/fantasy-premier-league-companion-gives-managers-a-new-tool-for-success/) (AI×FPL is a mainstream editorial theme this season); "FPL AI" search volume has [roughly tripled since 2024](https://www.fplpulse.com/blog/fpl-ai-tools-2026). The differentiator vs the 2023 ChatGPT stunt: this is a real probabilistic model, accountable weekly, with open methodology — "the AI stunt, done honestly."

**Mechanics:** DM/email 6–10 targets Wednesday–Thursday with the two-squads graphic attached; expect zero coverage before GW1 (their deadline-week slates are full) and that's fine — the ask is a **GW3–5 segment once the ledger has data**. A 2–3 GW scoreline turns the pitch from "new tool" into "the model is actually winning/losing — come argue."

**Effort:** ~2 h for the target list + personalized notes. **Impact:** per-hit the highest of all channels (one mid-size podcast/YouTube mention has historically minted FPL tools — it's why FFH pays £25/signup for it); probability per pitch ~10–20%, so volume + patience.

---

## 7. AI-agent / citation surface

**Honest read of the evidence:**

- **llms.txt is currently theater**: ~10% site adoption but AI crawlers essentially never fetch it — one 90-day study saw [408 llms.txt hits out of 500M+ AI bot visits](https://ai.aeo.press/the-state-of-llms-txt-in-2026); Otterly measured 0.1%; no major lab (OpenAI, Google, Anthropic, Meta) has committed to it and [Google is on record as "no"](https://derivatex.agency/blog/llms-txt-guide/) (Gary Illyes, Jul 2025). Keep evmax's llms.txt (zero cost, small upside if the standard catches), expect nothing from it this season.
- **What actually gets sports sites cited by assistants**: crawlable static HTML with stable URLs and self-describing tables; being the named source in high-authority text that LLMs retrieve (Reddit threads, Wikipedia-grade pages, established FPL sites — note from the prior competitor audit that AllAboutFPL/RotoWire dominate retrieval for FPL queries); and structured data. Every Reddit post and podcast mention above is therefore *also* AEO — assistants cite what communities name.
- **The agent-builder wedge is real and hungry**: there is a constant stream of "I built an FPL AI" builders (the r/FantasyPL graveyard, a [TechRadar GPT-5 FPL-program story](https://www.techradar.com/ai-platforms-assistants/chatgpt/i-used-gpt-5-to-code-a-fantasy-premier-league-program-and-i-might-actually-stand-a-chance-of-winning-my-draft-this-year-thanks-to-chatgpt), an [FPL MCP server on Glama](https://glama.ai/mcp/servers/@lewis-king/fpl-mcp-server), another MCP server posted to r/FantasyPL on Aug 20 2026). They all scrape the official API for *raw* stats; none has free, licensed, **projection** data. CC BY 4.0 xPts/EV JSON is a unique input every one of them wants.
- **Precedent that open FPL data compounds into citations**: [vaastav's dataset](https://github.com/vaastav/Fantasy-Premier-League) (1.8k stars) became the default citation in FPL academic work and downstream tools without any marketing.

**Recommended play:** (1) publish an `evmax-data` GitHub repo mirroring the per-GW JSON (CC BY) with a clear README + data dictionary — GitHub is itself a discovery surface and the repo becomes the citable artifact; (2) ship a thin **MCP server** over the API (a weekend project, and "connect Claude/ChatGPT to honest FPL projections" is a second Show HN / r/FantasyPL Community post later in September); (3) put `Dataset` + `Article` schema.org markup on article pages; (4) add a visible "Cite this / used by agents" page so builders credit evmax by name — the name in *their* READMEs is what LLMs later repeat. **Effort:** low, spread over 2–3 weeks post-launch. **Impact:** slow-burn moat; near-zero GW1-week traffic, meaningful by mid-season.

---

## The 72-hour launch sequence (deadline: Friday 18:30 UK)

**Pre-flight (Wednesday daytime):**
- Freeze the GW1 model run; render the 3 core graphics: (A) two-squads side-by-side card, (B) captain-EV distribution Haaland vs model pick, (C) EV-vs-ownership gap table. Same visual identity everywhere — these will be screenshotted.
- Re-read r/FantasyPL live sidebar rules; make sure the posting account has non-promo comment history (spend 30–60 min genuinely answering questions in today's RMT daily thread).
- Submit evmax.ai to [fplindex.xyz](https://fplindex.xyz) and the [FPL Unplugged resource list](https://fplunplugged.substack.com/p/the-ultimate-fpl-resources-list).

**Wednesday evening (19:00–21:00 UK) — X launch:**
- Pinned launch thread (graphic A lead, B and C inside, link last, #FPL #FPLCommunity, full disclosure). Tag exactly one quant-adjacent account with a genuine question.

**Thursday morning (09:00–12:00 UK) — the flagship, highest-EV move:**
- **r/FantasyPL Analysis post**: *"We simulated GW1 50,000 times from market odds — the model refuses to captain Haaland (we're grading its squad vs the expert-consensus squad publicly all season)."* Squads + charts in-post, methodology in plain English, disclosure, one link, "tell me why it's wrong." Then live in the comments for 6+ hours answering everything (comment velocity in hour 1–3 decides the post's fate).
- Send the 6–10 podcast/YouTube/newsletter pitches (FPL Wire, FPL BlackBox, Corridor of Uncertainty, FML FPL, Planet FPL, Ted Talks FPL, FPL Penguin, LazyFPL, FPLTips, AllAboutFPL) — ask for a GW3–5 slot, not deadline-week coverage.

**Thursday evening:**
- Variant post to r/FantasyPremierLeague (93k).
- X: post graphic C standalone ("biggest EV-vs-ownership gaps before GW1").

**Friday — deadline day (all times UK):**
- 07:30–09:00: X — final captain-EV table ("last call: the maths on the armband"). Quote-tweet your own launch thread with it.
- ~11:00: if the Reddit flagship survived and is discussed, drop ONE comment linking the rate-my-team tool where someone asks "what would your model do with my team" (only if asked; disclosed).
- 12:00–17:30: reply (disclosed, chart-in-hand) to 2–3 big-account captain polls; nothing new after 17:30.
- 18:30: deadline. **Post nothing analytical.** Optional single X post at 18:35: "Both squads are locked. Ledger starts now." — screenshot of both squads timestamped. This tweet is the season's accountability anchor; everything future links back to it.

**Saturday–Sunday (GW1 matches):**
- X only: 1–2 honest in-play observations (e.g., if Haaland hauls: own it immediately — "the model takes the L on transparency too"; credibility is the product).
- Sunday night: **GW1 scorecard graphic** — "Model X – Y Experts. Season ledger: 1–0/0–1." Post to X; if the result is spicy (either direction), a short r/FantasyPL follow-up Monday morning: "GW1 verdict: the no-Haaland model scored…" referencing Thursday's post.

**Next week (not in the 72h, pre-booked):** Show HN (mid-week, engineering/falsifiability framing), r/dataisbeautiful [OC] chart, GitHub `evmax-data` repo + MCP server, follow up podcast pitches with the GW1–2 scoreline.

---

## Single highest-EV play

**The Thursday-morning r/FantasyPL Analysis post built on the no-Haaland controversy — with the season-long public grading framed as the accountability mechanism, followed by the weekly Model-vs-Experts scorecard franchise.** Every piece of evidence converges on it: 744k FPL managers in one place; Monte-Carlo-with-a-surprising-takeaway is a repeatedly proven 150–500-point format on that sub; the Haaland premium-pick debate is its single highest-engagement topic in GW1 week; the analysis window (Wed–Thu before a Friday deadline) is empirically optimal; plain tool launches are provably dead there this month; and the weekly grading gives the one thing no competitor post has — a reason to come back 37 more times. The launch post is not marketing a site; it's opening a season-long public bet, disclosed and checkable, which is the only marketing this community has ever rewarded.
