# Renault PRB ablation recovery: fail-closed stop at 210330

## Scope and disposition

The recovery run used authorization commit
`ca7dd129c7a092631dfbb0332a5b6852cb515395`.  It was restricted to the eight
frozen Renault cases and did not run any scaling condition.

The runner preserved the certified PRB-SG canonical results for 210202 and
210628.  It then produced certified canonical results for 210129 attempt-002
and 210310 attempt-001.  PRB-SG 210330 attempt-001 failed the frozen global
risk-budget coupling certification, so the runner stopped immediately.  It
did not execute 210323, 210428, or 210611, and it did not start A-PRB or
A-PRB-SG.

All three execution authorizations were closed after the stop.  No automatic
retry was made.

## 210330 numerical evidence

The worker completed the algorithm and independent fixed-solution
certification, but the final formal classification remains failed:

- solver status: `ERROR`
- exact certification: `false`
- internal exact certification: `true`
- independent certification: `true`
- cut validity: `true`
- objective: `657659.5492546142`
- lower bound: `657659.5492562540`
- upper bound: `657659.5492546142`
- reported final gap: `0.0`
- Direct objective residual: `5.596084520220757e-07`
- global risk-budget coupling residual: `1.6398262232542038e-06`
- frozen coupling threshold: `1.0e-06`
- threshold multiple: `1.6398262232542038`
- algorithm core time: `1.2759538998361677` seconds
- peak monitored process-tree RSS: `0.059825897216796875` GiB
- worker return code: `1`
- resource stop reason: `null`

This is a numerical certification failure, not a resource failure, process
monitor failure, or archive race.  The attempt contains `result.json`,
`provenance.json`, `first_stage_solution.json`, `iteration_trajectory.json`,
`solver.log`, `stdout.log`, `stderr.log`, and `resource_monitor.json`.  It was
not copied to the canonical result directory.

## New accepted results

| Case | Attempt | Status | Coupling residual | Core seconds | LP solves | Pruning fraction |
|---|---|---|---:|---:|---:|---:|
| 210129 | attempt-002 | exact certified | 1.1641532182693481e-10 | 1.6199083998799324 | 107 | 0.9576740506329114 |
| 210310 | attempt-001 | exact certified | 4.656612873077393e-10 | 1.7984982999041677 | 124 | 0.9607594936708861 |

The 210129 attempt-001 recovery candidate remains historical evidence and was
not promoted or modified.

The complete 41-file manifest for the new attempts, accepted canonical copies,
and stopped batch report is archived as
`artifacts/renault_prb_ablation_partial_sha256_manifest.csv`.  Byte-for-byte
comparison found zero mismatches between each accepted attempt and its
canonical copy.  A targeted secret-pattern scan found no API key, access token,
password, license key, or other machine secret in the new evidence.

## SHA-256 evidence

| Artifact | SHA-256 |
|---|---|
| 210129 attempt-002 result | `41a9ea2c66a05153a10d2d80eb431d18a9fdd86bd8dd8fc5455e39cf56ef6441` |
| 210129 attempt-002 provenance | `8c7581aa2841d02672c323f0577ddb259d627dc0ceaae0e15dd512782287e924` |
| 210310 attempt-001 result | `b61ce49c7d4a4164f9088b48a411d26bed39b91d5bcab0b95e16ac33c88a276b` |
| 210310 attempt-001 provenance | `66722238ac2b0a7b5a9037922bce7f42645f2ac1f47cf9e0be22933b7c6abd1f` |
| 210330 attempt-001 result | `f0ce4bba68cabb775727a2b30c4e6137652f7ec96efa5394c450ea3c64f2240d` |
| 210330 attempt-001 provenance | `bd185b96e1ec27f7f7b3dd88209cb52f14dd6b8f8d94073eb6e4c15a6747b300` |
| stopped batch report | `4827db75e271844cdcc878b7dd821b87f25d232ded7818adf67c4ac475f74e56` |

## Final state

The requested four-group ablation is incomplete and therefore no 2-by-2
performance conclusion or recommendation is valid.  Further execution needs
a new explicit authorization that states how the independently preserved
210330 numerical failure is to be handled.  The frozen coupling tolerance was
not changed and the failed attempt was not reclassified.
