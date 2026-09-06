from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROVENANCE_FILES = tuple(sorted((ROOT / "artifacts").rglob("*.json"))) + tuple(
    sorted((ROOT / "configs").rglob("*.json"))
)
NONPORTABLE_PATH = re.compile(
    r"(?i)(?:(?<![a-z0-9+.-])[a-z]:[\\/]|/(?:Users|home)/[^/\s\"']+|/tmp/|"
    r"AppData[\\/]Local[\\/]Temp[\\/])"
)


def test_nonportable_path_pattern_distinguishes_paths_from_logical_references() -> None:
    for value in (
        r"C:\\Users\\researcher\\instances.tar.gz",
        "/Users/researcher/instances.tar.gz",
        "/home/researcher/instances.tar.gz",
        "/tmp/instances.tar.gz",
    ):
        assert NONPORTABLE_PATH.search(value)
    assert not NONPORTABLE_PATH.search("external://renault-raw/instances.tar.gz")


def test_committed_provenance_and_manifests_have_no_local_absolute_paths() -> None:
    tracked = {
        (ROOT / item).resolve()
        for item in subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    }
    violations: list[str] = []
    for path in PROVENANCE_FILES:
        if path.resolve() not in tracked:
            continue
        text = path.read_text(encoding="utf-8")
        if NONPORTABLE_PATH.search(text):
            violations.append(path.relative_to(ROOT).as_posix())
    assert violations == [], f"nonportable provenance paths: {violations}"
