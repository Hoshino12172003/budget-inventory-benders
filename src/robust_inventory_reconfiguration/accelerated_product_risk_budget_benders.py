from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
from math import comb
import os
import pickle
from time import perf_counter
import traceback

from .accelerated_product_risk_subproblem import (
    AcceleratedProductRiskSubproblem,
    AcceleratedProductSeparationResult,
)
from .instance import InventoryInstance
from .product_risk_budget_benders import (
    PRBIteration,
    ProductCutAddition,
    _build_master,
    _solution_from_master,
)
from .product_risk_subproblem import ProductCut
from .reconfiguration_model import ReconfigurationSolution
from .risk_budget_composition import RiskBudgetComposition


@dataclass(frozen=True)
class AcceleratedPRBBendersResult:
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
    gamma_combination_runtime: float
    certification_runtime: float
    oracle_model_build_runtime: float
    exact_certification_pass: bool
    global_risk_budget_coupling_pass: bool
    global_risk_budget_coupling_error: float
    cuts: tuple[ProductCut, ...]
    cut_additions: tuple[ProductCutAddition, ...]
    cache_hits: int
    cache_misses: int
    product_solves_avoided: int
    warm_starts: int
    simplex_iterations: float
    cold_product_solve_runtime: float
    warm_product_solve_runtime: float
    parallel_worker_count: int
    selective_separation_enabled: bool
    full_final_verification: bool
    certification_cache_hits: int
    certification_product_state_solves: int
    runtime_profile: dict[str, dict[str, float | int]]
    separation_audit: tuple[dict[str, object], ...]


def _product_worker(
    connection, instance, gamma, product_indices, subproblem_class, subproblem_options
):
    try:
        started = perf_counter()
        subproblems = {}
        individual_build_times = []
        for j in product_indices:
            product_started = perf_counter()
            subproblems[j] = subproblem_class(
                instance, j, gamma, **subproblem_options
            )
            individual_build_times.append(perf_counter() - product_started)
        connection.send(
            (
                "ready",
                {
                    "worker_build_runtime": perf_counter() - started,
                    "individual_build_times": individual_build_times,
                },
            )
        )
        while True:
            command, payload = connection.recv()
            if command == "close":
                break
            if command != "solve":
                raise ValueError(f"Unknown product-worker command: {command}")
            connection.send(
                ("results", [(j, subproblems[j].solve(vector)) for j, vector in payload])
            )
        for subproblem in subproblems.values():
            subproblem.close()
        connection.close()
    except BaseException:
        connection.send(("error", traceback.format_exc()))
        connection.close()


def _compose_risk_budget_exact_dp(
    product_values: list[list[float]], gamma: int
) -> RiskBudgetComposition:
    states: dict[int, tuple[float, tuple[int, ...]]] = {0: (0.0, ())}
    for values in product_values:
        updated: dict[int, tuple[float, tuple[int, ...]]] = {}
        for used, (prior_value, allocation) in states.items():
            for local_gamma in range(min(gamma - used, len(values) - 1) + 1):
                next_used = used + local_gamma
                candidate = (prior_value + values[local_gamma], allocation + (local_gamma,))
                incumbent = updated.get(next_used)
                if incumbent is None or candidate[0] > incumbent[0]:
                    updated[next_used] = candidate
        states = updated
    _, (value, allocation) = max(states.items(), key=lambda item: item[1][0])
    return RiskBudgetComposition(value, allocation)


def _select_parallel_workers(instance: InventoryInstance, gamma: int) -> int:
    patterns_per_product = sum(comb(instance.num_regions, g) for g in range(gamma + 1))
    total_blocks = instance.num_products * patterns_per_product
    worker_cap = 2 if total_blocks <= 1_000 else 8
    return max(1, min(worker_cap, instance.num_products, os.cpu_count() or 1))


def _forced_allocation_upper_bound(
    upper_values: list[list[float]], gamma: int, product: int, local_gamma: int
) -> float:
    if local_gamma > gamma:
        return float("-inf")
    other_values = [
        values for j, values in enumerate(upper_values) if j != product
    ]
    remainder = _compose_risk_budget_exact_dp(other_values, gamma - local_gamma)
    return upper_values[product][local_gamma] + remainder.value


def _select_products_for_exact_separation(
    upper_values: list[list[float]],
    eta_values: list[list[float]],
    theta_value: float,
    gamma: int,
    exact_cached_products: set[int],
    tolerance: float,
) -> tuple[set[int], set[int], dict[str, int]]:
    selected: set[int] = set()
    screened: set[int] = set()
    reasons = {"individual": 0, "gamma": 0}
    for j in range(len(upper_values)):
        if j in exact_cached_products:
            selected.add(j)
            continue
        state_safe = []
        for g in range(gamma + 1):
            individual_safe = upper_values[j][g] <= eta_values[j][g] + tolerance
            gamma_safe = (
                _forced_allocation_upper_bound(upper_values, gamma, j, g)
                <= theta_value + tolerance
            )
            state_safe.append(individual_safe or gamma_safe)
            if individual_safe:
                reasons["individual"] += 1
            elif gamma_safe:
                reasons["gamma"] += 1
        if all(state_safe):
            screened.add(j)
        else:
            selected.add(j)
    return selected, screened, reasons


class _ExactParallelProductOracle:
    def __init__(
        self,
        instance: InventoryInstance,
        gamma: int,
        workers: int,
        *,
        subproblem_class=AcceleratedProductRiskSubproblem,
        subproblem_options: dict | None = None,
        backend: str = "process",
    ):
        self.instance = instance
        self.gamma = gamma
        self.workers = max(1, min(workers, instance.num_products))
        self.backend = backend
        if backend not in {"process", "thread"}:
            raise ValueError("oracle backend must be 'process' or 'thread'")
        subproblem_options = subproblem_options or {}
        if backend == "thread":
            self.connections = []
            self.processes = []
            self._executor = ThreadPoolExecutor(max_workers=self.workers)
            started = perf_counter()

            def build(j):
                product_started = perf_counter()
                subproblem = subproblem_class(
                    instance, j, gamma, **subproblem_options
                )
                return j, subproblem, perf_counter() - product_started

            built = list(self._executor.map(build, range(instance.num_products)))
            self.subproblems = {j: subproblem for j, subproblem, _ in built}
            self.build_runtime = perf_counter() - started
            self._worker_build_profiles = [
                {
                    "worker_build_runtime": self.build_runtime,
                    "individual_build_times": [elapsed for _, _, elapsed in built],
                }
            ]
            self._initialize_statistics()
            return
        context = multiprocessing.get_context("spawn")
        groups = [list(range(worker, instance.num_products, self.workers)) for worker in range(self.workers)]
        self.connections = []
        self.processes = []
        self._worker_build_profiles = []
        started = perf_counter()
        for group in groups:
            parent, child = context.Pipe()
            process = context.Process(
                target=_product_worker,
                args=(
                    child,
                    instance,
                    gamma,
                    group,
                    subproblem_class,
                    subproblem_options,
                ),
                daemon=True,
            )
            process.start()
            child.close()
            self.connections.append((parent, group))
            self.processes.append(process)
        for connection, _ in self.connections:
            status, payload = connection.recv()
            if status != "ready":
                raise RuntimeError(f"Product worker failed during construction:\n{payload}")
            self._worker_build_profiles.append(payload)
        self.build_runtime = perf_counter() - started
        self._initialize_statistics()

    def _initialize_statistics(self) -> None:
        self.cache: dict[
            tuple[int, tuple[float, ...]], AcceleratedProductSeparationResult
        ] = {}
        self.cache_hits = 0
        self.cache_misses = 0
        self.product_solves_avoided = 0
        self.product_state_solves = 0
        self.pattern_evaluations = 0
        self.warm_starts = 0
        self.simplex_iterations = 0.0
        self.cold_solve_runtime = 0.0
        self.warm_solve_runtime = 0.0
        self.model_update_runtime = 0.0
        self.result_extraction_runtime = 0.0
        self.cache_lookup_runtime = 0.0
        self.dispatch_runtime = 0.0
        self.serialization_probe_runtime = 0.0
        self.ipc_payload_bytes = 0
        self.result_processing_runtime = 0.0
        self.worker_compute_critical_runtime = 0.0
        self.ipc_residual_runtime = 0.0
        self.evaluate_calls = 0
        self.dispatch_calls = 0
        self.maximum_product_optimization_runtime = 0.0
        self.maximum_product_update_runtime = 0.0
        self.maximum_product_extraction_runtime = 0.0
        self.inventory_loss_cost = tuple(
            tuple(
                max(
                    0.0,
                    max(
                        self.instance.shortage_penalty[r][j]
                        + self.instance.service_penalty[j]
                        - self.instance.transport_cost[i][r][j]
                        for r in range(self.instance.num_regions)
                    ),
                )
                for i in range(self.instance.num_depots)
            )
            for j in range(self.instance.num_products)
        )

    @staticmethod
    def _signature(values: list[float]) -> tuple[float, ...]:
        # Python float equality is exact here; no rounding or proximity reuse occurs.
        return tuple(0.0 if value == 0.0 else value for value in values)

    def evaluate(
        self,
        x: list[list[float]],
        *,
        allow_cache: bool,
        selected_products: set[int] | None = None,
    ) -> tuple[list[AcceleratedProductSeparationResult | None], float]:
        if selected_products is None:
            selected_products = set(range(self.instance.num_products))
        vectors = [
            [x[i][j] for i in range(self.instance.num_depots)]
            for j in range(self.instance.num_products)
        ]
        results: list[AcceleratedProductSeparationResult | None] = [
            None
        ] * self.instance.num_products
        pending_by_worker = [[] for _ in self.connections]
        thread_pending = []
        started = perf_counter()
        cache_started = perf_counter()
        for j, vector in enumerate(vectors):
            if j not in selected_products:
                continue
            key = (j, self._signature(vector))
            if allow_cache and key in self.cache:
                results[j] = self.cache[key]
                self.cache_hits += 1
                self.product_solves_avoided += self.gamma + 1
            else:
                self.cache_misses += 1
                if self.backend == "thread":
                    thread_pending.append((j, key, vector))
                else:
                    pending_by_worker[j % self.workers].append((j, key, vector))
        cache_elapsed = perf_counter() - cache_started
        self.cache_lookup_runtime += cache_elapsed
        worker_critical_times = []
        call_dispatch_runtime = 0.0
        call_serialization_runtime = 0.0
        call_result_processing_runtime = 0.0
        if self.backend == "thread":
            futures = {
                self._executor.submit(self.subproblems[j].solve, vector): (j, key)
                for j, key, vector in thread_pending
            }
            for future in as_completed(futures):
                j, key = futures[future]
                result = future.result()
                processing_started = perf_counter()
                results[j] = result
                self.cache[key] = result
                self._record_result(result)
                processed_in = perf_counter() - processing_started
                self.result_processing_runtime += processed_in
                call_result_processing_runtime += processed_in
                worker_critical_times.append(
                    result.model_update_runtime
                    + result.runtime
                    + result.result_extraction_runtime
                )
        for (connection, _), pending in zip(self.connections, pending_by_worker):
            if pending:
                message = ("solve", [(j, vector) for j, _, vector in pending])
                serialization_started = perf_counter()
                encoded = pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
                serialized_in = perf_counter() - serialization_started
                self.serialization_probe_runtime += serialized_in
                call_serialization_runtime += serialized_in
                self.ipc_payload_bytes += len(encoded)
                dispatch_started = perf_counter()
                connection.send(message)
                dispatched_in = perf_counter() - dispatch_started
                self.dispatch_runtime += dispatched_in
                call_dispatch_runtime += dispatched_in
                self.dispatch_calls += 1
        for (connection, _), pending in zip(self.connections, pending_by_worker):
            if not pending:
                continue
            status, payload = connection.recv()
            if status != "results":
                raise RuntimeError(f"Product worker failed during solve:\n{payload}")
            serialization_started = perf_counter()
            encoded = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
            serialized_in = perf_counter() - serialization_started
            self.serialization_probe_runtime += serialized_in
            call_serialization_runtime += serialized_in
            self.ipc_payload_bytes += len(encoded)
            worker_critical_times.append(
                sum(
                    result.model_update_runtime
                    + result.runtime
                    + result.result_extraction_runtime
                    for _, result in payload
                )
            )
            processing_started = perf_counter()
            keys = {j: key for j, key, _ in pending}
            for j, result in payload:
                results[j] = result
                self.cache[keys[j]] = result
                self._record_result(result)
            processed_in = perf_counter() - processing_started
            self.result_processing_runtime += processed_in
            call_result_processing_runtime += processed_in
        if any(results[j] is None for j in selected_products):
            raise RuntimeError("Parallel product oracle returned an incomplete result set")
        elapsed = perf_counter() - started
        critical = max(worker_critical_times, default=0.0)
        self.worker_compute_critical_runtime += critical
        self.ipc_residual_runtime += max(
            0.0,
            elapsed
            - critical
            - cache_elapsed
            - call_dispatch_runtime
            - call_serialization_runtime
            - call_result_processing_runtime,
        )
        self.evaluate_calls += 1
        return results, elapsed

    def state_upper_bounds(self, x: list[list[float]]) -> list[list[float]]:
        """Valid upper bounds from all previously solved exact inventory states."""
        vectors = [
            tuple(x[i][j] for i in range(self.instance.num_depots))
            for j in range(self.instance.num_products)
        ]
        bounds = [
            [float("inf")] * (self.gamma + 1)
            for _ in range(self.instance.num_products)
        ]
        for (j, prior_x), result in self.cache.items():
            inventory_loss_bound = sum(
                self.inventory_loss_cost[j][i] * max(prior_x[i] - vectors[j][i], 0.0)
                for i in range(self.instance.num_depots)
            )
            for worst in result.worst_cases:
                bounds[j][worst.local_gamma] = min(
                    bounds[j][worst.local_gamma],
                    worst.value + inventory_loss_bound,
                )
        return bounds

    def _record_result(self, result: AcceleratedProductSeparationResult) -> None:
        self.product_state_solves += self.gamma + 1
        self.pattern_evaluations += result.pattern_evaluations
        self.warm_starts += result.warm_starts
        self.simplex_iterations += result.simplex_iterations
        self.cold_solve_runtime += result.cold_solve_runtime
        self.warm_solve_runtime += result.warm_solve_runtime
        self.model_update_runtime += result.model_update_runtime
        self.result_extraction_runtime += result.result_extraction_runtime
        self.maximum_product_optimization_runtime = max(
            self.maximum_product_optimization_runtime, result.runtime
        )
        self.maximum_product_update_runtime = max(
            self.maximum_product_update_runtime, result.model_update_runtime
        )
        self.maximum_product_extraction_runtime = max(
            self.maximum_product_extraction_runtime,
            result.result_extraction_runtime,
        )

    def close(self) -> None:
        if self.backend == "thread":
            self._executor.shutdown(wait=True)
            for subproblem in self.subproblems.values():
                subproblem.close()
            return
        for connection, _ in self.connections:
            try:
                connection.send(("close", None))
            except (BrokenPipeError, EOFError):
                pass
        for process in self.processes:
            process.join(timeout=10)
            if process.is_alive():
                process.terminate()
                process.join()
        for connection, _ in self.connections:
            connection.close()


def solve_accelerated_prb_benders(
    instance: InventoryInstance,
    x0: list[list[float]],
    budget: float,
    gamma: int,
    lambda_r: float,
    *,
    relative_gap_tolerance: float = 1e-6,
    cut_tolerance: float = 1e-7,
    max_iterations: int = 500,
    parallel_workers: int | None = None,
    _subproblem_class=AcceleratedProductRiskSubproblem,
    _subproblem_options: dict | None = None,
    _oracle_backend: str = "process",
    _selective_separation: bool = False,
) -> AcceleratedPRBBendersResult:
    """Exact PRB with compact parallel product oracles and exact-state caching."""
    from gurobipy import GRB

    if gamma < 0 or gamma > instance.num_regions:
        raise ValueError("gamma must be between zero and the number of regions")
    if lambda_r < 0:
        raise ValueError("lambda_r must be nonnegative")
    if len(x0) != instance.num_depots or any(
        len(row) != instance.num_products for row in x0
    ):
        raise ValueError("x0 has incompatible dimensions")
    workers = parallel_workers or _select_parallel_workers(instance, gamma)
    started = perf_counter()
    master_build_started = perf_counter()
    master, variables = _build_master(instance, x0, budget, gamma, lambda_r)
    master_build_runtime = perf_counter() - master_build_started
    oracle = _ExactParallelProductOracle(
        instance,
        gamma,
        workers,
        subproblem_class=_subproblem_class,
        subproblem_options=_subproblem_options,
        backend=_oracle_backend,
    )
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
    gamma_runtime = 0.0
    main_gamma_runtime = 0.0
    certification_runtime = 0.0
    certification_preparation_runtime = 0.0
    lb_ub_runtime = 0.0
    cut_construction_runtime = 0.0
    cut_insertion_runtime = 0.0
    maximum_master_solve_runtime = 0.0
    maximum_gamma_runtime = 0.0
    maximum_lb_ub_runtime = 0.0
    maximum_cut_construction_runtime = 0.0
    maximum_cut_insertion_runtime = 0.0
    separation_audit: list[dict[str, object]] = []

    def add_violated_cuts(
        product_results: list[AcceleratedProductSeparationResult | None],
        iteration: int,
    ) -> tuple[int, int]:
        nonlocal cut_construction_runtime
        nonlocal cut_insertion_runtime
        nonlocal maximum_cut_construction_runtime
        nonlocal maximum_cut_insertion_runtime
        violated = 0
        added = 0
        for j, result in enumerate(product_results):
            if result is None:
                continue
            for worst in result.worst_cases:
                cut_started = perf_counter()
                g = worst.local_gamma
                violation = worst.value - variables["eta"][j, g].X
                if violation <= cut_tolerance:
                    cut_elapsed = perf_counter() - cut_started
                    cut_construction_runtime += cut_elapsed
                    maximum_cut_construction_runtime = max(
                        maximum_cut_construction_runtime, cut_elapsed
                    )
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
                cut_elapsed = perf_counter() - cut_started
                cut_construction_runtime += cut_elapsed
                maximum_cut_construction_runtime = max(
                    maximum_cut_construction_runtime, cut_elapsed
                )
                insertion_started = perf_counter()
                master.addConstr(
                    variables["eta"][j, g]
                    >= cut.alpha
                    + sum(
                        cut.beta[i] * variables["x"][i, j]
                        for i in range(instance.num_depots)
                    ),
                    name=f"product_cut[{j},{g},{cuts_by_product[j]}]",
                )
                insertion_elapsed = perf_counter() - insertion_started
                cut_insertion_runtime += insertion_elapsed
                maximum_cut_insertion_runtime = max(
                    maximum_cut_insertion_runtime, insertion_elapsed
                )
                cut_signatures.add(signature)
                cuts.append(cut)
                cut_additions.append(ProductCutAddition(iteration, violation, cut))
                cuts_by_product[j] += 1
                cuts_by_gamma[g] += 1
                added += 1
        return violated, added

    try:
        for iteration in range(1, max_iterations + 1):
            master_started = perf_counter()
            master.optimize()
            master_elapsed = perf_counter() - master_started
            master_runtime += master_elapsed
            maximum_master_solve_runtime = max(
                maximum_master_solve_runtime, master_elapsed
            )
            if master.Status != GRB.OPTIMAL:
                raise RuntimeError(f"Exact master failed with status {master.Status}")
            lower_bound = float(master.ObjVal)
            xbar = [
                [variables["x"][i, j].X for j in range(instance.num_products)]
                for i in range(instance.num_depots)
            ]

            eta_values = [
                [variables["eta"][j, g].X for g in range(gamma + 1)]
                for j in range(instance.num_products)
            ]
            theta_value = float(variables["theta"].X)
            potential_states = instance.num_products * (gamma + 1)
            upper_values = (
                oracle.state_upper_bounds(xbar)
                if _selective_separation
                else [
                    [0.0] * (gamma + 1)
                    for _ in range(instance.num_products)
                ]
            )
            selected_products = set(range(instance.num_products))
            screened_products: set[int] = set()
            state_screen_reasons = {"individual": 0, "gamma": 0}
            if _selective_separation:
                exact_cached_products = {
                    j
                    for j in range(instance.num_products)
                    if (
                        j,
                        oracle._signature(
                            [xbar[i][j] for i in range(instance.num_depots)]
                        ),
                    )
                    in oracle.cache
                }
                (
                    selected_products,
                    screened_products,
                    state_screen_reasons,
                ) = _select_products_for_exact_separation(
                    upper_values,
                    eta_values,
                    theta_value,
                    gamma,
                    exact_cached_products,
                    cut_tolerance,
                )

            cache_hits_before = oracle.cache_hits
            cache_misses_before = oracle.cache_misses
            exact_states_before = oracle.product_state_solves
            product_results, elapsed = oracle.evaluate(
                xbar,
                allow_cache=True,
                selected_products=selected_products,
            )
            separation_runtime += elapsed
            lb_ub_started = perf_counter()
            for j, result in enumerate(product_results):
                if result is not None:
                    upper_values[j] = [worst.value for worst in result.worst_cases]
            lb_ub_elapsed = perf_counter() - lb_ub_started
            lb_ub_runtime += lb_ub_elapsed
            maximum_lb_ub_runtime = max(maximum_lb_ub_runtime, lb_ub_elapsed)
            gamma_started = perf_counter()
            composition = _compose_risk_budget_exact_dp(upper_values, gamma)
            gamma_elapsed = perf_counter() - gamma_started
            gamma_runtime += gamma_elapsed
            main_gamma_runtime += gamma_elapsed
            maximum_gamma_runtime = max(maximum_gamma_runtime, gamma_elapsed)
            lb_ub_started = perf_counter()
            first_stage = float(variables["first_stage"].getValue())
            candidate_upper_bound = first_stage + composition.value
            if candidate_upper_bound <= upper_bound + 1e-8:
                upper_bound = min(upper_bound, candidate_upper_bound)
                best_solution = _solution_from_master(
                    instance, x0, lambda_r, master, variables, composition.value
                )
            lb_ub_elapsed = perf_counter() - lb_ub_started
            lb_ub_runtime += lb_ub_elapsed
            maximum_lb_ub_runtime = max(maximum_lb_ub_runtime, lb_ub_elapsed)

            checked = potential_states
            violated, added = add_violated_cuts(product_results, iteration)
            exact_states = oracle.product_state_solves - exact_states_before
            cache_hits = oracle.cache_hits - cache_hits_before
            cache_misses = oracle.cache_misses - cache_misses_before
            screening_skipped = len(screened_products) * (gamma + 1)
            final_verification_states = 0
            missed_violations = 0

            should_verify = (
                _selective_separation
                and added == 0
                and composition.value <= theta_value + cut_tolerance
            )
            if should_verify:
                verification_states_before = oracle.product_state_solves
                verification_results, verification_elapsed = oracle.evaluate(
                    xbar, allow_cache=True
                )
                separation_runtime += verification_elapsed
                final_verification_states = (
                    oracle.product_state_solves - verification_states_before
                )
                exact_values = [
                    [worst.value for worst in result.worst_cases]
                    for result in verification_results
                    if result is not None
                ]
                exact_composition = _compose_risk_budget_exact_dp(
                    exact_values, gamma
                )
                missed_violations, missed_added = add_violated_cuts(
                    verification_results, iteration
                )
                violated += missed_violations
                added += missed_added
                if missed_added == 0:
                    composition = exact_composition
                    candidate_upper_bound = first_stage + composition.value
                    upper_bound = candidate_upper_bound
                    best_solution = _solution_from_master(
                        instance,
                        x0,
                        lambda_r,
                        master,
                        variables,
                        composition.value,
                    )

            separation_audit.append(
                {
                    "iteration": iteration,
                    "potential_product_risk_states": potential_states,
                    "exact_state_solves": exact_states,
                    "cache_hits": cache_hits,
                    "cache_misses": cache_misses,
                    "cache_avoided_state_solves": cache_hits * (gamma + 1),
                    "screening_avoided_state_solves": screening_skipped,
                    "screened_products": len(screened_products),
                    "individual_bound_safe_states": state_screen_reasons["individual"],
                    "gamma_bound_safe_states": state_screen_reasons["gamma"],
                    "newly_violated_states": violated,
                    "states_generating_new_cut": added,
                    "exact_states_without_new_cut": max(0, exact_states - added),
                    "allocation": list(composition.allocation),
                    "states_in_gamma_allocation": instance.num_products,
                    "final_verification_state_solves": final_verification_states,
                    "missed_violations_at_final_verification": missed_violations,
                }
            )

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
            if _selective_separation and should_verify and added == 0:
                break
            if not _selective_separation and gap <= relative_gap_tolerance and violated == 0:
                break
        else:
            raise RuntimeError("Accelerated PRB-Benders reached the iteration limit")

        if best_solution is None:
            raise RuntimeError("Accelerated PRB-Benders produced no incumbent")
        certification_started = perf_counter()
        certification_hits_before = oracle.cache_hits
        certification_states_before = oracle.product_state_solves
        certified_results, _ = oracle.evaluate(best_solution.x, allow_cache=True)
        certification_cache_hits = oracle.cache_hits - certification_hits_before
        certification_product_state_solves = (
            oracle.product_state_solves - certification_states_before
        )
        certification_preparation_started = perf_counter()
        certified_values = [
            [worst.value for worst in result.worst_cases]
            for result in certified_results
        ]
        gamma_started = perf_counter()
        certified_composition = _compose_risk_budget_exact_dp(certified_values, gamma)
        gamma_elapsed = perf_counter() - gamma_started
        gamma_runtime += gamma_elapsed
        maximum_gamma_runtime = max(maximum_gamma_runtime, gamma_elapsed)
        certification_preparation_runtime += (
            perf_counter() - certification_preparation_started
        )
        certification_runtime = perf_counter() - certification_started
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
        total_runtime = perf_counter() - started
        worker_build_times = [
            float(profile["worker_build_runtime"])
            for profile in oracle._worker_build_profiles
        ]
        individual_build_times = [
            float(value)
            for profile in oracle._worker_build_profiles
            for value in profile["individual_build_times"]
        ]
        construction_critical = max(worker_build_times, default=0.0)
        worker_startup_runtime = max(0.0, oracle.build_runtime - construction_critical)
        top_level_accounted = (
            master_build_runtime
            + oracle.build_runtime
            + master_runtime
            + separation_runtime
            + main_gamma_runtime
            + lb_ub_runtime
            + cut_construction_runtime
            + cut_insertion_runtime
            + certification_runtime
        )
        miscellaneous_runtime = max(0.0, total_runtime - top_level_accounted)

        def profile(total: float, count: int, maximum: float | None = None):
            return {
                "total_seconds": total,
                "percent_core": 100.0 * total / max(total_runtime, 1e-12),
                "call_count": count,
                "average_seconds": total / max(count, 1),
                "maximum_seconds": total if maximum is None else maximum,
            }

        runtime_profile = {
            "master_model_construction": profile(master_build_runtime, 1),
            "worker_startup": profile(worker_startup_runtime, oracle.workers),
            "product_model_construction_critical_path": profile(
                construction_critical,
                instance.num_products,
                max(individual_build_times, default=0.0),
            ),
            "product_model_construction_cumulative": profile(
                sum(individual_build_times),
                instance.num_products,
                max(individual_build_times, default=0.0),
            ),
            "master_solve": profile(
                master_runtime, len(iterations), maximum_master_solve_runtime
            ),
            "product_model_update_cumulative": profile(
                oracle.model_update_runtime,
                oracle.cache_misses,
                oracle.maximum_product_update_runtime,
            ),
            "product_optimization_cumulative": profile(
                oracle.cold_solve_runtime + oracle.warm_solve_runtime,
                oracle.cache_misses,
                oracle.maximum_product_optimization_runtime,
            ),
            "product_result_extraction_cumulative": profile(
                oracle.result_extraction_runtime,
                oracle.cache_misses,
                oracle.maximum_product_extraction_runtime,
            ),
            "parallel_worker_compute_critical_path": profile(
                oracle.worker_compute_critical_runtime, oracle.evaluate_calls
            ),
            "cache_lookup": profile(
                oracle.cache_lookup_runtime, oracle.cache_hits + oracle.cache_misses
            ),
            "worker_dispatch": profile(
                oracle.dispatch_runtime, oracle.dispatch_calls
            ),
            "serialization_probe": {
                **profile(oracle.serialization_probe_runtime, oracle.dispatch_calls * 2),
                "payload_bytes": oracle.ipc_payload_bytes,
            },
            "ipc_and_wait_residual": profile(
                oracle.ipc_residual_runtime, oracle.evaluate_calls
            ),
            "result_processing": profile(
                oracle.result_processing_runtime, oracle.cache_misses
            ),
            "gamma_allocation": profile(
                gamma_runtime, len(iterations) + 1, maximum_gamma_runtime
            ),
            "lb_ub_computation": profile(
                lb_ub_runtime, len(iterations), maximum_lb_ub_runtime
            ),
            "cut_construction": profile(
                cut_construction_runtime,
                len(iterations) * instance.num_products * (gamma + 1),
                maximum_cut_construction_runtime,
            ),
            "cut_insertion": profile(
                cut_insertion_runtime, len(cuts), maximum_cut_insertion_runtime
            ),
            "certification_total": profile(certification_runtime, 1),
            "certification_preparation": profile(
                certification_preparation_runtime, 1
            ),
            "miscellaneous_python": profile(miscellaneous_runtime, 1),
        }
        return AcceleratedPRBBendersResult(
            "OPTIMAL" if exact_certification_pass else "ERROR",
            final_solution,
            iterations[-1].lower_bound,
            upper_bound,
            max(0.0, upper_bound - iterations[-1].lower_bound)
            / max(1.0, abs(upper_bound)),
            tuple(iterations),
            len(iterations),
            oracle.product_state_solves,
            oracle.pattern_evaluations,
            len(cuts),
            tuple(cuts_by_product),
            tuple(cuts_by_gamma),
            total_runtime,
            master_runtime,
            separation_runtime,
            gamma_runtime,
            certification_runtime,
            oracle.build_runtime,
            exact_certification_pass,
            global_coupling_pass,
            global_coupling_error,
            tuple(cuts),
            tuple(cut_additions),
            oracle.cache_hits,
            oracle.cache_misses,
            oracle.product_solves_avoided,
            oracle.warm_starts,
            oracle.simplex_iterations,
            oracle.cold_solve_runtime,
            oracle.warm_solve_runtime,
            oracle.workers,
            _selective_separation,
            True,
            certification_cache_hits,
            certification_product_state_solves,
            runtime_profile,
            tuple(separation_audit),
        )
    finally:
        oracle.close()
