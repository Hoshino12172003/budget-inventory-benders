# Mathematical model foundation

## Depot semantics

All 15 Renault depots are existing facilities. For each depot (i),

\[
y_i =
\begin{cases}
1, & \text{existing depot } i \text{ is active during the planning horizon},\\
0, & \text{otherwise}.
\end{cases}
\]

(f_i) is the fixed planning-period depot activation or operating cost. It is not interpreted as new-warehouse construction cost in the Renault cases. If (y_i=0), then (x_{ij}=0) for every product (j); the reconfiguration balance therefore records withdrawal of existing inventory.

## Reconfiguration Model V2 draft

The model baseline (x^0_{ij}) is the **nominal incumbent inventory
configuration** selected by the independent, budget-unconstrained, (\Gamma=0)
planning model before reconfiguration costs or robust protection are introduced.
It is not observed or historical Renault stock. The separately archived observed
`initial_inventory` audit remains unchanged. Add nonnegative adjustment variables

\[
a^+_{ij}\ge 0, \qquad a^-_{ij}\ge 0,
\]

with

\[
x_{ij}-x^0_{ij}=a^+_{ij}-a^-_{ij}.
\]

The reconfiguration cost is

\[
R(x;x^0)=\sum_{i,j}\left(g^+_{ij}a^+_{ij}+g^-_{ij}a^-_{ij}\right).
\]

The first specification uses

\[
g^+_{ij}=g^-_{ij}=\lambda_R h_{ij},
\]

where \(\lambda_R\ge 0\) is a calibrated economic or policy parameter measuring
reconfiguration friction. It is not an observed Renault parameter, and
\(\lambda_R=0\) is the frictionless benchmark.

The first-stage cost and budget are

\[
C^{FS}=\sum_i f_i y_i+\sum_{i,j}h_{ij}x_{ij}+R(x;x^0),
\qquad C^{FS}\le B,
\]

and the objective draft is

\[
\min C^{FS}+\theta.
\]

The second-stage variables, constraints, uncertainty semantics, and costs are unchanged.

## Budget reference

The reference budget is frozen from the incumbent state rather than reoptimized:

\[
B_{ref}=\sum_i f_i y_i^0+\sum_{i,j}h_{ij}x^0_{ij}.
\]

At that state, both adjustment variables and \(R(x^0;x^0)\) are zero, so this
definition is independent of \(\lambda_R\). Experiment budgets are represented
as \(\beta=B/B_{ref}\).
