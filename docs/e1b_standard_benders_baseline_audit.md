# E1b Standard Benders baseline audit

## Result

`MATHEMATICAL_BASELINE_AUDIT = PASS`

`STANDARD_AGGREGATE_CUT_VALID = true`

`GLOBAL_GAMMA_COUPLING_PRESERVED = true`

`PRB_STRUCTURED_MASTER_USED = false`

The implementation in `src/robust_inventory_reconfiguration/standard_benders.py`
has a standalone first-stage master with exactly one robust-recourse surrogate.
The exact oracle returns one aggregate cut obtained from a single feasible
global uncertainty realization selected at the current point. The derivation in
the protocol proves global validity and generating-point tightness.

## Independence and fairness

The Standard master has no `eta` variables and accepts no PRB cut pool, warm
start, or iteration history. It shares only scientifically common components:
the first-stage equations, exact product recourse LP oracle, Gamma composer,
solver profile, and artifact utilities. Unit tests inspect the master variable
names and public solver signature in addition to numerical validity checks.

The eight frozen E1a PRB results contain adequate comparable core timings and
component timings, so a timing-only PRB rerun is not required. All eight record
Gurobi `13.0.2` on the same hardware identity. The currently attached Python
environment reports Gurobi `13.0.1`; therefore formal authorization remains
false and the runner enforces `13.0.2` before any Standard solve. This is an
environment readiness condition, not a mathematical or implementation defect.

## Verification scope

Small exact tests compare Direct, Standard BD, and PRB at Gamma 1 and 2. Other
tests check aggregate-cut validity at multiple inventory points, tightness,
dual feasibility, exact risk-budget composition, Gamma feasibility, absence of
PRB master state and cut reuse, termination, certification, authorization
fail-closed behavior, immutable E1a PRB hashes, and the eight-case protocol
identity. No Renault E1b optimization was executed.

## Execution decision

The mathematical baseline and implementation are ready. Formal execution is
not yet authorized and must use the frozen `13.0.2` solver environment. After an
explicit authorization patch in that environment, the eight Standard runs may
proceed. Until then the operational classification is
`E1B_STANDARD_BENDERS_BLOCKED` with blockers `FORMAL_AUTHORIZATION_FALSE` and
`SOLVER_VERSION_13.0.2_REQUIRED`.

