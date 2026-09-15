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
Gurobi `13.0.2` on the same hardware identity. Execution-readiness was
revalidated with
`C:\Users\Hu Jiaxin\Documents\Codex\2026-07-07\z\work\paper-code\.venv\Scripts\python.exe`.
That runner context imports `gurobipy 13.0.2`, native Gurobi `(13, 0, 2)`, from
the environment's `Lib\site-packages\gurobipy\__init__.py`. The earlier
`13.0.1` observation came from the unrelated system-Python executable and is
not an E1b execution blocker.

Audit-only revalidation also reconfirmed all eight immutable E1a PRB result
hashes, objectives, core-runtime fields, and exact-certification statuses. The
dataset identity, mapping hash, instance hash, x0 hash, calibration/B_ref hash,
Gamma, beta, lambda_R, tolerance, thread/seed convention, and solver profile
pass for 8/8 cases. No formal optimization was invoked.

## Verification scope

Small exact tests compare Direct, Standard BD, and PRB at Gamma 1 and 2. Other
tests check aggregate-cut validity at multiple inventory points, tightness,
dual feasibility, exact risk-budget composition, Gamma feasibility, absence of
PRB master state and cut reuse, termination, certification, authorization
fail-closed behavior, immutable E1a PRB hashes, and the eight-case protocol
identity. No Renault E1b optimization was executed.

## Execution decision

The mathematical baseline, implementation, identities, environment, and timing
contract are ready for authorization. Formal execution remains disabled by
`formal_run_authorized = false`; this is the intended authorization boundary,
not an execution-readiness defect. The readiness classification is
`E1B_READY_FOR_AUTHORIZATION`.
