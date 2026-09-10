from __future__ import annotations

from types import SimpleNamespace

import pytest

import robust_inventory_reconfiguration.e4_reporting as reporting


def test_status_13_uses_explicit_diagnostic_fallback(monkeypatch) -> None:
    expected = SimpleNamespace(robust_recourse_cost=17.0)
    diagnostic = {
        "original_status": 13,
        "original_status_name": "SUBOPTIMAL",
        "fallback_used": True,
        "primary_economic_recourse_preserved": True,
        "Gamma_feasible": True,
    }
    monkeypatch.setattr(
        reporting,
        "evaluate_robust_service_detailed",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(reporting.SUBOPTIMAL_TIEBREAK_ERROR)),
    )
    monkeypatch.setattr(reporting, "_diagnose_and_recover", lambda *args: (expected, diagnostic))

    result, observed = reporting.evaluate_e4_service(SimpleNamespace(), [], 4)

    assert result is expected
    assert observed == diagnostic


def test_other_reporting_failures_are_not_silently_accepted(monkeypatch) -> None:
    monkeypatch.setattr(
        reporting,
        "evaluate_robust_service_detailed",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("different failure")),
    )
    with pytest.raises(RuntimeError, match="different failure"):
        reporting.evaluate_e4_service(SimpleNamespace(), [], 4)


def test_optimal_original_reporting_path_is_unchanged(monkeypatch) -> None:
    expected = SimpleNamespace(robust_recourse_cost=11.0)
    monkeypatch.setattr(reporting, "evaluate_robust_service_detailed", lambda *args, **kwargs: expected)

    result, diagnostic = reporting.evaluate_e4_service(SimpleNamespace(), [], 3)

    assert result is expected
    assert diagnostic["original_status_name"] == "OPTIMAL"
    assert diagnostic["fallback_used"] is False
