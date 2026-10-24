# E1 empirical data builder

The static builder is `scripts/freeze_e1_empirical_cases.py`. It reads normalized
customer coordinates and daily demand directly from the official Renault ZIP;
it does not call a solver.

## Geographic rule

The mapping uses the 298 customer identities present in all eight selected
cases as its fixed geographic reference. It computes a deterministic,
unweighted 12-medoids partition with haversine distance:

1. choose the global medoid;
2. add centers by deterministic farthest-first initialization;
3. update each center to its cluster medoid until convergence;
4. order centers west to east;
5. assign every customer in every date to its nearest frozen center, breaking
   ties by region order.

No demand, cost, inventory, optimization output, clock, random seed, or local
absolute path enters the mapping. The resulting mapping hash is
`0bcdd7bb99926ed780c56764c531b76971dbb0bf24e77198766a754d9dde95ff`.
All 4,923 case-customer observations are covered, and every one of the 96
case-region cells is nonempty. Case totals and center coordinates are recorded
in `table_e1_empirical_region_mapping_audit.csv`; complete identity assignments
are in `artifacts/e1_empirical_region_mapping_v1.json`.

## Compatibility gate

The archive does not contain the legacy customer-to-region mapping used to
build the frozen 210202 and 210628 formal instances. To test whether the new
rule was nevertheless equivalent, the builder reconstructed weekday mean
demand for the same eight products and compared it with each frozen
`base_demand` array. It also solved the finite 12-by-12 row-assignment problem,
so region labels were allowed to permute.

The best possible permutation still gives:

| case | minimum L1 difference | maximum cell difference | exact cells / 96 |
|---|---:|---:|---:|
| 210202 | 1969.2857142857144 | 187.28571428571422 | 13 |
| 210628 | 1309.692307692308 | 120.46153846153854 | 12 |

Therefore the new location-only rule is internally valid but not compatible
with the already frozen formal inputs. Combining new instances under this rule
with the four existing E1 observations would compare different regional model
definitions. The builder stops with `BLOCK_E1_EMPIRICAL_REGION_MAPPING` before
parameter transformation, nominal baseline construction, or formal instance
generation.

Resolution requires one explicit scientific choice: recover and freeze the
legacy case-invariant mapping, or authorize rebuilding and rerunning 210202 and
210628 under this new mapping. The latter conflicts with the current instruction
to preserve and reuse those results.

Re-run the static audit with:

```powershell
python scripts/freeze_e1_empirical_cases.py E:\文献阅读\论文写作\第二版预算\工厂数据\renault_data_pipeline.zip
```
