# Formal experiment protocol

## Protocol status

`PROTOCOL_READY`. Parameter, case-identity, formulation-identity, tolerance,
schema, provenance, and authorization-guard audits pass. This status approves the
protocol design only.

`formal_run_authorized=false`. The guarded runner still rejects `--execute`
before solver dispatch, and no formal result directory exists.

The formal Renault cases are `210202` and `210628`. Case `210712` exists in the
raw archive but is outside the current formal processing/calibration chain and is
not silently substituted or rebuilt.

## Frozen anchors

- `B_ref(210202)=84614.30513135393`;
- `B_ref(210628)=50558.18771213083`;
- `beta^0=1.0`, hence `B^0_case=beta^0*B_ref_case`;
- `Gamma^0=2`;
- `lambda_R^0=0.05`.

The evidence and parameter classification are recorded in
`docs/formal_parameter_freeze.md`. Every E1-E7 config references the central
machine-readable freeze and derives budgets from `beta`, never from duplicated
case-specific experimental constants.

## Solver and certification contract

Direct, PRB master, and PRB product LPs use solver profile
`gurobi-balanced-1e-8-v1`: `MIPGap=0`, `FeasibilityTol=1e-8`,
`OptimalityTol=1e-8`, `IntFeasTol=1e-8` for mixed-integer solves,
`NumericFocus=0`, and no explicit `BarConvTol` override. The profile reuses the
stable Direct/evaluator setting and remains tighter than the cut-violation gate.

PRB algorithmic/certification tolerances are unchanged: relative gap `1e-6`, cut
violation `1e-7`, objective absolute certification `1e-4`, and global coupling
`1e-6`. Solver-native feasibility/optimality tolerances are stricter than these
gates and do not weaken the frozen correctness contract.

## Reproducibility and execution guard

Each config records the formal cases, `B_ref`, budget derivation rule, parameter
grid, solver profile, central freeze source, and an execution-time Git-commit
placeholder. The central freeze records formal-instance, `x0`, calibration, and
evidence hashes. The runner binds immutable config, source, data, parameter,
`x0`, and Git identities before any future authorized run.

Checkpoint resume is permitted only when every identity matches. Results must
conform to the unified schema and retain explicit nulls for inapplicable fields.
Peak memory remains null until a reliable process-level recorder is reviewed.

Formal execution requires a separate authorization change and reviewed solver
dispatch. Protocol readiness does not grant that authority.
