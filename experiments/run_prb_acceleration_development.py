from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys
import threading
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from robust_inventory_reconfiguration.accelerated_product_risk_budget_benders import (
    solve_accelerated_prb_benders,
)
from robust_inventory_reconfiguration.instance import load_instance


OUTPUT = ROOT / "experiments/results/prb_acceleration_development_v4"
CASES = ("210202", "L", "XL_low")
WORKERS = 8


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def normalized_solution(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("x") or not isinstance(payload["x"][0], dict):
        return payload
    depot_ids = payload["depot_ids"]
    product_ids = payload["product_ids"]
    x_values = {
        (row["depot_id"], row["product_id"]): float(row["value"])
        for row in payload["x"]
    }
    y_values = {row["depot_id"]: int(row["value"]) for row in payload["y"]}
    return {
        **payload,
        "x": [
            [x_values[(depot, product)] for product in product_ids]
            for depot in depot_ids
        ],
        "y": [y_values[depot] for depot in depot_ids],
    }


def load_problem(case: str):
    if case == "210202":
        instance = load_instance(ROOT / "data/formal_instances_v2/210202.json")
        calibration = read_json(
            ROOT / "artifacts/renault_empirical_8case_v1/calibration/210202.json"
        )
        return instance, instance.initial_inventory, float(calibration["B_ref"])
    prepared = ROOT / f"experiments/results/e1c_development_probe_v1/{case}/PREPARE"
    instance = load_instance(prepared / "instance.json")
    baseline = read_json(prepared / "baseline.json")
    return instance, instance.initial_inventory, float(baseline["B_ref"])


def load_baselines(case: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if case == "210202":
        prb_root = ROOT / "experiments/results/e1_empirical_8case_v1/E1-210202-PRB"
        pure_root = ROOT / "experiments/results/e1b_pure_benders_v1/E1B-210202-PURE"
        prb_raw = read_json(prb_root / "result.json")
        pure_raw = read_json(pure_root / "result.json")
        prb_solution = normalized_solution(
            read_json(prb_root / "first_stage_solution.json")
        )
        pure_solution = normalized_solution(
            read_json(pure_root / "first_stage_solution.json")
        )
        prb = {
            "objective": prb_raw["objective"],
            "first_stage_expenditure": prb_raw["first_stage_expenditure"],
            "robust_recourse_cost": prb_raw["robust_recourse_cost"],
            "iterations": prb_raw["iteration_count"],
            "cuts": prb_raw["unique_product_cuts"],
            "core_runtime": prb_raw["runtime_seconds"],
            "master_runtime": prb_raw["master_runtime_seconds"],
            "oracle_runtime": prb_raw["subproblem_runtime_seconds"],
            "certification_runtime": prb_raw["certification_runtime_seconds"],
            "certified": prb_raw["status"] == "OPTIMAL"
            and prb_raw["global_coupling_pass"],
            "solution": prb_solution,
        }
        pure = {
            "objective": pure_raw["objective"],
            "iterations": pure_raw["iteration_count"],
            "cuts": pure_raw["aggregate_cut_count"],
            "core_runtime": pure_raw["core_runtime_seconds"],
            "certified": pure_raw["status"] == "OPTIMAL"
            and pure_raw["cut_validity_pass"],
            "solution": pure_solution,
        }
        return pure, prb

    root = ROOT / f"experiments/results/e1c_development_probe_v1/{case}"
    prb_raw = read_json(root / "PRB_BENDERS/result.json")
    pure_raw = read_json(root / "PURE_BENDERS/result.json")
    prb = {
        "objective": prb_raw["solution"]["objective"],
        "first_stage_expenditure": prb_raw["solution"]["first_stage_expenditure"],
        "robust_recourse_cost": prb_raw["solution"]["robust_recourse_cost"],
        "iterations": prb_raw["iterations"],
        "cuts": prb_raw["cuts"],
        "core_runtime": prb_raw["core_runtime_seconds"],
        "master_runtime": prb_raw["master_runtime_seconds"],
        "oracle_runtime": prb_raw["oracle_runtime_seconds"],
        "certification_runtime": prb_raw["certification_runtime_seconds"],
        "certified": prb_raw["exact_certification"]
        and prb_raw["global_coupling_pass"],
        "solution": prb_raw["solution"],
    }
    pure = {
        "objective": pure_raw["solution"]["objective"],
        "iterations": pure_raw["iterations"],
        "cuts": pure_raw["cuts"],
        "core_runtime": pure_raw["core_runtime_seconds"],
        "certified": pure_raw["exact_certification"],
        "solution": pure_raw["solution"],
    }
    return pure, prb


class PeakMemoryMonitor:
    def __init__(self) -> None:
        self.peak_bytes: int | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        try:
            import psutil

            process = psutil.Process()
            while not self._stop.is_set():
                total = process.memory_info().rss
                for child in process.children(recursive=True):
                    try:
                        total += child.memory_info().rss
                    except psutil.Error:
                        pass
                self.peak_bytes = max(self.peak_bytes or 0, total)
                self._stop.wait(0.02)
        except ImportError:
            self.peak_bytes = None

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()


def max_x_difference(left: dict[str, Any], right: dict[str, Any]) -> float:
    return max(
        abs(a - b)
        for left_row, right_row in zip(left["x"], right["x"])
        for a, b in zip(left_row, right_row)
    )


def solve_case(case: str) -> dict[str, Any]:
    instance, x0, budget = load_problem(case)
    if x0 is None:
        raise RuntimeError(f"{case} has no x0")
    pure, original = load_baselines(case)
    with PeakMemoryMonitor() as memory:
        solved = solve_accelerated_prb_benders(
            instance,
            x0,
            budget,
            gamma=2,
            lambda_r=0.05,
            relative_gap_tolerance=1e-6,
            cut_tolerance=1e-7,
            max_iterations=500,
            parallel_workers=WORKERS,
        )
    accelerated_solution = asdict(solved.solution)
    objective_difference = abs(solved.solution.objective - original["objective"])
    recourse_difference = abs(
        solved.solution.robust_recourse_cost - original["robust_recourse_cost"]
    )
    x_difference = max_x_difference(accelerated_solution, original["solution"])
    same_y = accelerated_solution["y"] == original["solution"]["y"]
    correctness = (
        objective_difference <= 1e-4
        and recourse_difference <= 1e-4
        and solved.exact_certification_pass
        and solved.global_risk_budget_coupling_pass
        and original["certified"]
    )
    return {
        "case": case,
        "development_only": True,
        "paper_final_observation": False,
        "algorithm": "prb_accelerated",
        "Gamma": 2,
        "lambda_R": 0.05,
        "beta": 1.0,
        "parallel_worker_count": WORKERS,
        "product_subproblem_threads": 1,
        "result": asdict(solved),
        "peak_process_tree_memory_gib": (
            memory.peak_bytes / (1024**3) if memory.peak_bytes is not None else None
        ),
        "original_prb": original,
        "pure_benders": pure,
        "comparison": {
            "objective_difference_vs_original": objective_difference,
            "recourse_difference_vs_original": recourse_difference,
            "same_y_as_original": same_y,
            "max_x_difference_vs_original": x_difference,
            "solution_relation": (
                "EXACT_SOLUTION_IDENTITY"
                if same_y and x_difference <= 1e-5
                else "CERTIFIED_OPTIMAL_FACE_EQUIVALENT"
                if correctness
                else "NOT_ESTABLISHED"
            ),
            "correctness_pass": correctness,
            "runtime_reduction_vs_original": 1.0
            - solved.total_runtime / original["core_runtime"],
            "oracle_time_reduction_vs_original": 1.0
            - solved.separation_runtime / original["oracle_runtime"],
            "iteration_change_vs_original": len(solved.iterations)
            - original["iterations"],
            "state_solve_reduction_fraction": solved.product_solves_avoided
            / max(
                1,
                solved.product_solves_avoided
                + solved.product_subproblem_evaluations,
            ),
            "runtime_ratio_vs_pure": solved.total_runtime / pure["core_runtime"],
            "iteration_change_vs_pure": len(solved.iterations) - pure["iterations"],
            "objective_difference_vs_pure": abs(
                solved.solution.objective - pure["objective"]
            ),
        },
    }


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite {OUTPUT}")
    OUTPUT.mkdir(parents=True)
    rows = []
    for case in CASES:
        print(f"[ACCELERATED PRB] {case}", flush=True)
        row = solve_case(case)
        rows.append(row)
        write_json(OUTPUT / case / "result.json", row)
        print(
            f"[DONE] {case}: objective={row['result']['solution']['objective']:.9f} "
            f"runtime={row['result']['total_runtime']:.6f}s "
            f"oracle={row['result']['separation_runtime']:.6f}s",
            flush=True,
        )
    status = (
        "ACCELERATION_CORRECTNESS_ESTABLISHED"
        if all(row["comparison"]["correctness_pass"] for row in rows)
        else "ACCELERATION_CORRECTNESS_NOT_ESTABLISHED"
    )
    write_json(
        OUTPUT / "summary.json",
        {
            "status": status,
            "development_only": True,
            "paper_final_observation": False,
            "selective_separation_implemented": False,
            "full_exact_final_verification": True,
            "cases": rows,
        },
    )
    print(status)


if __name__ == "__main__":
    main()
