# EF-BD L10 resource protocol V2 (7 GiB)

This protocol is an independent revision of the blocked 4 GiB preparation. It does not alter or replace that record.

## Why 4 GiB was rejected

The EF-BD Oracle contains 2,257,537 variables, 184,303 constraints, and an estimated 6,773,683 nonzeros. It retains 99.96% of the variables in the frozen L10 Direct extensive form. The same-seed Direct attempt reached 4.698249816894531 GiB, and the maximum archived L10 Direct peak is 4.866119384765625 GiB. A 4 GiB cap therefore had no evidence-based execution margin.

## Revised contract

- exactly one condition: `EF_L10_S20260921`, next identity `attempt-001`;
- process-tree RSS cap: 7 GiB;
- startup available RAM: at least 11 GiB;
- system available RAM floor: 3 GiB;
- 900 seconds, `Threads=2`, 20 GiB free disk, 0.25-second monitoring;
- one worker, no parallel execution, no automatic retry;
- resource/time failure is retained as a failed attempt and is never published as a certified canonical result.

The cap provides 2.302 GiB (49.0%) over the same-seed Direct peak and 2.134 GiB (43.8%) over the maximum archived L10 Direct peak. At the startup threshold, a process at the full cap leaves 4 GiB, one GiB above the system floor. Windows process disappearance is treated as zero further RSS only after the process API reports that it no longer exists; the supervisor still records the worker return code, stdout/stderr, monitor samples and outcome. A nonzero worker exit cannot become a canonical success.

This is a safety judgment for one monitored pilot, not proof that 7 GiB will be sufficient to finish. The protocol remains `formal_run_authorized=false` and is `READY_FOR_AUTHORIZATION` only within this scope.
