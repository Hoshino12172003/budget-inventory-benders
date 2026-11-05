# Final archive audit: Basic PRB versus Accelerated PRB V2 Scaling30

## Verdict

`PASS_FOR_DRAFT_PR_ARCHIVE`

- 30 unique `(size, seed)` pairs and 60 method results were resolved from raw JSON evidence.
- L10, XL10, and XXL10 each contain exactly 10 seeds (20260921--20260930).
- Accelerated PRB V2 is faster in 30/30 paired core-time observations.
- V2 certificate classes are 5 `legacy_strict_exact`, 24 `strict_original`, and 1 `independently_numerically_validated`.
- The maximum paired objective difference is `6.7800283432006836e-07`, below the frozen `1e-4` objective tolerance.
- No optimization was invoked by the archive builder or verifier.

## L10/20260925 qualification

The original global risk-budget coupling check failed with error `4.071509465575218e-06`, so the original strict certificate remains `False`. Independent product-recourse evaluation matched the V2 objective within `6.789341568946838e-07`; the returned-cut audit found no final-inventory violation above `1e-6`, with maximum observed excess `6.785867299186066e-07`. The audit is limited to candidate recourse and returned cuts at the final inventory. It is not exact arithmetic, a whole-domain cut-validity proof, or a restoration of the original strict certificate.

## Claim-evidence matrix

| Claim | Required evidence | Current evidence | Boundary | Review risk |
| --- | --- | --- | --- | --- |
| V2 reduces runtime relative to Basic PRB | Same instances, parameters, tolerances, hardware batch, and paired timing | 30 same-environment pairs; V2 wins 30/30 | Applies only to this frozen Scaling30 protocol | Low |
| V2 preserves solution quality | Objective agreement and disclosed certification | Max objective difference `6.78e-07`; 29 strict + 1 separate numerical validation | The numerical case is not a strict certificate | Low if disclosed |
| V2 is faster than Direct, EF-BD, and Aggregate-BD | Unified five-method paired experiment | Only historical-batch descriptive timings | No cross-batch speedup is valid | High if overclaimed |
| Pure Benders is represented correctly | Separate method identity and historical record | Existing Pure Benders audit retained | Not EF-BD and not a new paired baseline | Low |

## Exclusions

Large stdout/stderr logs, monitor logs, caches, temporary files, unrelated development result roots, and historical E2--E7 data are not part of this archive commit. The selected formal result/provenance JSON files and the four L10/20260925 diagnostics are sufficient to audit the published rows.
