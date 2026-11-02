# Second-paper experiment reproducibility map

## Scope

This repository contains the executable entry points, frozen configs, common eight-case Renault
inputs, and compact formal result bundles for E1--E7, the E6-5X5 supplement, and the later service
policy calibration experiment. Run the read-only verifier from the repository root:

```powershell
python scripts/verify_second_paper_experiments.py
```

The machine-readable contract is `experiments/second_paper_experiments.json`. Historical source
commits named there remain reachable in this Git repository; use the commit recorded by each cell's
provenance when an exact historical replay is required. The current checkout may contain later model
changes and should not be silently substituted for a provenance-pinned code state.

## Experiment inventory

| Experiment | Formal cells | Runner and config | Result evidence | Reproducibility conclusion |
| --- | ---: | --- | --- | --- |
| E1 | 16 | `run_e1_empirical_local.py`; eight-case authorization | result, first-stage solution, provenance; Direct/PRB pair outputs | Formal result and first-stage provenance retained |
| E2 | 24 | `run_e2_policy_local.py`; E2 authorization | historical `result.json` only | Legacy numerical evidence retained; exact original-coordinate replay is not fully proven |
| E3 | 40 | `run_e3_budget_local.py`; budget authorization | 40 exact-certified cells | Reproducible from provenance commits |
| E4 | 40 | `run_e4_gamma_local.py`; Gamma authorization | 40 exact-certified cells | Reproducible from provenance commits |
| E5 | 40 | `run_e5_lambda_local.py`; friction authorization | 40 exact-certified cells | Reproducible from provenance commits |
| E6 | 72 | `run_e6_budget_risk_local.py`; interaction authorization | 72 exact-certified cells | Reproducible from frozen E6 commit |
| E7 | 72 | `run_e7_risk_friction_local.py`; interaction authorization | 72 exact-certified cells | Reproducible from provenance commit |
| E6-5X5 | 200 | frozen extension runner and identity | 104 certified reuse cells and 96 new exact solves | Archival execution bundle retained byte-for-byte |
| Service calibration | 40 | service-calibration runner and formal YAML | 40 exact-certified physical solves plus scenario archive | Reproducible from commit `a42093a...` and the lossless scenario ZIP |

E3--E7 use all eight Renault cases. Older documents describing a two-case E1--E7 planning matrix
are protocol history and must not be used as the final result inventory.

## E2 limitation

The original E2 result tree predates the later provenance contract and contains no per-cell
`provenance.json` or serialized first-stage coordinate files. It supports preservation of the
reported numerical rows, but not a claim that every original policy coordinate can be reconstructed
from those 24 files alone. The separately archived E2 stockout V2R1 package is the auditable
fixed-policy supplement; it must not be relabeled as recovery of missing original E2 coordinates.

## Service scenario packaging

The repository tracks the compact service result bundle and
`service_calibration_physical_results_archive.zip`. The ZIP losslessly contains the 40 large
`service_scenarios.json` files, and its SHA-256 is frozen in the machine-readable manifest. Keeping
the scenario rows in the ZIP avoids duplicating roughly 86 MiB of identical payload in Git.

## What is intentionally excluded

Temporary pytest directories, diagnostic IIS files, intermediate review packages, duplicated ZIPs,
chat exports, and one-off audit bundles are not part of the reproducibility package. They do not
define model parameters, inputs, solver settings, first-stage solutions, or published result cells.
