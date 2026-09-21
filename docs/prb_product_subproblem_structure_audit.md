# PRB product-subproblem structure audit

This is a development-only implementation audit. It changes no model, uncertainty set, master, cut, tolerance, or certification contract.

## Exact product-state formulation

For product `j`, inventory vector `x_j`, and a fixed shocked-region set `S` with `|S|=g`, demand is `d_r = dbar_rj + dhat_rj 1[r in S]`. The recourse variables are shipments `q_ir >= 0`, shortages `u_r >= 0`, and service violation `e >= 0`. It minimizes `sum_ir c_irj q_ir + sum_r p_rj u_r + s_j e`, subject to `sum_i q_ir + u_r >= d_r`, `sum_r q_ir <= x_ij`, and `sum_r u_r - e <= (1-alpha_j) sum_r d_r`.

With demand duals `pi_r >= 0`, supply duals `mu_i <= 0`, and service dual `sigma <= 0`, the dual maximizes `sum_r d_r pi_r + sum_i x_ij mu_i + A sigma`, subject to `pi_r + mu_i <= c_irj`, `pi_r + sigma <= p_rj`, and `-sigma <= s_j`. The Benders cut has intercept `sum_r d_r pi_r + A sigma` and inventory coefficients `mu_i`.

For fixed `g`, `V_jg(x_j)` is the maximum recourse value over all `g`-region shock patterns. The cut returned by the maximizing pattern is therefore a globally valid supporting cut for `V_jg` and is tight at the generation point.

## Exploitable structure and decision

Each fixed-pattern LP is a continuous capacitated transportation/min-cost-flow problem. The service term can be represented by an allowance-shortage source of capacity `A` with regional costs `p_rj`, plus an unlimited excess-shortage source with costs `p_rj+s_j`. Arbitrary depot-region transport costs, shared depot capacities, and the shared allowance pool prevent independent sorting or continuous-knapsack evaluation.

A custom min-cost-flow implementation would also have to return numerically valid capacity duals under degeneracy. No repository implementation provides that contract, so no closed-form, sorting, or custom-network solver safely replaces Gurobi. The exact sparse-matrix prototype retains Gurobi and batches all scenario blocks; it is exact but slower on L and XL-low and is not promoted.

V2 already maintains one Gurobi model per product, not one model per `g`. It contains `1 + R + R(R-1)/2` independent scenario blocks at Gamma=2. V3 keeps one model per product but replaces per-block Python construction with one sparse matrix insertion and bulk RHS/value/dual operations.

## Exactness audit

The audit covered 136 product/inventory vectors and 408 `(product,x_j,g)` states. Maximum value, cut-tightness, and strong-duality errors were respectively `1.164e-10`, `1.164e-10`, and `1.164e-10`. Maximum demand-dual, supply-dual, cut-intercept, and cut-slope differences from V2 were `4.441e-16`, `1.776e-15`, `0.000e+00`, and `1.776e-15`. Every dual was feasible and all worst patterns matched V2.

## Solver micro-audit

The predeclared profiles were Auto, primal simplex with Presolve 0/1, and dual simplex with Presolve 0/1/2, all with unchanged formal feasibility and optimality tolerances, Threads=1, and LPWarmStart=2. Auto had the lowest total solve time on the deterministic XL-low sample and remains selected; no solver parameter is changed.

## Development benchmark

| Case | Pure median | V2 median | V3 median | V3/Pure | V3/V2 | V3 oracle median | Peak GiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| 210202 | 0.407s | 1.038s | 0.676s | 1.66x | 0.65x | 0.152s | 0.14 |
| L | 0.817s | 3.230s | 7.942s | 9.72x | 2.46x | 2.329s | 1.34 |
| XL_low | 1.610s | 6.583s | 21.884s | 13.59x | 3.32x | 7.770s | 3.38 |

All six end-to-end V3 runs match the frozen objective and recourse within the existing formal tolerance, retain the same `y`, have only floating-point-scale `x` differences, and pass global coupling and exact certification. The prototype nevertheless increases L and XL-low time because sparse-matrix/environment construction and full primal/dual extraction outweigh fewer Python model-building calls.

Relative to V2, the measured construction reductions for 210202/L/XL-low are 40.8%, -151.5%, -241.3%, and cumulative product-optimization reductions are -24.1%, -158.7%, -234.0%. Negative values denote regressions. Static scenario coefficients and sparse indices are fully precomputed, but this does not yield a net large-instance gain.

Final classification: `NO_SAFE_STRUCTURAL_SIMPLIFICATION`.

E2--E7 reruns: 0. Paper text changed: no. Eight-case expansion: no.
