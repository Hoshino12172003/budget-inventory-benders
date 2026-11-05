"""Independent recourse-value audit of the failed V2 L10/20260925 run.

Save next to the two previous Scaling30 runners under experiments/.
Read-only to all existing results and source code. Writes one new diagnostic JSON.
This audit verifies the V2 incumbent's recourse value using the original
ProductRiskSubproblem implementation. It does NOT by itself certify V2 cuts,
the V2 lower bound, or the overall V2 run.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import run_accelerated_prb_v2_scaling30 as frozen
from robust_inventory_reconfiguration.product_risk_subproblem import ProductRiskSubproblem
from robust_inventory_reconfiguration.risk_budget_composition import compose_risk_budget

SIZE, SEED, WORKERS = 'L10', 20260925, 2

def main() -> None:
    instance, prep, base, _ = frozen.fetch_inputs(SIZE, SEED)
    failure_dir = ROOT / f'experiments/results/prb_basic_v2_fair_scaling30_W{WORKERS}/failed_diagnostics'
    failures = sorted(failure_dir.glob(f'{SIZE}_{SEED}_v2_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not failures:
        raise FileNotFoundError(f'No preserved V2 failure file under {failure_dir}')
    raw = frozen.read_json(failures[0])['result']
    solution = raw['first_stage_solution']
    x = solution['x']
    if len(x) != instance.num_depots or any(len(row) != instance.num_products for row in x):
        raise RuntimeError('V2 candidate inventory has unexpected shape')
    values = []
    worst_dual_failures = []
    max_strong_duality_error = 0.0
    for j in range(instance.num_products):
        model = ProductRiskSubproblem(instance, j, 2)
        try:
            result = model.solve([x[i][j] for i in range(instance.num_depots)])
            values.append([float(case.value) for case in result.worst_cases])
            for case in result.worst_cases:
                if not case.cut.dual_feasible:
                    worst_dual_failures.append({'product': j, 'gamma': case.local_gamma})
                max_strong_duality_error = max(max_strong_duality_error, case.cut.strong_duality_error)
        finally:
            model.model.dispose()
        print(f'[INDEPENDENT] product {j + 1}/{instance.num_products}', flush=True)
    composition = compose_risk_budget(values, 2)
    recovered_objective = float(solution['first_stage_expenditure']) + composition.value
    record = {
        'size': SIZE,
        'seed': SEED,
        'failed_result': str(failures[0].relative_to(ROOT)),
        'reference_basic_objective': float(base['final_objective']),
        'v2_reported_objective': float(solution['objective']),
        'independent_robust_recourse_cost': composition.value,
        'v2_reported_robust_recourse_cost': float(solution['robust_recourse_cost']),
        'independent_objective_at_v2_inventory': recovered_objective,
        'objective_difference_independent_vs_frozen_basic': abs(recovered_objective - float(base['final_objective'])),
        'objective_difference_independent_vs_v2': abs(recovered_objective - float(solution['objective'])),
        'recourse_difference_independent_vs_v2': abs(composition.value - float(solution['robust_recourse_cost'])),
        'independent_risk_allocation': list(composition.allocation),
        'worst_case_dual_feasibility_failures': worst_dual_failures,
        'maximum_strong_duality_error': max_strong_duality_error,
        'scope_note': 'Independent candidate-recourse check only. Does not validate V2 lower bound or all historical cuts.',
    }
    out = failure_dir / f'independent_{SIZE}_{SEED}_v2_risk_check.json'
    frozen.write_json(out, record)
    print(json.dumps(record, indent=2, ensure_ascii=False))
    print(f'[AUDIT WRITTEN] {out}')

if __name__ == '__main__':
    main()
