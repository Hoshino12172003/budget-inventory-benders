# E1a PRB source recovery audit

Status: `BLOCKED_SOURCE_MISSING`

The eight `result.json` files referenced by the immutable E1b authorization
manifest were searched by repository path and expected SHA-256 across all Git
objects and the available historical ZIP archives under the known paper and
Codex work directories. No byte-identical source artifact was found. The
manifest paths and hashes remain unchanged; summary tables are not promoted to
raw evidence and no result is regenerated.

The missing paths are the eight `experiments/results/e1_empirical_8case_v1/
E1-<case>-PRB/result.json` references for cases 210129, 210202, 210310, 210323,
210330, 210428, 210611, and 210628. Recovery requires a byte-identical file
whose SHA-256 equals the corresponding value in
`e1b_standard_vs_prb_authorization.json`.
