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

Observed initial inventory is (x^0_{ij}). Add nonnegative adjustment variables

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

but this phase deliberately leaves \(\lambda_R\) unset.

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
