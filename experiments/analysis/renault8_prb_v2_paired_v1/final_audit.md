# Renault8 Basic PRB vs Accelerated PRB V2 final audit

## Completeness and identity

- Eight frozen `RENAULT_EMPIRICAL_8CASE_V1` cases and 16 method results are present; each result has a matching provenance hash.
- Every condition uses its case-specific frozen instance, canonical x0, calibration artifact, and B_ref. No demand, geography, inventory, or budget was rebuilt.
- Basic and V2 share Gamma=2, beta=1.0, lambda_R=0.05, relative gap 1e-6, cut tolerance 1e-7, maximum 500 iterations, and the `gurobi-balanced-1e-8-v1` solver profile.
- All 16 objectives match the frozen historical Direct objective within 1e-4, and each Basic/V2 pair matches within 1e-4.

## Certification boundary

- Fourteen of 16 method results are `strict_original` (7/8 for each method).
- Renault 210330 retains the original global-risk coupling failure for both methods: residual 1.6398262232542038e-6 exceeds the unchanged 1e-6 threshold.
- Both 210330 results passed the separate final-inventory product recourse and returned-cut numerical audit and are labelled `independently_numerically_validated`. This narrower audit is not a proof of whole-domain cut validity or exact arithmetic.
- No failed, slow, or losing result was removed. V2 wins and certification rates are reported over all eight paired cases.

## Scaling30 comparison boundary

- Renault8 and Scaling30 use the same Gamma/beta/lambda_R values, stopping tolerances, solver-native profile, Basic/V2 worker allocation, one Gurobi thread per model, and core-time definition.
- They do not share an instance population: Renault8 uses eight empirical frozen cases and case-specific B_ref/x0, whereas Scaling30 uses synthetic calibrated scaling instances and seeds. Results may be displayed together as complementary evidence, but should not be pooled as one homogeneous sample.

## Resource and publication decision

- Maximum observed process-tree RSS was 0.229 GiB; no timeout or resource stop occurred.
- V2 won 6/8 cases. The paired geometric-mean speedup is 1.099x.
- The table is suitable for Chapter 5 Table 2 if the caption discloses 2-process V2 versus serial Basic and preserves the 210330 separate numerical-validation label.
- Historical E1 and E2-E7 files were read only; this experiment writes only its independent result and analysis roots.
