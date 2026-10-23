# Algorithm benchmark inventory audit

## Decision

`PREPARATION_COMPLETE_AWAITING_FORMAL_DIRECT_AUTHORIZATION`

No optimization was run. The audit distinguishes tracked raw artifacts from narrative statements and derived tables.

## Renault eight-case inventory

| Method | Cases with tracked reusable rows | Objective/certification | Timing | Audit status |
|---|---:|---|---|---|
| Direct exact | 8/8 | 8/8 certified and objective-consistent | 8/8 core times | COMPLETE_DERIVED_FORMAL_TABLE |
| PRB-Benders | 8/8 | 8/8 certified and objective-consistent | 8/8 core and algorithm counters | COMPLETE_DERIVED_FORMAL_TABLE |
| Pure Benders | 8/8 recovered formal runs | 8/8 exact-certified and objective-consistent | 8/8 core times | COMPLETE_HASH_VERIFIED_RAW_EVIDENCE |
| Aggregate + Structured | 8/8 recovered formal runs | 8/8 exact-certified and objective-consistent | 8/8 core times | COMPLETE_HASH_VERIFIED_RAW_EVIDENCE |

Primary evidence is `table_e1_empirical_performance.csv`, the recovered E1b result directories, and `artifacts/renault_e1b_recovery_audit.json`. The 88 E1b files are byte-identical copies from the historical Codex work directory: 40 Pure files and 48 Aggregate files. All 16 result/provenance chains, exact-certification states, instance/x0 identities, and E1c numerical cross-checks pass. Table 1 is regenerated directly from these raw JSON files and contains all four methods for all eight cases.

The historical Aggregate ZIP has SHA-256 `1f02e8834c7be16cac80a07e5470765b109f6f0c84825f8ef3d7e235010ee5ed`; all 48 members are byte-identical to the restored Aggregate directory. No historical Pure ZIP was found, and none is represented as an original-run archive. See `docs/renault_e1b_recovery_report.md` and `artifacts/renault_e1b_recovery_manifest.csv`.

The older `experiments/results/e1_algorithm_benchmark/attempt_002` uses a different earlier objective scale and Gurobi 13.0.1 for two cases. It is preserved as historical evidence and is not mixed into the later eight-case table.

## Scaling inventory

- Frozen prepared instances: 30/30 present, with L10 `(25,24,12)`, XL10 `(30,30,14)`, XXL10 `(36,36,16)` and seeds 20260921–20260930.
- Instance and preparation files: 60/60 present and hashed in `artifacts/direct_scaling_instance_manifest.csv`.
- Identity checks: 30/30 pass for dimensions, seed, instance hash, x0 hash, `B_ref`, budget, Gamma, beta, and lambda_R.
- Final three-method formal identity: `ALGORITHM_SCALING_CONVERGENCE_COST_V2_REPAIRED_GUARD`, config hash `38f7d73d468091bfbc1f3b5e0c03711b0ea0c2eee3cd2a876ebd9a11369b7c0f`, execution commit `c46d09c306deb80086a7ceab12812847c117df87`.
- Final condition accounting: expected 90, exact-certified 89, documented non-certified 1, unattempted 0.
- The sole non-certified condition is `ASC_XXL10_S20260925_PURE_BENDERS`; it is an attempted numerical cut-validity failure, not a resource stop or final objective-gap failure.
- Scaling V2 did not persist its Python executable or Gurobi version. Gurobi 13.0.1 is the evidence-supported inference, but the formal historical value remains `NOT_VERIFIABLE`; Renault's verified 13.0.2 is not transferred to Scaling V2.

## Reuse boundary

The 87/90 evidence in `prb_large_scale_simulation_v1` and commit `ed7c66c...` is development evidence with three Pure errors and incomplete raw identity. The 89/90 V2 evidence is the final formal evidence after the repaired cut guard, with exactly one transparently documented failure. They are not pooled or substituted. The Direct extension references only the 30 V2 prepared instances and never rewrites the 89 results or the failure record.
