"""CED v0.2 recognition, route coverage and executable-adapter truth gates."""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "studio"))

import feature_dispatch as dispatch


def _source():
    return {
        "source": {"engine": "unity"}, "cutscene_id": "source",
        "assets": [
            {"asset_id": "A", "ced_type": "asset.identity", "name": "asset",
             "metadata": {"asset_type": "UnityEngine.Texture2D"}},
            {"asset_id": "B", "ced_type": "plugin.proprietary_asset", "name": "vendor",
             "metadata": {"asset_type": "Vendor.SceneBundle"}},
        ],
        "entities": [
            {"entity_id": "c", "ced_type": "entity.camera", "name": "Cam",
             "metadata": {"native_type": "UnityEngine.Camera"}},
        ],
        "tracks": [
            {"track_id": "cam-track", "name": "CAM", "ced_type": "camera.cut",
             "sections": [{"section_id": "c1", "ced_type": "camera.cut",
                           "native_payload": {"native_asset_type": "UnityEngine.Timeline.CameraClip"},
                           "payload": {"animation": {"curves": [
                               {"property_name": "lens.CustomVendorCurve",
                                "canonical_semantic": "plugin.lens_effect"},
                           ]}}}]},
        ],
        "relationships": [
            {"relationship_id": "r", "ced_type": "transform.parent",
             "source_id": "c", "target_id": "group"},
        ],
    }


def test_39_feature_families_have_routes_for_every_canonical_semantic():
    data = dispatch.catalog()
    assert data["version"] == "0.2.0"
    assert len(data["feature_families"]) == 39
    assert len(data["_domain_for"]) >= 700
    assert all(dispatch.recipe(semantic, features=data)["candidate_route"] != "plugin_required"
               for semantic in data["_domain_for"])
    assert data["_sha256"]
    old = json.loads((ROOT / "packages" / "contracts" / "dictionary" /
                      "cutscene-elements-v0.1.json").read_text())
    for category, ids in old["categories"].items():
        assert set(ids) <= set(data["categories"][category])


def test_source_assets_entities_tracks_sections_curves_relationships_never_disappear():
    record = dispatch.audit(_source(), {"actions": [
        {"kind": "camera_cut", "track_name": "CAM"},
        {"kind": "camera_setup", "entity_name": "Cam"},
    ]})
    assert record["source_occurrence_count"] == 7
    assert record["accounted_occurrence_count"] == 7
    assert {r["kind"] for r in record["source_occurrences"]} == {
        "assets", "entities", "tracks", "sections", "curves", "relationships"}
    assert record["full_conversion_verified"] is False
    assert len(record["catalog_sha256"]) == 64
    unknown = next(r for r in record["source_occurrences"] if r["ced"] == "plugin.lens_effect")
    assert unknown["state"] == "SOURCE_RECORDED_ADAPTER_MISSING"
    native = next(r for r in record["source_occurrences"] if r["ced"] == "plugin.proprietary_asset")
    assert native["source_native_type"] == "Vendor.SceneBundle"
    assert native["target_readback_verified"] is False


def test_all_existing_native_actions_are_candidates_not_fidelity_claims():
    csir = _source()
    result = dispatch.audit(csir, {"actions": [
        {"kind": "camera_cut", "track_name": "CAM"},
        {"kind": "camera_setup", "entity_name": "Cam"},
    ]})
    camera = next(r for r in result["source_occurrences"]
                  if r["kind"] == "tracks")
    assert camera["state"] == "NATIVE_ACTION_PLANNED_UNVERIFIED"
    assert camera["matching_plan_action_kinds"] == ["camera_cut"]
    assert camera["target_readback_verified"] is False
    assert result["full_conversion_verified"] is False


def test_incomplete_or_custom_target_action_exposed_before_native_generation():
    result = dispatch.audit(_source(), {"actions": [
        {"kind": "vendor_magic_cinematic", "entity_name": "Cam"},
    ]})
    assert result["unknown_action_kinds"] == ["vendor_magic_cinematic"]
    assert result["full_conversion_verified"] is False
    assert result["missing_adapter_count"] > 0


def test_registered_custom_extension_is_versioned_not_auto_verified():
    features = dispatch.catalog()
    extensions = dispatch.HandlerRegistry(features)
    extensions.register("plugin.proprietary_asset", lambda x: x, name="My Adapter",
                        version="1.0.0")
    record = dispatch.audit(_source(), handlers=extensions, features=features)
    row = next(r for r in record["source_occurrences"]
               if r["ced"] == "plugin.proprietary_asset")
    assert row["state"] == "REGISTERED_ADAPTER_NOT_EXECUTED"
    assert row["custom_handler"] == {"name": "My Adapter", "version": "1.0.0"}
    assert row["behavior_fidelity_verified"] is False
    assert record["missing_adapter_count"] > 0
    with pytest.raises(dispatch.FeatureDispatchError, match="Duplicate"):
        extensions.register("plugin.proprietary_asset", lambda x: x, name="Dup",
                            version="1.1")
    with pytest.raises(dispatch.FeatureDispatchError, match="evidence"):
        extensions.register("ui.canvas", lambda x: x, name="Unsafe",
                            version="1.0", requires=("SOURCE",))


def test_registered_entity_adapter_executes_with_exact_source_provenance():
    source = _source()
    mapping = {"entities": {"Cam": {"actor_label": "CSAI_Cam"}}}
    before = deepcopy(source)

    def build(copy_of_csir, copy_of_mapping, entity):
        copy_of_csir["entities"].clear()
        copy_of_mapping["entities"].clear()
        entity["name"] = "changed"
        return [{"kind": "camera_setup", "entity_name": "Cam",
                 "actor_label": "CSAI_Cam",
                 "source_behavior_strategy": "exact_source_camera_metadata"}]

    registry = dispatch.HandlerRegistry()
    registry.register("entity.camera", build, name="source_camera", version="1.0.0",
                      source_kinds=("entities",), builder_actions=("camera_setup",))
    actions = registry.plan_other_occurrences(source, mapping)
    assert source == before
    assert mapping["entities"]["Cam"]["actor_label"] == "CSAI_Cam"
    assert len(actions) == 1
    assert actions[0]["source_location"] == "entities[0]"
    assert actions[0]["source_id"] == "c"
    assert actions[0]["required_evidence_gates"] == [
        "SOURCE", "PLAN", "NATIVE_READBACK", "BEHAVIOR"
    ]
    report = dispatch.audit(source, {"actions": actions}, handlers=registry)
    camera = next(row for row in report["source_occurrences"]
                  if row["source_location"] == "entities[0]")
    assert camera["state"] == "CUSTOM_HANDLER_REGISTERED_UNVERIFIED"
    assert camera["target_readback_verified"] is False
    assert report["full_conversion_verified"] is False


def test_new_ced_scalar_adapter_can_emit_a_typed_native_action_without_parity_claim():
    source = _source()
    mapping = {"entities": {"Cam": {"actor_label": "CSAI_Cam"}}}
    registry = dispatch.HandlerRegistry()
    registry.register(
        "entity.camera",
        lambda _source, _mapping, _entity: [{
            "kind": "property_float", "source_semantic": "entity.camera",
            "entity_name": "Cam", "actor_label": "CSAI_Cam",
            "target_scope": "component", "target_class": "CineCameraComponent",
            "target_property_name": "post_process_blend_weight",
            "target_property_path": "post_process_blend_weight",
            "source_behavior_strategy": "source_explicit_boolean_to_blend_weight",
            "keys": [{"frame": 0, "value": 0.0}],
        }],
        name="camera_postprocess_candidate", version="1.0.0",
        source_kinds=("entities",), builder_actions=("property_float",),
    )
    actions = registry.plan_other_occurrences(source, mapping)
    assert len(actions) == 1
    dispatch.verify_executable_actions({"actions": actions})
    report = dispatch.audit(source, {"actions": actions}, handlers=registry)
    camera = next(row for row in report["source_occurrences"]
                  if row["source_location"] == "entities[0]")
    assert camera["matching_plan_action_kinds"] == ["property_float"]
    assert camera["state"] == "CUSTOM_HANDLER_REGISTERED_UNVERIFIED"
    assert actions[0]["fidelity_status"] == "NATIVE_READBACK_AND_BEHAVIOR_UNVERIFIED"
    assert camera["behavior_fidelity_verified"] is False


def test_same_named_tracks_need_exact_source_location_for_ced_attribution():
    source = _source()
    duplicate = deepcopy(source["tracks"][0])
    duplicate["track_id"] = "another"
    source["tracks"].append(duplicate)
    unrelated = dispatch.audit(source, {"actions": [
        {"kind": "camera_cut", "track_name": "CAM"}
    ]})
    assert all(row["state"] == "NATIVE_ACTION_HANDLER_MISSING"
               for row in unrelated["source_occurrences"] if row["kind"] == "tracks")
    exact = dispatch.audit(source, {"actions": [
        {"kind": "camera_cut", "track_name": "CAM", "source_location": "tracks[1]"}
    ]})
    tracks = [row for row in exact["source_occurrences"] if row["kind"] == "tracks"]
    assert [row["state"] for row in tracks] == [
        "NATIVE_ACTION_HANDLER_MISSING", "NATIVE_ACTION_PLANNED_UNVERIFIED"
    ]


def test_registered_adapter_rejects_a_mismatched_source_location():
    source = _source()
    registry = dispatch.HandlerRegistry()
    registry.register("entity.camera", lambda _c, _m, _e: [],
                      name="camera", version="1.0.0", source_kinds=("entities",),
                      builder_actions=("camera_setup",))
    with pytest.raises(dispatch.FeatureDispatchError, match="source kind"):
        registry.plan_for(source, {}, source["entities"][0],
                          kind="entities", location="tracks[0]")


@pytest.mark.parametrize("action", [
    {"kind": "vendor_magic", "entity_name": "Cam", "actor_label": "CSAI_Cam"},
    {"kind": "property_float", "source_semantic": "entity.camera",
     "entity_name": "Cam", "actor_label": "CSAI_Cam", "target_scope": "component",
     "target_class": "CineCameraComponent", "target_property_name": "post_process_blend_weight",
     "target_property_path": "post_process_blend_weight",
     "keys": [{"frame": 0, "value": float("nan")}]},
    {"kind": "property_bool", "source_semantic": "entity.camera",
     "entity_name": "Cam", "actor_label": "CSAI_Cam", "target_scope": "component",
     "target_class": "CineCameraComponent", "target_property_name": "bConstrainAspectRatio",
     "target_property_path": "bConstrainAspectRatio",
     "keys": [{"frame": 0, "value": 1}]},
    {"kind": "camera_setup", "source_behavior_strategy": "source_camera",
     "target_readback_verified": True},
])
def test_adapter_rejects_undeclared_unsafe_or_fake_verified_actions(action):
    registry = dispatch.HandlerRegistry()
    registry.register("entity.camera", lambda _c, _m, _e: [action],
                      name="unsafe", version="1.0.0", source_kinds=("entities",),
                      builder_actions=("camera_setup", "property_float", "property_bool"))
    with pytest.raises(dispatch.FeatureDispatchError):
        registry.plan_other_occurrences(
            _source(), {"entities": {"Cam": {"actor_label": "CSAI_Cam"}}}
        )


def test_new_vendor_semantic_keeps_original_type_and_requires_plugin():
    value = dispatch.recipe("company.magic_cutscene")
    assert value["registered"] is False
    assert value["candidate_route"] == "plugin_required"
    assert value["executable_handler"] is None
    assert value["preserve_source_native_payload"] is True


def test_no_generic_catalog_route_is_automatically_executable():
    data = dispatch.catalog()
    assert all(dispatch.recipe(k, features=data)["executable_handler"] is None
               for k in data["_domain_for"])
    assert dispatch.BUILDER_ACTIONS == {
        "camera_setup", "camera_cut", "camera_fov", "transform",
        "skeletal_animation", "light_intensity", "audio", "marker",
        "skeletal_world_root_lock", "actor_visibility", "property_float",
        "property_bool",
    }


def test_identical_ced_in_unrelated_track_not_false_positive_planned():
    source = _source()
    source["tracks"].append({
        "track_id": "other", "name": "OTHER",
        "ced_type": "camera.cut", "sections": [],
    })
    report = dispatch.audit(source, {"actions": [
        {"kind": "camera_cut", "track_name": "CAM"},
    ]})
    by_name = {row["source_name"]: row for row in report["source_occurrences"]
               if row["kind"] == "tracks"}
    assert by_name["CAM"]["state"] == "NATIVE_ACTION_PLANNED_UNVERIFIED"
    assert by_name["OTHER"]["state"] == "NATIVE_ACTION_HANDLER_MISSING"
    assert by_name["OTHER"]["matching_plan_action_kinds"] == []
    assert report["full_conversion_verified"] is False


def test_unattributed_native_action_never_claims_source_implementation():
    report = dispatch.audit(_source(), {"actions": [{"kind": "camera_cut"}]})
    track = next(row for row in report["source_occurrences"] if row["kind"] == "tracks")
    assert track["state"] == "NATIVE_ACTION_HANDLER_MISSING"


def test_unknown_ue_action_is_blocked_before_studio_generation():
    with pytest.raises(dispatch.FeatureDispatchError, match="No executable Unreal builder handler"):
        dispatch.verify_executable_actions({
            "actions": [{"kind": "plugin.execute_vendor_shader"}],
        })
    dispatch.verify_executable_actions({
        "actions": [{"kind": "camera_cut"}, {"kind": "audio"}],
    })
    with pytest.raises(dispatch.FeatureDispatchError, match="requires a list"):
        dispatch.verify_executable_actions({"actions": "fake_sequence"})
