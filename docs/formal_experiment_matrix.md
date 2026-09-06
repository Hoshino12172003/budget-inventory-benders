# Formal experiment matrix E1–E7

All counts below are protocol estimates for one deterministic run per cell and two intended Renault cases. They do not authorize execution. The total is 84 runs if every unresolved level and case identity is approved.

| Group | Comparison / levels | Runs | Freeze state |
|---|---|---:|---|
| E1 | PRB versus factorized Direct on 2 Renault cases plus 4 synthetic scales | 12 | Blocked by case identity, anchors, main integration, and tolerance mismatch |
| E2 | Existing system, nominal reconfiguration, robust reconfiguration | 6 | Semantics frozen; robust anchor unresolved |
| E3 | Five budget ratios around `B_ref` | 10 | Not frozen. `{0.8,0.9,1.0,1.1,1.2}` is only a candidate until feasibility/economic audit |
| E4 | `Gamma={0,1,2,3,4}` | 10 | Gamma levels frozen by protocol; `B^0` and `lambda_R^0` unresolved |
| E5 | `{0,0.5,1,2,4} lambda_R^0` | 10 | Not frozen because `lambda_R^0` is not formal. If 0.05 is approved, implied values `{0,0.025,0.05,0.1,0.2}` all lie in the development grid |
| E6 | 3 budget × 3 risk levels | 18 | Supplementary candidate; budget levels unresolved, proposed risk levels `{0,2,4}` |
| E7 | 3 risk × 3 friction levels | 18 | Higher-priority interaction; proposed risk `{0,2,4}` and development friction `{0.0025,0.05,0.2}` are not yet formal |

## E2 semantics

- Existing system fixes `x=x0`; adjustment variables therefore represent no inventory change. Its uncertainty setting must be declared by the eventual formal decision and may not be inferred from the label. The current protocol config uses `Gamma=0` solely to compare the three requested rows consistently and remains blocked pending anchor approval.
- Nominal reconfiguration permits `x!=x0` and requires `Gamma=0`.
- Robust reconfiguration permits `x!=x0` and uses the future positive `Gamma^0`.

The value of reconfiguration compares existing system with nominal reconfiguration. The value of robustness compares nominal with robust reconfiguration. All use the same approved financial anchor and friction convention unless the final protocol explicitly documents otherwise.

## Synthetic scaling ladder for E1

The ladder is derived from the exact formulation counts at `Gamma=2`, not chosen from old fulfillment-flexibility experiments.

| Scale | `(I,R,J)` | Uncertainty terms | Local patterns/product | Global scenarios | Risk DP states | Direct variables | Direct constraints | Expected memory pressure |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Small | `(5,4,3)` | 12 | 11 | 79 | 12 | 885 | 409 | Low |
| Medium | `(10,8,5)` | 40 | 37 | 821 | 18 | 16,641 | 3,832 | Low |
| Renault-like | `(15,12,8)` | 96 | 79 | 4,657 | 27 | 122,376 | 18,629 | Moderate |
| Large | `(20,16,10)` | 160 | 137 | 12,881 | 33 | 462,341 | 52,547 | High; mandatory preflight |

For scale `(I,R,J)` and `Gamma=2`, local patterns per product are `sum_g C(R,g)`, global-scenario count is `sum_g C(RJ,g)`, risk-composition DP states are `(J+1)(Gamma+1)`, and allocation vectors number `C(J+Gamma,Gamma)`. Direct counts refer to the fair factorized product-pattern extensive formulation. They are structural counts, not runtime or memory measurements.

The 32 GB host must use a preflight stop threshold of 24 GB projected/observed process memory, leaving operating-system headroom. The qualitative memory classes are planning labels only. No synthetic model was solved in this protocol task.
