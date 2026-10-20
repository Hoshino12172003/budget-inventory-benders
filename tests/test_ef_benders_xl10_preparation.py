import json
from pathlib import Path

import pytest

from experiments import run_ef_benders_scaling as ef_runner
from scripts.audit_ef_benders_scaling_l10_preparation import theoretical_size
from scripts import run_ef_benders_scaling_xl10_pilot as xl_runner


def _write_archive(root: Path) -> None:
    attempt = root / "worker_logs" / xl_runner.CONDITION_ID / "attempt-001"
    canonical = root / "runs" / xl_runner.CONDITION_ID
    attempt.mkdir(parents=True)
    canonical.mkdir(parents=True)
    payloads = {
        "result.json": {"solver_status": "OPTIMAL", "exact_certification": True, "cut_validity": True},
        "iteration_trajectory.json": [],
        "first_stage_solution.json": {"x": []},
        "resource_monitor.json": {"stop_reason": None, "worker_return_code": 0, "peak_process_tree_memory_gib": 1.0},
        "outcome.json": {"status": "SUCCESS"},
    }
    for name, value in payloads.items():
        text = json.dumps(value) + "\n"
        (attempt / name).write_text(text, encoding="utf-8")
        (canonical / name).write_text(text, encoding="utf-8")
    provenance = {
        "result_sha256": xl_runner.sha256(attempt / "result.json"),
        "trajectory_sha256": xl_runner.sha256(attempt / "iteration_trajectory.json"),
        "first_stage_sha256": xl_runner.sha256(attempt / "first_stage_solution.json"),
    }
    text = json.dumps(provenance) + "\n"
    (attempt / "provenance.json").write_text(text, encoding="utf-8")
    (canonical / "provenance.json").write_text(text, encoding="utf-8")


def test_xl10_static_size_matches_frozen_direct_counts():
    size = theoretical_size(30, 30, 14, 2)
    assert size["product_local_scenario_blocks"] == 6524
    assert size["risk_budget_allocations"] == 120
    assert size["ef_oracle"] == {"variables": 6073887, "constraints": 404608, "nonzeros": 18223332}
    assert size["direct_extensive_form"] == {"variables": 6075177, "constraints": 405479, "nonzeros": 18422892}


def test_protocol_is_single_condition_authorized_and_resource_frozen():
    config = ef_runner.load_config(xl_runner.DEFAULT_CONFIG)
    xl_runner.validate_protocol(config)
    assert config["formal_run_authorized"] is True
    assert config["authorized_condition_ids"] == [xl_runner.CONDITION_ID]
    assert config["resource_policy"]["maximum_process_tree_memory_gib_by_size"] == {"XL10": 8}
    assert config["resource_policy"]["minimum_available_memory_gib_by_size"] == {"XL10": 12}
    assert ef_runner.candidate(config) == {"condition_id": xl_runner.CONDITION_ID, "size": "XL10", "seed": 20260921}
    with pytest.raises(RuntimeError, match="outside"):
        ef_runner.candidate(config, "EF_XL10_S20260922")


def test_completed_pilot_dry_run_is_closed_without_optimization(monkeypatch):
    original = ef_runner.dry_run

    def stable_resources(config_path, condition_id):
        row = original(config_path, condition_id)
        row["resource_gate"]["available_memory_gib"] = 64.0
        row["resource_gate"]["free_disk_gib"] = 64.0
        return row

    monkeypatch.setattr(xl_runner.runner, "dry_run", stable_resources)
    monkeypatch.setattr(
        xl_runner,
        "git_status_for_execution",
        lambda _output: {"head": "test", "clean_for_execution": True, "unexpected": []},
    )
    monkeypatch.setattr(xl_runner, "active_solver_workers", lambda: [])
    dry = xl_runner.build_dry_run()
    assert dry["decision"] == "BLOCKED"
    assert dry["optimization_calls"] == 0
    assert all(dry["identity_checks"].values())
    assert dry["gates"]["attempt_absent"] is False
    assert dry["gates"]["canonical_absent"] is False
    assert dry["next_attempt"] == "attempt-001"


def test_execute_is_closed_before_worker_launch_when_authorization_is_false(monkeypatch, tmp_path):
    config = ef_runner.load_config(xl_runner.DEFAULT_CONFIG)
    config["formal_run_authorized"] = False
    closed = tmp_path / "closed.json"
    closed.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(
        ef_runner,
        "run_condition",
        lambda *_args, **_kwargs: pytest.fail("optimization launcher must not be called"),
    )
    with pytest.raises(RuntimeError, match="NOT_AUTHORIZED"):
        xl_runner.execute(closed)


def test_archive_acceptance_requires_hashes_and_byte_identity(tmp_path):
    _write_archive(tmp_path)
    audit = xl_runner.verify_archive(tmp_path, xl_runner.CONDITION_ID)
    assert all(audit["checks"].values())
    (tmp_path / "runs" / xl_runner.CONDITION_ID / "result.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="ARCHIVE_OR_CERTIFICATION_FAILURE"):
        xl_runner.verify_archive(tmp_path, xl_runner.CONDITION_ID)
