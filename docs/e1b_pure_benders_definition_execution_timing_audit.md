# E1b Pure Benders definition, execution path, and timing audit

## Decision

`PURE_BENDERS_AUDIT_PASS`

This is a static/code-path and frozen-artifact audit. No optimization was run,
and the existing `E1B-210202-PURE` result was not modified.

## A. Exact algorithm definition

`PURE_BENDERS_DEFINITION_CONFIRMED`

The master contains the unchanged first-stage variables \(y,x,a^+,a^-\) and
one aggregate robust-recourse surrogate \(\theta\). It contains no
\(\eta_{j,g}\). At iteration \(k\), it adds at most one cut,

\[
\theta \ge \alpha^k + \sum_{i,j}\mu^k_{ij}x_{ij}.
\]

The separation problem is one global adversarial MILP. For the 210202
instance, that one model creates every one of the \(12\times8=96\) binary
variables \(z_{rj}\) and directly adds

\[
\sum_{r,j}z_{rj}\le 2.
\]

The Pure module and runner do not import or call `ProductRiskSubproblem`,
`compose_risk_budget`, `risk_budget_composition`, `standard_benders`, or
`product_risk_budget_benders`. They have no product-risk tables, local
\(V_{j,g}\), Gamma-allocation DP, PRB cut pool, or structured oracle.

## B. 210202 execution path

The actual call chain is:

1. `experiments.run_e1b_pure_benders_local.main`
2. `validate_execution_gate` and identity/hash/no-overwrite checks
3. `load_instance`, then `solve_pure_benders`
4. `_build_pure_master`
5. `GlobalRobustAdversarialSubproblem.__init__`
6. each iteration: `master.optimize`
7. `GlobalRobustAdversarialSubproblem.solve`
8. global MILP `model.optimize`
9. extraction of all \(z,\mu\), followed by \(\alpha\) and one
   `PureAggregateCut`
10. `evaluate_fixed_scenario_recourse_global` and its all-product LP
    `optimize` for strong-duality certification
11. aggregate-cut addition and relative-gap/no-violation convergence check
12. final `GlobalRobustAdversarialSubproblem.solve` at the incumbent
13. `build_first_stage_solution_artifact`, JSON serialization, provenance
    hashes, and atomic directory move

All loops use the complete depot, region, and product ranges. The global
recourse LP contains 1,440 shipment variables/terms, 96 shortages, and eight
service-violation variables. The instance contains 90 positive and six zero
demand deviations; all 96 corresponding \(z\) variables nevertheless remain
binary and free subject to the global Gamma row. No region or product is
screened out.

`PURE_BENDERS_HIDDEN_STRUCTURE_LEAKAGE = false`.

## C. Global adversarial MILP

For fixed \(x\), the model maximizes

\[
\begin{aligned}
&\sum_{rj}\bar d_{rj}\pi_{rj}+\sum_{ij}x_{ij}\mu_{ij}
-\sum_j(1-s_j)\Bigl(\sum_r\bar d_{rj}\Bigr)\kappa_j\\
&\quad+\sum_{rj}\hat d_{rj}
\left[w_{rj}-(1-s_j)t_{rj}\right],
\end{aligned}
\]

where \(w=z\pi\), \(t=z\kappa\) are exact bounded linearizations and

\[
\pi_{rj}+\mu_{ij}\le c_{irj},\qquad
\pi_{rj}-\kappa_j\le p_{rj},\qquad
0\le\kappa_j\le q_j.
\]

Thus it directly represents \(\max_{z\in U(\Gamma)}Q(x,z)\); it does not
compute product-wise values and aggregate them afterward. The bounds
\(\pi_{rj}\le p_{rj}+q_j\) and \(\kappa_j\le q_j\) make both linearizations
exact. The returned scenario is checked by an independent all-product primal
recourse LP, and the dual/primal difference is stored in each cut as the
strong-duality error.

For 210202:

| Item | Count/value |
|---|---:|
| Depots \(I\) | 15 |
| Regions \(R\) | 12 |
| Products \(J\) | 8 |
| Gamma | 2 |
| Binary \(z\) | 96 |
| Core dual variables \(\pi,\mu,\kappa\) | 224 |
| Linearization auxiliaries \(w,t\) | 192 |
| Continuous variables total | 416 |
| Variables total | 512 |
| Constraints | 2,113 |

All shock indicators are present and binary; the only fixed restriction on
them is the global cardinality limit. All demand, supply, service,
transportation, shortage, service-penalty, nominal-demand, deviation, and
inventory-dual terms are present.

## D. Frozen 210202 result

Artifact:
`experiments/results/e1b_pure_benders_v1/E1B-210202-PURE/result.json`

SHA-256:
`531e9ab4a43bed715248808518bb977db687cf0ec56fcb0adc90b8587ae0cb88`

| Field | Frozen value |
|---|---:|
| run_id | E1B-210202-PURE |
| status | OPTIMAL |
| exact certification | true, established by runner acceptance path |
| certification status | CERTIFIED_PURE_BENDERS_EXACT |
| objective | 1,058,780.7942496866 |
| LB | 1,058,780.7942496866 |
| UB | 1,058,780.7942496866 |
| absolute gap | 0 |
| relative gap | 0 |
| iterations | 9 |
| aggregate cuts | 8 |
| T_core | 0.41859719999774825 s |
| master optimize time | 0.06973239999206271 s |
| global adversarial optimize time | 0.21662959997775033 s |
| fixed-scenario certification time | 0.06623270000272896 s |
| cut construction time | NOT RECORDED SEPARATELY |
| post-evaluation/serialization time | 0.05900870000186842 s |
| total runner wall-clock | NOT RECORDED |
| recorded component sum, not a wall-clock field | 0.47760589999961667 s |
| Gurobi | 13.0.2 |

The result JSON does not contain a standalone `exact_certification_pass`
boolean. The value is nevertheless true under the frozen code path: the runner
refuses to serialize a formal result unless `status == "OPTIMAL"` and
`exact_certification_pass` is true, and it records
`CERTIFIED_PURE_BENDERS_EXACT`. This is a provenance observation, not a schema
change.

The frozen PRB objective is 1,058,780.7942496866 and the Direct objective is
1,058,780.7942496864. Pure minus PRB is exactly zero at stored precision; Pure
minus Direct is approximately \(2.33\times10^{-10}\). Both pass the frozen
\(10^{-4}\) objective-consistency tolerance.

## E. Timing contract

### Pure Benders T_core

The timer starts immediately before `_build_pure_master` and stops while
constructing the returned `PureBendersResult`, after final certification.

| Component | Included in T_core? |
|---|---|
| Master model construction | YES |
| Every master `optimize()` | YES |
| Global adversarial MILP construction | YES |
| Every global adversarial `optimize()` | YES |
| Dual/scenario extraction | YES |
| Aggregate-cut construction/addition | YES |
| Gap and convergence checks | YES |
| Per-iteration and final fixed-scenario LP certification | YES |
| Result JSON/provenance/reporting | NO |

`global_oracle_runtime_seconds` is narrower than T_core: it records only the
MILP `optimize()` calls. `certification_runtime_seconds` accumulates all ten
fixed-scenario LP checks (nine iterations plus final certification), not only
the final check. Construction, extraction, cut, and convergence time remain in
T_core but are not separate artifact fields.

### Frozen PRB T_core

The PRB timer starts before `_build_master` and before all eight
`ProductRiskSubproblem` objects/tables are constructed. It stops after final
product-risk evaluation, Gamma composition, certification checks, and result
construction.

| Component | Included in PRB T_core? |
|---|---|
| PRB master construction | YES |
| Every master `optimize()` | YES |
| Product-risk scenario/table construction | YES |
| All product subproblem solves/extraction | YES |
| Gamma allocation enumeration/composition | YES |
| Product-cut construction/addition | YES |
| Gap and convergence checks | YES |
| Final structured certification | YES |
| Runner post-evaluation/reporting | NO |

The PRB component field `subproblem_runtime_seconds` is also narrower than its
T_core, but the published `runtime_seconds` includes construction, DP,
cut-handling, and overhead. Therefore the method-level T_core definitions have
the same boundary: all algorithm work from model construction through exact
certification, excluding runner reporting.

`PURE_VS_PRB_TIMING_COMPARABLE`.

## F. Why the 210202 run is fast

The artifact supports only these factual statements:

- convergence took nine master iterations and eight aggregate cuts;
- ten global adversarial MILP solves, including final certification, consumed
  0.2166296 seconds in aggregate, or 0.0216630 seconds per call as an aggregate
  average;
- all fixed-scenario recourse checks consumed 0.0662327 seconds;
- the master solves consumed 0.0697324 seconds;
- the complete algebraic adversarial model has only 512 variables and 2,113
  constraints before presolve.

The following were not persisted and cannot be reconstructed without a rerun:

| Question | Audit answer |
|---|---|
| Presolved model size | UNKNOWN / NOT RECORDED |
| Root-relaxation strength | UNKNOWN / NOT RECORDED |
| Branch-and-bound node count | UNKNOWN / NOT RECORDED |
| Per-oracle solve times | UNKNOWN / NOT RECORDED |
| Fraction completed at the root node | UNKNOWN / NOT RECORDED |
| Number of binaries fixed by presolve | UNKNOWN / NOT RECORDED |
| Number of shock components materially competing | UNKNOWN / NOT RECORDED |

Consequently, the 0.4186-second T_core is a credible frozen observation, but
the audit cannot attribute it specifically to Gamma=2, presolve, root-node
solution, or a small competitive uncertainty set.

## G. Historical Benders versus new Pure Benders

| Dimension | Historical Benders | New Pure Benders |
|---|---|---|
| Source | old repo PR 82, commit `b78f6c9` | current PR 11, commit `ce68bf4` |
| Mathematical model | old robust inventory model | Reconfiguration Model V2 with \(x^0,a^+,a^-\) |
| Dataset | old Renault formal v6 | RENAULT_EMPIRICAL_8CASE_V1 |
| Raw date case | 210202 | 210202 |
| Formal mapping/instance | old formal package | new deterministic 12-region mapping and new hashes |
| Gamma | 2 | 2 |
| Master | single \(\theta\), old first stage | single \(\theta\), current first stage |
| Robust SP | global robust dual MILP | global robust dual MILP plus independent global primal LP check |
| SP calls/iteration | one primary global MILP at fixed Gamma; optional core-point auxiliary stages | one exact global MILP plus one fixed-scenario global LP |
| Precision | adaptive master/SP precision, ending at historical contract | exact frozen Gurobi profile (`MIPGap=0`) |
| Core-point strengthening | enabled; 16.5293 s auxiliary time | absent |
| Stabilization | no separate stabilization component established | absent |
| Cut | at most one aggregate, potentially core-point strengthened | one unstrengthened aggregate supporting cut |
| Iterations/cuts | 2,154 / 2,154 | 9 / 8 |
| Termination | 1,800 s time limit, uncertified, gap 0.000327302 | exact no-violation termination and final certification |
| Runtime | 1,800.1849 s | 0.4185972 s T_core |
| Runtime boundary | algorithm runtime; post-evaluation not separately identified | algorithm T_core; reporting excluded |

The 1,800-to-sub-second contrast is not an apples-to-apples speedup. Concrete
differences include the formal dataset/mapping, mathematical first stage,
precision policy, cut-strengthening path, certification path, and—most
importantly—the observed 2,154-cut master versus the new eight-cut master. The
historical audit classified 84.53% of its runtime as master time and 14.15% as
robust-subproblem time. These execution differences can explain the contrast;
the available evidence does not isolate any one of them causally.

## H. Three current methods

| Method | Master surrogate | Cut granularity | Robust oracle | Product decomposition | Gamma allocation decomposition | Per-iteration SP work | Structural idea |
|---|---|---|---|---|---|---|---|
| Pure Benders | one \(\theta\) | one aggregate cut | one global adversarial dual MILP | no | no | one global MILP plus global primal certification LP | classical global robust separation |
| Aggregate Benders + Structured Oracle | one \(\theta\) | one aggregate cut assembled from selected product cuts | product scenario LPs plus exact Gamma composer | yes, oracle only | yes, oracle only | eight product-model solves returning local-budget values, then composition | structured oracle with aggregate master |
| PRB-Benders | \(\theta\) and \(\eta_{j,g}\) | product-budget cuts | product scenario LPs plus exact Gamma composer | yes | yes | eight product-model solves and all product-budget cut checks | exposes product/risk-budget structure in both oracle and master |

The recommended paper labels are exactly those in the table. The existing
code and frozen result names need not change.

## I. Recommendation

The stored 210202 runtime is internally consistent and comparable with the
frozen PRB T_core. No timing instrumentation repair or baseline redefinition
is required before continuing the remaining seven authorized cases. Future
interpretation should report the fast result as an empirical observation and
avoid unsupported claims about presolve or root-node behavior. If those
mechanisms are important for the paper, they require a separately authorized
instrumented experiment rather than reconstruction of this frozen run.

`formal optimization runs during this audit = 0`.
