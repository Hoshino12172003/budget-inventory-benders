# E6 budget-risk 5x5 extension audit

## Decision

**PREPARED BUT NOT AUTHORIZED.** No optimization was executed. The formal authorization remains `false`.
All 104 planned reuse cells pass the live source-file and overlap identity audit. The historical sources are recovered and bound to this manifest; no source-restoration blocker remains.

The recovered artifacts independently authenticate their exact historical code commits and frozen
model identity. This resolves reuse identity without pretending the extension layer produced them.
This execution checkout matches the frozen E6 model and PRB identities byte for byte.

## Frozen extension

- Experiment: `E6_BUDGET_RISK_5X5_V1` (independent of historical E6).
- Grid: beta = 0.80, 0.90, 1.00, 1.10, 1.20; Gamma = 0, 1, 2, 3, 4.
- Parameter combinations: 25.
- Renault cases: 8; expected case-level cells: 200.
- Planned exact reuse cells: 104; live identity-audit passes: 104.
- Genuinely absent parameter cells requiring new optimization after authorization: 96.
- Fixed scientific inputs: Renault 8-case dataset, case-specific `B_ref`, `x0`, lambda_R=0.05,
  model identity, solver profile, and tolerances inherited byte-for-byte from the formal E6 contract.

## Deterministic reuse rule

Historical E6 is selected for all 72 cells in its 3x3 grid. E3 supplies only the 16 additional
`Gamma=2` cells at beta 0.90 and 1.10. E4 supplies only the 16 additional beta 1.00 cells at
Gamma 1 and 3. Candidate overlaps are recorded in the reuse map; they are never counted twice.
Reuse requires the source result, first-stage solution, and provenance files plus matching case,
beta, Gamma, lambda_R, instance/x0/calibration/mapping/model/solver identities, `OPTIMAL` status,
and `CERTIFIED_PRB_EXACT` certification. Missing source files fail closed.

The E3 audit preserves per-file hashes, and the historical E6 audit preserves per-file hashes.
For E4, the recovered frozen ZIP is SHA-256 authenticated and all 120 ZIP members match the recovered
result tree byte for byte. `e4_per_file_hashes_for_e6_reuse_audit.csv` records the derived per-file
hashes with classification `DERIVED_FROM_FROZEN_ARCHIVE_FOR_REUSE_AUDIT`; it is audit evidence, not
a new experiment result.

Recovered formal source paths:

- E3: `C:/Users/Hu Jiaxin/Documents/Codex/2026-09-06/github-hoshino12172003-robust-inventory-benders-v1/work/new_repo/experiments/results/e3_budget_sensitivity_v1`
- E4: `C:/Users/Hu Jiaxin/Documents/Codex/2026-09-06/github-hoshino12172003-robust-inventory-benders-v1/work/new_repo/experiments/results/e4_gamma_sensitivity_v1`
- E6: `C:/Users/Hu Jiaxin/Documents/Codex/2026-09-06/github-hoshino12172003-robust-inventory-benders-v1/work/new_repo/experiments/results/e6_budget_risk_interaction_v1`

The provenance commits are `045663bbecd912cb36f39002bdf8061cb513630d, 0826e10c51f973397d8a16c6c9713471ccb53a93, 183b4a07fae28fb7d3235b5ec113276ef5bc35b8, 47f4010becae0d05223251571a465b63b66cd1c2, cc87b68363fa9cc444046f7823a6807412bb7ca8`. All resolve in the
current Git object database and reproduce model identity `c4f718f6a12deb22772cdce20464ca617fa6e19c750a90be06cd2ddc8c245173`.
The E6-producing commit is `cc87b68363fa9cc444046f7823a6807412bb7ca8`; a detached audit
worktree is available at `E:/paper-code/formal-history/e6-frozen-code-cc87b683`.

## Runner and recovery contract

`experiments/run_e6_budget_risk_5x5_local.py` uses a separate result root,
`experiments/results/e6_budget_risk_5x5_v1`. It refuses authorization=false, validates every planned
reuse source before any optimization, refuses dirty worktrees and overwrites, writes each cell through
an atomic temporary directory, and resumes only from a complete checkpoint whose manifest, runner,
result, solution, status, and certification identities all match. Reuse cells are materialized without
optimization; only the cells in `e6_budget_risk_5x5_missing_cells.json` enter the solver path.

## Heatmap contract

`scripts/summarize_e6_budget_risk_5x5_results.py` refuses anything except the exact 200-run ID set,
rejects duplicate, uncertified, or missing-metric results, and writes discrete 5x5 matrices for mean
objective normalized within each case by beta=1.00/Gamma=2 and mean RI in percent. It performs no
interpolation, smoothing, or synthetic completion.

## Current safety conclusion and commands

This preparation snapshot was produced while formal authorization was false. The later manual
authorization is recorded separately in the authorization manifest and frozen execution audit.

Preparation checkout: `codex/e6-5x5-frozen-execution` at
`94794269fde12f30c58190d96e51f0267eedb261`. The branch label is not itself a scientific
blocker; commit, model, data, and experiment identities control admission. The observed model identity is
`c4f718f6a12deb22772cdce20464ca617fa6e19c750a90be06cd2ddc8c245173` versus the frozen E6 identity
`c4f718f6a12deb22772cdce20464ca617fa6e19c750a90be06cd2ddc8c245173`. The observed PRB file is
`eab5ea31c6dbbc6446799f28bb6b54673eb7b57690cd4540f8a49b4a53757b6f` versus
`eab5ea31c6dbbc6446799f28bb6b54673eb7b57690cd4540f8a49b4a53757b6f`. These are hard runtime blockers, not waived differences.

Targeted extension tests: `11 passed`. Extension plus available historical E6 protocol tests:
`26 passed, 4 failed`; the four failures are legacy physical-file hash gates or a read-only fixture
assumption. E3/E4 protocol tests: `37 passed, 6 failed`; those failures are historical checkout
line-ending hashes or absent E1/E2 fixtures.
`e6_budget_risk_5x5_regression_classification.csv` classifies every failure as
`TRUE_CURRENT_BLOCKER`, `HISTORICAL_FREEZE_MISMATCH`, `MISSING_FIXTURE`, or
`IRRELEVANT_TO_E6_5X5_EXECUTION` and separately
records whether it blocks reuse or the future 96-cell run.

`git diff` reports no modification to the historical E6 runner, authorization, or final E3/E4/E6
audits. Therefore the failures are preserved evidence, not repaired by weakening old contracts.

The combined scoped gate reports `43 passed, 10 failed`. No failure was hidden, and none was changed
to a pass by editing a historical authorization or result.

## Admission recommendation

Preparation decision at the time of this snapshot: `READY_FOR_MANUAL_AUTHORIZATION`.

Current execution admission is governed by the later frozen execution audit and authorization manifest:
104/104 reuse cells are verified, the 96-cell missing set is unchanged, and the execution checkout
uses the frozen E6 model bundle. The separate manual authorization has now been recorded; current readiness is stated only by the
frozen execution audit.

PyCharm: run `experiments/run_e6_budget_risk_5x5_local.py` with parameter `--audit-only` and the
repository root as working directory.

Command line (authorized preparation audit only):

```powershell
python experiments/run_e6_budget_risk_5x5_local.py --audit-only
```

Future formal command, shown for review only and guaranteed to fail until a separately reviewed
manifest changes authorization to true:

```powershell
python experiments/run_e6_budget_risk_5x5_local.py --run-all
```
