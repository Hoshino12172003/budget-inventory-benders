from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments/run_renault8_prb_v2_paired_v1.py"
SPEC = importlib.util.spec_from_file_location("renault8_prb_v2_paired_v1", SCRIPT)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_protocol_is_frozen_to_eight_cases_and_two_methods() -> None:
    assert runner.CASE_IDS == (
        "210202",
        "210628",
        "210129",
        "210310",
        "210330",
        "210323",
        "210428",
        "210611",
    )
    assert runner.METHODS == ("basic", "v2")
    assert (runner.GAMMA, runner.BETA, runner.LAMBDA_R) == (2, 1.0, 0.05)
    assert runner.V2_WORKERS == 2
    assert runner.GUROBI_THREADS == 1


@pytest.mark.parametrize("case_id", runner.CASE_IDS)
def test_frozen_input_and_direct_reference_identity(case_id: str) -> None:
    loaded = runner.load_frozen_renault_case(case_id)
    reference = runner.direct_reference(case_id, loaded)
    assert reference["historical_status"] == "CERTIFIED_EXACT"
    assert reference["objective"] > 0
    assert loaded["gamma"] == 2
    assert loaded["lambda_r"] == 0.05
    assert loaded["budget"] > 0


def test_v2_call_is_explicitly_nonselective_process_backend() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'parallel_workers=workers' in source
    assert '_oracle_backend="process"' in source
    assert '_selective_separation=False' in source
    assert 'gp.setParam("Threads", GUROBI_THREADS)' in source


def test_result_verification_rejects_partial_and_tampered_outputs(tmp_path: Path) -> None:
    identity = {"frozen": True}
    partial = tmp_path / "partial"
    partial.mkdir()
    (partial / "result.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="partial result"):
        runner.verified_result(partial, identity)

    complete = tmp_path / "complete"
    complete.mkdir()
    result = {
        "condition_completed": True,
        "certification_class": "strict_original",
    }
    result_path = complete / "result.json"
    result_path.write_text(json.dumps(result) + "\n", encoding="utf-8")
    provenance = {
        "identity": identity,
        "result_sha256": runner.sha256(result_path),
    }
    (complete / "provenance.json").write_text(
        json.dumps(provenance) + "\n", encoding="utf-8"
    )
    assert runner.verified_result(complete, identity)
    provenance["result_sha256"] = "0" * 64
    (complete / "provenance.json").write_text(
        json.dumps(provenance) + "\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="damaged result"):
        runner.verified_result(complete, identity)


def test_output_is_isolated_from_historical_roots() -> None:
    relative = runner.OUTPUT_ROOT.relative_to(ROOT).as_posix()
    assert relative == "experiments/results/renault8_prb_v2_paired_v1"
    assert "e1_empirical_8case_v1" not in relative
    assert "scaling30" not in relative
