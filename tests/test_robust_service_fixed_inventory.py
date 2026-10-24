from pathlib import Path

import pytest

from robust_inventory_reconfiguration.robust_service import (
    canonical_fixed_inventory,
    evaluate_robust_service_detailed,
)


pytest.importorskip("gurobipy")


def test_fixed_inventory_canonicalization_matches_prb_recourse_boundary(
    tiny_instance,
) -> None:
    assert canonical_fixed_inventory(tiny_instance, [[-5e-8, 1.0]]) == [[0.0, 1.0]]
    with pytest.raises(ValueError, match="materially negative"):
        canonical_fixed_inventory(tiny_instance, [[-1e-3, 1.0]])


def test_solver_scale_negative_fixed_inventory_is_projected(tiny_instance) -> None:
    result = evaluate_robust_service_detailed(
        tiny_instance,
        [[-5e-8, 1.0]],
        0,
    )
    assert result.scenario_count == 1


def test_materially_negative_fixed_inventory_is_rejected(tiny_instance) -> None:
    with pytest.raises(ValueError, match="materially negative"):
        evaluate_robust_service_detailed(tiny_instance, [[-1e-3, 1.0]], 0)


def test_diagnostic_raw_inventory_writes_iis(tiny_instance, tmp_path: Path) -> None:
    iis_path = tmp_path / "fixed_recourse.ilp"
    with pytest.raises(RuntimeError, match="failed: 3"):
        evaluate_robust_service_detailed(
            tiny_instance,
            [[-5e-8, 1.0]],
            0,
            infeasibility_iis_path=iis_path,
            preserve_solver_noise_for_diagnostic=True,
        )
    text = iis_path.read_text(encoding="utf-8")
    assert "supply_p0_snone_d0" in text
    assert "q_p0_snone" in text
