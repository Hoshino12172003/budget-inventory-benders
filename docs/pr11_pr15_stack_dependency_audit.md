# PR #11–#15 stacked dependency audit

Audit date: 2026-10-22

Repository: `Hoshino12172003/budget-inventory-benders`

Scope: read-only code/result inspection, non-optimization tests, and the authorized PR #15 base change.
Optimization calls: **0**.

## Stack identity

The verified dependency chain is:

`main` → PR #11 → PR #12 → PR #13 → PR #14 → PR #15.

PR #15 now targets `codex/direct-scaling-experiment-preparation` and remains a Draft PR. Relative to that remote base it contains exactly **106 commits** and **1,854 changed files**. The file distribution is:

| Area | Files |
|---|---:|
| `experiments/` | 1,702 |
| `artifacts/` | 53 |
| `scripts/` | 36 |
| `tests/` | 28 |
| `docs/` | 27 |
| `src/` | 6 |
| `.gitattributes` / `.gitignore` | 2 |

All 1,650 result-tree changes in the PR #15 comparison are additions. No result file is deleted or modified relative to the PR #14 remote head. GitHub reports all five PRs as `MERGEABLE/CLEAN`, but no PR currently has GitHub status checks configured.

## Audit criteria

`READY_FOR_REVIEW` in this report requires all of the following:

1. GitHub reports a clean merge;
2. the PR-specific non-optimization regression set passes;
3. no live execution authorization can launch a new formal optimization from the reviewed branch;
4. referenced formal source evidence is present or explicitly classified as unavailable;
5. the PR does not delete or overwrite a previously frozen formal result.

## Per-PR status

| PR | Base → head | Primary scope | Non-optimization tests | Risk | Ready for review? |
|---|---|---|---:|---|---|
| #11 | `main` → `codex/e1-formal-algorithm-benchmark` | Renault E1–E7 evidence, E1b baselines, convergence audits | 35 passed, 2 failed | **HIGH** | **No** |
| #12 | PR #11 → `codex/service-calibration-robustness` | Formal service-level / penalty calibration archive | 11 passed, 1 failed | **MEDIUM** | **No** |
| #13 | PR #12 → `codex/algorithm-scaling-convergence-cost` | Scaling V2, repaired Pure cut guard, 89/90 final reporting | 14 passed | **MEDIUM** | **No; safety closeout required** |
| #14 | PR #13 → `codex/direct-scaling-experiment-preparation` | Renault E1b evidence recovery and guarded Direct preparation | 24 passed | **HIGH** | **No** |
| #15 | PR #14 → `experiment/xxl10-four-method-final-archive` | Direct/EF/Aggregate/PRB XXL10 archive and four-method analysis | 96 passed | **MEDIUM, stack-dependent** | **Yes as Draft review only; not merge-ready** |

### PR #11

- GitHub state: Draft, mergeable, clean; 69 commits and 401 files relative to `main`.
- Result diff: 25 additions; no result deletions or overwrites.
- The E1b protocol regression detects protected-identity hash drift for the Standard-Benders implementation/runner/schema/protocol/audit bundle.
- Eight referenced E1a PRB source paths matching `experiments/results/e1_empirical_8case_v1/E1-<case>-PRB/result.json` are absent from the Git tree. Consequently the E1b comparison cannot be independently reconstructed from those referenced PRB raw files on this branch.
- Eleven historical configurations have `formal_run_authorized=true`. They are execution records, but they are not closed authorization controls.
- Recommendation: reconcile the protected hash table with the intended frozen commit without rewriting historical results; archive the eight referenced E1a PRB raw records or explicitly downgrade their reproducibility status; add a new execution-freeze control rather than editing historical authorization records.

### PR #12

- GitHub state: non-Draft, mergeable, clean; 6 commits and 150 files relative to PR #11.
- Result diff: 127 additions; no result deletions or overwrites.
- Fixed scientific parameters remain `Gamma=2`, `beta=1.0`, and `lambda_R=0.05`; the `SL` and `phi_multiplier` grids are intentional experimental factors rather than parameter drift.
- The service-calibration configuration remains `formal_run_authorized=true`, while `test_unauthorized_execution_is_blocked` still expects a closed gate. The runner refuses to overwrite an existing target, so the current archive is protected, but the test/config contract is inconsistent.
- Recommendation: preserve the original authorization record and add a separate post-run freeze/closure control; update the stale test to validate archived-state protection.

### PR #13

- GitHub state: non-Draft, mergeable, clean; 15 commits and 631 files relative to PR #12.
- Result diff: 605 additions; no result deletions or overwrites.
- The final Scaling V2 record is intact: 90 expected, 89 exact-certified, 1 documented non-certified, 0 unattempted.
- `ASC_XXL10_S20260925_PURE_BENDERS` remains non-certified with `solution_level_certification=true`, `cut_validity_certification=false`, and disposition `PRESERVED_AS_NON_CERTIFIED_NO_TOLERANCE_RELAXATION_NO_RERUN`. No result.json is fabricated for it.
- The Scaling V2 authorization configuration remains open. Certified results are resume-verified and skipped, but the one documented failure has no result.json and can therefore be selected for another attempt by the historical runner.
- Scientific parameters align with the downstream Direct protocol (`Gamma=2`, `beta=1.0`, `lambda_R=0.05`, `SL=0.90`, `phi_multiplier=1.85`); no unintended parameter inconsistency was found.
- Recommendation: add an immutable post-run freeze control that blocks every Scaling V2 execution, including the documented Pure failure, while leaving the historical authorization and failure evidence unchanged.

### PR #14

- GitHub state: Draft, mergeable, clean; 8 commits and 133 files relative to PR #13.
- Result diff: 99 additions; no result deletions or overwrites.
- Renault Pure and Aggregate E1b recovery tests pass and the 88 recovered evidence files are present in the stack.
- **Blocking safety finding:** `experiments/configs/formal/direct_scaling_l10_resource_retry_v2.yaml` remains `formal_run_authorized=true` for `DIRECT_L10_S20260921`. The remote PR #14 head contains attempt-001 and attempt-002, but no successful canonical result. The runner computes the next attempt dynamically, so an execution command can still launch attempt-003.
- The whitelist limits the exposure to one L10 condition; it does not authorize the remaining 29 Direct conditions. This limits scope but does not close the execution risk.
- Recommendation: before marking PR #14 ready, add a new versioned freeze/closure control with authorization false and a regression test proving attempt-003 cannot launch. Do not rewrite the historical authorization commit or attempts.

### PR #15

- GitHub state: Draft, mergeable, clean after rebasing the review base only; branch history was not rewritten.
- Exact comparison against the PR #14 remote head: 106 commits, 1,854 files, 745,114 insertions, and 86 deletions. Result-tree changes are additions only.
- The four-method XXL10 archive contains 40/40 seed-method records. Direct remains 3/10 exact-certified; EF-BD, Aggregate-BD, and PRB-BD remain 10/10 exact-certified.
- The Direct three-stage history, seed-20260922 post-hoc timeout classification, and seed-20260927 monitor hard-timeout evidence remain preserved.
- PR #15-specific regression coverage passes. It is suitable for Draft review, but it must not be merged before PR #11–#14 are merged in order and the execution-gate blockers above are resolved.

## Merge-conflict and result-integrity summary

- GitHub currently reports no code merge conflicts in PR #11–#15.
- Across each adjacent PR comparison, no file is deleted.
- Formal result-tree changes are additions only: PR #11: 25; PR #12: 127; PR #13: 605; PR #14: 99; PR #15: 1,650.
- No scientific-model or solver-parameter change was made during this audit.
- No formal instance or result file was regenerated or edited.

## Recommended merge order

1. Resolve PR #11 protected-hash and missing E1a PRB raw-source findings; close historical execution gates using additive freeze controls; then review and merge PR #11.
2. Add the service-calibration post-run closure/test correction; review and merge PR #12.
3. Add the Scaling V2 freeze control that preserves the 89/90 + 1 non-certified truth; review and merge PR #13.
4. Close the PR #14 Direct attempt-003 authorization without rewriting its historical authorization record; review and merge PR #14.
5. Reconfirm PR #15's base diff after the lower stack merges, rerun its non-optimization archive tests, then move PR #15 from Draft to Ready for Review. Do not auto-merge.

## Final decision

- `PR #15 base corrected`: **PASS**.
- `Stack ancestry`: **PASS**.
- `No formal result overwrite/deletion`: **PASS**.
- `Pure XXL10 seed 20260925 failure preserved`: **PASS**.
- `All lower PRs ready for review`: **FAIL** because PR #11, #12, #13, and #14 require the additive safety/evidence closeouts described above.
- `PR #15 ready for Draft review`: **PASS**, contingent on the stacked dependencies and not yet merge-ready.
