from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from .instance import InventoryInstance
from .product_risk_subproblem import ProductRiskSubproblem
from .reconfiguration_model import ReconfigurationSolution
from .risk_budget_composition import compose_risk_budget
from .solver_profile import apply_formal_solver_profile


STANDARD_BENDERS_EXACT = True


@dataclass(frozen=True)
class AggregateCut:
    alpha: float
    beta: tuple[tuple[float, ...], ...]
    generation_value: float
    generation_x: tuple[tuple[float, ...], ...]
    gamma_allocation: tuple[int, ...]
    patterns: tuple[tuple[int, ...], ...]
    dual_feasible: bool
    strong_duality_error: float

    def value_at(self, x: list[list[float]] | tuple[tuple[float, ...], ...]) -> float:
        return self.alpha + sum(
            self.beta[i][j] * x[i][j]
            for i in range(len(self.beta))
            for j in range(len(self.beta[i]))
        )


@dataclass(frozen=True)
class StandardOracleResult:
    value: float
    gamma_allocation: tuple[int, ...]
    cut: AggregateCut
    product_subproblem_evaluations: int
    product_pattern_evaluations: int
    cut_construction_runtime: float


@dataclass(frozen=True)
class StandardBendersIteration:
    iteration: int
    lower_bound: float
    upper_bound: float
    absolute_gap: float
    relative_gap: float
    master_objective: float
    master_best_bound: float
    master_gap: float
    cut_violation: float
    cut_added: bool


@dataclass(frozen=True)
class StandardBendersResult:
    status: str
    solution: ReconfigurationSolution
    final_lower_bound: float
    final_upper_bound: float
    final_absolute_gap: float
    final_relative_gap: float
    iterations: tuple[StandardBendersIteration, ...]
    master_solve_count: int
    product_subproblem_evaluations: int
    product_pattern_evaluations: int
    aggregate_cut_count: int
    total_runtime: float
    master_runtime: float
    oracle_runtime: float
    cut_construction_runtime: float
    certification_runtime: float
    exact_certification_pass: bool
    cut_validity_pass: bool
    cuts: tuple[AggregateCut, ...]


def evaluate_standard_benders_oracle(
    instance: InventoryInstance,
    x: list[list[float]],
    gamma: int,
    *,
    subproblems: list[ProductRiskSubproblem] | None = None,
) -> StandardOracleResult:
    """Evaluate exact robust recourse and return one aggregate supporting cut."""
    if gamma < 0 or gamma > instance.num_regions:
        raise ValueError("gamma must be between zero and the number of regions")
    if len(x) != instance.num_depots or any(
        len(row) != instance.num_products for row in x
    ):
        raise ValueError("x has incompatible dimensions")
    if subproblems is None:
        subproblems = [
            ProductRiskSubproblem(instance, j, gamma)
            for j in range(instance.num_products)
        ]
    if len(subproblems) != instance.num_products:
        raise ValueError("subproblem collection has incompatible dimensions")

    product_results = [
        subproblems[j].solve([x[i][j] for i in range(instance.num_depots)])
        for j in range(instance.num_products)
    ]
    product_values = [
        [worst.value for worst in result.worst_cases] for result in product_results
    ]
    composition = compose_risk_budget(product_values, gamma)
    cut_started = perf_counter()
    selected = [
        product_results[j].worst_cases[composition.allocation[j]]
        for j in range(instance.num_products)
    ]
    alpha = sum(worst.cut.alpha for worst in selected)
    beta = tuple(
        tuple(selected[j].cut.beta[i] for j in range(instance.num_products))
        for i in range(instance.num_depots)
    )
    cut = AggregateCut(
        alpha=alpha,
        beta=beta,
        generation_value=composition.value,
        generation_x=tuple(tuple(value for value in row) for row in x),
        gamma_allocation=composition.allocation,
        patterns=tuple(worst.pattern for worst in selected),
        dual_feasible=all(worst.cut.dual_feasible for worst in selected),
        strong_duality_error=abs(
            composition.value
            - (alpha + sum(beta[i][j] * x[i][j]
                           for i in range(instance.num_depots)
                           for j in range(instance.num_products)))
        ),
    )
    cut_construction_runtime = perf_counter() - cut_started
    return StandardOracleResult(
        value=composition.value,
        gamma_allocation=composition.allocation,
        cut=cut,
        product_subproblem_evaluations=instance.num_products * (gamma + 1),
        product_pattern_evaluations=sum(
            result.pattern_evaluations for result in product_results
        ),
        cut_construction_runtime=cut_construction_runtime,
    )


def solve_standard_benders(
    instance: InventoryInstance,
    x0: list[list[float]],
    budget: float,
    gamma: int,
    lambda_r: float,
    *,
    relative_gap_tolerance: float = 1e-6,
    cut_tolerance: float = 1e-7,
    objective_certification_tolerance: float = 1e-4,
    max_iterations: int = 500,
    time_limit: float | None = None,
    log_file: Path | None = None,
) -> StandardBendersResult:
    """Exact classical Benders with one aggregate robust-recourse surrogate."""
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
    master, variables = _build_standard_master(instance, x0, budget, lambda_r)
    if time_limit is not None:
        master.Params.TimeLimit = time_limit
    if log_file is not None:
        master.Params.LogFile = str(log_file)
    subproblems = [
        ProductRiskSubproblem(instance, j, gamma)
        for j in range(instance.num_products)
    ]
    cuts: list[AggregateCut] = []
    cut_signatures: set[tuple[object, ...]] = set()
    iterations: list[StandardBendersIteration] = []
    upper_bound = float("inf")
    best_solution: ReconfigurationSolution | None = None
    master_runtime = 0.0
    oracle_runtime = 0.0
    cut_construction_runtime = 0.0
    subproblem_evaluations = 0
    pattern_evaluations = 0

    for iteration in range(1, max_iterations + 1):
        master_started = perf_counter()
        master.optimize()
        master_runtime += perf_counter() - master_started
        if master.Status == GRB.TIME_LIMIT:
            raise RuntimeError("Standard Benders reached the time limit")
        if master.Status != GRB.OPTIMAL:
            raise RuntimeError(f"Exact Standard master failed with status {master.Status}")
        lower_bound = float(master.ObjVal)
        xbar = [
            [variables["x"][i, j].X for j in range(instance.num_products)]
            for i in range(instance.num_depots)
        ]

        oracle_started = perf_counter()
        oracle = evaluate_standard_benders_oracle(
            instance, xbar, gamma, subproblems=subproblems
        )
        oracle_elapsed = perf_counter() - oracle_started
        oracle_runtime += oracle_elapsed - oracle.cut_construction_runtime
        cut_construction_runtime += oracle.cut_construction_runtime
        subproblem_evaluations += oracle.product_subproblem_evaluations
        pattern_evaluations += oracle.product_pattern_evaluations
        first_stage = float(variables["first_stage"].getValue())
        candidate_upper_bound = first_stage + oracle.value
        if candidate_upper_bound <= upper_bound + 1e-8:
            upper_bound = min(upper_bound, candidate_upper_bound)
            best_solution = _solution_from_master(
                instance, x0, lambda_r, variables, oracle.value
            )

        violation = oracle.value - float(variables["theta"].X)
        cut_added = False
        if violation > cut_tolerance:
            cut_started = perf_counter()
            cut = oracle.cut
            signature = (
                round(cut.alpha, 10),
                tuple(tuple(round(value, 10) for value in row) for row in cut.beta),
            )
            if signature in cut_signatures:
                raise RuntimeError("A previously added aggregate cut remains violated")
            master.addConstr(
                variables["theta"]
                >= cut.alpha
                + sum(
                    cut.beta[i][j] * variables["x"][i, j]
                    for i in range(instance.num_depots)
                    for j in range(instance.num_products)
                ),
                name=f"aggregate_cut[{len(cuts)}]",
            )
            cut_signatures.add(signature)
            cuts.append(cut)
            cut_added = True
            cut_construction_runtime += perf_counter() - cut_started

        absolute_gap = max(0.0, upper_bound - lower_bound)
        relative_gap = absolute_gap / max(1.0, abs(upper_bound))
        iterations.append(
            StandardBendersIteration(
                iteration=iteration,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                absolute_gap=absolute_gap,
                relative_gap=relative_gap,
                master_objective=float(master.ObjVal),
                master_best_bound=float(master.ObjBound),
                master_gap=float(master.MIPGap),
                cut_violation=violation,
                cut_added=cut_added,
            )
        )
        if relative_gap <= relative_gap_tolerance and not cut_added:
            break
    else:
        raise RuntimeError("Standard Benders reached the iteration limit")

    assert best_solution is not None
    certification_started = perf_counter()
    certified = evaluate_standard_benders_oracle(
        instance, best_solution.x, gamma, subproblems=subproblems
    )
    certification_runtime = perf_counter() - certification_started
    subproblem_evaluations += certified.product_subproblem_evaluations
    pattern_evaluations += certified.product_pattern_evaluations
    certified_objective = best_solution.first_stage_expenditure + certified.value
    final_solution = ReconfigurationSolution(
        objective=certified_objective,
        first_stage_expenditure=best_solution.first_stage_expenditure,
        robust_recourse_cost=certified.value,
        y=best_solution.y,
        x=best_solution.x,
        a_plus=best_solution.a_plus,
        a_minus=best_solution.a_minus,
        reconfiguration_cost=best_solution.reconfiguration_cost,
    )
    exact_certification_pass = abs(certified_objective - upper_bound) <= objective_certification_tolerance
    cut_validity_pass = all(
        cut.dual_feasible and cut.strong_duality_error <= objective_certification_tolerance
        for cut in cuts
    )
    final_absolute_gap = max(0.0, upper_bound - iterations[-1].lower_bound)
    return StandardBendersResult(
        status="OPTIMAL" if exact_certification_pass and cut_validity_pass else "ERROR",
        solution=final_solution,
        final_lower_bound=iterations[-1].lower_bound,
        final_upper_bound=upper_bound,
        final_absolute_gap=final_absolute_gap,
        final_relative_gap=final_absolute_gap / max(1.0, abs(upper_bound)),
        iterations=tuple(iterations),
        master_solve_count=len(iterations),
        product_subproblem_evaluations=subproblem_evaluations,
        product_pattern_evaluations=pattern_evaluations,
        aggregate_cut_count=len(cuts),
        total_runtime=perf_counter() - started,
        master_runtime=master_runtime,
        oracle_runtime=oracle_runtime,
        cut_construction_runtime=cut_construction_runtime,
        certification_runtime=certification_runtime,
        exact_certification_pass=exact_certification_pass,
        cut_validity_pass=cut_validity_pass,
        cuts=tuple(cuts),
    )


def _build_standard_master(instance, x0, budget, lambda_r):
    import gurobipy as gp
    from gurobipy import GRB

    depots = range(instance.num_depots)
    products = range(instance.num_products)
    master = gp.Model(f"standard_benders_master_{instance.name}")
    master.Params.OutputFlag = 0
    apply_formal_solver_profile(master, mixed_integer=True)
    y = master.addVars(depots, vtype=GRB.BINARY, name="y")
    x = master.addVars(depots, products, lb=0, name="x")
    a_plus = master.addVars(depots, products, lb=0, name="a_plus")
    a_minus = master.addVars(depots, products, lb=0, name="a_minus")
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
    master.setObjective(first_stage + theta, GRB.MINIMIZE)
    return master, {
        "y": y,
        "x": x,
        "a_plus": a_plus,
        "a_minus": a_minus,
        "theta": theta,
        "first_stage": first_stage,
        "reconfiguration_cost": reconfiguration_cost,
    }


def _solution_from_master(instance, x0, lambda_r, variables: dict[str, Any], robust_recourse):
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
        objective=first_stage + robust_recourse,
        first_stage_expenditure=first_stage,
        robust_recourse_cost=robust_recourse,
        y=[int(round(variables["y"][i].X)) for i in range(instance.num_depots)],
        x=x,
        a_plus=a_plus,
        a_minus=a_minus,
        reconfiguration_cost=float(variables["reconfiguration_cost"].getValue()),
    )
