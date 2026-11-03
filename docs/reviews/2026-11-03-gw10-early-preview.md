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

Validation: 1,444 tests passed, five existing skips; local article is distinct
from the homepage; key local links resolve; original historical evidence is
unchanged (397 protected files; only the intentionally mutable GW9 status source
changed). Publication is pending in this checkpoint; see the release review for
remote/deployment and live verification evidence. No security configuration or
FPL account action is involved.

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

Pending push, deployment and live verification. Visual browser QA has not been
completed; local semantic, link, artifact and history checks passed.
