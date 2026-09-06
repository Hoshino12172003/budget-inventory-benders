# Formal experiment protocol

These files describe E1–E7 but cannot run them. All `.yaml` files are JSON-compatible YAML and deliberately set `formal_run_authorized` to `false`.

From the repository root:

```powershell
$env:PYTHONPATH='src'
python experiments/audit_protocol.py
python experiments/run_formal.py experiments/configs/formal/e1_algorithm_benchmark.yaml
```

The runner prints a read-only plan. Passing `--execute` is rejected. Formal result rows must follow `experiments/schemas/formal_result.schema.json`; unavailable metrics are explicit `null`.
