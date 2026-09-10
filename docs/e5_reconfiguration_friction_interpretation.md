# E5 reconfiguration friction interpretation

## 1. Research question

E5 measures how the symmetric reconfiguration-friction parameter `lambda_R` changes the economic cost, magnitude, and composition of inventory reconfiguration. `lambda_R` is not a budget and is not an observed Renault parameter. Reconfiguration spending enters both the objective and the financial-budget constraint.

## 2. Experimental design

The paper-final design uses `RENAULT_EMPIRICAL_8CASE_V1`, `beta=1.00`, `Gamma=2`, and five predeclared friction levels: 0, 0.0025, 0.01, 0.05, and 0.20. The eight cases produce 40 conditions. The eight `lambda_R=0.05` observations are identity-verified reuses of E4 G2. The materiality threshold remains `RI > 1e-6`.

## 3. Completeness and certification

All 40 expected run IDs are present once, have the three required artifacts, report `OPTIMAL`, and pass exact certification. Result and first-stage-solution hashes match provenance, and each historical runner, manifest, and reporting hash matches the Git commit recorded by its run. The frozen ZIP contains 120 files and matches the result root byte for byte.

All eight L0500 first-stage artifacts are identical to their E4 G2 sources. Four E5 RI values differ from their E4 source RI only because E5 recomputed canonical RI from the identical saved `x`; every difference is below `1e-6` and does not alter materiality or economic identity.

`E5-210330-L0100` stored `global_coupling_pass=false`. A fixed-first-stage product-wise recomputation returns the identical exact recourse value, `591881.645312855`, a feasible allocation summing to Gamma 2, and zero objective reconstruction error. Its classification is `DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH`; feasibility, recourse, objective, and exact certification are unaffected. The L0500 runs inherit the previously audited E4 reuse-chain diagnostic status rather than manufacturing a missing field.

## 4. Aggregate economic effect

| lambda_R | Mean objective / L0500 | Median objective / L0500 | Mean recourse / L0500 | Mean objective change vs L0000 |
|---:|---:|---:|---:|---:|
| 0 | 0.99983880 | 0.99991857 | 0.99982029 | 0.000000% |
| 0.0025 | 0.99984654 | 0.99992273 | 0.99982892 | 0.000775% |
| 0.01 | 0.99986978 | 0.99993444 | 0.99985483 | 0.003099% |
| 0.05 | 1.00000000 | 1.00000000 | 1.00000000 | 0.016126% |
| 0.20 | 1.00058569 | 1.00030425 | 1.00065294 | 0.074718% |

From lambda 0 to 0.20, objective deterioration averages 0.074718% and has a median of 0.038574%, with a case range from numerical zero to 0.246441%. Robust recourse deterioration averages 0.083300%, has a median of 0.043287%, and ranges from numerical zero to 0.274022%. The supported wording is therefore: reconfiguration friction has a measurable but modest effect on total economic performance over the tested range.

## 5. RI response

Mean RI is 4.3271%, 3.8213%, 3.8634%, 4.0989%, and 3.0799% across the five friction levels. Median RI is 3.0287%, 1.8378%, 1.8580%, 1.9713%, and 2.2912%. Higher friction does not imply monotonically lower RI.

The four material trajectories are:

- 210129: 7.9564%, 7.9854%, 8.0733%, 8.5655%, 4.5824%.
- 210202: 12.7834%, 12.8300%, 12.9712%, 13.7620%, 7.2351%.
- 210323: 7.8200%, 3.6756%, 3.7161%, 3.9427%, 4.9940%.
- 210330: 6.0574%, 6.0795%, 6.1464%, 6.5211%, 7.8277%.

The other four cases remain below the frozen materiality threshold at every level.

## 6. Case heterogeneity

For 210129 and 210202, RI rises through lambda 0.05 and drops at 0.20. Both retain three materially changed pairs while the largest-pair share rises from about 72.7% to 80.0%. For 210323, the move from lambda 0 to 0.0025 reduces changed pairs from four to two and sharply lowers RI; RI then increases while the two-pair composition remains concentrated. For 210330, changed pairs move from four to two and back to four while RI rises over the grid. These patterns show magnitude and composition substitution, not uniform shrinkage of every coordinate.

## 7. Extensive and intensive margins

Exactly four of eight cases materially reconfigure at every tested lambda. The incidence is therefore unchanged over the grid, while RI, changed-pair composition, and concentration change substantially within those four cases. Over this tested range, friction primarily affects the intensive margin and composition of reconfiguration rather than the incidence of whether reconfiguration occurs. This is an empirical grid result, not a continuous friction threshold.

## 8. Budget mechanism

Mean and median budget utilization are numerically 100% at every friction level. As lambda rises, reconfiguration spending increases and inventory spending generally falls in the four adjusted cases, while robust recourse increases. For example, 210202 inventory spending falls from `105389.9999990062` to `104445.99999938402`, reconfiguration spending rises from zero to `943.9999996221973`, and robust recourse rises by 0.2740%. Thus friction works through both channels built into the model: it directly penalizes movement in the objective and consumes scarce first-stage budget.

## 9. Optimal-face audit

There are 13 adjacent-lambda pairs with material RI increases. For each pair, the lower-friction solution becomes budget-infeasible at the higher lambda when its same physical movement is repriced. The higher-friction solution is feasible at the lower lambda but has an objective gap larger than `1e-4`. None of the 13 pairs is a known optimal-face-equivalent substitution.

At lambda zero, canonical RI is computed only from `x-x0`, solver adjustment degeneracy is excluded, and RS is zero for all cases. Cross-evaluation of the already-saved solutions finds no material RI range among known points on the L0000 objective face. The four stay-put cases contain multiple numerically equivalent saved points, but all RI differences remain below `1e-6`. No secondary first-stage optimization was run, so these are known-solution checks rather than exhaustive minimum/maximum RI face bounds.

The observed non-monotonicity is therefore not supported as an optimal-face or reporting artifact. It is consistent with structural reallocation under a binding budget and heterogeneous inventory-cost weights.

## 10. Service metrics

Service measures do not move uniformly. From lambda 0 to 0.20, average fill rate improves by 0.122 and 0.281 percentage points in 210129 and 210202, but declines by 0.212 and 0.378 points in 210323 and 210330. Shortage cost, service penalty, and transport cost also move differently by case. These metrics describe the worst-case solution but are not themselves the optimized objective; higher friction should not be described as uniformly worsening service.

## 11. Depot-network stability

No condition changes its active-depot identity set: opened and closed depot lists are empty in all 40 results. The observed friction responses are implemented through inventory-level adjustment rather than depot-network redesign.

## 12. Managerial implications

Increasing movement friction need not reduce the number of units moved. When the budget binds, the model can switch toward a smaller set of lower-cost or economically different inventory movements, reduce final-inventory spending, and accept higher robust recourse. Managers should therefore interpret lambda as shaping the composition and budget burden of adjustment, not as a direct cap on RI.

## 13. Limitations

The conclusions apply to five tested lambda values, one beta, one Gamma, and eight Renault-derived cases. They do not establish a continuous threshold or a monotonic theorem. The optimal-face assessment uses cross-evaluation of existing certified solutions only; exhaustive face extrema would require additional first-stage optimization and was intentionally not run.

## 14. Recommended paper wording

“Higher reconfiguration friction does not uniformly suppress adjustment intensity; instead, it changes the magnitude and composition of inventory reconfiguration in a case-dependent manner.”

“Over the tested range, friction primarily affects the intensive margin of reconfiguration rather than the incidence of whether adjustment occurs.”

“Because the first-stage budget is binding, reconfiguration friction operates through both a direct objective penalty and competition for first-stage expenditure.”
