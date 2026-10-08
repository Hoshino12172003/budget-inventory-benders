# Service-metric semantics audit

## Scope and conclusion

This audit reads the 40 post-run-audited results in
`experiments/results/service_calibration_robustness_v2_fixed_recourse` and the
associated 186,280 saved scenario rows. It does not run an optimizer or alter
any formal result.

The reporting implementation is internally consistent, but its service fields
do not all refer to the same scenario and its `aggregate_fill_rate` is not the
fill-rate counterpart of the model's SLA constraint. The low reported rates are
real under the implemented definition, not a numerator/denominator or indexing
error. The decline at `SL=0.95` is also present under fixed-scenario and
demand-weighted derived metrics; it is not caused by a change in the selected
reporting scenario.

## Exact definitions

Let `i`, `r`, `j`, and `omega` index depots, regions, products, and a full demand
scenario. Let `q_irj(omega)` be shipment, `u_rj(omega)` shortage, and
`d_rj(omega)` demand. For a region define

```text
D_r(omega) = sum_j d_rj(omega)
U_r(omega) = sum_j u_rj(omega)
FR_r(omega) = 1                              if D_r(omega) = 0
              1 - U_r(omega) / D_r(omega)    otherwise.
```

Products are therefore pooled inside each region. The implementation does not
first calculate product fill rates.

For each scenario:

```text
scenario_minimum_fill(omega) = min_r FR_r(omega)
scenario_average_fill(omega) = (1 / |R|) sum_r FR_r(omega).
```

`scenario_average_fill` is an equal-region macro-average. It is not
`1 - total_shortage / total_demand`; regions with small and large demand receive
equal weight.

The service-reporting identity is

```text
(omega_service, r_service)
    = canonical first argmin_(omega,r) FR_r(omega),
```

where a new minimum must improve by more than `1e-12`. Scenarios use canonical
region-major enumeration and contain at most `Gamma=2` shocks. Consequently:

```text
minimum_fill_rate = FR_r_service(omega_service)
                  = min_(omega,r) FR_r(omega)

aggregate_fill_rate = scenario_average_fill(omega_service).
```

Despite its name, `aggregate_fill_rate` is therefore the equal-region average
inside one endogenously selected worst-minimum-fill scenario. It is not averaged
over scenarios and it is not taken from the worst-recourse scenario.

The remaining reported service fields use a different identity:

```text
omega_recourse = canonical first argmax_omega recourse_cost(omega)
total_shortage = sum_(r,j) u_rj(omega_recourse)
service_penalty_cost = sum_j phi_j e_j(omega_recourse).
```

Thus `total_shortage` is not the maximum-shortage statistic, and neither it nor
`service_penalty_cost` is generally evaluated at `omega_service`.

## SLA aggregation level

For each product and product-local shock pattern, the model uses

```text
sum_r u_rj - e_j <= (1 - SL_j) sum_r d_rj,
e_j >= 0,
penalty = phi_j e_j.
```

The SLA pools regions within a product. Reporting fill rates instead pool
products within a region. These are transposed aggregation levels and cannot be
compared directly. In addition, `e_j` makes the SLA soft: increasing `SL` raises
the penalized excess but does not impose `fill_rate >= SL` on any reported
region-level metric.

`service_violation_amount` is unavailable because `ScenarioServiceResult` and
the saved scenario JSON retain only the weighted sum `sum_j phi_j e_j`, not the
product-level `e_j` values. Since `phi_j` differs by product, the unweighted
violation amount cannot be recovered uniquely from the saved penalty cost. This
is a frozen reporting-contract limitation, not evidence that the slack is
absent and not an optimization error.

## Scenario-selection audit

- Every condition contains exactly 4,657 scenarios: `1 + 96 + choose(96,2)`.
- All 186,280 saved scenario rows have valid region/product identities and at
  most two shocks.
- For all 40 conditions, `omega_service` is scenario index 0, the no-shock
  nominal scenario. Nominal already contains a region with fill approximately
  zero, and the `1e-12` tie rule retains the first canonical identity.
- Therefore all reported `aggregate_fill_rate` values in this experiment come
  from the same type of scenario and are ex-post comparable across parameter
  levels. The implementation could select different scenarios in another data
  set, so this comparability must not be assumed without the identity audit.
- `omega_recourse` differs from `omega_service` in 40/40 conditions. Between
  `SL=0.90` and `SL=0.95`, the worst-recourse scenario changes in 1/8 cases.

## Why the fill rates are about 0.11--0.14

For the nominal scenario, the saved solutions have shortage ratios between
0.8381 and 0.8864, leaving demand-weighted network fill between approximately
0.1136 and 0.1619. The equality

```text
total nominal demand - nominal shortage = total first-stage inventory
```

holds to a maximum absolute residual of `3.6e-8` across all 40 conditions.
Inventory is therefore scarce relative to demand and is almost entirely used;
low fill is the direct numerical consequence. The equal-region macro-average
differs from the demand-weighted rate by about 0.0101 on average and at most
0.0246, but both remain low.

The following checks passed: reported aggregate and minimum values match the
selected scenario; reported shortage and penalty match the worst-recourse
scenario; scenario counts, shock budgets, region/product identities, and rate
ranges are valid. This excludes a reversed ratio, shortage/shipment confusion,
demand-axis mismatch, scenario-index mismatch, and invalid region/product
weighting. Equal region weighting is intentional in the frozen definition,
although it must be disclosed.

## Why `SL=0.95` has lower fill

The observed direction is not a scenario-selection artifact:

| Metric, mean over 8 cases | SL=0.85 | SL=0.90 | SL=0.95 |
|---|---:|---:|---:|
| Reported equal-region aggregate | 0.136513 | 0.135683 | 0.119706 |
| Derived nominal demand-weighted network fill | 0.141772 | 0.145309 | 0.134209 |
| Derived minimum scenario-average fill | 0.119672 | 0.122371 | 0.110125 |
| Reported worst-recourse total shortage | 3585.832 | 3565.940 | 3614.846 |

From `SL=0.90` to `0.95`, all eight cases decline under the reported nominal
macro-average, the nominal demand-weighted network rate, the minimum
scenario-average rate, and the uniform scenario diagnostic. Worst-recourse
shortage increases in all eight cases. Equal-region aggregation changes the
magnitude, not the sign.

This is classification **C: true service deterioration under multiple saved-data
metrics**, within a soft-SLA economic optimum. It is not A (scenario-selection
effect) or D (reporting bug); B (aggregation definition) affects magnitude only.
There is no monotonicity theorem here: `e_j` absorbs SLA excess, while the
robust economic objective, budget, reconfiguration spending, and inventory
placement change with `SL`. At `SL=0.95`, mean reconfiguration spending rises
from 119.41 to 507.49 and mean total inventory units fall from 583.10 to 538.25.
Those inventory-unit sums are diagnostic only because products are heterogeneous,
but every case shows the same fall in total units.

## Metric-use classification

| Metric | Classification | Use |
|---|---|---|
| Derived nominal demand-weighted network fill | `PRIMARY_INTERPRETATION_METRIC` | Same scenario and network-level physical ratio; derived without reoptimization. |
| `total_shortage` | `PRIMARY_INTERPRETATION_METRIC` with scenario disclosure | Physical quantity at the worst-recourse scenario; retain case-level scenario identity. |
| `service_penalty_cost` | `PRIMARY_INTERPRETATION_METRIC` for objective decomposition; `SECONDARY_DIAGNOSTIC_ONLY` as a physical-service claim | Comparable in SL sensitivity where phi is fixed; mechanically rescaled in phi sensitivity. |
| `aggregate_fill_rate` | `SECONDARY_DIAGNOSTIC_ONLY` | Ex-post comparable here because all selected scenarios are nominal, but it is an equal-region macro-average selected through a worst-minimum rule and is not the SLA. |
| `minimum_fill_rate` | `SECONDARY_DIAGNOSTIC_ONLY` | The same worst-case functional and uncertainty set make it technically comparable, but its numerical-zero floor provides almost no discrimination. |
| `service_violation_amount` | `SECONDARY_DIAGNOSTIC_ONLY`; currently unavailable | Cannot be reconstructed from saved aggregates; this is not a `REPORTING_BUG`. |

No audited metric is classified as `REPORTING_BUG`. The current
`aggregate_fill_rate` would be `NOT_COMPARABLE_ACROSS_PARAMETER_LEVELS` without
an identity check if parameter levels selected different scenarios; that did not
happen in these formal results.

## Publication recommendation and direct answers

The main text should retain objective, worst-recourse total shortage, and
service penalty cost as an explicitly labelled monetary objective component.
It should add the derived nominal demand-weighted network fill rate for a
fixed-scenario physical-service comparison. For phi sensitivity, do not treat
penalty cost as evidence of physical service improvement because the multiplier
itself changes.

The existing equal-region `aggregate_fill_rate`, near-zero
`minimum_fill_rate`, uniform-scenario averages, worst-scenario-average fill, and
the unavailable violation amount belong in the appendix or diagnostic material.

Direct answers:

- **A.** `aggregate_fill_rate` can be compared across the completed SL
  sensitivity only after noting that all 24 SL analysis rows select the nominal
  scenario. It is secondary and must not be interpreted as SLA attainment.
- **B.** `minimum_fill_rate` is technically comparable as a worst-case
  functional over the same uncertainty set, but is uninformative because it is
  numerically zero throughout; keep it diagnostic.
- **C.** Main text: objective, total shortage with worst-recourse identity,
  service penalty as an objective component, and derived fixed-nominal
  demand-weighted network fill.
- **D.** Appendix/diagnostic: current aggregate fill, minimum fill,
  scenario-uniform and worst-scenario-average fills, and unavailable violation
  amount.
- **E.** No formal optimization or new recourse evaluation is required. All
  added audit quantities are derived from existing scenario-level artifacts.
