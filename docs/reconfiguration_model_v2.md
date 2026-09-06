# Reconfiguration Model V2

## First stage

For every existing depot \(i\) and selected product \(j\),

\[
y_i\in\{0,1\},\quad x_{ij}\ge0,\quad a^+_{ij},a^-_{ij}\ge0,
\]

\[
x_{ij}-x^0_{ij}=a^+_{ij}-a^-_{ij},
\quad x_{ij}\le UB_{ij}y_i,
\quad \sum_jv_jx_{ij}\le C_i y_i.
\]

Here \(y_i=1\) means that an existing depot is operated during the planning
horizon. The fixed charge \(f_i\) is a planning-period activation or operating
cost, not a construction cost. If \(y_i=0\), final inventory is zero and any
positive incumbent stock is withdrawn through \(a^-\).

For calibrated friction \(\lambda_R\ge0\),

\[
R(x;x^0)=\lambda_R\sum_{i,j}h_{ij}(a^+_{ij}+a^-_{ij}),
\]

\[
C^{FS}=\sum_i f_i y_i+\sum_{i,j}h_{ij}x_{ij}+R(x;x^0),
\qquad C^{FS}\le B,
\qquad \beta=B/B_{ref}.
\]

The three controls are distinct: \(\beta\) controls financial tightness,
\(\lambda_R\) controls reconfiguration friction, and \(\Gamma\) controls the
uncertainty budget.

## Recourse and uncertainty

For scenario \(z\),

\[
d_{rj}=\bar d_{rj}+\hat d_{rj}z_{rj},\quad
z_{rj}\in\{0,1\},\quad \sum_{r,j}z_{rj}\le\Gamma.
\]

The shock unit is one region-product pair. Multiple regions of the same product
may be shocked. The unchanged recourse LP is

\[
\sum_iq_{irj}+u_{rj}\ge d_{rj},\qquad
\sum_rq_{irj}\le x_{ij},
\]

\[
\sum_ru_{rj}-e_j\le(1-SL_j)\sum_rd_{rj},
\]

with nonnegative \(q,u,e\), and transport, shortage, and service-violation
costs. The exact robust model minimizes

\[
C^{FS}+\theta,\qquad \theta\ge Q(x,z)
\quad\text{for every feasible }z.
\]

For 12 regions and 8 products, \(\Gamma=2\) has
\(1+96+\binom{96}{2}=4657\) scenarios.
