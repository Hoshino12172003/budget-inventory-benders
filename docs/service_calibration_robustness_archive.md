# Service calibration robustness formal archive

## Archived experiment

- Experiment: `SERVICE_CALIBRATION_ROBUSTNESS_V2`
- Code commit used by every formal solve: `a42093a16a82283ce15d3e9984a15418db04b066`
- Cases: the frozen eight Renault cases
- Design: OFAT service-level and service-penalty calibration robustness
- Formal physical solves: 40
- Post-run audit: `POST_RUN_AUDIT_PASS`
- Exact certification: 40/40 `CERTIFIED_PRB_EXACT`
- Reused results: 0

The formal output directory is
`experiments/results/service_calibration_robustness_v2_fixed_recourse`.

## Result layout

The repository keeps the following files directly reviewable:

- aggregate and case-level CSV tables;
- the execution manifest and its result hashes;
- the Markdown experiment summary;
- every condition's `result.json`, `provenance.json`, and
  `first_stage_solution.json`;
- the post-run/static audit, baseline-reuse audit, fixed-recourse IIS diagnostic,
  and service-metric semantics audit.

The 40 `service_scenarios.json` files contain 186,280 scenario rows and are
stored without loss in:

`service_calibration_physical_results_archive.zip`

Archive SHA256:

`16f6b2497b7644ef5310fa41201fbe0a81e4c754c485427d39a1fb5b43e57ff2`

The zip preserves the `physical_results/<condition_id>/...` directory layout.
The execution manifest records the SHA256 of every original scenario file, so
an extracted archive can be checked against the formal provenance.

## Main numerical conclusions

### Service-level sensitivity

| SL | Mean normalized objective | Material cases | Mean shortage | Mean reported aggregate fill |
|---:|---:|---:|---:|---:|
| 0.85 | 0.966486 | 8/8 | 3585.832 | 0.136513 |
| 0.90 | 1.000000 | 4/8 | 3565.940 | 0.135683 |
| 0.95 | 1.035015 | 8/8 | 3614.846 | 0.119706 |

Increasing `SL` to 0.95 raises the mean normalized objective by about 3.5%
relative to the current-version baseline and produces material reconfiguration
in every case. The lower reported fill is not a scenario-selection artifact:
all 40 conditions select the nominal scenario for the worst-service reporting
identity, and the independently derived nominal demand-weighted network fill
also declines in all eight cases from `SL=0.90` to `SL=0.95`.

### Service-penalty sensitivity

| phi multiplier | Mean normalized objective | Material cases | Mean shortage | Mean service penalty cost |
|---:|---:|---:|---:|---:|
| 1.50 | 0.895205 | 7/8 | 3579.325 | 336885.712 |
| 1.85 | 1.000000 | 4/8 | 3565.940 | 415638.815 |
| 2.50 | 1.194564 | 4/8 | 3578.801 | 561192.954 |

The penalty-cost increase is partly mechanical because the multiplier itself
changes. Physical shortage and fixed-scenario fill must accompany it in any
service interpretation.

## Fixed-recourse diagnostic retained

The original `SCAL_PHI250_210628` post-evaluation failure was diagnosed as a
solver-scale fixed-inventory mapping issue:

- primary PRB status: `OPTIMAL`, exact certification passed;
- minimum raw inventory: `-1.4279483781087839e-08` at depot `90016100`, product
  `BAC-O-4325`;
- raw evaluator: Gurobi status 3;
- IIS: nonnegative shipment lower bounds conflicted with a negative fixed-supply
  RHS;
- canonicalized evaluator: `OPTIMAL`, 4,657 scenarios;
- classification: `FIXED_INVENTORY_MAPPING_BUG` and
  `PRIMARY_OPTIMIZATION_SUCCESS_POST_EVALUATION_FAILURE`.

The `.ilp`, structured IIS JSON, fixed inventory, and primary diagnostic are
archived under
`artifacts/service_calibration_diagnostics/SCAL_PHI250_210628`.

## Interpretation contract

See `docs/service_metric_semantics_audit.md` for exact definitions. In short:

- `aggregate_fill_rate` is an equal-region average inside the selected
  worst-service scenario, not a demand-weighted network ratio;
- `minimum_fill_rate` is the minimum region-level fill across scenarios and
  regions;
- the soft SLA pools regions within each product, so it is not at the same
  aggregation level as either reported fill metric;
- `total_shortage` and `service_penalty_cost` are evaluated at the
  worst-recourse scenario;
- `service_violation_amount` cannot be reconstructed because product-level
  slack values were not serialized.

No additional optimization was run for the semantics audit.
