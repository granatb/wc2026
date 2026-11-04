# GW8–9 comparison recovery

### GW8–9 comparison recovery published, 4 November 2026

This supersedes the earlier blanket statement that neither week had anything
to grade. The 21 October GW8 early player forecast and chosen team survived;
their SHA-256 hashes match the retained pre-deadline live publication receipt.
The ordinary grader did not discover preview archives. The 23 October final
refresh stopped on an ESPN tunnel 403, before a new simulation/publication.
No final GW8 deadline team or published GW9 model selection is inferred.

The owner authorized public account scores **GW8 42 / GW9 69**, with zero
transfers, and asked to assume the consensus remained stable. Public rows now
show **GW8 early model 42 (projected 64.10), consensus 32, account 42** and
**GW9 model unavailable, consensus 36, account 69**. The account scores are
owner-supplied Points-screen evidence, not model scores or fetched account data.
The matching GW8 model/account totals do not establish identical teams.

Consensus uses the exact **published GW7 archive selection of 14 October**,
not the older raw `state_consensus.json` template. XI: Raya; Calafiori,
O'Reilly, Guéhi; Szoboszlai, Mbeumo, Rogers, Slater; Haaland (C), João Pedro,
Calvert-Lewin (VC). Reserve GK Kinsky; outfield bench Shaw, Diop, Tzolis.
No transfers, hits or active chips. GW8: Diop replaces O'Reilly. GW9: Diop
replaces João Pedro, Tzolis replaces Guéhi. Both have Haaland captain.
GW8 early model: De Cuyper replaces Saka; Palmer inherits captaincy, doubling
his -1 to -2. All 668 early player projections are graded, MAE **1.172**.

Official bootstrap, fixtures and live event 8/9 feeds were refreshed by
**2026-11-04T13:26:22.309803+00:00**. Both events are finished and data checked;
all ten fixtures in each are final. Field averages **45 / 47** are separate
context, never substituted for consensus. Result records are explicitly dated
4 November. The original frozen-forecast accuracy series and duel **2–5** stay
unchanged; reconstructed comparisons are excluded from that tally.

Code/content commit **73969ffaf8b41f5e3e63a05a4340f5cea2f2b750** is pushed and
remote-verified on `chore/gw6-thursday`. Deployed through the existing script to
<https://eb1882e5.evmax.pages.dev>. **1,458-test suite passed (5 skipped)**;
site evidence checks passed. **17 exact-byte and semantic live checks passed
at 13:36:57 UTC**; local and live desktop screenshots were inspected. All
original JSON and historical/GW10 forecast values are unchanged. Eight existing
export files changed, plus the comparison API and review page. IndexNow 764
URLs, HTTP 200. No CI run is configured for this branch push.

Live: <https://evmax.ai/> · <https://evmax.ai/fpl/gw8-9/review/> ·
<https://evmax.ai/api/fpl/comparisons/gw8-gw9.json>.
Versioned recovery: `games/fpl/continuity.py`,
`evmax/assets/comparisons/gw8-gw9.json`, and the unchanged recovered preview
bytes under `evmax/assets/previews/gw8/2026-10-21.json`.
Reproduction: `python3 scripts/publish_fpl_continuity.py --source
data/releases/2026-11-04-continuity --out dist` (do not rerun model forecasts).
Private capture, logs, preservation receipt, live checks and visual proof are
in `data/releases/2026-11-04-continuity/`. No FPL account or security changes;
unrelated edits preserved. No release blockers. GW10 navigation was not moved.

## Validation scope

Seven new tests cover missing-model display, separate account results, captain
fallback with negative points, formation-legal automatic substitutions, correct
published consensus selection, finality and completeness failures, provenance
hash/time tampering, and exclusion from the original duel. The publication gate
replays the record and compares the exported comparison JSON before deployment.

The two recorded October 21 evidence hashes are:

- Players: `0576862d9f2d44e85ed5bc39e3a85792154ad884963afb6b0832153eeca87988`
- Plan: `2671c0787ffd6844c26940aa6a92b77acb17f83e1def5218af03ac4d51425bd8`

Neither GW8 early forecasts nor reconstructed consensus results are represented
as a final pre-deadline freeze. A GW9 research horizon existed privately on
October 21; it is not substituted for a published GW9 selection.
