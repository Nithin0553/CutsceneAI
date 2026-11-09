"""Adaptive Unity-source component -> Unreal native cinematic properties.

This module is an executable adapter registry, unlike the CED taxonomy.
It makes conservative source-value / target-property decisions, records exact
source IDs and uncovered fields, and requires fresh native readback.
No source scanner data is executed as code and unknown components cannot claim
successful conversion.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Mapping

import feature_dispatch

SOURCE_CAMERA = "UnityEngine.Rendering.Universal.UniversalAdditionalCameraData"
SOURCE_LIGHT = "UnityEngine.Light"
SOURCE_COLLIDERS = {
    "UnityEngine.BoxCollider", "UnityEngine.SphereCollider", "UnityEngine.MeshCollider"
}
SOURCE_LOD_GROUP = "UnityEngine.LODGroup"
SOURCE_RECEIVER = "UnityEngine.Timeline.SignalReceiver"


def _identity_map(csir: Mapping[str, Any], mapping: Mapping[str, Any]) -> dict[tuple[str, str], dict]:
    """Bind component paths to exact mapped CSIR entities, never approximate name matches."""
    index: dict[tuple[str, str], dict] = {}
    for entity in csir.get("entities", []):
        metadata = entity.get("metadata") or {}
        name = str(entity.get("name") or "")
        target = mapping.get("entities", {}).get(name)
        if not isinstance(target, dict) or not target.get("actor_label"):
            continue
        key = (str(metadata.get("scene_path") or ""), str(metadata.get("hierarchy_path") or ""))
        if key[0] and key[1]:
            if key in index:
                index[key] = {"ambiguous": True}
            else:
                index[key] = {"name": name, "entity_id": str(entity.get("entity_id")),
                              "entity_ced": str(entity.get("ced_type") or ""),
                              "actor_label": str(target["actor_label"])}
    return index


def _flags(row: Mapping[str, Any]) -> dict[str, Any]:
    value = row.get("feature")
    return value if isinstance(value, dict) else {}


def _native_bool(feature: dict[str, Any], member: str) -> bool | None:
    if feature.get("has_" + member) is not True:
        return None
    value = feature.get(member)
    return value if isinstance(value, bool) else None



_NATIVE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SOURCE_MEMBER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\[\]]*$")


def _explicit_property_rules(mapping: Mapping[str, Any]) -> list[dict[str, Any]]:
    specs = mapping.get("component_property_mappings") or []
    if not isinstance(specs, list):
        raise ValueError("component_property_mappings must be a list.")
    seen: set[tuple[str, str, str]] = set()
    result = []
    for spec in specs:
        if not isinstance(spec, dict):
            raise ValueError("Component property mapping must be a JSON object.")
        required = (
            "source_component_type", "source_entity_name", "source_property_path",
            "target_scope", "target_class", "target_property_name", "value_type",
        )
        if any(not isinstance(spec.get(key), str) or not spec[key] for key in required):
            raise ValueError("Missing required typed CED component mapping field.")
        if spec["value_type"] not in {"bool", "float"}:
            raise ValueError("Generic component property mapping only supports bool/float.")
        if spec["target_scope"] not in {"actor", "component"}:
            raise ValueError("Invalid native Unreal component property target scope.")
        if not _SOURCE_MEMBER.fullmatch(spec["source_property_path"]):
            raise ValueError("Invalid source serialized component property path.")
        if not all(_NATIVE_IDENTIFIER.fullmatch(spec[key]) for key in (
            "target_class", "target_property_name"
        )):
            raise ValueError("Invalid target Unreal native class/property identifier.")
        token = (spec["source_entity_name"], spec["target_class"],
                 spec["target_property_name"])
        if token in seen:
            raise ValueError("Duplicate target component property mapping.")
        seen.add(token)
        scale = float(spec.get("value_scale", 1.0))
        offset = float(spec.get("value_offset", 0.0))
        if not math.isfinite(scale) or not math.isfinite(offset) or scale == 0:
            raise ValueError("Invalid scale/offset for native component mapping.")
        if spec["value_type"] == "bool" and (scale != 1 or offset != 0):
            raise ValueError("Boolean property values cannot be scaled.")
        result.append(spec)
    return result


def _explicit_actions(
    row: Mapping[str, Any], target: Mapping[str, Any], feature: Mapping[str, Any],
    rules: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    actions: list[dict[str, Any]] = []
    not_found: list[str] = []
    for rule in rules:
        if (rule["source_component_type"] != row.get("component_type") or
                rule["source_entity_name"] != target["name"]):
            continue
        matches = [
            x for x in feature.get("native_properties", [])
            if isinstance(x, dict) and x.get("path") == rule["source_property_path"]
            and x.get("native_type") == rule["value_type"]
        ]
        if len(matches) != 1:
            not_found.append(rule["source_property_path"])
            continue
        property_value = matches[0]
        if rule["value_type"] == "bool":
            value = property_value.get("bool_value")
            if not isinstance(value, bool):
                not_found.append(rule["source_property_path"])
                continue
        else:
            try:
                original = float(property_value["float_value"])
                value = original * float(rule.get("value_scale", 1)) + float(
                    rule.get("value_offset", 0))
            except (TypeError, ValueError, KeyError):
                not_found.append(rule["source_property_path"])
                continue
            if not math.isfinite(value):
                not_found.append(rule["source_property_path"])
                continue
        actions.append({
            "kind": "property_bool" if rule["value_type"] == "bool" else "property_float",
            "entity_name": target["name"],
            "actor_label": target["actor_label"],
            "track_name": "CutSceneAI Native Component: " + rule["source_property_path"],
            "target_scope": rule["target_scope"],
            "target_class": rule["target_class"],
            "target_property_name": rule["target_property_name"],
            "target_property_path": rule["target_property_name"],
            "source_semantic": str(rule.get("source_semantic") or "metadata.property_descriptor"),
            "source_component_type": str(row["component_type"]),
            "source_component_id": str(row.get("component_global_id") or ""),
            "source_property_path": rule["source_property_path"],
            "source_behavior_strategy": "explicit_ced_scalar_component_property",
            "keys": [{"frame": 0, "value": value}],
            "fidelity_status": "NATIVE_READBACK_AND_SEMANTIC_PARITY_UNVERIFIED",
            "semantic_losses": [
                "Matching native property values does not establish equivalent "
                "shader, plugin or runtime behavior."
            ],
        })
    return actions, not_found


def adapt(
    csir: Mapping[str, Any],
    mapping: Mapping[str, Any],
    census: Mapping[str, Any],
) -> dict[str, Any]:
    """Return source-attributed property actions and inspectable remaining gaps.

    Exact native properties:
      Unity URP renderPostProcessing -> Unreal CineCameraComponent
      post_process_blend_weight (effect-enable approximation only)
      Unity Light.shadows -> Unreal LightComponent.cast_shadows

    Full URP color grading/antialiasing, light cookies, SignalReceiver calls,
    and collider runtime geometry are NOT silently equated.
    """
    known = _identity_map(csir, mapping)
    rules = _explicit_property_rules(mapping)
    ced = feature_dispatch.catalog()
    actions: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    reserved: set[tuple[str, str]] = set()
    expected = 0
    for idx, row in enumerate(census.get("loaded_scene_components", [])):
        if not isinstance(row, dict):
            continue
        native_type = str(row.get("component_type") or "")
        if native_type not in {SOURCE_CAMERA, SOURCE_LIGHT, SOURCE_RECEIVER, SOURCE_LOD_GROUP,
                               *SOURCE_COLLIDERS,
                               "UnityEngine.Rendering.Universal.UniversalAdditionalLightData"} and not any(
                                   r["source_component_type"] == native_type for r in
                                   mapping.get("component_property_mappings", [])
                                   if isinstance(r, dict)
                               ):
            continue
        scene = str(row.get("scene_path") or "")
        path = str(row.get("object_path") or "")
        feature = _flags(row)
        target = known.get((scene, path))
        desc = {
            "source_location": f"loaded_scene_components[{idx}]",
            "source_component_id": str(row.get("component_global_id") or ""),
            "source_native_type": native_type,
            "source_object_path": path,
            "target_actor": target.get("actor_label") if target else None,
            "status": "SOURCE_COMPONENT_ADAPTER_MISSING",
            "actions": [],
            "unconverted_properties": [],
        }
        expected += 1
        if target is None or target.get("ambiguous"):
            desc["status"] = "EXACT_TARGET_OBJECT_MAPPING_REQUIRED"
            decisions.append(desc)
            continue
        custom_actions, unresolved_paths = _explicit_actions(row, target, feature, rules)
        for new_action in custom_actions:
            token = (target["actor_label"], new_action["target_property_path"])
            if token in reserved:
                desc["status"] = "DUPLICATE_TARGET_COMPONENT_PROPERTY"
                continue
            reserved.add(token)
            actions.append(new_action)
            desc["actions"].append(new_action["kind"])
            desc["status"] = "NATIVE_PROPERTY_PLANNED_PARTIAL_UNVERIFIED"
        if unresolved_paths:
            desc["unconverted_properties"].extend(unresolved_paths)
            desc["status"] = "SOURCE_NATIVE_PROPERTY_NOT_CAPTURED"
        if native_type == SOURCE_CAMERA:
            if target.get("entity_ced") != "entity.camera":
                desc["status"] = "SOURCE_CAMERA_MAPPED_TO_NONCAMERA_ACTOR"
                decisions.append(desc)
                continue
            post = _native_bool(feature, "render_post_processing")
            if post is not None:
                token = (target["actor_label"], "post_process_blend_weight")
                if token in reserved:
                    desc["status"] = "DUPLICATE_TARGET_COMPONENT_PROPERTY"
                else:
                    reserved.add(token)
                    action = {
                        "kind": "property_float",
                        "entity_name": target["name"],
                        "actor_label": target["actor_label"],
                        "track_name": "CutSceneAI URP Camera Post Process Enable",
                        "target_scope": "component",
                        "target_class": "CineCameraComponent",
                        "target_property_name": "post_process_blend_weight",
                        "target_property_path": "post_process_blend_weight",
                        "source_semantic": "camera.postprocess",
                        "source_component_type": native_type,
                        "source_component_id": desc["source_component_id"],
                        "source_behavior_strategy": "ced_exact_property_value_partial_renderer_equivalence",
                        "keys": [{"frame": 0, "value": 1.0 if post else 0.0}],
                        "fidelity_status": "NATIVE_PROPERTY_READBACK_AND_RENDER_PARITY_UNVERIFIED",
                        "semantic_losses": [
                            "Unity URP postprocessing volumes, renderer features and AA are not reconstructed.",
                            "Unreal post-process override settings may differ even when blend weight matches.",
                        ],
                    }
                    actions.append(action)
                    desc["actions"].append("property_float")
                    desc["status"] = "NATIVE_PROPERTY_PLANNED_PARTIAL_UNVERIFIED"
            else:
                desc["status"] = "SOURCE_PROPERTY_EVIDENCE_REQUIRED"
            desc["unconverted_properties"].extend([
                "render_shadows", "camera_stacking", "render_type",
                "antialiasing", "requires_depth_texture", "requires_color_texture",
            ])
        elif native_type == SOURCE_LIGHT:
            if target.get("entity_ced") != "entity.light":
                desc["status"] = "SOURCE_LIGHT_MAPPED_TO_NONLIGHT_ACTOR"
                decisions.append(desc)
                continue
            shadows = _native_bool(feature, "cast_shadows")
            if shadows is not None:
                token = (target["actor_label"], "cast_shadows")
                if token in reserved:
                    desc["status"] = "DUPLICATE_TARGET_COMPONENT_PROPERTY"
                else:
                    reserved.add(token)
                    action = {
                        "kind": "property_bool",
                        "entity_name": target["name"],
                        "actor_label": target["actor_label"],
                        "track_name": "CutSceneAI Unity Light Shadow Enable",
                        "target_scope": "component",
                        "target_class": "LightComponent",
                        "target_property_name": "cast_shadows",
                        "target_property_path": "cast_shadows",
                        "source_semantic": "light.shadow",
                        "source_component_type": native_type,
                        "source_component_id": desc["source_component_id"],
                        "source_behavior_strategy": "ced_light_shadow_cast_property",
                        "keys": [{"frame": 0, "value": shadows}],
                        "fidelity_status": "NATIVE_PROPERTY_READBACK_AND_RENDER_PARITY_UNVERIFIED",
                        "semantic_losses": [
                            "URP shadow filtering, cascades and pipeline settings are not equivalent to Unreal.",
                        ],
                    }
                    actions.append(action)
                    desc["actions"].append("property_bool")
                    desc["status"] = "NATIVE_PROPERTY_PLANNED_PARTIAL_UNVERIFIED"
            else:
                desc["status"] = "SOURCE_PROPERTY_EVIDENCE_REQUIRED"
            desc["unconverted_properties"].extend([
                "shadow_filter", "shadow_bias", "shadow_resolution", "rendering_layers",
            ])
        elif native_type == "UnityEngine.MeshCollider":
            desc["status"] = (
                "MESH_COLLIDER_SOURCE_CAPTURED_NATIVE_ADAPTER_REQUIRED"
                if feature.get("extraction") ==
                "MESH_COLLIDER_SOURCE_SNAPSHOT_NATIVE_UNVERIFIED"
                else "SOURCE_COLLISION_MESH_IDENTITY_REQUIRED"
            )
            desc["unconverted_properties"].extend([
                "unreal_collision_mesh", "mesh_collision_cooking",
                "convexity_and_trigger_behavior", "physical_material",
                "contact_and_overlap_events", "physics_engine_parity",
            ])
        elif native_type == SOURCE_LOD_GROUP:
            desc["status"] = (
                "LOD_GROUP_SOURCE_CAPTURED_NATIVE_ADAPTER_REQUIRED"
                if feature.get("extraction") ==
                "LOD_GROUP_SOURCE_SNAPSHOT_NATIVE_UNVERIFIED"
                else "SOURCE_LOD_RENDERER_GRAPH_REQUIRED"
            )
            desc["unconverted_properties"].extend([
                "unreal_static_mesh_lod_chain", "screen_size_thresholds",
                "cross_fade_semantics", "billboard_lods",
                "lod_material_and_renderer_binding", "rendered_lod_parity",
            ])
        elif native_type in SOURCE_COLLIDERS:
            desc["status"] = ("COLLIDER_GEOMETRY_CAPTURED_NATIVE_ADAPTER_REQUIRED"
                              if feature.get("has_geometry") is True
                              else "SOURCE_COLLIDER_GEOMETRY_REQUIRED")
            desc["unconverted_properties"].extend([
                "collision_shape_native_component", "rigidbody_constraints",
                "physics_material", "overlap_callbacks", "scene_hierarchy",
            ])
        elif native_type == SOURCE_RECEIVER:
            desc["status"] = "SIGNAL_REACTIONS_CAPTURED_TARGET_CALLBACK_ADAPTER_REQUIRED"
            desc["unconverted_properties"].extend([
                "signal_event_payload", "call_target_mapping", "event_execution_order",
            ])
        elif native_type == "UnityEngine.Rendering.Universal.UniversalAdditionalLightData":
            desc["status"] = "URP_LIGHT_OVERRIDE_TARGET_ADAPTER_REQUIRED"
            desc["unconverted_properties"].extend([
                "shadow_filter", "light_layers", "light_cookie", "render_pipeline_policy",
            ])
        elif (not desc["actions"]
              and desc["status"] == "SOURCE_COMPONENT_ADAPTER_MISSING"):
            desc["status"] = "EXPLICIT_COMPONENT_PROPERTY_UNAVAILABLE"
        decisions.append(desc)
    # The CED is now an executable dispatch constraint, not just a catalog
    # printed alongside the plan. Native handlers must declare the actual
    # source concept and be registered to a builder action kind.
    for action in actions:
        semantic = str(action["source_semantic"])
        if semantic in ced["_domain_for"]:
            recipe = feature_dispatch.recipe(semantic, features=ced)
            if action["kind"] not in recipe["potential_builder_actions"]:
                raise ValueError(
                    "CED has no registered native action for " + semantic
                    + ": " + action["kind"]
                )
            action["ced_resolution"] = "KNOWN_SEMANTIC_AND_NATIVE_HANDLER"
        else:
            # Only an explicit user-authored namespaced plugin mapping may
            # extend the fixed CED. Unknown source data never auto-executes.
            if not any(
                rule.get("source_semantic") == semantic
                for rule in rules
            ):
                raise ValueError("Unregistered CED source semantic: " + semantic)
            action["ced_resolution"] = "EXPLICIT_PLUGIN_ADAPTER_UNVERIFIED"
    if len({(a["actor_label"], a["target_property_path"]) for a in actions}) != len(actions):
        raise ValueError("Adaptive component rules produced duplicate Unreal target properties.")
    # No arbitrary per-native reflection remapping: a new CED adapter is code,
    # with a version, source parser, target object type and native test.
    if not all(
        all(math.isfinite(float(k["value"])) for k in a["keys"]
            if a["kind"] == "property_float")
        for a in actions
    ):
        raise ValueError("Adaptive component float action is not finite.")
    counts = Counter(d["status"] for d in decisions)
    return {
        "kind": "cutsceneai.studio.adaptive_component_transfer",
        "schema_version": "0.1.0",
        "source_component_candidates": expected,
        "action_count": len(actions),
        "actions": actions,
        "decisions": decisions,
        "status_counts": dict(sorted(counts.items())),
        "all_source_features_converted": False,
        "source_target_fidelity_verified": False,
        "strategy": "native_first_with_evidence_gated_partial_fallback",
    }
