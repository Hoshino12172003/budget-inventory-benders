# E2 existing, nominal, and robust reconfiguration protocol

E2 asks how much value deterministic and robust reconfiguration create relative
to maintaining the same Renault-data-derived nominal incumbent configuration.
All policies use `RENAULT_EMPIRICAL_8CASE_V1`, case-specific `B_ref`, `beta=1`,
`lambda_R=0.05`, the frozen solver profile, and exact evaluation at `Gamma=2`.

- `EXISTING` fixes `x=x0`, `y=y0`, and both adjustment matrices to zero. It is
  evaluated but not optimized.
- `NOMINAL` optimizes the unchanged reconfiguration model at `Gamma_plan=0`,
  then fixes its first-stage solution for exact evaluation at `Gamma_eval=2`.
- `ROBUST` uses `Gamma_plan=2`. The eight E1 PRB solutions have matching
  instance, x0, calibration, mapping, solver-profile, Gamma, beta, and lambda
  identities, so they are reused rather than reoptimized. Each is still passed
  through the common exact `Gamma_eval=2` evaluator.

The eight cases are 210202, 210628, 210129, 210310, 210330, 210323, 210428,
and 210611. The protocol contains 24 evaluation IDs. It requires eight new
nominal optimization solves and 24 fixed-first-stage evaluations; eight robust
planning solves are reused from E1. Direct is not run.

Economic metrics separate fixed depot, final inventory, reconfiguration, and
robust recourse costs. Reconfiguration metrics include adjustment totals,
changed pairs, active-set changes, `RI=sum(a_plus+a_minus)/sum(x0)`, and
`RS=reconfiguration_cost/B`. Available service metrics are total shortage,
shortage cost, and service-penalty cost in the worst-recourse scenario, plus
minimum/average fill rate and worst region in the frozen worst-service scenario.
These identities are kept distinct rather than presenting one scenario as worst
for every metric.

Primary contrasts report Nominal minus Existing, Robust minus Existing, and
Robust minus Nominal for the common `Gamma=2` evaluation. Negative objective or
recourse changes represent improvements. Results must be written to the E2-only
namespace and the runner refuses an existing run directory.

The authorization manifest is enabled only after all eight instance, x0,
calibration, mapping, parameter, solver-profile, and runner-hash checks pass.
Authorization does not execute E2. E3-E7 remain unauthorized.

## Commands

From the repository root in PyCharm Terminal or PowerShell:

```powershell
$env:PYTHONPATH = "src"
python experiments/run_e2_policy_local.py --case 210202 --policy EXISTING
python experiments/run_e2_policy_local.py --case 210202 --policy NOMINAL
python experiments/run_e2_policy_local.py --case 210202 --policy ROBUST
```

Repeat the three commands for `210628`, `210129`, `210310`, `210330`,
`210323`, `210428`, and `210611`. Run only from the authorized clean commit.
