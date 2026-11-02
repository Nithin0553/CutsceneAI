"""Pin and refresh the active Studio planner before Unreal source verification.

Unreal embeds a long-lived Python interpreter. Importing transfer_backend once
can leave an older module (25 actions) cached after a developer pulls changes
and prepares a new candidate (29 actions). This module synchronizes the *local
repository code* on disk, verifies canonical module origins and reloads the
dependency chain before any Unreal asset/actor creation. No project data or
saved candidate evidence is mutated.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
MODULES = (
    ("csir_plan", "integrations/unreal"),
    ("source_surface_gap", "packages/studio"),
    ("feature_dispatch", "packages/studio"),
    ("scalar_property_adapter", "packages/studio"),
    ("visual_activation", "packages/studio"),
    ("adaptive_components", "packages/studio"),
    ("transfer_backend", "packages/studio"),
    ("prepared_transfer", "packages/studio"),
)


class PlannerSyncError(RuntimeError):
    """A stale or shadowed editor planner cannot be trusted for transfer."""


def synchronize() -> dict[str, str]:
    """Refresh all local source/target planning modules, fail closed on shadowing.

    The module file paths are fixed repository code, never taken from a
    candidate plan or user-supplied path. Loading this pipeline is an explicit
    step before any actual engine mutation.
    """
    for _name, relative in MODULES:
        path = str(ROOT / relative)
        if path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)
    importlib.invalidate_caches()
    origins = {}
    for name, relative in MODULES:
        expected = (ROOT / relative / (name + ".py")).resolve()
        existing: ModuleType | None = sys.modules.get(name)
        if existing is not None:
            actual_raw = getattr(existing, "__file__", None)
            if not actual_raw or Path(actual_raw).resolve() != expected:
                raise PlannerSyncError(
                    "Unreal cached a shadowed " + name + " module. "
                    "Restart Unreal Editor and load the canonical Studio companion."
                )
        try:
            module = importlib.reload(existing) if existing is not None \
                else importlib.import_module(name)
        except Exception as exc:
            raise PlannerSyncError(
                "Cannot refresh current Studio planner module " + name +
                "; restart Unreal with the updated repository: " + str(exc)
            ) from exc
        if Path(str(getattr(module, "__file__", ""))).resolve() != expected:
            raise PlannerSyncError(
                "Studio planner imported from a non-repository path: " + name
            )
        origins[name] = str(expected)
    return origins
