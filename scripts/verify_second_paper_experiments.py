from __future__ import annotations

import fnmatch
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments/second_paper_experiments.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_hash(root: Path, excluded_globs: list[str]) -> tuple[int, str]:
    records = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if any(fnmatch.fnmatch(relative, pattern) for pattern in excluded_globs):
            continue
        records.append(f"{relative}\t{path.stat().st_size}\t{sha256(path)}")
    return len(records), hashlib.sha256("\n".join(sorted(records)).encode("utf-8")).hexdigest()


def verify_experiment(spec: dict) -> dict:
    runner = ROOT / spec["runner"]
    config = ROOT / spec["config"]
    result_root = ROOT / spec["result_root"]
    if not runner.is_file() or not config.is_file() or not result_root.is_dir():
        raise RuntimeError(f"{spec['id']}: missing runner, config, or result root")

    results = sorted(result_root.glob(spec["result_glob"]))
    if len(results) != spec["expected_results"]:
        raise RuntimeError(
            f"{spec['id']}: expected {spec['expected_results']} results, found {len(results)}"
        )
    for result_path in results:
        for filename in spec["required_siblings"]:
            if not (result_path.parent / filename).is_file():
                raise RuntimeError(f"{spec['id']}: missing {filename} beside {result_path}")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get(spec["status_field"]) != spec["status_value"]:
            raise RuntimeError(f"{spec['id']}: non-optimal result {result_path}")
        certification_field = spec.get("certification_field")
        if certification_field and result.get(certification_field) != spec["certification_value"]:
            raise RuntimeError(f"{spec['id']}: uncertified result {result_path}")

        provenance_path = result_path.parent / "provenance.json"
        if provenance_path.is_file():
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            if provenance.get("result_sha256") and provenance["result_sha256"] != sha256(result_path):
                raise RuntimeError(f"{spec['id']}: result provenance mismatch {result_path}")
            solution_path = result_path.parent / "first_stage_solution.json"
            if (
                solution_path.is_file()
                and provenance.get("first_stage_solution_sha256")
                and provenance["first_stage_solution_sha256"] != sha256(solution_path)
            ):
                raise RuntimeError(f"{spec['id']}: solution provenance mismatch {solution_path}")

    file_count, observed_tree_hash = tree_hash(result_root, spec.get("excluded_tree_globs", []))
    if observed_tree_hash != spec["tree_sha256"]:
        raise RuntimeError(
            f"{spec['id']}: result-tree hash mismatch: {observed_tree_hash} != {spec['tree_sha256']}"
        )
    for relative, expected_hash in spec.get("required_file_hashes", {}).items():
        path = result_root / relative
        if not path.is_file() or sha256(path) != expected_hash:
            raise RuntimeError(f"{spec['id']}: required file hash mismatch: {relative}")
    for commit in spec["source_commits"]:
        if subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=ROOT, capture_output=True
        ).returncode:
            raise RuntimeError(f"{spec['id']}: unavailable source commit {commit}")
    return {
        "id": spec["id"],
        "results": len(results),
        "bundle_files": file_count,
        "tree_sha256": observed_tree_hash,
        "reproducibility_status": spec["reproducibility_status"],
    }


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    dependency = manifest["common_dependencies"]
    expected = dependency["expected_json_files_each"]
    for key in ("instances", "x0", "calibration"):
        files = list((ROOT / dependency[key]).glob("*.json"))
        if len(files) != expected:
            raise RuntimeError(f"common dependency {key}: expected {expected} JSON files, found {len(files)}")
    report = [verify_experiment(spec) for spec in manifest["experiments"]]
    print(json.dumps({"status": "PASS", "experiments": report}, indent=2))


if __name__ == "__main__":
    main()
