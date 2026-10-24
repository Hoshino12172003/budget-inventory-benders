from __future__ import annotations

from .accelerated_product_risk_budget_benders import (
    AcceleratedPRBBendersResult,
    solve_accelerated_prb_benders,
)
from .instance import InventoryInstance


def solve_accelerated_prb_benders_v4(
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
) -> AcceleratedPRBBendersResult:
    """Exact PRB V4 with proof-based product-level selective separation."""
    return solve_accelerated_prb_benders(
        instance,
        x0,
        budget,
        gamma,
        lambda_r,
        relative_gap_tolerance=relative_gap_tolerance,
        cut_tolerance=cut_tolerance,
        max_iterations=max_iterations,
        parallel_workers=parallel_workers,
        _selective_separation=True,
    )
