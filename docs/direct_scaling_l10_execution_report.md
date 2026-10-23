# Direct scaling L10 execution report

## Decision

`BATCH_STOPPED_AFTER_RESOURCE_CAP`

The authorized batch did not complete. The first L10 condition reached the unchanged 4-GiB process-tree cap, and the remaining nine same-scale conditions were not started because continuing presented the same model-scale memory risk.

- Attempted: 1/10 (`DIRECT_L10_S20260921`).
- Exact-certified: 0/10.
- Resource-stop: 1/10.
- Unattempted after safety stop: 9/10.
- Peak process-tree RSS: 4.024109 GiB.
- Monitored wall time: 53.499005 s.
- Last solver checkpoint: runtime 36.103000 s, no feasible incumbent, best bound -275.418770674776.
- No tolerance, model, parameter, or resource threshold was changed; the condition was not retried.
- No XL10 or XXL10 condition was started.
- The active formal execution gate was closed after the resource stop.

The solver log, stdout/stderr, resource monitor, and last available solver-progress checkpoint are retained under the formal Direct output root. No `result.json` is synthesized because the worker was terminated by the external hard resource guard before solver termination and certification.
