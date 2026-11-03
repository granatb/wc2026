# GW10 early preview release — 3 November 2026

The authorized Tuesday preview uses a completed fresh input refresh and unchanged
model `2026-10-09.1`: 50,000 simulations, seed 12345, 670 player projections.
Official bootstrap/fixtures were captured at **10:15:58 UTC**; all 454 requested
histories completed at **10:21:25 UTC**, without failures. Fresh ESPN market
inputs cover all ten GW10 fixtures, captured **10:17:00 UTC**. The offline model
run completed **10:23:45 UTC**. No October rehearsal outputs were reused.

Palmer leads at **7.29 xPts / 14.58 captain xPts**, Haaland follows at **7.12 /
14.23**, then Barry 6.73 and Gabriel 6.46. The 0.17-point Palmer–Haaland gap is
small. These are provisional individual rankings ahead of European fixtures,
not an accepted squad selection, account ownership claim or deadline-final plan.
Saka remains injured, zero projection; Szoboszlai and Calvert-Lewin are available
in the fresh feed. Liverpool's official Arsenal match report confirms Szoboszlai
returned from the bench. Availability does not guarantee minutes.

Newcastle 0–1 Everton completes all ten GW9 matches. The second official check
at **10:25:38 UTC** still has `finished=false` and `data_checked=false`; GW9
remains provisional. No frozen GW8/GW9 board exists, so no retrospective forecast
or team grade was created. Original GW7 forecasts, 53-point early grade and
59-point final-selection record remain untouched.

The new preview publisher reuses existing article/card styles and preserves a
dated derived board at `evmax/assets/previews/gw10/2026-11-03.json`. Publication
validation binds the board and every current player-card projection to that
record, while all previous accepted-squad gates remain in force. The earlier
GW8 preview API is retained under `/api/fpl/previews/gw8/2026-10-21/`; its article
only changes data links to that archive. The current cards show GW10, with no
stale future-week projections or inferred owner squad. Current status points to
the new preview rather than a future publication target.

Validation: **1,444 tests passed, five existing skips**. Publication validation
passes. The article is distinct from the homepage, and key links resolve. All
397 protected historical/input/model files are unchanged; only the intentionally
mutable GW9 status source changed. No security configuration or FPL account action.

Published and verified **3 November, 10:32:51 UTC**. Content commit `f0657bd`
(`f0657bd68fb22aff1447e91624e12182872ab22b`) is pushed and remote-confirmed on
`chore/gw6-thursday`. Deployment: https://a65858e7.evmax.pages.dev . All **27 live
checks** match the reviewed local bytes, including production and deployment
URLs, current cards, archived GW8 data and preserved GW7 53/59 records.
Live: https://evmax.ai/ and https://evmax.ai/fpl/gw10/preview/ .
Updated results: https://evmax.ai/fpl/gw9/update/ .
No CI run is configured for this branch push (workflow triggers main/PR only).
IndexNow accepted 763 URLs, HTTP 200. Browser visual QA is not claimed; semantic,
link, exact-byte and retained-evidence checks passed. No delivery blocker remains.

Private inputs, run logs, simulation manifest and QA receipts:
`data/reviews/gw10/2026-11-03-preview/`. Build command:
`python3 scripts/publish_fpl_preview.py --source data/reviews/gw10/2026-11-03-preview --out data/reviews/gw10/2026-11-03-preview/site-preview`.

## Sources

- Official player/events: https://fantasy.premierleague.com/api/bootstrap-static/
- Official fixtures: https://fantasy.premierleague.com/api/fixtures/
- Official player history: `/api/element-summary/{id}/` on the same FPL host.
- Markets: https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard
  for 20261106, 20261107 and 20261108. Raw payloads and SHA256 receipts retained.
- Liverpool return evidence: https://www.liverpoolfc.com/news/match-report-liverpool-arsenal-premier-league-november-2026
- No definitive Saka return date inferred from reporting; current official
  availability is the model input.

## Release evidence

Content commit and deployment are verified above. Private `live-check.json`
contains all 27 URL hashes, response statuses and exact-byte comparisons.
`tests-final.log`, `preservation.json`, `build-final.log` and the raw input receipts
retain the validation trail. Visual browser QA was not completed.

### Preview wording correction, 3 November 2026

Direct live checks at 13:46 UTC confirmed that the GW10 cards promised a
Thursday refresh/final card. No such publication was scheduled. The shared
preview note now says availability and expected minutes may change and retains
the actual FPL deadline; the byline says “provisional preview”. The optional
squad-row copy no longer promises Thursday either. No update was scheduled.

Focused command: `python3 -m unittest tests.test_preview_cards tests.test_fpl_players tests.test_fpl_early_preview` — **131 tests passed**. Site evidence
validation passes. All **2,908 JSON data/evidence files are byte-identical**;
**677 HTML files differ only in the requested wording**. Forecast values and
capture/model timestamps remain unchanged.

Content commit `00bf2cc` is pushed and remote-confirmed. Deployed via the existing
script to https://a0d64443.evmax.pages.dev . **14 live exact-content checks passed
at 13:49:10 UTC**, including Palmer, Bobby Thomas, the player index, MID tiers,
homepage, GW10 preview and their data. The initial restricted fetch returned
HTTP 403; bounded read-only release verification succeeded. No remaining blocker,
FPL account action, new schedule or security configuration change.
Evidence: `data/reviews/gw10/2026-11-03-preview/wording-*.json` and
`wording-tests.log`. The original preview release receipts are retained.

