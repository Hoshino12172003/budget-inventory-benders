# Formal parameter freeze

## Status and evidence boundary

`FORMAL_PARAMETER_FREEZE_PASS`. This freeze uses only artifacts already committed
to `origin/main`; it does not rerun calibration or optimization. Formal execution
remains unauthorized.

Evidence:

- `artifacts/nominal_baseline_summary.json`, SHA-256
  `e8e5c17d64d6cff6aeb5322b9b4e9d38c60ff661cb6bf13ee95136eb2abde623`;
- `artifacts/nominal_baseline_provenance.json`, SHA-256
  `490f42f8ac119beea3e1da26e2b3b0df71261cdf1473dfc3435b9f200de24344`;
- `artifacts/lambda_calibration_summary.json`, SHA-256
  `7e727f89379da5fdffc63a7ac9fce711cac9814a948b8f5e1921c91d16920e94`;
- `artifacts/lambda_calibration_runs.csv`, SHA-256
  `f5d414bb1c7e30a1d9541849794fc750673dce0e75db1d55403cd308b693f3d7`.
- `artifacts/lambda_response_by_case.csv`, SHA-256
  `edd0f8e61c9ff35bc0822c1bf2ecc57292b01d611fca2eed92e75e531691447b`;
- `artifacts/nominal_baseline_degeneracy_audit.csv`, SHA-256
  `c00aac8eb0934d67fc0f79a3a21762b63ba099ba1615e1ac14fd6cce6070abcf`;
- `artifacts/reconfiguration_correctness_audit.json`, SHA-256
  `ffda5546453641acdd05a910bfb170288ac0575206b923b4f43753013e5d9034`;
- `artifacts/prb_benders_correctness_summary.json`, SHA-256
  `f52794afce046bf069885c4a5f8b11484b90b0d9b47fde71eee8122c4f907dc6`;
- `artifacts/prb_correctness_contract_summary.json`, SHA-256
  `3f2c9cff6c26fea8e239d31b0f574c2f32e5f24cf0cbf6ea480cdad675faf84b`.

The formal cases are `210202` and `210628`. Case `210712` exists in the raw
archive but is outside the current formal processing and calibration chain.

## Parameter classes

- Observed parameters: Renault demand, deviations, costs, capacities, inventory
  bounds, service data, and source identity metadata in the formal instances.
- Derived parameters: the nominal-incumbent `x0`, `B_ref`, and each
  `B=beta*B_ref_case`.
- Calibrated parameter: `lambda_R`, interpreted as economic/policy friction and
  not as an observed Renault quantity.
- Policy parameters: `beta` and `Gamma`, which define financial and uncertainty
  stress.
- Formal baselines: `beta^0=1.0`, `Gamma^0=2`, and `lambda_R^0=0.05`.

## Budget baseline

The noncircular reference is the first-stage expenditure of the frozen nominal
incumbent. The verified values are:

| Case | `B_ref` | `B^0` at `beta^0=1` |
| --- | ---: | ---: |
| 210202 | 84614.30513135393 | 84614.30513135393 |
| 210628 | 50558.18771213083 | 50558.18771213083 |

Both incumbents are feasible, use 13 of 15 existing depots, stock all eight
products, and are structurally stable. In the development primary environment
(`Gamma=2`, `beta=1`), both cases use essentially 100% of the budget and retain
nonzero reconfiguration; absolute budget residuals are below `2e-11`. The robust
solutions operate 13 and 10 depots, respectively, so neither is all-open or
all-closed. Thus the reference is active and nondegenerate.

E3 freezes `beta={0.8,0.9,1.0,1.1,1.2}`. Values are converted to case-specific
budgets only through `B=beta*B_ref_case`. Static feasibility at the lowest level
is certified by the all-inactive, zero-final-inventory construction: its complete
baseline-removal costs at `lambda_R=0.05` are 4005.5321947514526 and
2387.7573168101367, below the respective `beta=0.8` budgets
67691.44410508315 and 40446.550169704664. Complete shortage recourse preserves
second-stage feasibility. This is a static precondition check, not an experiment.

## Risk baseline

Each Renault case has `12*8=96` uncertain region-product demand items. The exact
product-risk composition supports every integer `Gamma` from zero through four;
the development and correctness artifacts include positive-risk evidence, with
`Gamma=2` as the primary calibration environment. `Gamma^0=2` is neither the
nominal edge (`0`) nor an extreme fraction of 96 items. E4 therefore freezes
`Gamma={0,1,2,3,4}`, with `0` as the nominal counterfactual.

## Friction baseline

The development artifact predeclared a normalized-RI selection rule and selected
`0.0025`, `0.05`, and `0.20` as low, medium, and high anchors. It records
`response_nondegenerate_in_both_cases=true` and
`ready_to_freeze_formal_levels=true`.

At `beta=1`, `Gamma=2`, `lambda_R=0.05`, RI is 0.020913487972572833 for 210202
and 0.09865262354354414 for 210628. Reconfiguration costs are 36.82276045566586
and 179.04193551218617, respectively. Both are positive, both are below their
zero-friction RI values, and neither system is frozen. The budget remains active.
Because each movement coefficient is `0.05*h_ij`, friction is expressed directly
on the inventory-cost scale while remaining a modest budget share (RS
0.0004351836299843481 and 0.0035413044575810064). This supports
`lambda_R^0=0.05` as an interpretable center rather than an observed parameter.

E5 freezes `lambda_R={0,0.0025,0.01,0.05,0.20}`. Zero is the frictionless
counterfactual, not the baseline. Values 0.0025, 0.05, and 0.20 retain the
calibrated anchors; 0.01 is a tested development-grid interpolation between the
low and baseline anchors. At the primary environment its RI values are
0.024335930540857285 and 0.20132748997800295, retaining nonzero movement in both
cases. No value was selected from formal outcomes.

## Interaction grids

- E6: `beta={0.8,1.0,1.2}` by `Gamma={0,2,4}`, with `lambda_R=0.05`.
- E7: `Gamma={0,2,4}` by `lambda_R={0.0025,0.05,0.20}`, with `beta=1.0`.

The machine-readable authority is
`experiments/configs/formal/formal_parameter_freeze.json`, SHA-256
`37b5f962c061d29b6b72417007424907b9b1f756a4ad1943a3719048d46b93c0`.
