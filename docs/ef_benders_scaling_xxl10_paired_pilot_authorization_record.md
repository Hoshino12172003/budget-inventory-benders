# EF-BD XXL10 paired-pilot authorization record

- Protocol: `EF_BD_XXL10_PAIRED_PILOT_V1`
- Condition: `EF_XXL10_S20260921`
- Attempt: `attempt-001`
- Frozen source: `ASC_INSTANCE_XXL10_S20260921`
- Authorization: `formal_run_authorized=false`
- Automatic retry: forbidden

The EF-BD pilot is independently authorization-closed. Its authorization cannot enable the Direct pilot. It retains the XL10-certified EF-BD algorithm: one global theta, at most one aggregate optimality cut per iteration, and the full Direct-equivalent recourse LP Oracle. Product decomposition, PRB multicut, SG pruning, and the compact Pure oracle remain excluded.

The resource protocol uses a 13-GiB process-tree cap and a 17-GiB startup gate. The four-GiB difference follows the prior EF-BD startup-minus-cap safety margin and leaves more than the three-GiB system floor at launch. The 11.08-GiB linear projection from the maximum XL10 EF-BD peak is a risk reference only; it is not evidence that XXL10 will fit.

Dry-run:

```powershell
python scripts\run_ef_benders_scaling_xxl10_paired_pilot.py --config experiments\configs\development\ef_benders_scaling_xxl10_paired_pilot_v1.yaml
```

Execution remains unavailable until a separate authorization changes only this protocol's authorization field:

```powershell
python scripts\run_ef_benders_scaling_xxl10_paired_pilot.py --config experiments\configs\development\ef_benders_scaling_xxl10_paired_pilot_v1.yaml --execute
```
