# Direct scaling static resource audit

## Decision

The Direct factorized deterministic equivalent has essentially the same scenario-block variable order as the measured structured oracle, but additionally keeps first-stage and risk-composition rows in one model. This supports a conservative static eligibility decision; it is not a Direct peak-memory measurement.

| Scale | Variables | Binary variables | Constraints | Scenario/product-risk blocks | Structured-oracle observed peak GiB | Direct build-memory estimate | Required free / process cap GiB | Current preflight | Decision |
|---|---:|---:|---:|---:|---:|---|---:|---:|---|
| L10 | 2,258,462 | 25 | 184,929 | 3,612 | 1.815 | approximately 1.82 GiB plus Direct coupling overhead | 7 / 4 | about 12.27 GiB | 10/10 STATICALLY_ELIGIBLE |
| XL10 | 6,075,177 | 30 | 405,479 | 6,524 | 4.860 | approximately 4.87 GiB plus Direct coupling overhead | 10 / 7 | about 12.27 GiB | 10/10 STATICALLY_ELIGIBLE |
| XXL10 | 14,227,589 | 36 | 791,070 | 10,672 | 10.815 | approximately 10.82 GiB plus Direct coupling overhead | 16 / 13 | about 12.27 GiB | 0/10 RESOURCE_GATE_BLOCKED |

Variable and constraint counts come from the audited algebraic formulas in `algorithm_scaling_instance_characteristics.csv`; no Gurobi model was built. Binary variables are the depot activations. Scenario blocks are `J * sum(g=0..2, C(R,g))`. The memory proxy is the maximum formal Aggregate/PRB process-tree RSS at the same scale, because those methods construct the same product-pattern recourse blocks. It is explicitly an estimate, not a Direct observation.

Disk free space was about 246 GiB at audit time and is not the limiting resource. Model/log/result disk use cannot be calibrated exactly before a Direct build and remains `NOT_VERIFIABLE`; the runner retains an isolated output root and refuses overwrite.

At the observed preflight, L10 and XL10 clear the existing size-specific launch thresholds. XXL10 does not clear its 16-GiB threshold and must remain `RESOURCE_GATE_BLOCKED`. Current Gurobi 13.0.1 matches the environment frozen for the new Direct batch, while exact software-version pairing to Scaling V2 remains unprovable. No resource limit was enlarged.
