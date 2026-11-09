"""Read-only diagnosis for stale Unreal Python transfer modules.

Run with Unreal: py "B:/Research/CutSceneAI/CutsceneAI/integrations/unreal/diagnose_backend_version.py"
No imports/reloads of CutSceneAI runtime modules; no project/level mutation.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import sys
from pathlib import Path
from typing import Any


def describe_module(name: str, expected_file: Path) -> dict[str, Any]:
    """Inspect the existing module cache and actual file without importing it."""
    expected = expected_file.resolve()
    exists = expected.is_file()
    contents = expected.read_bytes() if exists else b""
    module = sys.modules.get(name)
    loaded_name = getattr(module, "__file__", None) if module else None
    loaded_file = Path(loaded_name).resolve() if loaded_name else None
    verifier = getattr(module, "verify_prepared_artifacts", None) if module else None
    consts = repr(verifier.__code__.co_consts) if inspect.isfunction(verifier) else ""
    disk_new = b"differs materially from source-derived JSON at" in contents
    live_new = " differs materially from source-derived JSON at " in consts
    same = loaded_file == expected if loaded_file else None
    return {
        "module": name,
        "expected_file": str(expected),
        "file_exists": exists,
        "file_sha256": hashlib.sha256(contents).hexdigest() if exists else None,
        "on_disk_has_new_float_verifier": disk_new if exists else None,
        "loaded_in_python": module is not None,
        "loaded_file": str(loaded_file) if loaded_file else None,
        "loaded_from_expected_file": same,
        "loaded_has_new_float_verifier": live_new if verifier else None,
        "loaded_verifier_first_line": verifier.__code__.co_firstlineno if inspect.isfunction(verifier) else None,
    }


def run() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    backend = describe_module(
        "transfer_backend", root / "packages" / "studio" / "transfer_backend.py"
    )
    builder = describe_module(
        "build_level_sequence",
        root / "integrations" / "unreal" / "build_level_sequence.py",
    )
    if not backend["file_exists"]:
        diagnosis = "BACKEND_SOURCE_MISSING"
    elif not backend["on_disk_has_new_float_verifier"]:
        diagnosis = "LOCAL_SOURCE_OUTDATED_RUN_GIT_PULL"
    elif (
        backend["loaded_in_python"]
        and backend["loaded_from_expected_file"] is False
    ):
        diagnosis = "WRONG_MODULE_IMPORT_PATH"
    elif (
        backend["loaded_in_python"]
        and backend["loaded_has_new_float_verifier"] is False
    ):
        diagnosis = "STALE_IMPORTED_MODULE_RESTART_UNREAL_AFTER_GIT_PULL"
    else:
        diagnosis = "CORRECT_SOURCE_ON_DISK_CONFIRM_FRESH_ENGINE_IMPORT"
    result = {
        "kind": "cutsceneai.unreal.backend_version_diagnostic",
        "diagnosis": diagnosis,
        "python_executable": sys.executable,
        "backend": backend,
        "builder": builder,
        "does_not_modify_level": True,
    }
    print("[CutSceneAI] TRANSFER BACKEND DIAGNOSTIC")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    run()
