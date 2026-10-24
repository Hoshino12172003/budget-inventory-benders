# E2-E7 reused-baseline evidence audit

Status: `CELL_LEVEL_DISCLOSURE_REQUIRED`

This audit concerns only cells whose provenance reuses the missing E1a PRB
baseline. It does not invalidate independently solved and archived cells.

| Experiment | Affected cell or dependency | Original source | Current evidence | Treatment |
|---|---|---|---|---|
| E2 policy comparison | Robust baseline policy and E1-derived first-stage state | E1a PRB result/solution | `SOURCE_MISSING`; downstream derivative may remain | Retain independently archived E2 outputs, but label the inherited robust baseline `HISTORICAL_SUMMARY_ONLY`; remove any claim that the full pathway is reconstructed from present E1a raw evidence. |
| E3 budget sensitivity | `beta=1.00` reference and quantities normalized to it | E2/E1 reuse chain | Reused reference is source-incomplete; newly solved budget levels may be `PRIMARY_VERIFIED` | Keep new budget cells. Mark B100 and dependent normalizations as inherited-source-limited. |
| E4 risk-budget sensitivity | `Gamma=2` reference/diagnostic | Direct read of E1a PRB result in the summarizer | `SOURCE_MISSING`; non-G2 runs may remain verified | Mark G2 historical. Keep independently archived G0/G1/G3/G4 cells and do not describe the complete panel as wholly raw-recomputed. |
| E5 friction sensitivity | `lambda_R=0.05` reference | E4 G2 / E1 chain | Transitive historical reuse | Mark the reference and any normalization to it. Keep independently archived non-reference friction levels. |
| E6 budget-risk interaction | Reused B100/G2 and other selected source cells | E3/E4 reuse plan | Mixed: reused cells limited; newly solved cells independently verifiable | Publish cell-level `reused` and source-experiment flags. Exclude limited cells from claims of full-table raw reproducibility. |
| E7 risk-friction interaction | Reused G2/L0.05 and selected E4/E5 cells | E4/E5/E1 chain | Mixed: reused cells limited; newly solved cells independently verifiable | Preserve the reuse plan and timing provenance; mark inherited cells and retain independent cells. |

## Figure and statistic rules

1. A figure may retain an affected baseline point only if the caption identifies
   it as `HISTORICAL_SUMMARY_ONLY` or inherited from such a source.
2. Lines, differences, normalized values, or interaction effects calculated
   from an affected reference must carry the same limitation.
3. Runtime copied from a reuse source is not a new execution time.
4. Independent non-reference cells must not be deleted merely because another
   cell in the panel is source-limited.
5. No E2-E7 output is promoted solely because its value agrees with a later
   development crosscheck.

## Main-text treatment

Main-text conclusions may use independently archived non-reuse cells. Claims
that require the exact E1a baseline lineage should be moved to a limitation or
supplementary note unless the affected cell is removed. Tables should expose
`reused`, `reuse_source_run`, and evidence-level columns wherever available.
