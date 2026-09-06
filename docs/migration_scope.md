# Selective migration scope

## Retained

- The identity-aware subset of the legacy `InventoryInstance` fields needed by the current paper.
- Budgeted binary demand uncertainty semantics from `src/scenarios.py`.
- Recourse variables, constraints, and objective semantics from `src/subproblem.py`.
- Renault case `210202` and `210628` Step 3 baseline parameter snapshots and index metadata.
- A reserved location for a future minimal monolithic correctness benchmark.

The migrated code was rewritten into small modules; no legacy source file was copied wholesale. The two formal JSON snapshots were mechanically converted without changing Step 1–3 parameter values, and each output records its source hashes.

## Excluded

No old adaptive or inexact Benders code, V1/V2/V3 strengthening, core-point or Pareto/Magnanti-Wong logic, stabilization, zig-zag diagnostics, hybrid Benders-to-CCG or handoff logic, Farkas machinery, adaptive gap schedules, secondary cut selection, certification state machines, experiment runners, final holdout infrastructure, fairness modules, fulfillment-flexibility diagnostics, or historical result artifacts were migrated.
