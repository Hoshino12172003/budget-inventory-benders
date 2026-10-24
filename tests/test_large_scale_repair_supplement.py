from __future__ import annotations

import json
import csv
import sys
from pathlib import Path

import pytest

import experiments.run_prb_large_scale_simulation as runner
import experiments.summarize_prb_large_scale_simulation as summarizer


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def configure_grid(monkeypatch, tmp_path: Path, seeds=(1, 2)) -> Path:
    output = tmp_path / "results"
    monkeypatch.setattr(runner, "OUT", output)
    monkeypatch.setattr(runner, "REPAIR_SUMMARY", output / "canonical_prepare_repair_summary.json")
    monkeypatch.setattr(runner, "COMPLETENESS_SUMMARY", output / "completeness.json")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "MAIN_SCALES", ("L10",))
    monkeypatch.setattr(runner, "MAIN_SEEDS", seeds)
    (tmp_path / "docs").mkdir()
    return output


def test_repair_only_archives_error_prepare_and_preserves_success(
    monkeypatch, tmp_path: Path
) -> None:
    output = configure_grid(monkeypatch, tmp_path)
    failed = output / "L10/1/PREPARE"
    successful = output / "L10/2/PREPARE"
    write_json(failed / "result.json", {"task": "PREPARE", "status": "ERROR", "terminal_record": True})
    (failed / "stderr.log").write_text("original failure", encoding="utf-8")
    write_json(successful / "result.json", {"task": "PREPARE", "status": "OPTIMAL", "terminal_record": True})
    original_success = (successful / "result.json").read_bytes()
    monkeypatch.setattr(runner, "preflight", lambda: [20.0])
    monkeypatch.setattr(runner, "gitsha", lambda: "test")

    def fake_run(scale, seed, task):
        assert (scale, seed, task) == ("L10", 1, "PREPARE")
        target = runner.tdir(scale, seed, task)
        write_json(target / "result.json", {"task": task, "status": "OPTIMAL", "terminal_record": True})
        write_json(target / "baseline.json", {"x0_hash": "x", "B_ref": 1.0, "repair_profile": "repair"})
        return runner.rj(target / "result.json")

    monkeypatch.setattr(runner, "run_monitored", fake_run)
    summary = runner.repair_failed_prepares()

    assert summary["attempted"] == 1
    assert summary["repaired_successfully"] == 1
    assert summary["still_failed"] == 0
    assert (output / "L10/1/PREPARE_PRE_REPAIR/stderr.log").read_text() == "original failure"
    assert (successful / "result.json").read_bytes() == original_success


@pytest.mark.parametrize("status", ("TIME_LIMIT", "RESOURCE_STOP", "ERROR"))
def test_supplement_preserves_terminal_nonoptimal_results(
    monkeypatch, tmp_path: Path, status: str
) -> None:
    configure_grid(monkeypatch, tmp_path, seeds=(1,))
    monkeypatch.setattr(runner, "METHODS", ("pure_benders",))
    monkeypatch.setattr(runner, "validate_prepared_identity", lambda *_: {})
    monkeypatch.setattr(runner, "build_completeness", lambda: {})
    write_json(
        runner.tdir("L10", 1, "pure_benders") / "result.json",
        {"task": "pure_benders", "status": status, "terminal_record": True},
    )
    calls = []
    monkeypatch.setattr(runner, "run_monitored", lambda *args: calls.append(args))

    runner.supplement_missing_main()
    assert calls == []


def test_supplement_runs_only_missing_then_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    configure_grid(monkeypatch, tmp_path, seeds=(1,))
    monkeypatch.setattr(runner, "METHODS", ("pure_benders",))
    baseline = {
        "instance_hash": "i", "x0_hash": "x", "B_ref": 1.0,
    }
    monkeypatch.setattr(runner, "validate_prepared_identity", lambda *_: baseline)
    monkeypatch.setattr(runner, "build_completeness", lambda: {})
    calls = []

    def fake_run(scale, seed, method):
        calls.append((scale, seed, method))
        value = {"scale": scale, "seed": seed, "task": method, "method": method,
                 "status": "OPTIMAL", "terminal_record": True, "exact_certification": True,
                 "instance_hash": "i", "x0_hash": "x", "B_ref": 1.0,
                 "Gamma": runner.GAMMA, "lambda_R": runner.LAMBDA_R}
        write_json(runner.tdir(scale, seed, method) / "result.json", value)
        return value

    monkeypatch.setattr(runner, "run_monitored", fake_run)
    runner.supplement_missing_main()
    runner.supplement_missing_main()
    assert calls == [("L10", 1, "pure_benders")]


def test_algorithm_identity_mismatch_fails_closed() -> None:
    baseline = {"instance_hash": "i", "x0_hash": "x", "B_ref": 1.0}
    record = {"scale": "L10", "seed": 1, "instance_hash": "wrong", "x0_hash": "x",
              "B_ref": 1.0, "Gamma": runner.GAMMA, "lambda_R": runner.LAMBDA_R}
    with pytest.raises(RuntimeError, match="ALGORITHM_IDENTITY_MISMATCH"):
        runner.validate_algorithm_identity(record, "L10", 1, baseline)


def test_missing_prepare_error_is_the_only_rerunnable_error(monkeypatch, tmp_path: Path) -> None:
    configure_grid(monkeypatch, tmp_path, seeds=(1,))
    target = runner.tdir("L10", 1, "pure_benders")
    write_json(target / "result.json", {"status": "ERROR", "terminal_record": True})
    (target / "stderr.log").write_text("PREPARE_NOT_COMPLETE", encoding="utf-8")
    assert runner.missing_prepare_only_error("L10", 1, "pure_benders") is True
    (target / "stderr.log").write_text("cut validity failure", encoding="utf-8")
    assert runner.missing_prepare_only_error("L10", 1, "pure_benders") is False


def test_summary_accepts_error_record_with_task_but_no_method(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "results"
    write_json(
        root / "XL10/20260924/pure_benders/result.json",
        {"scale": "XL10", "seed": 20260924, "task": "pure_benders", "status": "ERROR"},
    )
    monkeypatch.setattr(sys, "argv", ["summary", str(root)])
    summarizer.main()

    with (root / "simulation_run_table.csv").open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["method"] == "pure_benders"
    assert rows[0]["status"] == "ERROR"
    with (root / "simulation_completeness_table.csv").open(encoding="utf-8-sig") as handle:
        completeness = list(csv.DictReader(handle))
    assert len(completeness) == 30
    issue = next(x for x in completeness if x["scale"] == "XL10" and x["seed"] == "20260924")
    assert issue["pure_status"] == "ERROR"
