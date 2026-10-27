# E2 stockout supplement independent review

## Scope

This review covers the fixed-policy evaluator, policy comparison definition,
eight SCAL_BASE Robust candidates, and historical E2 runner identity. It does
not authorize or execute the complete 8-case common-scenario evaluation.

## A. Complete-scenario statistical gate

**Pass.** Formal worst-value reporting now requires exact equality between the
observed scenario-ID set and the complete frozen ID set `S0000`--`S4656`.

The gate rejects:

- any missing ID;
- duplicate IDs, including the deceptive case where the row count remains
  4,657 because another ID is missing;
- any unknown ID;
- invalid or missing IDs;
- any count mismatch.
- any non-`OPTIMAL` row or missing required metric.

The check is set-based and does not rely on `len(rows) == 4657`. Pilot and
diagnostic subsets use a separate interface and are marked
`PARTIAL_SCENARIO_DIAGNOSTIC`. Their subset maxima are named
`worst_over_observed_subset`; they cannot emit `worst_over_frozen_set`.

The no-shock `S0000` summary remains independently available. Tests cover the
three-scenario pilot, one missing ID, duplicate-plus-missing IDs, an unknown ID,
an incomplete solver result, the exact 4,657-ID set, and four distinct
worst-value selectors.

## B. Independent configuration comparison

**Pass, pending policy approval.** The supplement now defines exactly two
independent first-stage configurations:

1. canonical Existing as **Baseline**;
2. certified later SCAL_BASE solution as **Robust candidate**.

Canonical Nominal and Baseline have identical coordinate hashes in all eight
cases. Nominal remains visible as a validation label but is not counted as a
third configuration. The original E2 Nominal coordinates remain unrecovered.
The identity manifest was not rewritten to imply recovery or difference.

## C. Robust source evidence

**Sufficient for an informed human approval of the later solutions as new
supplemental Robust candidates; insufficient to claim historical E1/E2 recovery.**

For all eight candidates:

- the first-stage file hash matches the hash recorded by `provenance.json`;
- the result file hash matches the hash recorded by `provenance.json`;
- the instance hash matches the frozen instance;
- solver status is `OPTIMAL`;
- certification is `CERTIFIED_PRB_EXACT`;
- E2-derived objective, RI, and RS agree within `1e-6`;
- the evaluator hashes the complete `y/x/a_plus/a_minus` payload before and
  after any recourse evaluation and rejects changes.

| Case | First-stage SHA prefix | Result SHA prefix | Provenance SHA prefix | Max aggregate delta | Status |
|---|---|---|---|---:|---|
| 210129 | `f5918ffca080` | `131632ec8695` | `e302e7356f84` | 0 | certified later candidate |
| 210202 | `b2dc3b97a866` | `4f5d13174b9d` | `cbf689e601f5` | 0 | certified later candidate |
| 210310 | `82834730a17d` | `1a563e44427e` | `0995f48f9d8b` | 3.49e-12 | certified later candidate |
| 210323 | `851b3d881d15` | `8baeada5a736` | `cec08bc05071` | 3.16e-11 | certified later candidate |
| 210330 | `2eb9e44f9d87` | `3865c2b08df7` | `02d17956fa7b` | 0 | certified later candidate |
| 210428 | `5cf1b31281d1` | `f181b1cafca8` | `264b0c674694` | 0 | certified later candidate |
| 210611 | `e16fdd8b1b13` | `d78aaf3026e7` | `da7325d6e993` | 1.61e-7 | certified later candidate |
| 210628 | `d120d26eda94` | `67b1cd6ae40e` | `e472372cbfde` | 1.21e-11 | certified later candidate |

Full hashes and individual objective/RI/RS deltas are in
`artifacts/e2_stockout_policy_identity_manifest.json`.

## D. Historical runner hash

**Cause established.** The authorized manifest hash exactly matches the runner
blob at historical commit `4b154729...`. The current committed runner differs
because commit `0631111...` added the protocol-freeze guard. The checked-out
file has a third byte hash because of checkout line endings.

The guard changes execution admissibility but not the economic model. The
current runner nevertheless cannot satisfy the historical runner identity. The
original E2 raw result/provenance directories are still absent, so complete
historical execution lineage is not recoverable from this checkout.

The existing historical test remains failing; no authorization record or formal
result was edited. Details are in `docs/e2_historical_runner_hash_audit.md` and
`experiments/audits/e2_historical_runner_hash_audit.json`.

## E. Remaining formal-run blockers

Formal evaluation remains locked because:

1. a human has not approved canonical Nominal as a Baseline validation label;
2. a human has not approved the SCAL_BASE lineage for the new Robust candidate;
3. every policy still has `formal_authorized=false`;
4. the common-scenario manifest still has `formal_run_authorized=false`;
5. the historical E2 raw execution package remains absent;
6. the known historical runner-identity regression remains open.

## Decision

**B. Continue only after human confirmation of the two-configuration definition
and Robust candidate lineage.** No full formal evaluation is authorized.

## F. Regression evidence

The supplement-only tests passed: **21 passed, 0 failed, 0 skipped**.

The related scenario, recourse, fixed-inventory service, first-stage artifact,
Renault eight-case, E2 summary, and E2 protocol selection produced **48 passed,
1 failed, 0 skipped**. The only failure was
`tests/test_e2_protocol.py::test_e2_identity_and_reuse_contract`, for the
historical runner-hash mismatch described in section D.

The complete repository suite produced **398 passed, 33 failed, 11 errors,
0 skipped**. The failures and errors are outside the supplement changes except
for the intentionally preserved E2 historical-hash finding. Each non-passing
test is accounted for below; no historical authorization or result was changed
to make it pass.

### Historical identity or frozen-protocol drift

- `tests/test_e1_formal.py::test_reuse_rows_load_historical_snake_case_fields`:
  E1 reuse identity closes instead of accepting the historical row.
- `tests/test_e1c_scaling_design.py::test_design_is_fail_closed_and_balanced`:
  the current design SHA differs from its frozen SHA.
- `tests/test_e2_protocol.py::test_e2_identity_and_reuse_contract`: the current
  runner SHA differs from the historical authorized SHA.
- `tests/test_e3_budget_protocol.py::test_unauthorized_execution_is_blocked`:
  the repository-wide formal freeze raises before the older expected
  authorization error.
- `tests/test_e3_budget_protocol.py::test_clean_worktree_gate_and_overwrite`:
  the repository-wide formal freeze blocks the older runner path.
- `tests/test_e4_gamma_protocol.py::test_case_validation_and_authorization_fail_closed`:
  the repository-wide formal freeze blocks the older runner path.
- `tests/test_e4_gamma_protocol.py::test_no_overwrite_behavior`: the
  repository-wide formal freeze blocks the older overwrite-path assertion.
- `tests/test_e4_gamma_protocol.py::test_static_audit_passes_without_outputs_or_solves`:
  the repository-wide formal freeze blocks the older static-audit path.
- `tests/test_e6_budget_risk_protocol.py::test_manifest_freezes_identity_and_authorizes_only_e6`:
  the E6 manifest rejects current model, PRB, runner, reporter, plotter, schema,
  protocol, and audit hashes.
- `tests/test_e6_budget_risk_protocol.py::test_dry_run_never_invokes_optimizer`:
  the same E6 identity gate rejects the dry run.
- `tests/test_e6_final_reporting.py::test_summary_generation_never_calls_optimizer_or_overwrites_primary`:
  the same E6 identity gate rejects reporting.
- `tests/test_e7_risk_friction_protocol.py::test_dry_run_has_zero_optimizer_calls`:
  the E7 manifest rejects current model, PRB, evaluator, protocol, schema,
  runner, audit, reporter, and plotter hashes.

All eleven setup errors in `tests/test_e7_risk_friction_protocol.py` have that
same E7 manifest-identity cause:

- `test_manifest_freezes_beta_and_authorizes_only_e7`;
- `test_authorization_record_matches_all_frozen_identities`;
- `test_reuse_is_derived_as_40_and_new_as_32`;
- `test_e4_e5_overlap_is_corroborated_and_counted_once`;
- `test_reuse_identity_mismatch_fails_closed`;
- `test_authorization_identity_mismatch_fails_closed`;
- `test_resume_states_distinguish_absent_completed_and_partial`;
- `test_timing_schema_and_containment`;
- `test_reused_result_satisfies_frozen_schema`;
- `test_reporting_complexity_and_no_unproven_acceleration`;
- `test_authorized_reporting_paths_now_contain_final_outputs`.

### Missing archived or development result artifacts

- The following four tests require the absent
  `experiments/results/e1c_development_probe_v1/L/PREPARE/instance.json`:
  `tests/test_e1c_gamma_sensitivity_development.py::test_dry_run_freezes_grid_identity_and_resources`,
  `::test_config_is_development_only_and_reuses_prepared_l`,
  `::test_preflight_fails_closed_below_frozen_threshold`, and
  `::test_gamma2_sanity_checks_all_three_frozen_methods`.
- `tests/test_e3_budget_protocol.py::test_B100_reuse_accepts_exact_identity_and_rejects_mismatch`
  requires absent `E1-210202-PRB/result.json`.
- `tests/test_e4_210628_g4_reporting_audit.py::test_210628_g4_result_serializes_diagnostic_without_schema_regression`
  requires absent `E4-210628-G4/result.json`.
- `tests/test_e4_gamma_protocol.py::test_G2_reuse_identity_is_complete_for_all_cases`
  requires absent `E3-210202-B100/result.json`.
- `tests/test_e4_gamma_protocol.py::test_G0_reuse_is_not_identity_safe`
  requires absent original `E2-210202-NOMINAL/result.json`.
- `tests/test_e4_gamma_protocol.py::test_Gamma2_reuse_reporting_schema_is_unchanged`
  requires absent `E3-210202-B100/result.json`.
- `tests/test_e5_reconfiguration_friction_protocol.py::test_l0500_reuse_identity_is_complete_for_all_cases`
  requires absent `E4-210202-G2/result.json`.
- `tests/test_e5_reconfiguration_friction_protocol.py::test_l0500_reuse_uses_e5_reporting_schema_without_solving`
  requires absent `E4-210202-G2/result.json`.
- `tests/test_e5_reconfiguration_friction_protocol.py::test_positive_friction_canonical_matches_frozen_baselines`
  requires absent `E4-210202-G2/first_stage_solution.json`.
- The following three tests require the absent
  `experiments/results/e1c_development_probe_v1/L/PREPARE/instance.json`:
  `tests/test_prb_j_scaling_development.py::test_static_audit_freezes_full_j_grid_before_results`,
  `::test_dry_run_has_twelve_methods_and_three_preparations`, and
  `::test_resource_preflight_fails_closed`.

### Missing E6 reuse inputs or test fixture path

- `tests/test_e6_budget_risk_protocol.py::test_reuse_plan_is_derived_and_overlap_counted_once`,
  `::test_reuse_sources_are_exactly_e3_and_e4`,
  `::test_dry_run_never_invokes_optimizer`,
  `::test_reused_result_conforms_to_frozen_schema[condition0-E3-210202-B080]`,
  and `::test_reused_result_conforms_to_frozen_schema[condition1-E4-210202-G0]`
  encounter the missing `E6-210202-B080-G2` reuse source (the dry-run test is
  already listed above because its first observed failure is the identity gate).
- `tests/test_e6_budget_risk_protocol.py::test_source_provenance_tampering_is_rejected`
  encounters a missing temporary-copy source path before its tamper assertion.

### Nonportable committed provenance

- `tests/test_provenance_portability.py::test_committed_provenance_and_manifests_have_no_local_absolute_paths`
  reports local absolute paths in three pre-existing tracked artifacts:
  `artifacts/algorithm_scaling_static_audit.json`,
  `artifacts/section5_reproducibility_metadata.json`, and
  `artifacts/service_calibration_diagnostics/SCAL_PHI250_210628/fixed_recourse_diagnostic.json`.
