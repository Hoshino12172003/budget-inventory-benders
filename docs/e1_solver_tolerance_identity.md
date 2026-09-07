# E1 solver-tolerance identity

`E1_SOLVER_NATIVE_TOLERANCE_IDENTITY=PASS`.

| Setting | Direct | PRB master | PRB product LP |
| --- | ---: | ---: | ---: |
| FeasibilityTol | `1e-8` | `1e-8` | `1e-8` |
| OptimalityTol | `1e-8` | `1e-8` | `1e-8` |
| IntFeasTol | `1e-8` | `1e-8` | not applicable |
| MIPGap | `0` | `0` | not applicable |
| NumericFocus | `0` | `0` | `0` |
| BarConvTol | no override | no override | no override |

The single code source is `src/robust_inventory_reconfiguration/solver_profile.py`.
The profile controls solver-native numerical behavior only.

PRB certification remains: relative gap `1e-6`, cut violation `1e-7`, objective
absolute certification `1e-4`, and global coupling `1e-6`. These gates are not
used to give either E1 method a solver-native advantage.

## Tolerance classification

- Solver-native formal profile: the six settings in the table above.
- PRB algorithmic/certification: relative gap, cut violation, objective absolute
  certification, and global-coupling checks. These remain frozen.
- Correctness-comparison tolerances: objective/component `1e-4`, `x` `1e-5`,
  fill-rate `1e-6`, and feasibility `1e-6` in the existing correctness grid.
  They validate formulations and are not passed to the formal solver.
- Numerical interface/reporting guards: negative-inventory interface threshold
  `1e-7`, dual-sign check `1e-8`, and canonical service tie tolerance `1e-12`.
  They do not relax solver optimality or formal certification.
- Development-only nominal-baseline generation retains its historical `1e-9`
  settings. It is not an E1 Direct or PRB solve and is not rerun here.
