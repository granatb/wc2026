# Retained joint engine samples — 7 September 2026

The lineup optimizer now consumes aligned appearance-and-points draws from the
actual market event engine. This replaces assumed independence and constant
conditional points for this market-model rehearsal. It does not produce joint
distributions for the statistical, hybrid or external forecast arms.

## Retention and consistency

The existing points accumulator already sums all fixtures at each simulation
index. Its optional joint export now retains both weekly points and whether the
player appeared in any fixture at that index. Presence in the accumulator, not
a nonzero point total, identifies appearance. This preserves zero-point cameos,
negative scores and double-gameweek appearance unions. Known blanks are explicit
all-zero points/all-false appearance arrays at the provider boundary.

The optional retention path consumes no random draws and bypasses the public
marginal cache. Normal artifacts contain no joint samples. Default seed 12345
and scoring are unchanged; an explicit alternate seed supports the audit and is
included in the cache key. Tests verify retained histograms and means against
normal artifacts, double aggregation and cache isolation. On the real GW4 inputs,
all 654 market forecast values exactly matched the pre-change baseline.

Decoder validation requires exact squad coverage, unique IDs, equal column
lengths, integer points, boolean appearances, DNP consistency and equality between
rounded sample means and published forecast means. Draw indices are never shuffled
between players. Raw vectors remain private in a content-addressed bundle with
the full provider source, audit inputs, seeds, models and code identities. Public
research exposes only derived diagnostics and results.

The provider/model source hashes change because the implementation changed;
existing experimental identity tracking detects this. No frozen history is
rewritten, and the first four-arm enrollment remains pending.

## Current-squad experiment

Use 5,000 engine draws with seed 12345 to select among all legal XI/bench orders
and captain/vice pairs. The baseline applies the existing mean policy to those
same market forecasts. Audit both fixed decisions on 5,000 fresh engine draws
with seed 12346. No audit-based retuning was performed.

The candidate starts Ndiaye instead of N. Williams. Both captain Szoboszlai and
vice-captain Thiago. The candidate audit expectation is 59.2466 points versus
59.2644 for the baseline: **-0.0178 points**. These are simulated weekly totals,
not observed results or a forecast of guaranteed squad performance.

Paired Monte Carlo standard error is 0.03064; the approximate normal 95% interval
for the simulated difference is [-0.07785, +0.04225]. This describes sampling
precision conditional on this engine. It does not measure model misspecification,
real-world performance uncertainty or confidence in winning next season. The
small difference provides no reason to replace the controlled decision policy.

## What this does and does not validate

Alignment and reproducibility are validated. Football calibration is not.
Within-fixture lineup, score, event allocation and bonus dependencies now come
from the engine's own draws. Availability and between-fixture dependence retain
the engine's assumptions; retaining them does not make those assumptions true.
We still need prospective appearance calibration, point-distribution scoring and
conditional lineup-value evaluation over multiple gameweeks.

This is an offline decision rehearsal, not a fifth arm, a frozen squad or an
intervention in the four-arm experiment. Transfers, chips and multiweek option
value are not part of the objective. The earlier constant-conditional-point
sensitivity study remains separately visible as historical research.

## Reproduce

Fresh pre-deadline run:

```sh
python3 scripts/fpl_joint_lineup.py --context data/experiments/gw4-context.json --out docs/research/2026-09-07-joint-lineup.json
```

The command prints the complete private bundle path. This dated run retained:

```text
data/experiments/joint-lineup/8f9801727c28b263ebc57744ec05d6506c37ea27c892d9aae62e7093d6355a51.json
```

Offline replay (works after source freshness expires, because it analyzes retained
samples rather than creating new forecasts):

```sh
python3 scripts/fpl_joint_lineup.py --replay data/experiments/joint-lineup/8f9801727c28b263ebc57744ec05d6506c37ea27c892d9aae62e7093d6355a51.json --out /tmp/joint-replay.json
python3 -m unittest discover -s tests -p 'test_joint_scenarios.py'
```

Replay exactly reproduced the retained report. A later analysis implementation
has its own code hashes in the output; preserve earlier reports instead of
silently replacing them. Source and audit bundles must be backed up privately;
the public summary cannot reconstruct joint draws. Local hashes are not
independent proof of capture time.

Next: freeze the first eligible weekly comparison and collect final outcomes;
use retained model distributions to measure calibration before any policy
promotion. No scheduler or early enrollment was created in this batch.

Verification: 1,360 tests passed, including six joint-sample regression tests.
All 654 real market forecast values matched the pre-change baseline, retained
means matched their forecasts, and offline replay reproduced the report exactly.
