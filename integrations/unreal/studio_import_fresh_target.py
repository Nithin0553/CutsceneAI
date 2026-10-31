"""Guarded, opt-in native Unreal import of fresh target character FBX and PNG.

No actor spawning, map saving, animation retargeting, or claims of cutscene parity.
Run from the target Unreal Editor's Python console only after a dry-run plan.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TOOL_DIR = ROOT / "tools"
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))
import studio_fresh_target_assets as fresh


class FreshTargetImportError(RuntimeError):
    pass


def _normal_path(value: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(value)))


def _project_path(api: Any) -> str:
    result = str(api.Paths.get_project_file_path())
    convert = getattr(api.Paths, "convert_relative_path_to_full", None)
    if callable(convert):
        result = str(convert(result))
    return _normal_path(result)


def _scene_path(api: Any) -> str:
    world = api.get_editor_subsystem(api.UnrealEditorSubsystem).get_editor_world()
    return str(world.get_path_name()).split(".")[0]


def _class_name(asset: Any) -> str:
    return str(asset.get_class().get_name()) if asset is not None else ""


def _task(api: Any, row: dict) -> Any:
    task = api.AssetImportTask()
    target = str(row["target_asset_path"])
    task.set_editor_property("filename", str(row["source_file"]))
    task.set_editor_property("destination_path", target.rsplit("/", 1)[0])
    task.set_editor_property("destination_name", target.rsplit("/", 1)[-1])
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", False)
    task.set_editor_property("save", True)
    task.set_editor_property("async_", False)
    if row["role"] == "CHARACTER_MODEL":
        options = api.FbxImportUI()
        options.set_editor_property("automated_import_should_detect_type", False)
        options.set_editor_property("mesh_type_to_import", api.FBXImportType.FBXIT_SKELETAL_MESH)
        options.set_editor_property("import_as_skeletal", True)
        options.set_editor_property("import_mesh", True)
        options.set_editor_property("import_animations", False)
        options.set_editor_property("import_materials", False)
        options.set_editor_property("import_textures", False)
        options.set_editor_property("create_physics_asset", False)
        task.set_editor_property("options", options)
    return task


def run(manifest_path: str, receipt_path: str, *,
        expected_project_path: str, expected_level_path: str,
        rights_confirmed: bool = False, unreal_api: Any = None) -> dict:
    """Import models/textures to an untouched target namespace after all checks.

    If import fails after any mutation, the receipt says MUST_INSPECT rather than
    deleting or rolling back editor state. The caller must choose a new folder
    and new receipt filename on retry.
    """
    api = unreal_api
    if api is None:
        import unreal as api
    receipt_file = Path(receipt_path).resolve()
    if receipt_file.exists() or receipt_file.is_symlink():
        raise FreshTargetImportError("Refusing to replace an existing receipt.")
    if not receipt_file.parent.is_dir():
        raise FreshTargetImportError("Receipt parent folder does not exist.")
    receipt = {
        "kind": "cutsceneai.studio.fresh_target_asset_import_receipt",
        "schema_version": "0.1.0", "stage": "source_preflight",
        "status": "BLOCKED", "engine_changes_possible": False,
        "scene_modified": False, "cutscene_generated": False,
        "skeletal_compatibility_verified": False, "fidelity_verified": False,
        "imported": [], "deferred": [],
        "manifest_path": str(Path(manifest_path).resolve()),
        "manifest_sha256": None,
    }
    mutation_started = False
    try:
        if not rights_confirmed:
            raise FreshTargetImportError("Source asset import rights must be confirmed.")
        manifest = fresh.verify(manifest_path)
        receipt["manifest_sha256"] = hashlib.sha256(
            Path(manifest_path).read_bytes()
        ).hexdigest()
        if _normal_path(expected_project_path) != _normal_path(manifest["target_project"]):
            raise FreshTargetImportError("Expected project differs from manifest.")
        if _project_path(api) != _normal_path(expected_project_path):
            raise FreshTargetImportError("Wrong Unreal project open in editor.")
        if not expected_level_path.startswith("/Game/"):
            raise FreshTargetImportError("Only saved /Game levels may be used.")
        if _scene_path(api) != expected_level_path:
            raise FreshTargetImportError("Wrong or unsaved Unreal level open in editor.")
        receipt["verified_project"] = manifest["target_project"]
        receipt["verified_level"] = expected_level_path
        folder = manifest["target_folder"]
        if api.EditorAssetLibrary.does_directory_exist(folder):
            raise FreshTargetImportError("Target import folder already exists. Use a new unique folder.")
        for required in ("AssetImportTask", "AssetToolsHelpers", "FbxImportUI", "FBXImportType"):
            if not hasattr(api, required):
                raise FreshTargetImportError("Unreal API missing: " + required)
        candidates = [x for x in manifest["files"] if x["status"] in {
            "CANDIDATE_SKELETAL_MODEL_UNVERIFIED", "CANDIDATE_TEXTURE_UNVERIFIED"}]
        models = [x for x in candidates if x["role"] == "CHARACTER_MODEL"]
        if len(models) < 1:
            raise FreshTargetImportError("No character model FBX candidates found.")
        if len({x["target_asset_path"] for x in candidates}) != len(candidates):
            raise FreshTargetImportError("Duplicate target asset paths in plan.")
        for row in candidates:
            if api.EditorAssetLibrary.does_asset_exist(row["target_asset_path"]):
                raise FreshTargetImportError("Target asset already exists: " + row["target_asset_path"])
        receipt["deferred"] = [{"source_path": x["source_path"], "status": x["status"]}
                               for x in manifest["files"] if x not in candidates]
        receipt["stage"] = "native_asset_import"
        for row in candidates:
            # A task can modify assets even when it throws. Reflect that honestly.
            task = _task(api, row)
            mutation_started = True
            api.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
            expected_class = "SkeletalMesh" if row["role"] == "CHARACTER_MODEL" else "Texture2D"
            imported_asset = api.load_asset(row["target_asset_path"])
            actual_class = _class_name(imported_asset)
            if actual_class != expected_class:
                raise FreshTargetImportError(
                    f"Import class mismatch for {row['source_path']}: expected "
                    f"{expected_class}, got {actual_class or 'MISSING'}"
                )
            receipt["imported"].append({
                "source_path": row["source_path"],
                "source_sha256": row["sha256"],
                "target_asset_path": row["target_asset_path"],
                "target_class": actual_class,
                "status": "IMPORTED_NATIVE_UNVERIFIED",
            })
        receipt["stage"] = "complete"
        receipt["status"] = "IMPORTED_ASSETS_UNVERIFIED"
        receipt["engine_changes_possible"] = True
        return receipt
    except Exception as exc:
        receipt["status"] = "FAILED_MUST_INSPECT" if mutation_started else "BLOCKED"
        receipt["engine_changes_possible"] = "POSSIBLE_MUST_INSPECT" if mutation_started else False
        receipt["error"] = {"type": type(exc).__name__, "message": str(exc),
                            "traceback": traceback.format_exc()}
        raise
    finally:
        with receipt_file.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n")
