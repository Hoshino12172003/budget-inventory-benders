# E4 Gamma sensitivity: final scientific interpretation

## Audit status

`E4_FINAL_AUDIT_PASS`.

The frozen E4 result root contains exactly 40 unique conditions: eight Renault
cases crossed with `Gamma = 0, 1, 2, 3, 4`. Every condition is `OPTIMAL`, every
condition has `CERTIFIED_PRB_EXACT` certification, all stored result and
first-stage-solution hashes match their provenance, and all dataset and
calibration identities match the frozen E4 manifest. The eight `Gamma=2`
conditions reproduce their E3-B100 source artifacts with exact solution hashes
and economic values. All 120 primary files also match the frozen
`e4_gamma_sensitivity_v1.zip` archive byte for byte.

No first-stage problem was solved during this final audit. The only optimization
work was 64 product-risk LP solves used in two fixed-first-stage audit attempts
for 210330/G3. No primary E1, E2, E3, or E4 artifact was overwritten.

## Aggregate response to Gamma

All normalized quantities use the same case's `Gamma=0` result as one. The
material-reconfiguration threshold is the frozen reporting tolerance `1e-6`.

| Gamma | Mean normalized objective | Mean normalized recourse | Mean RI | Median RI | Material cases | Mean runtime (s) | Mean iterations | Mean cuts |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0 | 0.097 | 5.000 | 13.250 |
| 1 | 1.0570 | 1.0645 | 0.0177 | 0.0000 | 2 | 0.286 | 5.000 | 21.750 |
| 2 | 1.0858 | 1.0971 | 0.0410 | 0.0197 | 4 | 1.278 | 4.625 | 32.500 |
| 3 | 1.1102 | 1.1246 | 0.0711 | 0.0522 | 4 | 4.202 | 4.500 | 44.125 |
| 4 | 1.1322 | 1.1495 | 0.1245 | 0.1546 | 5 | 12.089 | 5.125 | 56.750 |

The mean objective and mean robust recourse rise with Gamma throughout the
tested grid. This is consistent with increasing economic exposure as the
uncertainty set admits more simultaneous adverse demand components. It is an
empirical result for these cases, not a claim about every possible instance.

Mean RI also rises from numerical zero at `Gamma=0` to `0.1245` at `Gamma=4`.
For every case, RI is weakly nondecreasing within the frozen `1e-6` reporting
tolerance. The number of materially reconfiguring cases rises from zero to two,
four, four, and five. The individual trajectories show that the aggregate
increase does not imply a common response threshold.

## Network-specific risk thresholds

| Case | First material Gamma | RI at first material Gamma | RI at Gamma=4 |
|---|---:|---:|---:|
| 210129 | 1 | 0.0684 | 0.1684 |
| 210202 | 1 | 0.0733 | 0.1552 |
| 210323 | 2 | 0.0394 | 0.2554 |
| 210330 | 2 | 0.0652 | 0.1540 |
| 210310 | 4 | 0.2633 | 0.2633 |
| 210428 | none through 4 | — | numerical zero |
| 210611 | none through 4 | — | numerical zero |
| 210628 | none through 4 | — | numerical zero |

These thresholds demonstrate heterogeneous inventory responses. Two networks
react immediately at `Gamma=1`, two begin at `Gamma=2`, one waits until
`Gamma=4`, and three retain their baseline inventory through the tested range.
The finding is descriptive and conditional on the frozen model, budget, and
parameter values.

## Inventory adjustment rather than network redesign

The active-depot set is unchanged across Gamma for all eight cases. Its mean
count is `2.625` at every Gamma, and none of the 15 material
case-Gamma observations records an opening or closure. In this experiment,
adaptation therefore occurs through inventory-level reconfiguration rather
than depot activation changes. This does not imply that depot changes cannot
occur under other budgets, costs, or uncertainty ranges.

Budget utilization remains numerically one for every aggregate Gamma level.
Mean total adjustment grows from numerical zero to `74.9941` units, while mean
RS grows from numerical zero to `0.004016`. The tables retain the raw persisted
floating-point values; values below `1e-6` are classified as numerical zero but
are not rewritten in the primary artifacts.

## 210330/G3 global-coupling diagnostic

The stored `global_coupling_pass=false` is classified as
`NUMERICAL_DIAGNOSTIC_TOLERANCE_ISSUE`, corresponding to the previously frozen
`DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH` contract.

The diagnostic is the absolute difference between final master `theta` and the
final-iteration exact product-wise composition, with threshold `1e-6`. The
persisted master-bound closure residual is `1.6398262232542038e-6`. A fresh
fixed-first-stage product-wise certification gives exactly
`609248.4624229416`, identical to the stored robust recourse. Its risk allocation
is `(0,0,0,0,0,0,2,1)`, sums to `3`, and is feasible for `Gamma=3`. The maximum
product strong-duality error is `5.820766091346741e-11`; all product duals are
feasible. Reconstructed and reported objectives both equal
`674898.8098508997`.

The diagnostic residual does not affect the objective, exact robust recourse,
Gamma feasibility, or first-stage feasibility. It is not a stale-field or true
certification failure, and the frozen threshold remains unchanged.

## Reused Gamma=2 diagnostic schema

The eight reused Gamma=2 result JSON files do not contain the newer
`global_coupling_pass` field because their E3-B100 source schema predates that
field. This is classified as
`MISSING_BY_REUSE_SCHEMA_SOURCE_DIAGNOSTIC_REFERENCED`, not as a failed
certificate. The summary layer references the identity-matched E1 PRB source
diagnostic without modifying the E4 primary artifact: seven source diagnostics
are `PASS`, while 210330 retains its audited
`DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH`. All eight exact certifications remain
valid.

## Service and computational metrics

The case-level and aggregate tables report shortage cost, service penalty,
average fill rate, runtime, iterations, cuts, and product-subproblem counts.
Runtime and cut counts rise materially with Gamma in this finite experiment,
but they should be interpreted as observed computational behavior rather than
a general complexity law.

Average and minimum fill rates are derived reporting statistics selected from
certified recourse solutions. They are not terms independently optimized by the
primary objective. Their trajectories must not be presented as proof that E4
optimizes service metrics directly.
