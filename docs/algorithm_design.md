# Product-wise risk-budget decomposition

The new quantities (x^0,a^+,a^-,g^+,g^-) occur only in the first stage. For fixed inventory (x) and scenario (z), every recourse variable and constraint is indexed by a single product. There are no cross-product recourse constraints or objective terms. Therefore

\[
Q(x,z)=\sum_j Q_j(x_j,z_j).
\]

With the unchanged binary uncertainty

\[
d_{rj}=\bar d_{rj}+\hat d_{rj}z_{rj},\quad z_{rj}\in\{0,1\},\quad \sum_{r,j}z_{rj}\le\Gamma,
\]

define \(\gamma_j=\sum_r z_{rj}\). The robust recourse has the exact reformulation

\[
Q^R(x)=\max_{\sum_j\gamma_j\le\Gamma}\sum_j V_{j,\gamma_j}(x_j).
\]

`PRODUCTWISE_BENDERS_COMPATIBLE = true`.

This is a static mathematical audit only. The Benders algorithm is not implemented in this phase.
