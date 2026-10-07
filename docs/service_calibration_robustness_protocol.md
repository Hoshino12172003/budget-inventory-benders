# Service calibration robustness protocol

This protocol adds two one-factor-at-a-time analyses to the frozen eight-case
Renault design. It does not authorize a full `SL x phi_multiplier` interaction.

## Safety state

`experiments/configs/formal/service_calibration_robustness_formal.yaml` is the
single formal configuration. Its `formal_run_authorized` value is `false` and
its authorization history is `[false]`. The runner refuses every optimization
request in that state. It also refuses execution unless all eight reused
baseline results pass the complete identity audit and the worktree is clean.

The current checkout does not contain the per-run E4 Gamma=2 baseline result,
solution, and provenance files. In addition, the current aggregate model-source
identity differs from the one frozen by the E4 manifest. Baseline reuse is
therefore not authorized in this checkout.

## Non-optimizing checks

Run these commands from the repository root:

```powershell
python experiments/run_service_calibration_robustness.py --dry-run
python scripts/audit_service_calibration_robustness.py
python scripts/report_service_calibration_robustness.py --validate-only
python -m pytest tests/test_service_calibration_robustness.py -q --basetemp .pytest_service_calibration
```

The dry run must report 24 SL analysis rows, 24 phi analysis rows, eight shared
physical baselines, and 32 prospective new optimization solves.

## Formal commands after separate authorization

Formal execution requires a reviewed configuration change that appends `true`
to `authorization_transition`, sets `formal_run_authorized` to `true`, and
resolves the eight baseline identity failures. After that separate change:

```powershell
python experiments/run_service_calibration_robustness.py --execute-all
python scripts/report_service_calibration_robustness.py
```

The runner writes one immutable directory per non-baseline condition and refuses
to overwrite it. Reporting reads the eight identity-safe E4 baselines, emits 40
unique physical rows, and expands those to 48 labeled OFAT analysis rows so the
shared baseline is not ambiguously double-counted.
