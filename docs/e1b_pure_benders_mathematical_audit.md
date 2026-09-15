# E1b Classical Pure Robust Benders audit

## Decision

`PURE_BENDERS_READY_FOR_AUTHORIZATION`

This baseline solves the same Reconfiguration Model V2 as Direct, the existing
structured-oracle aggregate Benders implementation, and PRB-Benders. Formal
execution is disabled. The existing E1b method is retained unchanged and is
reported henceforth as **Aggregate-cut Benders with structured exact robust
oracle**.

## Master

The master contains the unchanged first-stage variables and constraints,
including

\[
x_{ij}-x^0_{ij}=a^+_{ij}-a^-_{ij},\qquad
x_{ij}\le UB_{ij}y_i,\qquad C^{FS}\le B,
\]

and exactly one recourse surrogate \(\theta\):

\[
\min\ C^{FS}(y,x,a^+,a^-)+\theta.
\]

There are no \(\eta_{j,g}\) variables or product-budget approximations.

## One global robust adversarial subproblem

For fixed \(x\), let \(\pi_{rj}\ge0\) be the demand dual, \(\mu_{ij}\le0\)
the supply dual, and \(\kappa_j\ge0\) the negated service dual. The single
global MILP maximizes

\[
\sum_{rj}\bar d_{rj}\pi_{rj}+\sum_{ij}x_{ij}\mu_{ij}
-\sum_j(1-s_j)\left(\sum_r\bar d_{rj}\right)\kappa_j
+\sum_{rj}\hat d_{rj}z_{rj}[\pi_{rj}-(1-s_j)\kappa_j]
\]

subject to

\[
\pi_{rj}+\mu_{ij}\le c_{irj},\quad
\pi_{rj}-\kappa_j\le p_{rj},\quad
0\le\kappa_j\le q_j,
\]

\[
z_{rj}\in\{0,1\},\qquad \sum_{r,j}z_{rj}\le\Gamma.
\]

The two binary-continuous products are linearized exactly with
\(0\le\pi_{rj}\le p_{rj}+q_j\) and \(0\le\kappa_j\le q_j\). All products and
regions coexist in this one MILP. The only risk-budget constraint is the one
global cardinality row, so global Gamma coupling is retained directly rather
than reconstructed by product allocation.

The selected global scenario is independently evaluated by one all-product
recourse LP. Equality of the adversarial dual objective and that primal value
is the fixed-state strong-duality certificate.

## Aggregate cut

At iteration \(k\), the optimal global adversarial dual solution gives

\[
\theta\ge \alpha^k+\sum_{ij}\mu^k_{ij}x_{ij},
\]

where \(\alpha^k\) contains every term not multiplying \(x\). Any feasible
adversarial primal/dual selection defines an affine lower bound on the maximum
dual value, hence the cut is globally valid. Exact maximization and recourse-LP
strong duality make it tight at \(x^k\). It uses neither future solutions nor
PRB cut state.

## Termination and timing

Termination requires the frozen relative-gap rule, no violated aggregate cut,
and a final fixed-first-stage solve of the same global adversarial MILP plus its
global recourse-LP certificate. `T_core` includes master, adversarial MILP,
cut, and final certification time; artifact serialization and reporting are
excluded. The runner imposes a 900-second per-run wall-clock cap and preserves
timeout logs in an isolated timeout directory. This limit is a preregistered
resource guard, not authorization to execute.

## Structure-leakage audit

The Pure execution path is:

1. `run_e1b_pure_benders_local.py` -> `solve_pure_benders`;
2. `_build_pure_master` for the standalone master;
3. `GlobalRobustAdversarialSubproblem.solve` for global separation;
4. `evaluate_fixed_scenario_recourse_global` for certification.

Its scientific imports are limited to the instance schema, first-stage
solution record, frozen solver profile, and artifact identity utilities. It
does not import or call `ProductRiskSubproblem`, `compose_risk_budget`,
`standard_benders`, `product_risk_budget_benders`, product-risk tables, PRB
cuts, or PRB history. Static dependency tests enforce this boundary.

## Global adversarial MILP size

For \(I\) depots, \(R\) regions, and \(J\) products, the model has \(RJ\)
binary variables, \(IJ+3RJ+J\) continuous variables, and
\(IRJ+7RJ+1\) linear constraints. At the frozen \(R=12,J=8\), the eight
cases range from 480 to 544 total variables and 1,729 to 2,497 constraints.
This compact algebraic size does not itself guarantee fast convergence because
the MILP is solved once per Benders iteration, but it does not present an
up-front 31.5-GiB memory blocker.

| Case | I | Binary | Continuous | Total variables | Constraints |
|---|---:|---:|---:|---:|---:|
| 210129 | 15 | 96 | 416 | 512 | 2,113 |
| 210202 | 15 | 96 | 416 | 512 | 2,113 |
| 210310 | 16 | 96 | 424 | 520 | 2,209 |
| 210323 | 13 | 96 | 400 | 496 | 1,921 |
| 210330 | 11 | 96 | 384 | 480 | 1,729 |
| 210428 | 18 | 96 | 440 | 536 | 2,401 |
| 210611 | 19 | 96 | 448 | 544 | 2,497 |
| 210628 | 15 | 96 | 416 | 512 | 2,113 |

## Verification scope

Tiny exact tests compare Pure Benders with the literal exact benchmark at
Gamma 1 and 2. Separate tests verify global-oracle strong duality, cut
tightness and validity at multiple inventory points, the single-theta master,
the size formula, dependency absence, fail-closed authorization, namespace
isolation, and timeout/no-overwrite policy. No Renault formal optimization was
run.
