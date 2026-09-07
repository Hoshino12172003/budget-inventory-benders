# Formal experiment metric definitions

Only metrics supported by the current model and frozen post-solve evaluator are eligible. Legacy `T`, fulfillment-flexibility, and old worst-region-shortage definitions are excluded.

| Metric | Definition | Unit | Source and aggregation | Role | Edge cases |
|---|---|---|---|---|---|
| Total objective | `C_FS + Q^R(x)` | cost units | Solver objective; one value per run | Optimization objective | Must equal certified components within tolerance |
| First-stage cost | `sum_i f_i y_i + sum_ij h_ij x_ij + R(x;x0)` | cost units | Master solution; system total | Objective and financial budget | Must not exceed the same run's `B` |
| Depot fixed cost | `sum_i f_i y_i` | cost units | Master `y`; system total | Objective component | Zero only if no depot is active |
| Inventory cost | `sum_ij h_ij x_ij` | cost units | Master `x`; system total | Objective component | Numerical values in `[-tau,0)` are treated only as solver noise |
| Reconfiguration cost | `R=lambda_R sum_ij h_ij(a_plus_ij+a_minus_ij)` | cost units | Master adjustment variables; system total | Objective and budget component | At `lambda_R=0`, cost is zero regardless of movement |
| RI | `sum_ij(a_plus_ij+a_minus_ij) / sum_ij x0_ij` | dimensionless | Final adjustments; system total, with optional product/depot breakdown using the same denominator convention | Reporting | `sum x0` must be positive or the run is invalid. At zero friction, reporting uses the canonical positive/negative parts of `x-x0`, as current solution extraction does, to avoid simultaneous unpriced adjustments |
| RS | `R/B` | dimensionless | Reconfiguration cost divided by the exact master financial budget used in that run | Reporting | `B` must be positive; infeasible or missing `B` is invalid, not zero |
| Robust recourse cost | `Q^R(x)=max_{z:sum z<=Gamma} Q(x,z)` | cost units | Frozen exact fixed-inventory evaluator; system worst case | Objective component and certification | Must match PRB final certification |
| Robust minimum fill rate | `min_{z:sum z<=Gamma} min_r [1-sum_j u_rj(z)/sum_j d_rj(z)]` | fraction `[0,1]` up to numerical tolerance | Frozen evaluator; products aggregated within region, then minimum over regions and scenarios | Post-evaluation only | If regional demand is zero, fill rate is 1. Ties use canonical scenario then canonical region order |
| Average fill rate in worst-service scenario | Mean across regions of their product-aggregated fill rates in the scenario selected by robust minimum fill rate | fraction | Frozen evaluator; one scenario then regional mean | Post-evaluation only | It is not the independently worst average fill rate |
| Worst region | Canonical region attaining robust minimum fill rate | identifier | Frozen evaluator | Post-evaluation only | Canonical tie rule applies |
| Worst scenario | Binary shock set associated with robust minimum fill rate | identity set | Frozen evaluator | Post-evaluation only | May differ from the scenario maximizing recourse cost |
| Total shortage in worst-service scenario | `sum_rj u_rj` in the scenario selected by robust minimum fill rate | inventory units | Frozen evaluator; system total | Post-evaluation only | It is not currently an independently maximized worst-case shortage metric |
| Service penalty cost | `sum_j service_penalty_j e_j` | cost units | Recourse variables | Objective component | Current frozen evaluator does not expose this separately; report `null` until a separately audited reporting extension exists |
| Total inventory | `sum_ij x_ij` | inventory units | Final master inventory; system total | Reporting | Never substitute capacity-weighted volume |
| Active depots | `sum_i y_i` | count | Master activation | Reporting | All Renault depots remain existing facilities |
| Runtime and phases | Wall-clock total, master, product separation, and final certification time | seconds | Solver instrumentation | Diagnostic/performance | Direct-inapplicable phase fields are explicit `null` |
| Iterations and cuts | PRB master solves and unique product optimality cuts | count | PRB instrumentation | Diagnostic/performance | Direct fields are explicit `null` |
| Optimality gap | Certified relative gap | fraction | Solver/PRB bound accounting | Certification | A missing certified bound is `null`, not zero |
| Peak memory | Maximum reliable process memory | GB | External process-level recorder | Diagnostic/performance | `null` until reliable capture is implemented; never estimate it as a measured result |

Product- and depot-level RI breakdowns are optional supplementary columns, not replacements for the system RI. The denominator is positive for both formal nominal baselines, 210202 and 210628.
