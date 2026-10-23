# E1a PRB missing-source scientific-impact audit

Status: `BLOCKED_MATERIAL_EVIDENCE`

Audit date: 2026-10-23

## Scope and decision rule

This is a read-only scientific-impact audit. It does not repeat the recovery
search, run an optimizer, regenerate an instance, or promote a derived table or
later experiment to the status of the missing source artifact.

The eight frozen E1a PRB `result.json` files referenced by
`experiments/configs/formal/e1b_standard_vs_prb_authorization.json` remain
absent. The completed recovery search found zero files matching the eight
expected SHA-256 values. A claim is therefore treated as independently
reproducible only when it has a separate, present raw result chain. Agreement
with a derived CSV or a later run is corroboration, not source recovery.

The evidence classes used below are:

- **F0 — missing frozen source:** the expected E1a PRB `result.json` is absent.
- **D1 — frozen derivative:** a table, JSON summary, audit, or figure retains
  values derived from F0, but cannot be regenerated from the committed source.
- **R2 — later replication:** a later development run uses the same frozen
  instance identity and model parameters, but has a different result hash,
  execution batch, solver environment, and certification record.
- **I3 — independent formal evidence:** a distinct experiment has its own raw
  result, provenance, identity, and certification chain and does not read F0.

The merge waiver is acceptable only if all material claims relying on F0 can be
supported by I3 evidence or are removed from the paper's evidentiary claims.
That condition is not currently met.

## Per-case evidence matrix

The frozen objective and runtime columns below are D1 values retained in
`table_e1_empirical_performance.csv`; they are not newly certified raw results.
The later replication is the PRB side of the Renault Basic-BD development
comparison. It used `Gamma=2` and `lambda_R=0.05`, the same frozen instance and
first-stage identities, and Gurobi 13.0.1. The missing E1a source was associated
with the E1a/E1b frozen environment, including Gurobi 13.0.2. Thus the later
records cannot validate the original timing provenance.

| Case | Expected E1a SHA-256 | Frozen PRB objective (D1) | Frozen core time (s, D1) | Later result SHA-256 (R2) | Same instance hash | Later objective | Later strict certification | Scientific interpretation |
|---|---|---:|---:|---|---|---:|---|---|
| 210129 | `4845e97bdc6486832b95519dd4b1d66fe5ad75b5e87ad74167e9df68f9bf7c91` | 851260.24783255 | 1.1686394000 | `a10d7b75994e0973cc8392af4fa3cd35191101c08224b7dd6788af399e38041d` | Yes | 851260.24783255 | PASS | Objective independently corroborated; original timing and provenance remain unverifiable. |
| 210202 | `dfa3cf6ac0de0cf65c7938f1a898343299e586f20b72e23f1800c0ac57c3ba85` | 1058780.7942496866 | 1.2333677001 | `41a075a785062a2f084bfd36580b687201d72631c3fa401a99b378b8dbf68495` | Yes | 1058780.7942496866 | PASS | Objective independently corroborated; original timing and provenance remain unverifiable. |
| 210310 | `94c02c30c52b26a3ba0e748170fb5f9e7ac8631f1c2d1515082334f7d81c177a` | 714814.5477077012 | 1.3473797999 | `879b3cd37f66931e345766267e8b2b897b71e1d53ff909c13f90653c776677ef` | Yes | 714814.5477077012 | PASS | Objective independently corroborated; the old mismatch audit remains a derivative of the missing source. |
| 210323 | `89acb6621531563c16850b48c26647507ce51b52112784e1042c27955cb4f655` | 627147.2289325014 | 1.0144453000 | `e7916e79b40b814b7bbb8c6ff6bc391f1593383783cdbfd8b1c2fbc3639f5bd3` | Yes | 627147.2289325014 | PASS | Objective independently corroborated; original timing and provenance remain unverifiable. |
| 210330 | `276557a1f3118ef7786e68fd9bdcd38ed5782fc8425d90a7ff64f09137fcffbb` | 657659.5492546142 | 0.9831330001 | `b817d0c78d170133045e30ae0e224d38ca582e2a5c79e348999364bc07c49fd2` | Yes | 657659.5492546142 | **FAIL** | Independent global objective and cut checks pass, but strict PRB certification fails the frozen global-risk-budget coupling gate; it cannot replace the missing E1a certification. |
| 210428 | `c359e1d428a69738107c22a66a56b4dc1c5a76f933d79e986d11cfa77e94e14c` | 793717.3880816748 | 1.4929630999 | `723781de260ebbb770ce22bf7eb9dcd927c68e9894841d0f47dc54c2f02ae6cb` | Yes | 793717.3880816748 | PASS | Objective independently corroborated; original timing and provenance remain unverifiable. |
| 210611 | `a8860c506e13dbde0fd01c5f30d38575065dca2f7e0d882f138f176383f3a4bb` | 617415.6681421611 | 1.7427417999 | `b72f8a8e4283b60d31e4623b48434a6fb3770619ee07861aa32ddc9141582e09` | Yes | 617415.6681421611 | PASS | Objective independently corroborated; original timing and provenance remain unverifiable. |
| 210628 | `bcf37227fc9c461658077ae0e68f51d2905da190d1efc5dae392c81e595c69b4` | 676700.8373031134 | 1.2426573001 | `fa38492fe7ae25f3a27b8dcb34c5a50acd9286f2cf6fce1c207ce439bdd219c1` | Yes | 676700.8373031134 | PASS | Objective independently corroborated; a separate E1 benchmark record also exists, but neither file is byte-identical to the expected E1a source. |

Summary of R2 evidence: instance identity matches 8/8; objective values match the
frozen derivative table 8/8; strict certification passes 7/8 and fails for
210330. The eight R2 SHA-256 values differ from the eight expected E1a hashes.
This is strong support for the mathematical objective values, but not recovery
of the original executions, timing observations, iteration diagnostics, or
certification provenance.

## Evidence-dependency matrix

| Paper output or claim | Direct dependency | Evidence remaining | Scientific impact | Required treatment |
|---|---|---|---|---|
| `table_e1_empirical_performance.csv` — eight Direct/PRB rows | Reads all eight missing E1a PRB results | D1 table; Direct-side records; R2 objective replication | PRB objectives are corroborated, but PRB timing, iterations, cut counts, and original certification cannot be independently regenerated | Retain only as a clearly labelled legacy derivative; do not present it as a fully reproducible raw-data table. |
| `table_e1_empirical_performance_summary.csv`, `artifacts/e1_empirical_performance_summary.json`, and `docs/e1_empirical_performance_summary.md` | Computed directly from the missing files by `scripts/summarize_e1_empirical_performance.py` | D1 summaries only | Claims of PRB faster in 8/8, mean/median times, geometric-mean speedup 2.2253, iteration mean 4.625, cut mean 32.5, and runtime correlations are not independently reproducible | Remove from confirmatory results or label explicitly as historical, source-incomplete descriptive statistics. Do not use them as primary performance evidence. |
| E1a objective-consistency claim (8/8 within `1e-4`) | Original claim reads missing PRB objectives/certifications | R2 reproduces all eight objective values; 7/8 strict PASS, 210330 strict FAIL | Numerical objectives are strongly corroborated, but the claim that all eight original PRB runs have a complete exact-certification chain is unsupported | Rephrase as: later independent runs reproduce 8/8 objectives, with 7/8 strict certification and one disclosed coupling-only failure. Do not call this recovery of E1a. |
| `table_e1_objective_mismatch_audit.csv`, `artifacts/e1_objective_mismatch_audit_210310_210330.json`, and associated report | Loads the missing 210310 and 210330 PRB results and saved first-stage decisions | D1 audit logs and fixed-first-stage evaluations remain | The numerical diagnostic can be cited only as a historical audit; its source decision identity cannot be rebuilt from the missing raw result chain | Downgrade to source-incomplete diagnostic or exclude from confirmatory evidence. |
| `artifacts/e1_210330_global_coupling_audit.json` and report | Loads the missing 210330 result | D1 diagnostic plus R2 210330 failure with the same objective | The diagnostic does not establish a strict E1a PASS; later evidence instead confirms a coupling-gate problem | Preserve the failure disclosure. Do not use objective agreement as a substitute for coupling certification. |
| E1b Standard-versus-PRB comparison | E1b runner and authorization manifest use E1a PRB files as immutable comparison rows | Standard-BD raw evidence is independently recoverable; PRB comparison rows are F0/D1 | E1b is not an independent formal PRB run. Standard-BD results stand alone, but paired runtime and objective claims against PRB are source-incomplete | Keep Standard-BD raw results; label or remove PRB paired statistics until a source-complete comparison exists. |
| Renault four-method table (Direct, Pure/Global, Aggregate, PRB) | Downstream summarizer takes Direct and PRB from `table_e1_empirical_performance.csv`; recovered Pure and Aggregate files are independent | Pure and Aggregate raw results; Direct summary/source records; PRB D1 rows | The table is complete numerically but not uniformly source-complete. Its PRB time/certification cells inherit F0 | Retain only with cell-level provenance disclosure; do not describe all four methods as 8/8 raw-recomputable. |
| E1c empirical-anchor mechanism comparison and iteration figure/table | Empirical PRB timing, iterations, cuts, and first-stage comparisons descend from E1a/E1b artifacts | Scaling portions have their own evidence; the empirical anchor is D1 | Large-scale mechanism conclusions may stand on their independent scaling records, but the Renault anchor cannot serve as raw confirmation | Remove or footnote the Renault anchor; preserve independently sourced scaling rows. |
| E2 policy comparison | The robust baseline/first-stage policy is read from the E1a PRB result chain | E2-specific outputs may retain their own computed results, but the imported baseline provenance is incomplete | Conclusions requiring the exact frozen E1a policy lineage are not fully reproducible from the repository | Mark E1-derived baseline cells and policy-path claims as source-incomplete; retain only independently archived E2 quantities with explicit provenance. |
| E3 budget sensitivity | The `beta=1` reference/reuse path descends from E1a/E2 | Non-reference budget runs may have independent evidence | Reference-cell reuse and normalized comparisons inherit the missing source | Label the reference cell; do not claim the entire table is regenerated solely from present raw files. |
| E4 risk-budget sensitivity | `scripts/summarize_e4_gamma_results.py` reads the E1a result for the `Gamma=2` diagnostic/reference | Other `Gamma` runs may be independent | The center/reference point is source-incomplete; other points are not invalidated solely by this absence | Mark `Gamma=2` as a legacy reused reference and keep independently archived non-reference points separate. |
| E5 friction sensitivity | Its `lambda_R=0.05` baseline is reused through E4/E1 | Non-baseline friction runs may be independent | Baseline-linked normalization/provenance is incomplete | Label baseline reuse; retain only source-complete non-baseline evidence without implying a complete regenerated panel. |
| E6 and E7 interaction tables/figures | Selected reused cells trace through E3–E5 and ultimately E1 | Newly solved cells can remain independently evidenced | Missing E1 does not invalidate every interaction cell, but it breaks the raw chain for inherited baseline cells | Publish cell-level source flags; exclude source-incomplete cells from claims of full-table reproducibility. |
| Scaling V2 (L10/XL10/XXL10) | No E1a Renault source path is used; it has separate frozen instances, runners, manifests, and results | I3 | No scientific impact from the missing Renault E1a files | Retain, including the disclosed 89/90 exact-certification count and the one Pure-BD failure. |
| XXL10 four-method final archive | No E1a Renault source path is used; 40 method/seed records have independent XXL10 identities | I3 | No scientific impact from the missing Renault E1a files | Retain the 40/40 record matrix and its stated certification split; continue to distinguish Direct limited runs from exact results. |

## Renault E1b independence assessment

Renault E1b does **not** supply an independent PRB source. Its protocol states
that the PRB rows are immutable references to E1a, and its authorization
manifest names the same eight missing paths and hashes. The recovered E1b Pure
and Aggregate/Standard files are valuable independent evidence for those two
methods, but they do not recreate PRB's original timing, iterations, first-stage
solution, or certification chain.

Consequently, E1b can support standalone conclusions about Pure/Global-BD and
Aggregate/Standard-BD and their own exact objectives. It cannot, without a
disclosure and a downgrade, support the principal paired claim that those
methods were compared against eight source-complete formal E1a PRB runs. A
numerically complete four-method table is not the same as an 8/8 raw-recomputable
four-method experiment.

## Independent experiments

Scaling V2 and the XXL10 final four-method archive use distinct synthetic
Scaling V2 instances, condition identifiers, manifests, and result directories.
Their analysis code does not use the missing
`experiments/results/e1_empirical_8case_v1/E1-<case>-PRB/result.json` paths or
the Renault E1a performance table as scientific inputs. Therefore:

- Scaling V2's 89/90 exact-certification statement is unaffected.
- The historical Pure-BD XXL10 seed 20260925 failure remains a failure.
- The XXL10 40-record matrix is unaffected: Direct 3/10 exact, EF-BD 10/10,
  Aggregate-BD 10/10, and PRB-BD 10/10, with Direct limited runs reported as
  limited rather than exact.
- No Scaling V2 or XXL10 result may be used to claim that the missing Renault
  E1a raw records have been recovered; they support separate scaling claims.

## Paper treatment

### Results that may be retained

1. Frozen Renault instance definitions, case characteristics, mappings, `x0`,
   and budget identities whose own source files and hashes are present.
2. Direct-side Renault evidence with a complete raw chain.
3. Recovered Pure/Global and Aggregate/Standard raw results, described as their
   own formal evidence rather than an independent PRB archive.
4. Later PRB development objectives as replication evidence: 8/8 objective
   agreement, 7/8 strict PASS, and the disclosed 210330 FAIL.
5. Scaling V2 and XXL10 results and conclusions, because they are independent.
6. E2–E7 cells that have their own complete raw and provenance chain, provided
   reused E1-derived cells are identified separately.

### Results that must be downgraded to historical description

1. The E1a PRB core times, iteration counts, cut counts, master solves, product
   subproblem counts, and original eight-run certification labels.
2. The 8/8 PRB runtime-win claim and all means, medians, correlations, and
   speedups computed from the absent source files.
3. Renault E1b/E1c paired PRB comparisons that inherit those values.
4. The 210310/210330 fixed-first-stage mismatch and 210330 coupling reports
   insofar as they claim direct reconstruction from the missing E1a result.

### Statistics that must be removed or relabelled

- Relabel the E1a runtime summary and speedup statistics as
  **legacy derived values; original raw PRB records unavailable**. If the journal
  requires raw-data reproducibility, remove them from confirmatory tables and
  the abstract/conclusion.
- Do not report an 8/8 exact PRB certification rate from the later development
  batch. Its correct strict rate is 7/8, with 210330 FAIL.
- Do not combine R2 runtimes with E1a Direct runtimes as if they were a paired
  same-batch benchmark; solver version and execution provenance differ.
- Add cell-level provenance flags to downstream Renault tables containing
  reused E1-derived baseline cells.

### Conclusions unaffected

- The mathematical definition of PRB-BD and code-level correctness arguments
  not based on these eight executions.
- Independent Scaling V2 convergence, iteration, and timing findings, subject
  to their own disclosed 89/90 certification status.
- Independent XXL10 four-method feasibility and performance findings, subject
  to their own exact/limited-run classifications.
- Standalone findings from source-complete Direct, Pure/Global,
  Aggregate/Standard, EF-BD, or later development experiments, when they are
  not presented as the missing E1a run.

## PR #11 merge recommendation

**Decision: `BLOCKED_MATERIAL_EVIDENCE`.**

PR #11 cannot presently receive a source-missing waiver while retaining its
current confirmatory E1a/E1b performance claims. The absent files are the sole
raw PRB basis for a central eight-case runtime table, the 8/8 speed claim,
iteration and cut statistics, and the PRB side of E1b paired comparisons.
Derived summaries preserve numbers but not an independently auditable execution
chain. Later development runs strongly corroborate all eight objective values,
but they use a different result identity and environment and yield only 7/8
strict certification. They do not validate the original runtimes.

The block can be removed without rerunning an experiment only by changing the
paper and PR scope: remove the source-incomplete runtime/certification claims
from confirmatory evidence, label retained values as historical derivatives,
add cell-level provenance to dependent tables, and base the principal algorithm
performance claims on source-complete independent experiments. That would be a
new editorial acceptance decision, not recovery of E1a. Until that revision is
made and audited, PR #11 remains blocked.

## Suggested supplementary-material limitation statement

> The original per-instance PRB-BD `result.json` records for the eight Renault
> E1a runs could not be recovered from the repository, local historical
> workspaces, Git objects, or available archives; none of the eight expected
> SHA-256 identities was found. Derived tables retain the reported objectives
> and timing statistics, but those execution records cannot be independently
> reconstructed. A later development experiment used the same frozen instance
> identities and scientific parameters and reproduced all eight objective
> values; seven runs passed the strict certification suite, while case 210330
> failed the global-risk-budget coupling tolerance check. Because the later
> runs used a different execution batch and solver environment, they are
> reported only as corroborating evidence and not as replacements for the
> missing E1a sources. All Scaling V2 and XXL10 results use independent frozen
> instances and raw result chains and are unaffected by this limitation.
