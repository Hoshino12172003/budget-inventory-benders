# E1 210330 global-coupling diagnostic audit

This audit reads the immutable `E1-210330-PRB` result and recomputes robust
recourse only at its saved final first-stage solution. It does not reoptimize the
first stage or overwrite a paper-final result.

## Diagnostic definition

`solve_prb_benders` defines the diagnostic as

```text
global_coupling_error = abs(final_master_theta - final_iteration_composition)
global_coupling_pass  = global_coupling_error <= 1e-6
```

The comparison is absolute. Both operands are in-memory full-precision Python
floats produced during the solve; JSON serialization is performed later and is
not used to decide the flag. The composition is the exact maximum over all
product-wise local-risk allocations whose sum is at most Gamma.

The diagnostic measures numerical closure between the final master surrogate
and an exact recourse composition at the final master point. It is not itself the
Gamma-budget feasibility constraint and is not a separate necessary feasibility
condition for the returned first-stage solution.

## Persisted-state reconstruction

The primary result stores:

| Quantity | Full persisted value |
|---|---:|
| Final master value / lower bound | 657659.549256254 |
| Certified feasible value / upper bound | 657659.5492546142 |
| First-stage expenditure | 65650.34742795814 |
| Inferred final master theta | 592009.2018282958 |
| Certified exact recourse | 592009.201826656 |
| `LB - UB` | 1.6398262232542038e-06 |
| Relative scale of `LB - UB` | 2.4934272225086203e-12 |

The runner persisted only `global_coupling_pass=false`, not the numeric error.
The persisted-state residual is reconstructible as `LB - UB` because
first-stage spending cancels between the final master and certified candidate
values. The original in-memory bit pattern was not persisted, so no audit can
recover more precision than these saved binary64 values. The tiny positive
`LB - UB` is a numerical bound-order inversion, not evidence of a second
recourse formulation.

## Fixed-final-state recomputation

The saved `x` gives the following exact global risk-budget allocation, in frozen
product order:

```text
(0, 0, 0, 0, 0, 0, 1, 1)
```

Its sum is exactly 2, equal to `Gamma=2`; the risk-budget excess is zero. The
fresh product-wise composition is `592009.201826656`, exactly equal to the
persisted certified recourse at binary64 precision. The maximum product LP
strong-duality error is `5.820766091346741e-11`, and all recovered product duals
are feasible. The independent Direct evaluator differs on the same saved `x`
by only `6.984919309616089e-10`.

Thus the residual recomputed on the returned certified state is zero. There is
no effect on feasibility, Gamma-budget satisfaction, exact recourse, objective,
or Direct/PRB equivalence.

## Source and classification

Classification: `DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH`.

The persisted `1.6398262232542038e-06` is the final master-surrogate closure
residual and is slightly larger than the separately frozen absolute diagnostic
threshold `1e-6`. It is not created by JSON serialization, rounded Gamma
values, a relative-versus-absolute comparison, stale cached composition, or a
penultimate master state. Per-iteration theta, eta, cut, and constraint-residual
details were not persisted, so it is not possible to apportion the remaining
binary64-scale closure more narrowly among master constraint, cut, and summation
tolerances without reoptimizing the first stage.

No production code or threshold is changed: the implementation matches its
documented absolute diagnostic definition, and broadening the threshold merely
to change this flag is prohibited. The paper-final certification should state
that 210330 passes exact-recourse and Direct/PRB objective consistency, while
the frozen `1e-6` master-surrogate coupling diagnostic remains unmet by a
numerical residual that does not violate the Gamma budget or alter the result.
