# Prospective season experiment

Four virtual approaches are registered in `protocol.json`: market, statistical,
hybrid and consensus. No weeks have been enrolled. Forecast provider integration
is still required; registration is not a running model or a performance result.
The two existing published teams retain their separate history.

All four start with the same affordable 15-player seed. The shared policy chooses
a legal XI, captain and vice; subsequent weeks consider at most one transfer with
positive expected gain after hits. Purchases, selling profits, bank and free
transfers carry forward. Chips are disabled. This is a controlled one-week policy,
not a full season optimizer. Human deviations require dated reasons and sources.

## Inputs and operation

Run commands from the repository root. Refresh bootstrap and fixtures using the
existing FPL cache writer so their matching `.meta.json` receipts exist. Each
provider supplies `market.json`, `statistical.json`, `hybrid.json` or
`consensus.json` in a board directory. Each file contains:

- `model_version`, `generated_at`, `trained_through` (UTC timestamps).
- `source_artifact_id`: SHA-256 identifying retained source evidence.
- `bootstrap_sha256` and `fixtures_sha256`, calculated with
  `core.forecast_archive.digest`; fixture context is filtered to the target GW.
- `predictions`: one `{ "player_id": 123, "x_points": 4.2 }` row for **every** player in
  the frozen bootstrap, with finite numbers and unique IDs.
- Optional `interventions`, each containing `reason`, `source`, `recorded_at`.

All providers must use the same context and generate within the registered
30-minute window before capture. Training cutoffs must precede generation.
Do not relabel old forecasts with a fresh timestamp. Source digests identify
evidence; operators must retain that evidence and verify provider provenance.

```sh
python3 scripts/fpl_experiment.py prepare --gw 4 --boards /path/to/boards --out /tmp/submissions.json
python3 scripts/fpl_experiment.py freeze --gw 4 --submissions /tmp/submissions.json
python3 scripts/fpl_experiment.py grade --gw 4 --results /path/to/final-results.json
python3 scripts/fpl_experiment.py report
```

`prepare` creates a reviewable draft. `freeze` must finish before the deadline;
it writes an exclusive, hashed weekly record. Publish its digest through an
independent pre-deadline receipt: a local hash alone does not prove capture time.
Result input contains `gameweek`, `fetched_at`, the matching final `fixtures`, and
official `live.elements` with minutes and points for every forecast player.
Corrections preserve previous grade receipts. Missing outcomes or changed fixture
membership require investigation rather than partial grading.

The site publishes the derived report at `/fpl/experiments/` and
`/api/fpl/experiments.json`. Forecast errors use identical populations and equal
gameweek weighting; squad results include official substitutions and transfer
hits. Model versions and human interventions remain visible. No automatic winner
is selected from a few gameweeks. Rules cannot change within a frozen history;
a changed protocol requires a separately identified experiment.

## Activation work remaining

Connect and validate all four forecast providers, including an explicitly defined
consensus forecast with point predictions. Freeze statistical training and hybrid
weights using earlier data, without FC27 ratings. Do not enroll placeholders or
reconstruct past weeks. Start only when all four can meet the input contract.
