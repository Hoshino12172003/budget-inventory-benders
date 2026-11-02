# E6-5X5 frozen execution admission audit

## Decision

`READY_TO_RUN_LOCALLY`

Manual authorization is recorded as `MANUAL_FORMAL_RUN_AUTHORIZATION` and
`formal_run_authorized=true`. No optimization was executed during authorization or gate validation.

## Execution identity

- Frozen execution checkout: `E:/paper-code/formal-history/e6-frozen-code-cc87b683`
- Base historical commit: `cc87b68363fa9cc444046f7823a6807412bb7ca8`
- Branch: `codex/e6-5x5-frozen-execution`
- `BASE_MODEL_IDENTITY`: `HISTORICAL_E6_FROZEN`
- `EXPERIMENT_LAYER`: `E6_5X5_EXTENSION`
- Frozen model SHA-256: `c4f718f6a12deb22772cdce20464ca617fa6e19c750a90be06cd2ddc8c245173`
- Frozen PRB working-tree SHA-256: `eab5ea31c6dbbc6446799f28bb6b54673eb7b57690cd4540f8a49b4a53757b6f`
- New E6-5X5 runner SHA-256: `41b921c9baa2f8005f13c773c58fd3a0514c7abcd5e4212c2297a4238da97976`
- Dataset bundle SHA-256: `e695f020bb9b9e7b7e6f14bcd9550872bfff197963f32c1161fbf0061e0b2044`
- Instance-generation identity SHA-256: `9bd9bac81e98ea61e983d73a1da3fc8e9c8ef776461916a97abc70fbe4805a64`
- Solver profile: `gurobi-balanced-1e-8-v1`
- Tolerances: budget feasibility/binding/reporting/materiality `1e-6`; objective certification `1e-4`.

The full identity record is `artifacts/e6_budget_risk_5x5_frozen_execution_identity.json`.

## Dependency audit

The extension runner imports the frozen historical `experiments/run_e6_budget_risk_local.py` and
uses its existing `solve_new_result`, service reporting, first-stage artifact, and PRB-Benders entry
points. No current-checkout model, PRB, instance-construction, or solver helper was copied into this
checkout. Git reports no changes to `src/`, the historical E6 runner, historical E6 authorization,
or historical result artifacts.

Extension text files are pinned to LF in `.gitattributes`, so the new runner and manifest hashes are
portable across future Windows checkouts without altering historical files.

## Reuse and missing-cell contract

- Expected cells: 200.
- Verified reuse cells: 104/104.
- Missing solve cells: 96/96.
- Failed reuse cells are never converted to new solves.
- Interpolation and synthetic completion: prohibited.
- Recovered source files: 456, all byte-identical to the authenticated source and marked read-only.
- New result root: absent.
- Optimization calls during this task: 0.

## Output and recovery safeguards

The extension tests cover authorization rejection, exact reuse/missing partition, frozen model and
dataset identity, incomplete-result rejection, discrete 5x5 aggregation, atomic per-cell output,
provenance hashes, overwrite refusal, complete-checkpoint resume, partial-checkpoint rejection, and
non-mutation of the read-only historical sources. The aggregator requires all 200 certified results
and contains no interpolation or synthetic completion path.

## Regression status

- E6-5X5 extension-specific tests: 14 passed.
- Extension plus available historical E6 protocol tests: 29 passed, 4 failed.
- Historical E3/E4 protocol tests: 37 passed, 6 failed.

All ten failures are classified in
`artifacts/e6_budget_risk_5x5_regression_classification.csv`. They are historical physical-file
line-ending gates, deliberately read-only fixture behavior, or absent E1/E2 fixtures; none blocks
the independently frozen E6-5X5 execution path. No frozen test, model, authorization, or artifact was
weakened to make a failure pass.

## Authorized local command

From the frozen execution checkout:

```powershell
python experiments/run_e6_budget_risk_5x5_local.py --run-all
```

This command has **not** been executed. The authorization manifest and zero-solve execution gate were
validated independently before this command was released for local use.
