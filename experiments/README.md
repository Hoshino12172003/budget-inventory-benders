# Formal experiment protocol

These files contain the frozen experiment design. E2–E7 remain unauthorized; the paper-final empirical E1 manifest separately authorizes exactly 16 Renault runs. The `.yaml` protocol files remain JSON-compatible YAML and fail closed.

From the repository root:

```powershell
$env:PYTHONPATH='src'
python experiments/audit_protocol.py
python experiments/run_formal.py experiments/configs/formal/e1_algorithm_benchmark.yaml
```

The runner prints a read-only plan. Passing `--execute` is rejected. Formal result rows must follow `experiments/schemas/formal_result.schema.json`; unavailable metrics are explicit `null`.

Formal cases are `210202` and `210628`. Budgets are derived from the case-specific
`B_ref` values in `configs/formal/formal_parameter_freeze.json`.
