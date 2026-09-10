# E1 objective mismatch audit: 210310 and 210330

The four paper-final run directories are immutable inputs. This audit fixes each saved
first-stage solution and evaluates its robust recourse with both the Direct extensive
form and the product-wise PRB certifier. No first-stage problem is reoptimized.

The frozen cross-method threshold remains `1e-4`; no model, tolerance, parameter,
dataset, authorization manifest, or paper-final result is changed.

## Findings

### 210310

Classification: `NUMERICAL_REPORTING_ONLY`.

Reported objective difference: `1.1082738637924194e-07`.
Direct/PRB use the same y: `true`. Maximum x difference:
`3.549902771737834e-08`; L1 x difference: `7.1000787471575677e-08`.
Same-x recourse differences are `9.3132257461547852e-10` on Direct x and
`1.1641532182693481e-09` on PRB x.

| Quantity | Direct | PRB | Absolute difference |
|---|---:|---:|---:|
| Objective | 714814.54770759039 | 714814.54770770122 | 1.1082738637924194e-07 |
| Fixed depot cost | 1519.692 | 1519.692 | 0 |
| Final inventory cost | 74874.39999991747 | 74874.399999917499 | 2.9103830456733704e-11 |
| Reconfiguration cost | 1.947155222515652e-11 | 0 | 1.947155222515652e-11 |
| Reported robust recourse | 638420.45570767287 | 638420.45570778369 | 1.1082738637924194e-07 |

| Fixed inventory | Direct evaluator Q | PRB evaluator Q | Difference |
|---|---:|---:|---:|
| Direct x | 638420.45570767217 | 638420.4557076731 | 9.3132257461547852e-10 |
| PRB x | 638420.45570778253 | 638420.45570778369 | 1.1641532182693481e-09 |

Largest x difference: depot `91017500`, product `CON-S-0130`,
Direct `85.073333329035279`, PRB `85.073333364534307`.
Reported/reconstructed objective errors are `6.9849193096160889e-10`
and `1.1641532182693481e-09`.
Direct bound/gap: `714814.54770759039` / `0`.
PRB lower bound/gap: `714814.54770770099` / `3.257217475504957e-16`;
global coupling pass: `true`.

The saved first-stage points differ only numerically, while the recourse formulations
agree on each fixed point. The supplied mismatch exponent was three orders of
magnitude too large: the recorded difference is below `1e-4` and the existing paired
comparison artifact already reports `PASS`.

### 210330

Classification: `NUMERICAL_REPORTING_ONLY`.

Reported objective difference: `5.5960845202207565e-07`.
Direct/PRB use the same y: `true`. Maximum x difference:
`4.6291438025036769e-06`; L1 x difference: `1.2220939984430856e-05`.
Same-x recourse differences are `6.9849193096160889e-10` on Direct x and
`6.9849193096160889e-10` on PRB x.

| Quantity | Direct | PRB | Absolute difference |
|---|---:|---:|---:|
| Objective | 657659.54925405455 | 657659.54925461416 | 5.5960845202207565e-07 |
| Fixed depot cost | 1612.7760000000001 | 1612.7760000000001 | 0 |
| Final inventory cost | 63898.34302485393 | 63898.343024853923 | 7.2759576141834259e-12 |
| Reconfiguration cost | 139.22840310421279 | 139.22840310421691 | 4.1211478674085811e-12 |
| Reported robust recourse | 592009.2018260964 | 592009.201826656 | 5.5960845202207565e-07 |

| Fixed inventory | Direct evaluator Q | PRB evaluator Q | Difference |
|---|---:|---:|---:|
| Direct x | 592009.2018260957 | 592009.2018260964 | 6.9849193096160889e-10 |
| PRB x | 592009.20182665531 | 592009.201826656 | 6.9849193096160889e-10 |

Largest x difference: depot `90016100`, product `CON-S-0130`,
Direct `341.74704357573671`, PRB `341.74704820488051`.
Reported/reconstructed objective errors are `6.9849193096160889e-10`
and `6.9849193096160889e-10`.
Direct bound/gap: `657659.54925405455` / `0`.
PRB lower bound/gap: `657659.54925625399` / `0`;
global coupling pass: `false`.

The saved first-stage points differ only numerically, while the recourse formulations
agree on each fixed point. The supplied mismatch exponent was three orders of
magnitude too large: the recorded difference is below `1e-4` and the existing paired
comparison artifact already reports `PASS`.

## Interpretation

Both fixed-x recourse formulations are mathematically consistent, and both cases pass the
frozen `1e-4` cross-method gate. The generic PRB relative termination rule alone does not
guarantee that absolute gate at this objective scale, so a future protocol revision should
state an absolute certification condition. That contract observation does not turn either
of these two recorded comparisons into a failure.

No recommendation in this audit changes the frozen threshold or retunes a solver.
