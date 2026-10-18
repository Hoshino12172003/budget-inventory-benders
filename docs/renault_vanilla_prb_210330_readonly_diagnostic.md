# Renault Vanilla-BD vs PRB-BD 210330 read-only diagnostic

## Scope and evidence boundary

This diagnostic did not call Gurobi, re-run an optimization, change a tolerance,
modify an algorithm, or rewrite any archived result. The development comparison
continues to classify 210330 as not paired; the aggregate count remains 7/8.

The current development artifact persists the final result but does **not** persist
the PRB iteration objects, final master `theta`, final-iteration composition,
`global_risk_budget_coupling_error`, or an identity hash for `best_solution.x`.
Consequently, the exact in-memory coupling residual and last two iteration records
from this particular development process are not recoverable. Values from a prior
formal run with the same frozen instance identity are identified below as historical
same-identity evidence, not misrepresented as fields from the development file.

## Proven facts from the current development run

| Quantity | Persisted value |
|---|---:|
| PRB status | `OPTIMAL` |
| Iteration count | 5 |
| Product-cut count | 33 |
| Returned objective | 657659.5492546142 |
| Independently certified global recourse | 592009.201826656 |
| Independent objective residual | 0.0 |
| Independent strong-duality residual | 1.1641532182693481e-10 |
| Maximum stored product-cut strong-duality residual | 5.820766091346741e-11 |
| Product-cut dual feasibility | PASS |
| Independent global final-solution certification | PASS |
| Internal exact flag used by the development comparison | FAIL |
| Resource stop | none |

The internal flag is false because the underlying PRB result returned
`global_risk_budget_coupling_pass=false`; PRB status is `OPTIMAL`, the product cuts
pass, and the independent final-solution certification passes.

The current development result does not contain the final two `PRBIteration`
records. Their exact lower bounds, upper bounds, master objectives, master best
bounds, master gaps, cuts checked, and cuts added must therefore be reported as
`NOT_PERSISTED_NOT_RECOVERABLE_WITHOUT_RERUN`.

## Diagnostic definition and solution identities

The unchanged implementation performs these operations:

1. It solves each master and requires `master.Status == GRB.OPTIMAL`.
2. It reads `xbar` from that master and computes `composition` at the same `xbar`.
3. It optionally updates `best_solution` when the candidate upper bound is no
   greater than the incumbent upper bound plus `1e-8`.
4. After termination it independently certifies recourse at `best_solution.x`.
5. It defines the coupling diagnostic as
   `abs(final_master_theta - final_iteration_composition)` and compares it with
   the absolute threshold `1e-6`.

Thus the two operands of the coupling diagnostic come from the same final master
iteration. The diagnostic does not directly mix `best_solution.x` into either
operand. The returned certified objective does use `best_solution.x`.

For the current development run, final-master optimality is implied by successful
control flow through the explicit status guard, but the raw integer master status
was not serialized. Likewise, the artifact does not persist either the final
`xbar` or `best_solution.x`; their equality cannot be proved byte-for-byte from the
current files. A final-master/best-solution identity mismatch is therefore neither
established nor completely falsifiable for this process from its archived schema.

## Historical same-identity reconstruction

An earlier immutable 210330 PRB audit used the same frozen scientific identity:

| Identity field | SHA-256 |
|---|---|
| Instance | `5c89a9e3151a8372f2be5884130cfc9b6eb84347fd132456527a7fdc984857a1` |
| Frozen x0 | `11cd91349ff218d7f951a38a65123de8c5e304d36a370c97a39a1ce9b3c3961a` |
| Calibration | `e182dde7a79c1c9e7909fb776df4d1cff0326d39bbee5414c3d7efdb147e071a` |
| Mapping | `0bcdd7bb99926ed780c56764c531b76971dbb0bf24e77198766a754d9dde95ff` |

It also has the same `Gamma=2`, `lambda_R=0.05`, first-stage expenditure,
certified recourse, and returned objective. Its persisted values reconstruct:

| Quantity | Value |
|---|---:|
| Final master objective / lower bound | 657659.549256254 |
| Certified feasible objective / upper bound | 657659.5492546142 |
| First-stage expenditure | 65650.34742795814 |
| Inferred final master theta | 592009.2018282958 |
| Exact risk-budget composition | 592009.201826656 |
| Reconstructed coupling residual | **1.6398262232542038e-6** |
| Absolute threshold | **1.0e-6** |
| Residual / threshold | **1.6398262232542038** |
| Excess above threshold | **6.398262232542038e-7** |
| Relative objective scale | 2.4934272225086203e-12 |

The corresponding exact risk allocation is `(0,0,0,0,0,0,1,1)`, whose sum is
exactly 2. Re-evaluation at the saved returned first-stage solution gives zero
recourse reconstruction residual. The historical audit classifies the event as
`DIAGNOSTIC_TOLERANCE_CONTRACT_MISMATCH`.

This `1.6398262232542038e-6` value is the exact residual reconstructible from the
historical persisted binary64 values. It is strong same-identity reproduction
evidence for the current false flag, but it is not a field persisted by the current
development process. The current process's exact in-memory residual remains
`NOT_PERSISTED`.

## Cross-case comparison

The same frozen baseline evidence reconstructs master-bound closure residuals of:

| Case | Signed LB - UB | Absolute residual / 1e-6 |
|---|---:|---:|
| 210202 | 0.0 | 0.0 |
| 210628 | 0.0 | 0.0 |
| 210129 | 1.1641532182693481e-10 | 0.0001164 |
| 210310 | -2.3283064365386963e-10 | 0.0002328 |
| 210330 | 1.6398262232542038e-6 | 1.6398262 |
| 210323 | -1.1641532182693481e-10 | 0.0001164 |
| 210428 | 0.0 | 0.0 |
| 210611 | 1.6111880540847778e-7 | 0.1611188 |

Only 210330 exceeds the `1e-6` diagnostic threshold. It is about 10.18 times the
next-largest absolute residual, 210611. This supports an isolated numerical closure
event under a common certification implementation, not a systematic failure of
the risk-budget composition or product-cut logic.

## Findings

### Established

- The current development final solution and cuts pass independent recourse,
  dual-feasibility, strong-duality, and objective reconstruction checks.
- The false flag belongs to the master-surrogate coupling diagnostic.
- The historical same-identity residual is `1.6398262232542038e-6`, which is
  `1.6398262232542038` times the frozen `1e-6` threshold.
- The diagnostic operands are the final master theta and the same final
  iteration's composition. The code does not directly compare final theta with a
  composition evaluated at `best_solution.x`.
- 210330 is the only one of the eight same-protocol cases whose historical
  closure residual exceeds the threshold.

### Likely explanation

- The evidence is consistent with a small absolute numerical closure mismatch
  between the final master surrogate and exact product-risk composition. It is
  not consistent with an infeasible Gamma allocation, invalid product cut, or an
  incorrectly certified returned objective.

### Not established

- The current development process's exact coupling error, final theta, final
  composition, and last two iteration records were not persisted.
- Equality of current final `xbar` and current `best_solution.x` cannot be proved
  from the archived schema.
- The residual cannot be apportioned more narrowly among master feasibility,
  individual cut activity, and floating-point summation without a separately
  authorized instrumented validation run.

## Decision

Keep 210330 as FAIL and preserve the 7/8 valid-pair statistic. Do not relax the
threshold or reinterpret the archived flag.

If narrower attribution is scientifically necessary, design a separate,
explicitly authorized instrumentation-only validation that records the final two
iterations, hashes both first-stage solutions, and persists theta, exact
composition, active allocation, cut slacks, and solver constraint residuals. Such
a validation must be a new attempt and must not overwrite or relabel the current
development evidence.
