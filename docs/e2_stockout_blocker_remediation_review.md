# E2 Stockout Supplement Blocker Remediation Review

> Historical admission snapshot: this report records the state before the
> authorized full-case resource preflight. The current admission decision is in
> `docs/e2_stockout_resource_preflight_report.md`.

## Scope and decision

This review applies only to the E2 stockout supplement in Draft PR #16. It does
not authorize or execute the 8-case by 2-policy by 4,657-scenario formal
evaluation. Historical authorization records, historical formal results, the
economic model, uncertainty set, service definition, cost parameters, and
paper parameters were not changed.

**Decision: `BLOCKED`.** The software blockers identified by the preceding
independent admission review have been repaired and tested. Formal evaluation
is still blocked because the required full 632-block case-policy resource and
recovery preflight has not been separately authorized or run, the SCAL_BASE
scientific interpretation has not received recorded human approval, and the
repository-wide regression baseline is not green.

## Blocker remediation evidence

| Prior blocker | Remediation | Verification | Status |
|---|---|---|---|
| Caller-controlled complete scenario set | The complete-summary API now derives exactly `S0000` through `S4656` from the hashed common-scenario manifest and verifies the frozen ID-order hash and exact set equality. Partial summaries use a separate status and never emit `worst_over_frozen_set`. | Tests reject 3 rows, one missing ID, duplicate plus missing ID, unknown replacement at unchanged row count, non-OPTIMAL status, missing metrics, and tampered ID-order identity; all 4,657 exact IDs pass. | Repaired |
| Missing formal runner | Added separate `formal-run` and `resume-formal` commands. The authorization gate executes before output creation or evaluator invocation. | Unit test replaces the evaluator with an exception and confirms an unauthorized run stops first; a direct CLI invocation returns `PermissionError` and creates no formal-result root. | Repaired, locked |
| Missing formal identity chain | Added a supplemental authorization manifest binding policy/scenario payloads and the runner, evaluator dependencies, protocol, schemas, and resource audit. Per-task checkpoints bind authorization, instance, policy, scenario order, solver profile/version, threads, and code/config identities. | Hash mismatch, corrupt sidecar, task mismatch, incomplete coverage, row identity, solver status, metric completeness, component reconciliation, and first-stage before/after hashes fail closed. | Repaired |
| Pilot/formal checkpoint ambiguity | Added a separate formal schema and `FORMAL_COMMON_SCENARIO_RESULT` classification. Pilot remains `PILOT_NON_PUBLISHABLE`. | Formal validator rejects other classifications; schema contract test verifies every required field is defined. | Repaired |
| 24-task protocol conflict | Formal plan contains Existing and later SCAL_BASE only: 8 cases by 2 independent configurations = 16 tasks. Canonical Nominal remains a validation label equal to Existing and is never scheduled. | Authorization-plan test requires 16 unique task IDs and rejects any Nominal task. | Repaired |
| Historical runner hash test | The test now hashes the runner blob pinned at historical commit `4b154729...` and verifies it against the unchanged historical authorization SHA. It separately asserts that the current runner does not match that SHA. | `tests/test_e2_protocol.py::test_e2_identity_and_reuse_contract` passes; no historical manifest or result was edited. | Repaired as a test contract; raw historical result lineage remains unavailable |
| Resource evidence | Added a non-authorizing structural audit: 632 product-local blocks per task, 16 serial tasks, 74,512 logical rows, `Threads=1`, and a maximum estimated 152,312 variables / 20,224 constraints. | Audit status is deliberately `FULL_CASE_RESOURCE_PREFLIGHT_STILL_REQUIRED`; the formal gate requires `PASS_FULL_CASE_PREFLIGHT_ON_32GB_TARGET`. | Still blocking |

## Policy comparison retained

The supplement compares two independent first-stage configurations only:

1. `EXISTING_CANONICAL_<case>` is the normalized Baseline. Its coordinates are
   identical to the canonical Nominal coordinates in all eight cases. Nominal
   is not counted again, and the original E2 Nominal coordinates remain
   unrecovered.
2. `ROBUST_EQUIVALENT_SCAL_BASE_<case>` is a later, exactly certified
   SCAL_BASE candidate. Its source lineage remains
   `SERVICE_CALIBRATION_ROBUSTNESS_V2`; it is not relabeled as an original E1
   or E2 coordinate recovery.

The identity manifest retains source file hashes, instance hashes, complete
`x/y/a+/a-` coordinate hashes, solver status, certification state, warehouse
openings, inventory totals, and first-stage cost components. Missing historical
coordinates remain marked missing. Both configurations are evaluated with the
same frozen scenario manifest and unchanged recourse objective. No warehouse
opening benefit may be claimed where the recorded `y` coordinates are equal;
the scientific claim is limited to the recorded inventory reallocation.

## Test evidence and PR-base comparison

All commands used `PYTHONPATH=src`. A repository-local `--basetemp` was used
because the machine's default pytest temporary root returned Windows access
denied during setup.

| Run | Result |
|---|---|
| Supplement plus scenario, recourse, first-stage, Renault identity, E2 protocol and summary tests | **64 passed** |
| Current full suite | **407 passed, 32 failed, 11 errors** |
| Exact PR base `ed2408269447bc20ea046d3e84a758805e2aab01` in an isolated worktree | **377 passed, 33 failed, 11 errors** |

The current and base `lastfailed` node sets were compared by exact node ID.
Base has 44 nodes and current has 43. The only base-only node is
`tests/test_e2_protocol.py::test_e2_identity_and_reuse_contract`; there are no
current-only failed/error nodes. Thus this patch removes the historical E2 test
failure and introduces no new failing/error node relative to the exact PR base.
This is node-level evidence, not an inference from unchanged counts.

### Remaining identity/freeze failures: 11 failures and 11 errors

These exact nodes are also present at the PR base. Their reproduced messages
are frozen identity mismatches or later protocol-freeze guards, not E2
supplement evaluator failures:

- `tests/test_e1_formal.py::test_reuse_rows_load_historical_snake_case_fields`
- `tests/test_e1c_scaling_design.py::test_design_is_fail_closed_and_balanced`
- `tests/test_e3_budget_protocol.py::test_unauthorized_execution_is_blocked`
- `tests/test_e3_budget_protocol.py::test_clean_worktree_gate_and_overwrite`
- `tests/test_e4_gamma_protocol.py::test_case_validation_and_authorization_fail_closed`
- `tests/test_e4_gamma_protocol.py::test_no_overwrite_behavior`
- `tests/test_e4_gamma_protocol.py::test_static_audit_passes_without_outputs_or_solves`
- `tests/test_e6_budget_risk_protocol.py::test_manifest_freezes_identity_and_authorizes_only_e6`
- `tests/test_e6_budget_risk_protocol.py::test_dry_run_never_invokes_optimizer`
- `tests/test_e6_final_reporting.py::test_summary_generation_never_calls_optimizer_or_overwrites_primary`
- `tests/test_e7_risk_friction_protocol.py::test_dry_run_has_zero_optimizer_calls`
- all 11 setup errors in `tests/test_e7_risk_friction_protocol.py`: `test_manifest_freezes_beta_and_authorizes_only_e7`, `test_authorization_record_matches_all_frozen_identities`, `test_reuse_is_derived_as_40_and_new_as_32`, `test_e4_e5_overlap_is_corroborated_and_counted_once`, `test_reuse_identity_mismatch_fails_closed`, `test_authorization_identity_mismatch_fails_closed`, `test_resume_states_distinguish_absent_completed_and_partial`, `test_timing_schema_and_containment`, `test_reused_result_satisfies_frozen_schema`, `test_reporting_complexity_and_no_unproven_acceleration`, and `test_authorized_reporting_paths_now_contain_final_outputs`.

The E1 assertion reproduces `BLOCK_E1_REUSE_IDENTITY`; E1C reproduces a
generator SHA mismatch; E3/E4 reproduce `FORMAL_PROTOCOL_FROZEN`; E6 reproduces
`BLOCK_E6_MANIFEST_IDENTITY`; and every E7 setup error reproduces
`BLOCK_E7_MANIFEST_IDENTITY` for the same nine identities on base and current.

### Missing archived/development inputs: 19 failures

The following exact nodes are present on base and current and reproduce missing
tracked/archive paths rather than optimizer failures:

- four `tests/test_e1c_gamma_sensitivity_development.py` nodes:
  `test_dry_run_freezes_grid_identity_and_resources`,
  `test_config_is_development_only_and_reuses_prepared_l`,
  `test_preflight_fails_closed_below_frozen_threshold`, and
  `test_gamma2_sanity_checks_all_three_frozen_methods`;
- `tests/test_e3_budget_protocol.py::test_B100_reuse_accepts_exact_identity_and_rejects_mismatch`;
- `tests/test_e4_210628_g4_reporting_audit.py::test_210628_g4_result_serializes_diagnostic_without_schema_regression`;
- three `tests/test_e4_gamma_protocol.py` nodes: `test_G2_reuse_identity_is_complete_for_all_cases`, `test_G0_reuse_is_not_identity_safe`, and `test_Gamma2_reuse_reporting_schema_is_unchanged`;
- all three `tests/test_e5_reconfiguration_friction_protocol.py` failures;
- four E6 reuse failures: `test_reuse_plan_is_derived_and_overlap_counted_once`, `test_reuse_sources_are_exactly_e3_and_e4`, and the two parameterizations of `test_reused_result_conforms_to_frozen_schema`;
- all three failures in `tests/test_prb_j_scaling_development.py`.

The common missing sources are
`e1c_development_probe_v1/L/PREPARE/instance.json`, historical E1/E3/E4
result or first-stage files, and `E6-210202-B080-G2` reuse sources.

### Other base-matched failures: 2 failures

- `tests/test_e6_budget_risk_protocol.py::test_source_provenance_tampering_is_rejected`
  fails while copying an absent fixture source (`WinError 3`).
- `tests/test_provenance_portability.py::test_committed_provenance_and_manifests_have_no_local_absolute_paths`
  reports the same three pre-existing tracked artifacts at base and current.

No remaining full-suite failed/error node is introduced by this remediation.
The suite is nevertheless not described as passing.

## Static and resource audit

`py_compile` and `git diff --check` pass. The static source audit confirms no
first-stage solver call path in the evaluator. The unauthorized formal CLI
gate was exercised before any formal output directory existed and left that
directory absent. The three-scenario Pilot remains non-publishable and is used
only for functional/runtime smoke evidence.

The structural resource audit is not sufficient evidence for 32 GB admission.
It does not solve a complete 632-block task, measure full-task peak RSS or
output size, or demonstrate interrupted full-task recovery. Those facts are
not inferred from the three-scenario Pilot.

## Remaining prerequisites and minimum next action

Before manual formal authorization can be approved:

1. Separately authorize one non-publishable full 632-block case-policy resource
   and recovery preflight on the target 32 GB machine. Record elapsed time,
   peak RSS, output size, digest/identity checks, and successful resume.
2. Independently review and record acceptance of SCAL_BASE as a later certified
   Robust candidate and the limited inventory-reallocation interpretation.
3. Record a reviewed scoped E2 regression gate or restore the missing/frozen
   evidence needed to make the relevant repository regressions green.
4. Only in a later explicit authorization change, update all supplemental
   manifest/policy approvals and the authorization transition. Do not reuse or
   overwrite historical E2 authorization.

Until those steps pass, all formal authorization flags remain `false`, the PR
remains Draft, and the correct admission conclusion is **`BLOCKED`**.
