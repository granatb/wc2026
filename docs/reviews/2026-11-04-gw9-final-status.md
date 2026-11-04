# GW9 final-results reconciliation — 4 November 2026

### GW9 final results, 4 November 2026

Official bootstrap, fixtures and event-9 player results were captured by
**09:51:00 UTC on 4 November**. Event 9 now has `finished=true`,
`data_checked=true`, and `average_entry_score=47`. All ten fixtures are finished.
All 670 live player point totals match the bootstrap event totals. The retained
combined result payload passes `forecast_archive.require_final` with matching
event receipt and digest.

The GW9 landing, results article and `/api/fpl/status.json` now show final,
checked results and the official **47-point average**. Forecast grading remains
unavailable: `grade_gw.load_snapshots(9)` confirms there is neither a frozen GW9
forecast nor committed GW9 projection snapshots. No model-team score, accuracy
metric or actual user-account performance was inferred. GW7's original 53 and
final-selection 59 records remain untouched.

Use `python3 scripts/publish_fpl_status.py --out dist --results-only` for this
kind of results correction. It leaves the homepage, latest-preview metadata,
GW10 article, cards and all predictions unchanged. Do not rerun the dated GW10
preview publisher merely to update results: its retained November 3 status
inputs predate this finality capture.

**22 tests passed** across `tests.test_fpl_status_update`,
`tests.test_fpl_early_preview`, `tests.test_fpl_finality_contract` and
`tests.test_final_selection`; site evidence validation also passed. Exactly four
protected files changed: the three exported GW9 results surfaces and the mutable
editorial status source. The other **3,815 protected files are byte-identical**.

Content commit `badcd3e` (`badcd3e7476f59d3a4ce36957e3bae81d0100214`) is pushed and
remote-confirmed. A transient GitHub internal-server error was resolved with one
retry after checking that the first push had not changed the remote branch.
Deployment: https://51e957bc.evmax.pages.dev . **13 live exact-byte and semantic
checks passed at 09:56:56 UTC**, including production and deployment URLs,
finality/average text, unchanged GW10 data and original GW7 records. IndexNow
accepted 763 URLs (HTTP 200). No CI run is configured for this branch push.

Live results: https://evmax.ai/fpl/gw9/update/ .
Status data: https://evmax.ai/api/fpl/status.json .
Sources: official FPL `/api/bootstrap-static/`, `/api/fixtures/` and
`/api/event/9/live/` at https://fantasy.premierleague.com .
Private receipts, finality proof, tests and live checks:
`data/releases/2026-11-04-gw9-final/`. No delivery blocker remains; the missing
pre-deadline GW9 forecast is an explicit limit on model grading, not on the
verified official-results publication. No account or security changes.
