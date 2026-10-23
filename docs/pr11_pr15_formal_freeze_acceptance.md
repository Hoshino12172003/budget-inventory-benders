# PR #11–#15 formal experiment freeze and pre-merge acceptance

Audit date: 2026-10-23  
Optimization calls during this work: **0**

## Immutable evidence baseline

- The `experiments/results` Git tree before and after the safety work is
  `0a531768368070cc7f589998b04129fd5e8a8e2c`; no tracked formal result byte
  changed.
- Scaling V2 remains 90 expected, 89 exact-certified, one documented
  non-certified condition, and zero unattempted conditions. The preserved
  condition is `ASC_XXL10_S20260925_PURE_BENDERS`; it was not rerun or
  reclassified.
- The XXL10 archive contains 40 records: Direct 3/10 exact-certified, EF-BD
  10/10, Aggregate-BD 10/10, and PRB-BD 10/10. The three Direct execution
  stages remain 1 pilot + 1 remaining-9 record + 8 remaining-8 records.
- `DIRECT_XXL10_S20260927` remains an outer
  `MONITOR_HARD_TIME_LIMIT` record with Worker return code 15; no objective,
  bound, gap, or final solver status was inferred.

## Safety mechanism

`formal_execution_freeze_v1.json` is an independent, versioned revocation
registry. In-scope historical Runner, Worker, monitored-launch, and direct
formal solve paths consult it before any optimizer model can be built. Copying
or renaming a historical Direct YAML does not bypass the experiment-identity
revocation. Read-only audits and reporting remain available. Any future run
requires a new protocol identity and new explicit authorization.

Historical authorization and provenance files were not rewritten. The E1b
and Direct frozen execution identities are verified against their original Git
blobs through explicit reconciliation records. The current Direct runner has
only an execution-revocation change; its historical execution blob remains
available at commit `3d4bcd10d837d3425a76ecaf54162a1e4a57e26b` with SHA-256
`fef8019f9aa9be1d2942a5d3aad363c2c3c28929e52cc02b359d1626a1880edd`.

## Per-PR acceptance

| PR | Head after repair | Scope and repair | Tests | Risk | Ready for Review |
|---|---|---|---:|---|---|
| #11 | `0631111342bdf663dfef943bb20c6fe708df3359` | Reconciled E1b historical blob identities; froze 11 historical authorization records at execution entry points; documented E1a PRB source search. | 38 passed | High | **No — BLOCKED_SOURCE_MISSING** |
| #12 | `e70da982dbbd65d842e771de90db9f3a4e283c27` | Added Service Calibration Runner/direct-solver revocation without changing the historical config; verified the 40-case archive. | 17 passed | Low | Technically yes; stack remains blocked by #11 |
| #13 | `ed2408269447bc20ea046d3e84a758805e2aab01` | Froze both Scaling V2 experiment identities at Runner and Worker paths; preserved the one non-certified Pure-BD record. | 30 passed | Low | Technically yes; stack remains blocked by #11 |
| #14 | `e738a42f096aebba34b824b8ed8fef2beef24048` | Revoked historical Direct protocols by experiment identity, including the L10 retry with no successful canonical; copied configs cannot reactivate it. | 33 passed | Medium | Technically yes after remote synchronization; stack remains blocked by #11 |
| #15 | recorded by final archive commit | Rebuilt the XXL10 comparison read-only, retained historical Direct code identity, and recorded the current execution-only guard identity. | Combined acceptance: 114 passed | Medium | Technically yes after remote synchronization; remains Draft and stack-blocked by #11 |

## E1a PRB source limitation

The eight E1a PRB `result.json` paths referenced by the E1b manifest are not
present in any Git object or historical ZIP found in the audited repository,
paper-project, and known Codex work locations. Their expected hashes remain
unchanged. Because only downstream summaries are available, these eight raw
sources remain `BLOCKED_SOURCE_MISSING`; no summary value was promoted to a raw
result and no optimization was rerun.

## Verification results

- Final selected regression set: **114 passed, 0 failed**.
- Python compilation: passed on modified source and experiment modules.
- `git diff --check`: passed.
- Service Calibration archive SHA-256:
  `16f6b2497b7644ef5310fa41201fbe0a81e4c754c485427d39a1fb5b43e57ff2`.
- XXL10 paper CSV, Excel, and Markdown were rebuilt from archived source files
  with `optimization_calls=0`; the integrity audit reports 40 records and all
  available provenance hashes matching.
- No result, instance, solver tolerance, mathematical model, or scientific
  parameter was changed.

## Recommended merge order

Keep the existing order: **#11 → #12 → #13 → #14 → #15**. Do not merge the
stack until #11's eight referenced E1a PRB raw results are recovered with the
exact manifest hashes, or the missing-source limitation is explicitly accepted
as a review blocker waiver. No PR was merged or changed from Draft/Ready state
by this work.
