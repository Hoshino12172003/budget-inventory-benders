# Formal experiment protocol

## Freeze status

**BLOCKED. Formal execution is not authorized.** Every E1–E7 configuration contains `formal_run_authorized: false`; the guarded runner performs no write and refuses `--execute` before importing or calling a solver.

The audit found four blockers:

1. `origin/main` contains PR #1 but not the stacked PR #2–#7 content. The latest validated implementation exists on the PR #6/#7 branch chain, not on `main`.
2. The requested formal cases are 210202 and 210712, while the repository contains 210202 and 210628. No 210712 formal instance, baseline inventory, calibration, or provenance artifact exists.
3. `B_ref` is frozen for 210202 and 210628, but the calibration artifact explicitly says `formal_levels_frozen=false`. Therefore no formal `B^0`, `Gamma^0`, or `lambda_R^0` currently exists. The development recommendation is `beta=1`, `Gamma=2`, and `lambda_R=0.05`; it is not silently promoted to a formal anchor.
4. Direct and PRB solve the same mathematical formulation, but their internal solver tolerances differ (`1e-8` for Direct versus `1e-9` for PRB master/product LPs). E1 requires an approved shared tolerance profile.

The frozen reference expenditures currently available are `B_ref(210202)=84614.30513135393` and `B_ref(210628)=50558.18771213083`. There is no valid `B_ref(210712)`.

## Frozen mathematical content on the validated branch chain

The validated PR chain contains Robust Inventory Reconfiguration with baseline `x0`, final `x`, nonnegative `a_plus/a_minus`, `x-x0=a_plus-a_minus`, and symmetric friction coefficient `lambda_R*h`. Depot activation means operating an existing depot. Recourse retains shipment, shortage, and service-violation variables under binary budgeted demand shocks.

PRB-Benders uses exact product-wise recourse separation, exact local shock counts, all global allocations satisfying `sum_j gamma_j <= Gamma`, global lower and upper bounds, and final exact robust certification. The optimal-face correctness contract classifies the 72-case development grid as 70 exact identities, 2 optimal-face equivalents, and 0 failures.

The source-observed Renault initial-inventory audit exists but found all-zero values and did not recommend them directly as `x0`. Subsequent development solves use the separately frozen nominal incumbent baseline artifacts as the operational reconfiguration baseline. This distinction must remain explicit in formal reporting.

## Safety and execution lifecycle

Protocol inspection is allowed with:

```powershell
$env:PYTHONPATH='src'
python experiments/audit_protocol.py
python experiments/run_formal.py experiments/configs/formal/e1_algorithm_benchmark.yaml
```

The second command prints a plan only. `--execute` currently raises `PermissionError`. Formal execution requires a later PR that resolves every blocker, records explicit authorization, and implements reviewed solver dispatch.

Before any run, the runner must bind one immutable run identity: source dataset SHA-256, processed/formal instance SHA-256, parameter SHA-256, nominal-baseline `x0` SHA-256, canonical config SHA-256, Git commit, Python version, solver version, and random seed where applicable. Because parameters and processed data currently share the same formal-instance JSON, their recorded hashes are identical and must be labelled as one shared artifact rather than falsely implying separate files.

Checkpoints may resume only when every identity field matches. A mismatch in config, source data, processed data, parameters, `x0`, or Git commit is fatal. Results use the unified schema and keep non-applicable fields explicitly `null`; missing columns are invalid.

## E1 Direct identity requirement

Direct means the current factorized exact extensive formulation, not a heuristic, relaxation, or deliberately inefficient literal global-scenario replication. It must receive the same case artifact, `x0`, `B`, `Gamma`, `lambda_R`, uncertainty semantics, costs, recourse/service equations, integrality assumptions, and approved solver tolerances as PRB. The static identity audit passes every mathematical item and fails only the current tolerance equality check. Peak memory is nullable until a reliable process-level recorder is reviewed.

## Formal readiness gate

Formal execution remains blocked until:

- PR #2–#7 content is integrated into `main` and retested there;
- the intended second case is resolved explicitly as 210712 or 210628, with complete instance, `x0`, calibration, and provenance artifacts;
- formal `B^0`, `Gamma^0`, `lambda_R^0`, E3 budget levels, and interaction levels are approved;
- Direct and PRB share one frozen solver-tolerance profile;
- an authorized execution PR changes `formal_run_authorized` only after the preceding checks pass.
