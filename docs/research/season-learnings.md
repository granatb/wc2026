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

## GW3 (graded 2026-09-07)

- Model 37 official, Consensus 59 (Guéhi autosubbed for O'Reilly), field average
  51 provisional. Duel 1-2, crowd leads. Player MAE 2.404 vs ep_next 3.198 —
  third week beating FPL's own number — but the first open-benchmark grade puts
  Fantasy Football IQ ahead of us on the same sample (2.37 vs 2.46 on 60+
  minutes, 1.19 vs 1.26 on everyone). Published as such.
- Squads benchmark, week one: Consensus 59 > FFIQ AI squad 45 > FFS Scout
  Picks 41 > Model 37. The crowd's template beat every model including ours.
- The captain: Bruno (model rank 1) returned 2 away at Everton, 4 doubled. Same
  process that produced 46 a week earlier. Captaincy from model rank is a policy,
  not a weekly bet; two data points say nothing yet, but the ledger holds both.
- The hold on Ndiaye: he started (86 min, 3 pts), so the agreed rule says keep.
  Gakpo scored 11 — the move we discussed and did not make cost 8 this week.
  Thiaw scored -1 — the move we discussed and did not make saved 4 (Le Fée, whom
  Thiaw would not have displaced anyway, scored 8 on the bench). Net of the two
  declined moves: -4, and the free transfer is banked (2 into GW4).
- Bench: Le Fée 8 and Shaw 4 sat behind an XI that scored 1-3 across six
  players. No autosub fired (everyone played). Bench order was right by
  projection; the outcome is variance, and the ledger records it as such.
- PROCESS MISS, owned: the runbook's Friday-morning re-freeze of FFS's FINAL
  Scout Picks did not run (no session Friday). Their squad is graded on the
  "early" version without a captain, labelled so on the page. Fix: the Thursday
  session must schedule the Friday check, or the freeze must be automated.


## Audit correction — 2026-09-07

The GW2/GW3 prose above overstated the ep_next streak. There are TWO measured
wins (GW2 and GW3); GW1 had no captured ep_next. There is no established
2.8-point noise ceiling. Original entries remain as the audit trail.
The original external GW3 comparison used different populations; corrected
common-population grades must be versioned, never presented as original grades.


## Role prior — 2026-09-08 (structural fix, closes the Sangaré/Watkins/Isak pattern)

- Mistake: Isak started all three September games (90, 90, 63) and the GW4
  preview card called him a 27% starter, 2.07 xPts, model rank 132nd. His GW2
  note (start 0.88, "re-pin forward each week while Ekitiké is out") was
  pinned to `round: 2` and nobody re-pinned it.
- Root cause: the minutes model weighted last season's start rate by its match
  count. 8 starts in 694 post-transfer minutes counted as 38 matches of
  "fringe" against 3 matches of "starts every week". Third occurrence of the
  same gap (Sangaré GW2, Watkins GW3); each time the fix was a research note,
  i.e. a knowledge-layer patch over a model defect.
- Structural fix (owner decision): last season's role is worth at most four
  matches and halves with every match played this season; this season's
  matches are recency-weighted with a three-match half-life from per-gameweek
  starts (form-history cache now carries `starts`; refetched once). Skill
  rates unchanged. Isak reads ~0.9 without any note.
- Cost accepted: a nailed starter benched twice in a row now reads below 50%
  (was >80%). That is a real role signal more often than not; the availability
  gate still handles injuries separately.
- Status: closed in code (`core/fpl_priors.py`), tests in
  `tests/test_role_prior.py`. Watch item: promoted-club players with no
  snapshot still start from the generic 0.35 prior.


## GW4 pre-deadline — 2026-09-12 (Saturday session; Thursday's did not run)

- Process: the runbook ran on Friday and Saturday, not Thursday. Nothing was
  lost (all freezes landed 24h+ before the deadline) but the owner's decision
  came in the last three hours, which is where mistakes happen.
- Decision (owner): Ndiaye → Palmer, Senesi → Bobby Thomas, two free
  transfers, Triple Captain on Palmer, 3-4-3, Szoboszlai vice. Model view at
  the time: +6.7 this week and +12.9 over five weeks versus holding, the best
  pair on the board. Ndiaye's keep-while-he-starts rule was set aside for the
  bigger upgrade; recorded here as a deliberate exception, not a drift.
- The transfer table hid the winning route (Gibbs-White → Palmer, and the
  Ndiaye route with a 4.0m filler) behind its five-row limit while showing two
  weaker Shaw rows. Open item: raise the row limit or rank by pair.
- Chips: no chip strategy existed in writing; the Triple Captain was a
  same-day owner call. The code recorded chips but never applied one; fixed
  today (state `active_chip`, tripled projection, tripled official grade).
  Proposal on the table, not decided: hold first-half chips for the double
  gameweek schedule and never Triple Captain a same-week signing.
- Expert scan: never a runbook step; done by hand this week (PL Scout, FFS,
  FFIQ, Fix, All About FPL). Owner asked for it as a weekly article with links.
- Bug found on the first real freeze: the forecast archive's checksum failed
  on integer-keyed distributions; fixed before the snapshot.
- Watch: Bobby Thomas is a 4.0m defender projected off three starts and the
  price prior; Palmer's Hull fixture is a one-week spike, the model has him
  5.1–5.5 a week from GW5.
