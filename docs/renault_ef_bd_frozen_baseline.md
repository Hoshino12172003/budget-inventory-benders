# Renault EF-BD frozen baseline

## Freeze decision

The Renault EF-BD development batch is frozen at archive HEAD
`70b0e86d41f0e6ea3b7bcad46c4c4adad00ebc7d`.  The execution identity is
`0938e4b4d05873942b8f68941b4dfcf784f5c3ca`; every run is `attempt-001` under
protocol `RENAULT_EF_BD_8CASE_V1` and solver profile
`gurobi-balanced-1e-8-v1`.

All eight conditions are OPTIMAL, exact-certified and independently certified.
The mean algorithm core time is 3.7256622125 seconds.  There were no resource,
worker, archival or numerical-certification failures.

## Evidence audit

- The 144-entry evidence manifest has SHA-256
  `9c78507f24565611f65b3bf8639da79245d13e319c1dcd09a4ee34ccfb020fd4`.
- Every current evidence file matches its manifest size and SHA-256.
- For all eight conditions the canonical result and attempt-001 payload are
  byte-identical for result, provenance, trajectory, first-stage solution,
  Oracle trace and solver log.
- Each provenance record's result, trajectory and first-stage hashes match the
  archived files.
- Execution config SHA-256 is
  `2b4608e8936cc748a69f0116eae88598928a471afa4fc5767d04b7575639cd75`.
- Closed post-run config SHA-256 is
  `5829f28f562c94cf18f14da1066b5b54e43d3a19239163ca9e9e9e5e5dc2cd05`.
- Implementation SHA-256 is
  `77e888175f4402c3442552a88b17313be6646713a31aa11c4295815a7d70b02d`.
- Runner SHA-256 is
  `8374026f15d71d85197f03e4c272249446d12417aa13eb1ed5debb50c4cf8294`.

The machine-readable per-case instance, x0, result, provenance and trajectory
hashes are registered in `artifacts/renault_ef_bd_frozen_baseline_v1.json`.

## Immutability rule

The complete directory
`experiments/results/renault_extensive_form_benders_development_v1` is an
immutable historical baseline.  It must never be overwritten, amended, retried
in place or used as the output root of a later experiment.  Any later EF-BD
development requires a new protocol ID, condition IDs, attempts and output
root.  This freeze does not convert the development classification into formal
evidence and does not authorize any new optimization.
