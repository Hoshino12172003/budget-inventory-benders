# Direct exact scaling extension protocol

## Scope and identity

This protocol adds one `direct_exact` observation for each of the 30 immutable prepared instances in `ALGORITHM_SCALING_CONVERGENCE_COST_V2_REPAIRED_GUARD`. It does not regenerate instances and does not modify the 89 certified or one documented non-certified three-method observations. Each Direct condition consumes the tracked `instance.json` and `preparation.json` after checking their hashes, dimensions, seed, `x0`, `B_ref`, budget, and scientific parameters.

Formal execution is disabled until a separate authorization commit changes `formal_run_authorized` to true. The new Direct batch is internally frozen to one environment: Python 3.12.7, gurobipy/native Gurobi 13.0.1, the existing solver profile, a clean committed worktree, one-worker execution, and the size-specific RAM gate. This is a consistent environment for all new Direct conditions, not a claim of exact software-environment identity with Scaling V2. Scaling V2 did not persist its interpreter or Gurobi version.

## Mathematical and solver contract

Direct uses the existing `build_exact_reconfiguration_model` factorized deterministic equivalent. It changes no objective, constraint, linearization, uncertainty set, `Gamma`, `beta`, `lambda_R`, service target, penalty rule, `x0`, or budget. It receives no incumbent, MIP start, cut, bound, or history from Pure, Aggregate, or PRB.

The explicit solver profile is `MIPGap=0`, `FeasibilityTol=OptimalityTol=IntFeasTol=1e-8`, and `NumericFocus=0`. `Threads`, `MIPGapAbs`, `Presolve`, `Method`, `Cuts`, and `Heuristics` retain the Gurobi 13.0.1 defaults; `Seed=0` is the frozen default. Defaults are version-dependent. Consequently, comparison with Scaling V2 is reasonable for paired instances, model, explicit profile, certification, and timing contract, but it is not labelled `EXACT_ENVIRONMENT_MATCH`.

## Timing and certification

`T_core_seconds` starts immediately before exact-model construction and stops after independent fixed-first-stage structured recourse certification. The result separately records `model_build_seconds`, `solver_optimize_seconds`, `certification_seconds`, and `total_wall_seconds`; reporting and serialization are outside `T_core` but inside total wall time. `Model.Runtime` is retained only as `solver_optimize_seconds` and is never substituted for `T_core`.

An `OPTIMAL` status is necessary but not sufficient. The independently certified first-stage expenditure plus robust recourse must reproduce the Direct objective within `1e-4`. Time limits preserve incumbent, bound, gap, node count, and status and are never reported as exact.

## Artifact and recovery contract

Each condition writes `result.json`, `first_stage_solution.json`, `provenance.json`, `solver.log`, and `resource_monitor.json` through a short sibling temporary directory followed by an atomic rename. Existing complete results are skipped only after identity and hash verification. Existing incomplete, mismatched, or uncertified outputs cause a hard failure; nothing is overwritten.

Every new result records Python, interpreter path, gurobipy and native Gurobi versions. Provenance additionally records a SHA-256 identity over the Direct runner and all model, recourse, composition, and solver-profile source files used by the run.

Runs are sequential in seed order. The timeout is the existing 900-second scaling contract. Resource stops and timeouts remain observations. The initial authorization covers only conditions passing both the environment and resource gates.
