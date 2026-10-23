# Scaling version and certification reconciliation

| Evidence line | Identity | Count | Permitted use |
|---|---|---:|---|
| Development scaling | `prb_large_scale_simulation_v1`, commit `ed7c66c49c000799b43f7ce75d2ca89dae9d8f42` | 87/90 certified | Historical design/mechanism evidence only |
| Final formal scaling | `ALGORITHM_SCALING_CONVERGENCE_COST_V2_REPAIRED_GUARD`, execution commit `c46d09c306deb80086a7ceab12812847c117df87` | 89 certified + 1 documented non-certified + 0 unattempted | Paper-final scaling evidence |

The development line contains Pure errors at one seed per scale. The final formal line uses the repaired cut-validity guard and complete trajectories/timings. Its only failure, XXL10 seed 20260925 Pure, reproduces the historical numerical mechanism: final objective/LB/UB agree and final solution certification passes, but one intermediate global-oracle cut has an enormous strong-duality residual. It remains a failure and is not rerun or tolerance-relaxed.

New Direct rows will use the V2 prepared-instance hashes but a separate experiment/config/code identity. Existing result `code_commit` fields remain unchanged. Until Direct execution is authorized and completed, Table 2 labels Direct as pending rather than combining development Direct observations with formal V2 statistics.
