# E1c Gamma-sensitivity development probe

## Status

`EVIDENCE_INSUFFICIENT`

The protocol and dry-run passed, but the execution gate stopped before the
first optimization. Available RAM was 15.911839 GiB, below the frozen 18 GiB
preflight requirement. The 14 GiB process-tree stop, 3 GiB system emergency
stop, 0.25-second monitor interval, and 900-second per-method timeout were not
changed.

This is a development-only probe. It is not a paper-final experiment and no
result is eligible for paper statistics.

## Frozen design

- Prepared instance: E1c L/PREPARE, seed 20260911.
- Dimensions: \(I=25,R=24,J=12\), so \(RJ=288\).
- Instance SHA-256:
  `f78bc7a03d913ffde4d2593b1fb61b3456e15cf7918c0ed5d0df6028bac1aa23`.
- x0 SHA-256:
  `39d3a0f6612fbbbbaf265e22813c26f72c3b975d8dfc55b7b134c3bc256ea444`.
- B_ref: 139324.8800849306.
- Gamma: 2, 4, 6, 8.
- Methods: Current Pure Benders, Aggregate Benders with Structured Oracle,
  and PRB-Benders.
- beta: 1.0; lambda_R: 0.05.
- Relative gap tolerance: 1e-6; cut tolerance: 1e-7; objective certification
  tolerance: 1e-4.
- T_core includes construction, master solves, oracle/subproblem solves, cut
  generation, convergence checks, and exact final certification. Reporting
  and serialization are excluded.

The dry-run enumerated exactly 12 method conditions and made zero optimization
calls. It also reproduced the prepared instance, x0, and B_ref identities.

## Static complexity

Pure's global adversarial MILP size is fixed by the L instance at 288 binary
variables, 1,176 continuous variables, and 9,217 constraints. Gamma changes
the cardinality right-hand side, not this algebraic size.

The current structured methods enumerate product-risk blocks. Their frozen
block counts are:

| Gamma | product-risk blocks |
|---:|---:|
| 2 | 3,612 |
| 4 | 155,412 |
| 6 | 2,280,612 |
| 8 | 15,259,512 |

These counts are preregistered size consequences, not measured runtimes. They
indicate a material resource risk for the structured implementations at Gamma
6 and 8, but they do not establish which method is faster.

## Gamma=2 gate

The runner is coded to execute all three Gamma=2 methods first and compare
their objectives with the immutable L probe within 1e-4. Gamma=4, 6, and 8 are
not attempted unless all three Gamma=2 runs are exact-certified and pass that
identity check.

Because the system-memory preflight failed before the first worker launch, the
Gamma=2 sanity solve did not occur. No model was constructed, no solver was
called, and no timing or memory observation was produced for any method.

## Interpretation

None of the four preregistered scientific outcomes concerning dominance or
crossover can be supported. There are no exact-certified observations from
this attempt, so runtime growth, Pure-oracle growth, PRB/Pure ratios, and
crossover are all `NOT_AVAILABLE`.

The next valid action is operational rather than scientific: retry the same
frozen runner when three consecutive available-memory samples are at least
18 GiB. The Gamma grid, methods, resource thresholds, tolerances, timeout, and
instance must remain unchanged. An existing blocked result root must be moved
to an audit archive or otherwise handled without overwriting before a retry.

`formal optimization runs = 0`

`development optimization runs = 0`
