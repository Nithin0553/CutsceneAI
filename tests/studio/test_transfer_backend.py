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
    assert "submitted_plan != expected_plan" in code
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
