# E3 budget sensitivity interpretation

## 1. Research question

E3 asks how financial capacity changes the robust inventory-reconfiguration solution, its economic objective, and the intensity of movement away from the nominal incumbent configuration.

## 2. Experimental design

The experiment contains eight Renault-data-derived cases and five budget multipliers, for 40 conditions. Each condition uses `Gamma=2`, `lambda_R=0.05`, and `B=beta * B_ref(case)`, with `beta` in `{0.80, 0.90, 1.00, 1.10, 1.20}`. `B_ref` is a model-derived reference expenditure, not observed Renault financial data. The B100 observations are the eight identity-verified reused results; the other 32 runs were completed before this audit.

## 3. Data completeness

All 40 expected run IDs are present and unique. All results are optimal, exactly certified under the frozen contract, budget feasible, and consistent with the frozen dataset, mapping, instance, incumbent, calibration, model, and solver identities. All 120 primary JSON files match the frozen result archive byte for byte. B100 reuse is `8/8`.

## 4. Economic performance

Mean normalized objective values for B080 through B120 are `1.010323`, `1.003081`, `1.000000`, `0.999751`, and `0.999751`; the corresponding medians are `1.010114`, `1.003025`, `1.000000`, `0.999890`, and `0.999890`. Economic performance therefore improves as budget availability increases, but the marginal benefit diminishes over the tested range. This is descriptive evidence from the tested instances, not an inferential significance claim.

## 5. Reconfiguration intensity

Mean RI values are `0.368066`, `0.264085`, `0.040989`, `0.010384`, and `0.010384`; medians are `0.368746`, `0.253044`, `0.019713`, `0.004994`, and `0.004994`. Material reconfiguration occurs in 8, 8, 4, 4, and 4 cases, respectively, using the pre-existing `1e-6` reporting tolerance. The observed reduction in RI with increasing beta is an empirical pattern over this grid, not a mathematical monotonicity result.

## 6. Budget utilization and diminishing returns

B080, B090, and B100 are essentially binding on average. Mean utilization falls to `92.118%` at B110 and `84.442%` at B120. All eight objectives are unchanged from B110 to B120 within the existing reporting tolerance. Four cases first exhibit an empirical plateau at B100 and four at B110. These are tested-grid plateaus, not universal optimal budget thresholds.

## 7. Scarcity-induced versus risk-induced reconfiguration

At B100, cases 210310, 210428, 210611, and 210628 have no material reconfiguration. At B080/B090 their RI values are respectively `0.3403/0.2406`, `0.3791/0.2253`, `0.3648/0.2286`, and `0.3893/0.2241`. This supports distinguishing risk-induced reconfiguration at baseline financial capacity from scarcity-induced reconfiguration under tighter budgets. These terms interpret observed mechanisms; they are not new model variables or theorems.

## 8. Service and shortage metrics

The case-normalized robust recourse mean decreases from `1.034910` at B080 to `1.015131` at B090, `1.000000` at B100, and `0.998197` at B110/B120. Service, shortage, and fill-rate components need not change monotonically because different worst scenarios can have equal recourse cost but different component decompositions. They should therefore be reported together with the selected scenario identity and economic recourse.

## 9. 210330 B110/B120 tie

The two saved first-stage states differ only by `1.1369e-13`, and both fixed-state evaluations have exact recourse `590417.1700726735`. Two Gamma=2 scenarios tie for worst economic recourse but have different shortage/service/transport decompositions. The classification is `REPORTING_SCENARIO_SELECTION_TIE`. The saved total-shortage difference must not be interpreted as service worsening from B110 to B120.

## 10. Managerial implications

Within the tested design, tighter budgets are associated with more intensive inventory reconfiguration and higher robust economic cost. Expanding budget toward the B100-B110 region captures most of the observed benefit, while further expansion often creates slack without additional objective improvement. The case heterogeneity cautions against applying one saturation multiplier mechanically across operating settings.

## 11. Limitations

The evidence covers eight Renault-data-derived instances, a fixed uncertainty budget and friction level, and five discrete budget multipliers. It does not identify Renault's actual financial budget, prove RI monotonicity, establish a universal saturation threshold, or support causal or inferential claims beyond the tested design.

## 12. Recommended paper wording

> Across the eight Renault-data-derived instances and the tested budget grid, tighter financial budgets are associated with more intensive inventory reconfiguration. Economic performance improves as budget availability increases, but the marginal benefit diminishes: many instances exhibit an empirical plateau in the B100-B110 region, and all tested objectives are unchanged from B110 to B120 within the frozen reporting tolerance. Some instances requiring no material risk-induced reconfiguration at the baseline budget nevertheless undergo substantial scarcity-induced reconfiguration under tighter financial capacity.

Supporting flat, one-row-per-observation tables are in `artifacts/e3_table_budget_sensitivity_case_level.csv`, `artifacts/e3_table_budget_sensitivity_aggregate.csv`, and `artifacts/e3_table_budget_thresholds.csv`.
