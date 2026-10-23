# PR #11 scientific blocker resolution

Decision: `BLOCKED_MATERIAL_EVIDENCE_RESOLVED_BY_SCOPE_REDUCTION`

## Original blocker

Eight E1a PRB `result.json` files are absent and zero expected SHA-256 values
were recovered. They were the sole raw basis for the E1a PRB timing,
iterations, cuts, certification labels, and the PRB side of E1b comparisons.

## Resolution

The missing evidence is not reconstructed. Instead, PR #11's scientific scope
is reduced so that no formal conclusion depends on it:

1. the E1a performance summary is explicitly historical and non-confirmatory;
2. its JSON artifact carries `E1_HISTORICAL_SUMMARY_SOURCE_INCOMPLETE` and
   forbids confirmatory timing/certification use;
3. a case-level evidence table marks all eight PRB sources `SOURCE_MISSING`;
4. E1b and E1c documents withdraw unqualified PRB paired-performance claims;
5. later development evidence is reported only as an 8/8 objective crosscheck
   with 7 PASS and 1 FAIL;
6. E2-E7 reused cells receive cell-level disclosure rules;
7. independent Scaling V2 and XXL10 evidence is explicitly protected.

No result value, model, parameter, tolerance, or raw experiment file is changed.

## Acceptance boundary

PR #11 is scientifically reviewable only under this reduced scope. It does not
establish a reproducible Renault E1a PRB runtime advantage, an 8/8 original
certification rate, or a source-complete four-method Renault comparison. If any
of those claims remains in the manuscript or a downstream PR without the
required label, the blocker reopens as `BLOCKED_MATERIAL_EVIDENCE`.

The resolution therefore concerns admissible paper claims, not recovery of the
missing files. Downstream PRs #12-#15 must incorporate this commit by a normal
merge of the updated PR #11 branch after #11 is reviewed; they must not be
force-rebased or have history rewritten automatically.

## Verification gates

- expected E1a PRB sources present: 0/8;
- expected E1a PRB SHA matches: 0/8;
- later development instance/x0 identity matches: 8/8;
- later development objective matches: 8/8;
- later strict certification: 7 PASS, 1 FAIL (210330);
- optimization calls during reconciliation: 0;
- historical formal result content changes permitted: none.
