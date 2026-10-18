# Renault EB-BD development results

The eight pre-specified Renault cases completed under the frozen development protocol. All eight runs are exact-certified, cut-valid, resource-clean, and objective-consistent with Direct Gurobi.

- EB-BD mean algorithm core time: 7.431788 s
- Basic-BD mean algorithm core time: 11.475244 s
- Basic-BD / EB-BD geometric mean speedup: 1.539632x
- EB-BD wins against Direct: 0/8
- EB-BD mean oracle time: 7.202045 s (96.91% of core time)
- Mean-time order, fastest to slowest: Global-BD < Aggregate-BD < PRB-BD < Direct < EB-BD < Basic-BD

EB-BD is faster than the original Basic-BD on every case, but it is slower than Direct and does not fall between Direct and Aggregate-BD on these data. Its runtime remains dominated by exact enumeration of all admissible global scenarios. Renault case 210330 remains excluded from strict PRB development pairing because its historical internal global-coupling certification failed; that record was not reclassified.
