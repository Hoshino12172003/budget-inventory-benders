# E1a, E1b, and E1c evidence reconciliation

Status: `RECONCILED_WITH_MATERIAL_DOWNGRADE`

## Evidence policy

| Label | Meaning | Permitted paper use |
|---|---|---|
| `PRIMARY_VERIFIED` | Original formal result, identity, and certification are present and verifiable. | Confirmatory result. |
| `SECONDARY_RECOMPUTABLE` | Result can be recalculated from independent raw evidence without optimization. | Confirmatory derived statistic with source citation. |
| `HISTORICAL_SUMMARY_ONLY` | Only a historical derivative remains; the source solver result is unavailable. | Historical description only; no confirmatory performance or certification claim. |
| `DEVELOPMENT_CROSSCHECK` | Later run from another batch/environment checks a value. | Corroboration only; never a replacement for a formal run. |
| `SOURCE_MISSING` | A required source artifact is absent. | Must be disclosed; no promotion to verified evidence. |

Evidence levels are assigned from file identity, not numerical agreement.

## E1a

The eight expected PRB `result.json` files are `SOURCE_MISSING` and the eight
expected SHA-256 values have zero matches. The retained table and summary are
`HISTORICAL_SUMMARY_ONLY`. Their objective, runtime, iteration, cut, and
certification fields remain byte-traceable as derivatives but are not
independently recomputable.

Later development results match the frozen instance and x0 identities 8/8 and
reproduce the eight PRB objectives. They are `DEVELOPMENT_CROSSCHECK`: seven
pass strict certification and 210330 fails the global-risk-budget coupling
gate. Their runtimes must not be paired with the historical Direct runtimes.

Consequences:

- the historical 8/8 runtime-win count, speedups, runtime moments,
  correlations, iterations, and cut counts are removed from confirmatory use;
- the objective values may be described as independently corroborated, with
  the 7 PASS / 1 FAIL development status stated explicitly;
- the E1a table is retained only with the companion evidence table
  `table_e1_empirical_performance_evidence.csv`.

## E1b

E1b did not independently rerun PRB. Its manifest refers to the same missing
E1a files. Standard/Aggregate and Pure/Global results with recovered raw files
remain `PRIMARY_VERIFIED`. PRB cells in any E1b or Renault four-method table are
`HISTORICAL_SUMMARY_ONLY`; paired PRB timing tests are not confirmatory.

The mathematical Standard-BD definition and cut-validity evidence are not
affected. The change is solely the evidentiary status of the empirical PRB
comparison.

## E1c

The Renault empirical anchor in the Pure-versus-PRB mechanism audit inherits
the missing PRB source and is historical only. Independent controlled scaling
records retain their own evidence status. Accordingly:

- the Renault anchor cannot establish empirical PRB timing, iterations, cuts,
  or active-depot identity as a confirmatory result;
- scaling-only conclusions may be retained when supported by their own raw
  records;
- a figure or table mixing the Renault anchor and scaling observations must
  mark the Renault point as historical or omit it from confirmatory analysis.

## Revised claim boundary

The Renault evidence supports an objective-value crosscheck, not a recovered
formal PRB performance experiment. The paper may retain independently verified
Direct, Pure/Global, and Aggregate/Standard results and the independently
verified Scaling V2/XXL10 experiments. It must not claim that the original E1a
PRB batch is 8/8 source-verified or that its speed advantage is reproducible.
