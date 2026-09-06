# Main integration audit

This ledger records the linear integration of stacked PRs #2-#7 into `main`.
Each layer was merged once, pushed to `origin/main`, and verified before the next
layer. No scientific artifact was regenerated during integration and no formal
optimization was run.

## Integration ledger

| Layer | Source branch | Source commit | Resulting main commit | Verification |
| --- | --- | --- | --- | --- |
| PR #2 | `codex/renault-x0-compatibility-audit`, plus `codex/pr2-provenance-portability-fix` | `67d8f6050670226e0c5d2b8a5de731d4faaddd1a`, fix `d4b3a931044da3808221638972e2c5a0806acfe7` | `b0cad1f4f3291ae56896a1786bbfacc1e1d5bea6` | 21 tests passed |
| PR #3 | `codex/nominal-incumbent-baseline` | `d34d388b18fb48de7c26192e34615d803db72115` | `b47c0731d88783772a895cf312ca24054fbdaf6f` | 26 tests passed |
| PR #4 | `codex/reconfiguration-lambda-calibration` | `6b44b451a0556ffcc153f6cdfd8ba94ca8b64b8b` | `0feddc6159f6fe3c9104ba8985f6527928a2b32e` | 31 tests passed |
| PR #5 | `codex/reconfiguration-model-v2-correctness` | `b7f26d12906c821315f9c44372f39660b04b78fc` | `a421be87bcbe5a72f335e72def2fae6c2d63eecf` | 41 tests passed |
| PR #6 | `codex/product-risk-budget-benders-minimal` | `c6be0bcc4a19c7f05d6fec8ccb2ac2011aeb2764` | `a07165b9fd52a53cc2d2d0de87bfcd2b211e3a94` | 48 tests passed |
| PR #7 | `codex/optimal-face-correctness-contract` | `28f8c1d4a3b4f850a78ef0340cd03adeccf45c64` | `e08e9f2af1e78cef39b822828138366f6709cd4d` | 61 tests passed |

## Changed files by layer

PR #2 and its provenance-only fix:

- `.gitignore`
- `artifacts/renault_x0_210202.csv`
- `artifacts/renault_x0_210628.csv`
- `artifacts/renault_x0_capacity_audit.csv`
- `artifacts/renault_x0_compatibility_summary.json`
- `artifacts/renault_x0_scale_audit.csv`
- `artifacts/renault_x0_ub_audit.csv`
- `docs/renault_formal_case_identity.md`
- `docs/renault_x0_compatibility_audit.md`
- `scripts/run_renault_x0_compatibility_audit.py`
- `tests/test_provenance_portability.py`
- `tests/test_renault_x0_compatibility_artifacts.py`

PR #3:

- `.gitignore`
- `artifacts/nominal_baseline_210202.csv`
- `artifacts/nominal_baseline_210628.csv`
- `artifacts/nominal_baseline_degeneracy_audit.csv`
- `artifacts/nominal_baseline_provenance.json`
- `artifacts/nominal_baseline_summary.json`
- `configs/nominal_baseline_210202.json`
- `configs/nominal_baseline_210628.json`
- `docs/mathematical_model.md`
- `docs/nominal_incumbent_baseline_protocol.md`
- `pyproject.toml`
- `scripts/generate_nominal_baselines.py`
- `src/robust_inventory_reconfiguration/nominal_baseline.py`
- `tests/test_nominal_baseline.py`
- `tests/test_nominal_baseline_artifacts.py`

PR #4:

- `.gitignore`
- `artifacts/lambda_calibration_runs.csv`
- `artifacts/lambda_calibration_summary.json`
- `artifacts/lambda_response_by_case.csv`
- `artifacts/reconfiguration_correctness_audit.json`
- `configs/lambda_calibration_development.json`
- `docs/mathematical_model.md`
- `docs/reconfiguration_budget_and_lambda_calibration.md`
- `scripts/run_lambda_calibration.py`
- `src/robust_inventory_reconfiguration/reconfiguration_model.py`
- `tests/test_reconfiguration_calibration.py`

PR #5:

- `.gitignore`
- `artifacts/exact_benchmark_contract.json`
- `artifacts/reconfiguration_correctness_runs.csv`
- `artifacts/reconfiguration_correctness_summary.json`
- `artifacts/robust_service_evaluation.csv`
- `configs/reconfiguration_correctness_grid.json`
- `docs/productwise_exactness_audit.md`
- `docs/reconfiguration_correctness_protocol.md`
- `docs/reconfiguration_model_v2.md`
- `scripts/run_reconfiguration_correctness.py`
- `src/robust_inventory_reconfiguration/exact_benchmark.py`
- `src/robust_inventory_reconfiguration/reconfiguration_model.py`
- `src/robust_inventory_reconfiguration/robust_service.py`
- `src/robust_inventory_reconfiguration/scenarios.py`
- `tests/test_reconfiguration_correctness.py`

PR #6:

- `.gitignore`
- `artifacts/prb_benders_correctness_runs.csv`
- `artifacts/prb_benders_correctness_summary.json`
- `artifacts/prb_cut_validity_audit.csv`
- `artifacts/prb_gamma_composition_audit.csv`
- `configs/prb_benders_correctness.json`
- `docs/product_risk_budget_benders.md`
- `docs/product_risk_budget_cut_derivation.md`
- `scripts/run_prb_benders_correctness.py`
- `src/robust_inventory_reconfiguration/exact_benchmark.py`
- `src/robust_inventory_reconfiguration/product_risk_budget_benders.py`
- `src/robust_inventory_reconfiguration/product_risk_subproblem.py`
- `src/robust_inventory_reconfiguration/risk_budget_composition.py`
- `tests/test_product_risk_budget_benders.py`
- `tests/test_product_risk_subproblem.py`
- `tests/test_risk_budget_composition.py`

PR #7:

- `.gitignore`
- `artifacts/prb_correctness_contract_summary.json`
- `artifacts/prb_correctness_reclassification.csv`
- `artifacts/prb_optimal_face_audit.csv`
- `docs/optimal_face_correctness_contract.md`
- `docs/product_risk_budget_benders.md`
- `scripts/audit_optimal_face_correctness.py`
- `src/robust_inventory_reconfiguration/optimal_face_correctness.py`
- `tests/test_optimal_face_artifacts.py`
- `tests/test_optimal_face_correctness.py`

## Provenance and authorization guardrails

`FORMAL_CASE_IDENTITY_RESOLVED`: the formal cases are `210202` and `210628`.
Case `210712` is present in the raw archive but is not part of the current formal
processing chain.

The PR #2 path correction records `instances.tar.gz`,
`external://renault-raw/instances.tar.gz`, and the immutable source archive SHA-256.
The scientific payload is unchanged; only provenance path serialization changed.
The generated summary artifact SHA-256 changed from
`53d91755103a999fb44b323fe0468de5a01a28ea21f9bd2ca7f2b0b60b931518` to
`4178020da083503080c36c9dd334f913828859ad144611d0dbf96f9542d66163`;
the source archive SHA-256 remains
`c27075450bc8ace8e74087316b64f22d2a9a9909cb4e4746341bc9f3998950ea`.

`formal_run_authorized = false`. Formal optimization runs executed: zero. Formal
result artifacts written: zero. PR #8 was not rebased or modified by this integration.
