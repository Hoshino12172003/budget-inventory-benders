# E1c development resource-probe report

## Status

`E1C_DEVELOPMENT_RESOURCE_BLOCKED`

The two requested probes did not start. Before instance preparation or any
solver call, the frozen resource gate required at least 24 GiB available system
memory. Three consecutive measurements reported 15.3303, 15.3259, and 15.3273
GiB available on a 31.4974-GiB machine. Starting a child process with a 22-GiB
process stop under this condition could impose system memory pressure before
the child reached its own stop. The runner therefore failed closed.

The user's authorization was recorded for exactly these two development cells;
it does not authorize formal E1c execution or any other scale or seed.

No application or user process was terminated to manufacture capacity. The
existing E1/E1b and E2--E7 results were not read by a reporting pipeline,
modified, moved, or overwritten.

## Requested development scope

The rejected launch was limited to seed 20260911, Gamma 2, a 900-second common
timeout, and these two scale cells:

| Scale | I | R | J |
|---|---:|---:|---:|
| L | 25 | 24 | 12 |
| XL-low | 30 | 30 | 14 |

The requested resource-safety order was Pure, PRB, Aggregate Structured, then
Direct. All eight method-scale observations are recorded as
`NOT_RUN_RESOURCE_PREFLIGHT_BLOCK`; no runtime, peak process memory,
certification, iteration, cut, or solver-model count is reported because none
was measured by an execution.

## Scientific consequences

The probes cannot yet answer whether L is trivial, whether XL-low is safe, or
whether Pure and PRB are invocable at both scales. It would be scientifically
incorrect to convert static estimates into observed timings or memory values.

Until the same probes are rerun with at least 24 GiB available memory, retain
S/M/L as the provisional grid, exclude XL, keep five replicates, and retain the
60-run estimate. These are pending recommendations, not a formal freeze.

## Execution accounting

- formal optimization runs: 0
- development optimization runs: 0
- generated development instances: 0
- nominal-baseline preparation runs: 0
- primary paper-final artifacts overwritten: false
