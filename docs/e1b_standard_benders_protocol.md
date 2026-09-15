# E1b Standard Benders versus PRB protocol

## Scientific question

E1b asks whether exploiting product-wise recourse separability and the global
risk-budget structure provides computational gains beyond standard Benders
decomposition itself. E1a remains the Direct-versus-PRB exactness and
full-formulation comparison. E1b is the Standard-BD-versus-PRB algorithmic
ablation and attributes any measured difference to decomposition structure.

## Standard Benders formulation

The Standard master contains the unchanged first-stage variables
`y`, `x`, `a_plus`, and `a_minus`, plus one nonnegative aggregate surrogate
`theta`. It retains the activation, capacity, inventory upper-bound,
reconfiguration-balance, and financial-budget constraints. Its objective is
first-stage expenditure plus `theta`. It contains no `eta[j,g]`, product-budget
surrogate, or PRB cut pool.

For a fixed `x`, let `Q[j,g](x_j)` be the worst product-j recourse among shock
patterns of cardinality exactly `g`. The unchanged global robust recourse is

    Q^R(x) = max_{gamma: sum_j gamma_j <= Gamma} sum_j Q[j,gamma_j](x_j).

The Standard oracle may evaluate this expression with the existing exact
product LPs and exact risk-budget composition. This is oracle reuse only: the
Standard master receives one aggregate cut and never sees product-budget state.

## Aggregate cut derivation

At a generated point `x^k`, the oracle selects a maximizing allocation
`gamma^k`. For each product it selects a worst pattern at that local allocation.
LP duality supplies

    Q[j,gamma^k_j](x_j) >= alpha^k_j + sum_i beta^k_ij x_ij.

Summing these inequalities gives

    theta >= alpha^k + sum_ij beta^k_ij x_ij,

where `alpha^k = sum_j alpha^k_j`. The selected allocation and patterns form a
feasible global uncertainty realization because `sum_j gamma^k_j <= Gamma`.
Consequently its scenario recourse is bounded above by `Q^R(x)` for every `x`,
so the affine expression is a global lower bound on `Q^R`. At `x^k`, each
selected product pattern is worst for its local allocation, the allocation is
globally maximizing, and strong duality makes every product cut tight. The
aggregate cut is therefore tight at `x^k`. It uses only the current point and
current oracle solution, not future information.

This establishes an exact classical Benders supporting-cut contract while
fully preserving global Gamma coupling. Failure of dual feasibility or the
strong-duality audit blocks certification; heuristic cuts are prohibited.

## Structural boundary from PRB

Both methods may share the instance loader, first-stage equations, exact
recourse LP implementation, solver profile, tolerance constants, and reporting
utilities. Standard BD may use product decomposition inside its exact oracle.
It does not expose that structure to its master. It may not use `eta[j,g]`,
product-budget cuts, the PRB structured master, a PRB final cut pool, a PRB warm
start, or PRB iteration history. PRB starts without any E1a cut-pool reuse.

## Fairness contract

Every comparison uses `RENAULT_EMPIRICAL_8CASE_V1`, its frozen instance and x0
hashes, case-specific B_ref, Gamma 2, beta 1.0, lambda_R 0.05, the same service
target, `gurobi-balanced-1e-8-v1`, default Gurobi seed 0 and automatic thread
selection, the same machine, and the same frozen tolerances. No method receives
a warm start. Presolve and other general solver defaults remain available to
both. The formal Standard runs must use the solver version recorded by the
reused E1a PRB artifacts (`13.0.2`); the runner fails closed otherwise.

## Termination and certification

The master provides the lower bound. Exact robust evaluation at each incumbent
provides a candidate upper bound. The iteration stops only when the relative
bound gap is at most `1e-6` and the current aggregate-cut violation is at most
`1e-7`. The returned incumbent is then independently re-evaluated by the exact
fixed-first-stage oracle. Its certified objective must reproduce the upper bound
within `1e-4`; all generated cuts must pass dual-feasibility and strong-duality
checks. The result stores LB, UB, absolute and relative gaps, iterations, the
final first-stage solution, and certification status. A Standard/PRB objective
difference above `1e-4` is `E1B_OBJECTIVE_MISMATCH_<case>` and does not trigger
tolerance adjustment.

## Timing and metrics

The primary comparison is `core_runtime_seconds`, excluding exhaustive service
evaluation and reporting. Standard timing additionally records master, exact
oracle, aggregate-cut construction, and final certification time. The frozen
E1a PRB `runtime_seconds` is its comparable core time and already excludes its
later service evaluation; its master, subproblem, and certification components
are available for all eight cases. No PRB timing-only rerun is currently needed.

Reported metrics are objective and difference, Standard/PRB core runtime and
speedup, iterations, total cuts, cuts per iteration, master time, oracle or
subproblem time, final gap, certification, timeout, and peak memory when it can
be measured reliably. Standard aggregate cuts and PRB product-level cuts have
different granularity; their counts are descriptive and are not ranked as if
they were equivalent units.

## Execution grid and artifact contract

The cases are `210129`, `210202`, `210310`, `210323`, `210330`, `210428`,
`210611`, and `210628`, each with its case-specific depot set, 12 regions, and
the frozen eight products. Only eight new Standard runs are planned. PRB rows
are immutable references to the corresponding E1a artifacts. The local runner
validates authorization, a clean worktree, dataset and per-case identities,
solver/hardware compatibility, and the referenced PRB artifact before solving.
It refuses overwrite and writes through an isolated partial directory.

## Failure and blocker rules

Execution is blocked by false authorization, an identity/hash/environment
mismatch, dirty Git state, an existing run or partial directory, invalid or
nontight aggregate cuts, lack of exact certification, or an objective mismatch.
Timeout is recorded as a failed formal condition and is not repaired by changing
the frozen profile. Controlled scaling and E2-E7 are outside this protocol.

