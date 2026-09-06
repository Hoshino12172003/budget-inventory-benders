# Direct versus PRB formulation identity audit

The static audit passes the first-stage feasible region, `x0`, reconfiguration cost, budget, Gamma semantics, demand uncertainty, recourse variables, service penalty, all cost coefficients, and integrality assumptions. Both methods solve Reconfiguration Model V2; Direct is the factorized exact product-pattern extensive formulation.

The audit is currently **BLOCKED** because solver tolerances are not identical:

| Component | MIP gap | Feasibility | Optimality | Integrality |
|---|---:|---:|---:|---:|
| Direct exact | 0 | `1e-8` | `1e-8` | `1e-8` |
| PRB master | 0 | `1e-9` | `1e-9` | `1e-9` |
| Product LP | NA | `1e-9` | `1e-9` | NA |

No tolerance was changed here because this task prohibits changes to the frozen solver implementation. A later correctness-preserving PR must approve and apply one shared profile before E1 can run.
