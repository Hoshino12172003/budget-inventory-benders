# E1 real-data redesign recommendation

## Decision: Option C

The raw archive contains 71 dates, but only `210202` and `210628` are currently
formal, reproducible inputs under the frozen Step 1-3 definitions. Their raw
workloads differ, but their formal dimensions and exact Direct formulation
sizes are identical. The two dates are sufficient for a real-instance
correctness/runtime comparison, but not for a scalability claim. Controlled
scaling is therefore still required.

The other 69 dates must not be called formal E1 cases until an independently
reviewed Step 1-3 builder freezes the missing region mapping, product ranking,
transformations, calibrations, incumbent construction, and budget anchor. This
audit does not introduce those assumptions.

## Recommended minimal design

### E1a - real-instance benchmark

Use `210202` and `210628` with Direct and PRB: four observations. All four are
already available and must be reused as
`FORMAL_REAL_BENCHMARK_RESULTS_ALREADY_AVAILABLE`, without reruns or overwrite.

| Case | Method | Objective | Runtime (s) | Reuse action |
| --- | --- | ---: | ---: | --- |
| 210202 | Direct | 116875.3457619544 | 8.680999994277954 | retain existing row |
| 210202 | PRB | 116875.34576195436 | 2.2748046000488102 | retain existing row |
| 210628 | Direct | 81468.15564321939 | 10.815999984741211 | retain existing row |
| 210628 | PRB | 81468.15564321943 | 3.2355355999898165 | retain existing row |

The absolute Direct/PRB objective difference is
`4.3655745685100555e-11` in each case, within the frozen E1 tolerance.

### E1b - Renault-derived controlled scaling

Replace the eight blocked random-synthetic observations with two nested reduced
scales for each formal case and both methods: eight new observations. Together
with the already available full-scale pair for each case, this creates three
within-case size levels:

- reduced: 5 depots by 4 regions by 4 products;
- medium: 10 depots by 8 regions by 6 products;
- full formal instance: 15 depots by 12 regions by 8 products, reuse only.

Before any execution, a separate approval must freeze a deterministic identity
selection rule. The construction must select nested identities from each frozen
formal Renault instance and subset the existing demand, deviation, transport,
shortage, service, capacity, UB, inventory-cost, fixed-cost, and incumbent
baseline arrays without rescaling, imputation, or random generation. The
reduced cases must be labeled `Renault-derived empirical subsets`, not original
full Renault cases. The baseline inventory remains the already documented
derived nominal incumbent, not observed raw Renault inventory.

This minimal redesign retains 12 total E1 observations: four existing
real-instance observations and eight new Renault-derived subset observations.
It supports descriptive scaling over the empirical model range. If a
larger-than-full scalability claim is required, use a separately approved
appendix and label every added dimension as empirical replication or controlled
expansion; do not represent it as additional original Renault data.

## Frozen-state protections

This recommendation changes no existing result, Step 1-3 parameter, model
definition, uncertainty semantics, lambda calibration, service penalty, or
budget anchor. It creates no synthetic generator and authorizes no run. The
eight synthetic runs remain `NOT_RUN`, and E2-E7 authorization remains `false`.
