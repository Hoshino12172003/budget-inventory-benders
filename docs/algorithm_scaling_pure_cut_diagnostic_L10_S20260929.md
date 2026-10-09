# Pure Benders focused cut-validity diagnostic

## Scope

Only `ASC_L10_S20260929_PURE_BENDERS` was reproduced. The diagnostic loaded the
existing identity-verified prepared instance and wrote a separate artifact. It did
not write a formal result, overwrite any successful L10 artifact, execute another
seed, or execute XL10/XXL10.

## Finding

Classification: `CUT_RECONSTRUCTION_MISMATCH`.

The failure is not an invalid cut and not a master-feasibility failure. At master
iteration 12, cut 10 (added at iteration 11) was binding with exact reconstructed
residual zero. The new oracle returned the exact same alpha and all 300 beta
coefficients. The actual Gurobi row also matched

`theta - sum_ij beta_ij x_ij >= alpha`

with zero coefficient difference, zero intercept difference, and zero row
violation. All 11 previously added master cuts matched their stored algebraic
representations; none had a positive violation.

The guard was instead triggered by comparing the certified fixed-scenario primal
recourse value with theta:

| Quantity | Value |
|---|---:|
| theta | 2,221,515.797109686 |
| candidate/stored cut RHS | 2,221,515.797109686 |
| certified fixed-scenario value | 2,221,515.7971099215 |
| actual previous-cut violation | 0.0 |
| primal-certification value minus theta | 2.3562461137771606e-07 |
| relative trigger residual | about 1.061e-13 |

Thus the reported exception text says a previous cut remains violated, while the
previous cut is exactly satisfied. The `2.356e-07` trigger is the candidate cut's
recorded primal-dual strong-duality residual.

## Tolerance comparison

| Tolerance | Value | Trigger / tolerance |
|---|---:|---:|
| formal cut check | 1e-7 | 2.356 |
| Gurobi FeasibilityTol | 1e-8 | 23.562 |
| Gurobi OptimalityTol | 1e-8 | 23.562 |
| Gurobi IntFeasTol | 1e-8 | 23.562 |
| project dual-feasibility/global-coupling scale | 1e-6 | 0.236 |
| objective certification | 1e-4 | 0.00236 |

Master status was optimal, MIPGap was `3.258981259790416e-13`, and all stored cut
rows were feasible. Raising the cut tolerance would hide the semantic mismatch and
is not the proposed repair.

## Exact source and minimal proposed fix

In `src/robust_inventory_reconfiguration/pure_benders.py`, current line 353 uses:

`violation = evaluated.value - theta`

Here `evaluated.value` is the certified fixed-scenario primal value, whereas the
constraint added to the master uses `evaluated.cut.alpha` and
`evaluated.cut.beta`. The minimal proposed fix, not applied in this diagnostic, is
to validate the cut using:

`evaluated.cut.value_at(xbar) - theta`

while retaining `evaluated.value` for the certified upper bound. This changes no
cut, scientific parameter, solver tolerance, or stopping tolerance; it makes the
guard validate the expression it claims to validate.
