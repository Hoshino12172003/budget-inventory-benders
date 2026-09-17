# E1c Pure Benders mechanism audit

## Decision

`PURE_BENDERS_MECHANISM_AUDIT_PASS`

This audit uses only frozen E1a/E1b artifacts and the user-supplied,
development-only `E1c_development_probe_v1.zip` (SHA-256
`55e225f26df4ce0020f42b167380cbf12bacc6437f74bee02c66c755a683493d`). No
optimization was invoked. The development probes are not paper-final
observations.

The primary computational verdict is
`PRB_SCALABILITY_ADVANTAGE_NOT_SUPPORTED`. Pure Benders is exact on every
available comparison, and its measured core time is lower than PRB at the
empirical, L, and XL-low scales. This does not remove PRB's structural value;
it says that the tested implementation and Gamma=2 regime do not provide
evidence of a PRB runtime or scaling advantage.

## 1. Exactness and objective consistency

The frozen tolerance is \(10^{-4}\).

| Case | Pure | PRB | Direct | max absolute difference | Result |
|---|---:|---:|---:|---:|---|
| 210129 | 851260.2478325499 | 851260.2478325500 | 851260.2478325500 | 1.16e-10 | PASS |
| 210202 | 1058780.7942496866 | 1058780.7942496866 | 1058780.7942496864 | 2.33e-10 | PASS |
| 210310 | 714814.5477077000 | 714814.5477077012 | 714814.5477075904 | 1.10e-7 | PASS |
| 210323 | 627147.2289325034 | 627147.2289325014 | 627147.2289325034 | 1.98e-9 | PASS |
| 210330 | 657659.5492540544 | 657659.5492546142 | 657659.5492540546 | 5.60e-7 | PASS |
| 210428 | 793717.3880816710 | 793717.3880816748 | 793717.3880816699 | 3.84e-9 | PASS |
| 210611 | 617415.6681423270 | 617415.6681421611 | 617415.6681422364 | 1.66e-7 | PASS |
| 210628 | 676700.8373030793 | 676700.8373031134 | 676700.8373030961 | 3.41e-8 | PASS |

All 24 empirical method artifacts report `OPTIMAL` with their method-specific
exact certification. Hence `EMPIRICAL_OBJECTIVE_CONSISTENCY_PASS`.

For L, Pure, PRB, Aggregate, and Direct objectives are respectively
2537677.6592963980, 2537677.6592963985, 2537677.6592963985, and
2537677.6592957140; the maximum difference is 6.84e-7. For XL-low, Pure, PRB,
and Aggregate are 3410117.8260541093, 3410117.8260549353, and
3410117.8260548680; the maximum difference is 8.26e-7. XL-low Direct is
`NOT_AVAILABLE` because its development run ended with `RESOURCE_STOP` before
an objective was produced. All available L/XL-low solutions are `OPTIMAL` and
exact-certified. The development schema did not persist LB, UB, or gap, so
those fields are `NOT_RECORDED`, not inferred. Hence
`E1C_OBJECTIVE_CONSISTENCY_PASS`.

## 2. Decision equivalence

Pure and PRB have identical active-depot vectors in all eight empirical cases
and both development instances. Using 1e-5 as the material coordinate
tolerance:

- six empirical cases are `EXACT_DECISION_IDENTITY`;
- 210323 and 210330 are `NUMERICAL_EQUIVALENCE` (maximum x differences
  2.62e-8 and 4.63e-6);
- L is `EXACT_DECISION_IDENTITY` (maximum x difference 2.16e-12);
- XL-low is `NUMERICAL_EQUIVALENCE` (maximum x difference 4.40e-8);
- no comparison is `DIFFERENT_BUT_OBJECTIVE_EQUIVALENT` or `MISMATCH`.

The same classifications hold after checking \(a^+\) and \(a^-\). First-stage
spending, active-depot count, total inventory, RI, and reconfiguration cost
are identical up to numerical noise. The largest empirical first-stage
spending difference is 1.31e-9; the largest empirical RI difference is
1.12e-12. The development result schema does not persist RI, RS, total
inventory, or active-depot summaries, but their saved full decisions match at
the stated tolerance. No claim about a distinct optimal face is needed.

## 3. Static exactness and structure-leakage audit

The E1b and E1c runners call the same
`robust_inventory_reconfiguration.pure_benders.solve_pure_benders` function.
Its master contains \(y,x,a^+,a^-\) and one \(\theta\). Its adversary is one
global MILP containing every binary \(z_{rj}\) and the single coupling row
\(\sum_{r,j}z_{rj}\le\Gamma\). It dualizes the all-product recourse LP, uses
exact bounded linearizations for \(z\pi\) and \(z\kappa\), and returns the
aggregate supporting cut

\[
\theta \ge \alpha^k + \sum_{i,j}\mu^k_{ij}x_{ij},\qquad
\alpha^k=Q^R(x^k)-\sum_{i,j}\mu^k_{ij}x^k_{ij}.
\]

Each adversarial result is independently checked with an all-product primal
fixed-scenario LP. Convergence requires no violated cut and the frozen gap
contract; the returned incumbent is then evaluated again by the same exact
global oracle. The module imports only the instance, reconfiguration solution,
and solver-profile helpers. It does not import or call product-risk
subproblems, Gamma-allocation DP, PRB utilities, structured tables, PRB cuts,
or PRB history. `PURE_BENDERS_STRUCTURE_LEAKAGE = false`.

## 4. Timing mechanism audit

All times below are comparable \(T_{core}\): construction through exact
certification, excluding reporting.

| Scale | Method | T_core s | master s | oracle/subproblem s | certification s | residual/unallocated s | iterations | cuts |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 210202 | Pure | 0.418597 | 0.069732 | 0.216630 | 0.066233 | 0.066003 | 9 | 8 |
| 210202 | PRB | 1.233368 | 0.040858 | 0.500456 | 0.099046 | 0.593008 | 4 | 31 |
| L | Pure | 0.758535 | 0.098650 | 0.223909 | 0.265405 | 0.170571 | 7 | 6 |
| L | PRB | 22.586866 | 0.091280 | 11.597027 | 1.717284 | 9.181274 | 6 | 48 |
| XL-low | Pure | 1.752701 | 0.263414 | 0.459209 | 0.693413 | 0.336666 | 12 | 11 |
| XL-low | PRB | 65.093776 | 0.124759 | 33.395608 | 5.035497 | 26.537913 | 6 | 60 |

Pure made one global adversarial MILP call per iteration plus one final call:
10 calls at 210202 (mean optimizer time 0.021663 s), 8 at L (0.027989 s), and
13 at XL-low (0.035324 s). Master means are 0.007748, 0.014093, and 0.021951
seconds per iteration. Cut-construction time and presolve/node statistics were
not recorded separately.

For PRB, saved product-subproblem evaluation counts are available for the
empirical run (120 at 210202) but are not recorded in the development ZIP.
Gamma-allocation DP and cut construction are not separately timed. Therefore
the residual is an inclusive remainder covering construction, Python
orchestration, extraction, composition, cut handling, and convergence checks;
it must not be labelled entirely as DP or Python time.

## 5. Mechanism evidence ratings

| Proposed mechanism | Rating | Evidence |
|---|---|---|
| Pure master is smaller | SUPPORTED | Pure has one theta; PRB adds product-budget surrogates and allocation rows. |
| Pure generates fewer cuts | SUPPORTED | 6-11 Pure cuts versus 31-60 PRB cuts in the audited runs. |
| Global adversarial MILP is easier than expected | PARTIALLY SUPPORTED | Observed optimizer time is small through XL-low, but presolve and node evidence were not saved. |
| PRB product enumeration is expensive | SUPPORTED | Structured subproblem time grows from 0.50 s at 210202 to 33.40 s at XL-low and dominates Pure's global-oracle time. |
| Gamma-allocation DP overhead is high | UNKNOWN | No separate DP timer exists. |
| Python orchestration overhead is high | PARTIALLY SUPPORTED | PRB residual grows to 26.54 s, but it combines several uninstrumented components. |
| Presolve fixes most z | UNKNOWN | Presolved size and fixed-variable counts are not recorded. |
| Gamma is small relative to RJ | PARTIALLY SUPPORTED | Ratios are 2/96, 2/288, and 2/420; causal impact on runtime is not isolated. |

## 6. Scaling comparison

The empirical anchor is the geometric mean across the eight Renault cases:
Pure 0.382660 s, PRB 1.257744 s, Aggregate 1.559767 s, and Direct 2.798851 s.
From empirical to L, growth factors are 1.98, 17.96, 17.38, and 38.19.
From L to XL-low, Pure grows 2.31x, PRB 2.88x, and Aggregate 3.27x; Direct is
not available. PRB/Pure rises from 3.29x at the empirical anchor to 29.78x at
L and 37.14x at XL-low. Thus Pure's observed advantage does not shrink over
the tested range.

These are two deterministic development scales, not a formal scaling sample.
They support a negative conclusion about a demonstrated PRB advantage, not a
universal theorem that Pure always scales better.

## 7. Historical reconciliation

The closest recoverable old experiment used case 210202 with the old formal-v6
dataset/model, Gamma=2, adaptive precision, core-point strengthening, and old
convergence machinery. It reached the 1800.1849 s limit after 2154 cuts with
gap 0.000327302; 84.53% of runtime was master time and 14.15% robust-subproblem
time. The current Pure method uses a new dataset/model, fixed exact profile,
unstrengthened aggregate cuts, and 6-11 cuts in the audited runs. Therefore the
historical and current runtimes are `NOT_DIRECTLY_COMPARABLE`. The old result
motivates the ablation but cannot be used as a current runtime estimate.

## 8. Paper-story recommendation

Report Pure Benders as a serious exact baseline, not as a deliberately weak
foil. Preserve PRB's contribution as a transparent product/risk-budget
decomposition and as an exact structured method, while stating that its
current implementation did not yield a computational or scalability advantage
at Gamma=2 on the audited instances. Aggregate Benders with a structured oracle
helps attribute the observed cost: it is slower than both Pure and PRB at L and
XL-low. Any stronger scaling claim requires a separately frozen formal design
with multiple replicates and, if mechanism attribution matters, finer timers
for DP, construction, cut handling, presolve, and nodes.

`formal optimization runs during this audit = 0`

`development optimization runs during this audit = 0`
