# Basic-BD scaling and XXL10 Direct readiness

## Decisions

- Basic-BD L10 seed 20260921: `READY_FOR_SINGLE_PILOT_AUTHORIZATION`; authorization remains false.
- XXL10 Direct seed 20260921: `BLOCKED_BY_RESOURCE`; authorization remains false.
- Optimization calls made by this preparation: 0.

## Basic-BD identity and frozen evidence

The reused implementation enumerates every admissible global shock scenario, solves one reusable all-product recourse LP per scenario, and adds at most one aggregate optimality cut per Benders iteration. Static source checks confirm that its oracle does not instantiate the Global-BD adversarial MILP and does not call Aggregate/PRB product-risk composition. The Renault micro Direct comparison, dual feasibility, strong duality, cut validity, 8/8 Basic certifications, and archived SHA manifests all pass.

## Theoretical workload

| Size | Global scenarios/oracle call | Reusable LP variables | Reusable LP constraints | Max scenario LP solves (502 calls) |
|---|---:|---:|---:|---:|
| L10 | 41,617 | 7,500 | 600 | 20,891,734 |
| XL10 | 88,411 | 13,034 | 854 | 44,382,322 |
| XXL10 | 166,177 | 21,328 | 1,168 | 83,420,854 |

These are formula counts, not measured runtimes or memory peaks. Sequential scenario-LP enumeration is the dominant expected bottleneck; the implementation reuses one LP, so it does not materialize all scenarios in memory.

## Frozen pilot resource contract

- One allowlisted development condition only: `BASIC_L10_S20260921`.
- 900 seconds total, 4 GiB process tree, 7 GiB startup availability, 3 GiB system floor, 20 GiB disk gate, 0.25-second monitoring, one process, no automatic retry.
- Scaling V2 tolerances and maximum 500 iterations are unchanged; the scenario safety cap is frozen once at 166,177.

## Convergence comparability

The archived Scaling V2 CSV contains complete LB/UB/gap/cumulative-time trajectories for 89 certified conditions. It correctly excludes the non-certified Global-BD XXL10 seed 20260925. No Basic-BD scaling trajectory exists yet, so a fair four-Benders gap comparison cannot be produced until an authorized Basic-BD run persists the same fields. Direct MIP progress is not treated as a Benders LB/UB trajectory.

## XXL10 Direct

Live available RAM is 14.108 GiB and free disk is 246.329 GiB. The unchanged gate is 16 GiB available RAM, 13 GiB process-tree cap, 3 GiB system floor, 20 GiB disk, and 900 seconds. The static model estimate remains 14,227,589 variables, 791,070 constraints, and 43,069,377 nonzeros; no XXL10 Direct model was built.

A larger-RAM migration must preserve Python/Gurobi, solver-profile, code/config/instance hashes, single-process monitoring, resource gates, archival, and certification. Because the historical Scaling V2 solver version is not verifiable, exact historical software identity must not be claimed.
