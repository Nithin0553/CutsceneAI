"""Regression checks for reusable Benchmark002 conversion behavior (pure Python)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "integrations" / "unreal"))
import csir_plan
import scene_prep


def rt(t):
    return {"value": int(t * 1000000), "rate": {"numerator": 1000000, "denominator": 1}}


def curve(semantic, keys, *, native=False):
    return {"canonical_semantic": semantic,
            "keys": [{"time_seconds": t, "value": v,
                      "in_tangent": 0.0, "out_tangent": 0.0, "weighted_mode": 0}
                     for t, v in keys],
            "native_keys": [{}] if native else []}


def document(sections):
    return {
        "schema_version": "0.1.0", "source": {"engine": "unity"},
        "timing": {"source_rate": {"numerator": 24, "denominator": 1},
                   "duration_seconds": 4.0},
        "assets": [],
        "entities": [{"entity_id": "prop", "name": "PROP", "ced_type": "entity.prop"}],
        "tracks": [{"ced_type": "animation.track", "name": "Motion",
                    "binding_entity_id": "prop", "sections": sections}],
    }


def section(start, end, curves):
    return {"start": rt(start), "end": rt(end), "source_offset": rt(0),
            "time_scale": 1.0, "payload": {"animation": {"curves": curves}}}


def mapped():
    return {"entities": {"PROP": {"actor_label": "PROP"}}}


def test_all_sequential_transform_sections_are_compiled():
    doc = document([
        section(0, 2, [curve("transform.position.x", [(0, 0), (2, 2)])]),
        section(2, 4, [curve("transform.position.x", [(0, 3), (2, 4)])]),
    ])
    action = next(a for a in csir_plan.build_plan(doc, mapped())["actions"]
                  if a["kind"] == "transform")
    assert [k["frame"] for k in action["keys"]] == [0, 48, 96]
    assert action["keys"][0]["location_cm"][1] == 0
    assert action["keys"][-1]["location_cm"][1] == 400


def test_overlapping_transform_clips_refuse_unsupported_blend():
    doc = document([
        section(0, 3, [curve("transform.position.x", [(0, 0), (3, 3)])]),
        section(2, 4, [curve("transform.position.x", [(0, 1), (2, 2)])]),
    ])
    try:
        csir_plan.build_plan(doc, mapped())
    except csir_plan.PlanError as e:
        assert "Overlapping transform clips" in str(e)
    else:
        raise AssertionError("must reject unimplemented transform blending")


def test_hermite_source_curve_is_evaluated_at_intermediate_frames():
    doc = document([section(0, 1, [
        curve("transform.position.x", [(0, 0), (1, 1)], native=True)
    ])])
    action = next(a for a in csir_plan.build_plan(doc, mapped())["actions"]
                  if a["kind"] == "transform")
    assert action["baked_source_curves"] is True
    assert len(action["keys"]) == 25
    # Zero slopes yield smoothstep: 0.25-time -> 0.15625, not 0.25.
    assert abs(action["keys"][6]["location_cm"][1] - 15.625) < 1e-5


def test_partial_quaternion_is_rejected():
    doc = document([section(0, 1, [
        curve("transform.rotation.x", [(0, 0), (1, 1)]),
    ])])
    try:
        csir_plan.build_plan(doc, mapped())
    except csir_plan.PlanError as e:
        assert "Partial quaternion" in str(e)
    else:
        raise AssertionError("must not silently default missing quaternion channels")


def test_skeletal_animation_metadata_contains_trim_and_blend():
    doc = document([])
    doc["entities"][0]["ced_type"] = "entity.character"
    doc["assets"] = [{"asset_id": "clip", "name": "walk"}]
    sec = section(0, 3, [curve("", [(0, 0)], native=False)])
    sec["payload"]["asset_id"] = "clip"
    sec["source_offset"] = rt(0.5)
    sec["native_payload"] = {"blend_in_seconds": 0.25, "blend_out_seconds": 0.5}
    doc["tracks"][0]["sections"] = [sec]
    mapping = {**mapped(), "assets": {"walk": "/Game/Walk"}}
    action = next(a for a in csir_plan.build_plan(doc, mapping)["actions"]
                  if a["kind"] == "skeletal_animation")
    assert action["source_offset_seconds"] == 0.5
    assert action["blend_in_seconds"] == 0.25
    assert action["blend_out_seconds"] == 0.5


def test_light_intensity_is_converted_to_sampled_target_track():
    doc = document([])
    doc["entities"][0]["ced_type"] = "entity.light"
    doc["tracks"][0]["ced_type"] = "light.animation"
    doc["tracks"][0]["sections"] = [
        section(0, 1, [curve("light.intensity", [(0, 2), (1, 6)], native=True)])
    ]
    action = next(a for a in csir_plan.build_plan(doc, mapped())["actions"]
                  if a["kind"] == "light_intensity")
    assert len(action["keys"]) == 25
    assert action["keys"][0] == {"frame": 0, "value": 2.0}
    assert action["keys"][-1] == {"frame": 24, "value": 6.0}


def test_only_final_skeletal_section_holds_last_pose():
    doc = document([])
    doc["entities"][0]["ced_type"] = "entity.character"
    doc["assets"] = [{"asset_id": "walk", "name": "Walk"},
                     {"asset_id": "idle", "name": "Idle"}]
    first = section(0, 2, [])
    first["payload"]["asset_id"] = "walk"
    second = section(1.75, 3, [])
    second["payload"]["asset_id"] = "idle"
    doc["tracks"][0]["sections"] = [first, second]
    mapping = {**mapped(), "assets": {"Walk": "/Game/Walk", "Idle": "/Game/Idle"}}
    actions = [a for a in csir_plan.build_plan(doc, mapping)["actions"]
               if a["kind"] == "skeletal_animation"]
    assert actions[0]["hold_end_frame"] == actions[0]["end_frame"]
    assert actions[0]["completion_mode"] == "project_default"
    assert actions[1]["hold_end_frame"] == 96


def test_provenance_checked_source_first_frame_places_dynamic_actor(tmp_path):
    doc = document([section(1, 3, [
        curve("transform.position.x", [(0, 0), (2, 2)])
    ])])
    doc["cutscene_id"] = "unity:fixed:7"
    doc["source"].update({"sequence_ref": "Timeline|123",
                          "project_fingerprint": "sha256:source"})
    capture = {
        "kind": "cinetwin.behavior_capture",
        "cutscene_id": doc["cutscene_id"],
        "source": {"sequence_ref": "Timeline|123", "project_fingerprint": "sha256:source"},
        "samples": [{"time_seconds": 0.0, "entities": [{
            "entity_id": "prop",
            "world_transform": {
                "position_m": [1.0, 2.0, -3.0],
                "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
                "scale_xyz": [1.0, 1.0, 1.0],
            },
        }]}],
    }
    source_file = tmp_path / "source.capture.json"
    source_file.write_text(json.dumps(capture), encoding="utf-8")
    mapping = {**mapped(), "source_behavior_capture_path": str(source_file)}
    operations = scene_prep.build_scene_prep(doc, mapping)
    assert len(operations) == 1
    assert operations[0]["source"] == "cinetwin.source_evaluated_first_frame"
    assert operations[0]["location_cm"] == (300.0, 100.0, 200.0)


def test_first_frame_capture_rejects_stale_project_identity(tmp_path):
    doc = document([])
    doc["cutscene_id"] = "unity:fixed"
    doc["source"].update({"sequence_ref": "A", "project_fingerprint": "sha256:correct"})
    capture_file = tmp_path / "wrong.json"
    capture_file.write_text(json.dumps({
        "kind": "cinetwin.behavior_capture",
        "cutscene_id": "unity:fixed",
        "source": {"sequence_ref": "A", "project_fingerprint": "sha256:wrong"},
        "samples": [{"time_seconds": 0, "entities": []}],
    }), encoding="utf-8")
    with pytest.raises(csir_plan.PlanError, match="provenance mismatch"):
        scene_prep.build_scene_prep(
            doc, {**mapped(), "source_behavior_capture_path": str(capture_file)})


def test_unreal_compat_uses_documented_easing_and_linear_api(monkeypatch):
    import importlib.util
    from types import SimpleNamespace

    easing_calls = []
    linear = object()
    fake_unreal = SimpleNamespace(
        FrameNumber=int,
        MovieSceneKeyInterpolation=SimpleNamespace(LINEAR=linear),
        MovieSceneSectionEasingExtensions=SimpleNamespace(
            set_ease_in_duration=lambda sec, frames: easing_calls.append(("in", frames)),
            set_ease_out_duration=lambda sec, frames: easing_calls.append(("out", frames)),
        ),
    )
    monkeypatch.setitem(sys.modules, "unreal", fake_unreal)
    path = Path(__file__).resolve().parents[2] / "integrations" / "unreal" / "unreal_compat.py"
    spec = importlib.util.spec_from_file_location("unreal_compat_correction_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.set_section_easing_frames(object(), ease_in=6, ease_out=12) == (
        "MovieSceneSectionEasingExtensions"
    )
    assert easing_calls == [("in", 6), ("out", 12)]

    calls = []

    class Channel:
        def add_key(self, frame, value, *, interpolation):
            calls.append((frame, value, interpolation))
            return "native-key"

    assert module.add_linear_channel_key(Channel(), 24, 1.25) == "native-key"
    assert calls == [(24, 1.25, linear)]



@pytest.mark.parametrize(
    "native,expected",
    [
        ({"blend_in_seconds": -1.0, "ease_in_seconds": 0.0}, 0.0),
        ({"blend_in_seconds": -1.0, "ease_in_seconds": 0.5}, 0.5),
        ({"blend_in_seconds": 0.0, "ease_in_seconds": 0.25}, 0.25),
        ({"blend_in_seconds": 0.75, "ease_in_seconds": 0.25}, 0.75),
        ({"blend_in_seconds": 0.0}, 0.0),
        ({}, 0.0),
    ],
)
def test_unity_timeline_blend_sentinel_and_explicit_ease(native, expected):
    assert csir_plan.timeline_clip_easing_seconds(native, "in") == expected


@pytest.mark.parametrize("invalid", [-2.0, -0.5, float("nan"), float("inf"), "bad"])
def test_unexpected_blend_value_blocks_planning(invalid):
    with pytest.raises(csir_plan.PlanError):
        csir_plan.timeline_clip_easing_seconds(
            {"blend_out_seconds": invalid}, "out"
        )


def test_negative_unity_ease_is_not_silently_discarded():
    with pytest.raises(csir_plan.PlanError, match="Negative Timeline"):
        csir_plan.timeline_clip_easing_seconds(
            {"blend_in_seconds": -1.0, "ease_in_seconds": -0.1}, "in"
        )


def test_skeletal_plan_normalizes_unset_unity_blend_before_runtime():
    doc = document([])
    doc["entities"][0]["ced_type"] = "entity.character"
    doc["assets"] = [{"asset_id": "clip", "name": "Walk"}]
    src_section = section(0, 3, [])
    src_section["payload"]["asset_id"] = "clip"
    src_section["native_payload"] = {
        "blend_in_seconds": -1.0,
        "blend_out_seconds": -1.0,
        "ease_in_seconds": 0.0,
        "ease_out_seconds": 0.0,
    }
    doc["tracks"][0]["sections"] = [src_section]
    mapping = {**mapped(), "assets": {"Walk": "/Game/Walk"}}
    action = next(
        x for x in csir_plan.build_plan(doc, mapping)["actions"]
        if x["kind"] == "skeletal_animation"
    )
    assert action["blend_in_seconds"] == 0.0
    assert action["blend_out_seconds"] == 0.0

    src_section["native_payload"]["ease_in_seconds"] = 0.25
    src_section["native_payload"]["blend_out_seconds"] = 0.4
    updated = next(
        x for x in csir_plan.build_plan(doc, mapping)["actions"]
        if x["kind"] == "skeletal_animation"
    )
    assert updated["blend_in_seconds"] == 0.25
    assert updated["blend_out_seconds"] == 0.4
