"""Read-only editor reflection census for Unreal Engine and installed plugins.

Uses reflection rather than a fixed Unreal object list, so newly exposed
native/Blueprint Python classes enter the evidence registry automatically.
Class discovery is NOT evidence of a working Unity->Unreal adapter.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def census(api: Any = None) -> dict[str, Any]:
    if api is None:
        import unreal as api

    native_types = []
    for name in sorted(dir(api)):
        if name.startswith("_"):
            continue
        try:
            obj = getattr(api, name)
            if not inspect.isclass(obj):
                continue
            ancestors = [cls.__name__ for cls in getattr(obj, "__mro__", ())[1:]]
            native_types.append({
                "native_type": name,
                "bases": ancestors[:8],
                "provider": str(getattr(obj, "__module__", "")),
            })
        except Exception:
            # Some plugin-defined Python descriptors may be lazy, inaccessible,
            # or raise; skipping them must be counted rather than hidden.
            native_types.append({
                "native_type": name,
                "inspection_status": "REFLECTION_UNAVAILABLE",
            })

    editor_actors = []
    subsystem = getattr(api, "EditorActorSubsystem", None)
    get_subsystem = getattr(api, "get_editor_subsystem", None)
    if subsystem is not None and callable(get_subsystem):
        try:
            for actor in get_subsystem(subsystem).get_all_level_actors():
                try:
                    actor_type = actor.get_class().get_name()
                    label = actor.get_actor_label()
                    editor_actors.append({
                        "actor_label": str(label),
                        "native_type": str(actor_type),
                        "native_package": str(actor.get_path_name()).split(":")[0],
                    })
                except Exception:
                    editor_actors.append({"inspection_status": "ACTOR_READBACK_UNAVAILABLE"})
        except Exception:
            editor_actors.append({"inspection_status": "ACTOR_SUBSYSTEM_UNAVAILABLE"})
    else:
        editor_actors.append({"inspection_status": "ACTOR_SUBSYSTEM_UNAVAILABLE"})

    project_path = ""
    paths = getattr(api, "Paths", None)
    if paths is not None and callable(getattr(paths, "get_project_file_path", None)):
        project_path = str(paths.get_project_file_path())
    engine_version = "UNKNOWN_UNREAL_VERSION"
    system = getattr(api, "SystemLibrary", None)
    if system is not None and callable(getattr(system, "get_engine_version", None)):
        try:
            engine_version = str(system.get_engine_version())
        except Exception:
            pass
    return {
        "kind": "cutsceneai.engine.feature_surface",
        "schema_version": "0.2.0",
        "engine": "unreal",
        "engine_version": engine_version,
        "project_fingerprint": hashlib.sha256(
            project_path.encode("utf-8")).hexdigest() if project_path else "",
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "registered_types": native_types,
        "loaded_level_actors": editor_actors,
        "reflection_unavailable_count": sum(
            "inspection_status" in item for item in native_types),
        "verification": "TARGET_CAPABILITY_DISCOVERY_ONLY_NOT_TRANSFER_VERIFIED",
        "limitations": [
            "Python reflection sees only types exposed by this Unreal Editor build/plugins.",
            "Classes present in the editor do not automatically have source adapters.",
            "Source-target parity requires generated native assets and independent readback.",
        ],
    }


def save_latest(api: Any = None, *, root: str | Path | None = None) -> Path:
    output_root = (
        Path(root).resolve()
        if root is not None
        else Path.home() / ".cutsceneai-studio" / "runs" / "feature-surfaces"
    )
    output_root.mkdir(parents=True, exist_ok=True)
    data = census(api)
    name = "unreal-feature-surface-" + datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8] + ".json"
    output = output_root / name
    with output.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print("[CutSceneAI] Unreal native feature surface: " + str(output))
    print("[CutSceneAI] Reflected types: {} | loaded-level actors: {}".format(
        len(data["registered_types"]), len(data["loaded_level_actors"])))
    print("[CutSceneAI] Native type discovery is not proof of conversion.")
    return output
