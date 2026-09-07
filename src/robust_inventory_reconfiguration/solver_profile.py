from __future__ import annotations

from typing import Any


FORMAL_SOLVER_PROFILE_ID = "gurobi-balanced-1e-8-v1"
FORMAL_SOLVER_NATIVE_PROFILE = {
    "MIPGap": 0.0,
    "FeasibilityTol": 1e-8,
    "OptimalityTol": 1e-8,
    "IntFeasTol": 1e-8,
    "NumericFocus": 0,
    "BarConvTol": None,
}


def apply_formal_solver_profile(model: Any, *, mixed_integer: bool) -> None:
    """Apply the shared solver-native profile used by Direct and PRB solves."""
    profile = FORMAL_SOLVER_NATIVE_PROFILE
    model.Params.FeasibilityTol = profile["FeasibilityTol"]
    model.Params.OptimalityTol = profile["OptimalityTol"]
    model.Params.NumericFocus = profile["NumericFocus"]
    if mixed_integer:
        model.Params.MIPGap = profile["MIPGap"]
        model.Params.IntFeasTol = profile["IntFeasTol"]
