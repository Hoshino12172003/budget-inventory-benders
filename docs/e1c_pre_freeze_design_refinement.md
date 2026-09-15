# E1c pre-freeze design refinement

## Decision

`E1C_PRE_FREEZE_READY`

This refinement uses only static construction counts and the already known
empirical-scale timing context. No E1c instance, nominal baseline, resource
probe, or formal optimization was run.

## Gamma recommendation

Use `FIXED_GAMMA_2` for the main scaling experiment. The proportional-exposure
rule is mathematically valid and more nearly preserves uncertainty intensity:

| Scale | R x J | Fixed Gamma/RJ | Proportional Gamma | Proportional Gamma/RJ |
|---|---:|---:|---:|---:|
| S | 96 | 0.020833 | 2 | 0.020833 |
| M | 160 | 0.012500 | 4 | 0.025000 |
| L | 288 | 0.006944 | 6 | 0.020833 |

However, proportional Gamma changes network size and cardinality depth
simultaneously. Under the current exact formulations, M rises to 25,170
product-risk blocks and L to 2,280,612, while the Pure global adversarial MILP
does not enumerate those blocks. This can create an artificial comparison in
which Direct and both structured methods absorb a combinatorial-depth shock
that is absent from the Pure representation. Fixed Gamma is therefore the
cleaner fairness contract for attributing growth to I/R/J. The limitation is
explicit: E1c holds the absolute shock budget fixed and does not claim
constant-fraction uncertainty exposure. The asymmetry is not a guaranteed
one-way bias toward PRB: proportional Gamma can favor PRB relative to Direct
and penalize it relative to Pure. It is nevertheless an avoidable confounder.

## Scale recommendation

Retain S=15/12/8, M=20/16/10, and L=25/24/12 as the default pre-freeze grid.
It expands IRJ from 1,440 to 7,200 and inventory pairs from 120 to 300. Static
counts cannot establish that L is nontrivial, so the grid is not paper-final
until the preregistered resource probes are resolved.

Search for a possible XL only inside I=30--35, R=30--36, J=14--16. The lower
anchor 30/30/14 already projects 6,075,177 Direct variables and 6,524
product-risk blocks; the upper anchor projects 13,843,348 Direct variables and
10,672 blocks. The box is `RESOURCE_RISK`, not an authorized scale.

## Development-only probes

After separate authorization, use seed 20260911 for at most two scale-replicate
cells: current L and XL-low. Test Direct first because it is the memory and
construction bottleneck. Use one isolated process, the unchanged 900-second
wall guard, and a 22-GiB process-memory stop. XL-low requires explicit approval
to cross the current static model-size gate. Probe outputs are limited to
feasibility, memory, construction size, timeout, and certification; they never
enter paper statistics or algorithm ranking. Within a safe cell, invoke methods
in the fixed order Direct, Aggregate Structured, PRB, and Pure under identical
guards; stop the complete cell if continuing would be unsafe.

## Freeze rules

Choose the largest scale whose generation is deterministic, whose construction
has no uncontrolled OOM risk on 31.5 GiB, and on which Pure and PRB can be
invoked under the common timeout. A safe Direct timeout remains an observation;
unsafe Direct construction excludes the complete scale for every method. The
rule is applied before formal outcomes and never depends on whether PRB wins.

Keep five replicates by default. Ten may be frozen only if both probes finish
exactly below 60 seconds and 12 GiB peak memory, before any formal comparison.
The default three-scale design has 60 runs; a safe XL would yield 80. Ten
replicates would yield 120 or 160 respectively.

## Authorization state

- formal execution: false
- development solve: false
- resource probe: false
- instance generation: false
- nominal-baseline preparation: false
