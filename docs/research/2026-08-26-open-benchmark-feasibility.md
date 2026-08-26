# The open benchmark — feasibility (verified 2026-08-26)

Owner's idea: "can't we fetch other websites' preds and evaluate them?" Answer: the
GAP is real, but scraping is mostly closed. The viable shape is an INVITATIONAL
benchmark, not a scraped one.

## The gap is confirmed empty
- **Nobody runs a public, recurring, named cross-model FPL benchmark today.**
- FPL Watchmen (Substack) did it GW1 2024/25 → GW30, naming ~9 providers. **Dead since
  2025-04-04.** In-post tables only, no data.
- `x0me/fplbench` (HF dataset + PascalAI2024/fplbench, created 2026-08-16) has real
  frozen-forecast infrastructure (git-committed pre-deadline, freeze guard, CI grading)
  but **grades only itself vs ep_next**, and RESULTS.md has zero scored gameweeks.
- FPL Review "Ultimate Truth" (2023-02-01): one-off, five of six models anonymised,
  data "not mine to share", published by the winner.
- Onside's "Open xPts Benchmark": four columns, **all four Onside's or FPL's**; no third
  party has ever joined. Submission channel is real: hello@onsidearena.com, subject
  "Open xPts Benchmark submission", element-id CSV before the deadline, hash published
  on receipt, graded on the 60+ minute population, published win or lose.

## Legal reality per source (operative terms quoted in the agent reports)
| Source | Data shape | Verdict |
|---|---|---|
| **Fantasy Football IQ** | 613 players, `proj_gw2..7`, CSV+JSON, no auth | **INCLUDE NOW** — explicitly free to use "in your articles, videos, tools and research" with a link back. Needs a name-join (no element id) and a pre-deadline snapshot by us |
| **FPL `ep_next`** | all 612, official API | **INCLUDE** as the reference. Mutable + unarchived, so we snapshot it. Caveat worth publishing: 27 distinct values, max 4.0, 97 zeros — a coarse yardstick |
| **Naive baselines** | ours to compute | **INCLUDE** (season pts/start, form-last-4) |
| **OpenFPL** | MIT, trained models released | **INCLUDE-WITH-CARE** — the *feature pipeline* is NOT released (~220 engineered cols) and it needs Understat, whose robots.txt is `Disallow: /`. Build cost is real |
| **FPL Copilot** | best shape: element-keyed, all GWs, daily, unauthenticated | **BY PERMISSION ONLY** — ToS forbids scraping AND redistribution; a documented Partner API key exists. Ask |
| **Onside** | 612 HTML player pages; `/data` is World Cup only | **BY INVITATION** — ToS forbids bulk harvest; their own benchmark invites columns. Ask |
| **Solio** | no-auth JSON, but only ~60 players (top-N lists), no element id | **BY PERMISSION**; top-N truncation means agreement metrics only, never MAE |
| **FPL Review** | paywalled, encrypted payload | **EXCLUDE** from any feed. Only the Groos precedent (subscribe, export manually, publish derived metrics only) is lawful |
| **FPL Form** | genuine CSV export | **EXCLUDE** — "You may not share the files or publish the data" |
| **fplestimator** | 571 players, frozen snapshots, no ToS at all | **ASK** — SPA scrape + id mapping otherwise |
| **fplpulse / fpl.page / Transfer Algorithm** | paywalled or account-gated | **EXCLUDE** |
| **vaastav** | MIT | **GROUND TRUTH ONLY** — and weaker than assumed: 3 dumps/season now, no `gws/` for 2026-27 yet, and its `xP` is FPL's own `ep_this` with documented lookahead |
| **football-data.co.uk** | match-level xG + odds, `Disallow:` empty | **INCLUDE** as input |
| **Understat / FBref** | — | **EXCLUDE** — Understat `Disallow: /`; FBref robots unreadable behind Cloudflare |

## Decision: the invitational benchmark
1. **v1 ships from clean sources only**: evmax · Fantasy Football IQ · FPL `ep_next` ·
   two naive baselines. Metric: MAE and RMSE on the 60+ minute population AND on all
   players (so the population effect is visible, not hidden). n published weekly.
2. **Everyone else is invited in writing**, quoting their own public invitations back.
   **Publish the invitation and the answer either way — a decline is the story.**
3. **Infrastructure is the moat**: snapshot every column + ep_next into a public git repo
   BEFORE each deadline; grade after lockdown. The commit timestamp is the proof. This is
   the piece fplbench got right and everyone else lacks.
4. Never republish anyone's projections — derived metrics only, exactly as with odds.

## Open items for the owner
- Send the Onside email (submission + reciprocal invitation + the ep_next display flag).
- Decide whether to buy an FPL Review subscription for the Groos-precedent column.
- Reddit and X could not be searched by any agent (blocked) — the only coverage gap.
