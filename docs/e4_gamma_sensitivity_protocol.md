# E4 Gamma sensitivity protocol

## Research question

E4 asks how the level of demand uncertainty alters the economic value and intensity of robust inventory reconfiguration. It studies how much the firm changes the data-derived nominal incumbent inventory configuration, and how worst-case economic exposure changes, as the uncertainty budget increases.

## Experimental design

The paper-final design is 8 Renault-data-derived cases by 5 Gamma levels, giving 40 conditions. Run IDs use `E4-<case>-G<gamma>`.

| Field | Frozen value |
|---|---|
| Dataset | `RENAULT_EMPIRICAL_8CASE_V1` |
| Cases | 210202, 210628, 210129, 210310, 210330, 210323, 210428, 210611 |
| Gamma | 0, 1, 2, 3, 4 |
| beta | 1.00 |
| Financial budget | case-specific `B_ref` |
| Reconfiguration friction | `lambda_R=0.05` |
| Solver profile | `gurobi-balanced-1e-8-v1` |
| Method | frozen exact PRB-Benders |

Only Gamma varies. Dataset, mapping, instances, canonical x0, B_ref, model, tolerances, solver profile, and PRB implementation remain fixed.

## Gamma interpretation

Gamma is the demand-uncertainty budget, not the financial budget and not the reconfiguration-friction parameter. It controls how many region-product demand components can simultaneously take their adverse deviations. With 12 regions and 8 products there are 96 uncertainty items. Gamma from 0 to 4 therefore means at most 0 to 4 adverse region-product components, not at most 4 regions or 4 products.

Gamma 0 is nominal demand, Gamma 1 represents mild uncertainty, Gamma 2 is the current baseline, and Gamma 3/4 provide progressively stronger tested protection. These labels do not impose monotonicity on the first-stage structural response.

## Reuse contract

Gamma 2 is identity-equivalent to the E3 B100 PRB result only when dataset, case, instance, x0, calibration, B_ref, beta, Gamma, lambda_R, solver profile, model and PRB identities, tolerance contract, objective accounting, certification, provenance hashes, and full first-stage artifact all agree. The static audit verifies all eight cases.

The E2 NOMINAL results were reviewed for Gamma 0 reuse. Their planning conditions align on several fields, but the saved package does not contain a full first-stage solution artifact, run provenance, recorded model/calibration identities, a Gamma-0 evaluated objective, or an explicit exact-certification field. Consequently their formal reuse classification is `E4_G0_REUSE_NOT_IDENTITY_SAFE`. They remain scientific context but are not E4 source observations.

Thus, 8 Gamma-2 observations are reusable and 32 new solves are required after authorization: Gamma 0, 1, 3, and 4 for each case.

## Execution and certification contract

The local runner fails closed unless the exact run ID is authorized, the repository is clean, all data and implementation identities match, and the target does not exist. Gamma-2 execution copies the independently verified E3 B100 result and complete first-stage artifact into the isolated E4 namespace with new provenance. Other Gamma levels invoke the unchanged exact PRB-Benders implementation and retain its final exact certification contract. No full scenario enumeration, cut-strategy change, stabilization, or tuning is introduced.

Each result records objective and cost components; budget accounting; reconfiguration movement, RI and RS; activation changes; worst-recourse cost components; service diagnostics; runtime, iterations, master/subproblem/cut counts; bounds, gap, and exact-certification fields; plus all dataset and implementation hashes.

## Scientific interpretation contract

E4 may report how objective, robust recourse, RI, RS, activation, shortage allocation, and economic protection vary with Gamma. It must not presume that RI is increasing, that service always improves, or that any first-stage response is monotone. Robust protection may become more costly in theory, while discrete and substitutable first-stage responses need not be monotone. Results must be described as empirical behavior over the eight cases and frozen Gamma grid.

## Preparation status

The protocol static audit performs identity reads, hashes, reuse eligibility checks, Git-ignore isolation checks, and tests only. It performs zero optimization solves and zero fixed-first-stage evaluations. The result root is `experiments/results/e4_gamma_sensitivity_v1/` and is narrowly ignored without affecting other experiment roots.

After the fail-closed protocol passed its static audit and targeted tests, the authorization manifest recorded the explicit transition `[false, true]`. This authorizes only the 40 enumerated E4 run IDs; it does not execute them.
