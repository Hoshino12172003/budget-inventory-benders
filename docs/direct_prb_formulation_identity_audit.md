# Direct and PRB formulation identity audit

`DIRECT_PRB_FORMULATION_IDENTITY_PASS=true`.

Direct and PRB receive the same formal instance, nominal-incumbent `x0`, budget,
`Gamma`, `lambda_R`, first-stage feasible region, recourse equations, uncertainty
semantics, objective coefficients, and integrality assumptions.

The former solver-native tolerance mismatch is resolved by shared profile
`gurobi-balanced-1e-8-v1`. Direct, PRB master, and PRB product LPs now obtain
their settings from `solver_profile.py`; they no longer hard-code competing
profiles. The selection uses the already stable Direct/evaluator `1e-8` setting,
which is stricter than the `1e-7` cut gate without introducing an untested demand
for uniformly tighter `1e-9` solves.

PRB-only algorithmic and certification gates are not solver-native tolerances and
remain unchanged.
