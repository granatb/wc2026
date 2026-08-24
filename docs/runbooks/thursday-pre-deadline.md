# Thursday pre-deadline runbook

The weekly publish session (spec D2/D3, owner-approved 2026-08-24). Manual for
now — say "run Thursday" and Claude drives it end-to-end; Bartek gets the
five-line summary at the end and posts what he chooses. Every command runs
from the repo root. `N` is the gameweek locking this Friday.

The one rule this runbook exists to enforce: **no red-flagged player ships
without a sourced note.** The build refuses them mechanically (the publish
gate, `evmax/fpl_build.dossier_gate`); this session is where the research that
clears or confirms each flag actually happens.

## 1. Refresh the FPL caches (bootstrap + fixtures + this week's odds)

```bash
python3 -c "from games.fpl import model as m; m.load_gameweek(N, refresh=True)"
```

Re-captures `data/fpl/bootstrap.json`, `fixtures.json` and `odds_gw{N}.json`
(current market lines — these beat every estimate). First run of a season also
pays the one-time DefCon backfill (~400 calls, then cached).

> Deviation from the phase-5 plan as written: the plan said
> `manage.py fpl --round N --refresh`, but that flag refreshes the ESPN World
> Cup schedule, not the FPL caches — the one-liner above is what actually
> refreshes them (it is the same path the build itself uses).

## 2. The feed diff — what changed since last week

```bash
python3 -m core.fpl_diff
```

Prints renames, club moves, status changes, arrivals/departures, price moves
and transfer-out spikes, then rotates `data/fpl/feed_snapshot.json`. Run this
BEFORE writing any notes: the publish gate accepts a note over a red flag only
when its `updated:` date is on/after this snapshot — so notes written after
this step (today's date) pass, and last week's stale ones correctly do not.

Act on the report immediately:

- **Renamed** → add to the state files' `aliases` map (`{frozen name: new
  web_name}`); never rewrite the frozen name itself.
- **Moved club / status changed / outflow spike** → each becomes a research
  item in step 3.

## 3. Research every red and every published player (the Claude step)

For each squad member of BOTH states (`games/fpl/state.json`,
`state_consensus.json`) and especially everyone the diff or the gate flags:

- **What to check, in trust order:** the official feed's own `status`/`news`
  string first (it is the gate's ground truth); the club's pre-match press
  conference; established beat writers; r/FantasyPL threads — via Bartek's
  logged-in Chrome (claude-in-chrome) or pasted content only, never scraped
  (D4). A community claim counts once verified against the feed or a source.
- **Where notes go:** `research/players/<player>-gw{N}.md` — pinned to the
  round so it cannot leak into other weeks' sims, re-pinned forward each week
  the fact still holds.
- **Format** (core/research.py frontmatter; the gate needs non-empty
  `sources:` and today's `updated:`):

```markdown
---
entity: player
name: Watkins
status: starter
start_prob_override: 0.85
lambda_multiplier: 1.0
round: N
sources:
  - official FPL feed 2026-08-28: status 'a', no news
  - https://... (press conference / beat writer)
updated: 2026-08-28
---
One paragraph: the claim, who says so, what would invalidate it.
```

Bartek's own notes always win when he writes them (owner delegation, spec).

## 4. Re-simulate on the fresh data

```bash
python3 manage.py fpl --round N            # the order book (sanity-read the top 30)
python3 manage.py fpl --round N --transfers --bank 0.0   # the weekly swap table, both squads
```

The transfer table forces red-dossier players to the top as sale candidates
regardless of delta (the Watkins rule). Decide the week's transfer for each
squad, update the state files (squad, captain, `free_transfers`), and mirror
the change in the real FPL app before the deadline — bench order included
(GW1 learning: the app and the published state must match).

## 5. The gate check — a dry build

```bash
python3 -m evmax.build --gw N --no-llm --out /tmp/evmax-dry
```

If the publish gate refuses, **that is the system working**: it lists every
red player and why. Fix each one by writing the missing sourced note (step 3)
or changing the squad (step 4) — never by weakening a rule. There is no
`--force-publish`, deliberately.

## 6. Build live and deploy

```bash
python3 -m evmax.build --gw N --live
scripts/deploy.sh
```

## 7. Draft the posts (nothing auto-posts — D4)

- The **"poke holes" shortlist comment** for r/FantasyPL: our XI + captain +
  the one non-obvious call, phrased as a request for holes, with the site
  link. Claude drafts it in the session; Bartek posts it.
- Any article-tweak follow-ups the research produced.
- The **newsletter blurb** (Buttondown, monetization rung 1 — D7): three
  sentences, the squad, the captain, the one insight; Bartek sends it.

## 8. The five-line owner summary (the session's last output)

```
GW{N} locked: {formation}, C {captain} (V {vice}) — projected {total}.
Transfer: {out} → {in} ({delta} over the horizon{, -4 hit if taken}).
Gate: {n} red flags, {m} cleared by sourced notes, 0 shipped unresearched.
Watch: {the one thing that could invalidate a pick before Friday}.
Post: shortlist comment drafted; newsletter blurb ready.
```

## To schedule this later — PARKED (owner decision D3)

Both routes work today; the owner has parked automation until the manual
routine has earned trust.

- Claude Code scheduled cloud agent: `/schedule` → "every Thursday 09:00
  Europe/Copenhagen, run docs/runbooks/thursday-pre-deadline.md end-to-end,
  stop before deploy and post the five-line summary".
- Plain cron (local, mac): `0 9 * * 4 cd ~/personal/projects/wc2026 && python3 -m core.fpl_diff >> data/fpl/diff.log 2>&1`
  (the diff only — research and publish stay human-triggered).
