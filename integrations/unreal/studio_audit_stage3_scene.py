"""CutSceneAI Stage 3: READ-ONLY saved-actor readback in Unreal Editor.

Run after Save All, closing and reopening the correct level.
No actors, assets, level transforms, or mappings are changed by this script.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any


class Stage3AuditError(RuntimeError):
    pass


def _read(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise Stage3AuditError(f"Expected JSON object in {path}")
    return data


def _normal_path(value: str) -> str:
    # Windows-relative Unreal project paths and slash styles are common.
    return os.path.normcase(os.path.normpath(os.path.abspath(value))).casefold()


def _object_path(obj: Any) -> str | None:
    return str(obj.get_path_name()) if obj is not None else None


def _mesh_asset_path(actor: Any, api: Any) -> str | None:
    comp = actor.get_component_by_class(api.SkeletalMeshComponent)
    if comp is None:
        return None
    for prop in ("skeletal_mesh_asset", "skeletal_mesh"):
        try:
            asset = comp.get_editor_property(prop)
        except Exception:
            continue
        if asset is not None:
            return _object_path(asset).split(".")[0]
    return None


def run(receipt_path: str, *, unreal_api: Any = None) -> dict:
    """Audit live loaded actor state; write a new report beside the receipt."""
    api = unreal_api
    if api is None:
        import unreal as api

    receipt = _read(receipt_path)
    if receipt.get("kind") != "cutsceneai.studio.stage3_scene_receipt" or receipt.get("status") != "ACTORS_CREATED_LEVEL_NOT_YET_VERIFIED":
        raise Stage3AuditError("Stage 3 receipt is not a completed creation receipt")
    plan = _read(receipt["plan_path"])
    if plan.get("kind") != "cutsceneai.studio.stage3_scene_plan":
        raise Stage3AuditError("Invalid Stage 3 plan")
    expected = plan.get("actors", [])
    if len(expected) != 8 or len(receipt.get("actors_created", [])) != 8:
        raise Stage3AuditError("Expected exactly eight planned and created actors")
    if {r["actor_label"] for r in expected} != {r["actor_label"] for r in receipt["actors_created"]}:
        raise Stage3AuditError("Plan/receipt actor labels disagree")

    raw_project = str(api.Paths.get_project_file_path())
    full = getattr(api.Paths, "convert_relative_path_to_full", None)
    actual_project = str(full(raw_project)) if callable(full) else raw_project
    if _normal_path(actual_project) != _normal_path(plan["target_project"]):
        raise Stage3AuditError(f"Wrong Unreal project: {actual_project}")
    world = api.get_editor_subsystem(api.UnrealEditorSubsystem).get_editor_world()
    actual_level = str(world.get_path_name()).split(".")[0]
    if actual_level != plan["target_level"]:
        raise Stage3AuditError(f"Wrong Unreal level: {actual_level}")

    editor_actors = api.get_editor_subsystem(api.EditorActorSubsystem).get_all_level_actors()
    by_label: dict[str, list[Any]] = {}
    for actor in editor_actors:
        by_label.setdefault(str(actor.get_actor_label()), []).append(actor)

    class_by_kind = {
        "character": "SkeletalMeshActor", "camera": "CineCameraActor",
        "light": "PointLight", "prop": "Actor",
    }
    rows = []
    for entry in expected:
        matches = by_label.get(entry["actor_label"], [])
        class_name = (str(matches[0].get_class().get_name()) if len(matches) == 1 else None)
        kind = entry["kind"]
        class_ok = class_name == class_by_kind[kind]
        mesh_path = _mesh_asset_path(matches[0], api) if (len(matches) == 1 and kind == "character") else None
        mesh_ok = (mesh_path == entry.get("mesh_path")) if kind == "character" else None
        row = {
            "source_name": entry["source_name"],
            "actor_label": entry["actor_label"],
            "actor_count": len(matches),
            "class_name": class_name,
            "class_matches": class_ok,
            "mesh_path": mesh_path,
            "mesh_matches": mesh_ok,
            "actor_path": _object_path(matches[0]) if len(matches) == 1 else None,
            "readback_ready": len(matches) == 1 and class_ok and (mesh_ok is True if kind == "character" else True),
        }
        rows.append(row)

    mapping_path = Path(receipt["mapping_path"])
    mapping_exists = mapping_path.is_file()
    mapping_matches = mapping_exists and _read(mapping_path) == plan["mapping"]
    passed = all(row["readback_ready"] for row in rows) and mapping_matches
    result = {
        "kind": "cutsceneai.studio.stage3_scene_persistence_audit",
        "schema_version": "0.1.0",
        "status": "STAGE3_SAVED_ACTORS_READBACK" if passed else "STAGE3_READBACK_INCOMPLETE",
        "project": actual_project,
        "level": actual_level,
        "receipt_path": str(Path(receipt_path).resolve()),
        "mapping_exists": mapping_exists,
        "mapping_matches_plan": mapping_matches,
        "readback_count": sum(bool(x["readback_ready"]) for x in rows),
        "expected_count": len(rows),
        "rows": rows,
        "source_target_fidelity_verified": False,
        "sequence_generated": False,
    }
    report_path = Path(receipt_path).with_name(
        "stage3_persistence_audit_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json"
    )
    with report_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    api.log("[CutSceneAI] STAGE 3 READBACK: " + result["status"])
    api.log(f"[CutSceneAI] ACTORS: {result['readback_count']}/{result['expected_count']}")
    api.log(f"[CutSceneAI] MAPPING: {mapping_matches}")
    api.log("[CutSceneAI] REPORT: " + str(report_path))
    api.log("[CutSceneAI] NOT A CUTSCENE FIDELITY PASS")
    return result
