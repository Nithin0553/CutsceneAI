"""Reconcile a real Unity Editor component census with an extracted cutscene.

The CED cannot account for components that the source extractor never saw.
This gate detects installed/scene native features and preserves them as
explicit evidence gaps rather than declaring a complete cutscene transfer.

It is read-only, source-identity scoped, and makes zero target parity claims.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class SourceSurfaceGapError(ValueError):
    pass


# These are only component classes whose source properties have *some*
# existing dedicated CSIR representation. Their full behavior is NOT proven.
KNOWN_SOURCE_COMPONENTS = frozenset({
    "UnityEngine.Transform",
    "UnityEngine.Camera",
    "UnityEngine.Light",
    "UnityEngine.Animator",
    "UnityEngine.AudioSource",
    "UnityEngine.MeshFilter",
    "UnityEngine.MeshRenderer",
    "UnityEngine.SkinnedMeshRenderer",
    "UnityEngine.Playables.PlayableDirector",
})


def audit(csir: Mapping[str, Any], source_surface: Mapping[str, Any]) -> dict[str, Any]:
    if csir.get("source", {}).get("engine") != "unity":
        raise SourceSurfaceGapError("Expected a Unity source CSIR.")
    if source_surface.get("kind") != "cutsceneai.engine.feature_surface":
        raise SourceSurfaceGapError("Expected a captured engine feature surface.")
    if source_surface.get("engine") != "unity":
        raise SourceSurfaceGapError("Cannot compare a non-Unity feature surface.")
    if source_surface.get("schema_version") != "0.2.0":
        raise SourceSurfaceGapError("Unsupported source feature census version.")
    source_id = str((csir.get("source") or {}).get("project_fingerprint") or "")
    surface_id = str(source_surface.get("project_fingerprint") or "")
    if source_id and surface_id and source_id != surface_id:
        raise SourceSurfaceGapError(
            "Unity feature census is from a different source project fingerprint."
        )
    source_version = str((csir.get("source") or {}).get("engine_version") or "")
    surface_version = str(source_surface.get("engine_version") or "")
    if source_version and surface_version and source_version != surface_version:
        raise SourceSurfaceGapError("Unity feature census engine version differs from CSIR.")
    scene_objects = {}
    scoped_scenes = set()
    for entity in csir.get("entities", []):
        metadata = entity.get("metadata") or {}
        scene = str(metadata.get("scene_path") or "")
        hierarchy = str(metadata.get("hierarchy_path") or "")
        if scene and hierarchy:
            scoped_scenes.add(scene)
            key = (scene, hierarchy)
            if key in scene_objects:
                scene_objects[key]["duplicate"] = True
            else:
                scene_objects[key] = {
                    "entity_id": str(entity.get("entity_id") or ""),
                    "native_ref": str(entity.get("native_ref") or ""),
                    "duplicate": False,
                }
    cases = []
    seen = set()
    matched_objects = set()
    totals = Counter()
    for row in source_surface.get("loaded_scene_components", []):
        if not isinstance(row, dict):
            continue
        scene = str(row.get("scene_path") or "")
        hierarchy = str(row.get("object_path") or "")
        native_type = str(row.get("component_type") or "UNKNOWN_COMPONENT")
        global_id = str(row.get("component_global_id") or "")
        if scene not in scoped_scenes:
            totals["OTHER_LOADED_SCENE_COMPONENT"] += 1
            continue
        source_entity = scene_objects.get((scene, hierarchy))
        is_member = source_entity is not None
        affects_source = is_member or any(
            hierarchy.startswith(parent + "/")
            for included_scene, parent in scene_objects
            if included_scene == scene
        )
        if not affects_source:
            totals["UNRELATED_SCENE_COMPONENT"] += 1
            continue
        observed_id = str(row.get("global_object_id") or "")
        if is_member and source_entity["duplicate"]:
            state = "DUPLICATE_SOURCE_ENTITY_PATH"
        elif is_member and source_entity["native_ref"] and observed_id != source_entity["native_ref"]:
            state = ("SOURCE_OBJECT_IDENTITY_MISMATCH" if observed_id
                     else "SOURCE_OBJECT_IDENTITY_UNVERIFIED")
        elif is_member and native_type == "UnityEngine.Transform":
            state = "SOURCE_OBJECT_TRANSFORM_IDENTIFIED"
        elif native_type in KNOWN_SOURCE_COMPONENTS:
            state = "SOURCE_COMPONENT_SEMANTIC_REQUIRES_TARGET_EVIDENCE"
        elif row.get("missing_script") is True:
            state = "MISSING_SOURCE_SCRIPT"
        else:
            state = "NATIVE_COMPONENT_EXTRACTION_OR_ADAPTER_REQUIRED"
        # Duplicate component records on the same object are not dropped;
        # a component's global ID is the identity when supplied.
        key = (scene, hierarchy, native_type, global_id)
        if key in seen:
            state = "DUPLICATE_SOURCE_COMPONENT_IDENTITY"
        seen.add(key)
        if is_member and state not in {
            "DUPLICATE_SOURCE_ENTITY_PATH", "SOURCE_OBJECT_IDENTITY_MISMATCH",
            "SOURCE_OBJECT_IDENTITY_UNVERIFIED", "DUPLICATE_SOURCE_COMPONENT_IDENTITY",
        }:
            matched_objects.add((scene, hierarchy))
        totals[state] += 1
        cases.append({
            "scene_path": scene,
            "hierarchy_path": hierarchy,
            "source_entity_id": source_entity["entity_id"] if is_member else None,
            "native_component": native_type,
            "source_component_id": global_id,
            "state": state,
            "target_native_verified": False,
            "behavior_verified": False,
        })
    referenced_paths = {
        str((asset.get("metadata") or {}).get("asset_path") or "")
        for asset in csir.get("assets", [])
    }
    extra_asset_types = Counter()
    source_asset_count = 0
    for row in source_surface.get("imported_assets", []):
        if not isinstance(row, dict):
            continue
        path = str(row.get("asset_path") or "")
        if path in referenced_paths:
            source_asset_count += 1
        else:
            extra_asset_types[str(row.get("native_type") or "UNKNOWN_NATIVE_ASSET")] += 1
    unresolved = sum(count for state, count in totals.items()
                     if state in {
                         "NATIVE_COMPONENT_EXTRACTION_OR_ADAPTER_REQUIRED",
                         "MISSING_SOURCE_SCRIPT",
                         "DUPLICATE_SOURCE_COMPONENT_IDENTITY",
                         "DUPLICATE_SOURCE_ENTITY_PATH",
                         "SOURCE_OBJECT_IDENTITY_MISMATCH",
                         "SOURCE_OBJECT_IDENTITY_UNVERIFIED",
                     })
    # No matching objects means the census cannot prove it inspected the
    # requested cutscene. Treat as incomplete evidence in strict mode.
    scope_matched = bool(matched_objects)
    if not scope_matched:
        unresolved += 1
        totals["SOURCE_SCOPE_NOT_VERIFIED"] += 1
    return {
        "kind": "cutsceneai.studio.source_feature_gap",
        "schema_version": "0.2.0",
        "cutscene_id": str(csir.get("cutscene_id") or ""),
        "source_engine_version": str(source_surface.get("engine_version") or ""),
        "source_project_fingerprint": source_id,
        "surface_project_fingerprint": surface_id,
        "project_identity_proven": bool(source_id and surface_id and source_id == surface_id),
        "loaded_scene_scope": sorted(scoped_scenes),
        "source_scope_matched": scope_matched,
        "indexed_cutscene_entities": len(scene_objects),
        "scoped_component_occurrences": len(cases),
        "component_findings": cases,
        "component_counts": dict(sorted(totals.items())),
        "source_assets_matched_by_path": source_asset_count,
        "other_project_asset_type_counts": dict(sorted(extra_asset_types.items())),
        "registered_native_type_count": len(source_surface.get("registered_types", [])),
        "unresolved_component_count": unresolved,
        "cutscene_completeness_verified": False,
        "parity_verified": False,
        "limitations": [
            "Only loaded Unity scenes and currently loaded assemblies are indexed.",
            "Unreferenced project assets are not automatically cutscene dependencies.",
            "Known CED component types still require native target readback and behavior comparison.",
            "A script on another GameObject can still drive a source object at runtime.",
        ],
    }


def audit_files(csir: str | Path, surface: str | Path) -> dict[str, Any]:
    first = Path(csir)
    second = Path(surface)
    csir_data = json.loads(first.read_text(encoding="utf-8-sig"))
    surface_data = json.loads(second.read_text(encoding="utf-8-sig"))
    result = audit(csir_data, surface_data)
    result["source_csir_sha256"] = hashlib.sha256(first.read_bytes()).hexdigest()
    result["source_surface_sha256"] = hashlib.sha256(second.read_bytes()).hexdigest()
    return result
