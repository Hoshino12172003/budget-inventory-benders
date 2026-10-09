from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from .instance import InventoryInstance
from .reconfiguration_model import ReconfigurationSolution
from .solver_profile import apply_formal_solver_profile


PURE_BENDERS_EXACT = True


class PureBendersTimeout(RuntimeError):
    """Raised when the shared Pure Benders wall-clock limit is exhausted."""


@dataclass(frozen=True)
class PureAggregateCut:
    alpha: float
    beta: tuple[tuple[float, ...], ...]
    generation_value: float
    generation_x: tuple[tuple[float, ...], ...]
    shock_pattern: tuple[tuple[int, int], ...]
    dual_feasible: bool
    strong_duality_error: float

    def value_at(self, x: list[list[float]]) -> float:
        return self.alpha + sum(
            self.beta[i][j] * x[i][j]
            for i in range(len(self.beta))
            for j in range(len(self.beta[i]))
        )


@dataclass(frozen=True)
class GlobalAdversarialResult:
    value: float
    cut: PureAggregateCut
    fixed_scenario_value: float
    mip_runtime: float
    certification_runtime: float
    binary_variables: int
    continuous_variables: int
    constraints: int


@dataclass(frozen=True)
class PureBendersIteration:
    iteration: int
    lower_bound: float
    upper_bound: float
    absolute_gap: float
    relative_gap: float
    cut_violation: float
    cut_added: bool
    master_time_seconds: float = 0.0
    oracle_time_seconds: float = 0.0
    certification_time_seconds: float = 0.0
    cumulative_time_seconds: float = 0.0


@dataclass(frozen=True)
class PureBendersResult:
    status: str
    solution: ReconfigurationSolution
    final_lower_bound: float
    final_upper_bound: float
    final_absolute_gap: float
    final_relative_gap: float
    iterations: tuple[PureBendersIteration, ...]
    aggregate_cut_count: int
    total_runtime: float
    master_runtime: float
    global_oracle_runtime: float
    certification_runtime: float
    exact_certification_pass: bool
    cut_validity_pass: bool
    cuts: tuple[PureAggregateCut, ...]


def estimate_global_adversarial_size(instance: InventoryInstance) -> dict[str, int]:
    """Return the algebraic size of the single global adversarial MILP."""
    i, r, j = instance.num_depots, instance.num_regions, instance.num_products
    return {
        "binary_variables": r * j,
        "continuous_variables": i * j + 3 * r * j + j,
        "total_variables": r * j + i * j + 3 * r * j + j,
        "constraints": i * r * j + 7 * r * j + 1,
    }


def evaluate_fixed_scenario_recourse_global(
    instance: InventoryInstance,
    x: list[list[float]],
    shock_pattern: tuple[tuple[int, int], ...],
    *,
    time_limit: float | None = None,
) -> float:
    """Solve one all-product recourse LP without product decomposition."""
    import gurobipy as gp
    from gurobipy import GRB

    _validate_x(instance, x)
    active = set(shock_pattern)
    depots = range(instance.num_depots)
    regions = range(instance.num_regions)
    products = range(instance.num_products)
    model = gp.Model(f"pure_global_fixed_recourse_{instance.name}")
    model.Params.OutputFlag = 0
    apply_formal_solver_profile(model, mixed_integer=False)
    if time_limit is not None:
        model.Params.TimeLimit = max(time_limit, 0.001)
    q = model.addVars(depots, regions, products, lb=0.0, name="q")
    u = model.addVars(regions, products, lb=0.0, name="u")
    e = model.addVars(products, lb=0.0, name="e")
    demand = {
        (r, j): instance.base_demand[r][j]
        + (instance.demand_deviation[r][j] if (r, j) in active else 0.0)
        for r in regions for j in products
    }
    for r in regions:
        for j in products:
            model.addConstr(gp.quicksum(q[i, r, j] for i in depots) + u[r, j] >= demand[r, j])
    for i in depots:
        for j in products:
            model.addConstr(gp.quicksum(q[i, r, j] for r in regions) <= x[i][j])
    for j in products:
        model.addConstr(
            gp.quicksum(u[r, j] for r in regions) - e[j]
            <= (1.0 - instance.service_level[j])
            * sum(demand[r, j] for r in regions)
        )
    objective = gp.quicksum(
        instance.transport_cost[i][r][j] * q[i, r, j]
        for i in depots for r in regions for j in products
    )
    objective += gp.quicksum(
        instance.shortage_penalty[r][j] * u[r, j]
        for r in regions for j in products
    )
    objective += gp.quicksum(instance.service_penalty[j] * e[j] for j in products)
    model.setObjective(objective, GRB.MINIMIZE)
    model.optimize()
    if model.Status == GRB.TIME_LIMIT:
        raise PureBendersTimeout("global fixed-scenario certification reached the time limit")
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"global fixed-scenario recourse failed with status {model.Status}")
    return float(model.ObjVal)


class GlobalRobustAdversarialSubproblem:
    """One global dual MILP over every region-product shock indicator."""

    def __init__(self, instance: InventoryInstance, gamma: int) -> None:
        import gurobipy as gp
        from gurobipy import GRB

        if gamma < 0 or gamma > instance.num_regions * instance.num_products:
            raise ValueError("gamma exceeds the global cardinality uncertainty set")
        self.instance = instance
        self.gamma = gamma
        depots = range(instance.num_depots)
        regions = range(instance.num_regions)
        products = range(instance.num_products)
        model = gp.Model(f"pure_global_adversary_{instance.name}")
        model.Params.OutputFlag = 0
        apply_formal_solver_profile(model, mixed_integer=True)
        z = model.addVars(regions, products, vtype=GRB.BINARY, name="z")
        pi = model.addVars(regions, products, lb=0.0, name="pi")
        mu = model.addVars(depots, products, lb=-GRB.INFINITY, ub=0.0, name="mu")
        kappa = model.addVars(
            products,
            lb=0.0,
            ub={j: instance.service_penalty[j] for j in products},
            name="kappa",
        )
        w = model.addVars(regions, products, lb=0.0, name="z_pi")
        t = model.addVars(regions, products, lb=0.0, name="z_kappa")
        for r in regions:
            for j in products:
                for i in depots:
                    model.addConstr(pi[r, j] + mu[i, j] <= instance.transport_cost[i][r][j])
                model.addConstr(pi[r, j] - kappa[j] <= instance.shortage_penalty[r][j])
                pi_bound = instance.shortage_penalty[r][j] + instance.service_penalty[j]
                model.addConstr(w[r, j] <= pi[r, j])
                model.addConstr(w[r, j] <= pi_bound * z[r, j])
                model.addConstr(w[r, j] >= pi[r, j] - pi_bound * (1.0 - z[r, j]))
                kappa_bound = instance.service_penalty[j]
                model.addConstr(t[r, j] <= kappa[j])
                model.addConstr(t[r, j] <= kappa_bound * z[r, j])
                model.addConstr(t[r, j] >= kappa[j] - kappa_bound * (1.0 - z[r, j]))
        model.addConstr(gp.quicksum(z[r, j] for r in regions for j in products) <= gamma)
        self.model = model
        self.variables = {"z": z, "pi": pi, "mu": mu, "kappa": kappa, "w": w, "t": t}

    def solve(
        self,
        x: list[list[float]],
        *,
        time_limit: float | None = None,
        certify: bool = True,
    ) -> GlobalAdversarialResult:
        import gurobipy as gp
        from gurobipy import GRB

        _validate_x(self.instance, x)
        instance = self.instance
        depots = range(instance.num_depots)
        regions = range(instance.num_regions)
        products = range(instance.num_products)
        v = self.variables
        base = gp.quicksum(
            instance.base_demand[r][j] * v["pi"][r, j]
            for r in regions for j in products
        )
        base += gp.quicksum(x[i][j] * v["mu"][i, j] for i in depots for j in products)
        base -= gp.quicksum(
            (1.0 - instance.service_level[j])
            * sum(instance.base_demand[r][j] for r in regions)
            * v["kappa"][j]
            for j in products
        )
        deviation = gp.quicksum(
            instance.demand_deviation[r][j]
            * (v["w"][r, j] - (1.0 - instance.service_level[j]) * v["t"][r, j])
            for r in regions for j in products
        )
        self.model.setObjective(base + deviation, GRB.MAXIMIZE)
        if time_limit is not None:
            self.model.Params.TimeLimit = max(time_limit, 0.001)
        started = perf_counter()
        self.model.optimize()
        mip_runtime = perf_counter() - started
        if self.model.Status == GRB.TIME_LIMIT:
            raise PureBendersTimeout("global robust adversarial MILP reached the time limit")
        if self.model.Status != GRB.OPTIMAL:
            raise RuntimeError(f"global robust adversarial MILP failed with status {self.model.Status}")
        pattern = tuple(
            (r, j) for r in regions for j in products if v["z"][r, j].X > 0.5
        )
        beta = tuple(
            tuple(float(v["mu"][i, j].X) for j in products) for i in depots
        )
        value = float(self.model.ObjVal)
        alpha = value - sum(beta[i][j] * x[i][j] for i in depots for j in products)
        certification_started = perf_counter()
        certification_limit = None
        if time_limit is not None:
            certification_limit = time_limit - mip_runtime
            if certification_limit <= 0:
                raise PureBendersTimeout("global oracle exhausted its wall-clock allowance before certification")
        fixed_value = (
            evaluate_fixed_scenario_recourse_global(
                instance, x, pattern, time_limit=certification_limit
            )
            if certify else value
        )
        certification_runtime = perf_counter() - certification_started
        dual_feasible = _dual_feasible(instance, v)
        cut = PureAggregateCut(
            alpha=alpha,
            beta=beta,
            generation_value=value,
            generation_x=tuple(tuple(row) for row in x),
            shock_pattern=pattern,
            dual_feasible=dual_feasible,
            strong_duality_error=abs(value - fixed_value),
        )
        size = estimate_global_adversarial_size(instance)
        return GlobalAdversarialResult(
            value=fixed_value,
            cut=cut,
            fixed_scenario_value=fixed_value,
            mip_runtime=mip_runtime,
            certification_runtime=certification_runtime,
            binary_variables=size["binary_variables"],
            continuous_variables=size["continuous_variables"],
            constraints=size["constraints"],
        )


def solve_pure_benders(
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
    cut_diagnostic_file: Path | None = None,
) -> PureBendersResult:
    from gurobipy import GRB

    _validate_x(instance, x0)
    if lambda_r < 0:
        raise ValueError("lambda_r must be nonnegative")
    started = perf_counter()
    master, variables = _build_pure_master(instance, x0, budget, lambda_r)
    if log_file is not None:
        master.Params.LogFile = str(log_file)
    oracle = GlobalRobustAdversarialSubproblem(instance, gamma)
    cuts: list[PureAggregateCut] = []
    signatures: set[tuple[object, ...]] = set()
    cut_constraints: list[tuple[Any, int]] = []
    iterations: list[PureBendersIteration] = []
    upper_bound = float("inf")
    best_solution: ReconfigurationSolution | None = None
    master_runtime = 0.0
    oracle_runtime = 0.0
    certification_runtime = 0.0

    def remaining() -> float | None:
        if time_limit is None:
            return None
        value = time_limit - (perf_counter() - started)
        if value <= 0:
            raise PureBendersTimeout("Pure Benders reached its total wall-clock limit")
        return value

    for iteration in range(1, max_iterations + 1):
        current_limit = remaining()
        if current_limit is not None:
            master.Params.TimeLimit = current_limit
        master_started = perf_counter()
        master.optimize()
        iteration_master_runtime = perf_counter() - master_started
        master_runtime += iteration_master_runtime
        if master.Status == GRB.TIME_LIMIT:
            raise PureBendersTimeout("Pure Benders master reached the wall-clock limit")
        if master.Status != GRB.OPTIMAL:
            raise RuntimeError(f"Pure Benders master failed with status {master.Status}")
        lower_bound = float(master.ObjVal)
        xbar = [[variables["x"][i, j].X for j in range(instance.num_products)]
                for i in range(instance.num_depots)]
        evaluated = oracle.solve(xbar, time_limit=remaining())
        oracle_runtime += evaluated.mip_runtime
        certification_runtime += evaluated.certification_runtime
        first_stage = float(variables["first_stage"].getValue())
        candidate_upper = first_stage + evaluated.value
        if candidate_upper <= upper_bound + 1e-8:
            upper_bound = min(upper_bound, candidate_upper)
            best_solution = _solution_from_master(instance, x0, variables, evaluated.value)
        violation = evaluated.value - float(variables["theta"].X)
        cut_added = False
        if violation > cut_tolerance:
            cut = evaluated.cut
            signature = _cut_signature(cut)
            if signature in signatures:
                if cut_diagnostic_file is not None:
                    _write_duplicate_cut_diagnostic(
                        cut_diagnostic_file,
                        master=master,
                        variables=variables,
                        cuts=cuts,
                        cut_constraints=cut_constraints,
                        candidate=cut,
                        certified_oracle_value=evaluated.value,
                        current_iteration=iteration,
                        cut_tolerance=cut_tolerance,
                    )
                raise RuntimeError("a previously added Pure Benders cut remains violated")
            constraint = master.addConstr(
                variables["theta"] >= cut.alpha + sum(
                    cut.beta[i][j] * variables["x"][i, j]
                    for i in range(instance.num_depots) for j in range(instance.num_products)
                ),
                name=f"pure_aggregate_cut[{len(cuts)}]",
            )
            signatures.add(signature)
            cuts.append(cut)
            cut_constraints.append((constraint, iteration))
            cut_added = True
        absolute_gap = max(0.0, upper_bound - lower_bound)
        relative_gap = absolute_gap / max(1.0, abs(upper_bound))
        iterations.append(PureBendersIteration(
            iteration=iteration,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            absolute_gap=absolute_gap,
            relative_gap=relative_gap,
            cut_violation=violation,
            cut_added=cut_added,
            master_time_seconds=iteration_master_runtime,
            oracle_time_seconds=evaluated.mip_runtime,
            certification_time_seconds=evaluated.certification_runtime,
            cumulative_time_seconds=perf_counter() - started,
        ))
        if relative_gap <= relative_gap_tolerance and not cut_added:
            break
    else:
        raise RuntimeError("Pure Benders reached the iteration limit")

    assert best_solution is not None
    final = oracle.solve(best_solution.x, time_limit=remaining())
    oracle_runtime += final.mip_runtime
    certification_runtime += final.certification_runtime
    objective = best_solution.first_stage_expenditure + final.value
    solution = ReconfigurationSolution(
        objective=objective,
        first_stage_expenditure=best_solution.first_stage_expenditure,
        robust_recourse_cost=final.value,
        y=best_solution.y,
        x=best_solution.x,
        a_plus=best_solution.a_plus,
        a_minus=best_solution.a_minus,
        reconfiguration_cost=best_solution.reconfiguration_cost,
    )
    exact = abs(objective - upper_bound) <= objective_certification_tolerance
    valid = all(c.dual_feasible and c.strong_duality_error <= objective_certification_tolerance for c in cuts)
    final_gap = max(0.0, upper_bound - iterations[-1].lower_bound)
    return PureBendersResult(
        "OPTIMAL" if exact and valid else "ERROR",
        solution,
        iterations[-1].lower_bound,
        upper_bound,
        final_gap,
        final_gap / max(1.0, abs(upper_bound)),
        tuple(iterations),
        len(cuts),
        perf_counter() - started,
        master_runtime,
        oracle_runtime,
        certification_runtime,
        exact,
        valid,
        tuple(cuts),
    )


def _cut_signature(cut: PureAggregateCut) -> tuple[object, ...]:
    return (
        round(cut.alpha, 10),
        tuple(round(value, 10) for row in cut.beta for value in row),
    )


def _write_duplicate_cut_diagnostic(
    path: Path,
    *,
    master: Any,
    variables: dict[str, Any],
    cuts: list[PureAggregateCut],
    cut_constraints: list[tuple[Any, int]],
    candidate: PureAggregateCut,
    certified_oracle_value: float,
    current_iteration: int,
    cut_tolerance: float,
) -> None:
    master.update()
    theta = float(variables["theta"].X)
    x = [
        [float(variables["x"][i, j].X) for j in range(len(candidate.beta[i]))]
        for i in range(len(candidate.beta))
    ]
    feasibility_tolerance = float(master.Params.FeasibilityTol)
    records = [
        _cut_validation_record(
            master,
            variables,
            cut,
            constraint,
            cut_id=cut_id,
            iteration_added=iteration_added,
            current_iteration=current_iteration,
            feasibility_tolerance=feasibility_tolerance,
        )
        for cut_id, (cut, (constraint, iteration_added)) in enumerate(
            zip(cuts, cut_constraints, strict=True)
        )
    ]
    matching_ids = [
        cut_id for cut_id, cut in enumerate(cuts)
        if _cut_signature(cut) == _cut_signature(candidate)
    ]
    matching_records = [record for record in records if record["cut_id"] in matching_ids]
    offender = max(matching_records, key=lambda record: record["signed_violation"])
    previous = cuts[offender["cut_id"]]
    coefficient_deltas = [
        abs(candidate.beta[i][j] - previous.beta[i][j])
        for i in range(len(candidate.beta))
        for j in range(len(candidate.beta[i]))
    ]
    candidate_rhs = candidate.value_at(x)
    payload = {
        "schema": "pure_benders_duplicate_cut_diagnostic_v1",
        "current_master_iteration": current_iteration,
        "cut_check_tolerance": cut_tolerance,
        "solver": {
            "master_status": int(master.Status),
            "master_status_name": "OPTIMAL" if int(master.Status) == 2 else str(master.Status),
            "MIPGap": float(master.MIPGap),
            "FeasibilityTol": feasibility_tolerance,
            "IntFeasTol": float(master.Params.IntFeasTol),
            "OptimalityTol": float(master.Params.OptimalityTol),
        },
        "theta_value": theta,
        "trigger": {
            "certified_oracle_value": certified_oracle_value,
            "candidate_cut_generation_value": candidate.generation_value,
            "candidate_cut_rhs_at_current_x": candidate_rhs,
            "certified_value_minus_theta": certified_oracle_value - theta,
            "candidate_cut_rhs_minus_theta": candidate_rhs - theta,
            "candidate_strong_duality_error": candidate.strong_duality_error,
            "matching_previous_cut_ids": matching_ids,
            "signature_round_decimal_places": 10,
            "candidate_vs_matching_cut": {
                "alpha_absolute_difference": abs(candidate.alpha - previous.alpha),
                "maximum_beta_absolute_difference": max(coefficient_deltas, default=0.0),
                "exact_alpha_equal": candidate.alpha == previous.alpha,
                "exact_beta_equal": candidate.beta == previous.beta,
            },
        },
        "max_previous_cut_violation": max(
            record["signed_violation"] for record in records
        ),
        "offending_cut_id": offender["cut_id"],
        "iteration_added": offender["iteration_added"],
        "iteration_detected": current_iteration,
        "offending_cut_signed_violation": offender["signed_violation"],
        "offending_cut_absolute_violation": offender["absolute_violation"],
        "previous_cuts": records,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _cut_validation_record(
    master: Any,
    variables: dict[str, Any],
    cut: PureAggregateCut,
    constraint: Any,
    *,
    cut_id: int,
    iteration_added: int,
    current_iteration: int,
    feasibility_tolerance: float,
) -> dict[str, Any]:
    theta = float(variables["theta"].X)
    x = [
        [float(variables["x"][i, j].X) for j in range(len(cut.beta[i]))]
        for i in range(len(cut.beta))
    ]
    evaluated_rhs = cut.value_at(x)
    signed_violation = evaluated_rhs - theta
    absolute_violation = abs(signed_violation)
    scale = max(1.0, abs(theta), abs(evaluated_rhs))
    row = master.getRow(constraint)
    solver_lhs = sum(
        float(row.getCoeff(index)) * float(row.getVar(index).X)
        for index in range(row.size())
    )
    solver_rhs = float(constraint.RHS)
    expected = {variables["theta"].VarName: 1.0}
    relevant_x = []
    flat_beta = []
    for i, beta_row in enumerate(cut.beta):
        for j, beta in enumerate(beta_row):
            beta = float(beta)
            flat_beta.append(beta)
            expected[variables["x"][i, j].VarName] = -beta
            if beta != 0.0:
                relevant_x.append({
                    "i": i,
                    "j": j,
                    "x": x[i][j],
                    "beta": beta,
                    "beta_times_x": beta * x[i][j],
                })
    actual = {
        row.getVar(index).VarName: float(row.getCoeff(index))
        for index in range(row.size())
    }
    names = set(expected) | set(actual)
    coefficient_difference = max(
        (abs(actual.get(name, 0.0) - expected.get(name, 0.0)) for name in names),
        default=0.0,
    )
    if signed_violation > feasibility_tolerance:
        activity = "violated"
    elif abs(signed_violation) <= feasibility_tolerance:
        activity = "binding"
    else:
        activity = "slack"
    beta_bytes = json.dumps(flat_beta, separators=(",", ":")).encode("utf-8")
    return {
        "cut_id": cut_id,
        "constraint_name": constraint.ConstrName,
        "iteration_added": iteration_added,
        "current_master_iteration": current_iteration,
        "stored_rhs_intercept": cut.alpha,
        "evaluated_lhs": theta,
        "evaluated_rhs": evaluated_rhs,
        "signed_violation": signed_violation,
        "absolute_violation": absolute_violation,
        "relative_violation": absolute_violation / scale,
        "theta_value": theta,
        "solver_constraint_slack": float(constraint.Slack),
        "solver_activity": activity,
        "cut_coefficients_summary": {
            "count": len(flat_beta),
            "nonzero_count": sum(value != 0.0 for value in flat_beta),
            "minimum": min(flat_beta),
            "maximum": max(flat_beta),
            "l1_norm": sum(abs(value) for value in flat_beta),
            "sha256": hashlib.sha256(beta_bytes).hexdigest(),
        },
        "relevant_first_stage_variable_values": relevant_x,
        "master_expression_audit": {
            "sense": constraint.Sense,
            "actual_solver_lhs": solver_lhs,
            "actual_solver_rhs": solver_rhs,
            "actual_solver_signed_violation": solver_rhs - solver_lhs,
            "expected_form": "theta - sum(beta[i,j] * x[i,j]) >= alpha",
            "maximum_coefficient_difference": coefficient_difference,
            "rhs_intercept_difference": solver_rhs - cut.alpha,
            "identical_to_stored_cut": (
                coefficient_difference == 0.0
                and solver_rhs == cut.alpha
                and constraint.Sense == ">"
            ),
        },
    }
def _build_pure_master(instance, x0, budget, lambda_r):
    import gurobipy as gp
    from gurobipy import GRB

    depots = range(instance.num_depots)
    products = range(instance.num_products)
    model = gp.Model(f"pure_benders_master_{instance.name}")
    model.Params.OutputFlag = 0
    apply_formal_solver_profile(model, mixed_integer=True)
    y = model.addVars(depots, vtype=GRB.BINARY, name="y")
    x = model.addVars(depots, products, lb=0.0, name="x")
    a_plus = model.addVars(depots, products, lb=0.0, name="a_plus")
    a_minus = model.addVars(depots, products, lb=0.0, name="a_minus")
    theta = model.addVar(lb=0.0, name="theta")
    for i in depots:
        model.addConstr(
            gp.quicksum(instance.product_volume[j] * x[i, j] for j in products)
            <= instance.capacity[i] * y[i]
        )
        for j in products:
            model.addConstr(x[i, j] <= instance.inventory_upper_bound[i][j] * y[i])
            model.addConstr(x[i, j] - x0[i][j] == a_plus[i, j] - a_minus[i, j])
    reconfiguration_cost = lambda_r * gp.quicksum(
        instance.inventory_cost[i][j] * (a_plus[i, j] + a_minus[i, j])
        for i in depots for j in products
    )
    first_stage = gp.quicksum(instance.fixed_depot_cost[i] * y[i] for i in depots)
    first_stage += gp.quicksum(instance.inventory_cost[i][j] * x[i, j] for i in depots for j in products)
    first_stage += reconfiguration_cost
    model.addConstr(first_stage <= budget, name="financial_budget")
    model.setObjective(first_stage + theta, GRB.MINIMIZE)
    return model, {
        "y": y, "x": x, "a_plus": a_plus, "a_minus": a_minus,
        "theta": theta, "first_stage": first_stage,
        "reconfiguration_cost": reconfiguration_cost,
    }


def _solution_from_master(instance, x0, variables: dict[str, Any], robust_recourse: float):
    x = [[variables["x"][i, j].X for j in range(instance.num_products)]
         for i in range(instance.num_depots)]
    return ReconfigurationSolution(
        objective=float(variables["first_stage"].getValue()) + robust_recourse,
        first_stage_expenditure=float(variables["first_stage"].getValue()),
        robust_recourse_cost=robust_recourse,
        y=[int(round(variables["y"][i].X)) for i in range(instance.num_depots)],
        x=x,
        a_plus=[[variables["a_plus"][i, j].X for j in range(instance.num_products)]
                for i in range(instance.num_depots)],
        a_minus=[[variables["a_minus"][i, j].X for j in range(instance.num_products)]
                 for i in range(instance.num_depots)],
        reconfiguration_cost=float(variables["reconfiguration_cost"].getValue()),
    )


def _validate_x(instance: InventoryInstance, x: list[list[float]]) -> None:
    if len(x) != instance.num_depots or any(len(row) != instance.num_products for row in x):
        raise ValueError("x has incompatible dimensions")


def _dual_feasible(instance: InventoryInstance, variables: dict[str, Any], tolerance: float = 1e-6) -> bool:
    for r in range(instance.num_regions):
        for j in range(instance.num_products):
            pi = variables["pi"][r, j].X
            kappa = variables["kappa"][j].X
            if pi < -tolerance or kappa < -tolerance or kappa > instance.service_penalty[j] + tolerance:
                return False
            if pi - kappa > instance.shortage_penalty[r][j] + tolerance:
                return False
            for i in range(instance.num_depots):
                if pi + variables["mu"][i, j].X > instance.transport_cost[i][r][j] + tolerance:
                    return False
    return True
