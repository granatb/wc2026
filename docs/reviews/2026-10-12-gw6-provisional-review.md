# GW6 retrospective draft, updated 13 October 2026

**All matches played. Official FPL finalization is pending. Publication is paused.**
Coventry beat Newcastle 4–1 on 12 October. Both clubs record full time.
[Coventry match report](https://www.ccfc.co.uk/news/2026/october/12/coventry-city-4-1-newcastle-united-/),
[Newcastle match centre](https://www.newcastleunited.com/en/matches/mens-team/coventry-city-v-newcastle-united-english-premier-league-20261012).

Official FPL captures at 08:48 and 08:50 UTC on 13 October agree: all ten
fixtures have `finished_provisional=true`, zero have `finished=true`, and
GW6 `finished=false` and `data_checked=false`. The second capture uses
cache-busting URLs and returns `Age: 0`. Final grading remains blocked.
Sources: [official fixtures](https://fantasy.premierleague.com/api/fixtures/?event=6),
[official points](https://fantasy.premierleague.com/api/event/6/live/), and
[official gameweek status](https://fantasy.premierleague.com/api/bootstrap-static/).

The eligible forecast is artifact
`a8a8df5f59f3f68008f2c761d90a01536efd257dd02311182ccb720efddedebf`, captured
9 October at 14:27:19 UTC. Every comparison below uses that forecast. Current
results do not rewrite the predictions, research notes or capture timestamps.

## What the available results say

| Registered website squad | Frozen XI forecast with captain | Provisional total with official autosubs |
|---|---:|---:|
| Model XI | 56.74 | 41 |
| Consensus XI | 48.36 | 71 |
| FPL displayed field average, unfinalized | — | 55 |

These are scores reconstructed from the published squads. They exclude any
unrecorded account transfers, hits or chips. The user account was not accessed.
Every player has completed his fixtures, and both reconstructed squads have
zero pending players. Bobby Thomas played as an unused model substitute.
The totals remain 41 and 71, with the same autosubs. The field average shown
by FPL is provisional. No settled comparison against it is banked. The
forecast column excludes autosub and conditional vice option value.

The 30-point gap is a portfolio failure in this snapshot. Its accounting is:
Consensus gained 13 points in the differing defenders, 6 in the differing
midfielders, 7 in the differing forwards and 6 through additional autosub
points. Model gained 2 through the captain bonus. These describe observed
outcomes. They do not establish which information was better before kickoff.

| Player | Frozen xPts | Provisional points | Minutes |
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

On all 667 frozen player rows, provisional paired MAE is 1.103 for evmax
and 1.176 for frozen official `ep_next`. Among the 315 who played, it is
2.010 versus 2.268. For the descriptive 206-player 60+ cohort, it is 2.383
versus 2.676. The first cohort contains 352 zero-minute players. These
unfinalized, single-week metrics establish no prospective superiority and
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

The comparison method also needs an accurate description. The archived
Consensus state's `method_note` declares the most-owned legal template from
GW2. The article still describes an expert mention tally and separate expert
minutes. Both squads are valued by the shared model. The score gap therefore
cannot isolate expert versus model minutes information. Proposed website copy:

> The Consensus XI follows the declared ownership-template policy. Evmax
> values both published squads with the same forecasting model. Their score
> gap compares portfolio outcomes. It does not isolate the quality of expert
> minutes information.

No four-arm comparison or external-projection benchmark was frozen for GW6.
None can be manufactured after the results.

## Reset checklist for GW7

1. Recheck final official FPL fixture and event flags. Require all fixtures
   `finished=true`, GW6 `finished=true` and `data_checked=true` before banking
   a final grade or settled field-average comparison. Recapture points and
   reconcile autosubs/captain fallback against the frozen squads.
2. Confirm the actual user portfolio, XI, bench order, captain/vice, bank,
   free transfers, hits and chips through the user. Keep it distinct from the
   website roster. No account access or transfers are authorized in this task.
3. Refresh GW7 inputs and histories after GW6 data is finalized.
   Recheck each availability override and the dated club news. GW6 round-only
   notes expire. Review Szoboszlai, the unavailable reserve keeper and the
   rotation/injury flags. Do not rebuild the old forecasts on new information.
4. Rebuild the working horizon and legal options using actual selling prices.
   Show market-priced versus estimated future fixtures and recovery scenarios.
   Reassess all 15 positions, bench cover and captaincy after research. Keep
   multiweek expected gain distinct from this week's realized return.
5. Record one accepted recommendation set and its assumptions before the
   verified **GW7 deadline: 17 October 2026, 10:00 UTC / 11:00 UK time**.
   Reconcile the published state with the accepted choices. Check every
   ranking claim and the ownership-template method label. An actual account
   submission remains the user's action.
6. Run the dossier, affordability, identity and publication checks. Retain
   the pre-deadline forecast and its receipt. Publish only after the parent's
   decision. Evaluate the next frozen week without tuning to GW6 winners.

## Evidence and current readiness

Timestamped official snapshots, the reproducible analysis and provisional
outputs are local at `data/reviews/gw6/2026-10-13-all-played-provisional/`
(Git-ignored). The 12 October pre-last-match snapshot is retained separately
in `data/reviews/gw6/2026-10-12-provisional/`.
Reproduce the captured analysis from the repo root:

```sh
UV_CACHE_DIR=/tmp/wc2026-uv-cache uv run python data/reviews/gw6/2026-10-13-all-played-provisional/analyze.py
```

Capture logs also remain under `/tmp/wc2026-gw6-review-20261013/`.

The 46 relevant live/grading/archive tests passed. Both squad totals reconcile
to their individual rows. The final-grade gate rejects the all-played but unfinalized GW6 snapshot.
The frozen artifacts, baselines, states and forecast-input caches are protected
by a SHA256 manifest. This is a local report draft. Final FPL grading and the field-average comparison, publication, a next-week
roster decision and any account changes remain pending.
