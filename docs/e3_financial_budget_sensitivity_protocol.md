# E3 financial budget sensitivity protocol

## Scientific scope

E3 asks how the available financial budget constrains the extent and economic
value of robust inventory reconfiguration. It uses only the ROBUST policy and
PRB-Benders. It is neither an algorithm benchmark nor another
EXISTING--NOMINAL comparison.

The experiment uses all eight `RENAULT_EMPIRICAL_8CASE_V1` cases. The frozen
factors are Gamma=2, lambda_R=0.05, the case-specific nominal incumbent `x0`,
the case-specific paper-final `B_ref`, and solver profile
`gurobi-balanced-1e-8-v1`. The financial-budget factor is exactly
beta in `{0.80, 0.90, 1.00, 1.10, 1.20}`, with
`B(case,beta) = beta * B_ref(case)`. Financial budget `B`, uncertainty budget
Gamma, and reconfiguration friction lambda_R are distinct quantities; beta is
not a risk parameter.

The full design has 40 run IDs of the form `E3-<case>-B080` through
`E3-<case>-B120`. The B100 run for each case is reused, without a new solve or
evaluation, only after exact identity checks against the existing E1 PRB
certification, E2 ROBUST evaluation, full first-stage artifact, and the current
frozen model sources. This leaves 32 new PRB solves when all eight reuse checks
pass.

## Correctness and preservation

Every new run must be exactly certified under the frozen PRB contract. The
runner verifies authorization, clean committed worktree, dataset, instance,
`x0`, calibration, `B_ref`, mapping, model source identity, Gamma, lambda_R,
solver profile, beta membership, and no-overwrite protection. It computes beta
and `B` through decimal string representations before conversion to the solver
float. A result passes financial feasibility only when
`budget_used - B <= 1e-6`; both signed slack and positive absolute violation
are stored.

The runner writes `result.json`, `first_stage_solution.json`, and
`provenance.json` into a temporary run directory and renames that directory to
the final run ID only after every file is complete. E1 and E2 result roots are
read-only reuse sources. E3 writes only below
`experiments/results/e3_budget_sensitivity_v1/`, which is Git-ignored.

RI, RS, depot activation, fill rates, shortage, reconfiguration cost, and
service metrics are reporting outcomes. Their cross-beta monotonicity is not a
correctness condition. The summary reports their observed paths and deltas
relative to B100 without rejecting nonmonotone responses. It supports analysis
of budget sensitivity, saturation or diminishing returns, the four E2
no-material cases, and whether added financial resources flow to inventory,
reconfiguration friction, or depot activation. It does not predeclare any of
those empirical answers.

## Future local execution

From a clean committed checkout, run the exact authorized grid in PowerShell:

```powershell
$cases = @('210202','210628','210129','210310','210330','210323','210428','210611')
$betas = @('0.80','0.90','1.00','1.10','1.20')
foreach ($case in $cases) {
    foreach ($beta in $betas) {
        python experiments/run_e3_budget_local.py --case $case --beta $beta
        if ($LASTEXITCODE -ne 0) { throw "E3 failed: case=$case beta=$beta" }
    }
}
python scripts/summarize_e3_budget_results.py
```

The result root is no-overwrite. Resume by running only missing run IDs; do not
rerun an existing directory.

## Preparation status

Protocol preparation and static auditing execute no E3 optimization. E1 and E2
results, the model, dataset, `x0`, `B_ref`, Gamma, lambda_R, and solver profile
remain unchanged.
