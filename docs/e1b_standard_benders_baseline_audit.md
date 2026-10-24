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

Evidence reconciliation: the Standard-BD implementation and its recovered raw
results are independently auditable, but the eight E1a PRB comparison sources
are missing. PRB cells are therefore `HISTORICAL_SUMMARY_ONLY`, not
`PRIMARY_VERIFIED`.

The Standard master has no `eta` variables and accepts no PRB cut pool, warm
start, or iteration history. It shares only scientifically common components:
the first-stage equations, exact product recourse LP oracle, Gamma composer,
solver profile, and artifact utilities. Unit tests inspect the master variable
names and public solver signature in addition to numerical validity checks.

The historical summary reports comparable PRB timings, but the eight source
`result.json` files cannot be independently inspected. Those timing fields may
not be used for a confirmatory Standard-versus-PRB speed comparison. The
historical E1a/E1b protocol records Gurobi `13.0.2`. Execution-readiness was
revalidated with
`C:\Users\Hu Jiaxin\Documents\Codex\2026-07-07\z\work\paper-code\.venv\Scripts\python.exe`.
That runner context imports `gurobipy 13.0.2`, native Gurobi `(13, 0, 2)`, from
the environment's `Lib\site-packages\gurobipy\__init__.py`. The earlier
`13.0.1` observation came from the unrelated system-Python executable and is
not an E1b execution blocker.

The authorization manifest preserves the eight expected paths and hashes, but
the files are absent and zero expected hashes were recovered. Later development
records match all eight instance and x0 identities and objectives, with 7/8
strict certifications; they remain `DEVELOPMENT_CROSSCHECK` evidence and do
not validate the original runtime fields. No formal optimization was invoked.

## Verification scope

Small exact tests compare Direct, Standard BD, and PRB at Gamma 1 and 2. Other
tests check aggregate-cut validity at multiple inventory points, tightness,
dual feasibility, exact risk-budget composition, Gamma feasibility, absence of
PRB master state and cut reuse, termination, certification, authorization
fail-closed behavior, immutable E1a PRB hashes, and the eight-case protocol
identity. No Renault E1b optimization was executed.

## Execution decision

The mathematical baseline remains valid. Any historical Standard-BD results
with their own raw evidence may be retained, but the paired PRB performance
claim is source-incomplete. The scientific comparison classification is
`E1B_PRB_COMPARISON_HISTORICAL_SUMMARY_ONLY`.
