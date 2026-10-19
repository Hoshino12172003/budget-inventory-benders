# Renault SG-BD development results

All eight frozen Renault cases completed once and passed SG exact separation, global cut, independent full-enumeration, Direct-objective, identity, resource, and SHA-256 checks.

- SG-BD mean algorithm core time: 0.296379 s
- EB-BD mean algorithm core time: 7.431788 s
- EB-BD / SG-BD geometric mean speedup: 25.194922x
- SG-BD wins against Direct: 8/8
- Mean SG-BD Oracle time: 0.074004 s
- Observed mean-time order: SG-BD < Global-BD < Aggregate-BD < PRB-BD < Direct < EB-BD < Basic-BD

The seven methods retain their original evidence classes and source paths; the table does not relabel separate historical batches as a single run. Historical PRB case 210330 remains ineligible for strict pairing because its internal global-coupling certification failed.
