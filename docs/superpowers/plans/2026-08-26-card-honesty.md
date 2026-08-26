# Card honesty + the crowd-vs-model landing

> REQUIRED SUB-SKILL: superpowers:executing-plans, task-by-task.
> Branch `card-honesty` off main in the worktree you are given. Suite 1123 green at
> start, green at every commit. Python 3.9 stdlib, explicit-path staging, no push/
> merge/deploy. WC pages byte-identical. Frozen GW1 artifacts untouched.
> Owner feedback verbatim, 2026-08-26 — these ARE the acceptance criteria:
>  - "could the form wave be just point of their last x appearances?"
>  - "we don't know what green means in GW below"
>  - "We say we don't buy haaland and call him S premium buy"
>  - "start by showing most transferred in and their cards, most transferred out,
>     our picks, our takes, and model's tier on each of them"
>  - "we have space to show small lower bound expected points in the middle and
>     small upper bound"

### Task 1 — the wave becomes a dot timeline: played, then projected
> **DESIGN CHANGE, owner 2026-08-26, supersedes the original Task 1** (a labelled
> auto-switching area wave): *"but we can have last few realised and next few
> projected dots right? the wave seems hard to get"*.

Replace the area wave with ONE horizontal dot strip carrying both halves of a
player's story:
- **One dot per gameweek**, left to right: the last up-to-3 PLAYED gameweeks,
  then the next PROJECTED gameweeks, capped at **7 dots total** (so a full
  3 played leaves the "next up-to-4 projected"; at GW2 today that is
  1 realized + 5 projected, and the mix slides as the season runs).
- **Realized dots**: solid, full-strength green; value = ACTUAL points that
  gameweek.
- **Projected dots**: hollow/outlined and lighter; value = that gameweek's xPts
  from the six-week vector, **rounded to whole points** for visual parity with
  realized (the exact figure stays in the title text).
- **Vertical position encodes the value** on a scale shared by every dot in the
  strip (a lollipop/scatter, not a wave), over a faint baseline.
- **A thin vertical divider** between the last played and the first projected
  dot — the "now" line.
- **Tiny GW labels under the dots**, and a caption `played · projected` whose
  two words are styled to match their dot styles, so the caption IS the legend.
- Degrade honestly: no history → all dots projected (correct today); no
  six-week vector → realized dots only; neither → the existing fixed-height
  empty band with its "no history yet" text, so the row rhythm holds.
- Deterministic, no RNG. Inline SVG for dots/baseline/divider; ALL numbers and
  labels in HTML (SVG text scales badly between card and page width). The
  `title`/aria text spells it out: `GW1 2 points played · GW2 8.6 projected · …`.

Source for the realized half: the per-gameweek history the FPL API's
`element-summary/{id}` returns (`history[].round`, `.total_points`,
`.minutes`). Cache it in `data/fpl/form_history.json` alongside the existing
defcon backfill, incrementally (only fetch players missing the current GW),
same politeness delay as `fpl_api.fetch_defcon_backfill`.
**Today this yields 1 played gameweek per player, so nearly every card is all
projected dots — that is correct and expected. Do not fake it.** Tests must pin
both dot types and every degradation path.

### Task 2 — the fixture chips explain themselves
The next-4 chips are difficulty-tinted with no key. Add a one-line caption under the
strip: `next 4 · greener = easier fixture` (and for chips with no priced fixture,
`grey = not priced yet`). Keep the existing `title` tooltips.

### Task 3 — kill the buy/sell contradiction
The card prints a generic call ("buy") derived from rank. It contradicts the site's
own published position (our squad does not own Haaland, yet his card says BUY) and
it is the single most damaging inconsistency on the page. Replace the call with OUR
ACTUAL STANCE, computed from the two published squad states:
- `in our XI` · `on our bench` · `in the consensus XI` · `not in either squad`
Render as: `{stance} · tier {T} · {price_band}`. The model's opinion is the TIER; our
position is the stance; nothing on the card tells a reader to buy anything.
Remove `verdict["call"]` from the card face (keep it in the JSON, renamed
`rank_call`, documented as "rank-derived, not a recommendation") so nothing silently
depends on it. A test must assert: a player absent from both squads never renders
the word "buy", and a player in our XI renders "in our XI".

### Task 3b — expected points per million comes back
> **ADDED, owner 2026-08-26**: *"but we used to have expected points per
> million"*.

The card shows only `realized {x} pts/£m` (season points ÷ price). At GW2 that
is 0.17 for B.Fernandes — 2 points over £12.0m, i.e. noise — and it silently
replaced the PROJECTED value (`projection.value`, x_points ÷ price = 0.72 for
the same player), the number the efficiency article actually ranks on and the
only one that means anything this early.
- **Always show** `value {projection.value} pts/£m` (projected), where
  `realized` currently sits in the stat rows.
- **Show realized alongside it ONLY at ≥3 played gameweeks** this season (the
  same played count the dot timeline needs), compactly:
  `pts/£m 0.72 proj · 1.41 so far`.
- Below the threshold realized pts/£m does not appear at all — it is division
  by a two-game sample and it misleads.
Pin both branches with tests.

### Task 4 — bounds around the hero number
Flank the big xPts with its own distribution: `{p10}` small and muted to the left,
`{p90}` small and muted to the right, e.g. `1 · 8.61 · 17`, with `title` text
"10th percentile" / "90th percentile" and a caption word `floor`/`ceiling` in the
existing tiny type. Degrade silently when a card has no distribution.

### Task 5 — the landing becomes crowd-vs-model
Replace "This week's top cards" with three labelled card rows, in this order:
1. **Most transferred in this gameweek** — top 4 by `transfers_in_event` (bootstrap),
   each card as-is, plus a one-line model take per card (see below).
2. **Most transferred out** — top 4 by `transfers_out_event`, same treatment.
3. **Our picks** — the 4 highest-xPts players in OUR squad.
Each row gets a short section intro naming what it is. Under each card in rows 1-2,
one derived sentence, generated NOT written: compare the crowd's move to the model's
tier and rank, e.g. `Crowd is buying. Model has him tier B, 41st by xPts this week.`
/ `Crowd is selling. Model still has him tier A, 6th.` Pure function with a test;
never invent a fact not in the row.
Keep the "Check your player" link under the last row.

### Task 6 — verification
Rebuild GW2, screenshot the landing and one player page into
`.../scratchpad/cardv2/` (`landing.png`, `player.png`), LOOK at them, iterate until
each acceptance sentence above is visibly satisfied. CHANGELOG. Report screenshots.
