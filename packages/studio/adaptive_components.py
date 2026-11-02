"""Adaptive Unity-source component -> Unreal native cinematic properties.

This module is an executable adapter registry, unlike the CED taxonomy.
It makes conservative source-value / target-property decisions, records exact
source IDs and uncovered fields, and requires fresh native readback.
No source scanner data is executed as code and unknown components cannot claim
successful conversion.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Mapping

SOURCE_CAMERA = "UnityEngine.Rendering.Universal.UniversalAdditionalCameraData"
SOURCE_LIGHT = "UnityEngine.Light"
SOURCE_COLLIDERS = {"UnityEngine.BoxCollider", "UnityEngine.SphereCollider"}
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
    actions: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    reserved: set[tuple[str, str]] = set()
    expected = 0
    for idx, row in enumerate(census.get("loaded_scene_components", [])):
        if not isinstance(row, dict):
            continue
        native_type = str(row.get("component_type") or "")
        if native_type not in {SOURCE_CAMERA, SOURCE_LIGHT, SOURCE_RECEIVER, *SOURCE_COLLIDERS,
                               "UnityEngine.Rendering.Universal.UniversalAdditionalLightData"}:
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
        if native_type == SOURCE_CAMERA:
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
                        "source_semantic": "camera.post_processing",
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
                        "source_semantic": "light.shadow_casting",
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
        else:
            desc["status"] = "URP_LIGHT_OVERRIDE_TARGET_ADAPTER_REQUIRED"
            desc["unconverted_properties"].extend([
                "shadow_filter", "light_layers", "light_cookie", "render_pipeline_policy",
            ])
        decisions.append(desc)
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
