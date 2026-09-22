# Legacy region mapping forensic audit

## Decision

`LEGACY_REGION_MAPPING_NOT_RECOVERABLE` (LEVEL D).

The search recovered a partial design description, but not the identity-bearing
artifact needed to reproduce the frozen 12-region arrays. No customer-to-region
table, center coordinates, executable clustering implementation, initialization,
seed, distance rule, tie rule, region ordering rule, or uniquely identifying
intermediate aggregate was found. Constructing any mapping from the available
material would require a new clustering choice or inverse inference from
`base_demand`; neither is provenance recovery.

No optimization was run. Existing formal instances, baselines, results, and
authorization files were not modified.

## Search scope

The audit inspected:

- every ref in `Hoshino12172003/budget-inventory-benders`, including `main`,
  PR #1--#11 heads, local historical branches, reflogs, named Git objects, and
  unreachable objects;
- every fetched ref in `Hoshino12172003/robust-inventory-benders`, including
  `main`, PR #1--#86 heads, tags, complete named Git objects, history, and an
  unreachable-object audit;
- scripts, notebooks, documents, artifacts, CSV, JSON, ZIP references, and
  deleted or renamed paths visible through those objects;
- the official raw/normalized Renault archive, both available pipeline ZIPs,
  the v6 formal package, the retained old repository checkout, the extracted
  v6 package, prior task attachments, and relevant local paper/code roots;
- the only related workbook found locally,
  `Renault真实数据处理与参数映射.xlsx`, using a read-only workbook import.

Neither `Renault模型参数对标与处理结果_v3.xlsx` nor
`renault_model_preparation_v3_geo.zip` is present in the searched repository
history or local paths. Their contents cannot be inferred from their names.

## Formal-package provenance boundary

The v6 package first enters the legacy Git history in source commit
`e4b2606ca332902f9f9cd0d69b228bb19ee0ca73` (PR #81), later represented by
merged commit `10fe8aa4f3b93dc17314a8561198c885e0c6bd2e`. The diff adds finalized
instances, index metadata, eligibility, a manifest, file hashes, dry-run
validation, and tests. Its parent tree contains no Renault formal-data builder,
mapping table, center table, or preparation workbook. The PR description also
describes input validation, not data construction.

The v6 ZIP has SHA-256
`4e30fe65536c96f9c487a121f554748e7fc799925d620d4599b83010f87a8ae0`
and contains 16 files. Its metadata identifies depot, product, and numeric
region order, but includes no customer identity, source workbook/path, mapping,
center, cluster rule, or seed. The current formal `base_demand` arrays are
cellwise identical to the v6 B1.00 arrays for both cases. This establishes the
copy chain from v6 to the new repository, not the construction chain from raw
customer data.

## Partial rule recovered from a descriptive workbook

The workbook `Renault真实数据处理与参数映射.xlsx` has SHA-256
`65564b4074324dd9fee072b0c540724893e46de60ad388018245b81d899c39c6`
and a filesystem creation/modification time of 2026-09-06 21:27:14 +08:00. Its
five sheets are explanatory tables; it contains no hidden mapping data, center
table, formulas, or external links.

It states this intended procedure:

1. use the customers common to cases 210202 and 210712;
2. cluster their latitude/longitude into 12 regions without demand weighting;
3. assign case-specific additional customers to the nearest common center.

The official archive independently confirms that 210202 has 551 customers,
210712 has 567, their identity intersection has exactly 411 customers, and the
411 shared identities have no coordinate conflicts. This corroborates the
workbook's count. It does not identify the clustering algorithm, seed, centers,
distance/tie rule, or label order.

The workbook also exposes a provenance conflict: it names 210712, while the
v6 formal package and the verified formal source chain identify 210628 as the
second formal case. There are 430 common customers between 210202 and 210628,
not 411. Without the missing preparation artifact, the audit cannot determine
how a mapping described for 210712 was applied to the frozen 210628 arrays.

## Exact reproduction test

No raw-to-formal reproduction was attempted because no provenance-qualified
mapping exists. The required errors are therefore unavailable, not approximate
passes:

| case | raw-to-formal status | L1 error | maximum error |
|---|---|---:|---:|
| 210202 | `NOT_RUN_NO_RECOVERED_MAPPING` | n.a. | n.a. |
| 210628 | `NOT_RUN_NO_RECOVERED_MAPPING` | n.a. | n.a. |

As a separate identity check, v6-to-current formal arrays have L1 and maximum
error exactly zero for both cases. This must not be described as regeneration
from raw data.

The eight-case location-only mapping built in the preceding audit remains a
rejection diagnostic. Even after allowing the best region-label permutation,
its minimum L1 errors are 1969.2857142857144 for 210202 and
1309.692307692308 for 210628. Label permutation is not accepted as recovery.

## Extension feasibility

Extension to 210129, 210310, 210330, 210323, 210428, and 210611 is
`NOT_ASSESSED_NO_RECOVERED_MAPPING`. Directly mapped, nearest-center assigned,
unmappable, and empty-region counts are unavailable because the legacy mapping
and centers are unavailable. Creating new centers would violate the recovery
contract.

## Missing evidence and next action

Exact recovery remains possible only if an external copy of one of the missing
preparation artifacts supplies one of the following:

- the complete customer-to-region mapping with region identities;
- the exact ordered center coordinates plus assignment and tie rules; or
- a uniquely identifying customer-region intermediate with a deterministic
  reconstruction proof.

Under the evidence currently available, Decision C applies: use one common
eight-case mapping, rebuild all eight formal instances, regenerate the 210202
and 210628 incumbents and budget references, and rerun the final empirical
experiments under one geographic contract. Those actions require separate
authorization and were not performed in this audit.

`optimization solves executed = 0`

`existing formal results modified = false`

`E2-E7 authorization = false`
