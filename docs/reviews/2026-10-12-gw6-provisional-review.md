# GW6 final retrospective, updated 14 October 2026

**Official FPL results are final and locally graded. Publication remains paused.**
Coventry beat Newcastle 4–1 on 12 October. Both clubs record full time.
[Coventry match report](https://www.ccfc.co.uk/news/2026/october/12/coventry-city-4-1-newcastle-united-/),
[Newcastle match centre](https://www.newcastleunited.com/en/matches/mens-team/coventry-city-v-newcastle-united-english-premier-league-20261012).

The retained official capture on 14 October at 11:35:28–11:35:37 UTC shows
all ten fixtures `finished=true`, GW6 `finished=true` and `data_checked=true`.
All three requests returned HTTP 200 and `Age: 0`. The existing finality guard
passed; `scripts/grade_gw.py` banked the grade from these retained inputs.
Earlier provisional captures remain unchanged. The displayed average moved
from 55 in the 13 October morning capture to the final 58; player totals and
the two reconstructed squad scores are unchanged.
Sources: [official fixtures](https://fantasy.premierleague.com/api/fixtures/?event=6),
[official points](https://fantasy.premierleague.com/api/event/6/live/), and
[official gameweek status](https://fantasy.premierleague.com/api/bootstrap-static/).

The eligible forecast is artifact
`a8a8df5f59f3f68008f2c761d90a01536efd257dd02311182ccb720efddedebf`, captured
9 October at 14:27:19 UTC. Every comparison below uses that forecast. Current
results do not rewrite the predictions, research notes or capture timestamps.

## What the available results say

| Registered website squad | Frozen XI forecast with captain | Final total with FPL autosub rules |
|---|---:|---:|
| Model XI | 56.74 | 41 |
| Consensus XI | 48.36 | 71 |
| Final FPL field average | — | 58 |

These are scores reconstructed from the published squads. They exclude any
unrecorded account transfers, hits or chips. The user account was not accessed.
Every player has completed his fixtures, and both reconstructed squads have
zero pending players. Bobby Thomas played as an unused model substitute.
The totals remain 41 and 71, with the same autosubs: E.Le Fée replaces
Szoboszlai for Model (+2); Guéhi replaces Szoboszlai (+6) and Diop replaces
Tzolis (+2) for Consensus. Palmer and Haaland retain their respective
captain bonuses; neither requires vice fallback. The banked published-XI-only
totals are 39 and 63; the `realized_official` fields are 41 and 71.
Model finishes 17 below the field average, Consensus 13 above it.
The forecast column excludes autosub and conditional vice option value.

The 30-point gap is a portfolio failure in this snapshot. Its accounting is:
Consensus gained 13 points in the differing defenders, 6 in the differing
midfielders, 7 in the differing forwards and 6 through additional autosub
points. Model gained 2 through the captain bonus. These describe observed
outcomes. They do not establish which information was better before kickoff.

| Player | Frozen xPts | Final points | Minutes |
|---|---:|---:|---:|
| Saka | 7.96 | 2 | 90 |
| B.Fernandes | 7.16 | 1 | 90 |
| Cole Palmer | 5.22 | 8 | 87 |
| João Pedro | 4.12 | 12 | 71 |
| Szoboszlai | 4.68 | 0 | 0 |

The refreshed captain ranking missed. Keeping Palmer produced more points
than following either Saka or Fernandes this week. This does not validate a
stale decision process. It does rule out blaming the poor score on failure
to execute those particular captain recommendations. Palmer → Saka would
have lost six raw points in GW6. Its published +13.03 estimate covered five
weeks, so that horizon remains unevaluated.

The clearest appearance miss was Szoboszlai's 0.90 start assumption.
Liverpool now confirms a hamstring problem after international duty.
The reviewed club preview and injury list did not establish a public
pre-deadline warning for him. The time at which a reliable warning became
available remains unverified. A later explanation cannot be used as evidence
that the earlier forecast knew it.
[Club injury update](https://www.liverpoolfc.com/news/dominik-szoboszlai-injury-update-andoni-iraola-man-city),
[club preview](https://www.liverpoolfc.com/news/team-news-premier-league-manchester-city).

## Model quality and process are separate checks

On all 667 frozen player rows, final paired MAE is 1.103 for evmax
and 1.176 for frozen official `ep_next`. Among the 315 who played, it is
2.010 versus 2.268. For the descriptive 206-player 60+ cohort, it is 2.383
versus 2.676. The first cohort contains 352 zero-minute players. These
single-week metrics establish no prospective superiority and
do not excuse the squad result. Coventry/Newcastle rows now contribute.
No current `ep_next` values enter the comparison.

The publication had concrete process failures. Its registered armbands
and refreshed ranking differed, while template copy asserted that they agreed.
The 10 October correction fixed the explanation after the deadline. The
registered XI also contained an unavailable reserve keeper. Research clearance
alone did not establish that this unchanged roster was freshly optimized.
The next publication needs an explicit decision receipt, including the owner
accepting or declining each proposed move and armband. An account change must
be confirmed separately. No missed user-account changes can be inferred here.

The original comparison method description was inaccurate. The archived
Consensus state's `method_note` declares the most-owned legal template from
GW2. The original article described an expert mention tally and separate expert
minutes. The 13 October local audit fixes correct this description, but have
not been published. Both squads are valued by the shared model. The score gap
therefore cannot isolate expert versus model minutes information. Correct description:

> The Consensus XI follows the declared ownership-template policy. Evmax
> values both published squads with the same forecasting model. Their score
> gap compares portfolio outcomes. It does not isolate the quality of expert
> minutes information.

No four-arm comparison or external-projection benchmark was frozen for GW6.
None can be manufactured after the results.

## Reset checklist for GW7

1. **Completed locally:** all fixture/event finality flags passed on 14 October;
   the existing artifact is graded, autosubs/captains reconcile and the final
   field average is 58. Preserve the retained results and original forecasts.
2. Confirm the actual user portfolio, XI, bench order, captain/vice, bank,
   free transfers, hits and chips through the user. Keep it distinct from the
   website roster. Current website files record Model bank 0.0 and two free
   transfers, Consensus one free transfer and no bank field. These are recorded
   website inputs, not verified GW7 account finances. Confirm purchase/selling
   prices and chip history; do not silently assume Consensus has zero bank.
   No account access or transfers are authorized in this task.
3. Refresh GW7 inputs and histories after GW6 data is finalized.
   Recheck each availability override and the dated club news. GW6 round-only
   notes expire. Review Szoboszlai, the unavailable reserve keeper and the
   rotation/injury flags. Do not rebuild the old forecasts on new information.
4. Rebuild the working horizon and legal options using actual selling prices.
   Show market-priced versus estimated future fixtures and recovery scenarios.
   Reassess all 15 positions, bench cover and captaincy after research. Keep
   multiweek expected gain distinct from this week's realized return.
5. Create a dry build **outside `dist`**, review `fpl-decision-gw7.json` and
   record one accepted recommendation set and its assumptions before the
   verified **GW7 deadline: 17 October 2026, 10:00 UTC / 11:00 UK time**.
   Review all 15, XI, ordered bench, captain/vice, chip, bank, free transfers,
   input context, hold/transfer rationale and one-week alternatives. Record a
   final dated news check near the deadline. Use the exact proposal ID with
   `scripts/fpl_decision.py` only after the operator accepts it, as described in
   [the acceptance procedure](2026-10-13-fpl-audit-fixes.md#gw7-operator-procedure).
   Changed forecast inputs, simulation count or squad roles require a new review.
   Reconcile the published state with the accepted choices. Check every ranking
   claim and the ownership-template method label. Account submission remains a
   separately confirmed user action; no GW7 proposal is accepted yet.
6. Run the dossier, affordability, identity and publication checks. Retain
   the pre-deadline forecast and its receipt, plus a durable private source
   backup. If enrolling prospective comparators, freeze them before the deadline
   on matching populations/vintages/policies; record gaps rather than backfill.
   Publish only after separate authorization. Evaluate the next frozen week
   without tuning to GW6 winners. No GW7 squad choice or model change is made here.

## Evidence and current readiness

The final official raw snapshots, response headers, source URLs, capture times,
SHA256 receipts, `results.json`, `final-analysis.json` and replay script are
retained at `data/reviews/gw6/2026-10-14-final/` (Git-ignored). Earlier 12 and
13 October evidence directories remain unchanged. The banked grade is
`evmax/assets/accuracy/gw6.json`. Its `results_sha256` binds to the canonical
retained payload:
`2a87accc591ed2b1071e81ab9beda6c12602bd23a4e6f44f871efdc08be2f4bc`.
Reproduce the final analysis without writing from the repo root:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/bartlomiej.granat/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -B data/reviews/gw6/2026-10-14-final/reconcile.py
```

The explicit interpreter is the installed Python 3.12 runtime used for final
verification. For test scratch files, use the permitted repository directory
`TMPDIR="$PWD/data/reviews/gw6/.runtime"`; no OS temporary directory is required.

Both squad totals reconcile to their individual rows, with no pending players
or missing forecast outcomes. Raw results are retained separately from forecast
inputs; no live or forecast-input cache was replaced. The finality guard accepts
this capture and continues to reject the earlier unchecked one. Verification
and preservation evidence are retained in the final evidence directory:
**59 focused finality, grading, live, decision and archive tests passed on Python
3.12 with networking blocked**, and **353 pre-existing protected files** retain
their SHA256 hashes. System Python 3.9.6's initial 54-test run had one retained
GW4 exact-float replay error (last-digit reduction differences); the same test
passes on 3.12. No historical grade or code was changed. New GW6 banked player
metrics match the Python 3.12 replay exactly.
Local grading is complete. Publication, a GW7 roster decision, durable off-device
backup and any account changes remain pending. Private ignored evidence must
travel separately from Git for replay on another machine.
