# Homepage restoration — 4 November 2026

The November 3 custom preview publisher omitted the regular homepage's
`duel_history` and `fixtures` inputs. Its single-week cards also failed to use
the available current projection when no multiweek horizon was present. This
hid the evaluation ledger, fixture sidebar and GW10 forecast dots/opponents;
the November 4 GW9 final-results correction did not cause the omissions.

Restored the canonical GW1–7 evaluation table (GW7 final selection **59**, projected
**61.80**), all ten GW10 fixtures, and each card's approved GW10 projection and
opponent. No GW8/GW9 model grades or GW11+ predictions were invented. Existing
forecast/data JSON files and GW9 final pages remain byte-identical. Fixture
schedule refreshed **2026-11-04T10:27:59.655613+00:00**; retained match forecasts
remain dated **2026-11-03T10:23:45.360062+00:00**.

The regular early-preview publisher now retains these sections. For a bounded
presentation restoration from retained artifacts, use
`scripts/restore_fpl_homepage.py`; it does not rerun the forecast or roll back
newer GW9 results. Fresh fixture receipts are retained separately in
`evmax/assets/editorial/fpl-gw10/fixtures.json` and published at
`/api/fpl/fixtures/gw10.json`.

**1,451 tests passed, 5 skipped**; site evidence validation passed. Content commit
`d0647390b12e584233782e5a2122a45e756bcf18` was pushed and remote-verified on
`chore/gw6-thursday`, then deployed to <https://4a06fefc.evmax.pages.dev>.
**18 live checks passed at 10:37:01 UTC**, comparing exact response bytes and
semantic content. Local and production desktop screenshots were inspected.
The user's Library screenshot was materialized and inspected successfully.
Live: <https://evmax.ai/> and <https://evmax.ai/fpl/gw10/>.

Evidence: `data/releases/2026-11-04-homepage-restore/` (private, ignored), including
`validation.json`, `tests.log`, `live-check.json`, `live-desktop.jpg` and
`live-cards.jpg`. Keep Library transfer credentials private. No account actions,
security changes, new schedule or unrelated edits. No release blockers.

## Regression coverage

`tests/test_fpl_homepage_restore.py` checks the history-only table, retained
fixture rail, current-week forecast fallback, absence of a fabricated live
score, and fixture identity/forecast preservation. Two player-card assertions
were updated to require the valid current projection instead of an empty
timeline. The full unittest discovery suite passed.

The restoration changed 672 existing HTML files (670 player pages and two
landing pages) and added the fixture schedule API. The original 3,819-file
protected baseline was checked for forecast/data and GW9 preservation.

GitHub Actions has no run for this branch: the repository workflow triggers
main pushes and pull requests. Local full-suite and live deployment checks
provide the validation evidence for this release.
