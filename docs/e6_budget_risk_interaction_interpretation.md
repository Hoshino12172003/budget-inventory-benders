# E6 Budget × Demand-Risk Interaction

## 1. Research question

E6 examines how financial capacity changes the response of the robust inventory plan to demand-risk exposure. The analysis is descriptive evidence from a controlled optimization experiment; its interaction contrasts are not causal difference-in-differences estimates.

## 2. Experimental design

The frozen design uses eight cases from `RENAULT_EMPIRICAL_8CASE_V1`, `beta` in `{0.8, 1.0, 1.2}`, `Gamma` in `{0, 2, 4}`, and `lambda_R=0.05`. The 72 cells contain 40 identity-validated reused results and 32 new formal solves. Normalized objective and recourse values use each case's B100-G2 cell as the reference.

## 3. Completeness and certification

All 72 expected run IDs are present exactly once. Every result reports `OPTIMAL`, `CERTIFIED_PRB_EXACT`, and `exact_certification_pass=true`. Provenance hashes, saved first-stage payloads, objective decomposition, static first-stage feasibility, and reuse identities pass. The review ZIP and result root are byte-identical for all 216 primary files. Forty-eight results carry `global_coupling_pass=true`; the remaining 24 are reused E3 artifacts whose earlier schema did not contain that diagnostic. This absence is provenance-traceable and is not treated as a failure.

## 4. Aggregate 3×3 results

| beta | Gamma | mean normalized objective | mean normalized recourse | mean RI | median RI | material cases | y-network changes | mean budget use | binding cases |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.8 | 0 | 0.931844 | 0.947238 | 0.368066 | 0.368746 | 8/8 | 6/8 | 1.000000 | 8/8 |
| 0.8 | 2 | 1.010323 | 1.034910 | 0.368066 | 0.368746 | 8/8 | 6/8 | 1.000000 | 8/8 |
| 0.8 | 4 | 1.053720 | 1.083412 | 0.368066 | 0.368746 | 8/8 | 6/8 | 1.000000 | 8/8 |
| 1.0 | 0 | 0.922213 | 0.913100 | 0.000000 | 0.000000 | 0/8 | 0/8 | 1.000000 | 8/8 |
| 1.0 | 2 | 1.000000 | 1.000000 | 0.040989 | 0.019713 | 4/8 | 0/8 | 1.000000 | 8/8 |
| 1.0 | 4 | 1.042279 | 1.047251 | 0.124536 | 0.154597 | 5/8 | 0/8 | 1.000000 | 8/8 |
| 1.2 | 0 | 0.922213 | 0.913100 | 0.000000 | 0.000000 | 0/8 | 0/8 | 0.833333 | 0/8 |
| 1.2 | 2 | 0.999751 | 0.998197 | 0.010384 | 0.004994 | 4/8 | 0/8 | 0.844419 | 0/8 |
| 1.2 | 4 | 1.041251 | 1.041393 | 0.031552 | 0.039165 | 5/8 | 0/8 | 0.866719 | 0/8 |

## 5. Economic interaction

From Gamma 0 to 4, the mean case-level objective increase is 13.27% at beta 0.8, 13.22% at beta 1.0, and 13.11% at beta 1.2. The corresponding robust-recourse increases are 14.61%, 14.95%, and 14.31%. The narrow cross-budget spread supports approximately additive aggregate economic exposure, not strong scarcity amplification. The mean tight-versus-relaxed descriptive interaction contrast is 2,146.68 objective units and 5,338.71 recourse units; these absolute differences are small relative to the objective scale and heterogeneous by case.

## 6. Reconfiguration interaction

The decision response is much stronger than the economic interaction. Mean RI changes from Gamma 0 to 4 are approximately 0.0000 at beta 0.8, 0.12454 at beta 1.0, and 0.03155 at beta 1.2. Mean DID-RI is -0.03155 for tight versus relaxed capacity and 0.09298 for reference versus relaxed capacity. The primary classification is `RECONFIGURATION_SATURATION_UNDER_TIGHT_BUDGET`, with `STRONG_DECISION_WEAK_ECONOMIC_INTERACTION` as a secondary description.

## 7. B080 saturation and composition mechanism

At beta 0.8, every case already makes a material adjustment under Gamma 0, every financial budget binds, and mean RI is 36.8066% at all three tested Gamma values. This is consistent with financial scarcity dominating the aggregate adjustment magnitude and inducing saturation before additional demand shocks are introduced.

Constant RI does not logically imply identical decisions. The coordinate audit finds one material composition change: case 210310 changes two inventory coordinates with an L1 difference of 6.6667 between G0 and G4 while retaining essentially identical RI. The other seven B080 cases have no coordinate change above `1e-6`. Economic exposure still rises because worst-case recourse changes with Gamma even when first-stage inventory is unchanged.

## 8. Extensive versus intensive margin

At beta 0.8, the extensive margin is already exhausted at the first tested point: 8/8 cases are material at Gamma 0, so subsequent Gamma comparisons are intensive-margin comparisons. At beta 1.0 and 1.2, 210202, 210129, 210330, and 210323 first become material at Gamma 2; 210310 first becomes material at Gamma 4; and 210628, 210428, and 210611 remain non-material through Gamma 4. These are tested-grid observations, not exact continuous risk thresholds.

## 9. Budget binding and slack

All B080 and B100 cells bind. No B120 cell binds. At B120, mean utilization rises from 83.33% at G0 to 84.44% at G2 and 86.67% at G4, while mean slack falls from 15,627.99 to 12,435.96. Higher demand risk therefore consumes part of the available financial slack but does not exhaust it over the tested range.

## 10. Active-depot and network response

The formal network measure is the binary planning-period activation variable `y_i`; positive-inventory depot status is reported separately. They coincide in all 72 E6 cells, but the interpretation remains planning-period operation rather than permanent facility closure.

At beta 0.8, six cases contract their `y`-active set at every tested Gamma. Cases 210202, 210628, 210323, 210330, and 210428 move from two active depots to one by deactivating depot `9624708`. Case 210611 moves from five to three by deactivating `90015700` and `90038200`. Cases 210129 and 210310 do not change their active set. No B100 or B120 condition changes `y`. Thus, under severe financial scarcity, adaptation can extend beyond inventory reallocation to contraction of the planning-period active depot footprint.

## 11. Service outcomes

Service metrics are diagnostics, not terms optimized independently of the economic objective. Mean minimum fill rate is essentially zero throughout. Mean average fill rate is approximately flat at B080, falls from 0.1408 to 0.1272 at B100, and rises modestly from 0.1408 to 0.1427 at B120 as Gamma moves from 0 to 4. Shortage and service-penalty costs increase with Gamma. Case-level responses are heterogeneous, so the results do not justify claims that more budget or more robustness uniformly improves every service measure.

## 12. Case heterogeneity

The common extensive-margin pattern at B100 and B120 masks different adjustment magnitudes. The strongest G0-to-G4 RI increases occur in 210310 and 210323, while three cases remain at their nominal incumbent through G4. At B080, network contraction occurs in six cases, but only 210310 changes its inventory composition materially as Gamma rises.

## 13. Runtime accounting audit

`runtime_seconds` is the PRB routine's `perf_counter` interval. It starts immediately before master construction and ends after final exact product-recourse certification. It includes master solves, product separation, and the final product-wise certification. It excludes instance/x0 loading and, critically, the subsequent `evaluate_e4_service` call, along with metric construction, artifact construction, hashing, provenance generation, file writing, process startup, and external idle time.

For Gamma 4, the excluded service/reporting stage constructs 6,352 product-risk blocks and enumerates 3,469,497 global scenarios. This explains why a run can report seconds of PRB time yet occupy the process for tens of minutes or longer. Completion-to-completion gaps for new G4 artifacts range from 2,302 to 16,901 seconds, with a median of 3,165 seconds, while reported PRB runtimes range from 7.28 to 32.73 seconds, with a median of 11.98 seconds. These gaps corroborate the missing timing stage but are not exact run durations: no runner start timestamp was persisted, and the largest gap can include pauses or other external delay.

The runtime classification is `CORE_SOLVER_TIME_ONLY`, `POST_EVALUATION_EXCLUDED_FROM_TIMER`, `RUNNER_WALLCLOCK_NOT_CAPTURED`, and `MULTI_STAGE_TIMING_ACCOUNTING_GAP`. Exact historical certification/post-evaluation/reporting/write breakdowns cannot be reconstructed without retrospective fabrication, so primary runtime fields remain unchanged.

## 14. Computational difficulty

The core PRB iteration count does not explode. Mean iterations are 3.5 at B080-G0, 3.375 at B080-G4, 5.0 at B120-G0, and 5.375 at B120-G4. However, mean subproblem evaluations rise from 36 to 175 at B080 and from 48 to 255 at B120; mean cuts rise from 9.5 to 45 and from 13 to 60.625. Core PRB runtime consequently rises from roughly 0.08–0.10 seconds at G0 to 13.0–14.6 seconds at G4. The much larger user-observed wall-clock increase is dominated by the excluded exhaustive post-evaluation rather than iteration explosion. The root cause is therefore mixed: more expensive per-iteration/certification work inside PRB, followed by a dominant reporting-stage enumeration outside its timer.

## 15. Managerial implications

Financial scarcity changes the mode of adaptation rather than uniformly amplifying the effect of demand risk. Under tight capacity, substantial reconfiguration and frequent planning-period depot contraction already occur under nominal demand. At reference capacity, increasing risk induces progressively stronger inventory reconfiguration; under relaxed capacity the response is more moderate and consumes slack without exhausting it.

## 16. Limitations

- The beta grid contains only 0.8, 1.0, and 1.2.
- The Gamma grid contains only 0, 2, and 4; observed transitions are not continuous thresholds.
- `B_ref` is calibrated and is not an observed corporate budget.
- Evidence comes from eight Renault-derived empirical cases.
- Service metrics are diagnostics rather than the primary objective.
- Historical runner wall-clock and stage-level timing are unavailable.
- Active-depot conclusions refer to planning-period `y_i`, not permanent warehouse closure.

## 17. Recommended paper wording

> Financial scarcity changes the mode of adaptation rather than uniformly amplifying the effect of demand risk. Under tight financial capacity, substantial reconfiguration is already induced under nominal demand, leaving little additional aggregate RI response to higher uncertainty. At reference capacity, increasing uncertainty induces progressively stronger inventory reconfiguration, whereas under relaxed capacity the adjustment response is more moderate. Budget and demand risk interact strongly in reconfiguration decisions but only weakly in aggregate economic exposure. Severe financial scarcity can also contract the planning-period active depot footprint.
