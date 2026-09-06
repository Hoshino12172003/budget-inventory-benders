# Nominal incumbent baseline protocol

## Frozen meaning

For each Renault case, \(x^0\) is the **nominal incumbent inventory
configuration**: the inventory plan selected before demand uncertainty is
explicitly protected against. It is model-derived and must not be described as
observed initial inventory, historical physical inventory, or actual Renault
stock. The observed Renault `initial_inventory` result remains archived as an
all-zero source observation and is not overwritten.

The corresponding \(y^0\) records the incumbent planning state. It is metadata,
not a restriction fixing the future robust model's activation decision.

## Independent generation rule

Candidate A is selected. For each case, solve the deterministic nominal model

\[
 \min_{y,x,q,u,e}
 \sum_i f_i y_i+\sum_{i,j}h_{ij}x_{ij}+Q_{nominal}(x)
\]

under the original activation, capacity, inventory-bound, demand, supply, and
service constraints, with \(d_{rj}=\bar d_{rj}\). There is no financial budget
constraint. Thus \(\Gamma=0\), and no \(x^0\), \(a^+\), \(a^-\),
reconfiguration cost, or \(\lambda_R\) enters baseline generation.

The generated \(x^0\) is frozen before the new reference budget and
\(\lambda_R\) are defined. Consequently, neither later quantity can feed back
into baseline generation:

`BASELINE_DEFINITION_NONCIRCULAR = true`

## Old reference-budget audit

The legacy formal-package manifest records \(B_{ref,old}\) as
84,614.30513135396 for 210202 and 50,558.18771213084 for 210628. The legacy
monolithic model constructs first-stage spending as
\(\sum_i f_i y_i+\sum_{i,j}h_{ij}x_{ij}\), applies the configured uncertainty
budget, and contains no reconfiguration term. Re-solving the migrated formal
parameters with nominal demand and no financial budget reproduces those values
as first-stage spending to less than \(3\times10^{-11}\). This confirms the old
values as nominal, budget-unconstrained economic anchors. They are natural
anchors for this baseline audit but are not the new reference budget.

Candidate B adds \(S(y,x)\le B_{ref,old}\). Because Candidate A attains exactly
that spending, its solution is feasible for B; B's feasible set is a subset of
A's, so both have the same optimum. Direct solves also return identical \(y\),
objective values, and \(x\) to below \(2\times10^{-11}\). Candidate A is retained
because it states the baseline independently of a stored budget constant.

## Structural stability audit

For each case, the primary optimum \(Z_{nom}\) is solved with zero MIP gap. Each
binary \(y_i\) is then forced to its opposite value and re-solved. Inventory
ranges are audited under
\(Z\le Z_{nom}+10^{-7}\). A range is treated as structurally material only when
its width exceeds \(10^{-3}\) inventory units; smaller widths are numerical
movement induced by the permitted objective slack.

The minimum forced-activation objective gaps are 21.8083585351 (210202) and
0.4851524528 (210628). Maximum inventory range widths are 0.0007566469 and
0.0006651635, respectively, with no material range. Therefore both baselines
are structurally stable and no secondary tie-break is required:

`BASELINE_STRUCTURALLY_STABLE = true`

The complete range evidence is in
`artifacts/nominal_baseline_degeneracy_audit.csv`.

## Reconfiguration and decomposition

After freezing the generated baseline,

\[
x_{ij}-x^0_{ij}=a^+_{ij}-a^-_{ij}
\]

allows additions, withdrawals, redistribution, total-stock increases, and
total-stock decreases. No conservation equation equating total additions and
withdrawals is imposed.

The baseline is a fixed first-stage parameter, and \(a^+\) and \(a^-\) remain
master variables. Recourse reads only \(x\). Hence product separability and the
risk-budget reformulation are unchanged:

\[
Q(x,z)=\sum_j Q_j(x_j,z_j),\qquad
Q^R(x)=\max_{\sum_j\gamma_j\le\Gamma}\sum_jV_{j,\gamma_j}(x_j).
\]

`PRODUCTWISE_BENDERS_COMPATIBLE = true`

No \(\lambda_R\) calibration, new \(B_{ref}\) calculation, robust
\(\Gamma>0\) experiment, or Product-wise Benders implementation is part of this
stage. No Step 1--3 parameter is modified.
