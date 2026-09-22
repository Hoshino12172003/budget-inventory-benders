# PRB original motivation audit

## Finding

PRB was introduced in commit `c6be0bcc4a19c7f05d6fec8ccb2ac2011aeb2764` as an exact implementation of the product separability of recourse and the global cardinality-budget composition. The contemporaneous document explicitly calls it a **correctness implementation, not a performance experiment**. Its stated construction replaces 4,657 global Gamma=2 scenarios for the Renault dimensions with 79 local patterns per product and 45 admissible risk allocations. This establishes the mathematical and representation motivation, but it is not historical evidence that the global adversarial oracle was slow.

The historical artifact closest to an observed computational motivation is older and belongs to a different model and algorithm lineage. Old commit `b78f6c976984ba22602902ed325eb1442d572ba4`, later summarized by `0dd11cc5ffe6230eb865d48a31bd68982062ecec`, records a 210202 Gamma=2 adaptive/core-point Benders run that reached 1,800.1849 seconds with 2,154 cuts and remained uncertified. Its accounting assigns 1,521.66 seconds (84.53%) to the master and 254.81 seconds (14.15%) to the robust subproblem. That artifact supports a historical concern about aggregate-master growth, cut accumulation, and lower-bound convergence. It does not directly validate the performance of the later PRB implementation because the dataset, first-stage model, precision policy, strengthening, and convergence machinery differ.

## What was fact and what was hypothesis

| Candidate difficulty | Status at PRB introduction | Evidence |
|---|---|---|
| Exact product separability | FACT | The recourse identity and product-local subproblems are derived and tested in PR #6. |
| Global Gamma coupling can be composed from local budgets | FACT | Exact composition and exhaustive tiny checks were part of PR #6. |
| Avoiding explicit global scenario construction | FACT about representation | The Renault dimensions have 4,657 global scenarios, while the implementation uses 79 local patterns per product and 45 allocations. |
| Global worst-case oracle is computationally hard | DESIGN HYPOTHESIS | PR #6 contains no performance experiment and no historical oracle-time attribution supporting this claim. |
| Aggregate master may be weak | HISTORICALLY PLAUSIBLE, not isolated for PRB | The old 2,154-cut run was master-dominated, but it is not algorithmically identical to the current methods. |
| Product cuts improve current lower-bound refinement | UNTESTED AT INTRODUCTION | PR #6 tested correctness, not an aggregate-master ablation. |
| Product coupling itself is the bottleneck | NOT ESTABLISHED | Coupling is only through the global risk budget; no contemporaneous runtime decomposition isolates it. |

The later empirical, L/XL-low, and J-only results are used in the separate validation document. They are not back-projected into the original motivation.

## Historical lineage boundary

The recoverable 1,800-second artifact used a global dual MILP and one aggregate cut per iteration, but also adaptive gaps and core-point strengthening. It is not the current Pure Benders baseline. The often-recalled “4,000+ seconds versus 1+ second” comparison was not recovered as an exact Renault Pure-Benders/CCG pair; archived 4,000-second records belong to other historical diagnostic/fairness paths. They must not be cited as PRB-origin evidence.

## Three mechanisms used in the present audit

1. **Pure Benders**: aggregate master plus one global worst-case adversarial subproblem.
2. **Aggregate Benders + structured oracle**: aggregate master plus product-level risk subproblems and exact Gamma composition.
3. **PRB**: product-level master/cuts plus the same structured product-risk oracle.

Pure versus Aggregate-Structured isolates oracle decomposition. Aggregate-Structured versus PRB isolates master/cut granularity. Pure versus PRB is only the combined algorithm comparison.

