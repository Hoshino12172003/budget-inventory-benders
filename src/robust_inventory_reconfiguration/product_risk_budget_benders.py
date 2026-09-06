from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from .instance import InventoryInstance
from .product_risk_subproblem import ProductCut, ProductRiskSubproblem
from .reconfiguration_model import ReconfigurationSolution
from .risk_budget_composition import compose_risk_budget, enumerate_gamma_allocations


PRODUCTWISE_BENDERS_COMPATIBLE = True


@dataclass(frozen=True)
class PRBIteration:
    iteration: int
    lower_bound: float
    upper_bound: float
    relative_gap: float
    master_objective: float
    master_best_bound: float
    master_gap: float
    cuts_checked: int
    cuts_violated: int
    cuts_added: int


@dataclass(frozen=True)
class ProductCutAddition:
    iteration: int
    violation_at_incumbent: float
    cut: ProductCut


@dataclass(frozen=True)
class PRBBendersResult:
    status: str
    solution: ReconfigurationSolution
    final_lower_bound: float
    final_upper_bound: float
    final_relative_gap: float
    iterations: tuple[PRBIteration, ...]
    master_solve_count: int
    product_subproblem_evaluations: int
    product_pattern_evaluations: int
    unique_product_cuts: int
    cuts_by_product: tuple[int, ...]
    cuts_by_gamma: tuple[int, ...]
    total_runtime: float
    master_runtime: float
    separation_runtime: float
    certification_runtime: float
    exact_certification_pass: bool
    global_risk_budget_coupling_pass: bool
    global_risk_budget_coupling_error: float
    cuts: tuple[ProductCut, ...]
    cut_additions: tuple[ProductCutAddition, ...]


def solve_prb_benders(
    instance: InventoryInstance,
    x0: list[list[float]],
    budget: float,
    gamma: int,
    lambda_r: float,
    *,
    relative_gap_tolerance: float = 1e-6,
    cut_tolerance: float = 1e-7,
    max_iterations: int = 500,
) -> PRBBendersResult:
    """Minimal exact Product-wise Risk-Budget Decomposed Benders."""
    from gurobipy import GRB

    if gamma < 0 or gamma > instance.num_regions:
        raise ValueError("gamma must be between zero and the number of regions")
    if lambda_r < 0:
        raise ValueError("lambda_r must be nonnegative")
    if len(x0) != instance.num_depots or any(
        len(row) != instance.num_products for row in x0
    ):
        raise ValueError("x0 has incompatible dimensions")
    started = perf_counter()
    master, variables = _build_master(instance, x0, budget, gamma, lambda_r)
    subproblems = [
        ProductRiskSubproblem(instance, j, gamma) for j in range(instance.num_products)
    ]
    cuts: list[ProductCut] = []
    cut_additions: list[ProductCutAddition] = []
    cut_signatures = set()
    cuts_by_product = [0] * instance.num_products
    cuts_by_gamma = [0] * (gamma + 1)
    iterations = []
    upper_bound = float("inf")
    best_solution = None
    master_runtime = 0.0
    separation_runtime = 0.0
    subproblem_evaluations = 0
    pattern_evaluations = 0

    for iteration in range(1, max_iterations + 1):
        master_started = perf_counter()
        master.optimize()
        master_runtime += perf_counter() - master_started
        if master.Status != GRB.OPTIMAL:
            raise RuntimeError(f"Exact master failed with status {master.Status}")
        lower_bound = float(master.ObjVal)
        xbar = [
            [variables["x"][i, j].X for j in range(instance.num_products)]
            for i in range(instance.num_depots)
        ]
        ybar = [int(round(variables["y"][i].X)) for i in range(instance.num_depots)]

        separation_started = perf_counter()
        product_results = [
            subproblems[j].solve([xbar[i][j] for i in range(instance.num_depots)])
            for j in range(instance.num_products)
        ]
        separation_runtime += perf_counter() - separation_started
        subproblem_evaluations += instance.num_products * (gamma + 1)
        pattern_evaluations += sum(result.pattern_evaluations for result in product_results)
        product_values = [
            [worst.value for worst in result.worst_cases] for result in product_results
        ]
        composition = compose_risk_budget(product_values, gamma)
        first_stage = float(variables["first_stage"].getValue())
        candidate_upper_bound = first_stage + composition.value
        if candidate_upper_bound <= upper_bound + 1e-8:
            upper_bound = min(upper_bound, candidate_upper_bound)
            best_solution = _solution_from_master(
                instance, x0, lambda_r, master, variables, composition.value
            )

        checked = instance.num_products * (gamma + 1)
        violated = 0
        added = 0
        for j, result in enumerate(product_results):
            for worst in result.worst_cases:
                g = worst.local_gamma
                violation = worst.value - variables["eta"][j, g].X
                if violation <= cut_tolerance:
                    continue
                violated += 1
                cut = worst.cut
                signature = (
                    j,
                    g,
                    round(cut.alpha, 10),
                    tuple(round(value, 10) for value in cut.beta),
                )
                if signature in cut_signatures:
                    raise RuntimeError("A previously added product cut remains violated")
                master.addConstr(
                    variables["eta"][j, g]
                    >= cut.alpha
                    + sum(
                        cut.beta[i] * variables["x"][i, j]
                        for i in range(instance.num_depots)
                    ),
                    name=f"product_cut[{j},{g},{cuts_by_product[j]}]",
                )
                cut_signatures.add(signature)
                cuts.append(cut)
                cut_additions.append(ProductCutAddition(iteration, violation, cut))
                cuts_by_product[j] += 1
                cuts_by_gamma[g] += 1
                added += 1

        gap = max(0.0, upper_bound - lower_bound) / max(1.0, abs(upper_bound))
        iterations.append(
            PRBIteration(
                iteration,
                lower_bound,
                upper_bound,
                gap,
                float(master.ObjVal),
                float(master.ObjBound),
                float(master.MIPGap),
                checked,
                violated,
                added,
            )
        )
        if gap <= relative_gap_tolerance and violated == 0:
            break
    else:
        raise RuntimeError("PRB-Benders reached the iteration limit")

    assert best_solution is not None
    certification_started = perf_counter()
    certified_results = [
        subproblems[j].solve(
            [best_solution.x[i][j] for i in range(instance.num_depots)]
        )
        for j in range(instance.num_products)
    ]
    certified_values = [
        [worst.value for worst in result.worst_cases] for result in certified_results
    ]
    certified_composition = compose_risk_budget(certified_values, gamma)
    certification_runtime = perf_counter() - certification_started
    subproblem_evaluations += instance.num_products * (gamma + 1)
    pattern_evaluations += sum(result.pattern_evaluations for result in certified_results)
    certified_objective = (
        best_solution.first_stage_expenditure + certified_composition.value
    )
    final_solution = ReconfigurationSolution(
        objective=certified_objective,
        first_stage_expenditure=best_solution.first_stage_expenditure,
        robust_recourse_cost=certified_composition.value,
        y=best_solution.y,
        x=best_solution.x,
        a_plus=best_solution.a_plus,
        a_minus=best_solution.a_minus,
        reconfiguration_cost=best_solution.reconfiguration_cost,
    )
    exact_certification_pass = abs(certified_objective - upper_bound) <= 1e-4
    global_coupling_error = abs(float(variables["theta"].X) - composition.value)
    global_coupling_pass = global_coupling_error <= 1e-6
    return PRBBendersResult(
        "OPTIMAL" if exact_certification_pass else "ERROR",
        final_solution,
        iterations[-1].lower_bound,
        upper_bound,
        max(0.0, upper_bound - iterations[-1].lower_bound) / max(1.0, abs(upper_bound)),
        tuple(iterations),
        len(iterations),
        subproblem_evaluations,
        pattern_evaluations,
        len(cuts),
        tuple(cuts_by_product),
        tuple(cuts_by_gamma),
        perf_counter() - started,
        master_runtime,
        separation_runtime,
        certification_runtime,
        exact_certification_pass,
        global_coupling_pass,
        global_coupling_error,
        tuple(cuts),
        tuple(cut_additions),
    )


def _build_master(instance, x0, budget, gamma, lambda_r):
    import gurobipy as gp
    from gurobipy import GRB

    depots = range(instance.num_depots)
    products = range(instance.num_products)
    master = gp.Model(f"prb_master_{instance.name}")
    master.Params.OutputFlag = 0
    master.Params.MIPGap = 0
    master.Params.FeasibilityTol = 1e-9
    master.Params.OptimalityTol = 1e-9
    master.Params.IntFeasTol = 1e-9
    y = master.addVars(depots, vtype=GRB.BINARY, name="y")
    x = master.addVars(depots, products, lb=0, name="x")
    a_plus = master.addVars(depots, products, lb=0, name="a_plus")
    a_minus = master.addVars(depots, products, lb=0, name="a_minus")
    eta = master.addVars(products, range(gamma + 1), lb=0, name="eta")
    theta = master.addVar(lb=0, name="theta")
    for i in depots:
        master.addConstr(
            gp.quicksum(instance.product_volume[j] * x[i, j] for j in products)
            <= instance.capacity[i] * y[i]
        )
        for j in products:
            master.addConstr(x[i, j] <= instance.inventory_upper_bound[i][j] * y[i])
            master.addConstr(x[i, j] - x0[i][j] == a_plus[i, j] - a_minus[i, j])
    reconfiguration_cost = lambda_r * gp.quicksum(
        instance.inventory_cost[i][j] * (a_plus[i, j] + a_minus[i, j])
        for i in depots for j in products
    )
    first_stage = gp.quicksum(instance.fixed_depot_cost[i] * y[i] for i in depots)
    first_stage += gp.quicksum(
        instance.inventory_cost[i][j] * x[i, j] for i in depots for j in products
    )
    first_stage += reconfiguration_cost
    master.addConstr(first_stage <= budget, name="financial_budget")
    for allocation_number, allocation in enumerate(
        enumerate_gamma_allocations(instance.num_products, gamma)
    ):
        master.addConstr(
            theta >= gp.quicksum(eta[j, allocation[j]] for j in products),
            name=f"risk_budget[{allocation_number}]",
        )
    master.setObjective(first_stage + theta, GRB.MINIMIZE)
    return master, {
        "y": y,
        "x": x,
        "a_plus": a_plus,
        "a_minus": a_minus,
        "eta": eta,
        "theta": theta,
        "first_stage": first_stage,
        "reconfiguration_cost": reconfiguration_cost,
    }


def _solution_from_master(instance, x0, lambda_r, master: Any, variables, robust_recourse):
    x = [
        [variables["x"][i, j].X for j in range(instance.num_products)]
        for i in range(instance.num_depots)
    ]
    if lambda_r > 0:
        a_plus = [
            [variables["a_plus"][i, j].X for j in range(instance.num_products)]
            for i in range(instance.num_depots)
        ]
        a_minus = [
            [variables["a_minus"][i, j].X for j in range(instance.num_products)]
            for i in range(instance.num_depots)
        ]
    else:
        a_plus = [
            [max(x[i][j] - x0[i][j], 0.0) for j in range(instance.num_products)]
            for i in range(instance.num_depots)
        ]
        a_minus = [
            [max(x0[i][j] - x[i][j], 0.0) for j in range(instance.num_products)]
            for i in range(instance.num_depots)
        ]
    first_stage = float(variables["first_stage"].getValue())
    return ReconfigurationSolution(
        first_stage + robust_recourse,
        first_stage,
        robust_recourse,
        [int(round(variables["y"][i].X)) for i in range(instance.num_depots)],
        x,
        a_plus,
        a_minus,
        float(variables["reconfiguration_cost"].getValue()),
    )
