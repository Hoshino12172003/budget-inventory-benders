# EF-BD L10 single-pilot preparation

## Model mapping

The Scaling V2 instance uses the same generic `InventoryInstance` consumed by the Renault EF-BD implementation. The pilot reuses the unchanged single-theta first-stage master and builds the complete recourse LP from the same demand, supply, soft-service and penalty rows as the frozen Direct extensive form. The fixed `x` values appear as the supply right-hand sides. The Oracle returns their dual multipliers as one global optimality cut. No product multicut, compact global adversarial MILP, or SG pruning is used. The mapping is therefore strict for the frozen L10 instance; no Renault recalibration or new instance generation occurs.

## Zero-build theoretical scale

For `I=25`, `R=24`, `J=12`, and `Gamma=2`, each product has `1+24+C(24,2)=301` local scenario blocks, hence 3,612 blocks. Formula evaluation (without constructing a Gurobi model) gives:

| model | variables | constraints | nonzeros |
|---|---:|---:|---:|
| EF-BD monolithic recourse Oracle | 2,257,537 | 184,303 | 6,773,683 |
| frozen Direct extensive form | 2,258,462 | 184,929 | 6,866,733 |

The Direct variable and constraint totals reproduce the frozen preparation record exactly. The nonzero counts are structural estimates, not measured Gurobi values.

## Resource decision

The configured 4 GiB process-tree cap is not defensible for this pilot. The EF Oracle retains 99.96% of the Direct variables and almost the complete recourse matrix. The archived L10 Direct attempt-002 reached 4.698249816894531 GiB, while attempt-001 crossed its 4 GiB cap at 4.02410888671875 GiB. Although EF-BD is a continuous decomposition and may avoid branch-and-bound memory, there is no measured EF-BD L10 RSS evidence supporting a lower peak. Per the frozen rule, the status is `BLOCKED_RESOURCE_DESIGN`; this preparation does not raise the cap.

The protocol remains authorization-closed, allows only `EF_L10_S20260921`, targets `attempt-001`, uses `Threads=2`, and retains the 900 s / 7 GiB startup / 3 GiB system floor / 20 GiB disk / 0.25 s monitor settings. Dry-run performs identity and resource checks only and does not instantiate or optimize a Gurobi model.

The eventual command, after a separately reviewed resource protocol changes the decision to `READY_FOR_AUTHORIZATION` and explicitly authorizes execution, is:

```powershell
python experiments\run_ef_benders_scaling.py --config experiments\configs\development\ef_benders_scaling_l10_pilot_v1.yaml --execute
```
