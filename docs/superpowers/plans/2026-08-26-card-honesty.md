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

### Task 1 — the wave says what it is, and becomes real form when form exists
The band is currently the six-gameweek PROJECTION and is unlabelled, so a reader
cannot tell what it means. Two changes:
(a) **Label it, always**: a small caption under the band, `projected · GW{n}–GW{m}`.
(b) **Auto-switch to realized form** the moment there is enough of it: when a player
has **≥3 played gameweeks** this season, the band draws his ACTUAL points per
gameweek instead, captioned `points · last {k} gameweeks`. Source: the per-gameweek
history the FPL API's `element-summary/{id}` returns (`history[].round`,
`.total_points`, `.minutes`). Cache it in `data/fpl/form_history.json` alongside the
existing defcon backfill, incrementally (only fetch players missing the current GW),
same politeness delay as `fpl_api.fetch_defcon_backfill`.
**Today this yields 1 row per player, so every card stays on the projection band —
that is correct and expected. Do not fake it.** A test must pin both branches.

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
