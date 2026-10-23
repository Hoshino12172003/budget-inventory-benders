# Direct scaling execution readiness

## Current status

`READY_FOR_EXPLICIT_AUTHORIZATION_WITH_SIZE_GATES`

Completed without optimization:

1. 30-instance identity and SHA-256 manifest: PASS (30/30).
2. V1 versus V2 result reconciliation: PASS; final source is 89/90 V2.
3. Static Direct model sizing: PASS.
4. Fail-closed runner, short atomic path, resume identity check, sequential parent monitor: implemented.
5. Result protection and identity tests: implemented.
6. Dry-run development safety test: PASS with `optimization_calls=0`.
7. Renault four-method table: complete and directly regenerated from 8/8 Direct, PRB, Pure, and Aggregate evidence.
8. Recovered E1b archive: PASS (88/88 byte-identical files; 16/16 exact-certified runs).

Blocking items:

- `formal_run_authorized=false` by design.
- Scaling V2's historical Python executable, Gurobi version, version-dependent defaults, complete dependency lock, exact license mechanism, and continuously monitored concurrent-process state remain `NOT_VERIFIABLE`.
- Current Python 3.12.7 and Gurobi 13.0.1 satisfy the environment frozen for the new Direct batch. This supports protocol-level paired comparison but not exact historical environment matching.
- Frozen Scaling V2 CPU/core identity is also `NOT_VERIFIABLE` from committed provenance.
- At the final read-only audit snapshot, about 12.27 GiB was available; XXL10 is below its 16-GiB preflight threshold.

## Authorization boundary

The preparation is ready for the user's explicit authorization, but authorization remains false. At the audited preflight, L10 has 10/10 statically eligible conditions, XL10 has 10/10, and XXL10 has 0/10 because available memory is below its unchanged 16-GiB launch threshold. A later authorization must not waive that gate; XXL10 can start only when the existing threshold is met. Formal runs must proceed one condition at a time in seed order.

No formal or development optimization was executed during this preparation.
