# Season learnings — 2026/27 FPL

Append-only (spec §8). One entry per mistake: mistake → root cause →
structural fix → status. The Monday runbook adds entries; nothing is ever
deleted — a repeated root cause is the signal that a fix did not hold.

## GW1

### 1. The double-Spurs-keeper squad advice

- **Mistake:** published squad advice carrying two keepers from the same club
  (Vicario + Kinsky), a squad no serious manager fields.
- **Root cause:** no per-squad validation between "the optimizer/tally
  produced 15 names" and "the site published them" — legality was checked,
  sanity was not, and under deadline pressure nobody looked.
- **Structural fix:** the publish gate builds a dossier for every published
  player and refuses reds without a sourced note (phase 5 task 2); the
  consensus squad itself is rebuilt mechanically from real ownership from GW2
  (`--reset-consensus`, phase 4c, spec D8).
- **Status:** closed (gate merged; consensus reset merged).

### 2. The wrong Sangaré

- **Mistake:** an expert wrote "Sangare, Brentford 5.5"; the feed had exactly
  one Sangaré — Forest, 5.0 — and the tally credited him. The expert meant a
  player who joined the league after our capture (M.Sangaré).
- **Root cause:** the bootstrap capture was a point-in-time snapshot with no
  churn detection — arrivals and renames between captures were invisible, so
  a name matched whoever happened to hold it.
- **Structural fix:** `core/fpl_diff.py` (phase 5 task 1) reports arrivals,
  renames and club moves at the top of every Thursday session; renames become
  state-file `aliases`, never rewrites. Unresolved/drifted names are red in
  the dossier.
- **Status:** closed (feed diff merged; Thursday runbook step 2).

### 3. The Watkins hold

- **Mistake:** held Watkins into a 0-minute blank while ~50k managers sold
  him inside two days. The crowd knew; the pipeline had no ear for it.
- **Root cause:** transfer-flow data was in the feed all along
  (`transfers_out_event`) and nothing read it; "the crowd is selling" was not
  a signal anywhere in the system.
- **Structural fix:** outflow z-spikes (threshold 3.0) in the feed diff AND
  as a red dossier condition (tasks 1-2); the transfer optimizer forces
  flagged players to the top of the sale block regardless of delta (task 5).
- **Status:** closed (all three merged; GW2's Watkins decision is the first
  live user).

### 4. The Isak proxy

- **Mistake:** Isak's start probability priced off 694 post-arrival minutes
  (~0.21) when he was Liverpool's only fit senior forward — effectively
  nailed. Reddit corrected us.
- **Root cause:** the minutes proxy (last season's start rate) treated a
  mid-season transfer's small sample as a rotation signal, and nothing forced
  a human read of low-start published players.
- **Structural fix:** `start_prob < 0.75 on the proxy` is a red dossier
  condition — unpublishable without a sourced note (task 2); the optimizer
  holds the same floor so it cannot propose what the gate refuses (task 3).
- **Status:** closed (note `research/players/fpl-gw2-isak.md` is the
  template; re-pin weekly while the injuries hold).

### 5. The Maguire proxy

- **Mistake:** Maguire priced at ~50% starts while both other senior United
  centre-backs were injured/doubtful — same failure shape as Isak, found the
  same way (community pointer, verified in the feed).
- **Root cause:** same as #4 — the proxy cannot see squad-context (who else
  is fit), and no gate forced the check.
- **Structural fix:** same as #4; additionally the Thursday runbook's
  research step explicitly checks the feed's status/news for every squad
  member's positional rivals.
- **Status:** closed (note `research/players/fpl-gw1-maguire.md`, round 2
  pinned; the runbook step is live).

### 6. The bench-order mismatch

- **Mistake:** the bench order in the owner's real FPL app did not match the
  published state file, so the site's autosub grading and the real team
  disagreed about who came in.
- **Root cause:** no step anywhere said "mirror the published state into the
  app" — the state file and the app were maintained independently.
- **Structural fix:** Thursday runbook step 4 ends with mirroring the state
  into the app, bench order included; the live layer's autosub walk
  (phase 4c) makes any residual mismatch visible the first Saturday it
  matters.
- **Status:** closed (runbook live); watch for one clean gameweek before
  calling the process proven.

## GW1 result (2026-08-25, Monday close)

**The duel, week 1: Consensus 53 — Model 44. The crowd won by 9.** Field average 50
(the model finished 6 UNDER average; the mid-week "+8 over average" was a mirage of
early kickoffs). João Pedro (11) decided it — the exact player the model rated ~#25
and the community roast called a troll. The model's other misses: Gakpo 12 (rated
4.8, unowned), Bruno (c) 2, Thiago 0, Watkins 0-minutes. Its wins: Ndiaye 9,
Calafiori 9 (the "best value in the game" call landed — in the OTHER squad),
Tarkowski 6, the Watkins autosub insurance (+2). Player-level MAE 2.734 over 58
graded players (noise ceiling ≈2.8; small sample).

- Mistake: mid-GW average (36) treated as a benchmark; final averages run much
  higher once all matches land. Fix: never quote average until the GW closes
  (runbook wording updated).
- Mistake: grading.squad_line banked as-published XI (42) as "realized"; readers
  compare official scores. Fix: `realized_official` (autosubs + captain fallback)
  banked alongside, with the autosub trail (shipped 2026-08-25).
- Bug found: `scripts/grade_gw.py --refresh` refreshes the BOOTSTRAP, which
  invalidates the frozen GW's sim cache — the Monday rebuild then drifts from the
  frozen snapshots. RESOLVED before GW3: the grading refresh path now calls only
  `fpl_live.refresh_live`, which writes live_gw{N}.json and nothing else — the
  GW2 Monday grade ran with the bootstrap untouched, and the field average was
  read in-memory rather than through the cache.

## GW2 (graded 2026-09-01)

- Model 93 official (81 as-published + Tarkowski autosub for Senesi),
  Consensus 84, provisional field average 81. Duel level 1-1. Player MAE 2.848
  over 64 graded, beating ep_next (2.909) for the second week.
- What worked: captaincy FROM the model rank. Bruno was rank 1 while the crowd
  sold him in six figures; 23 raw, 46 doubled. The credibility engine's
  panic-sell verdicts (Bruno, Mbeumo, Calvert-Lewin holds) all returned.
- What worked: the forced-sale rule. Watkins sold on verified reporting two
  days before FPL flagged anything; Evanilson returned 5 against a certain 0.
- What cost: benching a 75% doubt (Gibbs-White) in the blind Saturday-lunch
  slot; he played 90 and scored 13, and only one autosub slot opened. Process
  stands — a rushed-back MCL at Anfield was the right thing to bench on the
  information held Thursday — but the ledger records the 13.
- Worth keeping: declining the -4 for Gakpo saved 12 points (Gibbs-White 13
  vs Gakpo 5 plus the hit). One-transfer discipline beat the optimizer's
  second row; the horizon delta was real but free next week.

- Mistake (owner-caught): our own "best value in the game" call (Calafiori, 0.931
  pts/£m) was never in the Model squad — the squad was optimized BEFORE the
  expert-corpus notes upgraded his minutes (0.58 proxy → 0.85), and selection was
  never re-run after the notes landed. The consensus squad got him via the experts
  directly; he scored 9. Root cause: optimize-then-research ordering. Fix: the
  Thursday runbook hard-orders research → notes → optimize → gate; a post-notes
  re-optimization is now structurally guaranteed. (GW1, entry added 2026-08-25.)

## GW2 preparation (2026-08-25)

- Bug: season rollover broke priors — post-GW1 bootstrap carries current-season
  per-90s (1-game noise) and team_matches=38 assumption; De Cuyper projected 12.3,
  300 cold-starts incl. Saliba. Interim fix: merge preseason rates + live fields.
  Structural fix (pre-GW3): priors blend element-summary history with current
  season by minutes.
- Gate catch #1: 117k/110k/83k out-spikes on Bruno/Mbeumo/DCL — investigated, all
  90 clean minutes, panic selling; held with documented notes.
- Gate catch #2: consensus template reset imported Hughes (0 GW1 minutes, 49k
  correcting owners) from raw ownership — replaced with evidenced Slater;
  consensus.py should gain an evidence filter (minutes > 0) next revision.
- Gate semantics fixed: graded gameweeks skip the gate (frozen history must not be
  re-judged against later snapshots).
- Owner recency correction: Watkins "treat as OUT" was 24h stale (returned to
  training + apology); rewritten as 0.40 with both-sides sources. Recency rule
  added to runbook.
- Decision: FT BANKED (2 next week, window closes Sept 1 = full information);
  risks handled free: DCL→XI over Gibbs-White (knee, 0.55), vice→Szoboszlai,
  bench order re-tuned. Optimizer confirmed: all GW-W sales horizon-negative.
- Tests decoupled from weekly state content (GW1 reference truths frozen as
  fixtures) — state files mutate weekly by design.

## Phase 2 (2026-08-26)

- Shipped in a day: distributions, public dataset, MCP server, accuracy page,
  benchmark exporter. Suite 982 → 1102.
- Design correction caught before it shipped: "full distribution view" had been
  filed as premium on 08-24, which contradicts the operative free/paid line
  (game data free, your-team tools paid) and would have hidden our one
  uncopyable output behind a wall nobody is paying at yet.
- Bug the exporter surfaced: the Sangaré alias lived in a squad state, and the
  consensus wildcard reset wiped it — a season-long fact stored in a weekly
  file. Fixed with a durable rename ledger. General lesson: durability of the
  FACT decides where it lives, not which feature first needed it.
- Both parallel agents flagged every interpretation loudly (the process change
  from the cards rejection held): the distributions agent caught a simcache
  int-key stringification the plan never anticipated, and reverted a caption fix
  that would have changed a WC page.
