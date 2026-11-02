# E6-5X5 archival provenance

## Archival status

`E6_5X5_ARCHIVAL_COMPLETE`

The E6-5X5 experiment was formally executed in the independent frozen historical checkout:

`E:/paper-code/formal-history/e6-frozen-code-cc87b683`

The directory below is a byte-identical archival copy for paper analysis and Section 5 writing. It
is not a rerun and must not be represented as a result produced by the main paper checkout:

`experiments/results/e6_budget_risk_5x5_v1`

No optimization was invoked during archival, no JSON was reserialized, and no result,
`first_stage_solution.json`, or historical E3/E4/E6 artifact was modified.

## Frozen execution identity

- Historical base commit: `cc87b68363fa9cc444046f7823a6807412bb7ca8`
- Formal authorization commit: `2fb30d2dd63c7a9d6e0135c422af09c498573169`
- Frozen model SHA-256: `c4f718f6a12deb22772cdce20464ca617fa6e19c750a90be06cd2ddc8c245173`
- Frozen PRB SHA-256: `eab5ea31c6dbbc6446799f28bb6b54673eb7b57690cd4540f8a49b4a53757b6f`
- Formal E6-5X5 runner SHA-256: `41b921c9baa2f8005f13c773c58fd3a0514c7abcd5e4212c2297a4238da97976`
- Deterministic result-tree SHA-256: `6259bffb978472bebe1743c4df87ccf067d0289de78a4eae21125852d7b3eb6e`

## Completeness and identity

- Expected and materialized cells: `200/200`
- Reused cells: `104` (`16` E3, `16` E4, `72` historical E6)
- Newly solved E6-5X5 cells: `96`
- Missing or failed cells: `0`
- Interpolated or synthetically completed cells: `0`
- `result.json`: `200`
- `provenance.json`: `200`
- `first_stage_solution.json`: `200`
- Total archived result files: `600`
- Source/destination hash mismatches: `0`

The file-level source manifest is
`artifacts/e6_budget_risk_5x5_final_source_hashes.csv`. The aggregate source identity is
`artifacts/e6_budget_risk_5x5_final_source_identity.json`. The post-copy comparison is recorded in
`artifacts/e6_budget_risk_5x5_archival_copy_audit.csv` and
`artifacts/e6_budget_risk_5x5_archival_copy_audit.json`.

The copied `artifacts/e6_budget_risk_5x5_delivery_sha256.csv` is historical frozen-checkout
evidence. Entries for checkout-level files such as `.gitignore` and `.gitattributes` describe the
execution checkout and are not a hash contract for this main repository.

## Analysis entry points

- Summarizer: `scripts/summarize_e6_budget_risk_5x5_results.py`
- Mean normalized objective matrix:
  `artifacts/e6_budget_risk_5x5_mean_normalized_objective.csv`
- Mean RI matrix: `artifacts/e6_budget_risk_5x5_mean_ri_percent.csv`

The summarizer resolves `ROOT` from its location and reads the repository-relative result root
`experiments/results/e6_budget_risk_5x5_v1`; it does not depend on the historical checkout path.
Metric definitions, RI computation, objective normalization, and reuse classification were not
changed during archival.

## Execution safety

`ARCHIVAL_ONLY — DO_NOT_USE_TO_TRIGGER_FORMAL_EXECUTION`

The formal authorized manifest from the historical checkout was not copied into an active execution
location in this repository. The pre-existing local preparation manifest in this checkout remains
unauthorized, and this checkout has a different current model identity from the frozen E6 execution
bundle. The archived result tree is an analysis input only. Any future execution must use an
independently reviewed execution protocol; this archival record grants no authorization.

The result tree is intentionally repository-local and ignored rather than committed as a large
result payload. The small hash manifests, copy audits, matrices, analysis script, and provenance
documents are suitable for Git tracking.
