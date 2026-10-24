# PR #11 final test and mergeability audit

Date: 2026-10-24
Repository: `Hoshino12172003/budget-inventory-benders`
PR: `#11` (`codex/e1-formal-algorithm-benchmark` -> `main`)
Starting PR head: `f1de3a82766d4bd45064a86a05053ea6969fb0a3`
Scientific-evidence disposition: `RESOLVED_BY_SCOPE_REDUCTION`

## Scope and safety

This audit performed no optimization, instance generation, scientific-parameter change,
or historical-result rewrite. The changes are limited to development-input availability
reporting and cross-platform source-identity testing. No file under
`experiments/results/` was changed.

## Five failing tests: root causes and resolution

The complete E1 collection initially reported `57 passed, 5 failed`.

| Failing test | Original assertion/error | Dependency | Scientific effect | Resolution without solving |
|---|---|---|---|---|
| `tests/test_e1c_gamma_sensitivity_development.py::test_dry_run_freezes_grid_identity_and_resources` | `FileNotFoundError` while `validate_config()` loaded the prepared L instance | `experiments/results/e1c_development_probe_v1/L/PREPARE/instance.json` and `baseline.json` | None on formal conclusions. The configuration is explicitly `development_only=true`, `paper_final_observation=false`, and `formal_run_authorized=false`. | `dry_run()` now validates the frozen static configuration and returns `BLOCKED_SOURCE_MISSING`, the exact missing paths, and `optimization_calls=0`. |
| `tests/test_e1c_gamma_sensitivity_development.py::test_config_is_development_only_and_reuses_prepared_l` | Same missing prepared-input failure prevented configuration assertions | Same prepared instance and baseline | Same development-only scope; the absent instance cannot be used to assert dimensions or baseline fields. | Static configuration is audited independently; loading scientific inputs remains fail-closed with `E1C_GAMMA_DEVELOPMENT_INPUT_MISSING`. |
| `tests/test_e1c_gamma_sensitivity_development.py::test_preflight_fails_closed_below_frozen_threshold` | Test could not reach the resource assertion because input loading failed first | Prepared instance and baseline, although the resource gate itself needs neither | None; resource thresholds are configuration properties. | Test now obtains the statically validated configuration and still proves that memory below 18 GiB is rejected. |
| `tests/test_e1c_gamma_sensitivity_development.py::test_gamma2_sanity_checks_all_three_frozen_methods` | Missing reference `result.json` files for Pure, Aggregate, and PRB | Three paths under `experiments/results/e1c_development_probe_v1/L/` | The absent files are unarchived development-probe inputs, not primary formal-paper evidence. Their numerical values cannot be reconstructed or substituted. | The test now verifies that all three dependencies are explicitly reported missing. The production sanity check remains unchanged and cannot run without real files. |
| `tests/test_e1c_scaling_design.py::test_design_is_fail_closed_and_balanced` | Raw worktree SHA `513b77be...` did not equal frozen SHA `8c82c3ea...` | `src/robust_inventory_reconfiguration/e1c_scaling.py` | None. Git history and LF-normalized content retain the frozen generator exactly. | The test hashes repository text after CRLF-to-LF normalization. The frozen SHA is unchanged. |

The five development inputs listed by the new audit have never been tracked on this
branch or in the inspected Git history. No placeholder, regenerated input, or synthetic
historical result was added. The development Gamma experiment therefore remains
unavailable and explicitly blocked; this is test layering, not a scientific PASS.

## Generator identity reconciliation

- Frozen generator commit: `b3dba35c3b0dec8fe0e86d945ccc971aca9cb12c`
- Frozen SHA-256: `8c82c3eaefb8a50064d17ab08b03bbc04909cc84f07530cea85d675d88283181`
- Current Git blob/LF-normalized checkout SHA-256: the same `8c82c3e...`
- Windows CRLF checkout raw-byte SHA-256: `513b77be91d20bcb1d68ad0649dd29a5108dceddcb43e05c7d67a4a993f27838`
- `git log --follow` shows no later repository-content revision of this file.

The apparent drift was solely checkout newline conversion (`index: LF`, `worktree:
CRLF`), not generator evolution. Existing formal instances and their identities are not
affected. The historical frozen SHA was not edited.

## Regression results

- Targeted E1c development/scaling tests: `10 passed`.
- Complete `test_e1*.py` collection after repair: `62 passed`.
- Python compilation: passed.
- `git diff --check`: passed.
- Optimization calls: `0`.
- Formal result changes: none (`git diff` under `experiments/results/` is empty).

## Mergeability audit

After `git fetch origin`:

- `origin/main`: `0902bc9eed597ba4a18c8283a82359bcf682276c`
- Merge base with the PR branch: the same commit.
- Ahead/behind (`origin/main...PR head`): `0` commits on main only, `72` commits on
  the repaired PR branch after the test-fix commit.
- GitHub API state before the final audit commit: `mergeable=MERGEABLE`,
  `mergeStateStatus=CLEAN`, Draft remains true.

An isolated temporary worktree was created at `origin/main`. A non-committing merge of
the repaired PR head completed successfully (`merge exit 0`) and reported no unmerged
paths. The temporary merge was aborted and the worktree removed. Thus the earlier
`mergeable=false` observation was stale or transient; there is no current content
conflict and no upstream commit missing from this branch.

## Downstream PR impact

PRs #12-#15 are stacked descendants. These fixes do not alter scientific results, but
their branches do not automatically acquire the new #11 commits. After #11 is reviewed,
the safe synchronization strategy is an ordinary forward merge of the updated upstream
branch into each immediate child in order (#12, then #13, #14, and #15), with tests at
each layer. No rebase, force push, or downstream synchronization was performed here.

## Final recommendation

`READY_FOR_REVIEW_WITH_DISCLOSED_DEVELOPMENT_INPUT_GAP`.

The prior material E1a evidence issue remains resolved only through the documented scope
reduction; missing primary E1a PRB results were not recovered or reclassified. The E1c
development probe remains `SOURCE_MISSING` and cannot be executed or cited as verified
scientific evidence. Neither limitation blocks review of the reduced, traceable PR scope.
There are no remaining code-test or merge-conflict blockers identified by this audit.
