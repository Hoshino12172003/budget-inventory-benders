# AI risk-trigger feasibility pilot

This directory contains the solver-free analysis entry point for the exploratory risk-trigger pilot. It reads only frozen E2/E3/E4/E5/E7 tables, formal instances, and nominal incumbent artifacts.

Run from an existing Python environment with NumPy and scikit-learn:

```powershell
python experiments/ai_trigger_pilot/run_ai_trigger_pilot.py
```

The default output namespace is `artifacts/ai_trigger_pilot/`. The script does not import repository optimization modules or Gurobi.
