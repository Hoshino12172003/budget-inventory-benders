# Renault SG-BD Oracle-only diagnostic

## Scope and identity

The authorized diagnostic completed all 16 frozen conditions: eight Renault cases at the persisted final EB-BD first-stage solution and the frozen real `x0`. Each available point was evaluated with cold and historical-pattern starts. No full SG-BD run or scaling optimization was executed.

The EB trajectory artifacts do not contain first-stage matrices for early or middle iterations. Those requested point classes are therefore recorded as `NOT_AVAILABLE`; `x0` is an additional real legal point and is not presented as an early iterate.

## Results

| Point | Start | Pairs | Mean pruning | Mean EB seconds | Mean SG seconds | Geometric speedup |
|---|---:|---:|---:|---:|---:|---:|
| final | cold | 8 | 99.9141% | 0.910983 | 0.006385 | 147.93x |
| final | historical_warm | 8 | 99.9356% | 0.910983 | 0.005321 | 175.79x |
| x0 | cold | 8 | 99.9571% | 0.921994 | 0.004570 | 200.28x |
| x0 | historical_warm | 8 | 99.9785% | 0.921994 | 0.005243 | 181.56x |

All 32 available comparisons passed objective equivalence, dual feasibility, strong-duality, and cut-anchor checks at the frozen tolerances. Full EB enumeration solved 4,657 LPs per point; SG solved only the unresolved leaves after safe upper-bound pruning. Detailed counts and timings are in `oracle_point_results.csv`.

## Decision

**NO_GO_FOR_FULL_SG_BD_YET — insufficient representative trajectory evidence.** The measured final and `x0` points show substantial exact Oracle acceleration, and bound/tree overhead does not erase it. However, the predeclared gate requires stable acceleration on real early and middle EB-BD iterates. Those decisions were not persisted, so this diagnostic cannot establish that condition without inventing or substituting data. A separately authorized trajectory-capture experiment is the minimum next step.
