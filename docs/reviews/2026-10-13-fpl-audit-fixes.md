# FPL audit fixes — 13 October 2026

## Scope and outcome

Local fixes on `chore/gw6-thursday`, starting at `1a62e47317e9b9fdc3d1cc307cac802aec7d50f2`. Forecasting, scoring, lineup sampling and transfer ranking logic are unchanged. No account was accessed, no transfer made, no real GW7 decision accepted, and nothing pushed or published. The independent diagnosis is in [the audit note](2026-10-13-independent-fpl-audit.md).

Official read-only recheck at **12:01 UTC**: GW6 has all ten fixtures finished but event `finished=false`, `data_checked=false`; field average 58. Published roster results remain provisional. No GW6 final grade was banked.

## Delivered fixes and acceptance evidence

| Fix | Contract | Evidence |
|---|---|---|
| Finality | New grades require the matching official event, both finality flags, and a hash-bound event receipt. Refresh reads event status without replacing forecast bootstrap inputs. | `tests/test_fpl_finality_contract.py`; incomplete/missing/wrong/tampered event evidence fails; a checked event passes. |
| Historical compatibility | Existing experiment grades replay under their original fixture-level evidence; they are named in `legacy_finality_gameweeks` and cannot be newly banked through the legacy path. | Real retained GW4 grade replay regression; no historical file changed. |
| Start-value semantics | `start_prob` remains the sampling input. UI and dataset glossary explain that lineup constraints can reduce realized simulated start frequency. | Presentation regression; archived payload values remain byte-for-byte unchanged. |
| Comparator truth | Future prose takes construction from the recorded state and identifies shared forecast/minutes modeling. GW2–6 rendered prose gets a dated ownership-template correction. | `tests/test_fpl_audit_presentation.py`, frozen-build tests. Numeric/API envelopes and original archived prose remain unchanged. |
| Decision reconciliation | GW7+ production builds require an immutable reviewed proposal matching exact forecast context and validated squad roles before site/snapshot writes. Site validation checks the receipt against frozen forecast context and published squads. | `tests/test_fpl_decision.py`; rejects missing acceptance, captain/bench/bank/forecast drift, late acceptance and mismatched publication. Integer-keyed live PMFs match serialized archive hashes. |
| Fair review alternatives | Proposal shows selected-XI versus best legal current-XI mean; affordable single swaps compare best XI on both sides, using recorded funds, prices and the existing sale-profit rule. Missing bank is explicitly unavailable. | Existing transfer tests plus accepted-decision regression. This is a one-week review aid, not a new transfer policy. |

Account submission remains `unverified` in a separate field. Acceptance of a website roster does not establish that the user's account was changed.

## GW7 operator procedure

1. Refresh and research using the existing workflow, then create a **dry build outside `dist`** with the intended simulation count. Its root contains `fpl-decision-gw7.json`.
2. Review the exact 15, XI, captain, vice, ordered bench, chip, bank, free transfers, input context and one-week alternatives. Update the state if necessary, then rebuild the proposal. Transfer alternatives exclude autosubs, vice option value and future weeks; the existing horizon analysis remains necessary for transfer decisions.
3. Only after a human/operator decision, record acceptance using the displayed `proposal_id`:

   ```sh
   python3 scripts/fpl_decision.py --proposal /path/to/dry-output/fpl-decision-gw7.json --accept-id REVIEWED_SHA256 --operator OPERATOR --rationale 'Reason for the selected squad, captain, bench and hold/transfer choice'
   ```

   This creates `games/fpl/decisions/gw7/<proposal_id>.json` exclusively. It never overwrites an earlier acceptance. It does not send anything or make account changes.
4. A later authorized production build must use the same inputs and simulation count. Changing any bound forecast or state requires a new review. The deployment validator requires the public receipt to match the frozen one and its forecast context.
5. Account execution is a separate user action. Do not infer it from an accepted publication receipt.

No GW7 build, acceptance or publishing has been performed as part of these fixes.

## Local implementation commits

- `b2f1c8c`: checked-event finality and legacy replay.
- `84c2f1d`: reviewed publication decisions and truthful method labels.

## Verification

- Full offline suite: **1,430 tests passed, five existing skips**. Test network calls were blocked. The first sandbox-only baseline run had eight filesystem permission errors; the authorized local-access run passed.
- Local GW1–6 rebuild, including all 667 GW6 player pages, passed `scripts/validate_site.py`. `load_gameweek` and `build_artifact` were patched to raise if a historical rebuild attempted simulation.
- All **335 protected pre-existing files** matched their SHA-256 manifest: forecasts, projections, scores, benchmark files, corrections, experiment records, research, FPL data and both current state files.
- Independent review found a forecast-context validator gap; fixed and re-reviewed. Reviewer verified dry → accept → production agreement and rejection of changes to rows, matches, simulation count, bootstrap, fixtures, odds and source fingerprint.
- Bounded archived replay after fixes exactly matches prior squad scores, benchmark metrics, full-board metrics, frozen-rule lineups and minutes-sampler results. Only the finality guard result changed.
- Reproduction: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. python3 -m unittest discover -s tests`; targeted tests named above; `python3 scripts/validate_site.py --out PATH_TO_LOCAL_BUILD`.

Task-local logs and raw API evidence: `/Users/bartlomiej.granat/Documents/Codex/2026-10-13/task/` (`fixes-full-suite.log`, `fixes-site.log`, `fixes-protected-before.json`, `official_final_recheck/`, `audit_deep_results.json`, `audit_deep_after_fixes.json`). The audit scripts write only into that task directory.

## Still uncertain; next bounded experiments

- **Joint minutes calibration:** labels are repaired; the sampler itself is unchanged. Before changing it, compare frozen input start priors, realized simulation start frequencies and subsequent actual starts on predeclared cohorts. Accept a replacement only on held-out weeks and preserve original forecasts.
- **Model edge:** completed GW1–5 totals and the stronger frozen benchmarks do not establish superiority. Freeze prospective comparators on the same population, vintage and policy before each deadline; retain every gap. Do not fill missing GW6 predictions retrospectively or select hindsight squads as evidence.
- **Late news:** existing 24-hour input freshness gate remains. Record a final predeadline news check and why a hold/transfer was accepted; test whether it changes decision quality prospectively.
- **User execution:** actual account holdings, accepted GW6 changes and missed-change cost remain unknown. No account access was available.
