# E1 empirical freeze report

Final state: `RENAULT_EMPIRICAL_8CASE_V1_READY`.

The eight case identities, raw CRC identities, empirical dimensions, frozen
product list, complete deterministic geographic mapping, and mapping audit are
frozen under Decision C. Paper-final instances use the audited common mapping;
legacy 210202/210628 instances remain historical artifacts.

## Preserved formal material

The old 210202/210628 instances, nominal incumbents, budget references, and four
Direct/PRB observations remain unchanged and historical-only. The new namespace
contains eight independently generated paper-final instances and canonical
Gamma=0 incumbents. Case `210428` retains a nonunique-primary-face diagnostic,
but the common lexicographic selector makes its incumbent reproducible; no
case-specific rule or manual incumbent choice was introduced.

## Reproducibility and execution

Two independent generations produce identical instance, x0, and calibration
hashes for all eight cases. Capacity and UB compatibility pass throughout. The
local runner authorizes only the 16 frozen empirical run IDs and remains
fail-closed for identity drift, dirty Git state, overwrite attempts, synthetic
runs, and E2--E7. Commands are listed in `docs/renault_empirical_8case_v1.md`.

Dataset preparation recorded 4,302 Gamma=0 solves. No Gamma=2 E1 benchmark or
synthetic solve ran. E2--E7 authorization remains false.
