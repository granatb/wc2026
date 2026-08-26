# Phase 2B — Public dataset, MCP server, accuracy page

> REQUIRED SUB-SKILL: superpowers:executing-plans, task-by-task.
> Branch `phase2-dataset-mcp` off main. Suite 982 green at start, green at every commit.
> Python 3.9 stdlib only for the site; the MCP server is Node and lives OUTSIDE the
> Python suite. Explicit-path staging, no push/merge/deploy. WC pages byte-identical.
> Frozen artifacts untouched. Spec: `docs/superpowers/specs/2026-08-26-phase2-design.md`
> (D3, D4, D5, D6, P2/P3/P4).
> NOTE: a parallel agent works `phase2-distributions` and owns `games/fpl/model.py`,
> `evmax/fpl_players.py` and row derivation. You own the dataset emission, `/data/`,
> `/fpl/accuracy/`, `mcp/`, `docs/DATASET.md`. Emit dataset columns DEFENSIVELY: include
> distribution fields when present on a row, omit silently when absent (his branch adds
> them; yours must work before and after the merge).

### Task 1: dataset emitters
**Files:** create `evmax/dataset.py`, test `tests/test_dataset.py`
Pure: `gameweek_payload(gw, rows, generated_at) -> dict` (meta block with license,
source URL, method one-liner + `players` list: every simulated player with id, name,
team, position, price, ownership, x_points, ceiling, captain_ev, value, bonus, defcon,
p_defcon, cs_points, start_prob, verdict fields, and any distribution fields present);
`to_csv(payload) -> str` (stable column order, header row, RFC4180 quoting, UTF-8, no
index); `index_payload(gameweeks) -> dict`; `merge_all(payloads) -> dict`.
- [ ] Failing tests: JSON meta carries `license: "CC BY 4.0"` + attribution string; CSV
  header stable and row count == players; a row WITHOUT distribution fields still emits
  (columns present, empty); quoting of a name containing a comma; `merge_all` orders by
  gameweek then x_points desc.
- [ ] Run. - [ ] Implement. - [ ] Full suite. - [ ] Commit
  `feat(data): CC BY dataset emitters — per-gameweek JSON and CSV`.

### Task 2: wire into the build + `/data/` page
**Files:** `evmax/fpl_build.py` (write-out block only), `evmax/render.py` (new
`data_page`), tests `tests/test_fpl_site.py`
Build writes `/api/fpl/dataset/gw{N}.json|.csv`, refreshes `/api/fpl/dataset/index.json`,
and rebuilds `all.json|.csv` by reading every `gw*.json` already on disk in `out`
(so old gameweeks survive without rebuilding them). `/data/` human page: what this is,
the CC BY terms with the exact attribution line, the column glossary, three curl
examples, links to every file, and a "cite us" block. Sitemap + llms.txt carry `/data/`
and the dataset URLs. WC builds: no dataset, no `/data/`, byte-identical.
- [ ] Failing tests: files exist after a build; `all.json` includes a pre-seeded prior
  gameweek file on disk; `/data/` names CC BY 4.0 and links the CSV; WC build has no
  `/data/`; sitemap contains `/data/`.
- [ ] Run. - [ ] Implement. - [ ] Full suite. - [ ] Commit
  `feat(data): the build publishes the dataset and the /data/ page`.

### Task 3: `/fpl/accuracy/` page + benchmark artifact
**Files:** `evmax/render.py` (accuracy page), `evmax/fpl_build.py`, `games/fpl/
grading.py` or a new `scripts/benchmark_export.py`, tests
Page: the full graded ledger (per-GW MAE, ep_next column stating "captured from GW2",
both squad lines projected→realized_official, running duel), the method in plain
language, links to every grading JSON, and a "how to check us" paragraph naming the
frozen-snapshot + public-JSON chain. Link it from the nav-adjacent spots that already
link `/track-record/` (do NOT add a nav pill; the track record links it).
Benchmark artifact: `scripts/benchmark_export.py --gw N` writes
`evmax/assets/benchmark/gw{N}-evmax.csv` with `player_id,player_name,gameweek,
predicted_points` from the FROZEN projection snapshot (never a rerun).
- [ ] Failing tests: page renders GW1's row with MAE 2.734 and duel "0-1"; ep_next cell
  reads the captured-from-GW2 note; benchmark CSV header + row count from a synthetic
  snapshot; the exporter refuses a gameweek with no frozen snapshot.
- [ ] Run. - [ ] Implement. - [ ] Full suite. - [ ] Commit
  `feat(site): the accuracy page and the benchmark submission artifact`.

### Task 4: the MCP server
**Files:** create `mcp/package.json`, `mcp/index.js`, `mcp/README.md`,
`mcp/test-smoke.js`, `docs/DATASET.md`
Node ESM, dependency `@modelcontextprotocol/sdk` only, stdio transport, no build step,
no secrets. Base URL defaults to `https://evmax.ai`, overridable by `EVMAX_BASE_URL`.
Tools: `list_gameweeks`, `get_projections({gameweek, position?, limit?})`,
`get_player({name, gameweek?})`, `get_duel()`, `get_accuracy()`,
`get_distribution({name, gameweek?})`. Every tool result appends the source URL and
"CC BY 4.0 — attribute evmax (https://evmax.ai)". Fetch failures return a clear text
error, never a stack. README: what it is, `npx`/`claude mcp add` lines, tool table, the
license line. `docs/DATASET.md`: the schema mirror (columns, types, meaning, update
cadence, license). `mcp/test-smoke.js`: node script hitting the LIVE site, asserting
each tool returns the expected shape; documented as manual (not in the Python suite).
- [ ] Write files. - [ ] `cd mcp && npm install && node test-smoke.js` — must pass
  against live evmax.ai; iterate until it does. - [ ] Full Python suite (unaffected).
- [ ] Commit `feat(mcp): evmax MCP server over the public CC BY API`.

### Task 5: verification + docs
- [ ] Build GW2 into a temp dir; verify dataset files, `/data/`, `/fpl/accuracy/`;
  screenshot `/data/` and `/fpl/accuracy/` into
  `/private/tmp/claude-501/-Users-bartlomiej-granat/3d62b63f-34db-4a8c-a6d3-c80067810eb9/scratchpad/phase2/`
  (`data.png`, `accuracy.png`); LOOK at them and iterate. - [ ] CHANGELOG + README.
- [ ] Commit.
