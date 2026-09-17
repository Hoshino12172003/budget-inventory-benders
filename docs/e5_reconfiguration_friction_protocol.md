# E5 Reconfiguration Friction Sensitivity protocol

## Scientific question

E5 asks: How does reconfiguration friction alter the extent and economic value
of robust inventory reconfiguration?

`lambda_R` is the economic and policy friction associated with changing the
incumbent inventory configuration. It is distinct from the financial resource
budget `B` and the uncertainty budget `Gamma`.

E5 changes the economic and budgetary friction associated with changing the
incumbent inventory configuration while leaving the financial capacity `B`
itself unchanged. Because reconfiguration cost enters both the objective and
the financial-budget constraint, the same adjustment uses more budget at a
higher `lambda_R`. This is the mechanism being studied, not a confounding
implementation error.

## Frozen design

The five predeclared friction levels are:

| Token | lambda_R | Interpretation |
|---|---:|---|
| `L0000` | 0 | frictionless benchmark |
| `L0025` | 0.0025 | very low friction |
| `L0100` | 0.01 | low friction |
| `L0500` | 0.05 | current baseline friction |
| `L2000` | 0.20 | high friction |

For all 40 conditions, `beta=1.00`, `B=B_ref(case)`, and `Gamma=2`.
Dataset, mapping, case-specific `x0`, solver profile, tolerances, exact
certification contract, Reconfiguration Model V2, and PRB-Benders remain
frozen. Friction remains symmetric:

```text
g_plus[i,j] = g_minus[i,j] = lambda_R * h[i,j].
```

No asymmetric cost, adjustment fixed cost, transfer-flow variable, or new
friction function is introduced.

The cases are `210202`, `210628`, `210129`, `210310`, `210330`, `210323`,
`210428`, and `210611`. Run IDs use the reversible form
`E5-<case>-<lambda token>`, producing 40 unique IDs.

## Frozen B_ref

| Case | B_ref |
|---|---:|
| 210202 | 106510.9559990062 |
| 210628 | 77408.83107532002 |
| 210129 | 90311.11199905835 |
| 210310 | 76394.09199991751 |
| 210330 | 65650.34742795816 |
| 210323 | 68276.20285663515 |
| 210428 | 75911.97599934557 |
| 210611 | 64656.257997955974 |

Dataset identity is `RENAULT_EMPIRICAL_8CASE_V1`; mapping SHA-256 is
`0bcdd7bb99926ed780c56764c531b76971dbb0bf24e77198766a754d9dde95ff`.

## Reuse policy

The single canonical reuse source is `E4-<case>-G2`. Each source has the same
dataset, mapping, instance, `x0`, `B_ref`, beta, Gamma, `lambda_R=0.05`, model,
PRB implementation, solver profile, tolerance contract, objective definition,
and exact certification status. Result and first-stage-solution provenance
hashes also match. Consequently, all eight `L0500` conditions are reused.

No identity-equivalent paper-final result exists for `L0000`, `L0025`,
`L0100`, or `L2000`. Development calibration and smoke-test outputs are not
eligible. The formal design therefore contains eight verified reuses and 32
future new solves.

## Canonical adjustment reporting

At `lambda_R=0`, the equality

```text
x - x0 = a_plus - a_minus
```

does not prevent `a_plus` and `a_minus` from increasing together. Solver-returned
adjustment variables can therefore be nonunique even when `x` is fixed. The
economic model is unchanged. E5 resolves only the reporting representation:

```text
a_plus_canonical  = max(x - x0, 0)
a_minus_canonical = max(x0 - x, 0)
total adjustment  = sum(abs(x - x0))
RI                = total adjustment / sum(x0)
```

At zero friction, `RS=0`. The formal first-stage solution artifact stores these
canonical adjustment matrices, preserving the solved `x` and `y`. At every
positive friction level, the runner requires canonical and solver-returned
adjustment variables to match within `1e-6`. The eight frozen L0500 sources pass
this identity check.

## High-friction feasibility backstop

For all eight cases, the incumbent stay-put solution sets `x=x0`, uses the
frozen `y0`, and has zero adjustment. Independent static checks confirm capacity,
UB, and B_ref feasibility in every case. Increasing `lambda_R` to 0.20 therefore
cannot by itself make the model structurally infeasible: the unchanged incumbent
remains a feasible backstop.

## Outcomes and hypotheses

Each formal condition records economic components, exact robust recourse,
budget accounting, canonical adjustment and RI, RS, depot changes, service
reporting, runtime, iterations, master solves, subproblem evaluations, cuts,
certification, reuse, and canonicalization status. Objective values are
normalized relative to the case's reused L0500 condition.

E5 examines whether higher friction is associated with lower RI, changes in
RS, objective, recourse, or stay-put behavior. None of these responses is
enforced as a monotonic property. Any reported friction threshold will be an
empirical threshold over the five tested grid points, not a continuous exact
threshold.

## Execution and authorization

Result root:

```text
experiments/results/e5_reconfiguration_friction_v1/
```

The root is narrowly ignored, the runner refuses overwrite, and formal runs
require a clean committed worktree plus exact manifest, model, reporting,
dataset, and source hashes. The static protocol audit passed, all targeted tests
passed, no formal output exists, and authorization transitioned from `false` to
`true`. No E5 optimization was executed during preparation.

Future PowerShell execution:

```powershell
$cases = '210202','210628','210129','210310','210330','210323','210428','210611'
$levels = 'L0000','L0025','L0100','L0500','L2000'
foreach ($case in $cases) {
    foreach ($level in $levels) {
        python experiments/run_e5_lambda_local.py --case $case --lambda-r $level
        if ($LASTEXITCODE -ne 0) { throw "E5 failed: $case $level" }
    }
}
```

The loop includes L0500, but those eight invocations perform verified artifact
reuse rather than first-stage optimization. The no-overwrite gate makes the
command safe to stop and resume only by explicitly skipping completed run IDs.
