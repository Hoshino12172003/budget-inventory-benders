# E5 210310 L2000 first-stage accounting audit

## Finding

`E5-210310-L2000` failed in post-solve reporting, not in the optimization model. The PRB solve had returned `OPTIMAL`, passed exact certification, exposed the complete first-stage solution in memory, and passed the independent robust-recourse reporting check before the accounting exception was raised. `write_run()` had not started, so no complete or partial formal artifact existed.

Classification: `CANONICAL_REPORTING_VS_SOLVER_ACCOUNTING_MISMATCH`.

The failed process did not persist its in-memory numerical solution. The values below come from the single permitted verification rerun after the reporting/accounting fix, using the unchanged formal model, data, parameters, solver profile, and tolerances.

## Original gate

The original runner compared

```text
fixed_cost + inventory_cost + canonical_reconfiguration_cost
```

against the primary solver's `first_stage_expenditure`. The canonical cost used

```text
lambda_R * sum(h_ij * (max(x_ij-x0_ij, 0) + max(x0_ij-x_ij, 0)))
```

whereas the solver expenditure used the solver-returned `a_plus` and `a_minus`. The check was absolute, hard-coded at `1e-6`, and evaluated from in-memory full-precision floats. The separate budget-feasibility tolerance was also `1e-6`; no relative accounting tolerance was used.

## Full-precision reconstruction

| Quantity | Value |
|---|---:|
| Certified primary objective | 714814.5477065423 |
| Fixed cost | 1519.692 |
| Inventory cost | 74874.39999991693 |
| Solver-based reconfiguration cost | -1.013109511038273e-06 |
| Canonical reconfiguration cost | 2.02895509460177e-06 |
| Solver-based first-stage cost | 76394.09199890382 |
| Primary first-stage expenditure | 76394.09199890384 |
| Exact robust recourse | 638420.4557076385 |
| Reconstructed total objective | 714814.5477065423 |
| Solver-based accounting error | -1.4551915228366852e-11 |
| Canonical-based accounting error | 3.0420487746596336e-06 |

The solver-based decomposition closes to approximately `1.46e-11`. The canonical-based decomposition exceeds the unchanged `1e-6` gate because it is not the adjustment representation used by the solver's economic expression.

The raw solver adjustment is a near-zero numerical residual: total solver `a_plus` is `-3.165967221994603e-08` and total solver `a_minus` is zero. The canonical representation has total plus `3.170115547845853e-08`, total minus `3.1723004667583155e-08`, and total adjustment `6.342416014604169e-08`. The maximum coordinate difference is `3.1700253089184116e-08`. Weighting these tiny residuals by `lambda_R=0.20` and the inventory-cost coefficients produces the `3.0420487746596336e-06` accounting discrepancy. The negative solver reconfiguration value is numerical noise around the mathematical lower bound zero and is retained for transparent certified-objective accounting; its magnitude is negligible relative to the frozen objective tolerance.

For context, the prior completed L2000 runs passed the old canonical gate with residuals `0` (210129), `1.4551915228366852e-11` (210202), and `2.653832780197263e-07` (210628). The same case at L0500 has canonical adjustment `1.9437003118127905e-09` and reported reconfiguration cost zero. Thus the L2000 failure is the expected amplification of near-zero adjustment noise, not a change in the economic solution.

## Fix and preservation

Economic accounting now uses solver-returned `a_plus`/`a_minus` and checks that their reconstructed reconfiguration cost matches the solver expression. Canonical adjustment remains the source for RI, total adjustment, and changed-pair reporting. For positive friction, the saved first-stage artifact preserves solver adjustments; lambda zero retains the degeneracy-safe canonical representation. RS uses the same reconfiguration cost that enters the primary objective and budget.

No tolerance was changed. No model, dataset, `B_ref`, beta, Gamma, lambda grid, solver profile, objective definition, or certification contract changed. The single verification rerun created the previously absent `E5-210310-L2000` artifact. Hash comparison found zero modifications among all E5 files that existed before the rerun; E1-E4 were not touched.

The runner is safe to resume. Same-run overwrite protection remains active.
