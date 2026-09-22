# Renault raw case inventory audit

## Scope and provenance

The supplied `renault_data_pipeline.zip` contains 71 identifiable raw cases and
220,518 ZIP members. Its SHA-256 is
`38fa3aa486d1974e3d037d9e1cfc2af3340b0d8d132a96cc4e409ce575c1ea33`.
This audit read the archive without extraction and did not run an optimization
model. Files inside the archive were treated as data and provenance, not as
instructions.

The embedded official `instances.tar.gz` has MD5
`5a557a2edd50bb308bf955f754b22503`, exactly matching the value declared by the
package README, and SHA-256
`c27075450bc8ace8e74087316b64f22d2a9a9909cb4e4746341bc9f3998950ea`.
The full ZIP CRC test found no bad member. The package `provenance.json` still
says the raw archive could not be materialized; that status is stale and
contradicted by the embedded raw archive and 71 processed case directories, so
it is recorded as a provenance inconsistency rather than used as case evidence.

The authoritative complete inventory is
`table_renault_case_inventory.csv`. Its 71 rows record the logical raw source
directory, processed-audit CRC32, original sizes, record counts, field
availability, reconstruction checks, each formal-processing component, frozen
post-processing dimensions, and expected Direct size where defined.

`demand_record_count` is the normalized customer-product-day row count.
`inventory_record_count` is the depot-product `initial_inventory` row count
relevant to reconstructing a depot baseline. Pair density is computed after
aggregating the daily panel over each original identity pair.

## Case inventory

The case IDs are:

`210129`, `210202`, `210208`, `210209`, `210210`, `210212`, `210215`,
`210218`, `210219`, `210222`, `210223`, `210224`, `210225`, `210301`,
`210302`, `210308`, `210309`, `210310`, `210312`, `210316`, `210317`,
`210318`, `210319`, `210323`, `210324`, `210330`, `210401`, `210407`,
`210408`, `210409`, `210412`, `210413`, `210414`, `210416`, `210426`,
`210427`, `210428`, `210429`, `210503`, `210505`, `210506`, `210512`,
`210513`, `210514`, `210519`, `210520`, `210524`, `210525`, `210526`,
`210531`, `210602`, `210604`, `210607`, `210609`, `210611`, `210614`,
`210616`, `210617`, `210618`, `210621`, `210623`, `210628`, `210629`,
`210705`, `210706`, `210708`, `210712`, `210713`, `210714`, `210719`,
and `210720`.

Archive-wide checks:

- the raw normalization input contract is complete for 71/71 cases;
- an exact depot-product `initial_inventory` table is reconstructible for
  71/71 cases, with no duplicate, missing, NaN, or infinite values;
- the frozen selected eight product identities occur in 71/71 cases;
- distance, `km_cost`, depot inventory cost, and customer shortage cost fields
  occur in 71/71 cases;
- every observed depot `initial_inventory` value is zero in all 71 cases.

The last point means the raw archive has no observed initial-inventory
distribution variation. The nonzero frozen incumbents used by the current
reconfiguration study are derived nominal incumbent baselines; they must not be
relabeled as observed Renault `initial_inventory`.

## Formal processing compatibility

The archive's `process_renault.py` is a lossless normalizer, not the paper's
Step 1-3 formal-instance builder. The current repository has frozen formal
instances only for `210202` and `210628`, and its converter explicitly lists
only those two cases.

For every other date, the supplied archive does not contain an executable
customer-to-12-region mapping, the exact product-ranking procedure, or the
complete transformations and calibrations for demand deviation, capacity, UB,
inventory cost, shortage cost, transport cost, fixed cost, service parameters,
the nominal incumbent, and `B_ref`. Recreating these definitions would require
scientific choices rather than file-path or parser plumbing. Raw field
availability alone is therefore not treated as formal reproducibility.

Classification:

- `READY_WITH_EXISTING_PIPELINE`: 2 (`210202`, `210628`);
- `REQUIRES_NONSCIENTIFIC_PLUMBING_ONLY`: 0;
- `REQUIRES_NEW_MODELING_ASSUMPTION`: 69.

For the 69 non-ready cases, the numerical post-processing dimensions are
reported as blank with `post_processing_dimensions_status=NOT_FROZEN`. Filling
them with 15/12/8 would incorrectly assume the missing selection and aggregation
rules.

## Size and structural variation

Across the 71 raw cases:

- original customers range from 485 to 760;
- original depots range from 11 to 19;
- original products range from 29 to 30;
- normalized demand records range from 295,365 to 444,180;
- depot inventory records range from 319 to 570;
- planning horizons range from 19 to 22 daily columns;
- nonzero customer-product demand pairs range from 1,687 to 2,254;
- nonzero demand-pair density ranges from 0.102269 to 0.129086;
- nonzero depot-inventory pairs and their density are zero throughout.

This is genuine raw workload, demand-density, and sparsity variation. It is not
yet formal model-size variation. Both ready cases have post-processing
dimensions 15 depots by 12 regions by 8 products and 96 uncertain items. At
`Gamma=2`, each exact Direct formulation has 122,376 variables and 18,629
constraints, matching the existing E1 model-size records.

The two ready cases still differ structurally: `210202` has 551 customers, 29
raw products, 319,580 demand records, 1,974 nonzero demand pairs, and demand-pair
density 0.123537; `210628` has 634 customers, 30 raw products, 361,380 demand
records, 2,062 nonzero demand pairs, and density 0.108412. These differences
support a multi-case real benchmark, but identical formal dimensions do not
support a scalability claim.

## Execution state

- Optimization runs executed by this audit: 0.
- Synthetic runs executed: 0; all eight remain `NOT_RUN`.
- Existing 210202 and 210628 Direct/PRB results were neither rerun nor
  overwritten.
- E2-E7 authorization remains `false`.
