# Independent FPL audit — completed 13 October 2026

The strongest verified defects are in decision reconciliation, minutes-probability semantics, and evaluation enforcement. The observed squad losses are real, but the available weeks do not establish a generally bad forecasting model or show that missed GW6 changes caused the loss. The original task-local note superseded `fpl_audit_note.md` and treats the earlier retrospective as hypotheses.

## What is verified

Official APIs were recaptured at **11:19 UTC on 13 October**, with `Age: 0`; receipts and raw JSON are in `/Users/bartlomiej.granat/Documents/Codex/2026-10-13/task/official_recheck/`. A separate 12:01 UTC capture confirmed the same provisional flags and average. All ten GW6 fixtures now have `finished=true`. The event still has **`finished=false`, `data_checked=false`**, and its displayed average is now **58**, up from 55 in the earlier capture. Player points are unchanged. The published squads still reconstruct to **Model 41 / Consensus 71**, provisionally. No account access occurred.

| Week | Published model, with autosubs/chip | Published comparator | Official displayed average |
|---|---:|---:|---:|
| GW1 | 44 | 53 | 50 |
| GW2 | 93 | 84 | 81 |
| GW3 | 37 | 59 | 51 |
| GW4 | 76 | 83 | 69 |
| GW5 | 44 | 31 | 48 |
| **Completed GW1–5** | **294** | **310** | **299** |
| GW6, provisional | 41 | 71 | 58, unfinalized |

All squad scores were independently replayed from frozen states or legacy article envelopes using retained official player results. They are website-roster points, not verified user-account totals. GW4 includes five extra points from the model's triple-captain chip; the comparator used its wildcard in GW2. Transfers/hits are not independently reconstructed as a complete account ledger. The field average mixes chips, hits and heterogeneous managers and is contextual rather than a controlled baseline. GW1–5 event flags and averages were confirmed in the fresh official capture.

## Ranked diagnosis

### 1. Portfolio choices missed; the magnitude attributable to model weakness is uncertain

The model entered GW6 forecasting an 8.38-point advantage over the comparator and instead lost by 30. Its raw XI scored 31 against 51.52 projected; Palmer added eight captain points and Le Fée two autosub points. Fernandes was 7.16→1, Szoboszlai 4.68→0, Virgil 3.71→0. The comparator's Calafiori, Mbeumo, Rogers and João Pedro scored 9, 8, 9 and 12.

This is a material selection/ranking failure in this realization. It is not primarily an excess club-stack problem: the model XI has at most two per club, while the comparator has three Arsenal players and several doubles. Persistent differentials and armbands create substantial relative-score risk. No retained joint portfolio distribution justifies a probability or significance claim for the 30-point gap; marginal player histograms cannot establish it.

**Contrary evidence matters:** the model won GW2 and GW5 and was only five points below the summed field averages through the five completed weeks. Bruno's GW2 captaincy scored 46, followed by poor results from the same policy. Frozen full-board forecasts beat archived official `ep_next` on both MAE and RMSE in GW4, GW5 and provisional GW6, including a cohort selected using *prior* average minutes rather than the realized minutes. This rules out explaining the better errors solely by hundreds of zero-minute players. It still does not demonstrate an edge over stronger forecasting systems.

### 2. The published team and recommendation process are not reconciled

The model's 15, XI, bench order, Palmer captain and Szoboszlai vice were identical in GW4–GW6. GW6's own ranking preferred Fernandes within the squad; its frozen best legal XI plus captain, from the same 15, was 60.44 xPts versus 56.74 published. Notes and proposed transfers were refreshed without a single accepted/declined decision receipt binding those choices to publication in the reviewed artifacts. The 9 October handoff explicitly reserved final squad/account actions for the owner; that boundary was legitimate and needed clear presentation when publishing refreshed forecasts. The user separately reports missing account changes; that execution issue cannot be quantified from repository state.

**Do not attribute the GW6 deficit to that inconsistency.** Replaying a deterministic rule that chooses XI/captain entirely from the frozen forecasts, without choosing on actual results, yields model scores **76, 44, 36** for GW4–GW6 versus the published **76, 44, 41**. It would have lost five points in GW6. Palmer's eight also beat Saka's two and Fernandes's one. An unavailable reserve keeper is an uncovered risk, but Raya played in all three weeks, so it cost no observed points. Holding an unavailable reserve can be legal and can be an opportunity-cost decision; its replacement is not automatically the highest-priority transfer.

The transfer engine is explicitly a single-swap discounted legal-XI-plus-captain evaluator, with sale-profit and club/budget constraints. It excludes autosub/vice value, banked-transfer option value, joint multi-transfer plans and chip timing. Historical notes record that the GW4 two-transfer route needed manual discovery. These are limits to the decision method, not evidence that a new optimizer would have won GW6.

### 3. Start-probability labels and the actual simulation are measurably inconsistent

The published `start_prob` is the research-adjusted input to the sampler. `core/engine_events.py::_intervals` then caps outfield starters at ten and chooses one goalkeeper if several were sampled. Those operations change the marginal probability of starting. Frozen GW6 priors replayed through the unchanged sampler for 20,000 draws per club give:

| Player | Published start probability | Actual sampler frequency |
|---|---:|---:|
| Cole Palmer | 75.0% | 69.9% |
| Raya | 99.7% | 94.8% |
| Thiago | 99.7% | 94.0% |
| Donnarumma | 99.5% | 90.1% |

These differences are far larger than Monte Carlo sampling error. Unknown reserve keepers receive a generic 25% input prior and can displace established starters in the selection step. Outfield caps also reduce probabilities. This is a verified inconsistency between the advertised probability, the minutes-floor gate and the simulation actually generating xPts; the code itself calls its start marginals approximate. It is not yet a measured estimate of lost FPL points. Raising all forecasts or retuning on GW6 would not follow from this check.

Szoboszlai's 0.90 input was also a real appearance miss, but the frozen 9 October note cited available official status, five starts/440 minutes and no injury news. The earliest reliable public injury warning remains unverified. GW6 sources were checked around 14:12 Friday, about 20 hours before the Saturday deadline, with final expert selections still pending. That leaves a news coverage window; it does not prove an avoidable missed warning.

### 4. The evaluation safeguards and product narrative are weaker than their descriptions

**Reproduced guard defect:** `core/forecast_archive.py::require_final` accepts the fresh GW6 snapshot because it checks fixtures and player rows, but never event `finished` or `data_checked`. `refresh_live` does not fetch those event flags. The earlier report's rejected snapshot tested only the fixture branch. No grade was written by this audit. This is an immediate measurement-integrity fix, with no claimed historical point cost.

**Comparator mismatch:** the registered comparator is the ownership template constructed at GW2; its 15 and XI remain unchanged in GW4–GW6. Published GW6 copy still describes an expert mention tally and majority captain. Both squads are valued by the same forecasting engine. Their score gap cannot measure whose minutes information is better or be presented as the current experts' recommendations.

**Stronger benchmarks temper the reassuring `ep_next` result.** Independently reproduced retained common-population scores:

| Frozen benchmark | Common players | evmax RMSE | FFIQ RMSE | `ep_next` RMSE | Simple points/appearance RMSE |
|---|---:|---:|---:|---:|---:|
| GW3 | 343 | 2.791 | **2.629** | 3.163 | 3.342 |
| GW4 | 387 | 2.797 | **2.726** | 2.940 | 3.170 |
| GW5 | 406 | **2.761** | 2.766 | 2.876 | 3.144 |

FFIQ wins two weeks and is essentially tied in the third. The two naive baselines are identical this early because each player has at most four previous appearances; the code's “last4” is **last four played appearances**, not four calendar gameweeks including DNPs. GW3's benchmark is an earlier horizon vintage, not its latest published article forecast; GW4's benchmark also predates the final publication refresh. This table compares exactly the frozen benchmark vintages on matching populations. No GW6 external or four-arm comparison was frozen. The separate controlled four-arm experiment has only GW4 graded and a GW5 gap, so there is no persuasive prospective season experiment yet.

## Further checks and uncertainty

- **Identity/freshness:** GW4–6 archives pass their own hash and predeadline checks. GW6 odds are timestamped 14:08 UTC, bootstrap 14:08:50, forecast 14:27:19, deadline next day 10:00. State joins use IDs, including Cole Palmer 154. No active GW6 stale-odds or wrong-Palmer defect was found. GW1–3 have only article-union forecasts for the published model (58/64/63 rows), plus the separate GW3 benchmark; no full-board series should be invented.
- **Calibration and ranking:** for the predeadline prior-60-minute cohort, model/`ep_next` RMSE is 3.455/3.650 in GW4 (185 players), 3.422/3.636 in GW5 (179), and provisional 2.845/3.533 in GW6 (172). Top-15 model-ranked players outperform top-15 `ep_next` in GW4 and GW6 and underperform in GW5. Cohort choice and model versions vary; this is diagnosis, not a significance test or a model-promotion result.
- **Future horizon:** GW6–7 used odds, GW8–10 strength estimates. Current availability is propagated without recovery forecasts. The quoted Palmer→Saka +13.03 is a five-week model estimate, not a predicted or proven GW6 points gain. Separate recommendations cannot simply be added.
- **Causality:** no finality bug, prose mismatch or keeper-cover concern explains the observed 30-point gap by itself. Joint minutes modeling, attacking allocation and benchmark superiority remain research questions. Actual user holdings, accepted changes and execution cost are unknown.

## Five bounded actions before GW7, with acceptance criteria

1. **Fix finality enforcement and labels.** Require a fresh, hashed event receipt alongside all final fixtures, with both event flags true, before banking a final grade or settled field-average comparison. Acceptance: today's retained snapshot is rejected; a genuinely checked final snapshot passes; previous captures remain retained. Align comparator copy with its actual policy.
2. **Create one decision receipt and execution check.** Record legal squad, XI, bench, armbands, bank, selling prices, FTs/hits/chips, alternatives accepted/declined and a timestamp. Assign an owner and time for the final news pass before the verified GW7 deadline (17 October, 10:00 UTC). Acceptance: published state matches the accepted receipt; separate user confirmation establishes account submission. An owner-approved hold is valid.
3. **Make minutes probabilities internally coherent.** First expose the actual simulated start frequency or accurately rename the input prior; test the minutes-floor gate against the intended probability. Shadow a mutually exclusive keeper/lineup allocation candidate without replacing production. Acceptance: displayed probability agrees with empirical sampler frequency within stated Monte Carlo tolerance, no multiple keepers or more than ten outfield starters, and cold-start reserves do not silently reduce the reported established-starter probability.
4. **Review the current 15 and bounded transfer alternatives.** Compare hold, best legal XI/armband, top single moves and a small set of affordable two-move routes using fresh inputs. Explicitly price unavailable cover, FTs, sale profits, captain/vice and chip assumptions; label omitted option value. Acceptance: every proposal is legally affordable and its forecast gain has a documented baseline; do not claim global optimality or force an inferior keeper transfer to clear a checklist.
5. **Resume existing frozen evaluation, rather than tune against GW6.** Freeze the existing provider comparison and simple baselines before deadline, with matching population/context, source retention and a declared policy. Track RMSE, prior-minutes calibration, selected-squad ranking and net portfolio points separately. Acceptance: complete GW7 receipts before lock and replayable post-finality grading; no model promotion from this small mixed-vintage sample. Review again after a prespecified block of future weeks.

## Reproduction and repository state

From this task directory:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 audit_deep.py
python3 audit_fpl.py
```

`audit_deep.py` reads the retained `official_recheck` snapshot, reproduces all six published squad scores, stronger benchmarks, predeadline cohorts, deterministic frozen-rule lineups and the minutes-sampler mismatch. It writes only `audit_deep_results.json` in task scratch. `audit_fpl.py` preserves reproduction against the earlier 08:48 capture. `capture_fpl_official.py` is the separate read-only API recapture command; avoid rerunning it if preserving the exact 11:19 evidence is required. Raw external projection payloads are not copied into the report.

Audited HEAD: `1a62e47317e9b9fdc3d1cc307cac802aec7d50f2`, branch `chore/gw6-thursday`, clean and two commits ahead. The lineup sampler was last changed in `733b73e` on 7 September, before the audited forecasts. Bounded grading tests: 41 passed in the initial pass. No forecasting logic, historical output, account, Git commit, push or deployment was changed.


## Implementation follow-up

Bounded local fixes and verification are documented in [the fix note](2026-10-13-fpl-audit-fixes.md). The findings above describe the pre-fix audit. Its scripts and retained evidence are in `/Users/bartlomiej.granat/Documents/Codex/2026-10-13/task/`; all original protected repository evidence is unchanged.
