# Formal experiment matrix E1-E7

All counts use one deterministic run per cell. They describe the frozen protocol
but do not authorize execution.

| Group | Frozen design | Count formula | Runs |
| --- | --- | --- | ---: |
| E1 | PRB vs Direct on two Renault cases and four synthetic scales | `2 cases*2 methods + 4 scales*2 methods` | 12 |
| E2 | Existing, nominal-reconfiguration, robust-reconfiguration variants | `2 cases*3 variants` | 6 |
| E3 | `beta={0.8,0.9,1.0,1.1,1.2}` | `2 cases*5 beta levels` | 10 |
| E4 | `Gamma={0,1,2,3,4}` | `2 cases*5 Gamma levels` | 10 |
| E5 | `lambda_R={0,0.0025,0.01,0.05,0.20}` | `2 cases*5 friction levels` | 10 |
| E6 | `beta={0.8,1.0,1.2}` by `Gamma={0,2,4}` | `2 cases*3*3` | 18 |
| E7 | `Gamma={0,2,4}` by `lambda_R={0.0025,0.05,0.20}` | `2 cases*3*3` | 18 |
| **Total** |  |  | **84** |

E1's 12 runs consist of four Renault method runs and eight synthetic method
runs. Its scales are small `(5,4,3)`, medium `(10,8,5)`, Renault-like
`(15,12,8)`, and large `(20,16,10)`. Structural sizes remain planning evidence,
not measured performance. The 24 GB preflight stop on a 32 GB host remains in
force for any later authorized large-scale execution.

E2 fixes `x=x0` for the existing-system row, uses `Gamma=0` for the nominal
rows, and uses `Gamma=2` for robust reconfiguration. All variants use
`beta=1.0` and `lambda_R=0.05`.

E2 follow-up requirement: compare Existing, Nominal, and Robust decisions with
one unified Gamma-based post-evaluation. Do not directly compare a Gamma=0
evaluation with a Gamma=2 evaluation.

Across E1-E7, case budgets are computed as `B=beta*B_ref_case`.
