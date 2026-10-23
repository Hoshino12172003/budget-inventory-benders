# Direct L10 attempt-002 archive failure

## Classification

`DIRECT_L10_S20260921` attempt-002 is classified as `SOLVER_OPTIMAL_FORMAL_ARCHIVE_FAILED`. It is not a formal certified Direct result.

The Gurobi log reports an optimal objective and bound of 2048661.14416857 with zero gap after 112.11 seconds. The parent resource monitor reports a 4.698249816894531 GiB peak process-tree RSS, 150.2879314001184 seconds monitored wall time, no resource stop, and worker return code 1.

## Root cause

After solution extraction and the in-process certification call, the worker wrote `result.json` and `first_stage_solution.json` into a temporary directory. It then called `shutil.move` on the active Gurobi `solver.log` before clearing the model `LogFile` parameter or disposing the model/default environment. Windows rejected both rename and fallback unlink with WinError 32 because Gurobi still held the file handle. The exception handler then deleted the entire temporary directory, including the already-written result and first-stage files.

## Recoverable evidence

The preserved attempt directory contains the resource monitor, full solver log, last progress checkpoint, stdout, and traceback. These establish that the main MILP solver returned OPTIMAL and establish the resource measurements. They do not contain the first-stage vector, independently certified recourse value, certification residual, result JSON, or provenance hash chain. The fact that the failure occurred after the certification call is execution-order evidence, not independently reproducible certification evidence.

The preserved SHA-256 hashes are:

- `resource_monitor.json`: `318079cbd7f284786c787d30063e837def76d4a6335bdced5d6b5d5e609ac52e`
- `solver_progress.json`: `e5ee13a70c22a800653087aebf5d404969bf9733c16d4d3f99c68c81f6bcdbb6`
- `solver.log`: `07fd3367497928425314a4cfb1586ad0761b0e57dc6b62eb8c668e61d0865657`
- `stderr.log`: `78e77fb8f67d4552a582596010a5feed22684ecc79f7f63c96d7c9fc4215b8c8`
- `stdout.log`: `5032112f6af6b3db5dc3dec22c288eac895f86eefc344509eea5cf07d4ec5c4e`

Consequently, attempt-002 cannot be promoted or repaired into a formal exact-certified result without another optimization run. No formal result has been synthesized.

## Fix

The worker now extracts the full solution and completes independent certification before explicitly clearing the Gurobi log target, disposing every certification subproblem, disposing the main model, and releasing the default Gurobi environment. Only then does artifact persistence begin.

Persistence writes result, first-stage solution, and a preliminary provenance record to a recovery candidate marked `CANDIDATE_NOT_FORMAL`. Solver-log copying retries transient Windows sharing violations. The candidate is atomically renamed into the canonical run directory only after the log, optional progress record, complete provenance, and hashes are present. Any copy or atomic-publication failure leaves the candidate in place with a non-formal marker instead of deleting it.

The execution gate is closed. Any attempt-003 requires a separate reviewed authorization commit; the 6 GiB process cap, 10 GiB launch gate, 3 GiB system floor, 0.25-second monitor interval, single-worker policy, 900-second limit, instance, seed, model, and solver parameters remain unchanged.
