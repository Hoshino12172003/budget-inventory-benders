# E2 scientific interpretation audit

## Scope and audit contract

This audit reads the 24 immutable `result.json` files under
`experiments/results/e2_existing_nominal_robust_v1/`. It performs no new
optimization and no new fixed-first-stage evaluation. All 24 expected run IDs
are present exactly once, all have the expected case and policy identity, and
all report `status=OPTIMAL`.

Material reconfiguration is declared before interpretation as `RI > 1e-6`, a
positive saved changed-pair count, or a saved opened/closed depot. Objective
improvement, service improvement, and shortage improvement use the same
`1e-6` materiality tolerance. Baseline consistency additionally requires the
EXISTING--NOMINAL objective difference to be at most `1e-4`, no material
NOMINAL reconfiguration, the same active-depot count, and no reported depot
opening or closure.

E2 result directories contain aggregate `result.json` files only. They do not
contain coordinate-wise NOMINAL `x` or `y` artifacts. Consequently, this audit
certifies saved objective and material-decision consistency, not exact
coordinate identity. No missing coordinate values were reconstructed and no
evaluation was rerun.

## Baseline consistency

All eight cases are `BASELINE_CONSISTENCY_PASS`. The largest absolute
EXISTING--NOMINAL objective difference is `2.691522240638733e-7`, and the
largest relative difference is `4.3593358243386796e-13`. Every NOMINAL result
has zero saved changed pairs, no depot opening or closure, the same active-depot
count as EXISTING, and only sub-tolerance `RI`/`RS` residuals.

EXISTING and NOMINAL agree because `x0` was itself constructed as the
Gamma=0 nominal optimum. This result does not mean that the NOMINAL runner
skipped optimization: NOMINAL used `Gamma_plan=0` first-stage optimization,
whereas EXISTING fixed `x=x0` and did not reoptimize the first stage.

## Case-level contrast

Positive objective improvement is `EXISTING - ROBUST`. Signed cost and service
changes are `ROBUST - EXISTING`.

| Case | Classification | Objective improvement | Improvement (%) | RI | RS | Changed pairs | Shortage change | Average fill-rate change |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 210202 | MATERIAL_ROBUST_RECONFIGURATION | 2250.370225 | 0.212093 | 0.137620 | 0.004496 | 3 | 16.935397 | -0.016397 |
| 210628 | NO_MATERIAL_RECONFIGURATION | -0.000000 | -0.000000 | 1.812e-11 | 4.257e-13 | 0 | 0.000000 | 1.943e-15 |
| 210129 | MATERIAL_ROBUST_RECONFIGURATION | 1130.962174 | 0.132681 | 0.085655 | 0.002747 | 3 | -3.750394 | -0.012325 |
| 210310 | NO_MATERIAL_RECONFIGURATION | -0.000000 | -0.000000 | 0.000000 | 0.000000 | 0 | 0.000000 | 1.776e-15 |
| 210330 | MATERIAL_ROBUST_RECONFIGURATION | 717.532687 | 0.108985 | 0.065211 | 0.002121 | 2 | -24.287430 | -0.007731 |
| 210323 | MATERIAL_ROBUST_RECONFIGURATION | 464.127780 | 0.073951 | 0.039427 | 0.001306 | 2 | -38.607355 | -0.004709 |
| 210428 | NO_MATERIAL_RECONFIGURATION | 0.000000 | 0.000000 | 3.094e-12 | 1.076e-13 | 0 | -4.547e-13 | -7.494e-16 |
| 210611 | NO_MATERIAL_RECONFIGURATION | -0.000000 | -0.000000 | 7.500e-11 | 1.728e-12 | 0 | 4.547e-13 | 5.579e-15 |

No case opens or closes a depot, and each ROBUST result has the same saved
active-depot count as its EXISTING baseline. Reconfiguration in the four
material cases is therefore an inventory-allocation change within the same
active-depot structure.

## Exact 210202 objective explanation

For 210202, ROBUST changes the monetary objective as follows:

| Component | ROBUST - EXISTING |
|---|---:|
| Fixed depot cost | 0.000000000 |
| Final inventory cost | -478.823511413 |
| Reconfiguration friction | +478.823511413 |
| Net first-stage spending | 0.000000000 |
| Robust recourse | -2250.370225318 |
| Total objective | -2250.370225318 |

The stored worst-recourse components give a complete recourse identity. The
shortage-cost change is `-2582.236535582`, the service-penalty change is
`+868.248989216`, and the implied transportation-cost change is
`-536.382678951`. These sum to the `-2250.370225318` robust-recourse change.
Thus the objective improves entirely through lower robust recourse cost; the
inventory-cost reduction is exactly offset by reconfiguration friction.

At the same time, stored total shortage rises by `16.935397090` units and the
average fill rate of the worst-service scenario falls by `0.016396855`. This is
not an objective contradiction: shortage cost is region/product weighted,
while total shortage is an unweighted quantity, and the fill-rate metrics are
reported from the worst-service scenario rather than necessarily the
worst-recourse scenario. The stored aggregates fully reconstruct the monetary
objective, but do not retain product-region detail for a finer attribution.

## Aggregate findings

- Material robust reconfiguration: 4 cases; no material reconfiguration: 4.
- Mean/median absolute objective improvement across all cases:
  `570.374108352` / `232.063890227`.
- Mean/median percentage improvement across all cases:
  `0.065963800%` / `0.036975732%`.
- Mean/median absolute improvement among adjusted cases only:
  `1140.748216865` / `924.247430861`.
- Mean/median percentage improvement among adjusted cases only:
  `0.131927600%` / `0.120833090%`.
- Adjusted-case RI range: `[0.039426582, 0.137620080]`; RS range:
  `[0.001305594, 0.004495533]`.
- Material total-shortage decrease: 3 cases. Material average fill-rate
  increase: 0 cases. Material objective improvement: 4 cases.
- ROBUST equals the baseline numerically in 4 cases under the `1e-6`
  materiality rule.

These are descriptive results for eight empirical cases; no significance test
is performed.

## Paper-facing interpretation and presentation

The evidence supports three restrained conclusions. First, nominal
reoptimization returns essentially the same incumbent because `x0` is already
nominally efficient. Second, Gamma=2 planning induces material inventory
reconfiguration in only a subset of cases. Third, an economic robust-objective
improvement need not produce monotonic improvement in aggregate fill-rate
metrics.

The recommended main-text presentation is **B**: use NOMINAL as a baseline
validation column or compact appendix check, and make EXISTING (the nominal
incumbent) versus ROBUST the main scientific contrast. Showing EXISTING and
NOMINAL as co-equal main comparisons would duplicate an empirically identical
baseline and risk double-counting the same contrast. A three-column validation
table may still document that NOMINAL was genuinely optimized and recovered
the incumbent.

## Preservation statement

`E2 new optimization solves = 0`; `E2 new evaluations = 0`; existing E2
results overwritten = false; E1 overwritten = false; model changed = false;
dataset changed = false; Gamma changed = false; lambda_R changed = false.
