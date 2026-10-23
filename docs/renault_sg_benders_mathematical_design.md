# Scenario-Generation Single-cut Benders: mathematical design

## Scope and decision gate

SG-BD is a development-only single-cut Benders candidate for the frozen Renault cases. It keeps one global recourse variable and adds at most one global optimality cut per master iteration. It does not use product risk-budget composition, product multi-cuts, or the compact Global-BD adversarial MILP. No Renault optimization is authorized by the draft protocol.

The experimental ordering Direct > SG-BD > Aggregate-BD > PRB-BD is a hypothesis, not a design constraint or acceptance condition.

## Recourse model and the unsafe monotonicity shortcut

For fixed first-stage inventory `x` and scenario demand `d`, the recourse LP minimizes transportation, shortage, and soft-service violation costs subject to demand satisfaction, per-depot/product inventory limits, and

`sum_r u[r,j] - e[j] <= (1 - SL[j]) sum_r d[r,j]`.

It is not valid to prune by merely asserting that recourse cost is componentwise increasing in demand. Increasing demand also increases the permitted shortage on the right-hand side of the service constraint. SG-BD therefore does not use demand monotonicity.

## Feasible-policy upper bound

For fixed `x`, construct once a feasible shipment plan `q0` for nominal demand. The prototype uses a deterministic greedy plan, but optimality of that plan is unnecessary. It satisfies

- `q0 >= 0`;
- `sum_r q0[i,r,j] <= max(0,x[i,j])`;
- `sum_i q0[i,r,j] <= base_demand[r,j]`.

For any nonnegative shock pattern `z`, retain the same shipment `q0` and define

- `u_z[r,j] = d_z[r,j] - sum_i q0[i,r,j] >= 0`;
- `e_z[j] = max(0, sum_r u_z[r,j] - (1-SL[j]) sum_r d_z[r,j])`.

This is a feasible recourse solution for every descendant scenario because shocks only increase demand and do not change the inventory used by `q0`. Consequently, the optimal recourse value `Q(x,d_z)` is no larger than the cost of this policy.

Let `U0` be the exact cost of this policy at nominal demand. A shock of size `delta[r,j]` increases shortage cost by `p[r,j] delta[r,j]`. Since the positive-part map is 1-Lipschitz, its service-violation cost increases by at most `phi[j] SL[j] delta[r,j]`. Therefore

`Q(x,d_z) <= U0 + sum_(r,j) z[r,j] delta[r,j] (p[r,j] + phi[j] SL[j]) = U(z)`.

This is a strict upper bound derived from a feasible policy. It is not a heuristic estimate. The implementation fails closed unless demand, deviations, shortage penalties, and service penalties are nonnegative and service levels lie in `[0,1]`.

The zero-shipment policy is an independent fallback proof: setting `q=0`, `u=d`, and `e=SL*sum(d)` is feasible and gives the same shock coefficients with a weaker nominal constant.

## Branch upper bound and exact separation

The global cardinality set contains all shock subsets of size at most `Gamma`. At a tree node with selected shocks `A`, unprocessed components `C`, and remaining budget `k`,

`UB(A,C,k) = U(A) + sum of the k largest positive shock coefficients in C`.

Every descendant pattern has at most `k` additional shocks, so its feasible-policy bound is at most this node bound. If the node bound does not exceed the best exactly evaluated recourse value, the complete node is safely pruned. Otherwise SG-BD branches. At an unresolved leaf it solves the exact recourse LP. A previous worst pattern may be evaluated first at the current `x`; its value is a valid incumbent only after that current-`x` evaluation.

When traversal ends, every scenario has either been exactly evaluated or excluded by an upper bound no smaller than its optimal recourse value. The largest evaluated recourse value is therefore the exact global maximum. Its LP dual produces the same single global Benders cut used by the existing single-theta master.

## Pseudocode

1. Build one nominal feasible shipment plan for the current first-stage `x`.
2. Compute `U0` and every additive shock coefficient.
3. Exactly evaluate the previous worst pattern at the current `x` to initialize the incumbent.
4. Traverse the cardinality-constrained scenario tree in descending bound weight.
5. Prune a node only when its strict upper bound is no greater than the incumbent.
6. Solve an exact recourse LP for every unresolved leaf and update the incumbent.
7. Return the exact worst scenario and its dual cut; add at most that one cut.
8. Independently certify the final solution by full enumeration before accepting a development result.

## Complexity and risks

For `n=R*J` and integer `Gamma`, full enumeration requires `S=sum(g=0..Gamma) C(n,g)` LP solves per oracle call. Renault has `n=96`, `Gamma=2`, and `S=4,657`. SG-BD still has worst-case `S` LP solves: a safe bound can fail to prune. Bound construction costs `O(J I R log(IR))`; tree bound work is small for fixed `Gamma`, and each node uses only pre-sorted coefficients.

The static screen at the already-certified final EB-BD solutions is deliberately optimistic because it uses the certified worst recourse value as the incumbent. It shows bound potential, not actual runtime. Early master iterates may have a weaker historical candidate, and Python traversal plus LP state changes may dominate when pruning is limited. These questions require the separately authorized Oracle-only diagnostic.

## Independence from existing methods

- **Global-BD/Pure:** uses a compact adversarial dual MILP. SG-BD does not import or invoke it; SG-BD traverses explicit global scenarios and solves primal recourse LPs only when bounds cannot exclude them.
- **Aggregate-BD:** composes product-level structured Oracle values under the global budget and emits one aggregate cut. SG-BD performs no product risk-budget composition.
- **PRB-BD:** uses product/local-budget structure and multiple cuts. SG-BD retains one global theta and at most one cut per iteration.

## Current decision

**GO for an Oracle-only diagnostic, not for the full eight-case Benders run.** The proof is valid under checked frozen-data assumptions, the prototype matches exhaustive separation on a non-optimization micro model, and the read-only final-solution screen indicates material pruning potential. Full SG-BD development remains gated on an authorized Oracle-only comparison that measures exact LP counts, upper-bound cost, and total Oracle time without using the certified answer as an unavailable runtime shortcut.
