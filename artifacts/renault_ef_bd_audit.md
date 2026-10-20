# Renault extensive-form Benders result audit

All timing comparisons below are descriptive cross-batch comparisons, not synchronized runs.

## EF-BD acceptance

- Exact-certified: 8/8
- Mean core time: 3.725662 s
- Mean Oracle time: 0.670018 s
- Mean master time: 0.110331 s
- Mean certification time: 1.709486 s
- Maximum Direct objective residual: 1.107e-07
- Peak process-tree RSS range: 0.105--0.133 GiB

## Paired descriptive comparisons

- EF-BD vs Direct: 0 wins / 8 losses; Direct/EF geometric time ratio 0.759.
- EF-BD vs Basic-BD: 8 wins / 0 losses; Basic/EF geometric time ratio 3.078.
- EF-BD vs Aggregate-BD: 0 wins / 8 losses; Aggregate/EF geometric time ratio 0.423.
- Historical PRB-BD 210330 remains excluded from strict pairing because its internal global-coupling certification failed.

## Core-time ordering

| Method | Eligible N | Mean core time (s) |
|---|---:|---:|
| SG-BD | 8 | 0.296379 |
| Global-BD | 8 | 0.385498 |
| Aggregate-BD | 8 | 1.574348 |
| PRB-BD | 7 | 1.657163 |
| Direct | 8 | 2.863875 |
| EF-BD | 8 | 3.725662 |
| EB-BD | 8 | 7.431788 |
| Basic-BD | 8 | 11.475244 |

EF-BD is a valid traditional single-cut baseline, but the observed ordering is empirical and must not be rewritten to match the prior hypothesis.
