from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Any

from .pure_benders import GlobalAdversarialResult, PureAggregateCut
from .scenario_generation_oracle import ExactScenarioLPEvaluator
from .scenario_generation_single_cut import Pattern, exact_separation


class ScenarioGenerationGlobalOracle:
    """Exact global separation by safe scenario-tree pruning."""

    def __init__(
        self,
        instance: Any,
        gamma: int,
        *,
        trace_path: Path | None = None,
    ) -> None:
        zero = [[0.0 for _ in range(instance.num_products)] for _ in range(instance.num_depots)]
        self.instance = instance
        self.gamma = gamma
        self.trace_path = trace_path
        self.evaluator = ExactScenarioLPEvaluator(instance, gamma, zero, threads=None)
        self.previous_pattern: Pattern = ()
        self.solve_count = 0
        self.scenario_lp_solves = 0
        self.safely_pruned_scenarios = 0
        self.upper_bound_seconds = 0.0
        self.oracle_seconds = 0.0
        self.records: list[dict[str, Any]] = []

    def solve(
        self,
        x: list[list[float]],
        *,
        time_limit: float | None = None,
        certify: bool = True,
    ) -> GlobalAdversarialResult:
        del certify
        self.evaluator.set_first_stage(x)
        self.evaluator.begin_call(time_limit)
        started = perf_counter()
        separated = exact_separation(
            self.instance,
            x,
            self.gamma,
            self.evaluator.evaluate,
            candidate_patterns=(self.previous_pattern,),
        )
        elapsed = perf_counter() - started
        evidence = separated.evaluation.payload
        cut = PureAggregateCut(
            evidence["alpha"],
            evidence["beta"],
            separated.evaluation.value,
            tuple(tuple(float(value) for value in row) for row in x),
            separated.pattern,
            evidence["dual_feasibility_max_violation"] <= 1e-7,
            evidence["strong_duality_residual"],
        )
        record = {
            "oracle_call": self.solve_count + 1,
            "first_stage_x": x,
            "incumbent_pattern_evaluated_first": self.previous_pattern,
            "worst_pattern": separated.pattern,
            "worst_recourse_value": separated.evaluation.value,
            "total_scenarios": separated.total_scenarios,
            "exact_lp_solves": separated.lp_solves,
            "safely_pruned_scenarios": separated.safely_pruned_scenarios,
            "pruning_fraction": separated.safely_pruned_scenarios / separated.total_scenarios,
            "branch_nodes": separated.branch_nodes,
            "upper_bound_seconds": separated.upper_bound_seconds,
            "lp_optimize_seconds": self.evaluator.lp_seconds,
            "oracle_seconds": elapsed,
            "dual_feasibility_max_violation": evidence["dual_feasibility_max_violation"],
            "strong_duality_residual": evidence["strong_duality_residual"],
            "cut_anchor_residual": evidence["cut_anchor_residual"],
        }
        self.solve_count += 1
        self.scenario_lp_solves += separated.lp_solves
        self.safely_pruned_scenarios += separated.safely_pruned_scenarios
        self.upper_bound_seconds += separated.upper_bound_seconds
        self.oracle_seconds += elapsed
        self.previous_pattern = separated.pattern
        self.records.append(record)
        if self.trace_path is not None:
            self.trace_path.parent.mkdir(parents=True, exist_ok=True)
            with self.trace_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
        return GlobalAdversarialResult(
            separated.evaluation.value,
            cut,
            separated.evaluation.value,
            elapsed,
            0.0,
            0,
            self.instance.num_depots * self.instance.num_regions * self.instance.num_products
            + self.instance.num_regions * self.instance.num_products
            + self.instance.num_products,
            self.instance.num_regions * self.instance.num_products
            + self.instance.num_depots * self.instance.num_products
            + self.instance.num_products,
        )

    def close(self) -> None:
        self.evaluator.close()


def solve_scenario_generation_benders(
    instance: Any,
    x0: list[list[float]],
    budget: float,
    gamma: int,
    lambda_r: float,
    *,
    trace_path: Path | None = None,
    **kwargs: Any,
) -> tuple[Any, dict[str, Any]]:
    """Use the unchanged single-theta master with exact SG separation."""
    from . import pure_benders as pure

    original = pure.GlobalRobustAdversarialSubproblem
    created: list[ScenarioGenerationGlobalOracle] = []

    def factory(oracle_instance: Any, oracle_gamma: int) -> ScenarioGenerationGlobalOracle:
        oracle = ScenarioGenerationGlobalOracle(
            oracle_instance, oracle_gamma, trace_path=trace_path
        )
        created.append(oracle)
        return oracle

    pure.GlobalRobustAdversarialSubproblem = factory
    try:
        result = pure.solve_pure_benders(
            instance, x0, budget, gamma, lambda_r, **kwargs
        )
        diagnostics = {
            "oracle_instances": len(created),
            "oracle_solve_calls": sum(oracle.solve_count for oracle in created),
            "scenario_lp_solves": sum(oracle.scenario_lp_solves for oracle in created),
            "safely_pruned_scenarios": sum(
                oracle.safely_pruned_scenarios for oracle in created
            ),
            "upper_bound_seconds": sum(oracle.upper_bound_seconds for oracle in created),
            "oracle_seconds": sum(oracle.oracle_seconds for oracle in created),
            "single_global_theta": True,
            "maximum_cuts_per_iteration": 1,
            "safe_candidate_pruning": True,
            "product_risk_budget_decomposition": False,
            "product_multicut": False,
            "compact_global_robust_milp_oracle": False,
        }
        return result, diagnostics
    finally:
        pure.GlobalRobustAdversarialSubproblem = original
        for oracle in created:
            oracle.close()
