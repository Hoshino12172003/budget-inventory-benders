# PRB next-generation 2x2 ablation design

## Frozen algorithm matrix

The frozen original PRB-BD implementation is method A and is not modified or rerun. The three new development methods change only the two declared mechanisms:

| Method | Adaptive cut selection | Exact product-scenario screening |
|---|---:|---:|
| PRB-BD (A) | No | No |
| PRB-SG (B) | No | Yes |
| A-PRB (C) | Yes | No |
| A-PRB-SG (D) | Yes | Yes |

All methods retain the product/local-risk-budget variables `eta[j,g]`, the global `theta`, every risk-budget composition constraint, the original product cut definition, `Gamma=2`, `lambda_R=0.05`, solver profile, and numerical tolerances. None calls the Pure/Global compact robust MILP oracle. SG-BD remains an external baseline.

## Existing PRB behavior

The original implementation solves every exact local-count state `g=0,...,Gamma` for every product and adds every product cut whose violation exceeds `1e-7`. This is already violation filtering. Adaptive selection is therefore defined as selecting a strict deterministic subset of the currently violated cuts; it is not a relabeling of the existing threshold.

The earlier selective-separation V4 bound screened whole cached product states and produced zero avoided state solves on its development cases. That engineering result is preserved and is not presented as the new branch-and-bound mechanism.

## Exact product-scenario branch-and-bound

Fix product `j`, inventory vector `x_j`, and a baseline feasible shipment plan for nominal demand. For a nonnegative demand shock `delta_rj`, keep this shipment fixed and increase shortage by `delta_rj`. Demand balance and depot supply remain feasible. The service constraint can require at most an additional `SL_j * delta_rj` violation because

`delta_rj - (1-SL_j) delta_rj = SL_j delta_rj`.

Therefore the recourse cost for any product scenario `S` is bounded above by

`U_j(S) = C_j(base feasible plan) + sum_(r in S) delta_rj * (p_rj + phi_j SL_j)`.

This is a feasible-policy upper bound, so it does not require monotonicity of the optimal recourse value. For an exact local budget `g`, a branch node with selected regions and undecided suffix is bounded by the selected increments plus the largest remaining `g-|selected|` increments. A node is pruned only when this bound is no larger than an objective value obtained from an actually solved scenario LP. Historical worst patterns may be evaluated first, but are re-solved at the current `x_j`; no historical objective is reused. Every unpruned leaf is solved exactly, and the returned dual generates the unchanged product cut.

Consequently PRB-SG and A-PRB-SG return the exact worst product recourse and an exact dual cut for every `(j,g)` state. Scenario accounting requires `LP solves + safely pruned patterns = all exact-g patterns`.

## Adaptive multi-cut selection

At each iteration all product/local-budget states are still separated exactly. Violated cuts are sorted deterministically by decreasing violation, then product and local budget. The selected budget depends on:

- the number of violated cuts (`ceil(sqrt(V))` baseline);
- accumulated master cuts (a decreasing burden cap);
- iteration count (a nondecreasing progress floor);
- current global gap (all violated cuts are selected once the gap is at most `1e-3`).

At least one violated, previously unseen cut is added whenever any violation exists. Existing cuts are never removed. Termination still requires both the original relative-gap threshold and a complete exact separation with zero violated product cuts.

The recourse functions are finite polyhedral maxima. Each nonterminal iteration adds at least one new supporting hyperplane from this finite representation; a duplicate violated cut is a fail-closed error. Thus no necessary violation can be permanently omitted, the lower bound remains valid, and finite exact convergence is retained. The rule changes master growth only; it does not change theta semantics, cut coefficients, certification, or stopping tolerances.

## Historical 210330 condition

The frozen PRB development record for Renault 210330 remains ineligible for strict pairing because `global_risk_budget_coupling_pass=false` at the frozen `1e-6` threshold. New methods use the same threshold. The anomaly is not relaxed, overwritten, or converted to success.

## Stage decisions

- Product screening: **GO** after the micro exact-enumeration equality, dual-feasibility, strong-duality, and scenario-accounting tests pass.
- Adaptive selection: **GO** after deterministic-selection tests and full tiny Direct/PRB objective equality pass.
- Full Renault execution: allowed only after all three closed configs pass identity/resource dry-run and an independent authorization commit enables them.
