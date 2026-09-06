# Optimal-face equivalence correctness contract

## Purpose

A correctness pass means that PRB-Benders solves the same mathematical optimization problem as the frozen exact benchmark and returns a certified globally optimal solution. It does not require two exact formulations to select the same coordinate-wise inventory vector when the problem has multiple globally optimal solutions.

This contract changes validation only. Reconfiguration Model V2, its objective and constraints, recourse, uncertainty, data, parameters, PRB product cuts, separation, convergence logic, and solver tolerances are unchanged.

## Classification

Each correctness case receives exactly one status.

`EXACT_SOLUTION_IDENTITY` requires both methods to be certified optimal, both first-stage solutions to be feasible, the objective, first-stage expenditure, robust recourse, and robust minimum fill rate to agree within the frozen tolerances, identical depot activation, and maximum coordinate-wise inventory difference at most `1e-5`.

`OPTIMAL_FACE_EQUIVALENT` requires the same certification, feasibility, objective-component, activation, and service checks, but the inventory vectors differ beyond `1e-5`. Each solution must additionally receive a fixed-inventory exact robust evaluation and satisfy

```text
C_FS(y,x) + Q^R(x) <= Z_star + tau_obj.
```

This establishes membership of both reported points in the certified global optimal objective set. It does not attempt to characterize the entire optimal face.

`FAIL` applies when either preceding definition is not satisfied. The aggregate correctness flag is true exactly when every case is either `EXACT_SOLUTION_IDENTITY` or `OPTIMAL_FACE_EQUIVALENT` and no case is `FAIL`.

## Independent audit of the former mismatches

For 210202 with `beta=1.10`, `lambda_R=0`, and `Gamma` equal to 1 or 2, the exact and PRB solutions were solved again independently. For each returned `(y,x)`, the audit checks nonnegativity, binary activation, capacity, activation-linked inventory bounds, reconfiguration balance, and financial budget directly. It then calls the frozen exact robust recourse and service evaluator at fixed `x`, recomputes `C_FS + Q^R(x)`, and compares that value with the independently solved exact benchmark optimum `Z_star`. The PRB master lower bound is not used as the sole evidence for membership.

Both pairs are independently feasible and exactly certified on the same optimal objective level. Their maximum coordinate differences and numbers of materially different coordinates are large, while total inventory is equal to numerical precision and objective components agree to substantially tighter than their frozen tolerances. They are therefore genuine alternate optima.

## Canonical reporting under multiple optima

If a future paper or reproducibility package needs one unique inventory vector, a separate reporting step may be run only after the primary optimum `Z_star` is established. Possible conventions include minimum total inventory, minimum weighted inventory movement, or deterministic lexicographic inventory.

No canonicalization is implemented here. A canonical solution is a reporting convention, not a requirement for correctness of the main optimization algorithm. No secondary objective or tie-break has been inserted into either solver.
