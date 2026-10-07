# Service calibration robustness protocol

This protocol adds two one-factor-at-a-time analyses to the frozen eight-case
Renault design. It does not authorize a full `SL x phi_multiplier` interaction.

## Safety state

`experiments/configs/formal/service_calibration_robustness_formal.yaml` is the
single formal configuration. Its `formal_run_authorized` value is `false` and
its authorization history is `[false]`. The runner refuses every optimization
request in that state. It also requires the frozen current model identity and a
clean committed worktree.

Legacy E4 baseline reuse is disabled. The experiment regenerates one baseline
for each of the eight cases with the same current code, runner, solver profile,
evaluation, result schema, and provenance schema as the 32 sensitivity solves.
Any comparison with old E4 results is non-blocking and is never a formal result
source.

## Non-optimizing checks

Run these commands from the repository root:

```powershell
python experiments/run_service_calibration_robustness.py --dry-run
python scripts/audit_service_calibration_robustness.py
python scripts/report_service_calibration_robustness.py --validate-only
python -m pytest tests/test_service_calibration_robustness.py -q --basetemp .pytest_service_calibration
```

The dry run must report eight baseline solves, 16 SL solves, 16 phi solves, 40
unique physical solves, and 48 logical analysis rows.

## Formal commands after separate authorization

Formal execution requires a reviewed configuration change that appends `true`
to `authorization_transition` and sets `formal_run_authorized` to `true`. After
that separate change:

```powershell
python experiments/run_service_calibration_robustness.py --execute-all
python scripts/report_service_calibration_robustness.py
```

The runner writes one immutable directory for each of the 40 current-version
physical conditions and refuses to overwrite it. Reporting uses only the eight
new `baseline` results, emits a 40-row execution manifest, and expands the
physical results to 48 labeled OFAT analysis rows so the common baseline is not
ambiguously double-counted.
