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


# A source snapshot is not an Unreal adapter or a behavior-equivalence proof.
# These exact scanner contracts already exist in Unity's
# CutSceneAIFeatureSurfaceScanner.CaptureComponent. The old census mistakenly
# classified all seven Benchmark002 instances as unextracted.
_PARTIAL_SCANNER_CONTRACTS = {
    "UnityEngine.BoxCollider": "STATIC_COLLIDER_WORLD_SHAPE_CANDIDATE",
    "UnityEngine.SphereCollider": "STATIC_COLLIDER_WORLD_SHAPE_CANDIDATE",
    "UnityEngine.Rendering.Universal.UniversalAdditionalCameraData":
        "URP_CAMERA_PROPERTIES_PARTIAL",
    "UnityEngine.Rendering.Universal.UniversalAdditionalLightData":
        "URP_LIGHT_PROPERTIES_PARTIAL",
    "UnityEngine.Timeline.SignalReceiver":
        "SIGNAL_REACTIONS_INSPECTED_NO_TARGET_EVENT_BINDING",
}


def _finite_xyz(value: Any, names: tuple[str, ...]) -> bool:
    """Reject missing or non-finite serialized vectors (never execute data)."""
    import math

    return (
        isinstance(value, dict)
        and all(type(value.get(name)) in (int, float)
                and math.isfinite(value[name]) for name in names)
    )


def _partial_source_evidence(row: Mapping[str, Any]) -> bool:
    """Recognize only a real, typed Unity source capture.

    This allows a *source-census* gate to account for a partial authoring
    snapshot while target conversion and runtime parity stay UNVERIFIED.
    Unknown, malformed, legacy and truncated captures remain blocked.
    """
    native_type = str(row.get("component_type") or "")
    required = _PARTIAL_SCANNER_CONTRACTS.get(native_type)
    feature = row.get("feature")
    if not required or not isinstance(feature, dict):
        return False
    if feature.get("extraction") != required:
        return False
    if not str(row.get("component_global_id") or "").strip():
        return False
    # Older/partial exporter payloads may omit this field entirely;
    # only the current scanner's explicit "not truncated" evidence qualifies.
    if feature.get("native_properties_truncated") is not False:
        return False
    if native_type in {"UnityEngine.BoxCollider", "UnityEngine.SphereCollider"}:
        if not (feature.get("has_geometry") is True
                and feature.get("shape") == ("box" if native_type.endswith("BoxCollider") else "sphere")
                and type(feature.get("enabled")) is bool
                and type(feature.get("is_trigger")) is bool
                and _finite_xyz(feature.get("world_center_m"), ("x", "y", "z"))
                and _finite_xyz(feature.get("world_rotation_xyzw"), ("x", "y", "z", "w"))):
            return False
        if native_type.endswith("BoxCollider"):
            size = feature.get("world_size_m")
            return bool(_finite_xyz(size, ("x", "y", "z"))
                        and all(size[axis] > 0 for axis in ("x", "y", "z"))
                        and feature.get("collider_scale_policy") == "LOSSY_SCALE_NO_SHEAR_PROOF")
        radius = feature.get("world_radius_m")
        return bool(type(radius) in (int, float) and _finite_xyz(
            {"r": radius}, ("r",)) and radius > 0
            and feature.get("collider_scale_policy") == "UNITY_SPHERE_MAX_AXIS_LOSSY_SCALE")
    if native_type.endswith("UniversalAdditionalCameraData"):
        return bool(
            feature.get("has_render_post_processing") is True
            and type(feature.get("render_post_processing")) is bool
            or feature.get("has_render_shadows") is True
            and type(feature.get("render_shadows")) is bool
            or isinstance(feature.get("native_properties"), list)
            and bool(feature["native_properties"])
        )
    if native_type.endswith("UniversalAdditionalLightData"):
        return bool(
            feature.get("has_use_pipeline_settings") is True
            and type(feature.get("use_pipeline_settings")) is bool
            or isinstance(feature.get("native_properties"), list)
            and bool(feature["native_properties"])
        )
    if native_type == "UnityEngine.Timeline.SignalReceiver":
        reactions = feature.get("signal_reactions")
        count = feature.get("signal_reaction_count")
        return (type(count) is int and 0 <= count <= 256
                and isinstance(reactions, list) and len(reactions) == count
                and all(isinstance(item, str) and item for item in reactions))
    return False


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
    matched_transforms = set()
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
        elif is_member and native_type in {"UnityEngine.Transform", "UnityEngine.RectTransform"}:
            state = "SOURCE_OBJECT_TRANSFORM_IDENTIFIED"
        elif row.get("missing_script") is True:
            state = "MISSING_SOURCE_SCRIPT"
        elif native_type in KNOWN_SOURCE_COMPONENTS:
            state = "SOURCE_COMPONENT_SEMANTIC_REQUIRES_TARGET_EVIDENCE"
        elif _partial_source_evidence(row):
            # Source authoring state exists; target functionality is NOT
            # equivalent merely because the component has been inventoried.
            state = "SOURCE_COMPONENT_SNAPSHOT_PARTIAL_TARGET_UNVERIFIED"
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
        if is_member and state == "SOURCE_OBJECT_TRANSFORM_IDENTIFIED":
            matched_transforms.add((scene, hierarchy))
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
    partial_source = [
        row for row in cases
        if row["state"] == "SOURCE_COMPONENT_SNAPSHOT_PARTIAL_TARGET_UNVERIFIED"
    ]
    unresolved = sum(count for state, count in totals.items()
                     if state in {
                         "NATIVE_COMPONENT_EXTRACTION_OR_ADAPTER_REQUIRED",
                         "MISSING_SOURCE_SCRIPT",
                         "DUPLICATE_SOURCE_COMPONENT_IDENTITY",
                         "DUPLICATE_SOURCE_ENTITY_PATH",
                         "SOURCE_OBJECT_IDENTITY_MISMATCH",
                         "SOURCE_OBJECT_IDENTITY_UNVERIFIED",
                     })
    # One matching component cannot prove that every extracted GameObject was
    # scanned. Require a matching Transform for each source object; a Camera or
    # other component on one object cannot stand in for a missing sibling.
    missing_objects = sorted(set(scene_objects) - matched_transforms)
    missing_object_findings = [
        {"scene_path": scene, "hierarchy_path": hierarchy,
         "source_entity_id": scene_objects[(scene, hierarchy)]["entity_id"],
         "state": "SOURCE_OBJECT_TRANSFORM_NOT_VERIFIED"}
        for scene, hierarchy in missing_objects
    ]
    if missing_objects:
        totals["SOURCE_OBJECT_TRANSFORM_NOT_VERIFIED"] += len(missing_objects)
        unresolved += len(missing_objects)
    scope_matched = bool(scene_objects and matched_objects and not missing_objects)
    if not scene_objects:
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
        "verified_cutscene_objects": len(matched_transforms),
        "missing_cutscene_objects": missing_object_findings,
        "scoped_component_occurrences": len(cases),
        "component_findings": cases,
        "component_counts": dict(sorted(totals.items())),
        "source_assets_matched_by_path": source_asset_count,
        "other_project_asset_type_counts": dict(sorted(extra_asset_types.items())),
        "registered_native_type_count": len(source_surface.get("registered_types", [])),
        "unresolved_component_count": unresolved,
        "source_snapshot_partial_count": len(partial_source),
        "source_snapshot_partial_findings": partial_source,
        "cutscene_completeness_verified": False,
        "parity_verified": False,
        "limitations": [
            "Only loaded Unity scenes and currently loaded assemblies are indexed.",
            "Unreferenced project assets are not automatically cutscene dependencies.",
            "Known CED component types still require native target readback and behavior comparison.",
            "Recorded URP, collider and signal source snapshots are partial authoring evidence, not converted Unreal behavior.",
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
