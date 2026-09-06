# Reconfiguration correctness protocol

This stage freezes model correctness and supplies ground truth; it is not a
formal performance experiment. The frozen cases, baselines, budget references,
and friction levels are unchanged.

The grid contains both Renault cases, \(\Gamma\in\{0,1,2\}\),
\(\beta\in\{0.90,1.00,1.10\}\), and
\(\lambda_R\in\{0,0.0025,0.05,0.20\}\): 72 combinations. Every run uses the
finite exact factorized extensive form. This form shares each product-pattern
recourse block across global scenarios but enforces every integer product
risk-budget allocation. It is algebraically identical to duplicating a full
recourse block for all 4,657 global \(\Gamma=2\) scenarios, while avoiding about
6.7 million shipment variables. This is an extensive-form compression, not
Benders.

Every run records solver status, objective, bound, MIP gap, runtime, node count,
scenario count, matrix size, accounting components, and reconfiguration
diagnostics. Solver peak memory is not exposed by the API and is reported as
unavailable rather than estimated.

The following audits pass at tolerance \(10^{-6}\):

- first-stage and objective accounting;
- reconfiguration identity and complementarity at positive friction;
- zero-friction equivalence on all 18 case/Gamma/beta settings;
- nominal incumbent recovery for every positive frozen friction level;
- robust-objective nesting in \(\Gamma\);
- feasibility and objective nesting as the budget is relaxed;
- direct global-scenario recourse versus the factorized exact value.

All 72 runs are optimal with zero reported time, memory, infeasibility, or error
classifications. Two small RI increases remain: 210202 at
\((\Gamma,\beta)=(2,0.9)\), 0.222348 to 0.227523 between friction 0.05 and 0.20;
and 210628 at \((0,0.9)\), 0.324853 to 0.326865 between 0.0025 and 0.05. Their
activation-change counts do not change. They are budget-driven inventory
substitutions, not uncertainty nesting or solver-status failures; RI monotonicity
is not imposed as a model constraint.

## Exact service reporting

For each certified first-stage solution, all feasible global scenarios are
evaluated. Product-pattern recourse LPs are solved once and cached. Primary
recourse cost is minimized exactly; among cost-optimal solutions, a strictly
convex shortage norm selects a unique shortage vector for reporting. For each
scenario and region,

\[
FR_{r,s}=1-\frac{\sum_j u_{rj,s}}{\sum_j d_{rj,s}}.
\]

When the denominator is zero, fill rate is defined as one. The reported identity
uses the lowest fill rate, then canonical region-major scenario order, then
canonical region order. The average is the arithmetic mean of regional fill
rates in that selected worst-service scenario. This evaluation does not use an
arbitrary active extensive-form block.

The future algorithm acceptance tolerances are frozen in
`artifacts/exact_benchmark_contract.json`.
