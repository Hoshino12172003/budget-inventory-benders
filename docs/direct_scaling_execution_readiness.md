# Direct scaling execution readiness

## Current status

`NOT_READY_FOR_FORMAL_EXECUTION`

Completed without optimization:

1. 30-instance identity and SHA-256 manifest: PASS (30/30).
2. V1 versus V2 result reconciliation: PASS; final source is 89/90 V2.
3. Static Direct model sizing: PASS.
4. Fail-closed runner, short atomic path, resume identity check, sequential parent monitor: implemented.
5. Result protection and identity tests: implemented.
6. Dry-run development safety test: PASS with `optimization_calls=0`.
7. Paper-table generator: implemented; missing evidence is retained as `NOT_VERIFIABLE` or `PENDING_AUTHORIZATION`.

Blocking items:

- `formal_run_authorized=false` by design.
- Current gurobipy/native Gurobi is 13.0.1; frozen comparable environment is 13.0.2.
- The frozen interpreter path no longer exists. A replacement 3.12.7 environment with Gurobi 13.0.2 must be created and recorded; dependency identity beyond Python/Gurobi is not fully recoverable from a lock file.
- Frozen CPU/core identity and exact license mechanism are `NOT_VERIFIABLE` from committed provenance.
- XXL10 currently has about 14.86 GiB available, below its 16-GiB preflight threshold.
- Seven of eight Pure/Aggregate Renault raw result sets are not tracked, so a complete four-method Renault timing table cannot be claimed from this commit.

## Authorization boundary

Do not authorize the 30-run batch yet. First restore the required solver environment, re-run the environment audit, and obtain at least 16 GiB available before any XXL10 attempt. Once those checks pass, a separate reviewed commit may set authorization true. L10 and XL10 are statically resource-eligible; XXL10 remains conditional on its existing preflight. Formal runs must proceed one condition at a time in seed order.

No formal or development optimization was executed during this preparation.
