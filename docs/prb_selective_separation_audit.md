# Exact selective-separation audit for Accelerated PRB V4

This development audit changes no model, master, product cut, uncertainty set, tolerance, termination tolerance, or exact-certification contract. V2 remains the recommended implementation.

## Safe state upper bound

For a previously solved exact inventory vector `x'_j`, define `L_ij = max_r [p_rj + s_j - c_irj]_+`. Starting from any feasible recourse plan at `x'_j`, every unit of shipment lost when inventory falls to `x_j` can be replaced by shortage in its destination region. Its incremental shortage plus possible service-violation cost, net of the removed transport cost, is at most `L_ij`. Inventory increases cannot increase recourse. Therefore, for every pattern and hence for its fixed-g maximum,

`V_jg(x_j) <= V_jg(x'_j) + sum_i L_ij (x'_ij-x_ij)_+`.

Taking the minimum over all cached exact states preserves a valid upper bound. If this bound is no larger than the current `eta_jg` plus the frozen cut tolerance, the state cannot produce a violated product cut.

## Exact Gamma screening

For a candidate `(j,g)`, V4 fixes that state and solves the exact risk-budget DP over all other products using their valid upper bounds and residual budget `Gamma-g`. If this forced-allocation upper bound is no larger than the current `theta` plus tolerance, no feasible global allocation containing `(j,g)` can violate the global surrogate. A product solve is skipped only when every local-g state is certified safe by one of these two proofs. Otherwise V4 falls back to the unchanged exact product solve.

## Why g-monotonicity is not used

`V_j,0 <= ... <= V_j,Gamma` is not guaranteed by the frozen formulation. Increasing demand also increases the allowed shortage `(1-alpha_j) sum_r d_rj`; cheap shipment to the newly increased region can relax an existing service-violation charge elsewhere. Nonnegative demand deviations alone therefore do not prove monotonicity. V4 assumes neither monotonicity nor convex/concave marginal risk increments.

## V2 state audit

Across the three instrumented V2 runs, 195 product-risk states were physically solved after exact-cache reuse; 56 (28.7%) produced no new cut. The detailed per-iteration table is `artifacts/prb_v2_state_solve_audit.csv`.

## V4 outcome

V2's product oracle solves all `g=0,1,2` blocks together. Although the bounds certify a few individual states safe, no changed product had every local-g state certified safe. The strict fallback therefore selected every changed product, giving zero screening-avoided physical state solves. Final full-state verification checked every state, required zero additional physical solves because the identical states were already in the exact cache, and found zero missed violations.

| Case | Pure | V2 | V4 | V4/Pure | Screening avoided | Missed |
|---|---:|---:|---:|---:|---:|---:|
| 210202 | 0.407s | 1.038s | 0.971s | 2.39x | 0 | 0 |
| L | 0.817s | 3.230s | 3.309s | 4.05x | 0 | 0 |
| XL_low | 1.610s | 6.583s | 7.806s | 4.85x | 0 | 0 |

All V4 runs match the frozen objective and recourse, preserve `x/y`, pass first-stage feasibility, Gamma coupling, and exact certification, and use unchanged tolerances. Because the safe screening ratio is zero, V4 is not promoted and the experiment is not expanded.

Final classification: `LIMITED_SAFE_SCREENING_OPPORTUNITY`.

E2--E7 reruns: 0. Paper text changed: no.
