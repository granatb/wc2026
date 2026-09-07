# Autosubstitution and vice-captain decision value — 7 September 2026

Decision: retain the current four-arm policy. The new finite-scenario optimizer
supports the same GW4 lineup choices under both tested appearance assumptions.
This is a useful negative finding: adding a more complete objective does not
justify changing this squad merely to demonstrate activity.

## Delivered

`games/fpl/lineup_decisions.py` accepts a complete 15-player squad and weighted
joint scenarios with explicit appearance flags and points. It enumerates 550
legal XIs × six outfield bench orders = 3,300 combinations. Goalkeeper bench
position is presentation-only. Every eligible captain/vice pair is evaluated
through its conditional bonus. Identical appearance patterns are grouped with
their probability-weighted point totals, preserving correlations and expectations.
The solution is exact for those supplied finite scenarios up to numerical ties.

Each scenario scores XI points, legal bench replacements, captain bonus and vice
fallback separately. A substitute never inherits the armband. A zero-point cameo
is still an appearance; negative points do not imply a DNP. A missing goalkeeper
can be replaced only by the reserve goalkeeper. Outfield replacements follow
bench order and formation minima/maxima. Tests compare 100 deterministic random
outcomes with the existing finalized FPL grader, as well as targeted edge cases.
Scenarios with points for a non-appearing player are refused: such disciplinary
edge cases require an explicitly extended playing-eligibility model.

The optimizer takes joint scenarios as inputs and does not itself assume player
independence. It does not make transfers, use chips, freeze a squad or change the
experiment policy. Its outputs can support a future versioned decision policy
once the scenario inputs are validated.

## Current-squad rehearsal

Use the same Model XI seed squad and retained 654-player source artifact as the
fixture shadow. Rebuild both production statistical and fixture forecasts against
those retained official inputs, with freshness/deadline checks. No odds or FC27
inputs enter either statistical forecast.

The current boards provide means, not complete joint appearance-and-points
samples. For this rehearsal only, approximate appearance marginals using raw
production start/cameo priors and aggregate across scheduled fixtures. These are
not the engine's simulated team-lineup probabilities. Zero-start unavailable
players are assigned zero appearance probability. Conditional points are fixed
at forecast mean divided by appearance probability, preserving the mean in the
underlying assumed distribution. Finite sampled means can differ.

Two prespecified cases share these marginal probabilities:

- Independent player appearance draws.
- A shared uniform draw within each club, an extreme dependence sensitivity case.

Choose the lineup on 256 weighted scenarios (seed 20260907), then audit both
candidate and baseline on 4,096 fresh scenarios (seed 20260908). Both decisions
see the same audit draws. The audit reduces scenario-selection optimism; it does
not validate these football assumptions. No tuning followed the audit.

| Point forecast | Appearance case | Audit candidate minus baseline |
|---|---|---:|
| Production statistical | Independent | 0.000 |
| Production statistical | Shared club | 0.000 |
| Fixture challenger | Independent | 0.000 |
| Fixture challenger | Shared club | 0.000 |

All four comparisons choose the same XI membership, outfield bench order and
captain/vice as the mean-based baseline. Display ordering within the XI and the
reserve goalkeeper's bench slot differ, with no effect on these choices. Both
forecasts captain B. Fernandes; production vice-captains Gibbs-White and the
fixture forecast vice-captains Szoboszlai. These are decision rehearsals for the
seed squad, not instructions sent to an official FPL account.

The scenario objective still matters: targeted tests demonstrate that the best
vice need not have the second-highest mean when his appearances coincide with
the captain's. Bench option value can exist even if it does not change the
optimal decision for this particular squad.

## Limits and next steps

We have not established improved real-world squad points. Constant conditional
points omit role/points dependence; correlations across opponents and fixtures
are not modeled realistically. The raw minutes priors are not calibrated joint
scenarios, and the separate minutes research candidate remains unpromoted.
The public table is a simulation diagnostic, not part of prospective standings.

Next, retain joint per-simulation appearance and point outputs from the event
engine, validate their calibration and dependence, and replay this optimizer on
those inputs. Then compare a versioned policy prospectively. Banked-transfer
option value, multiweek moves and chips remain outstanding; they should not be
bolted onto an unvalidated weekly objective.

## Reproduction and rule sources

```sh
python3 -m unittest discover -s tests -p 'test_lineup_decisions.py'
python3 scripts/fpl_lineup_rehearsal.py --source data/experiments/fixture-shadow/drafts/f39a4bc0cfe6a78f35edb026d456911a4018c0b6e69464b7fcc6cf8a91cbccd3.json --out docs/research/2026-09-07-lineup-rehearsal.json
```

The dated JSON stores candidate/baseline decisions, component expectations,
separate-seed audit results, appearance assumptions, seeds, source hash and code
hashes. The private source artifact must remain backed up; rerunning after its
freshness window must refuse publication and use newly refreshed inputs instead.
No old experiment forecast is rewritten.

Official sources checked for current captain/vice, bench priority and formation
semantics: [FPL basics: managing your team](https://www.premierleague.com/en/news/2174899/fpl-basics-managing-your-team)
and [FPL FAQ](https://www.premierleague.com/en/news/4661030).

Verification: 1,354 tests passed, including nine lineup-specific tests and
100 deterministic scenario comparisons with the finalized grader. The retained
rehearsal checksum and public rendering were checked. No experimental records,
production forecasts or squad instructions were changed.
