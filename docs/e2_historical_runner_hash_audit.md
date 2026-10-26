# E2 historical runner hash audit

## Finding

The failure in
`tests/test_e2_protocol.py::test_e2_identity_and_reuse_contract` is real and is
not repaired by changing the historical authorization manifest.

Three identities must be distinguished:

| Object | SHA-256 |
|---|---|
| Authorized historical runner recorded in the E2 manifest | `0ba3e0069db8ab8d37f9fe693511ac6c780a44c61a60776ff18659560cd0e2c9` |
| Runner blob at commit `4b1547296013c498cf4353c49c791cf1baf3566d` | `0ba3e0069db8ab8d37f9fe693511ac6c780a44c61a60776ff18659560cd0e2c9` |
| Current committed runner blob | `23db440e4ff03765440c5e2ab231bf2ad5da4b6be9c8d3f4d91ee6d16365f41d` |
| Current checked-out runner bytes | `dd296522c954ad4876279a6ca5045feb99187e434a162809d53b39cd103d2ad6` |

The checked-out byte hash also reflects the checkout's line-ending
representation. The committed-blob comparison independently proves that the
current runner is not the authorized historical blob.

## Semantic change

Commit `0631111342bdf663dfef943bb20c6fe708df3359` added exactly two semantic
elements:

- an import of `require_protocol_not_frozen`;
- a call to that guard before the historical authorization checks.

This strengthens execution admissibility after protocol freeze. It does not
change the E2 economic model, policy definitions, uncertainty set, or recourse
evaluation, but it does change runner identity and whether a run may start.
Consequently, the current runner must not be treated as the historically
authorized executable.

## Recoverable evidence

Git history contains the exact historical runner blob at commit `4b154729...`,
and its SHA-256 exactly matches the authorization manifest. This is independent,
verifiable evidence for the historical code identity.

It is not complete execution-lineage evidence because the ignored original E2
run directories and result provenance are absent from the current repository.
The retained E2 summaries remain aggregate evidence only.

## Test disposition

The existing test compares the current working-tree runner bytes to a historical
manifest hash. It therefore continues to fail and is reported as a known
historical identity mismatch. It is not skipped, marked xfail, or made to pass by
editing historical records.

To close the issue without destroying evidence, a future change must either:

1. change the historical test contract to hash the runner blob pinned by its
   historical commit and authorization manifest; or
2. restore a separately archived historical runner and original E2
   result/provenance package and verify both.

The machine-readable audit is
`experiments/audits/e2_historical_runner_hash_audit.json`.
