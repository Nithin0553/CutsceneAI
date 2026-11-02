"""Actual source-side CED adapters must change native actions, not just reports."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for folder in ("integrations/unreal", "packages/cinetwin", "packages/studio"):
    sys.path.insert(0, str(ROOT / folder))

import adaptive_components
import transfer_backend
from test_transfer_backend import mapping, source


def _census(source_data, *, payload=True):
    camera = source_data["entities"][1]
    camera["metadata"]["scene_path"] = "Assets/Benchmark002.unity"
    camera["metadata"]["hierarchy_path"] = "Benchmark002/CAM"
    camera["metadata"]["world_transform"] = {
        "position": {"x": 0, "y": 1, "z": -5},
        "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
        "scale": {"x": 1, "y": 1, "z": 1},
    }
    return {
        "kind": "cutsceneai.engine.feature_surface", "schema_version": "0.2.0",
        "engine": "unity", "engine_version": "6000.1",
        "project_fingerprint": "proj-any",
        "registered_types": [],
        "loaded_scene_components": [{
            "scene_path": "Assets/Benchmark002.unity",
            "object_path": "Benchmark002/CAM",
            "component_type": "UnityEngine.Rendering.Universal.UniversalAdditionalCameraData",
            "component_global_id": "camera-data-guid",
            "feature": ({
                "extraction": "URP_CAMERA_PROPERTIES_PARTIAL",
                "has_render_post_processing": True,
                "render_post_processing": False,
            } if payload else {}),
        }],
        "imported_assets": [],
    }


def test_camera_census_now_produces_real_editable_native_float_action():
    csir, mapped = source(), mapping()
    captured = _census(csir)
    frozen = copy.deepcopy(csir)
    result = adaptive_components.adapt(csir, mapped, captured)
    assert result["action_count"] == 1
    action = result["actions"][0]
    assert action["kind"] == "property_float"
    assert action["target_class"] == "CineCameraComponent"
    assert action["target_property_name"] == "post_process_blend_weight"
    assert action["keys"] == [{"frame": 0, "value": 0.0}]
    assert action["source_component_id"] == "camera-data-guid"
    assert action["semantic_losses"]
    assert result["all_source_features_converted"] is False
    assert csir == frozen


def test_one_unextracted_legacy_urp_component_cannot_claim_conversion():
    csir, mapped = source(), mapping()
    data = adaptive_components.adapt(csir, mapped, _census(csir, payload=False))
    assert data["action_count"] == 0
    assert data["decisions"][0]["status"] == "SOURCE_PROPERTY_EVIDENCE_REQUIRED"


def test_wrong_actor_kind_and_name_guess_do_not_bind_camera():
    csir, mapped = source(), mapping()
    data = _census(csir)
    csir["entities"][1]["ced_type"] = "entity.prop"
    first = adaptive_components.adapt(csir, mapped, data)
    assert first["action_count"] == 0
    assert first["decisions"][0]["status"] == "SOURCE_CAMERA_MAPPED_TO_NONCAMERA_ACTOR"
    csir["entities"][1]["ced_type"] = "entity.camera"
    data["loaded_scene_components"][0]["object_path"] += "-Similar"
    second = adaptive_components.adapt(csir, mapped, data)
    assert second["action_count"] == 0
    assert second["decisions"][0]["status"] == "EXACT_TARGET_OBJECT_MAPPING_REQUIRED"


def test_native_unity_light_shadows_use_bool_property_with_actor_identity():
    csir, mapped = source(), mapping()
    csir["entities"].append({
        "entity_id": "light-one", "name": "LIGHT_KEY",
        "ced_type": "entity.light",
        "metadata": {
            "scene_path": "Assets/Benchmark002.unity",
            "hierarchy_path": "Benchmark002/LIGHT_KEY",
        },
    })
    mapped["entities"]["LIGHT_KEY"] = {"actor_label": "LightUE"}
    census = _census(csir)
    census["loaded_scene_components"].append({
        "scene_path": "Assets/Benchmark002.unity",
        "object_path": "Benchmark002/LIGHT_KEY",
        "component_type": "UnityEngine.Light",
        "component_global_id": "light-guid",
        "feature": {"extraction": "UNITY_LIGHT_NATIVE_PROPERTIES_PARTIAL",
                    "has_cast_shadows": True, "cast_shadows": False},
    })
    result = adaptive_components.adapt(csir, mapped, census)
    assert result["action_count"] == 2
    action = next(a for a in result["actions"] if a["kind"] == "property_bool")
    assert action["keys"] == [{"frame": 0, "value": False}]
    assert action["target_class"] == "LightComponent"
    assert action["target_property_name"] == "cast_shadows"
    assert action["source_component_id"] == "light-guid"


def test_colliders_and_signal_callbacks_remain_explicit_when_no_native_handler():
    csir, mapped = source(), mapping()
    data = _census(csir)
    for cls, shape in [
        ("UnityEngine.BoxCollider", "box"),
        ("UnityEngine.SphereCollider", "sphere"),
        ("UnityEngine.Timeline.SignalReceiver", ""),
    ]:
        data["loaded_scene_components"].append({
            "scene_path": "Assets/Benchmark002.unity",
            "object_path": "Benchmark002/CAM",
            "component_type": cls, "component_global_id": cls,
            "feature": {"has_geometry": bool(shape), "shape": shape,
                        "signal_reaction_count": 3},
        })
    result = adaptive_components.adapt(csir, mapped, data)
    assert result["action_count"] == 1
    states = [x["status"] for x in result["decisions"]]
    assert states.count("COLLIDER_GEOMETRY_CAPTURED_NATIVE_ADAPTER_REQUIRED") == 2
    assert "SIGNAL_REACTIONS_CAPTURED_TARGET_CALLBACK_ADAPTER_REQUIRED" in states


def test_full_compose_files_uses_source_census_to_change_native_sequence_plan(tmp_path):
    csir, mapped = source(), mapping()
    census = _census(csir)
    census["loaded_scene_components"].append({
        "scene_path": "Assets/Benchmark002.unity",
        "object_path": "Benchmark002/CAM", "component_type": "UnityEngine.Camera",
        "component_global_id": "builtin-camera",
    })
    mapped["source_feature_surface_path"] = str(tmp_path / "surface.json")
    mapped["require_complete_source_features"] = False
    cp, mp, sp = (tmp_path / "source.json", tmp_path / "mapping.json",
                  tmp_path / "surface.json")
    cp.write_text(json.dumps(csir))
    mp.write_text(json.dumps(mapped))
    sp.write_text(json.dumps(census))
    baseline, baseline_report = transfer_backend.compose(csir, mapped)
    plan, report, evidence = transfer_backend.compose_files(cp, mp)
    assert len(plan["actions"]) == len(baseline["actions"]) + 1
    assert report["actions"]["property_float"] == 1
    assert report["adaptive_components"]["action_count"] == 1
    assert report["no_full_fidelity_claim"] is True
    assert report["source_feature_surface_state"] == "SOURCE_CENSUS_PARTIAL_EXPLICIT_REVIEW_REQUIRED"
    assert report["feature_dispatch"]["full_conversion_verified"] is False
    assert len(evidence["source_feature_surface_sha256"]) == 64
    assert "property_float" not in baseline_report["actions"]


def test_native_builder_has_bool_track_and_source_type_checks():
    body = (ROOT / "integrations" / "unreal" / "build_level_sequence.py").read_text()
    assert 'elif kind == "property_bool":' in body
    assert "unreal.MovieSceneBoolTrack" in body
    assert 'if action.get("kind") == "property_bool"' in body
    assert "not isinstance(existing, bool)" in body
    assert 'channels[0].add_key(' in body


def test_scanner_captures_source_values_and_native_callback_metadata():
    script = (ROOT / "integrations" / "unity"
              / "com.cutsceneai.extractor" / "Editor"
              / "CutSceneAIFeatureSurfaceScanner.cs").read_text()
    for fragment in (
        'TryBoolProperty(component, "renderPostProcessing"',
        "feature.has_cast_shadows = true",
        "feature.world_size_m = new Vec3(size)",
        "feature.world_radius_m = sphere.radius",
        "receiver.GetRegisteredSignals()",
        "reaction.GetPersistentMethodName(k)",
    ):
        assert fragment in script


def test_duplicate_census_component_cannot_inflate_native_action_counts():
    csir, mapped = source(), mapping()
    data = _census(csir)
    data["loaded_scene_components"].append(copy.deepcopy(data["loaded_scene_components"][0]))
    result = adaptive_components.adapt(csir, mapped, data)
    assert result["action_count"] == 1
    assert result["status_counts"]["DUPLICATE_TARGET_COMPONENT_PROPERTY"] == 1


def test_generic_custom_plugin_property_creates_verified_type_matched_native_action():
    csir, target = source(), mapping()
    census = _census(csir)
    census["loaded_scene_components"].append({
        "scene_path": "Assets/Benchmark002.unity",
        "object_path": "Benchmark002/CAM",
        "component_type": "MyCompany.CinematicGlow",
        "component_global_id": "glow-123",
        "feature": {"native_properties": [
            {"path": "m_BloomFactor", "native_type": "float", "float_value": 0.5},
        ]},
    })
    target["component_property_mappings"] = [{
        "source_component_type": "MyCompany.CinematicGlow",
        "source_entity_name": "CAM",
        "source_property_path": "m_BloomFactor",
        "value_type": "float",
        "target_scope": "component",
        "target_class": "CineCameraComponent",
        "target_property_name": "post_process_blend_weight",
        "value_scale": 0.75,
        "value_offset": 0.1,
    }]
    result = adaptive_components.adapt(csir, target, census)
    assert result["action_count"] == 2  # One built-in + one custom from real serialized data
    selected = next(x for x in result["actions"]
                    if x["source_component_type"] == "MyCompany.CinematicGlow")
    assert selected["source_property_path"] == "m_BloomFactor"
    assert selected["keys"] == [{"frame": 0, "value": 0.475}]
    assert selected["fidelity_status"] == "NATIVE_READBACK_AND_SEMANTIC_PARITY_UNVERIFIED"
    assert result["all_source_features_converted"] is False


def test_custom_bool_component_property_requires_exact_source_type():
    csir, target = source(), mapping()
    census = _census(csir)
    census["loaded_scene_components"] = [{
        "scene_path": "Assets/Benchmark002.unity",
        "object_path": "Benchmark002/CAM",
        "component_type": "Vendor.Visibility",
        "component_global_id": "vendor",
        "feature": {"native_properties": [
            {"path": "m_Enabled", "native_type": "bool", "bool_value": True},
        ]},
    }]
    target["component_property_mappings"] = [{
        "source_component_type": "Vendor.Visibility",
        "source_entity_name": "CAM",
        "source_property_path": "m_Enabled",
        "target_scope": "actor",
        "target_class": "CineCameraActor",
        "target_property_name": "bHidden",
        "value_type": "bool",
    }]
    record = adaptive_components.adapt(csir, target, census)
    assert record["actions"][0]["kind"] == "property_bool"
    assert record["actions"][0]["keys"][0]["value"] is True
    census["loaded_scene_components"][0]["feature"]["native_properties"][0]["native_type"] = "float"
    missing = adaptive_components.adapt(csir, target, census)
    assert missing["action_count"] == 0
    assert missing["decisions"][0]["status"] == "SOURCE_NATIVE_PROPERTY_NOT_CAPTURED"


def test_invalid_component_rule_never_executes_untrusted_target_expression():
    csir, target = source(), mapping()
    census = _census(csir)
    target["component_property_mappings"] = [{
        "source_component_type": "Vendor.Actor",
        "source_entity_name": "CAM",
        "source_property_path": "m_Custom",
        "target_scope": "actor",
        "target_class": "CineCameraActor",
        "target_property_name": "__import__('os').system('bad')",
        "value_type": "float",
    }]
    with __import__("pytest").raises(ValueError, match="Invalid target Unreal"):
        adaptive_components.adapt(csir, target, census)
