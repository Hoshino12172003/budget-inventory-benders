# E1c development resource-probe report

## Status

`E1C_DEVELOPMENT_RESOURCE_BLOCKED`

The subsequently authorized execution attempt on runner commit `c7af506` was
blocked by that revised gate before the first L preparation: the runner
measured 17.726021 GiB available against the unchanged 18-GiB threshold. The
isolated result root contains only a machine-readable `BLOCKED` summary with
zero completed top-level runs. No development instance, nominal baseline, or
solver model was created.

The two requested probes did not start. Before instance preparation or any
solver call, the frozen resource gate required at least 24 GiB available system
memory. Three consecutive measurements reported 15.3303, 15.3259, and 15.3273
GiB available on a 31.4974-GiB machine. Starting a child process with a 22-GiB
process stop under this condition could impose system memory pressure before
the child reached its own stop. The runner therefore failed closed.

The user's authorization was recorded for exactly these two development cells;
it does not authorize formal E1c execution or any other scale or seed.

That blocked attempt remains an immutable historical audit. A subsequent host
cleanup produced about 19.15 GiB available memory, demonstrating that the old
24-GiB launch threshold was unattainable even under the intended clean-host
condition. The operational development gate is therefore revised prospectively
to 18 GiB available at launch and a 14-GiB process-tree hard stop. No probe was
launched during this memory-gate audit.

## Revised memory-gate audit

Candidate A (18-GiB preflight, 14-GiB process stop) leaves an estimated 4 GiB
for Windows and non-probe activity at the process cap. Candidate B
(18-GiB/16-GiB) leaves only 2 GiB and is rejected because native allocation
bursts and a monitoring interval could exhaust that margin.

The selected gate is fail-closed:

- three consecutive available-memory samples and the immediate launch sample
  must each be at least 18 GiB;
- one method runs at a time in an isolated child process;
- the full child process tree is stopped at 14 GiB resident or private
  committed memory;
- an independent emergency stop triggers if system available memory reaches
  3 GiB;
- samples are taken at intervals no longer than 0.5 seconds;
- termination writes `RESOURCE_STOP` atomically and never resumes with a
  higher cap.

Under this revised gate, L may proceed when its launch check passes. XL-low may
also be attempted as a development probe: Pure, PRB, and Aggregate Structured
run sequentially under the cap, while Direct may return
`SAFE_CONSTRUCTION_BLOCKED` from its frozen size audit rather than allocate an
unsafe model. This permission is not evidence that XL-low is formal-grid safe.

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

Until the same probes are rerun under the revised gate, retain S/M/L as the
provisional grid, exclude XL, keep five replicates, and retain the 60-run
estimate. These are pending recommendations, not a formal freeze.

## Execution accounting

- formal optimization runs: 0
- development optimization runs: 0
- generated development instances: 0
- nominal-baseline preparation runs: 0
- primary paper-final artifacts overwritten: false
- memory-gate audit optimization runs: 0
- latest authorized probe optimization runs: 0
