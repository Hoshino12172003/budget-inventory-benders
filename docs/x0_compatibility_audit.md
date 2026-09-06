# Initial-inventory compatibility audit

## Result

Both cases stop at the identity-mapping gate:

| Case | Mapping | Classification | Reason |
| --- | --- | --- | --- |
| 210202 | FAIL | SOURCE_MAPPING_FAILURE | `initial_inventory` is absent from the available Renault source snapshot |
| 210628 | FAIL | SOURCE_MAPPING_FAILURE | `initial_inventory` is absent from the available Renault source snapshot |

The audit emits a complete 15-by-8 target identity table for each case. Every value is blank and marked `MISSING_SOURCE_FIELD`; no value is imputed and no ordering assumption is used.

Because identity mapping failed, capacity compatibility, upper-bound compatibility, zero-stock, total-inventory, and inventory-coverage metrics are not computed. Reporting zero for those metrics would incorrectly imply an audited zero-inventory state, so machine-readable reports use `null`.

## Required source contract

Provide one CSV per case at `data/raw/renault_initial_inventory/<case>.csv` with columns:

```text
depot_id,product_id,initial_inventory
```

Rows must identify the canonical depot and product directly. The audit rejects duplicate pairs, unknown identities, missing target pairs, NaN, infinity, and negative inventory. It never changes source values.

Observed `initial_inventory` should not be used as (x^0) until both mappings pass and capacity/upper-bound compatibility is reported.
