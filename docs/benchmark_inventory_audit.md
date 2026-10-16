# Algorithm benchmark inventory audit

## Decision

`PREPARATION_COMPLETE_FORMAL_DIRECT_EXECUTION_BLOCKED`

No optimization was run. The audit distinguishes tracked raw artifacts from narrative statements and derived tables.

## Renault eight-case inventory

| Method | Cases with tracked reusable rows | Objective/certification | Timing | Audit status |
|---|---:|---|---|---|
| Direct exact | 8/8 | 8/8 certified and objective-consistent | 8/8 core times | COMPLETE_DERIVED_FORMAL_TABLE |
| PRB-Benders | 8/8 | 8/8 certified and objective-consistent | 8/8 core and algorithm counters | COMPLETE_DERIVED_FORMAL_TABLE |
| Pure Benders | 1/8 raw-equivalent table rows on this commit | The mechanism audit states 8/8 certified; only 210202 is retained in the tracked machine-readable mechanism table | 210202 only | NOT_FULLY_REUSABLE_FROM_TRACKED_RAW_ARTIFACTS |
| Aggregate + Structured | 1/8 raw-equivalent table rows on this commit | The mechanism audit states 8/8 certified; only 210202 is retained in the tracked machine-readable mechanism table | 210202 only | NOT_FULLY_REUSABLE_FROM_TRACKED_RAW_ARTIFACTS |

Primary evidence is `table_e1_empirical_performance.csv`, `table_e1c_algorithm_mechanism_comparison.csv`, `docs/e1c_pure_benders_mechanism_audit.md`, and the E1 result directories. The frozen E1a Direct/PRB table is complete for the later Renault empirical identity. The E1b documents cite `experiments/results/e1b_pure_benders_v1` and `experiments/results/e1b_standard_benders_v1`, but those directories and their per-case result/provenance files are absent from Git history at this branch. The audit therefore does not treat the narrative claim as a reusable eight-case raw record. Table 1 reports `NOT_VERIFIABLE` for missing Pure/Aggregate timings instead of fabricating them.

The older `experiments/results/e1_algorithm_benchmark/attempt_002` uses a different earlier objective scale and Gurobi 13.0.1 for two cases. It is preserved as historical evidence and is not mixed into the later eight-case table.

## Scaling inventory

- Frozen prepared instances: 30/30 present, with L10 `(25,24,12)`, XL10 `(30,30,14)`, XXL10 `(36,36,16)` and seeds 20260921–20260930.
- Instance and preparation files: 60/60 present and hashed in `artifacts/direct_scaling_instance_manifest.csv`.
- Identity checks: 30/30 pass for dimensions, seed, instance hash, x0 hash, `B_ref`, budget, Gamma, beta, and lambda_R.
- Final three-method formal identity: `ALGORITHM_SCALING_CONVERGENCE_COST_V2_REPAIRED_GUARD`, config hash `38f7d73d468091bfbc1f3b5e0c03711b0ea0c2eee3cd2a876ebd9a11369b7c0f`, execution commit `c46d09c306deb80086a7ceab12812847c117df87`.
- Final condition accounting: expected 90, exact-certified 89, documented non-certified 1, unattempted 0.
- The sole non-certified condition is `ASC_XXL10_S20260925_PURE_BENDERS`; it is an attempted numerical cut-validity failure, not a resource stop or final objective-gap failure.

## Reuse boundary

The 87/90 evidence in `prb_large_scale_simulation_v1` and commit `ed7c66c...` is development evidence with three Pure errors and incomplete raw identity. The 89/90 V2 evidence is the final formal evidence after the repaired cut guard, with exactly one transparently documented failure. They are not pooled or substituted. The Direct extension references only the 30 V2 prepared instances and never rewrites the 89 results or the failure record.
