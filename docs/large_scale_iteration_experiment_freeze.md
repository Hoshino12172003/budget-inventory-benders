# Large-scale iteration experiment freeze

## Frozen design

- Dataset construction: Renault-calibrated controlled simulation
- Scales:
  - `L10`: `I=25`, `R=24`, `J=12`
  - `XL10`: `I=30`, `R=30`, `J=14`
  - `XXL10`: `I=36`, `R=36`, `J=16`
- Seeds: `20260921` through `20260930` at every scale
- Prepared instances: 30
- Methods: Pure Benders, Aggregate Benders with structured exact oracle, and PRB-Benders
- Algorithm observations: 90 (30 per method)
- Exact-certified observations: 87
- Certified Pure-PRB pairs with objective agreement within the frozen tolerance: 27
- Certified Aggregate-PRB pairs with objective agreement within the frozen tolerance: 30

Three Pure Benders runs remain non-certified/error observations. They are retained transparently in the completeness and run-level audit artifacts; they are not rerun, removed, or converted into certified observations.

## Frozen iteration results

| Scale | Certified Pure-PRB pairs | Pure median iterations | PRB median iterations |
|---|---:|---:|---:|
| L10 | 9 | 13 | 6 |
| XL10 | 9 | 12 | 6 |
| XXL10 | 9 | 14 | 6 |
| Pooled | 27 | 13 | 6 |

- Median pooled PRB/Pure iteration ratio: `0.444`
- Median pooled iteration reduction: `55.6%`
- PRB has fewer iterations in `27/27` certified Pure-PRB pairs.
- PRB has fewer iterations in `30/30` certified Aggregate-PRB pairs.

Pure Benders is frozen as an iteration-mechanism baseline. The main-text Pure-PRB comparison concerns Benders iteration counts, not wall-clock superiority. Raw timing fields remain preserved in the run-level and group-level audit artifacts.

## Frozen artifacts

- `experiments/results/prb_large_scale_simulation_v1/simulation_run_table.csv`
- `experiments/results/prb_large_scale_simulation_v1/simulation_group_summary.csv`
- `experiments/results/prb_large_scale_simulation_v1/simulation_paired_comparisons.csv`
- `experiments/results/prb_large_scale_simulation_v1/simulation_completeness_table.csv`
- `artifacts/table_pure_vs_prb_iterations_paper.csv`
- `artifacts/table_aggregate_vs_prb_iterations_paper.csv`
- `artifacts/fig_pure_vs_prb_iterations.png`
- `artifacts/fig_pure_vs_prb_iterations.pdf`
- `docs/large_scale_iteration_mechanism_final.md`

Frozen result and paper-output source commit: `ed7c66c49c000799b43f7ce75d2ca89dae9d8f42`.

## Authorization closure

No further optimization is authorized for this experiment. In particular, no Pure, Aggregate, or PRB reruns and no `40x40x16` stress test are authorized as part of this freeze.
