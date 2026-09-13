# E6 budget-risk interaction protocol

## Research question

E6 asks how financial capacity changes the effect of demand uncertainty on robust inventory reconfiguration. It is a two-dimensional interaction design, not a repetition of the one-dimensional E3 budget and E4 risk analyses.

The experiment separates economic outcomes, inventory reconfiguration, financial-budget use, and service diagnostics. Service measures describe outcomes; they are not the optimized objective.

## Frozen design

- Dataset: `RENAULT_EMPIRICAL_8CASE_V1`.
- Cases: 210202, 210628, 210129, 210310, 210330, 210323, 210428, and 210611.
- Financial-capacity levels: beta 0.8 (tight), 1.0 (reference), and 1.2 (relaxed), with `B=beta*B_ref`.
- Demand-risk levels: Gamma 0, 2, and 4. Gamma counts simultaneously adverse region-product demand components; it is neither a product count nor a region count.
- Reconfiguration friction: `lambda_R=0.05`.
- Materiality: canonical `RI > 1e-6`.
- Method: the frozen exact PRB-Benders implementation and exact-certification contract.

The Cartesian product has 72 conditions. The runner accepts only budget tokens `B080`, `B100`, and `B120`, and risk tokens `G0`, `G2`, and `G4`.

## Reuse contract

E6 discovers candidate sources from frozen E3 and E4 artifacts. Reuse requires exact dataset, case, instance, x0, calibration, mapping, B_ref, beta, Gamma, lambda, solver-profile, model, provenance, artifact-hash, objective-accounting, and certification identity.

The independently discovered reusable parameter cells are:

- E3: B080-G2, B100-G2, and B120-G2.
- E4: B100-G0 and B100-G4.

B100-G2 exists in both E3 and E4. E6 verifies their first-stage and economic identity, selects the E3 artifact once, and records the E4 artifact as corroborating provenance. It never double-counts the overlap. Across eight cases this yields 40 reusable conditions and 32 new-solve conditions; these counts are computed from artifacts rather than stored as runner constants.

Any reuse mismatch blocks authorization. The runner neither silently reuses a mismatched result nor silently replaces it with a new solve.

## Static feasibility

The preflight uses a constructive feasible point and invokes no optimizer: deactivate all depots, set final inventory to zero, use `a_minus=x0`, and meet second-stage demand through shortage and service-violation variables. For every case, the resulting removal cost at `lambda_R=0.05` is below the tight B080 budget. Capacity, upper-bound, reconfiguration-balance, and recourse feasibility therefore hold for the B080-G4 corner without changing any parameter.

This construction establishes mathematical feasibility only. It does not predict the optimized E6 outcome.

## Interaction estimands

All normalization uses the case-specific B100-G2 E6 cell. For each case and beta, reporting computes the G0-to-G4 change in RI, objective, robust recourse, and RS. The descriptive tight-versus-relaxed interaction contrast is

`[Y(B080,G4)-Y(B080,G0)] - [Y(B120,G4)-Y(B120,G0)]`.

This contrast describes a controlled optimization experiment; it is not a causal estimator. The report separately classifies extensive responses (whether material reconfiguration occurs) and intensive responses (how much an already-adjusting case changes). `first_material_gamma_observed_in_e6_grid` may be 0, 2, 4, or `none_through_4`; it is not a continuous threshold.

Budget binding is recomputed for every condition. A transition from slack at B120-G0 to binding at B120-G4 may be described as risk consuming financial slack only if the completed results support it.

## Future reporting

After all 72 certified artifacts exist, `scripts/summarize_e6_budget_risk_results.py` will create:

- `artifacts/e6_table_budget_risk_interaction_case_level.csv`;
- `artifacts/e6_table_budget_risk_interaction_aggregate.csv`;
- `artifacts/e6_table_interaction_contrasts.csv`.

`scripts/plot_e6_budget_risk_results.py` will create four white-background matplotlib figures in PNG and PDF: RI interaction, normalized-objective interaction, budget-utilization heatmap, and material-reconfiguration heatmap. No table or figure is generated before formal results exist.

## Execution controls

The result namespace is `experiments/results/e6_budget_risk_interaction_v1/`. It is isolated from E1-E5 and protected against overwrite. Writes are atomic and preserve the complete first-stage solution, result, provenance, hashes, and available exact-certification data.

The authoritative paper-final manifest is `experiments/configs/formal/e6_budget_risk_interaction_authorization.json`. The earlier two-case `e6_budget_risk_interaction.yaml` remains an untouched historical protocol artifact and is not an E6 execution authority.

`--dry-run` enumerates and validates all conditions, sources, hashes, configuration, and static feasibility. It cannot invoke the optimizer. Formal execution fails closed while `formal_run_authorized=false` and requires a clean committed worktree and a matching passed static-audit/config hash.

No E6 formal optimization is authorized or executed during protocol preparation.
