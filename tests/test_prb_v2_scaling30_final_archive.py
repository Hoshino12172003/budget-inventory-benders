from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments/analysis/prb_v2_scaling30_final/build_archive.py"


def load_archive_module():
    spec = importlib.util.spec_from_file_location("prb_v2_scaling30_final_archive", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_archive_integrity_and_statistics() -> None:
    module = load_archive_module()
    module.verify_archive()


def test_archive_builder_has_no_solver_entry_point() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "gurobipy" not in imported_modules
    assert "solve_prb_benders" not in called_names
    assert "solve_accelerated_prb_benders" not in called_names
