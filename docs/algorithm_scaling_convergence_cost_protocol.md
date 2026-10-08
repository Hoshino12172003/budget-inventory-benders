# Algorithm scaling and convergence-cost trade-off protocol

## Scientific question

This independent formal experiment asks whether a finer product-risk representation improves
master/lower-bound convergence enough to justify its additional oracle cost. It does not assume
that PRB is faster in wall-clock time.

The paired methods are:

1. `pure_benders`: one aggregate recourse surrogate and the global exact oracle.
2. `aggregate_benders_structured_oracle`: the same aggregate master representation with the
   structured product-risk oracle used to isolate the effect of master granularity.
3. `prb_benders`: the frozen Product-Risk-Budget master and structured oracle.

Direct deterministic-equivalent runs are excluded from this grid. The smallest frozen L10
deterministic equivalent is already a multi-million-variable expansion, and the current evidence
does not certify it as safe under the 32 GiB protocol cap. No XXXL scale is authorized.

## Frozen design

- Sizes: L10 `(I,R,J)=(25,24,12)`, XL10 `(30,30,14)`, XXL10 `(36,36,16)`.
- Seeds: integers `20260921` through `20260930`.
- Physical algorithm runs: `3 sizes × 10 seeds × 3 methods = 90`.
- Shared instance preparations: 30. These construct the frozen canonical nominal `x0` and budget
  once per instance; they are not method comparisons.
- Direct runs: 0.
- Execution is sequential. Each condition runs in an isolated monitored process.

Every condition freezes `Gamma=2`, `beta=1.0`, `lambda_R=0.05`, `SL=0.90`, and
`phi_multiplier=1.85`. The generated instance is rejected unless its service vector is exactly
0.90 and its penalty vector satisfies `phi_j = 1.85 max_r p_rj`.

## Identity and fairness

The runner records the config hash, code commit, model-source identity, source-data hashes,
prepared instance hash, canonical `x0` hash, solver profile, and method. Resume skips an existing
condition only after rechecking its hashes and exact certification; incomplete or mismatched
directories fail closed and are never overwritten.

All three methods use the same prepared instance, financial budget, scientific parameters,
solver tolerances, and exact-certification requirement. Formal reporting refuses a triple whose
objectives differ by more than `1e-4`.

## Convergence and cost accounting

Each iteration records LB, UB, relative gap, `LB / final_LB`, master time, oracle time,
certification time, cumulative time, and cuts added. Aggregate outputs retain total core,
master, oracle, certification, and measurable residual overhead time. The primary interpretation
jointly considers iteration count, lower-bound refinement, and the master/oracle split.

The only permitted final classifications are:

- `PRB_FEWER_ITERATIONS_AND_FASTER_TOTAL_TIME`
- `PRB_FEWER_ITERATIONS_BUT_HIGHER_ORACLE_COST`
- `PRB_NO_CLEAR_CONVERGENCE_ADVANTAGE`
- `SIZE_DEPENDENT_TRADEOFF`

Reporting never writes a universal “PRB is faster” conclusion without supporting paired data.
After reporting, `audit_algorithm_scaling_convergence_cost.py --post-run` independently requires
all 90 exactly certified conditions, all 30 instance records, complete trajectories/timings,
pairwise objective equivalence, no reused results, and all six required tables.

## Resource and authorization gates

The formal config remains unauthorized in this implementation phase. Before execution, the user
must explicitly change `formal_run_authorized` to true, append true to the authorization
transition, commit the change, and use a clean worktree. The runner checks static dimension caps,
samples available RAM, allows only one worker, monitors process-tree memory, and terminates a
condition at the declared memory or time cap.
