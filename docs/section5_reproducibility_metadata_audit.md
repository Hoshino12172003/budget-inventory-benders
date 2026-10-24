# Section 5 reproducibility metadata audit

## Scope and evidence labels

This is a static audit of frozen configurations, runners, result provenance,
controlled-scaling artifacts, the official Renault archive, and the current
execution host. No optimization was invoked. The four labels below are used
literally throughout:

- `RECOVERED_FROM_FROZEN_ARTIFACT`: read from a frozen config, result,
  provenance record, or frozen source implementation.
- `SYSTEM_OBSERVED`: queried from the current execution host or interpreter.
- `DEFAULT_SOLVER_SETTING`: the formal execution path does not set the Gurobi
  parameter; the audit does not infer a custom value.
- `NOT_RECOVERABLE`: the requested value is absent from the frozen E1--E7
  artifact chain.

## Formal execution machine

| Item | Value | Evidence status | Qualification |
|---|---:|---|---|
| CPU exact model | Intel(R) Core(TM) Ultra 5 225H | `SYSTEM_OBSERVED` | Windows CIM on the current host |
| Physical cores | 14 | `SYSTEM_OBSERVED` | Windows CIM |
| Logical processors | 14 | `RECOVERED_FROM_FROZEN_ARTIFACT` | Every E1 result records 14; current CIM also returns 14 |
| Installed RAM | 32.0 GiB (34,359,738,368 bytes) | `SYSTEM_OBSERVED` | Sum of physical DIMM capacity |
| OS-usable physical RAM | 31.4974 GiB (33,820,106,752 bytes) | `SYSTEM_OBSERVED` | `Win32_ComputerSystem.TotalPhysicalMemory` |
| Frozen platform string | Windows-11-10.0.26200-SP0 | `RECOVERED_FROM_FROZEN_ARTIFACT` | E1 paper-final results |
| Frozen processor string | Intel64 Family 6 Model 197 Stepping 2, GenuineIntel | `RECOVERED_FROM_FROZEN_ARTIFACT` | E1 paper-final results |

The frozen E1--E7 result schema does not contain the CPU marketing name,
physical-core count, or installed RAM. Those three values are therefore
`NOT_RECOVERABLE` from E1--E7 alone and are supplied only as
`SYSTEM_OBSERVED`. The observed logical-processor count and CPU-family identity
agree with the frozen E1 hardware record. The 31.497-GiB usable-memory value is
also independently present in the frozen E1c resource artifact.

## Python and solver

| Item | Value | Evidence status |
|---|---|---|
| Python | 3.12.7 | `SYSTEM_OBSERVED` |
| Python executable | `C:\Users\Hu Jiaxin\Documents\Codex\2026-07-07\z\work\paper-code\.venv\Scripts\python.exe` | `SYSTEM_OBSERVED` |
| `gurobipy` | 13.0.2 | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| Native Gurobi | 13.0.2 | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| Imported package | `...\.venv\Lib\site-packages\gurobipy\__init__.py` | `SYSTEM_OBSERVED` |

The E1 paper-final result files explicitly store solver version `13.0.2`.
The frozen E1b readiness audit records both `gurobipy 13.0.2` and native
Gurobi `(13, 0, 2)` from the same interpreter. Python 3.12.7 is observed now
and is corroborated by frozen formal-acceptance provenance, although the
paper-final E1--E7 result schema itself omitted a Python-version field.

## E1--E7 Gurobi parameters

The shared profile is `gurobi-balanced-1e-8-v1`, defined in
`src/robust_inventory_reconfiguration/solver_profile.py:6-25`.

| Parameter | Mixed-integer master / Direct | Continuous recourse subproblem | Evidence status |
|---|---:|---:|---|
| `MIPGap` | 0.0 | not applicable | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| `FeasibilityTol` | 1e-8 | 1e-8 | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| `OptimalityTol` | 1e-8 | 1e-8 | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| `IntFeasTol` | 1e-8 | not applicable | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| `NumericFocus` | 0 | 0 | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| `OutputFlag` | 0 | 0 | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| `Threads` | DEFAULT (automatic) | DEFAULT (automatic) | `DEFAULT_SOLVER_SETTING` |
| `TimeLimit` | DEFAULT | DEFAULT | `DEFAULT_SOLVER_SETTING` |
| `MIPGapAbs` | DEFAULT | DEFAULT | `DEFAULT_SOLVER_SETTING` |
| `Seed` | DEFAULT | DEFAULT | `DEFAULT_SOLVER_SETTING` |
| `Presolve` | DEFAULT | DEFAULT | `DEFAULT_SOLVER_SETTING` |
| `Method` | DEFAULT | DEFAULT | `DEFAULT_SOLVER_SETTING` |
| `BarConvTol` | DEFAULT | DEFAULT | `DEFAULT_SOLVER_SETTING` |
| `Cuts` | DEFAULT | not applicable | `DEFAULT_SOLVER_SETTING` |
| `Heuristics` | DEFAULT | not applicable | `DEFAULT_SOLVER_SETTING` |

`BarConvTol=None` in the Python profile is not assigned to the model and is
therefore a default solver setting, not a custom null tolerance. Static search
of the frozen E1--E7 paths found no other numerical Gurobi parameter override.
E1 Direct assigns a per-run `LogFile`; that affects logging, not the numerical
contract. `solve_exact_benchmark` assigns `TimeLimit` only when a non-null
argument is passed (`exact_benchmark.py:40,54-55`), and the formal E1 runner
passes no time limit (`run_e1_empirical_local.py:152-155`).

Development-only accelerated PRB modules set `Threads=1`, `LPWarmStart`, and
occasionally `Method`/`Presolve`. They are not the frozen E1--E7 solver path and
are intentionally excluded from this table.

## PRB and aggregate-Benders termination contract

| Contract item | Frozen value | Evidence status |
|---|---:|---|
| Global relative gap | 1e-6 | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| Cut violation tolerance | 1e-7 | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| Maximum Benders iterations | 500 | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| Master feasibility tolerance | 1e-8 | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| Master optimality tolerance | 1e-8 | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| Master integrality tolerance | 1e-8 | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| Product subproblem feasibility tolerance | 1e-8 | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| Product subproblem optimality tolerance | 1e-8 | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| Exact absolute objective certification | 1e-4 | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| Global-coupling residual | 1e-6 | `RECOVERED_FROM_FROZEN_ARTIFACT` |
| Budget/reporting residual | 1e-6 | `RECOVERED_FROM_FROZEN_ARTIFACT` |

PRB defaults are declared at
`src/robust_inventory_reconfiguration/product_risk_budget_benders.py:63-73`.
It terminates the iteration loop only when
`relative_gap <= 1e-6` and no product-risk state is violated
(`product_risk_budget_benders.py:186-187`). It then recomputes every product's
states and the exact global risk-budget composition
(`product_risk_budget_benders.py:191-219`). The final objective check is

```text
abs(certified_objective - upper_bound) <= 1e-4
```

and the diagnostic global-coupling check is

```text
abs(theta_final - exact_composed_recourse) <= 1e-6
```

at `product_risk_budget_benders.py:219-221`.

The aggregate structured-oracle baseline uses the same `1e-6`, `1e-7`,
`1e-4`, and 500-iteration contract
(`standard_benders.py:152-164`). Its loop stops when the relative gap is within
tolerance and no new aggregate cut is added (`standard_benders.py:256-275`),
then performs a fixed-first-stage exact recertification
(`standard_benders.py:277-303`).

## Material reconfiguration and first-material Gamma

The formal RI measure is

```text
RI = sum_{i,j} |x[i,j] - x0[i,j]| / sum_{i,j} x0[i,j].
```

The frozen materiality threshold is exactly `1e-6`
(`e6_budget_risk_interaction_authorization.json:60` and
`e7_risk_friction_interaction_v1.json:31`). The executable classification is:

```text
material_reconfiguration = (RI > 1e-6)
```

See `experiments/run_e6_budget_risk_local.py:542-550` and
`experiments/run_e7_risk_friction_local.py:521-524`. Consequently,
`RI <= 1e-6` is classified as **not material**. For the Gamma sensitivity
summary, the first Gamma with `RI > tolerance` is selected; if none exists the
status is `NONE_THROUGH_G4`
(`scripts/summarize_e4_gamma_results.py:300-309`). All of these values are
`RECOVERED_FROM_FROZEN_ARTIFACT`.

## Controlled scaling

There is a naming distinction that matters for reproducibility:

- The final controlled simulation uses `L10` and `XL10`, frozen in
  `docs/large_scale_iteration_experiment_freeze.md` and backed by 10 prepared
  seeds each. These are the paper-final scales.
- The literal `L` and `XL_low` instances under
  `experiments/results/e1c_development_probe_v1` use seed `20260911` and are
  explicitly marked `development_only=true` and
  `paper_final_observation=false`. They must not be presented as paper-final
  observations.

### Paper-final dimensions

| Scale | I | R | J | Binary uncertainty components R×J | Gamma | Global extreme scenarios up to Gamma | Local modes per product | Product-risk blocks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| L10 | 25 | 24 | 12 | 288 | 2 | 41,617 | 301 | 3,612 |
| XL10 | 30 | 30 | 14 | 420 | 2 | 88,411 | 466 | 6,524 |

Both rows are `RECOVERED_FROM_FROZEN_ARTIFACT`. Each scale uses seeds
`20260921`--`20260930`. For global cardinality uncertainty, the reported
scenario count is

```text
sum_{k=0}^Gamma C(R*J, k).
```

The product-local mode count is `sum_{k=0}^Gamma C(R,k)` per product, and the
last column multiplies it by `J`. These are combinatorial counts implied by the
frozen binary cardinality set, not counts inferred from runtime output.

### Literal development artifacts requested in the audit

| Artifact | I | R | J | R×J | Gamma | Global extreme scenarios | Local modes/product | Blocks | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| L | 25 | 24 | 12 | 288 | 2 | 41,617 | 301 | 3,612 | development only |
| XL-low (`XL_low`) | 30 | 30 | 14 | 420 | 2 | 88,411 | 466 | 6,524 | development only |

These values come from the generated `PREPARE/instance.json` files and
`e1c_development_probe_authorization.json`; no proposal dimensions were used.

### Renault-derived expansion rule

The generator is `deterministic_empirical_bootstrap_v1`
(`src/robust_inventory_reconfiguration/e1c_scaling.py:142-280`). Given a fixed
seed, it:

1. cycles through and shuffles the frozen eight-product donor schema until `J`
   product donors are selected (`174-179`);
2. shuffles empirical case-region and case-depot pools from all eight Renault
   formal cases and selects `R` and `I` donors (`180-195`);
3. copies donor-region base demand, deviation, and shortage penalty, and copies
   frozen product volume/service attributes (`197-208`);
4. rescales depot capacity and fixed cost by generated-to-donor system
   demand/volume-demand ratios, rescales UB by product-demand ratios, and
   preserves empirical inventory cost (`219-242`); and
5. forms transport costs from empirical donor transport cost per unit product
   volume and the generated product volume (`243-252`).

No random economic parameter distribution is introduced. The randomness is
only the frozen, seeded empirical donor selection.

## Geographic data and publication CSV

The official archive is `renault_data_pipeline.zip`, frozen logical identity
`external://renault-raw/renault_data_pipeline.zip`, SHA-256
`38fa3aa486d1974e3d037d9e1cfc2af3340b0d8d132a96cc4e409ce575c1ea33`.
All geography below is `RECOVERED_FROM_FROZEN_ARTIFACT`.

- Customer coordinates:
  `renault_data_pipeline/data/renault_processed/<case>/customers.csv`;
  identifier `customer_code`; coordinate fields `latitude`, `longitude`.
- Depot coordinates:
  `renault_data_pipeline/data/renault_processed/<case>/depots.csv`;
  identifier `depot_code`; the same coordinate field names.
- Distances:
  `renault_data_pipeline/data/renault_processed/<case>/distances.csv`, with a
  corresponding raw `renault_raw/instances/instances/<case>/distances.csv`.

Because depot latitude/longitude are present, no coordinates were inferred
from the distance matrix.

The mapping builder reads those customer coordinate fields at
`scripts/freeze_e1_empirical_cases.py:149-160`, assigns every customer to the
nearest frozen medoid at lines `165-172`, and freezes the rule and coordinates
at lines `220-235`. Mapping SHA-256 is
`0bcdd7bb99926ed780c56764c531b76971dbb0bf24e77198766a754d9dde95ff`.

| Region | Medoid customer | Latitude | Longitude |
|---:|---:|---:|---:|
| 1 | 40771302 | 35.66 | -5.67 |
| 2 | 1925732 | 41.89 | -5.06 |
| 3 | 2571500 | 40.49 | -3.41 |
| 4 | 28237800 | 54.53 | -1.36 |
| 5 | 239414 | 48.37 | 0.56 |
| 6 | 2814600 | 41.57 | 1.67 |
| 7 | 7235904 | 48.82 | 4.98 |
| 8 | 3043109 | 50.10 | 11.38 |
| 9 | 26367200 | 47.86 | 17.78 |
| 10 | 11509705 | 49.83 | 18.97 |
| 11 | 23342502 | 44.97 | 24.93 |
| 12 | 27752300 | 41.62 | 25.38 |

`artifacts/paper_geographic_network_coordinates.csv` contains 5,045 data rows:
4,923 case-customer rows and 122 case-depot rows. It has no missing coordinate
row. Customer rows contain the frozen region assignment and medoid flag; depot
rows deliberately leave `region_id` blank because the geographic mapping
assigns customers, not depots. The CSV SHA-256 is
`520b3f0b6f9cebd880defa9b279e50a9b95e3de3fe682874ca41bbfc608ae36c`.

## Non-recoverable fields and integrity statement

From the frozen E1--E7 result artifacts alone, the exact CPU marketing name,
physical-core count, and installed RAM are `NOT_RECOVERABLE`; only the generic
processor string and 14 logical CPUs were persisted. The missing fields are
reported from current-system observation and are not presented as if they had
been stored in the result provenance.

No model, data, algorithm, frozen result, parameter, or tolerance was changed.
Optimization solves executed: **0**.
