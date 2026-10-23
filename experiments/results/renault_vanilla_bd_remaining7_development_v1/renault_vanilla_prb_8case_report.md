# Renault Vanilla-BD vs PRB-BD development comparison

This is development evidence and does not replace frozen Renault formal results.

- Expected cases: 8
- Valid exact pairs: 7
- PRB wins among valid pairs: 7
- Vanilla wins among valid pairs: 0
- Geometric mean Vanilla/PRB total-time ratio: 4.822025
- Mean Vanilla/PRB oracle-time ratio: 16.730745
- Mean iteration difference, Vanilla minus PRB: 3.142857

210330 is not a valid pair: PRB returned an optimal final solution and passed the independent global final-solution and cut checks, but its internal global risk-budget coupling certification failed. It was not retried.

The immutable 210202 baseline predates explicit cut_validity_pass output; its archived internal exact flag and independent global certification pass.
