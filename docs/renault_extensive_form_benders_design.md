# Renault extensive-form Benders design audit

## Decision

**GO**, under one explicit interpretation: the prohibition on product-risk-budget
decomposition applies to the PRB algorithm (separate product subproblems and
product cuts), not to the algebraic product-pattern structure already present in
the repository's frozen Direct deterministic equivalent.  A prohibition on that
structure would conflict with the requirement to derive EF-BD from the existing
Direct model.

The literal global-scenario model is not the frozen Direct implementation.  For a
Renault case it would replicate an all-product recourse block for all 4,657
global scenarios, producing about 7,190,784 variables and 1,043,424 constraints.
That alternative is neither the existing Direct model nor a prudent 4 GiB
development baseline.

## A. What EF-BD decomposes from Direct

The frozen Direct solver uses `build_exact_reconfiguration_model`.  EF-BD keeps
its complete continuous recourse block in one model: every product/local-budget
scenario block, every product epigraph constraint, the global risk-allocation
constraints, and the recourse epigraph.  It removes the first-stage binary and
inventory decisions from that model.  The standard master retains `y`, `x`,
reconfiguration variables and one global `theta`.

For fixed inventory x, the monolithic LP value is Q(x).  If pi denotes the dual
multipliers of all supply rows whose right-hand side is x_ij, then

    beta_ij = sum_s pi_ijs
    alpha = Q(xbar) - sum_ij beta_ij xbar_ij
    theta >= alpha + sum_ij beta_ij x_ij

is a supporting cut.  Gurobi's LP dual signs give beta <= 0 for the `<= x_ij`
supply rows.  Each returned cut is checked by reduced-cost dual feasibility and
the full primal-dual objective residual.  An independent full global-scenario
enumeration certifies the final solution.

## B. Difference from Basic-BD

Basic-BD reuses one small all-product recourse LP and calls the optimizer once
for each of 4,657 global scenarios at every Oracle invocation.  EF-BD makes one
optimizer call per invocation on the complete Direct recourse LP.  For the
Renault dimensions the Direct model audit records about 122,376 variables and
18,629 constraints.  Thus EF-BD trades thousands of small solves for one much
larger cached LP; it is not a rename of Basic-BD.

## C. Algorithm boundary

- Not Pure/Global-BD: no compact adversarial mixed-integer Oracle.
- Not Aggregate-BD or PRB-BD: no separate product Oracle calls, no algorithmic
  risk-budget composition, and no product cuts.
- Not SG-BD: no bound-based pruning; every Direct recourse block remains active.
- Single global theta and at most one aggregate optimality cut per iteration.

## D. Cost of literal enumeration

The Renault uncertainty set has 1 + 96 + C(96,2) = 4,657 global scenarios.
Basic-BD therefore performs 4,657 LP optimizations per Oracle call.  Its archived
eight-case mean is 7.875 Benders iterations and 11.289 seconds of Oracle time.
The literal one-model global-scenario alternative would have roughly 7.19
million variables and 1.04 million constraints, before considering nonzeros and
solver work arrays.  Those figures are algebraic estimates, not measured memory.

## E. Standard implementation choice

The selected implementation is the standard L-shaped separation of the actual
Direct deterministic equivalent: one persistent monolithic recourse LP, right-
hand-side updates, solver-native basis reuse, and one aggregate cut.  It adds no
screening, warm-start information from historical solutions, or strengthened
cuts.  Its performance is an empirical question rather than an acceptance
criterion.

## Correctness gates

1. Micro fixed-x recourse agrees with complete global enumeration.
2. Micro EF-BD, Basic-BD and literal Direct objectives agree.
3. Every cut passes dual feasibility and strong-duality checks.
4. Renault results require independent global enumeration certification and
   frozen instance hashes.
5. Any identity, numerical, resource-monitor, worker, or archive failure closes
   the batch.
