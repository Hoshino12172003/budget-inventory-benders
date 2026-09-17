# E7 Demand-Risk × Reconfiguration-Friction Interaction

## Correctness status

E7 passes its final audit. All 72 expected parameter cells are present exactly once, comprising 40 provenance-validated reuses and 32 new formal conditions. Every result is `OPTIMAL`, reports `CERTIFIED_PRB_EXACT`, and passes exact certification. All result, first-stage, provenance, authorization, frozen-identity, accounting, feasibility, and timing checks pass. The audit modified no primary result.

The stored `global_coupling_pass=false` for `E7-210330-G4-L0025` is a diagnostic-tolerance mismatch, not a robust-feasibility or optimality failure. Its master-closure residual is `1.6399426385760307e-6`, just above the diagnostic threshold `1e-6`. Fixed-first-stage product-wise recomputation returns the stored exact recourse `625127.644766705` with zero difference, allocation `(0,0,0,0,0,0,3,1)` summing exactly to Gamma 4, maximum strong-duality error `5.82e-11`, and zero objective reconstruction error. The first stage was not reoptimized.

Eight reused G2-L0500 results carry a null diagnostic field because their source schema did not persist it. They are classified as `MISSING_BY_REUSE_SCHEMA_SOURCE_REFERENCED`, with the audited upstream E4/E1 status retained. Missing schema fields are not treated as failed certification.

## Extensive and intensive margins

The extensive-margin trigger is invariant across the three tested friction levels for all eight cases. The first material Gamma is 2 for 210129, 210202, 210323, and 210330; 4 for 210310; and `none_through_4` for 210428, 210611, and 210628. Thus the number of material cases is 0 at Gamma 0, 4 at Gamma 2, and 5 at Gamma 4 for every friction level. This is a statement about the discrete tested grid, not a continuous threshold theorem.

Friction strongly changes the intensive margin at Gamma 4. Mean RI is 38.10% at lambda 0.0025, 12.45% at lambda 0.05, and 3.46% at lambda 0.20. Conditional on material adjustment, the corresponding means are 60.96%, 19.93%, and 5.53%. The mean low-minus-high-friction difference in the G0-to-G4 RI response is 34.64 percentage points. This supports the descriptive conclusion that friction dampens the magnitude of high-risk reconfiguration while leaving the observed extensive trigger pattern unchanged.

## Adjustment composition and network response

At Gamma 4, material cases change an average of 4.6 depot-product pairs under low friction, 3.8 under baseline friction, and 2.8 under high friction. The mean share accounted for by the largest adjustment is 55.10%, 66.10%, and 80.00%, respectively. Over this grid, high friction is therefore associated with smaller, more concentrated changes across fewer coordinates. This is an empirical composition pattern, not a monotonicity property of the model.

Most E7 responses remain inventory-level. Only two of 72 observations change planning-period depot status, both at G4-L0025. In 210310, depots `90018300` and `91017500` deactivate. In 210323, depots `90018300`, `90019100`, and `91017500` activate while `90016100` deactivates. No network-status change occurs at baseline or high friction. The appropriate paper statement is therefore that the interaction is primarily, but not exclusively, absorbed through inventory reconfiguration at reference financial capacity.

## Economic, budget, and service interpretation

Mean normalized objective relative to the same case/lambda Gamma-0 state rises to about 1.086 at Gamma 2 and 1.132–1.134 at Gamma 4. Mean normalized robust recourse rises to about 1.097 and 1.149–1.152. The objective trajectories are close across friction levels even though decisions differ materially: friction primarily changes how the system reconfigures, while the tested economic exposure is dominated by demand risk.

Seventy of 72 cells are budget-binding within `1e-6`. The two exceptions, 210310 at L2000 for Gamma 0 and 2, have slack `1.0136864e-6`, only `1.37e-8` beyond that threshold. Friction acts through both its direct reconfiguration charge and consumption of the shared first-stage budget, but these nearly universal binding budgets make the two channels difficult to separate empirically.

Shortage, shortage cost, service penalty, average fill rate, and minimum fill rate remain reporting diagnostics. They are evaluated separately from the optimized economic objective and should not be summarized as a general claim that higher Gamma improves service or higher friction worsens service.

## Timing

All eight timing fields are present, nonnegative, and satisfy the containment contract. The 32 new conditions have full E7 stage instrumentation; the 40 reused conditions record E7 validation/materialization time and retain source-reported historical runtime rather than fabricating unavailable historical stage splits.

For the 16 new Gamma-4 conditions, mean core PRB time is `14.43 s`, whereas mean exhaustive post-evaluation time is `3017.39 s` (about 50.3 minutes) and mean total runner wall-clock is `3040.04 s`. Post-evaluation dominates every new Gamma-4 condition. This is a reporting-layer scalability limitation; it does not indicate slow primary PRB optimization or weaken exact certification.

## Paper-level conclusion

Within the frozen Renault eight-case design, reconfiguration friction changes the intensity and composition of the response to demand risk much more than it changes whether a case begins to reconfigure. Low friction permits large, distributed inventory changes and, in two high-risk cases, depot-network changes. High friction retains the same observed trigger set but concentrates smaller adjustments on fewer depot-product coordinates. Economic exposure rises with Gamma under every friction level, while the detailed service measures remain distinct post-hoc diagnostics.
