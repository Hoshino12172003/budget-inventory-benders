from __future__ import annotations

import json
from pathlib import Path


FREEZE_REGISTRY = "experiments/configs/formal/formal_execution_freeze_v1.json"


def require_protocol_not_frozen(repository_root: Path, config_path: Path) -> None:
    root = repository_root.resolve()
    relative = config_path.resolve().relative_to(root).as_posix()
    registry_path = root / FREEZE_REGISTRY
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if relative in registry["revoked_config_paths"]:
        raise PermissionError(f"FORMAL_PROTOCOL_FROZEN:{relative}")
