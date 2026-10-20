# Renault PRB ablation execution interruption

## Decision

**BLOCKED_AFTER_PARTIAL_PRB_SG_EXECUTION.** No automatic retry or additional optimization was performed after the monitoring failure.

## Completed correctness gates

- Static/non-optimization tests: passed.
- Product-level exact screening versus full enumeration on the tiny instance: passed.
- PRB-SG, A-PRB, and A-PRB-SG tiny objectives versus Direct and original PRB: passed.
- All three Renault dry-runs: `READY_FOR_AUTHORIZATION` before execution.
- Preparation commit: `3314587e892a97a6753e56ae13ac712ea87411ad`.
- Authorization commit: `1a2dfcb96786b84cf58d5f92f5187c473ae0b707`.

## Execution evidence

The PRB-SG batch accepted two complete canonical conditions before the monitor failed:

| Condition | Certification | Core seconds | Oracle seconds | Exact LP solves | Safely pruned | Pruning fraction |
|---|---:|---:|---:|---:|---:|---:|
| PRB_SG_RENAULT_210202 | PASS | 1.589458 | 0.070841 | 117 | 2411 | 95.3718% |
| PRB_SG_RENAULT_210628 | PASS | 1.686476 | 0.093234 | 129 | 3031 | 95.9177% |

`PRB_SG_RENAULT_210129/attempt-001` contains a solver result that reports exact internal and independent certification, objective `851260.24783255`, Direct residual `0`, and coupling residual `1.1641532182693481e-10`. Its `result.json` SHA-256 is `923d232864b397859ab0bc427b0fd524f35998c59c88b446fd90f82c79b4327d`. However, the supervisor failed before it could write `resource_monitor.json`, `stdout.log`, and `stderr.log` or atomically create a canonical directory. It is therefore retained only as an incomplete recovery candidate and is not counted as an accepted canonical result. Peak process-tree memory is `NOT_RECORDED`.

## Root cause

The worker exited between the supervisor's `process.poll()` check and `psutil.Process.children(recursive=True)`. The latter raised `psutil.NoSuchProcess`, which escaped from `tree_rss` and aborted the batch. This is a monitoring race, not a mathematical, solver, time, or resource failure.

The repair makes a vanished process tree contribute zero additional RSS for that final sampling instant; the following loop/`communicate()` path still records the worker return code and performs the same fail-closed certification checks. A regression test simulates the exact `NoSuchProcess` race.

## Frozen status after interruption

- PRB-SG: 2 canonical successes, 1 incomplete recovery candidate, 5 unattempted.
- A-PRB: 0 attempted, 8 unattempted.
- A-PRB-SG: 0 attempted, 8 unattempted.
- Original PRB-BD: frozen historical evidence only; not rerun.
- All three new execution authorizations are closed.

A new explicit authorization is required before any unattempted condition or a separately numbered retry of 210129 may run.
