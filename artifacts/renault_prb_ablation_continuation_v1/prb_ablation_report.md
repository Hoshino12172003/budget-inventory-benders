# Renault PRB 2x2 ablation continuation

All rates use the fixed denominator of eight. Timing comparisons use only pairs certified by both methods. The frozen PRB-BD and PRB-SG 210330 failures remain failures.

| Method | Certified | Failed | Mean core time (certified, s) | Mean oracle time (s) | Mean iterations | Mean added cuts | Mean pruning |
|---|---:|---:|---:|---:|---:|---:|---:|
| PRB-BD | 7/8 | 1 | 1.657163 | 0.685696 | 4.571 | 32.429 | 0.000% |
| PRB-SG | 7/8 | 1 | 1.729177 | 0.090145 | 4.571 | 32.429 | 95.774% |
| A-PRB | 8/8 | 0 | 4.764479 | 2.110884 | 10.125 | 31.000 | 0.000% |
| A-PRB-SG | 8/8 | 0 | 1.885815 | 0.192607 | 10.125 | 31.000 | 95.857% |

## Strict paired effects

- PRB-SG versus PRB-BD: N=7, geometric mean speedup=0.956x, wins=2, losses=5, ties=0.
- A-PRB versus PRB-BD: N=7, geometric mean speedup=0.334x, wins=0, losses=7, ties=0.
- A-PRB-SG versus PRB-SG: N=7, geometric mean speedup=0.889x, wins=0, losses=7, ties=0.
- A-PRB-SG versus A-PRB: N=8, geometric mean speedup=2.519x, wins=8, losses=0, ties=0.

The multiplicative interaction factor on the 7 fully certified common cases is 2.659; values above 1 indicate positive runtime synergy beyond independent multiplicative effects.

## Interpretation

- Safe screening cut mean Oracle time sharply, but PRB-SG was slightly slower overall than frozen PRB-BD on the seven strict pairs (0.956x speedup).
- Adaptive selection alone was slower on every strict pair and increased the mean iteration count; it did not add a practical benefit in this Renault study.
- Screening strongly recovered the adaptive variant (A-PRB-SG was 2.519x faster than A-PRB), but A-PRB-SG still lost all seven strict pairs against PRB-SG.
- Therefore A-PRB-SG is not recommended as the paper's main algorithm and is not recommended for L10 expansion without redesigning the adaptive rule.

The runs were produced in separate frozen batches. Cross-batch timing is descriptive, not a claim of simultaneous benchmarking.
