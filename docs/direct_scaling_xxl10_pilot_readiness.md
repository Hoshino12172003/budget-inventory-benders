# XXL10 Direct single-pilot preparation

## Decision

`BLOCKED_BY_RESOURCE`

The read-only snapshot found 14.653 GiB available versus the unchanged 16-GiB startup gate. Authorization remains false and no optimization attempt was created.

## Scope and identity

- Candidate: `DIRECT_XXL10_S20260921`, next identity `attempt-001`.
- Frozen XXL10 inputs: 10/10 identity checks pass; I=36, R=36, J=16, Gamma=2.
- Historical Pure `ASC_XXL10_S20260925_PURE_BENDERS` remains non-certified and excluded from valid four-method pairing.
- L10/XL10 frozen evidence: 179/179 SHA-256 records unchanged.

## Static model size

The current model formula gives 14,227,589 variables (36 binary), 791,070 constraints, and 43,069,377 constraint-matrix nonzeros across 10,672 product-scenario blocks. These are algebraic counts, not a Gurobi build or measured memory result.

## Candidate protocol

- Method=2, Threads=2, MIPGap=0; all frozen tolerances and scientific parameters unchanged.
- 13-GiB process-tree cap, 16-GiB startup gate, 3-GiB system floor, 20-GiB disk gate, 900-second limit, 0.25-second monitoring, one process.
- Method=2 avoids automatic concurrent LP selection, but Barrier factorization and Crossover remain material root-node memory risks.
- Historical Scaling V2 software versions remain `NOT_VERIFIABLE`; exact environment identity is not claimed.

No Gurobi model construction, optimization, or historical algorithm rerun was performed.
