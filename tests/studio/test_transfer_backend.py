"""Best-effort backend protects source semantics and reports every partial transfer."""
import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for p in ("integrations/unreal", "packages/cinetwin", "packages/studio"):
    sys.path.insert(0, str(ROOT / p))

import sampling_plan
import transfer_backend


def rt(s):
    return {"value": round(s * 1_000_000), "rate": {"numerator": 1_000_000, "denominator": 1}}


def source():
    return {
        "schema_version": "0.1.0", "cutscene_id": "scene:any",
        "source": {
            "engine": "unity", "engine_version": "6000.1",
            "sequence_ref": "director-any", "project_fingerprint": "proj-any",
        },
        "timing": {
            "source_rate": {"numerator": 2, "denominator": 1},
            "duration_seconds": 2.0, "playback_start": rt(0),
            "playback_end": rt(2),
        },
        "assets": [{"asset_id": "sound", "name": "source.wav"}],
        "entities": [
            {"entity_id": "moving", "name": "MOVING_PROP", "ced_type": "entity.prop"},
            {"entity_id": "lens", "name": "CAM", "ced_type": "entity.camera",
             "metadata": {"camera": {
                 "field_of_view_degrees": 55.0, "aspect": 1.777,
             }}},
        ],
        "tracks": [
            {
                "name": "Move", "track_id": "moving:1", "ced_type": "animation.track",
                "binding_entity_id": "moving",
                "sections": [{"section_id": "s1", "start": rt(0), "end": rt(2),
                              "source_offset": rt(0), "time_scale": 1.0,
                              "payload": {"animation": {"curves": [{
                                  "canonical_semantic": "transform.position.x",
                                  "keys": [{"time_seconds": 0, "value": 0},
                                           {"time_seconds": 2, "value": 2}],
                              }]}}}],
            },
            {
                "name": "Mystery", "track_id": "custom:1", "ced_type": "shader.custom",
                "binding_entity_id": "moving",
                "sections": [{"section_id": "s2", "start": rt(0), "end": rt(2),
                              "payload": {"unknown": {"shader": "CustomGraph"}}}],
            },
            {
                "name": "Cuts", "track_id": "cuts:1", "ced_type": "camera.cut",
                "binding_entity_id": "lens",
                "sections": [{"section_id": "s3", "start": rt(0), "end": rt(2),
                              "payload": {}}],
            },
            {
                "name": "Sound", "track_id": "sound:1", "ced_type": "audio.track",
                "binding_entity_id": "",
                "sections": [{"section_id": "s4", "start": rt(0), "end": rt(2),
                              "payload": {"asset_id": "sound"}}],
            },
            {
                "name": "Event", "track_id": "event:1", "ced_type": "event.trigger",
                "binding_entity_id": "",
                "sections": [{"section_id": "s5", "start": rt(1), "end": rt(1),
                              "payload": {"signal": {}}}],
            },
        ],
    }


def mapping():
    return {
        "entities": {
            "MOVING_PROP": {"actor_label": "PropUE"},
            "CAM": {"actor_label": "CameraUE"},
        },
        "assets": {}, "sequence_asset_path": "/Game/Staging/LS_Mixed",
        "overwrite_sequence": False,
    }


def fake_capture(src, source_sha="sha-here"):
    plan = sampling_plan.build_plan(src, csir_sha256=source_sha)
    return {
        "kind": "cinetwin.behavior_capture", "cutscene_id": src["cutscene_id"],
        "source": plan["source"],
        "capture_layers": [{
            "layer": x["layer"],
            "status": "CAPTURED" if x["status"] == "PLANNED" else "NOT_IMPLEMENTED",
        } for x in plan["capabilities"]],
        "rigs": [],
        "samples": [{
            "time_seconds": entry["time_seconds"], "skeletal_poses": [],
            "entities": [{
                "entity_id": eid,
                "world_transform": {
                    "position_m": [entry["time_seconds"], 0.0, 0.0],
                    "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
                    "scale_xyz": [1.0, 1.0, 1.0],
                },
                **({"camera": {"vertical_fov_degrees": 55.0}} if eid == "lens" else {}),
                **({"light": {"intensity": 5.0 + entry["time_seconds"]}}
                   if eid == "light" else {}),
            } for eid in (x["entity_id"] for x in src["entities"])],
        } for entry in plan["samples"]],
        "errors": [],
    }


def test_one_unsupported_track_does_not_lose_native_camera_and_prop():
    src, target = source(), mapping()
    original = copy.deepcopy(src)
    plan, report = transfer_backend.compose(src, target)
    assert src == original
    assert report["source_track_count"] == 5
    assert report["accounted_track_count"] == 5
    assert [x["outcome"] for x in report["tracks"]] == [
        "NATIVE_UNVERIFIED", "SKIPPED", "NATIVE_UNVERIFIED",
        "SKIPPED", "NATIVE_UNVERIFIED",
    ]
    assert any(x["kind"] == "camera_cut" for x in plan["actions"])
    assert any(x["kind"] == "transform" for x in plan["actions"])
    assert any(x["kind"] == "marker" for x in plan["actions"])
    assert "Event" in report["tracks"][-1]["track_name"]
    assert report["no_full_fidelity_claim"] is True


def test_capture_bakes_unknown_actor_track_and_avoids_double_transform_animation():
    src = source()
    capture = fake_capture(src)
    plan, report = transfer_backend.compose(src, mapping(), capture=capture)
    assert report["tracks"][1]["outcome"] == "BAKED_PARTIAL"
    transforms = [x for x in plan["actions"] if x["kind"] == "transform"]
    assert len(transforms) == 1
    assert transforms[0]["track_name"] == "CutSceneAI Evaluated World Motion"
    assert [x["frame"] for x in transforms[0]["keys"]] == [0, 1, 2, 3]
    assert transforms[0]["keys"][-1]["location_cm"] == [0.0, 150.0, 0.0]


def test_invalid_capture_rejected_before_bake(tmp_path):
    src = source()
    src_path, map_path, capture_path = (
        tmp_path / "source.json", tmp_path / "mapping.json",
        tmp_path / "capture.json",
    )
    src_path.write_text(json.dumps(src), encoding="utf-8")
    map_path.write_text(json.dumps(mapping()), encoding="utf-8")
    cap = fake_capture(src, source_sha="totally-wrong")
    capture_path.write_text(json.dumps(cap), encoding="utf-8")
    with pytest.raises(transfer_backend.TransferBackendError, match="SHA-256"):
        transfer_backend.compose_files(src_path, map_path, capture_path=capture_path)
    cap["source"]["csir_sha256"] = hashlib.sha256(src_path.read_bytes()).hexdigest()
    cap["samples"].pop()
    capture_path.write_text(json.dumps(cap), encoding="utf-8")
    with pytest.raises(transfer_backend.TransferBackendError, match="failed verification"):
        transfer_backend.compose_files(src_path, map_path, capture_path=capture_path)


def test_a_valid_capture_is_bound_to_plan_with_byte_hashes(tmp_path):
    src_path, map_path = tmp_path / "source.json", tmp_path / "mapping.json"
    src_path.write_text(json.dumps(source()), encoding="utf-8")
    map_path.write_text(json.dumps(mapping()), encoding="utf-8")
    capture_path = tmp_path / "capture.json"
    capture_path.write_text(json.dumps(
        fake_capture(source(), hashlib.sha256(src_path.read_bytes()).hexdigest())
    ), encoding="utf-8")
    plan, report, evidence = transfer_backend.compose_files(
        src_path, map_path, capture_path=capture_path
    )
    assert report["source_capture_verification"]["failures"] == []
    assert evidence["source_capture_path"] == str(capture_path.resolve())
    assert report["outcomes"]["BAKED_PARTIAL"] == 1
    assert plan["overwrite_sequence"] is False


def test_only_unknown_features_are_blocked_without_any_meaningful_output():
    src = source()
    src["tracks"] = [src["tracks"][1]]
    src["entities"] = [src["entities"][0]]
    with pytest.raises(transfer_backend.TransferBackendError, match="empty sequence"):
        transfer_backend.compose(src, mapping())


def test_source_muted_track_does_not_trigger_a_bake():
    src = source()
    src["tracks"][1]["muted"] = True
    plan, report = transfer_backend.compose(src, mapping(), capture=fake_capture(src))
    assert report["tracks"][1]["outcome"] == "INACTIVE"
    assert sum(a["kind"] == "transform" for a in plan["actions"]) == 1


def test_unsafe_overwrite_is_refused():
    target = mapping()
    target["overwrite_sequence"] = True
    with pytest.raises(transfer_backend.TransferBackendError, match="Refusing"):
        transfer_backend.compose(source(), target)


def test_runtime_builder_checks_recomputed_prepared_plan_and_generates_receipt():
    code = (ROOT / "integrations" / "unreal" / "build_level_sequence.py").read_text()
    assert "def build_prepared_files(" in code
    assert "transfer_backend.compose_files(" in code
    assert "transfer_backend.verify_prepared_artifacts(" in code
    assert 'receipt["status"] = "GENERATED_UNVERIFIED"' in code
    assert "return _build_prepared_plan(csir, mapping, plan)" in code



def test_unhandled_camera_track_bakes_source_lens_and_world_pose():
    src = source()
    src["tracks"].append({
        "track_id": "cam:extra",
        "ced_type": "camera.transform",
        "binding_entity_id": "lens",
        "sections": [{"section_id": "unsupported-camera-animation",
                      "start": rt(0), "end": rt(2),
                      "payload": {"animation": {"curves": []}}}],
    })
    plan, report = transfer_backend.compose(src, mapping(), capture=fake_capture(src))
    assert report["tracks"][-1]["outcome"] == "BAKED_PARTIAL"
    assert len([a for a in plan["actions"] if a["kind"] == "camera_fov"]) == 1
    assert len([a for a in plan["actions"] if a["kind"] == "transform"]) == 2
    assert next(a for a in plan["actions"] if a["kind"] == "camera_fov")["keys"][0] == {
        "frame": 0, "value": 55.0,
    }


def test_unknown_light_animation_bakes_independently_measured_intensity():
    src = source()
    src["entities"].append({
        "entity_id": "light", "name": "LIGHT", "ced_type": "entity.light",
    })
    src["tracks"].append({
        "track_id": "light:unknown",
        "ced_type": "light.animation",
        "binding_entity_id": "light",
        "sections": [{"section_id": "light:section",
                      "start": rt(0), "end": rt(2),
                      "payload": {"animation": {"curves": [
                          {"canonical_semantic": "light.color.r", "keys": []},
                      ]}}}],
    })
    mapping_result = mapping()
    mapping_result["entities"]["LIGHT"] = {"actor_label": "LightUE"}
    plan, report = transfer_backend.compose(
        src, mapping_result, capture=fake_capture(src)
    )
    assert report["tracks"][-1]["outcome"] == "BAKED_PARTIAL"
    intensity = [a for a in plan["actions"] if a["kind"] == "light_intensity"]
    assert len(intensity) == 1
    assert intensity[0]["keys"][0] == {"frame": 0, "value": 5.0}
    assert intensity[0]["keys"][-1] == {"frame": 3, "value": 6.5}



def test_static_only_cutscene_produces_source_derived_pose_in_sequence():
    src = source()
    src["tracks"] = []
    src["entities"] = [{
        "entity_id": "static-prop",
        "name": "MY_PROP",
        "ced_type": "entity.prop",
        "metadata": {"world_transform": {
            "position": {"x": 1.0, "y": 2.0, "z": -3.0},
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
            "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
        }},
    }]
    target = mapping()
    target["entities"] = {"MY_PROP": {"actor_label": "PropUE"}}
    plan, report = transfer_backend.compose(src, target)
    assert report["source_track_count"] == 0
    assert len(plan["actions"]) == 1
    only = plan["actions"][0]
    assert only["kind"] == "transform"
    assert only["source_behavior_strategy"] == "source_static_world_pose"
    assert only["keys"][0]["location_cm"] == [300.0, 100.0, 200.0]
    assert only["keys"][0]["rotation_rpy_degrees"] == [0.0, 0.0, 0.0]



def test_persisted_preparation_verification_matches_cli_json_semantics():
    """Regression for an actual Unreal startup failure: Python tuple != JSON list."""
    plan, report = transfer_backend.compose(source(), mapping())
    evidence = {"csir_sha256": "A" * 64, "mapping_sha256": "B" * 64}
    saved = [json.loads(json.dumps(item)) for item in (plan, report, evidence)]
    # Native adapter emits tuples for transforms. CLI writes them as JSON
    # arrays; the Unreal editor must accept that honest round trip.
    action = next(a for a in plan["actions"] if a["kind"] == "transform")
    assert any(isinstance(key["location_cm"], tuple) for key in action["keys"])
    assert saved[0] != plan
    transfer_backend.verify_prepared_artifacts(
        saved[0], saved[1], saved[2], plan, report, evidence
    )


def test_preparation_verification_still_rejects_changed_values_and_evidence():
    plan, report = transfer_backend.compose(source(), mapping())
    evidence = {"csir_sha256": "A" * 64, "mapping_sha256": "B" * 64}
    saved = [json.loads(json.dumps(item)) for item in (plan, report, evidence)]
    saved[0]["duration_frames"] += 1
    with pytest.raises(transfer_backend.TransferBackendError, match=r"transfer-plan.json.*duration_frames"):
        transfer_backend.verify_prepared_artifacts(
            saved[0], saved[1], saved[2], plan, report, evidence
        )
    saved = [json.loads(json.dumps(item)) for item in (plan, report, evidence)]
    saved[2]["mapping_sha256"] = "tampered"
    with pytest.raises(transfer_backend.TransferBackendError, match=r"evidence.json.*mapping_sha256"):
        transfer_backend.verify_prepared_artifacts(
            saved[0], saved[1], saved[2], plan, report, evidence
        )


def test_engine_builder_calls_shared_semantically_exact_preparation_verifier():
    code = (ROOT / "integrations" / "unreal" / "build_level_sequence.py").read_text()
    assert "transfer_backend.verify_prepared_artifacts(" in code
    assert "submitted_plan != expected_plan" not in code



def test_cross_runtime_float_noise_does_not_reject_verified_rotation_keys():
    """C-math library last-bit drift must not falsely reject an identical CSIR."""
    plan, report = transfer_backend.compose(source(), mapping())
    evidence = {"csir_sha256": "A" * 64, "mapping_sha256": "B" * 64}
    saved = [json.loads(json.dumps(value)) for value in (plan, report, evidence)]
    key = next(
        key
        for action in saved[0]["actions"] if action["kind"] == "transform"
        for key in action["keys"]
    )
    key["rotation_rpy_degrees"][0] += 2e-10
    transfer_backend.verify_prepared_artifacts(
        saved[0], saved[1], saved[2], plan, report, evidence
    )


def test_cross_runtime_float_difference_greater_than_bound_is_rejected():
    plan, report = transfer_backend.compose(source(), mapping())
    evidence = {"csir_sha256": "A" * 64, "mapping_sha256": "B" * 64}
    saved = [json.loads(json.dumps(value)) for value in (plan, report, evidence)]
    key = next(
        key
        for action in saved[0]["actions"] if action["kind"] == "transform"
        for key in action["keys"]
    )
    key["rotation_rpy_degrees"][0] += 0.0001
    with pytest.raises(
        transfer_backend.TransferBackendError, match=r"rotation_rpy_degrees\[0\].*observed="
    ):
        transfer_backend.verify_prepared_artifacts(
            saved[0], saved[1], saved[2], plan, report, evidence
        )


def test_plan_rotation_plus_360_is_not_a_harmless_serialization_difference():
    plan, report = transfer_backend.compose(source(), mapping())
    evidence = {"csir_sha256": "A" * 64, "mapping_sha256": "B" * 64}
    saved = [json.loads(json.dumps(value)) for value in (plan, report, evidence)]
    key = next(
        key
        for action in saved[0]["actions"] if action["kind"] == "transform"
        for key in action["keys"]
    )
    key["rotation_rpy_degrees"][0] += 360.0
    with pytest.raises(transfer_backend.TransferBackendError, match="rotation_rpy_degrees"):
        transfer_backend.verify_prepared_artifacts(
            saved[0], saved[1], saved[2], plan, report, evidence
        )


def test_float_tolerance_never_softens_timeline_structure_or_provenance():
    plan, report = transfer_backend.compose(source(), mapping())
    evidence = {"csir_sha256": "A" * 64, "mapping_sha256": "B" * 64}
    saved = [json.loads(json.dumps(value)) for value in (plan, report, evidence)]
    key = next(
        key
        for action in saved[0]["actions"] if action["kind"] == "transform"
        for key in action["keys"]
    )
    key["frame"] += 1
    with pytest.raises(transfer_backend.TransferBackendError, match="frame"):
        transfer_backend.verify_prepared_artifacts(
            saved[0], saved[1], saved[2], plan, report, evidence
        )

    saved = [json.loads(json.dumps(value)) for value in (plan, report, evidence)]
    saved[2]["extra_floating_timestamp"] = 2e-10
    with pytest.raises(transfer_backend.TransferBackendError, match="provenance"):
        transfer_backend.verify_prepared_artifacts(
            saved[0], saved[1], saved[2], plan, report, evidence
        )



def test_parented_synthetic_static_pose_uses_source_hierarchy_instead_of_double_transform():
    src = source()
    src["entities"].append({
        "entity_id": "child", "name": "PROP_PARENTED",
        "ced_type": "entity.prop", "parent_entity_id": "moving",
        "metadata": {"world_transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 2.0},
            "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
            "scale": {"x": 1, "y": 1, "z": 1},
        }},
    })
    target = mapping()
    target["entities"]["PROP_PARENTED"] = {"actor_label": "ChildUE"}
    target["enable_cinetwin_hierarchy"] = True
    plan, report = transfer_backend.compose(src, target)
    assert report["hierarchy_reconstruction"] == [{
        "entity_name": "PROP_PARENTED",
        "outcome": "STATIC_CHILD_INHERITS_PARENT",
        "source_parent_name": "MOVING_PROP",
        "removed_synthetic_world_pose_tracks": 1,
    }]
    assert not any(
        a["kind"] == "transform" and a.get("entity_name") == "PROP_PARENTED"
        for a in plan["actions"]
    )
    assert any(
        a["kind"] == "transform" and a.get("entity_name") == "MOVING_PROP"
        for a in plan["actions"]
    )


def test_parented_independently_animated_child_gets_local_keys_from_capture():
    src = source()
    src["entities"].append({
        "entity_id": "child", "name": "PROP_PARENTED",
        "ced_type": "entity.prop", "parent_entity_id": "moving",
    })
    original = copy.deepcopy(src["tracks"][0])
    original["track_id"] = "child-dynamic"
    original["binding_entity_id"] = "child"
    original["name"] = "Child authored movement"
    src["tracks"].append(original)
    target = mapping()
    target["entities"]["PROP_PARENTED"] = {"actor_label": "ChildUE"}
    target["enable_cinetwin_hierarchy"] = True
    capture = fake_capture(src)
    for sample in capture["samples"]:
        t = sample["time_seconds"]
        for pose in sample["entities"]:
            if pose["entity_id"] == "child":
                pose["world_transform"]["position_m"] = [2.0 + 2*t, 0, 0]
            elif pose["entity_id"] == "moving":
                pose["world_transform"]["position_m"] = [t, 0, 0]
    plan, report = transfer_backend.compose(src, target, capture=capture)
    child = [
        a for a in plan["actions"]
        if a["kind"] == "transform" and a.get("entity_name") == "PROP_PARENTED"
    ]
    assert len(child) == 1
    assert child[0]["transform_space"] == "PARENT_LOCAL"
    assert child[0]["source_parent_entity_id"] == "moving"
    assert [k["frame"] for k in child[0]["keys"]] == [0, 1, 2, 3]
    assert child[0]["keys"][0]["location_cm"] == [0.0, 200.0, 0.0]
    assert child[0]["keys"][-1]["location_cm"] == [0.0, 350.0, 0.0]
    assert report["hierarchy_reconstruction"][0]["outcome"] == (
        "CAPTURED_PARENT_LOCAL_BEST_EFFORT"
    )
    assert report["tracks"][-1]["outcome"] == "BAKED_PARTIAL"


def test_parented_independent_child_is_blocked_if_source_capture_missing():
    src = source()
    src["entities"].append({
        "entity_id": "child", "name": "PROP_PARENTED",
        "ced_type": "entity.prop", "parent_entity_id": "moving",
    })
    original = copy.deepcopy(src["tracks"][0])
    original["track_id"] = "child-dynamic"
    original["binding_entity_id"] = "child"
    src["tracks"].append(original)
    target = mapping()
    target["entities"]["PROP_PARENTED"] = {"actor_label": "ChildUE"}
    target["enable_cinetwin_hierarchy"] = True
    with pytest.raises(transfer_backend.TransferBackendError, match="verified CineTwin"):
        transfer_backend.compose(src, target)


def test_generic_hierarchy_planner_accepts_only_provenance_checked_child_local_motion():
    from hierarchy_realization import build_attachment_operations
    src = source()
    src["entities"].append({
        "entity_id": "child", "name": "PROP_PARENTED",
        "ced_type": "entity.prop", "parent_entity_id": "moving",
    })
    target = mapping()
    target["entities"]["PROP_PARENTED"] = {"actor_label": "ChildUE"}
    child = {
        "kind": "transform", "entity_name": "PROP_PARENTED",
        "source_parent_entity_id": "moving",
        "transform_space": "PARENT_LOCAL",
        "source_behavior_strategy": "captured_parent_child_relative_trs",
        "keys": [{"frame": 0, "location_cm": [0.0, 200.0, 0.0],
                  "rotation_rpy_degrees": [0.0, 0.0, 0.0]}],
    }
    result = build_attachment_operations(src, target, [child])
    assert len(result["attachments"]) == 1
    assert result["attachments"][0]["parent_actor_label"] == "PropUE"

    unsafe = dict(child, source_behavior_strategy="source_world_curve")
    from hierarchy_realization import HierarchyRealizationError
    with pytest.raises(HierarchyRealizationError, match="verified conversion provenance"):
        build_attachment_operations(src, target, [unsafe])
