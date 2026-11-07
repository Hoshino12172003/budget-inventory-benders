# E8 formal results archive audit

Status: AUDIT_COMPLETE

Audit scope: read-only deterministic verification of existing E8 results. New optimization calls = 0. Solver imports were blocked in this audit process.
Execution commit: 0aa68f4d51db0475596bc10c2bfb7db300eda1c7. Existing target worktree: E:/w/direct-prep.
24/24 formal conditions passed; 192/192 product checkpoints passed identity, payload hash, block coverage and OPTIMAL primary/tiebreak status checks.
Each condition contains 4,657 scenario rows, reconstructed exactly from saved product blocks. All summaries were recomputed and matched exactly.
All frozen source/input/arc identities and delivery_sha256.json entries passed. The code delivery manifest remains unchanged and is separate from this result manifest.
Immutable protocol SHA-256: 2b7e9e0ffdc97e8214ba909277c5bc27a191c11cba4ad966ba3f514946c52ccd

## Condition completion and resources

| Condition | Result | Evaluation runtime (s) | Sum of monitored attempts (s) | Peak monitored RSS (GiB) | Attempts |
|---|---|---:|---:|---:|---:|
| E8-210202-K1 | PASS; 8/8 OPTIMAL | 0.644316800 | 2.502470000 | 0.056365967 | 1 |
| E8-210202-K2 | PASS; 8/8 OPTIMAL | 0.721054600 | 2.488674300 | 0.056739807 | 1 |
| E8-210202-FULL | PASS; 8/8 OPTIMAL | 0.792591200 | 4.159000300 | 0.070529938 | 2 |
| E8-210628-K1 | PASS; 8/8 OPTIMAL | 0.671229400 | 2.241707300 | 0.056270599 | 1 |
| E8-210628-K2 | PASS; 8/8 OPTIMAL | 0.757925200 | 2.482513800 | 0.063369751 | 1 |
| E8-210628-FULL | PASS; 8/8 OPTIMAL | 0.785418100 | 2.498168500 | 0.059825897 | 1 |
| E8-210129-K1 | PASS; 8/8 OPTIMAL | 0.841840700 | 2.499398900 | 0.055446625 | 1 |
| E8-210129-K2 | PASS; 8/8 OPTIMAL | 0.856522600 | 2.488838600 | 0.055732727 | 1 |
| E8-210129-FULL | PASS; 8/8 OPTIMAL | 0.900252800 | 2.777682200 | 0.057247162 | 1 |
| E8-210310-K1 | PASS; 8/8 OPTIMAL | 0.741228500 | 2.175942300 | 0.058891296 | 1 |
| E8-210310-K2 | PASS; 8/8 OPTIMAL | 0.726245500 | 2.191871200 | 0.056667328 | 1 |
| E8-210310-FULL | PASS; 8/8 OPTIMAL | 0.744034900 | 2.471584400 | 0.071544647 | 1 |
| E8-210330-K1 | PASS; 8/8 OPTIMAL | 0.680585900 | 2.204986200 | 0.055416107 | 1 |
| E8-210330-K2 | PASS; 8/8 OPTIMAL | 0.665635400 | 2.200972000 | 0.056888580 | 1 |
| E8-210330-FULL | PASS; 8/8 OPTIMAL | 0.661009500 | 2.217427500 | 0.057037354 | 1 |
| E8-210323-K1 | PASS; 8/8 OPTIMAL | 0.617110400 | 2.209018200 | 0.070556641 | 1 |
| E8-210323-K2 | PASS; 8/8 OPTIMAL | 0.681513900 | 2.219058400 | 0.056400299 | 1 |
| E8-210323-FULL | PASS; 8/8 OPTIMAL | 0.690447600 | 2.181112100 | 0.071487427 | 1 |
| E8-210428-K1 | PASS; 8/8 OPTIMAL | 0.670138000 | 2.222436800 | 0.056381226 | 1 |
| E8-210428-K2 | PASS; 8/8 OPTIMAL | 0.748227400 | 2.214707400 | 0.056835175 | 1 |
| E8-210428-FULL | PASS; 8/8 OPTIMAL | 0.728038200 | 2.234110400 | 0.056617737 | 1 |
| E8-210611-K1 | PASS; 8/8 OPTIMAL | 0.694184000 | 2.230704300 | 0.056354523 | 1 |
| E8-210611-K2 | PASS; 8/8 OPTIMAL | 0.704547300 | 2.206646000 | 0.056922913 | 1 |
| E8-210611-FULL | PASS; 8/8 OPTIMAL | 0.776939300 | 2.488052000 | 0.056690216 | 1 |

Monitor scope is sampled process-tree RSS, not an unsampled continuous memory maximum. All 25 retained monitors have return_code=0 and stop_reason=null. 210202-FULL has two successful resume attempts; both are retained. Monitor wall time can include checkpoint reuse and is not an independent solver timing.

## Full versus historical E2

| Case | E8 Full | E2 robust recourse | Absolute error |
|---|---:|---:|---:|
| 210202 | 952269.838250680361 | 952269.838250680477 | 1.16415321827e-10 |
| 210628 | 599292.006227792124 | 599292.006227792124 | 0 |
| 210129 | 760949.135833491571 | 760949.135833491571 | 0 |
| 210310 | 638420.455707783578 | 638420.455707783694 | 1.16415321827e-10 |
| 210330 | 592009.201826656004 | 592009.201826656004 | 0 |
| 210323 | 558871.026075866190 | 558871.026075866190 | 0 |
| 210428 | 717805.412082329276 | 717805.412082329276 | 0 |
| 210611 | 552759.410145326983 | 552759.410144364228 | 9.62754711509e-07 |

All eight absolute errors are <= 1e-4.

## Historical certification exception

210330 retains historical E1 label CERTIFIED_PRB_EXACT and global_coupling_pass=false. E8 evaluates fixed inventory. Full/E2 agreement does not repair or independently establish historical E1 global optimality. The all-eight analysis and seven-case analysis excluding 210330 are both retained.

## Paired analysis and interpretation

The CSV has 48 rows = 8 cases x 3 modes x 2 common-scenario evaluation bases. Its fields agree with JSON and archived scenario rows. Nominal service comparisons use S0000. Adverse service comparisons evaluate all three modes at the Full-mode worst-economic-cost representative scenario, using the same scenario ID and shock set. These paired service outcomes are not each mode's own worst-service outcomes.
Full <= k2 <= k1 holds within 1e-4 for all 37,256 case/scenario combinations and for mode-specific maximum economic costs. Arc nesting was verified from frozen input inventories. No universal ordering of shortage or service metrics is assumed.
Eight-case and seven-case sensitivity summaries were deterministically rebuilt in memory and matched exactly. These are descriptive comparisons; no statistical significance is asserted.

- all_8_cases: n=8; mean k1-to-Full reduction=8.849591047768%; mean k1-Full saving=64953.013933859998; mean k2-Full saving=3956.902799123534.
- exclude_210330_7_cases: n=7; mean k1-to-Full reduction=8.854943821055%; mean k1-Full saving=66059.161015376812; mean k2-Full saving=4522.174627569753.

## Archive inventory and SHA-256

340 existing files: 120 formal result files, 192 product checkpoints, 25 monitor records and three paper analysis files. Adding this report and the independent checksum manifest gives 342 archived files.
The checksum manifest covers 341 files including this report. It excludes itself to avoid self-reference. All recorded original provenance result hashes and checkpoint payload hashes were verified before archival. The newly generated checksum list was then verified byte-for-byte.
stdout/stderr, launcher scripts, caches, pilot files and unrelated experimental outputs are excluded. Historical E1/E2 files, model, runner, configuration, authorizations and immutable protocol are unchanged.

The archive is self-contained with the inputs/code already present in PR #20. Result identities pin the historical execution commit, not the later archive commit. For future audits, compare result identities against their recorded execution commit rather than constructing an identity from the current archive HEAD.

## Git byte preservation

All 342 staged blobs were compared against original local bytes. Existing analysis text attributes would normalize line endings; archival blobs were staged without content filters to preserve original SHA-256 identities. The ordinary git diff --cached --check reports preserved CRLF as trailing whitespace. The same check with core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol passes without changing payloads or tracked attributes.
