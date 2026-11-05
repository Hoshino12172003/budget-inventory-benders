# Scaling30 experiment environment and reproducibility

The 60 provenance records agree on Python 3.12.7, Gurobi/gurobipy 13.0.1, Windows 11 build identity `10.0.26200`, 14 logical CPUs, one Gurobi thread per model, one Basic worker, and two V2 process workers. CPU model, physical core count, physical RAM, NumPy version, and psutil version were not written into the historical runtime provenance and therefore remain unverified historical facts.

For archival context only, the current machine reports `Intel(R) Core(TM) Ultra 5 225H`, 14 physical cores, 14 logical processors, and 31.497 GiB RAM. Current package versions are Python 3.12.7, gurobipy 13.0.1, NumPy 2.4.4, and psutil 7.2.2. These current observations must not be substituted for fields absent from historical runtime records.

Core time is the algorithm's returned `total_runtime`; child wall time wraps the solve call. Outer monitor time and the exceptional numerical audit are excluded from the paper core-time comparison.
