# Renault data calibration and provenance

The repository selectively retains the two Step 3 baseline snapshots for cases `210202` and `210628`. Each has 15 canonical depot identities, 12 regions, and 8 canonical product identities.

Retained parameter logic:

- weekday demand aggregation for nominal demand;
- demand deviation under the existing budgeted binary uncertainty;
- transport-cost construction;
- shortage-penalty aggregation;
- product volume, depot capacity, inventory upper bounds, inventory cost, fixed depot cost, and service parameters.

The JSON provenance block preserves the legacy source paths, SHA-256 hashes, and the observed/derived/calibrated/policy classification from the Step 3 metadata. No Step 1–3 value is recalibrated. The old budget is intentionally not carried forward because the new reference budget \(B_{ref}\) remains to be defined.

The legacy repository does not contain the Renault source field `initial_inventory` or a Step 1–3 builder capable of reconstructing it. Accordingly, this repository does not infer (x^0) from array position or from any other parameter.
