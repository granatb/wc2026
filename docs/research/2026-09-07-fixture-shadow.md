# Receipt-backed fixture shadow — 7 September 2026

The fixture candidate now has a live adapter and a separate rehearsal, freeze and
grading workflow. The four production experiment arms and their squad policy are
unchanged. No model promotion or prospective accuracy gain is claimed.

## Inputs and modeling policy

Collect official `element-summary/{player_id}/` responses for every player in the
same bootstrap used by the production statistical baseline. Retain the raw JSON,
requested URL, player ID, season deadline, retrieval time and payload hash. Three
workers with a per-request delay bound concurrency. Successful individual receipts
are reusable for 24 hours within that season; a failed collection never produces
a complete bundle. Each draft contains all source payloads, models and code hashes.

The adapter verifies population completeness, source freshness, player/fixture
identity, kickoff, scores and finality. Per-fixture totals reconcile to retained
per-GW live results for points, minutes, xG and xA (0.011 tolerance accommodates
published xG/xA precision). The production baseline separately reconciles points
and minutes to bootstrap totals. Lower-GW fixtures must be final and at least
three hours past kickoff before the history receipt and forecast capture.
Historical club identity comes from each fixture, not the player's current club.
Missing zero-minute rows cannot be detected from total reconciliation alone;
registration and historical zero-row coverage remain a limitation.

The historical candidate's shared transform and fixed coefficients produce one
forecast for each target fixture. A double's legs use the same pre-GW player
history, with separate home/away and opponent rates. The live policy clamps each
fixture forecast to zero and applies the same official availability factor as
production. These live adjustments were not evaluated in the historical report.
The production comparator runs its existing transform on the identical bootstrap,
fixture list and per-GW results; it is not a copied forecast from another time.

No-history players copy the production forecast and are explicitly excluded from
the fixture-eligible comparison. A known blank is zero and is evaluated in a
separate cohort. The retained forecasts identify each player's method, per-fixture
features, raw points, adjusted points and comparator points. No FC27 or odds input
is used by the shadow models. The supplied four-provider context may contain odds
and external forecasts as retained source evidence, but neither shadow transform
reads them.

## Lifecycle and commands

The current live rehearsal covers 654 players, all with recorded prior fixtures.
Its mean absolute difference from production is about 0.098 points per player;
this is a prediction difference, not a measured accuracy improvement. It is not
frozen and cannot be graded. The public page labels the dated observation as a
rehearsal. No scheduler has been installed.

In the final 24 hours before the official deadline, refresh the context, collect
histories, rebuild and freeze within 30 minutes of building. GW4's window opens
11 September at 12:30 UTC and closes 12 September at 12:30 UTC. All inputs must
still be at most 24 hours old when frozen. An identical freeze retry returns the
existing receipt, including after the deadline. Another draft cannot replace it.

```sh
python3 scripts/fpl_providers.py refresh --gw 4 --context data/experiments/gw4-context.json
python3 scripts/fpl_fixture_shadow.py collect --context data/experiments/gw4-context.json --out data/experiments/gw4-fixture-history.json
python3 scripts/fpl_fixture_shadow.py build --context data/experiments/gw4-context.json --histories data/experiments/gw4-fixture-history.json --out data/experiments/fixture-shadow/drafts --summary experiments/fpl-2026-27/fixture-shadow-status.json
# Use the exact evidence_path printed by build; do not select a draft by guesswork.
python3 scripts/fpl_fixture_shadow.py freeze --record /absolute/path/to/printed-draft.json --out data/experiments/fixture-shadow/records --summary experiments/fpl-2026-27/fixture-shadow-status.json
```

Freeze replays the retained inputs, verifies all forecasts and writes an atomic,
create-only weekly snapshot with its complete evidence. Commit and publish the
resulting public receipt before the deadline; a local receipt alone is not
independent timestamp evidence. Back up the private `data/experiments/fixture-shadow`
folder separately; public summaries do not replace it. Public status is a dated
snapshot, not a live monitor.

After all target fixtures are final, use retained official results in the existing
`fpl_live.refresh_live` format (`gameweek`, `fetched_at`, `fixtures`, `live.elements`):

```sh
python3 scripts/fpl_fixture_shadow.py grade --record data/experiments/fixture-shadow/records/gw4.json --results /absolute/path/to/final-results.json --out data/experiments/fixture-shadow/grades
```

Grade rejects rehearsals, partial or mismatched fixtures, missing players, duplicate
IDs and future receipts. It reports MAE/RMSE/bias on fixed fixture-eligible,
cold-start and blank cohorts. Full results are retained in content-addressed grade
artifacts; later corrected outcomes produce another artifact without overwriting
the earlier result. Do not replace `fixture-shadow-status.json` with grade output;
it currently describes forecast enrollment only. There is no automatic season
winner selection or cross-week aggregation yet.

## Next evidence gate

Freeze the first comparison in the deadline window and collect outcomes. Then add
version-aware season aggregation and calibration diagnostics before considering a
replacement of a production arm. Multiweek transfers, vice-captain/autosub value
and optimized blend weights remain separate priorities.

Verification: 1,345 tests passed, including nine dedicated shadow/collection tests.
The real 654-player collection and rehearsal passed all identity, time and
reconciliation gates. The public summary was checked against its retained source
artifact; no forecast was frozen outside the enrollment window.
