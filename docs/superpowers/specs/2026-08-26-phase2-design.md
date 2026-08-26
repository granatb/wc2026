# Phase 2 — the surfaces nobody else holds

Owner-approved 2026-08-26 ("spec and do the whole phase 2 now"; GW1-only numbers are
fine, traffic is low, experiment). Grounded in
`docs/research/2026-08-24-fpl-competitor-landscape.md` moves 1/3/4/5 and STRATEGY §12.

## The four pieces

| # | Piece | The gap it fills |
|---|---|---|
| P1 | **Distributions** — per-player point histograms from the sims, surfaced on cards + a distributions page | Verified unclaimed: everyone ships a mean, nobody ships the shape. Only a real Monte-Carlo engine can |
| P2 | **Public dataset** — bulk CC BY JSON+CSV per GW + cumulative, schema doc, `/data/` page | CC BY requires attribution → every reuse is a citation. Competitors either paywall or block crawlers |
| P3 | **MCP server** — `npx evmax-mcp`, tools over the public API | Onside's has been dormant at v0.2.0 since June; the agent front door is effectively empty |
| P4 | **Accuracy page + benchmark artifact** — our graded numbers, method, and the submission file for Onside's Open xPts Benchmark | Third-party grading beats self-grading; nobody else publishes a testable record |

## Decisions

| # | Decision |
|---|---|
| D1 | **Distributions are FREE.** Supersedes the 08-24 note listing "full distribution view" as premium. The line is: game data free (projections, distributions, verdicts, duel, accuracy, dataset, API), your-team tools paid (transfer/captain runs on YOUR squad, dossier alerts, history depth, bulk/live API tiers). Public framing unchanged: "we will never charge you to see what we predicted" |
| D2 | Histogram is a discrete PMF over integer FPL points (they ARE integers), stored per player in the cached artifact as `{points: count}` sparse dict. Cheap: ~30 keys × 610 players |
| D3 | Dataset is emitted BY THE BUILD from artifacts already in memory — no new pipeline, no scraping, no database. Files land under `/api/fpl/dataset/` and are linked from a human `/data/` page |
| D4 | MCP server is a thin Node client over the PUBLIC API (zero infrastructure, no secrets, no server). It lives in `mcp/` in this repo, outside the Python suite, with its own smoke test. Publishing to npm is an owner action, not a build step |
| D5 | GW1-only content is acceptable everywhere (owner). `ep_next` was not captured pre-GW1, so the comparison column reads "captured from GW2" — stated, not hidden |
| D6 | The "audit the graders" essay is NOT auto-generated prose: it is a hand-written page reviewed before publish (it names competitors). Phase 2 ships the accuracy PAGE and the benchmark artifact; the essay is drafted for the owner, published on his word |

## P1 — Distributions

`SimPointsAccumulator` already holds every player's per-sim total. Add `histogram(name)`
→ `{int_points: count}`. `build_rows` stores it as `distribution`; `_derive_row` derives
`p10` (floor), `median`, `mode` (most likely), `p90`, `p_haul` (P ≥ 10), `p_blank`
(P ≤ 2), keeping `ceiling` (tail mean) as-is. Surfaces:
- **Card**: the reserved `distribution` slot becomes a real inline SVG — a small bar
  chart of the PMF with floor / most-likely / ceiling marked. Replaces the "coming soon"
  premium strip; the premium slot text becomes your-team tools only.
- **`/fpl/gw{N}/distributions/`**: a ninth article slug — the week's captaincy
  candidates with their spreads, "beats the field" probabilities computed from the
  stored PMFs (P(A ≥ B) by convolving the two PMFs — independent approximation,
  labelled as such), and a haul/blank table.

## P2 — Public dataset

Per gameweek: `/api/fpl/dataset/gw{N}.json` (every simulated player: projection,
components, distribution summary, price, ownership, verdict) and `gw{N}.csv` (the same
flat). Cumulative: `/api/fpl/dataset/all.json` + `.csv` (every graded GW, appended).
`/api/fpl/dataset/index.json` lists what exists. `/data/` is the human page: what the
columns mean, the CC BY 4.0 terms, curl examples, links. `DATASET.md` in the repo
mirrors the schema. Sitemap + llms.txt carry it.

## P3 — MCP server

`mcp/` — Node, `@modelcontextprotocol/sdk`, single `index.js`, no build step. Tools:
`list_gameweeks`, `get_projections(gw, position?, limit?)`, `get_player(name)`,
`get_duel()`, `get_accuracy()`, `get_distribution(name, gw?)`. Every response cites
the source URL and the CC BY terms. README with the `claude mcp add` / `npx` lines.
Smoke test: `node mcp/test-smoke.js` hits the live API and asserts each tool's shape.

## P4 — Accuracy page + benchmark artifact

`/fpl/accuracy/`: the graded ledger in full (per-GW MAE, ep_next when present, squad
lines, duel), the method in plain language, links to every grading JSON, and an
explicit "how to check us" paragraph. The benchmark artifact: `evmax/assets/benchmark/
gw{N}-evmax.csv` in a generic `player_id,player_name,gameweek,predicted_points` shape
(the common submission format), regenerated per GW, ready for the owner to submit.

## Non-goals
Paywall plumbing, accounts, npm publish, the audit essay's publication, live API tiers,
histogram-based optimizer changes (the optimizer stays on means this phase).
