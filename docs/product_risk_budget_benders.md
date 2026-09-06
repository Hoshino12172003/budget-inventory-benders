# Product-wise Risk-Budget Decomposed Benders

## Scope

PRB-Benders changes only the solution method for the frozen Reconfiguration Model V2. It does not change `x0`, the selected `lambda_R` levels, `B_ref`, `beta = B/B_ref`, the binary uncertainty set, recourse, service, Renault data, or any Step 1–3 parameter. This is a correctness implementation, not a performance experiment.

For fixed inventory and uncertainty, recourse separates by product:

```text
Q(x,z) = sum_j Q_j(x[:,j], z[:,j]).
```

For product `j` and an exact local shock count `g`, define

```text
V[j,g](x_j) = max { Q_j(x_j,z_j) : z_j binary, sum_r z[r,j] = g }.
```

The global uncertainty set uses at most `Gamma` shocks. Its exact composition is

```text
Q^R(x) = max { sum_j V[j,gamma_j](x_j) : gamma_j integer >= 0,
                                                    sum_j gamma_j <= Gamma }.
```

The implementation enumerates local product patterns with exactly `g` shocks. With 12 regions and `Gamma=2`, each product has `1 + 12 + 66 = 79` patterns. It does not construct the 4,657 global scenarios as the algorithmic structure. Canonical risk allocations include sums below `Gamma`; for 8 products and `Gamma=2`, there are 45.

## Master and bounds

The exact master retains `y`, `x`, `a_plus`, and `a_minus`, with the frozen activation, capacity, inventory-bound, reconfiguration-balance, and financial-budget constraints. It adds `eta[j,g]` and `theta`:

```text
eta[j,g] >= alpha[j,g,k] + sum_i beta[i,j,g,k] x[i,j]
theta >= sum_j eta[j,gamma_j]                    for every feasible gamma vector
minimize C_FS + theta.
```

Every master is solved with zero requested MIP gap. Its optimal objective is the global lower bound. At each incumbent, every `(j,g)` is separated exactly and every violated product cut is added. The exact upper-bound candidate is `C_FS + max_gamma sum_j V[j,gamma_j](x_j)`; the algorithm keeps the best historical candidate.

Termination requires both relative `UB-LB` gap at most `1e-6` and no product-cut violation above `1e-7`. The returned incumbent then receives a fresh exact product-pattern evaluation and full risk-budget composition. A small master nonnegativity tolerance projection is applied only when a solver reports `x` in `[-1e-7,0)`; a materially negative value is an error.

## Complete recourse and exclusions

Shortage `u` and service violation `e` make every fixed-inventory recourse problem feasible. An infeasible product LP therefore indicates an implementation error; feasibility and Farkas cuts are unnecessary.

This implementation contains no adaptive or inexact gaps, core-point or Pareto cuts, stabilization, trust region, level method, cut deletion, cross-product cut aggregation, CCG, handoff logic, warm-start heuristic, callback-only logic, parallelization, or Renault-specific performance tuning.

Post-solve service reporting calls the frozen exact evaluator from PR #5; PRB-Benders does not define a second service metric.

## Correctness result

The exhaustive tiny checks match literal global enumeration, the factorized exact formulation, and PRB-Benders for both `Gamma=1` and `Gamma=2`. All generated cuts pass global validity and generation-point tightness checks, and random fixed-inventory tests confirm exact risk-budget composition.

On the 72-case Renault grid, all 72 runs are optimal and match objective, first-stage expenditure, robust recourse, depot activation, and frozen service reporting tolerances. Seventy return coordinate-wise identical inventory. The other two—210202 with `lambda_R=0`, `beta=1.10`, and `Gamma` equal to 1 or 2—were subsequently verified by independent fixed-inventory audits as different members of the same certified global optimal face. Under the [optimal-face correctness contract](optimal_face_correctness_contract.md), the classification is 70 `EXACT_SOLUTION_IDENTITY`, 2 `OPTIMAL_FACE_EQUIVALENT`, and 0 `FAIL`; therefore `PRB_BENDERS_CORRECTNESS_PASS = true`. No tie-break or canonicalization was introduced.
