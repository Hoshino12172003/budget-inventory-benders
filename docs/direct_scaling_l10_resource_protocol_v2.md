# L10 Direct resource protocol revision V2

## Scope and authorization

This revision prepares one possible retry of `DIRECT_L10_S20260921`. It does not authorize execution: `formal_run_authorized=false`. The whitelist contains exactly that condition, so neither the remaining nine L10 conditions nor XL10/XXL10 can be launched with this protocol.

No mathematical model, instance, seed, Gurobi parameter, tolerance, precision setting, or the 900-second condition limit is changed.

## Original attempt evidence

The immutable `attempt-001` record remains under `experiments/results/direct_scaling_extension_v1/worker_logs/DIRECT_L10_S20260921/attempt-001/`. It stopped with `RESOURCE_PROCESS_CAP` after 53.499 seconds. The monitor collected 193 samples at 0.25-second intervals and observed a 4.024109 GiB peak process-tree RSS. The last solver checkpoint had no incumbent, a best bound of -275.41877067477606, and zero processed branch-and-bound nodes.

The original monitor retained the sample count and peak, not the complete per-sample RSS series. Consequently, the exact growth slope and a projected peak cannot be independently reconstructed. The 6 GiB assessment is conditional rather than a claim that the model will finish below 6 GiB.

## Safety assessment

The proposed process-tree cap is 6 GiB. With the required 3 GiB system-available floor, a launch gate below 9 GiB would not provide enough static headroom. This protocol therefore raises the L10 launch requirement from 7 GiB to 10 GiB, providing a 1 GiB reserve above `6 + 3` GiB. The locally reported 12.57 GiB available memory satisfies that launch gate with approximately 2.57 GiB additional headroom.

The retry remains conditional on the live preflight immediately before launch. It will fail closed if available RAM is below 10 GiB, free disk is below 20 GiB, the Python/Gurobi identity differs, the worktree is dirty outside the result root, or the condition is not the sole whitelist entry. During execution, the parent monitor samples every 0.25 seconds and kills the worker if process-tree RSS reaches 6 GiB or system-available memory reaches 3 GiB. Execution remains single-process.

This is a reasonable guarded retry on the reported 31.50 GiB host, but it is not risk-free. Windows and other applications can consume memory between samples. Closing unnecessary applications before launch is recommended. The system-available floor remains the independent fail-safe even if external memory use changes rapidly.

## Evidence preservation

The runner selects the first unused attempt directory. Because `attempt-001` exists, the prepared retry is reported by dry-run as `attempt-002`. Neither the original logs nor any prior formal result can be overwritten. A completed certified result is also protected by the existing canonical run-directory refusal.

The historical Scaling V2 software environment remains `NOT_VERIFIABLE`; using Python 3.12.7 and Gurobi 13.0.1 for this new Direct attempt does not establish exact historical environment identity.
