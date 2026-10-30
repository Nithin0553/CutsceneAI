"""Opt-in Unreal WAV import stage with full preflight and immutable outcomes.

Run inside the *correct target Unreal Editor*, after producing asset manifest
with tools/studio_assets.py. No scene/Level Sequence is generated here.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for folder in (ROOT / "packages" / "studio",):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import asset_staging


class UnrealImportError(RuntimeError):
    """No rights, provenance failure, target conflict, or native import failure."""


def _project_matches(actual: str, expected: str) -> bool:
    return (os.path.normcase(os.path.normpath(os.path.abspath(actual)))
            == os.path.normcase(os.path.normpath(os.path.abspath(expected))))


def _asset_class(value: Any) -> str:
    return str(value.get_class().get_name()) if value is not None else ""


def _preflight(
    api: Any, manifest: dict[str, Any], mapping: dict[str, Any],
    *, expected_project_path: str,
) -> list[dict[str, Any]]:
    """All collisions, mappings, dependencies and native APIs checked before import."""
    project = str(api.Paths.get_project_file_path())
    if not expected_project_path or not _project_matches(project, expected_project_path):
        raise UnrealImportError("Wrong target Unreal project; no imports attempted.")
    folder = manifest["target_folder"]
    if api.EditorAssetLibrary.does_directory_exist(folder):
        raise UnrealImportError("Target staging directory already exists; choose a fresh namespace.")
    available = getattr(api, "AssetImportTask", None)
    toolset = getattr(api, "AssetToolsHelpers", None)
    if available is None or toolset is None:
        raise UnrealImportError("Unreal AssetImportTask/AssetToolsHelpers unavailable.")

    by_id = {row["asset_id"]: row for row in manifest["assets"]}
    importable = []
    for row in manifest["assets"]:
        status, target = row["status"], row.get("target_asset_path")
        if status == "EXISTING_MAPPING_UNVERIFIED":
            asset = api.load_asset(str(target))
            if asset is None:
                raise UnrealImportError(f"Existing target mapping missing: {target}")
            if row.get("expected_target_class") and _asset_class(asset) != row["expected_target_class"]:
                raise UnrealImportError(f"Incompatible existing asset class: {target}")
        elif status == "READY_WAV_IMPORT":
            if not target or api.EditorAssetLibrary.does_asset_exist(str(target)):
                raise UnrealImportError(f"Target asset already exists: {target}")
            if not row.get("source_file") or not row.get("source_sha256"):
                raise UnrealImportError("Import source lacks trustworthy provenance.")
            for dep in row["dependency_asset_ids"]:
                linked = by_id.get(dep)
                if linked is None or linked["status"] not in {
                    "READY_WAV_IMPORT", "EXISTING_MAPPING_UNVERIFIED"
                }:
                    raise UnrealImportError(f"Required dependency not transferable: {dep}")
            importable.append(row)
    if len({row["target_asset_path"] for row in importable}) != len(importable):
        raise UnrealImportError("Two source assets map to the same destination.")
    if len({row["name"] for row in importable}) != len(importable):
        raise UnrealImportError("Duplicate Unity names cannot produce safe name-keyed mappings.")
    for row in importable:
        if row["name"] in mapping.get("assets", {}):
            raise UnrealImportError("Refusing to override a curated target asset mapping.")
    return importable


def run(
    manifest_path: str | Path,
    csir_path: str | Path,
    mapping_path: str | Path,
    *,
    expected_project_path: str,
    resolved_mapping_path: str | Path,
    runtime_receipt_path: str | Path,
    rights_confirmed: bool = False,
    unreal_api: Any = None,
) -> dict[str, Any]:
    """Import only supported WAVs, then emit new mapping for ordinary Studio planning.

    Failure leaves any already-created Unreal packages in place for operator
    inspection; never force-delete live UObjects or claim a rollback.
    """
    if unreal_api is None:
        import unreal as unreal_api

    receipt_path = Path(runtime_receipt_path)
    mapping_output = Path(resolved_mapping_path)
    if (receipt_path.exists() or receipt_path.is_symlink() or not receipt_path.parent.is_dir()
        or mapping_output.exists() or mapping_output.is_symlink()
        or not mapping_output.parent.is_dir()):
        raise UnrealImportError("Use new receipt/mapping filenames in existing output folders.")
    receipt: dict[str, Any] = {
        "kind": "cutsceneai.unreal.asset_import_receipt", "schema_version": "0.1.0",
        "status": "BLOCKED", "stage": "preflight", "source_assets_modified": False,
        "target_assets_modified": False, "imported": [], "blocked": [],
        "behavioral_fidelity_verified": False,
    }
    mutation_started = False
    try:
        if rights_confirmed is not True:
            raise UnrealImportError("Import requires explicit rights_confirmed=True.")
        manifest = asset_staging.read_json(manifest_path)
        if manifest.get("kind") != "cutsceneai.studio.asset_import_manifest":
            raise UnrealImportError("Wrong manifest type.")
        asset_staging.verify_files(manifest, csir_path, mapping_path)
        original_mapping = asset_staging.read_json(mapping_path)
        ready = _preflight(
            unreal_api, manifest, original_mapping, expected_project_path=expected_project_path,
        )
        receipt["stage"] = "unreal_asset_import"
        receipt["target_project"] = expected_project_path
        receipt["manifest_sha256"] = asset_staging.digest(Path(manifest_path))
        receipt["source_csir_sha256"] = manifest["source_csir_sha256"]
        receipt["blocked"] = [{
            "asset_id": row["asset_id"], "status": row["status"],
            "reason": row.get("reason", ""),
        } for row in manifest["assets"] if row["status"] not in {
            "READY_WAV_IMPORT", "EXISTING_MAPPING_UNVERIFIED"
        }]
        resolved = json.loads(json.dumps(original_mapping))
        resolved.setdefault("assets", {})
        for row in ready:
            # Recheck source integrity immediately before the engine touches it.
            source = Path(row["source_file"])
            if asset_staging.digest(source) != row["source_sha256"]:
                raise UnrealImportError("Source content changed after preflight.")
            target_path = str(row["target_asset_path"])
            folder, name = target_path.rsplit("/", 1)
            if unreal_api.EditorAssetLibrary.does_asset_exist(target_path):
                raise UnrealImportError(f"Import destination collision: {target_path}")
            task = unreal_api.AssetImportTask()
            for key, value in {
                "filename": str(source), "destination_path": folder,
                "destination_name": name, "automated": True, "save": True,
                "replace_existing": False, "replace_existing_settings": False,
            }.items():
                task.set_editor_property(key, value)
            mutation_started = True
            unreal_api.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
            asset = unreal_api.load_asset(target_path)
            if asset is None or _asset_class(asset) != "SoundWave":
                raise UnrealImportError(
                    f"Native import did not produce expected SoundWave: {target_path}"
                )
            # No claims of audio waveform parity: this verifies only object type and provenance.
            receipt["imported"].append({
                "asset_id": row["asset_id"], "source_sha256": row["source_sha256"],
                "target_asset_path": target_path, "target_class": "SoundWave",
                "status": "IMPORTED_NATIVE_UNVERIFIED",
            })
            resolved["assets"][row["name"]] = target_path
        with mapping_output.open("x", encoding="utf-8") as handle:
            json.dump(resolved, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
        receipt["status"] = "IMPORTED_PARTIAL" if receipt["blocked"] else "IMPORTED_UNVERIFIED"
        receipt["stage"] = "complete"
        receipt["target_assets_modified"] = mutation_started
        receipt["resolved_mapping_sha256"] = asset_staging.digest(mapping_output)
        return receipt
    except Exception as exc:
        receipt["target_assets_modified"] = "POSSIBLE_MUST_INSPECT" if mutation_started else False
        receipt["error"] = {"type": type(exc).__name__, "message": str(exc),
                            "traceback": traceback.format_exc()}
        raise
    finally:
        with receipt_path.open("x", encoding="utf-8") as handle:
            json.dump(receipt, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
