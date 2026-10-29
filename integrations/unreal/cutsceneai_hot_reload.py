"""Reload CutSceneAI Python modules inside an already-running Unreal Editor.

Typical Unreal Python Output Log command:
    import sys
    sys.path.insert(0, "B:/Research/CutsceneAI/CutsceneAI/integrations/unreal")
    import cutsceneai_hot_reload
    cutsceneai_hot_reload.reload_project_python()

Only reloads Python code. It never saves, deletes, spawns or modifies any
Unreal actor/asset. It CANNOT repair a corrupt Unreal package or loaded
native object reference after a failed force-deletion. Restart Unreal and
inspect a known-good project copy in that exceptional case.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_ORDER = (
    "csir_plan",
    "sampling_plan",
    "scene_prep",
    "hierarchy_plan",
    "hierarchy_local",
    "ced_preflight",
    "transfer_readiness",
    "hierarchy_realization",
    "unreal_compat",
    "cinetwin_hierarchy_runtime",
    "transfer_backend",
    "build_level_sequence",
)


class HotReloadError(RuntimeError):
    """A requested Python reload does not originate from this repo."""


def _inside_repo(path: str | Path) -> bool:
    try:
        return Path(path).resolve().is_relative_to(PROJECT_ROOT.resolve())
    except (OSError, ValueError):
        return False


def _verify_module_origin(module: object, name: str) -> None:
    module_file = getattr(module, "__file__", None)
    if not module_file or not _inside_repo(module_file):
        raise HotReloadError(
            f"Cannot reload {name}: module is not loaded from the active CutSceneAI repo."
        )


def reload_project_python() -> dict[str, object]:
    """Reload a fixed whitelist of CutSceneAI modules in dependency order.

    Reload after editing Python sources and when the previous generator call
    has finished. Do not keep stale symbol references imported via from-import
    between runs: use build_level_sequence.build_prepared_files.
    """
    root = PROJECT_ROOT.resolve()
    if not (root / "integrations" / "unreal" / "build_level_sequence.py").is_file():
        raise HotReloadError("Active directory does not look like a CutSceneAI checkout.")
    for directory in (
        root / "integrations" / "unreal",
        root / "packages" / "cinetwin",
        root / "packages" / "studio",
    ):
        directory_str = str(directory)
        if directory_str not in sys.path:
            sys.path.insert(0, directory_str)
    # Check all already-loaded modules up front, before changing anything.
    for name in MODULE_ORDER:
        module = sys.modules.get(name)
        if module is not None:
            _verify_module_origin(module, name)

    importlib.invalidate_caches()
    fresh = []
    reloaded = []
    for name in MODULE_ORDER:
        module = sys.modules.get(name)
        if module is None:
            module = importlib.import_module(name)
            _verify_module_origin(module, name)
            fresh.append(name)
        else:
            importlib.reload(module)
            reloaded.append(name)
    print(
        "[CutSceneAI] Python HOT RELOAD: OK; "
        f"{len(reloaded)} reloaded, {len(fresh)} imported."
    )
    print("[CutSceneAI] Unreal native objects, open level and assets unchanged.")
    return {
        "status": "PYTHON_RELOADED",
        "reloaded": reloaded,
        "imported": fresh,
        "engine_restarted": False,
        "unreal_assets_modified": False,
    }
