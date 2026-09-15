# E4 210628/G4 reporting tie-break audit

## Conclusion

`E4-210628-G4` is classified as `AUXILIARY_NUMERICAL_SUBOPTIMAL`.
Gurobi status 13 applied only to the post-solve continuous quadratic reporting
tie-break. The primary PRB solve had already reached `OPTIMAL`, with
`CERTIFIED_PRB_EXACT` certification, objective `708428.6873031154`, and robust
recourse `631019.8562277922`. The model, first-stage solution, and scientific
parameters were not changed.

The original failed invocation wrote no formal run artifact. One clean formal
rerun was therefore required after the reporting fix; it created the immutable
`E4-210628-G4` result once and did not overwrite another result.

## Failure boundary

The E4 runner first completes PRB optimization, checks `status == OPTIMAL` and
exact certification, and only then calls the detailed service evaluator with
the fixed first-stage inventory. The exception occurred in that evaluator.
Consequently, the original solve had valid in-memory `y`, `x`, `a_plus`, and
`a_minus`, but its reporting exception happened before `result.json`,
`first_stage_solution.json`, `provenance.json`, a target run directory, or a
temporary output directory was written.

## Tie-break formulation

For every product `j` and every shocked-region subset `S` with
`|S| <= Gamma`, the evaluator constructs the usual continuous recourse block
with shipment `q`, shortage `u`, and service violation `e`.

1. The primary auxiliary LP minimizes the sum of economic block costs
   (transportation + shortage + service penalty). Separability makes the
   resulting value for each block its exact fixed-inventory recourse optimum.
2. Each block cost is constrained by
   `cost[j,S] <= optimum[j,S] + 1e-7`.
3. The original secondary objective minimizes
   `sum[j,S,r] u[j,S,r]^2` to choose representative flows for reporting.

This is a continuous convex QP, not a MILP. It has no applicable MIP gap. The
formal continuous profile is `FeasibilityTol=1e-8`,
`OptimalityTol=1e-8`, `NumericFocus=0`, and automatic `Method=-1`. The
economic-band tolerance remains `1e-7`. The secondary solution selects
reported shortage, cost-component, and fill-rate values; it is not used to
establish the primary PRB objective or exact robust-recourse certificate.

## Full-precision diagnostic

The reproduced 210628/G4 QP had 1,225,936 variables, 184,208 constraints,
76,224 quadratic nonzeros, and 6,352 independent product-risk blocks. Its
matrix coefficients ranged from `0.06999276018099547` to `512.45`.

The QP returned:

- status: `13 (SUBOPTIMAL)`
- solution count: `1`
- objective: `298396086.55992794`
- objective bound: `298396609.087596`
- constraint violation: `0.004116335796425119`
- bound violation: `0.0`
- dual violation: `0.0`
- barrier iterations: `38`
- maximum block-cost deviation: `0.004116435797186568`
- exact robust-recourse target reconstructed from the blocks:
  `631019.8562277922`
- tied global Gamma allocations: `1`
- tied worst scenarios: `1`

Although a feasible-looking incumbent existed, its block-cost deviation was
far larger than the frozen `1e-7` reporting band (including the existing
feasibility tolerance). It was therefore not silently accepted.

The same fixed-state audit returned `OPTIMAL` for 210628/G3 and 210202/G4.
210628/G3 was much smaller (461,656 variables, 69,368 constraints, 28,704
quadratic nonzeros, and 2,392 blocks). 210202/G4 had the same dimensions as the
failed case but a less extreme minimum matrix coefficient
(`0.38722932651321396`) and two tied global allocations/scenarios. All three
used identical solver parameters. The evidence supports a numerical failure of
the very large, degenerate secondary QP—not a recourse-formulation failure or a
parameter mismatch.

## Reporting-only recovery

Only the exact status-13 exception activates the recovery path; all other
errors still propagate. The status-13 candidate is diagnosed and rejected.
Using the same fixed `x` and the same `1e-7` economic bands, the recovery uses
two deterministic continuous LP stages:

1. minimize total shortage in every separable block;
2. retain each block's minimum shortage within `1e-7`, then minimize
   region-order-weighted shortage.

The final LP was `OPTIMAL`, had constraint violation
`1.3500311979441904e-13`, and maximum block-cost deviation
`1.0000803740695119e-7`, which is within the unchanged economic band plus the
existing feasibility tolerance. The reported worst-recourse shock set contains
four items and respects `Gamma=4`. The certified robust recourse remains
`631019.8562277922`.

The fallback can change only representative recourse flows and derivative
reporting fields among economically admissible solutions. It cannot mutate the
first-stage solution or primary objective.

## Verification and scope

The formal rerun finished with objective `708428.6873031154`, lower bound
`708428.6873031153`, relative gap `1.6432892105218233e-16`, exact certification
PASS, RI `3.21972926956679e-11`, RS `4.489841057469114e-13`, and a feasible
four-item Gamma allocation. Result, first-stage-solution, and provenance files
are complete and their recorded hashes validate.

The original failed reporting attempt used 2 auxiliary optimizer calls. The
recovery, formal verification, and audit then used 28 calls: 6 during recovery
and formal reporting, 4 in the initial comparator audit, and 18 across three
fixed-state diagnostic passes. The total reporting-layer count is therefore
30. It performed no extra first-stage optimization beyond the one necessary
formal rerun. No other E4 case was rerun.

The E4 runner is safe to resume. No model, dataset, Gamma grid, `B_ref`, beta,
`lambda_R`, tolerance, primary solver profile, E1, E2, or E3 artifact changed.
