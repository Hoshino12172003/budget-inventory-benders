from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import math
from time import perf_counter
from pathlib import Path
from typing import Any

from .instance import InventoryInstance
from .product_risk_budget_benders import (
    PRBIteration,
    ProductCutAddition,
    _build_master,
    _solution_from_master,
)
from .product_risk_subproblem import (
    ProductCut,
    ProductRiskSubproblem,
    ProductSeparationResult,
    ProductWorstCase,
)
from .reconfiguration_model import ReconfigurationSolution
from .risk_budget_composition import compose_risk_budget
from .solver_profile import apply_formal_solver_profile


@dataclass(frozen=True)
class ProductScreeningStats:
    product_index: int
    total_patterns: int
    lp_solves: int
    safely_pruned_patterns: int
    branch_nodes: int
    upper_bound_seconds: float
    lp_seconds: float


@dataclass(frozen=True)
class PrunedProductSeparationResult:
    worst_cases: tuple[ProductWorstCase, ...]
    runtime: float
    pattern_evaluations: int
    screening: ProductScreeningStats


@dataclass(frozen=True)
class PRBAblationIteration:
    iteration: int
    lower_bound: float
    upper_bound: float
    relative_gap: float
    master_objective: float
    master_best_bound: float
    master_gap: float
    cuts_checked: int
    cuts_violated: int
    cuts_selected: int
    cuts_added: int
    master_time_seconds: float
    oracle_time_seconds: float
    cumulative_time_seconds: float
    scenario_patterns: int
    scenario_lp_solves: int
    safely_pruned_patterns: int
    pruning_fraction: float
    branch_nodes: int
    upper_bound_seconds: float


@dataclass(frozen=True)
class PRBAblationResult:
    method_id: str
    status: str
    solution: ReconfigurationSolution
    final_lower_bound: float
    final_upper_bound: float
    final_relative_gap: float
    iterations: tuple[PRBAblationIteration, ...]
    master_solve_count: int
    candidate_cuts: int
    violated_cuts: int
    selected_cuts: int
    unique_product_cuts: int
    cuts_by_product: tuple[int, ...]
    cuts_by_gamma: tuple[int, ...]
    total_runtime: float
    master_runtime: float
    separation_runtime: float
    certification_runtime: float
    scenario_patterns: int
    scenario_lp_solves: int
    safely_pruned_patterns: int
    branch_nodes: int
    upper_bound_seconds: float
    exact_certification_pass: bool
    global_risk_budget_coupling_pass: bool
    global_risk_budget_coupling_error: float
    cuts: tuple[ProductCut, ...]
    cut_additions: tuple[ProductCutAddition, ...]


class ExactProductScenarioBranchAndBound:
    """Exact product/local-budget separation with a feasible-policy upper bound."""

    def __init__(self, instance: InventoryInstance, product_index: int, gamma: int):
        import gurobipy as gp

        self.instance = instance
        self.product_index = product_index
        self.gamma = gamma
        self.model = gp.Model(f"prb_sg_product_{product_index}")
        self.model.Params.OutputFlag = 0
        apply_formal_solver_profile(self.model, mixed_integer=False)
        I = instance.num_depots
        R = instance.num_regions
        self.q = self.model.addVars(range(I), range(R), lb=0.0, name="q")
        self.u = self.model.addVars(range(R), lb=0.0, name="u")
        self.e = self.model.addVar(lb=0.0, name="e")
        self.demand_constraints = [
            self.model.addConstr(
                gp.quicksum(self.q[i, r] for i in range(I)) + self.u[r] >= 0.0,
                name=f"demand[{r}]",
            )
            for r in range(R)
        ]
        self.supply_constraints = [
            self.model.addConstr(
                gp.quicksum(self.q[i, r] for r in range(R)) <= 0.0,
                name=f"supply[{i}]",
            )
            for i in range(I)
        ]
        self.service_constraint = self.model.addConstr(
            gp.quicksum(self.u[r] for r in range(R)) - self.e <= 0.0,
            name="service",
        )
        j = product_index
        self.model.setObjective(
            gp.quicksum(
                instance.transport_cost[i][r][j] * self.q[i, r]
                for i in range(I)
                for r in range(R)
            )
            + gp.quicksum(instance.shortage_penalty[r][j] * self.u[r] for r in range(R))
            + instance.service_penalty[j] * self.e
        )
        self._last_pattern: dict[int, tuple[int, ...]] = {}

    def _demand(self, pattern: tuple[int, ...]) -> tuple[float, ...]:
        j = self.product_index
        shocked = frozenset(pattern)
        return tuple(
            float(self.instance.base_demand[r][j])
            + (float(self.instance.demand_deviation[r][j]) if r in shocked else 0.0)
            for r in range(self.instance.num_regions)
        )

    def _evaluate(self, x: tuple[float, ...], pattern: tuple[int, ...]) -> ProductWorstCase:
        from gurobipy import GRB

        demand = self._demand(pattern)
        allowance = (1.0 - self.instance.service_level[self.product_index]) * sum(demand)
        for constraint, rhs in zip(self.demand_constraints, demand, strict=True):
            constraint.RHS = rhs
        for constraint, rhs in zip(self.supply_constraints, x, strict=True):
            constraint.RHS = rhs
        self.service_constraint.RHS = allowance
        self.model.optimize()
        if self.model.Status != GRB.OPTIMAL:
            raise RuntimeError(
                f"product scenario LP status={self.model.Status}, "
                f"product={self.product_index}, pattern={pattern}"
            )
        demand_dual = tuple(float(constraint.Pi) for constraint in self.demand_constraints)
        supply_dual = tuple(float(constraint.Pi) for constraint in self.supply_constraints)
        service_dual = float(self.service_constraint.Pi)
        alpha = sum(value * dual for value, dual in zip(demand, demand_dual, strict=True))
        alpha += allowance * service_dual
        value = float(self.model.ObjVal)
        dual_value = alpha + sum(
            coefficient * amount for coefficient, amount in zip(supply_dual, x, strict=True)
        )
        j = self.product_index
        dual_feasible = (
            all(value >= -1e-8 for value in demand_dual)
            and all(value <= 1e-8 for value in supply_dual)
            and service_dual <= 1e-8
            and all(
                demand_dual[r] + supply_dual[i]
                <= self.instance.transport_cost[i][r][j] + 1e-7
                for i in range(self.instance.num_depots)
                for r in range(self.instance.num_regions)
            )
            and all(
                demand_dual[r] + service_dual
                <= self.instance.shortage_penalty[r][j] + 1e-7
                for r in range(self.instance.num_regions)
            )
            and -service_dual <= self.instance.service_penalty[j] + 1e-7
        )
        cut = ProductCut(
            j,
            len(pattern),
            alpha,
            supply_dual,
            value,
            x,
            pattern,
            dual_feasible,
            abs(value - dual_value),
        )
        return ProductWorstCase(
            j,
            len(pattern),
            value,
            pattern,
            tuple(
                tuple(float(self.q[i, r].X) for r in range(self.instance.num_regions))
                for i in range(self.instance.num_depots)
            ),
            tuple(float(self.u[r].X) for r in range(self.instance.num_regions)),
            float(self.e.X),
            demand_dual,
            supply_dual,
            service_dual,
            cut,
        )

    def _feasible_policy_bound(
        self, x: tuple[float, ...]
    ) -> tuple[float, tuple[float, ...]]:
        instance = self.instance
        j = self.product_index
        I, R = instance.num_depots, instance.num_regions
        demand = [float(instance.base_demand[r][j]) for r in range(R)]
        remaining_supply = [max(0.0, float(value)) for value in x]
        remaining_demand = demand.copy()
        shipment = [[0.0 for _ in range(R)] for _ in range(I)]
        service_target = float(instance.service_level[j]) * sum(demand)
        service_shipped = 0.0
        service_edges = sorted(
            (
                float(instance.shortage_penalty[r][j])
                + float(instance.service_penalty[j])
                - float(instance.transport_cost[i][r][j]),
                i,
                r,
            )
            for i in range(I)
            for r in range(R)
        )
        for saving, i, r in reversed(service_edges):
            if saving <= 0.0 or service_shipped >= service_target:
                break
            quantity = min(
                remaining_supply[i],
                remaining_demand[r],
                service_target - service_shipped,
            )
            shipment[i][r] += quantity
            remaining_supply[i] -= quantity
            remaining_demand[r] -= quantity
            service_shipped += quantity
        ordinary_edges = sorted(
            (
                float(instance.shortage_penalty[r][j])
                - float(instance.transport_cost[i][r][j]),
                i,
                r,
            )
            for i in range(I)
            for r in range(R)
        )
        for saving, i, r in reversed(ordinary_edges):
            if saving <= 0.0:
                break
            quantity = min(remaining_supply[i], remaining_demand[r])
            shipment[i][r] += quantity
            remaining_supply[i] -= quantity
            remaining_demand[r] -= quantity
        service_violation = max(
            0.0,
            sum(remaining_demand) - (1.0 - float(instance.service_level[j])) * sum(demand),
        )
        value = sum(
            float(instance.transport_cost[i][r][j]) * shipment[i][r]
            for i in range(I)
            for r in range(R)
        )
        value += sum(
            float(instance.shortage_penalty[r][j]) * remaining_demand[r]
            for r in range(R)
        )
        value += float(instance.service_penalty[j]) * service_violation
        increments = tuple(
            float(instance.demand_deviation[r][j])
            * (
                float(instance.shortage_penalty[r][j])
                + float(instance.service_penalty[j]) * float(instance.service_level[j])
            )
            for r in range(R)
        )
        return value, increments

    def solve(self, x: list[float]) -> PrunedProductSeparationResult:
        if len(x) != self.instance.num_depots:
            raise ValueError("product inventory vector has incompatible length")
        if min(x) < -1e-7:
            raise ValueError("product inventory contains a materially negative value")
        clean_x = tuple(max(0.0, float(value)) for value in x)
        started = perf_counter()
        bound_started = perf_counter()
        base_bound, increments = self._feasible_policy_bound(clean_x)
        upper_bound_seconds = perf_counter() - bound_started
        order = tuple(sorted(range(self.instance.num_regions), key=lambda r: (increments[r], r), reverse=True))
        worst_cases: list[ProductWorstCase] = []
        lp_solves = 0
        pruned = 0
        branch_nodes = 0
        lp_seconds = 0.0
        total_patterns = 0

        for local_gamma in range(self.gamma + 1):
            total_patterns += math.comb(self.instance.num_regions, local_gamma)
            candidates = []
            historical = self._last_pattern.get(local_gamma)
            if historical is not None:
                candidates.append(historical)
            candidates.append(tuple(sorted(order[:local_gamma])))
            cache: dict[tuple[int, ...], ProductWorstCase] = {}
            pruned_patterns: set[tuple[int, ...]] = set()
            best: ProductWorstCase | None = None

            def evaluate(pattern: tuple[int, ...]) -> None:
                nonlocal best, lp_solves, lp_seconds
                canonical = tuple(sorted(pattern))
                if canonical not in cache:
                    lp_started = perf_counter()
                    cache[canonical] = self._evaluate(clean_x, canonical)
                    lp_seconds += perf_counter() - lp_started
                    lp_solves += 1
                if best is None or cache[canonical].value > best.value + 1e-9:
                    best = cache[canonical]

            for pattern in candidates:
                evaluate(pattern)

            def visit(index: int, selected: tuple[int, ...]) -> None:
                nonlocal branch_nodes, upper_bound_seconds
                assert best is not None
                branch_nodes += 1
                need = local_gamma - len(selected)
                remaining = len(order) - index
                if need < 0 or remaining < need:
                    return
                bound_started = perf_counter()
                node_bound = base_bound + sum(increments[r] for r in selected)
                if need:
                    node_bound += sum(sorted((increments[r] for r in order[index:]), reverse=True)[:need])
                upper_bound_seconds += perf_counter() - bound_started
                if node_bound <= best.value - 1e-9:
                    for suffix in combinations(order[index:], need):
                        pattern = tuple(sorted((*selected, *suffix)))
                        if pattern not in cache:
                            pruned_patterns.add(pattern)
                    return
                if need == 0:
                    if tuple(sorted(selected)) not in cache:
                        evaluate(selected)
                    return
                if index == len(order):
                    return
                visit(index + 1, (*selected, order[index]))
                visit(index + 1, selected)

            visit(0, ())
            assert best is not None
            accounted = len(cache) + len(pruned_patterns)
            if accounted != math.comb(self.instance.num_regions, local_gamma):
                raise RuntimeError("product scenario branch accounting is incomplete")
            pruned += len(pruned_patterns)
            self._last_pattern[local_gamma] = best.pattern
            worst_cases.append(best)

        stats = ProductScreeningStats(
            self.product_index,
            total_patterns,
            lp_solves,
            pruned,
            branch_nodes,
            upper_bound_seconds,
            lp_seconds,
        )
        return PrunedProductSeparationResult(
            tuple(worst_cases),
            perf_counter() - started,
            total_patterns,
            stats,
        )

    def close(self) -> None:
        self.model.dispose()


def select_adaptive_cuts(
    violations: list[tuple[float, int, ProductWorstCase]],
    *,
    iteration: int,
    relative_gap: float,
    existing_cut_count: int,
) -> list[tuple[float, int, ProductWorstCase]]:
    """Choose a deterministic subset while guaranteeing at least one new cut."""
    if not violations:
        return []
    ordered = sorted(violations, key=lambda item: (-item[0], item[1], item[2].local_gamma))
    if relative_gap <= 1e-3:
        return ordered
    base = math.ceil(math.sqrt(len(ordered)))
    burden_cap = max(1, 12 - existing_cut_count // 20)
    iteration_floor = min(len(ordered), 1 + iteration // 5)
    budget = min(len(ordered), max(iteration_floor, min(base, burden_cap)))
    selected: list[tuple[float, int, ProductWorstCase]] = []
    seen_products: set[int] = set()
    for item in ordered:
        if item[1] not in seen_products:
            selected.append(item)
            seen_products.add(item[1])
            if len(selected) == budget:
                return selected
    for item in ordered:
        if item not in selected:
            selected.append(item)
            if len(selected) == budget:
                break
    return selected


def solve_prb_ablation(
    instance: InventoryInstance,
    x0: list[list[float]],
    budget: float,
    gamma: int,
    lambda_r: float,
    *,
    method_id: str,
    scenario_screening: bool,
    adaptive_cut_selection: bool,
    relative_gap_tolerance: float = 1e-6,
    cut_tolerance: float = 1e-7,
    max_iterations: int = 500,
    log_file: Path | None = None,
) -> PRBAblationResult:
    """Run PRB with only the two declared ablation mechanisms varied."""
    from gurobipy import GRB

    if method_id not in {"PRB-SG", "A-PRB", "A-PRB-SG"}:
        raise ValueError("method_id is outside the frozen ablation set")
    if scenario_screening != ("SG" in method_id):
        raise ValueError("method_id and scenario_screening disagree")
    if adaptive_cut_selection != method_id.startswith("A-"):
        raise ValueError("method_id and adaptive_cut_selection disagree")
    started = perf_counter()
    master, variables = _build_master(instance, x0, budget, gamma, lambda_r)
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        master.Params.OutputFlag = 1
        master.Params.LogToConsole = 0
        master.Params.LogFile = str(log_file.resolve())
    subproblems: list[Any] = [
        ExactProductScenarioBranchAndBound(instance, j, gamma)
        if scenario_screening
        else ProductRiskSubproblem(instance, j, gamma)
        for j in range(instance.num_products)
    ]
    cuts: list[ProductCut] = []
    cut_additions: list[ProductCutAddition] = []
    signatures: set[tuple[Any, ...]] = set()
    cuts_by_product = [0] * instance.num_products
    cuts_by_gamma = [0] * (gamma + 1)
    iterations: list[PRBAblationIteration] = []
    upper_bound = float("inf")
    best_solution: ReconfigurationSolution | None = None
    master_runtime = 0.0
    separation_runtime = 0.0
    candidate_cuts = violated_cuts = selected_cuts = 0
    scenario_patterns = scenario_lp_solves = safely_pruned = branch_nodes = 0
    upper_bound_seconds = 0.0
    final_composition = None

    try:
        for iteration in range(1, max_iterations + 1):
            master_started = perf_counter()
            master.optimize()
            iteration_master = perf_counter() - master_started
            master_runtime += iteration_master
            if master.Status != GRB.OPTIMAL:
                raise RuntimeError(f"Exact master failed with status {master.Status}")
            lower_bound = float(master.ObjVal)
            xbar = [
                [variables["x"][i, j].X for j in range(instance.num_products)]
                for i in range(instance.num_depots)
            ]
            separation_started = perf_counter()
            product_results = [
                subproblems[j].solve([xbar[i][j] for i in range(instance.num_depots)])
                for j in range(instance.num_products)
            ]
            iteration_oracle = perf_counter() - separation_started
            separation_runtime += iteration_oracle
            iteration_patterns = sum(result.pattern_evaluations for result in product_results)
            if scenario_screening:
                iteration_lp = sum(result.screening.lp_solves for result in product_results)
                iteration_pruned = sum(result.screening.safely_pruned_patterns for result in product_results)
                iteration_nodes = sum(result.screening.branch_nodes for result in product_results)
                iteration_bound = sum(result.screening.upper_bound_seconds for result in product_results)
            else:
                iteration_lp = iteration_patterns
                iteration_pruned = iteration_nodes = 0
                iteration_bound = 0.0
            scenario_patterns += iteration_patterns
            scenario_lp_solves += iteration_lp
            safely_pruned += iteration_pruned
            branch_nodes += iteration_nodes
            upper_bound_seconds += iteration_bound
            values = [[case.value for case in result.worst_cases] for result in product_results]
            composition = compose_risk_budget(values, gamma)
            final_composition = composition
            first_stage = float(variables["first_stage"].getValue())
            candidate_upper = first_stage + composition.value
            if candidate_upper <= upper_bound + 1e-8:
                upper_bound = min(upper_bound, candidate_upper)
                best_solution = _solution_from_master(
                    instance, x0, lambda_r, master, variables, composition.value
                )
            gap = max(0.0, upper_bound - lower_bound) / max(1.0, abs(upper_bound))
            violations: list[tuple[float, int, ProductWorstCase]] = []
            for j, result in enumerate(product_results):
                for worst in result.worst_cases:
                    violation = worst.value - variables["eta"][j, worst.local_gamma].X
                    if violation > cut_tolerance:
                        violations.append((violation, j, worst))
            selected = (
                select_adaptive_cuts(
                    violations,
                    iteration=iteration,
                    relative_gap=gap,
                    existing_cut_count=len(cuts),
                )
                if adaptive_cut_selection
                else sorted(violations, key=lambda item: (item[1], item[2].local_gamma))
            )
            candidate_cuts += instance.num_products * (gamma + 1)
            violated_cuts += len(violations)
            selected_cuts += len(selected)
            for violation, j, worst in selected:
                cut = worst.cut
                signature = (
                    j,
                    worst.local_gamma,
                    round(cut.alpha, 10),
                    tuple(round(value, 10) for value in cut.beta),
                )
                if signature in signatures:
                    raise RuntimeError("a previously added product cut remains violated")
                master.addConstr(
                    variables["eta"][j, worst.local_gamma]
                    >= cut.alpha
                    + sum(
                        cut.beta[i] * variables["x"][i, j]
                        for i in range(instance.num_depots)
                    ),
                    name=f"{method_id}_cut[{j},{worst.local_gamma},{cuts_by_product[j]}]",
                )
                signatures.add(signature)
                cuts.append(cut)
                cut_additions.append(ProductCutAddition(iteration, violation, cut))
                cuts_by_product[j] += 1
                cuts_by_gamma[worst.local_gamma] += 1
            iterations.append(
                PRBAblationIteration(
                    iteration,
                    lower_bound,
                    upper_bound,
                    gap,
                    float(master.ObjVal),
                    float(master.ObjBound),
                    float(master.MIPGap),
                    instance.num_products * (gamma + 1),
                    len(violations),
                    len(selected),
                    len(selected),
                    iteration_master,
                    iteration_oracle,
                    perf_counter() - started,
                    iteration_patterns,
                    iteration_lp,
                    iteration_pruned,
                    iteration_pruned / iteration_patterns if iteration_patterns else 0.0,
                    iteration_nodes,
                    iteration_bound,
                )
            )
            if gap <= relative_gap_tolerance and not violations:
                break
            if not selected:
                raise RuntimeError("PRB ablation stalled without an admissible new cut")
        else:
            raise RuntimeError("PRB ablation reached the iteration limit")

        assert best_solution is not None and final_composition is not None
        certification_started = perf_counter()
        certified_results = []
        for j in range(instance.num_products):
            certifier = ProductRiskSubproblem(instance, j, gamma)
            try:
                certified_results.append(certifier.solve(
                    [best_solution.x[i][j] for i in range(instance.num_depots)]
                ))
            finally:
                certifier.model.dispose()
        certified_values = [
            [case.value for case in result.worst_cases] for result in certified_results
        ]
        certified_composition = compose_risk_budget(certified_values, gamma)
        certification_runtime = perf_counter() - certification_started
        certified_objective = best_solution.first_stage_expenditure + certified_composition.value
        final_solution = ReconfigurationSolution(
            certified_objective,
            best_solution.first_stage_expenditure,
            certified_composition.value,
            best_solution.y,
            best_solution.x,
            best_solution.a_plus,
            best_solution.a_minus,
            best_solution.reconfiguration_cost,
        )
        exact_pass = abs(certified_objective - upper_bound) <= 1e-4
        coupling_error = abs(float(variables["theta"].X) - final_composition.value)
        coupling_pass = coupling_error <= 1e-6
        return PRBAblationResult(
            method_id,
            "OPTIMAL" if exact_pass and coupling_pass else "ERROR",
            final_solution,
            iterations[-1].lower_bound,
            upper_bound,
            max(0.0, upper_bound - iterations[-1].lower_bound) / max(1.0, abs(upper_bound)),
            tuple(iterations),
            len(iterations),
            candidate_cuts,
            violated_cuts,
            selected_cuts,
            len(cuts),
            tuple(cuts_by_product),
            tuple(cuts_by_gamma),
            perf_counter() - started,
            master_runtime,
            separation_runtime,
            certification_runtime,
            scenario_patterns,
            scenario_lp_solves,
            safely_pruned,
            branch_nodes,
            upper_bound_seconds,
            exact_pass,
            coupling_pass,
            coupling_error,
            tuple(cuts),
            tuple(cut_additions),
        )
    finally:
        for subproblem in subproblems:
            close = getattr(subproblem, "close", None)
            if close is not None:
                close()
        master.dispose()
