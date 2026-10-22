"""Regression checks for reusable Benchmark002 conversion behavior (pure Python)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "integrations" / "unreal"))
import csir_plan


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
