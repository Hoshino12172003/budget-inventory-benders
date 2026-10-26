# E2 stockout supplement formal-admission review

## Review identity and decision

- Pull request: `#16`, still Draft
- Reviewed remote head: `b850c72bbfe8f5ec06352478f867a5e9b9109f99`
- Reviewed tree: `a7ea69bcdb56a2e37de76c55ec6b541280b517da`
- PR base: `ed2408269447bc20ea046d3e84a758805e2aab01`
- Review scope: policy identity, SCAL_BASE lineage, fixed-policy evaluator,
  scenario completeness, checkpoint/authorization chain, resource protocol, and
  current versus base regression evidence
- Full formal evaluation executed: **no**
- Formal authorization changed: **no**

**Admission decision: `BLOCKED`.**

The two-policy scientific comparison is identifiable, and the 21 supplement
tests pass. Formal admission nevertheless cannot be approved because the
complete-set summary API is not bound to the frozen 4,657-ID manifest, no
formal runner or formal checkpoint schema exists, and the frozen identity and
recovery chain is pilot-only. This finding supersedes the earlier admission
language in `docs/e2_stockout_independent_review.md`; it does not alter that
document or any historical record.

## 1. Policy identity and non-duplication

The following four independent checks agree in all eight cases:

1. `recover_policy_candidates` constructs Existing and redeclared Nominal from
   the same `artifacts/renault_empirical_8case_v1/x0/<case>.json` file.
2. It raises if their complete `{y,x,a_plus,a_minus}` coordinate hashes differ.
3. The identity manifest assigns them the same `same_configuration_group` and
   the same complete and component hashes.
4. The scenario manifest declares two independent configurations and labels
   Nominal as the same coordinates as Baseline, not a separate configuration.

Observed for 8/8 cases:

- Existing coordinate hash equals redeclared Nominal coordinate hash;
- `y`, `x`, `a_plus`, and `a_minus` component hashes each agree;
- both point to the same source file and instance hash;
- the original E2 Nominal coordinates remain unrecovered;
- all Nominal `formal_authorized` values remain `false`.

Therefore Nominal is scientifically a validation label for Baseline, not a
third policy. The protocol text is inconsistent with this decision in one
place: its future workload still says **24** case-policy tasks and 111,768 rows.
For two independent configurations the correct plan is **16** case-policy
tasks and 74,512 logical policy-scenario rows. Until corrected and enforced by
the runner, duplicate Nominal execution remains possible.

## 2. Existing versus SCAL_BASE Robust scientific comparison

### 2.1 Recoverable first-stage quantities and costs

All quantities below were read from the frozen coordinates or computed directly
from those coordinates and the frozen instance coefficients. No objective
difference was used. `FS` is fixed-depot plus inventory plus reconfiguration
cost; Existing has zero `a_plus/a_minus`, hence zero reconfiguration cost.

| Case | Active depots, both policies | Existing total `x` | Robust total `x` | L1 change in `x` | Existing / Robust fixed cost | Existing inventory cost | Robust inventory cost | Robust reconfiguration cost | Existing / Robust FS |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 210129 | 90016100, 9624708 | 678.881250 | 650.194144 | 58.149539 | 860.112 / 860.112 | 89,451.000 | 89,202.895 | 248.105 | 90,311.112 / 90,311.112 |
| 210202 | 90016100, 9624708 | 815.464286 | 760.100317 | 112.224260 | 1,120.956 / 1,120.956 | 105,390.000 | 104,911.176 | 478.824 | 106,510.956 / 106,510.956 |
| 210310 | 90018300, 90018400, 90019100, 91017500 | 557.006667 | 557.006667 | 1.94e-9 | 1,519.692 / 1,519.692 | 74,874.400 | 74,874.400 | 0 | 76,394.092 / 76,394.092 |
| 210323 | 90016100, 9624708 | 529.907143 | 519.600212 | 20.892427 | 1,581.060 / 1,581.060 | 66,695.143 | 66,606.002 | 89.141 | 68,276.203 / 68,276.203 |
| 210330 | 90016100, 9624708 | 500.400000 | 484.301716 | 32.631657 | 1,612.776 / 1,612.776 | 64,037.571 | 63,898.343 | 139.228 | 65,650.347 / 65,650.347 |
| 210428 | 90016100, 9624708 | 591.120000 | 591.120000 | 1.83e-9 | 1,222.776 / 1,222.776 | 74,689.200 | 74,689.200 | 8.17e-9 | 75,911.976 / 75,911.976 |
| 210611 | 90015700, 90016100, 90038200, 90038300, 9624708 | 496.462500 | 496.462500 | 5.42e-8 | 691.008 / 691.008 | 63,965.250 | 63,965.250 | 1.12e-7 | 64,656.258 / 64,656.258 |
| 210628 | 90016100, 9624708 | 606.046154 | 606.046154 | 1.83e-8 | 1,909.908 / 1,909.908 | 75,498.923 | 75,498.923 | 3.30e-8 | 77,408.831 / 77,408.831 |

Direct recomputation agrees with the SCAL_BASE result fields `fixed_cost`,
`inventory_cost`, `reconfiguration_spending`, and `budget_used` to floating
point precision. The first-stage artifact's `first_stage_expenditure` also
agrees. Existing artifacts do not store separate first-stage component fields;
those entries are directly recoverable from `y0/x0` and instance cost arrays,
but the absence of explicit stored component fields must remain visible.

Only products `BAC-O-4312` and `CON-S-0130` have positive first-stage inventory
in these policies. Material changes occur in four cases:

| Case | BAC-O-4312 Existing -> Robust | CON-S-0130 Existing -> Robust | Robust RI | Material flag |
|---|---:|---:|---:|---|
| 210129 | 191.700000 -> 148.281678 | 487.181250 -> 501.912466 | 0.085655 | true |
| 210202 | 250.842857 -> 167.048743 | 564.621429 -> 593.051575 | 0.137620 | true |
| 210323 | 180.900000 -> 165.300321 | 349.007143 -> 354.299891 | 0.039427 | true |
| 210330 | 160.264286 -> 135.899315 | 340.135714 -> 348.402401 | 0.065211 | true |

Cases 210310, 210428, 210611, and 210628 differ only at numerical-noise scale
(`RI <= 1.10e-10`) and are marked non-material by the source results.

### 2.2 Scientific interpretation

The warehouse activation vector is identical between Existing and SCAL_BASE in
8/8 cases. Fixed cost and total first-stage expenditure are consequently also
equal, within numerical tolerance. The scientifically supported comparison is:

> common-scenario recourse performance of the canonical inventory vector versus
> a later, certified Gamma=2 inventory reallocation under the same warehouse
> footprint and first-stage budget.

It is **not** evidence for a warehouse-opening effect. In four cases it is also
not a materially different inventory policy, so aggregate claims must report
that effective policy contrast is concentrated in 4/8 cases.

Both policies are evaluated by the same supplemental recourse code, frozen
instance, demand arrays, service levels, service penalties, shortage penalties,
transport costs, solver profile, tie-break, and scenario order. The SCAL_BASE
service-penalty vector hash is
`902aaa6e55a88266a1504e5a4d0bd3ca099b9fb56940de3601d6810672409aa5`,
which directly matches the service-penalty array in the frozen instances.

### 2.3 Missing evidence that is not inferred

- original E2 Nominal coordinates: **missing**;
- original E1/E2 Robust first-stage artifact: **missing**;
- original E2 raw result and provenance directories: **missing** and untracked;
- E2 solver status/exact certificate for canonical Existing: **missing**;
- explicit stored Existing fixed/inventory/first-stage component fields:
  **missing**, though directly computable from frozen variables and coefficients;
- formal common-scenario results for either configuration: **not created**.

## 3. SCAL_BASE source evidence

For all eight candidates:

- `first_stage_solution.json` validates its internal payload hash and coordinate
  identities;
- provenance-recorded first-stage and result SHA-256 values match the files;
- `result.json` and the first-stage artifact agree on instance/data hash,
  config hash, and source commit;
- source commit `a42093a16a82283ce15d3e9984a15418db04b066` exists in Git;
- solver status is `OPTIMAL`, certification is `CERTIFIED_PRB_EXACT`, and the
  frozen solver profile is `gurobi-balanced-1e-8-v1`;
- direct first-stage cost recomputation matches the result;
- E2-derived objective, RI, and RS agree within `1e-6`.

| Case | First-stage SHA prefix | Result SHA prefix | Provenance SHA prefix | E2 aggregate status |
|---|---|---|---|---|
| 210129 | `f5918ffca080` | `131632ec8695` | `e302e7356f84` | within 1e-6 |
| 210202 | `b2dc3b97a866` | `4f5d13174b9d` | `cbf689e601f5` | within 1e-6 |
| 210310 | `82834730a17d` | `1a563e44427e` | `0995f48f9d8b` | within 1e-6 |
| 210323 | `851b3d881d15` | `8baeada5a736` | `cec08bc05071` | within 1e-6 |
| 210330 | `2eb9e44f9d87` | `3865c2b08df7` | `02d17956fa7b` | within 1e-6 |
| 210428 | `5cf1b31281d1` | `f181b1cafca8` | `264b0c674694` | within 1e-6 |
| 210611 | `e16fdd8b1b13` | `d78aaf3026e7` | `da7325d6e993` | within 1e-6 |
| 210628 | `d120d26eda94` | `67b1cd6ae40e` | `e472372cbfde` | within 1e-6 |

This is sufficient lineage for a human to consider SCAL_BASE as a later
supplemental candidate. It is not evidence that historical E1/E2 coordinates
were recovered.

## 4. Common-scenario completeness review

### 4.1 Controls that pass

When the caller supplies `S0000` through `S4656`, the current complete-summary
validator rejects:

- any missing ID;
- duplicates, including duplicate-plus-missing with 4,657 rows;
- unknown IDs;
- non-`OPTIMAL` rows;
- missing required summary metrics;
- empty or duplicate partial diagnostics.

The Pilot uses the separate partial interface and its checkpoint contains
`PARTIAL_SCENARIO_DIAGNOSTIC`, `worst_over_observed_subset`, and no
`worst_over_frozen_set`.

The four maxima are separately computed for:

1. total shortage;
2. total service violation;
3. shortage-penalty cost;
4. economic-optimum recourse cost.

Tests use distinct maximizing scenarios for all four metrics, so maximum
shortage is not conflated with worst economic cost.

### 4.2 Blocking completeness defect

`summarize_complete_policy_metrics(rows, expected_scenario_ids)` trusts an
arbitrary caller-supplied expected set. It does not read or validate the frozen
scenario manifest, require 4,657 IDs, or compare the expected-set hash to the
case's `scenario_order_sha256`.

A read-only admission probe passed three valid rows with expected IDs
`S0000`, `S0001`, and `S0097`. The function returned:

```text
coverage_status = COMPLETE_FROZEN_SCENARIO_SET
scenario_count = 3
worst_over_frozen_set present = true
```

Thus the implementation does not yet guarantee that a formal-looking summary
covers the frozen uncertainty set. Existing tests only prove rejection after
they explicitly pass `frozen_scenario_ids(4657)`.

## 5. Regression comparison with PR base

The comparison was executed in an isolated worktree at the exact PR base. The
PR adds 19 files and modifies no base file.

| Tree | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| Base `ed240826...` | 377 | 33 | 11 | 0 |
| Reviewed HEAD tree | 398 | 33 | 11 | 0 |

The sorted 44-node non-passing set is identical in both trees. Its SHA-256 is
`b95ed833edab05e81f10b0af0c339b0615dc37df8bb35d7ac3e3264afcc8a684`.
There are no HEAD-only or base-only non-passing nodes. The 21 added supplement
tests account for the pass-count increase and all pass.

This proves that none of the 33 failures or 11 errors was introduced by PR #16.
It does not make them acceptable for formal execution.

### 5.1 Identity, authorization, or freeze drift: 12 failures + 11 errors

- E1 reuse identity: 1 failure;
- E1C scaling-design frozen SHA: 1 failure;
- historical E2 runner SHA: 1 failure;
- E3 formal-freeze behavior versus old test expectations: 2 failures;
- E4 formal-freeze behavior versus old test expectations: 3 failures;
- E6 manifest identity: 3 failures;
- E7 manifest identity: 1 failure and 11 fixture errors.

These have the same exception signatures on base and HEAD. The E2 failure is
directly relevant: the manifest's historical SHA matches the runner blob at
commit `4b154729...`, while the current runner contains the later protocol-freeze
guard. It must remain a recorded mismatch; the legacy authorization cannot be
reused for this supplement.

### 5.2 Missing archived/development inputs: 19 failures

The same missing paths occur on base and HEAD:

- E1C and PRB-J development tests: missing
  `e1c_development_probe_v1/L/PREPARE/instance.json` (7 failures);
- E3/E4/E5 reuse and reporting tests: missing E1, E2, E3, or E4 result/solution
  files (8 failures);
- E6 reuse tests: missing `E6-210202-B080-G2` sources (4 failures).

These are repository/archive-state failures, not operating-system solver
failures. The absent historical E2 Nominal result is also consistent with the
policy-identity audit.

### 5.3 Temporary-path fixture failure: 1 failure

`test_source_provenance_tampering_is_rejected` fails because a source path for
its temporary copy is absent. The same WinError 3 occurs at base and HEAD.

### 5.4 Nonportable tracked provenance: 1 failure

The portability test finds local absolute paths in three pre-existing tracked
artifacts. The same three-file violation occurs at base and HEAD.

### 5.5 Effect on E2 formal admission

The unrelated E1C/E3-E7 failures do not demonstrate a defect in the supplement
evaluator, but the repository does not have a green full-suite baseline. A
formal authorization must therefore either restore/fix the archived evidence
or explicitly freeze a reviewed, scoped E2 test gate. It must not describe the
whole repository suite as passing.

## 6. Formal authorization and recovery-chain review

| Admission item | Evidence | Status |
|---|---|---|
| Policy identity | Full coordinate hashes and source hashes frozen | Pass, human SCAL_BASE approval still required |
| Two-policy definition | Manifest says two; protocol workload still says 24 tasks | **Blocked** |
| Scenario identity | Per-case instance and scenario-order hashes frozen | Pass at manifest level |
| Complete result gate | Expected ID set is caller-controlled | **Blocked** |
| Formal runner | CLI has only `freeze`, `audit`, `pilot`, `resume-pilot`, `hashes` | **Missing / blocked** |
| Formal result schema | Only scenario-row schema and Pilot checkpoint schema exist | **Missing / blocked** |
| Runner/protocol/schema freeze | Scenario manifest does not hash the supplemental runner, protocol, schemas, or all code dependencies | **Blocked** |
| Checkpoint identity | Pilot validates sidecar, instance, policy, scenario-order, evaluator-code and config hashes | Pilot pass only |
| Checkpoint content | Resume does not schema-validate evaluation rows, expected scenario IDs, or summary coverage | **Blocked for formal use** |
| Solver status/cost identity | Evaluator fails non-optimal solves and directly reconciles cost components | Pass for evaluated rows |
| Resource settings | `Threads=1`, serial case-policy protocol, model disposal | Pass by design |
| Resource evidence | Pilot used 11 local blocks, not the full 632-block case-policy model | **Insufficient for formal admission** |
| Recovery | One completed Pilot checkpoint can resume; no formal case-policy orchestration exists | **Blocked** |
| Historical runner | Exact old blob recovered, current blob intentionally differs | Historical mismatch remains open |
| Authorization | Scenario and every policy flag remain `false` | Correctly locked |

The Pilot checkpoint schema explicitly requires
`classification=PILOT_NON_PUBLISHABLE`; it cannot serve as a formal-result
schema. Its config hash binds the scenario-manifest payload, but the formal
runner, protocol document, schema files, and dependency identity are not part
of that manifest. Delivery hashes are useful audit evidence but are not an
authorization manifest.

## 7. Minimum fixes before manual authorization can be considered

1. Bind the complete-summary API internally to the reviewed scenario manifest:
   require exactly 4,657 canonical IDs, validate the frozen order/set hash, and
   remove the ability to declare an arbitrary caller set complete.
2. Add a regression test proving that three IDs cannot be declared complete
   even when the caller supplies those same three IDs as its expectation.
3. Correct the protocol workload to 16 tasks and ensure the future runner
   selects Existing plus SCAL_BASE only; Nominal must remain metadata, not a
   scheduled policy.
4. Implement a separate, initially unauthorized formal runner and formal
   checkpoint/result schemas. Do not reuse or relabel the Pilot checkpoint.
5. Freeze runner, evaluator/dependency, protocol, schemas, solver profile,
   policy manifest, scenario manifest, and output-schema hashes in a new
   supplemental authorization record.
6. On resume, validate schema, every row's instance/policy/scenario identity,
   exact coverage, solver status, required metrics, component-cost identity,
   checkpoint digest, code/config identities, and task completion state.
7. Obtain resource evidence for one complete 632-block case-policy task under a
   separately authorized non-publishable preflight before approving all 16
   tasks. Record peak RSS, elapsed time, output size, and restart behavior.
8. Record human acceptance that SCAL_BASE is a later candidate, that only four
   cases contain material inventory changes, and that no warehouse-opening
   effect is being claimed.
9. Resolve the historical-runner test contract by pinning the old blob or
   restoring the historical archive; never overwrite the historical SHA.
10. Define an explicit scoped regression gate if unrelated archive failures are
    not restored, while retaining the full-suite failure report.

## 8. Formal-evaluation prerequisites

Manual authorization may be requested only after all of the following are true:

- the completeness and caller-controlled-ID defect is fixed and tested;
- the two-policy/16-task protocol is internally consistent;
- a formal runner, formal schemas, fail-closed authorization gate, and formal
  checkpoint recovery chain exist;
- all formal identities are frozen in a new supplemental authorization record;
- SCAL_BASE lineage and the limited scientific interpretation are approved;
- a full-case non-publishable resource/recovery preflight passes on the target
  32 GB machine;
- historical E2 evidence is kept separate from supplemental evidence;
- formal authorization remains `false` until a subsequent explicit human
  authorization change.

Until then, the only defensible decision is **`BLOCKED`**.
