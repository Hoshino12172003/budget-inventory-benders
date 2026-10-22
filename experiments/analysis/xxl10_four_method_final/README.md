# XXL10 four-method final archive

This directory is the reproducible paper-analysis layer for the ten frozen XXL10 seeds (`20260921`–`20260930`) and four methods: Direct, EF-BD, Aggregate-BD, and PRB-BD.

The 40-row CSV and Excel workbook are regenerated from the archived raw result files by:

```powershell
python scripts\build_xxl10_four_method_final_archive.py
$env:NODE_PATH='C:\Users\Hu Jiaxin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
& 'C:\Users\Hu Jiaxin\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' scripts\build_xxl10_four_method_workbook.mjs
python scripts\plot_xxl10_four_method_final.py
python scripts\build_xxl10_four_method_final_archive.py
```

The second Python invocation refreshes the integrity audit after the workbook and figures exist. No command above builds or solves an optimization model.

## Interpretation rules

- Direct is exact-certified on 3/10 seeds. Its seven limited runs remain in the ten-seed denominator and are not included in ordinary exact-pair speedups.
- The original seed-20260922 batch report remains unchanged at `STOPPED_INTEGRITY_FAILURE`. The separate recovery audit records the evidence-backed post-hoc classification `TIME_LIMIT_NO_INCUMBENT`.
- Seed 20260927 is an outer-monitor hard timeout with Worker return code 15. No objective, bound, gap, or final solver status is inferred.
- EF-BD, Aggregate-BD, and PRB-BD are exact-certified on all ten seeds.
- Direct and EF-BD provenance records Python 3.12.7 and Gurobi 13.0.1. The historical Scaling V2 solver version for Aggregate-BD and PRB-BD remains not fully verifiable.
- Timing comparisons across historical batches are descriptive rather than synchronized benchmarking.

The source manifest records SHA-256 and byte size for every raw file used. The integrity audit records the analysis-file hashes and reports `optimization_calls=0`.
