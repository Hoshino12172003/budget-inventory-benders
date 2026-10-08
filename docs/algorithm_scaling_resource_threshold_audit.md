# Algorithm scaling resource-threshold audit

## Decision

The uniform 18-GiB preflight is replaced by a size-dependent fail-closed gate:

| Size | Empirical worst process-tree peak | Preflight free RAM | Process-tree cap | Reserve at cap | 12 GiB free |
|---|---:|---:|---:|---:|---|
| L10 | 1.820 GiB | 7 GiB | 4 GiB | 3 GiB | sufficient |
| XL10 | 4.867 GiB | 10 GiB | 7 GiB | 3 GiB | sufficient |
| XXL10 | 10.821 GiB | 16 GiB | 13 GiB | 3 GiB | insufficient |

The threshold is not merely a uniform reduction. For each size, the process cap is more than
2 GiB above the observed worst method peak, and the launch threshold retains another 3 GiB for
Windows, monitor latency, native allocation bursts, and unrelated system activity. The independent
3-GiB system-available emergency stop remains active.

## Origin of the old 18-GiB threshold

The original resource audit first required 24 GiB free. That gate blocked before construction on
a 31.5-GiB host. After cleanup exposed about 19.15 GiB, the audit selected an 18-GiB launch gate
with a 14-GiB process-tree stop, yielding a nominal 4-GiB reserve. The 18-GiB value was therefore
a conservative host-level reserve policy, not a peak-memory estimate calibrated to any specific
size. The large-scale development runner subsequently applied it uniformly.

## Empirical evidence

The tracked development table contains ten observations for every size-method cell. Peak memory
is whole process-tree memory sampled by the development monitor; no Gurobi `MemUsed` record is
available.

| Size | Method | Peak range GiB | Median GiB | Runtime range seconds | Memory stops |
|---|---|---:|---:|---:|---:|
| L10 | Pure | 0.055–0.083 | 0.067 | 0.838–6.327 | 0 |
| L10 | Aggregate-Structured | 1.811–1.820 | 1.814 | 26.073–109.667 | 0 |
| L10 | PRB | 1.812–1.818 | 1.815 | 19.020–45.632 | 0 |
| XL10 | Pure | 0.063–0.094 | 0.069 | 1.480–6.631 | 0 |
| XL10 | Aggregate-Structured | 4.860–4.865 | 4.862 | 76.719–231.942 | 0 |
| XL10 | PRB | 4.862–4.867 | 4.865 | 58.531–101.000 | 0 |
| XXL10 | Pure | 0.080–0.086 | 0.084 | 2.625–3.616 | 0 |
| XXL10 | Aggregate-Structured | 10.811–10.818 | 10.816 | 244.991–316.892 | 0 |
| XXL10 | PRB | 10.814–10.821 | 10.816 | 157.320–192.453 | 0 |

Three Pure observations are non-optimal, but their peaks are only 0.070–0.085 GiB and the retained
records do not classify them as memory failures. All 60 structured-oracle observations completed
without `RESOURCE_STOP`.

The relevant algebraic growth is also monotone: uncertainty components increase from 288 to 420
to 576, product-risk blocks from 3,612 to 6,524 to 10,672, and structured-oracle variable blocks
from approximately 2.26 million to 6.07 million to 14.23 million. This matches the measured
1.82/4.87/10.82-GiB scaling pattern.

## Evidence limits and safety margin

The tracked summary does not contain Gurobi-specific memory counters, raw per-run monitor logs, or
the peak of the shared canonical-baseline preparation phase. No values are invented for those
quantities. The additional process headroom of roughly 2.1 GiB and the 3-GiB system reserve are an
inferred safety margin for those unmeasured components and short-lived allocations.

At 12 GiB free, L10 and XL10 pass their size gates. XXL10 does not: its empirical 10.821-GiB peak
would leave only about 1.18 GiB free, below the retained 3-GiB system floor even before allowing
for unmeasured preparation or allocation bursts.

## Staged execution recommendation

Run L10 first and inspect the new formal monitor artifacts. If observed peak memory remains below
the 4-GiB cap, proceed to XL10 and check against its 7-GiB cap. Run XXL10 only after achieving at
least 16 GiB free and retaining the 13-GiB process cap. The runner remains strictly sequential and
supports these stages through `--execute-size L10`, `XL10`, and `XXL10`.

This audit changes no scientific parameter, method, tolerance, or model and executes no formal
optimization.
