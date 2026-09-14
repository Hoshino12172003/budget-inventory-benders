# E7 Demand-Risk × Reconfiguration-Friction Interaction Protocol

## Research question

E7 asks how reconfiguration friction alters the inventory response to increasing demand uncertainty. It complements E4 and E5 by estimating a two-dimensional Gamma-by-friction interaction rather than another one-dimensional sensitivity exercise.

## Frozen design

- Dataset: `RENAULT_EMPIRICAL_8CASE_V1`.
- Cases: 210202, 210628, 210129, 210310, 210330, 210323, 210428, and 210611.
- Financial capacity: `beta=1.0`, so `B=B_ref`.
- Demand-risk levels: `G0`, `G2`, and `G4`, corresponding to Gamma 0, 2, and 4 adverse region-product demand components.
- Friction levels: `L0025`, `L0500`, and `L2000`, corresponding to lambda_R 0.0025, 0.05, and 0.20.
- Symmetric friction: `g_plus_ij=g_minus_ij=lambda_R*h_ij`.
- Materiality threshold: canonical `RI > 1e-6`.
- Solver and certification: frozen PRB-Benders solver profile and exact-certification contract.

Lambda_R is a model-consistent sensitivity parameter, not an observed Renault parameter. The full Cartesian design contains 72 conditions.

## Reuse contract

Reuse is derived from completed source designs rather than fixed counts. E4 supplies the L0500 column at G0, G2, and G4. E5 supplies the G2 row at L0025, L0500, and L2000. G2-L0500 is validated from both experiments, selected once from E4, and retains E5 as corroborating provenance. Every reused result must match case, dataset, mapping, instance, x0, calibration, B_ref, beta, Gamma, lambda_R, model, PRB implementation, solver profile, tolerance contract, first-stage payload, economic accounting, and exact certification.

Any missing or mismatched planned source blocks authorization. The runner must not silently replace a rejected reuse with a new solve.

## Interaction outcomes

E7 reports economic exposure, robust recourse, inventory reconfiguration, budget use, service diagnostics, and algorithmic effort. The reporting-only concentration metric is

`top_adjustment_share = max_ij |x_ij-x0_ij| / sum_ij |x_ij-x0_ij|`,

with value zero when total adjustment is zero. It does not enter the optimization model.

For each friction level, reporting computes the G0-to-G4 change in RI, objective, robust recourse, RS, and changed-pair count. The low-versus-high descriptive contrast is

`[Y(G4,L0025)-Y(G0,L0025)] - [Y(G4,L2000)-Y(G0,L2000)]`.

This is an optimization-experiment interaction contrast, not causal difference-in-differences. `first_material_gamma_observed_in_e7_grid` may be 0, 2, 4, or `none_through_4`; it is not a continuous threshold.

## Timing contract

All E7 runner timers use `time.perf_counter()`.

- `t_instance_load_seconds`: formal instance and x0 loading and validation.
- `t_reuse_validation_seconds`: reuse-plan discovery, source validation, overlap corroboration, and source selection for the requested condition.
- `t_core_prb_seconds`: PRB master construction/iterations/separation time excluding the separately reported final certification time.
- `t_exact_certification_seconds`: final exact product-wise recourse certification inside PRB.
- `t_post_evaluation_seconds`: reporting-only exact service evaluation after primary PRB certification.
- `t_reporting_seconds`: deterministic construction of costs, reconfiguration, service, network, and schema fields.
- `t_artifact_write_seconds`: first-stage and result artifact materialization up to the final timing snapshot.
- `t_total_runner_wallclock_seconds`: monotonic time from the beginning of the condition execution through the final timing snapshot immediately before final provenance serialization and atomic directory commit.

The final provenance serialization and atomic rename occur after the self-recorded timing snapshot and are excluded. The runner enforces that total wall-clock is no smaller than the sum of the non-overlapping contained stages within the frozen reporting tolerance.

Core PRB time and total runner wall-clock are distinct quantities. Algorithm comparisons use the consistent core-optimization contract; operational execution reporting uses total runner wall-clock.

## Primary certification versus post-evaluation

Primary correctness remains governed by the existing PRB exact-certification contract. The service/reporting evaluator is post-hoc and does not affect the objective, feasibility, cuts, or convergence logic.

For `R=12`, `J=8`, and Gamma 4, the current reporting evaluator creates

`8 * sum_{g=0}^4 C(12,g) = 6,352`

product-risk blocks and enumerates

`sum_{g=0}^4 C(96,g) = 3,469,497`

global scenarios. Full enumeration is unnecessary for the worst economic recourse because product-risk dynamic programming already gives that value exactly. It is not presently proven dispensable for the full reporting contract: independently worst shortage and minimum-fill scenarios, region-level fill vectors, selected scenario identity, and deterministic tie handling depend on more than the scalar economic value. No faster evaluator is introduced without an exact equivalence proof. The exhaustive evaluator remains the frozen reference, and G4 post-evaluation may dominate total wall-clock.

## Static feasibility

Every planned new cell is checked without optimization using the constructive point `y=0`, `x=0`, `a_plus=0`, `a_minus=x0`, with shortage and service-violation recourse. The first-stage expenditure is the friction-weighted removal cost. The G4-L2000 corner receives explicit case-wise audit; no parameter may be altered to force feasibility.

## Execution and output controls

The result namespace is `experiments/results/e7_risk_friction_interaction_v1/`. Writes are atomic, refuse overwrite, preserve full first-stage solutions and provenance, and cannot touch E1-E6. The runner accepts only the frozen Gamma/lambda tokens, enforces beta 1.0, and supports a solver-free `--dry-run`.

The current authorization is deliberately false. This protocol may become ready for authorization after its static audit, but no formal E7 solve is allowed in this task.

Future completed-result reporting paths are:

- `artifacts/e7_table_risk_friction_case_level.csv`
- `artifacts/e7_table_risk_friction_aggregate.csv`
- `artifacts/e7_table_interaction_contrasts.csv`
- `artifacts/e7_table_adjustment_composition.csv`
- `artifacts/e7_runtime_breakdown.csv`

Future figures are generated in PNG and PDF with matplotlib on a white background. No paper result, table, or figure is generated before the 72-result grid is complete.
