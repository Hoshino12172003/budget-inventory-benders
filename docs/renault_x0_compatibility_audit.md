# Renault initial-inventory compatibility audit

This audit uses exact depot and product identity matches against the verified official Renault source. No value was filled, normalized, clipped, repaired, interpolated, or inferred. No optimization was run and no Step 1–3 parameter was changed.

All 15 depots in each case remain existing facilities, including any depot with zero stock among the eight selected products.

## 210202

Classification: `DIRECTLY_COMPATIBLE`.

Mapped: 120/120; missing 0; duplicate 0; ambiguous 0; negative 0; NaN 0; Inf 0.

| Metric | Value |
| --- | ---: |
| Capacity violations | 0 |
| Maximum rhoC | 0 |
| Median rhoC | 0 |
| P90 rhoC, nearest rank | 0 |
| UB violations | 0 |
| Maximum rhoUB, excluding UB=0 | 0 |
| Median rhoUB, excluding UB=0 | 0 |
| Total X0 | 0 |
| Minimum product IC | 0 |
| Maximum product IC | 0 |
| Median product IC | 0 |
| System IC | 0 |

Violating depots: none.

Violating depot-product pairs: none.

Zero-stock depots: ['90015100', '90016100', '90016200', '90016500', '90016700', '90016900', '90017100', '90018300', '90019100', '91017200', '91017300', '91017500', '91017600', '91017700', '9624708'].

Across all depot commodities in the official source, 0/435 initial-inventory values are nonzero and their total is 0.

## 210628

Classification: `DIRECTLY_COMPATIBLE`.

Mapped: 120/120; missing 0; duplicate 0; ambiguous 0; negative 0; NaN 0; Inf 0.

| Metric | Value |
| --- | ---: |
| Capacity violations | 0 |
| Maximum rhoC | 0 |
| Median rhoC | 0 |
| P90 rhoC, nearest rank | 0 |
| UB violations | 0 |
| Maximum rhoUB, excluding UB=0 | 0 |
| Median rhoUB, excluding UB=0 | 0 |
| Total X0 | 0 |
| Minimum product IC | 0 |
| Maximum product IC | 0 |
| Median product IC | 0 |
| System IC | 0 |

Violating depots: none.

Violating depot-product pairs: none.

Zero-stock depots: ['90015100', '90015700', '90016100', '90016200', '90016500', '90016900', '90017100', '90018300', '90018400', '90019100', '91017200', '91017300', '91017500', '91017600', '9624708'].

Across all depot commodities in the official source, 0/450 initial-inventory values are nonzero and their total is 0.

## Reconfiguration semantics

Observed initial inventory is the parameter x0 in `x - x0 = a_plus - a_minus`. The adjustment variables are first-stage variables. Recourse reads only x and does not read x0, a_plus, or a_minus.

`PRODUCTWISE_BENDERS_COMPATIBLE = true`.

## Decision boundary

The observed values are source-valid and constraint-compatible, but the official source reports zero initial inventory for every depot commodity in both cases. Direct use is therefore not recommended for a paper whose reconfiguration mechanism requires a nonzero incumbent stock baseline. Lambda_R calibration and the new B_ref definition should wait for an explicit modeling decision: accept the zero baseline and its degenerate withdrawal semantics, or introduce a separately justified nonzero baseline without labeling it observed Renault initial inventory.
