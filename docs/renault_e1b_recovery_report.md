# Renault E1b formal evidence recovery

## Decision

`RECOVERY_AUDIT_PASS`

The 88 files are byte-identical copies of the historical formal-run artifacts. No optimization was run and no result, timing, status, or provenance field was changed.

- Pure Benders: 8 runs, 40 files, 8 exact-certified.
- Aggregate Benders + Structured Oracle: 8 runs, 48 files, 8 exact-certified.
- Historical Aggregate ZIP SHA-256: `1f02e8834c7be16cac80a07e5470765b109f6f0c84825f8ef3d7e235010ee5ed`.
- Historical Aggregate ZIP comparison: 48/48 byte-identical (`PASS`).
- Result/provenance/reference-hash checks: 16/16 PASS.
- Sensitive-key/token scan: 0 matches. Solver logs retain only ordinary Gurobi username/license-identification banner data, not license keys.
- Recovered Renault solver version: Gurobi 13.0.2, independently present in result files and solver logs.

The Pure recovery is committed as its original 40 files. No historical Pure ZIP was found, so no ZIP is represented as an original-run archive.

Recovery manifest: `artifacts/renault_e1b_recovery_manifest.csv`.
