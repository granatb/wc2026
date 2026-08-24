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
