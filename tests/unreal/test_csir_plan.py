import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNREAL_INTEGRATION = ROOT / "integrations" / "unreal"
sys.path.insert(0, str(UNREAL_INTEGRATION))

import csir_plan


def _rt(seconds: float) -> dict:
    return {
        "value": round(seconds * 1_000_000),
        "rate": {"numerator": 1_000_000, "denominator": 1},
    }


def _curve(semantic: str, values: list[tuple[float, float]], property_name: str = "") -> dict:
    return {
        "canonical_semantic": semantic,
        "property_name": property_name,
        "keys": [
            {
                "time_seconds": time_seconds,
                "value": value,
                "in_tangent": 0.0,
                "out_tangent": 0.0,
            }
            for time_seconds, value in values
        ],
    }


def _fixture() -> tuple[dict, dict]:
    prop_id = "entity:prop"
    camera_id = "entity:camera"
    character_id = "entity:character"
    assets = [
        {"asset_id": "anim", "name": "mixamo.com"},
        {"asset_id": "audio", "name": "ominous"},
        {"asset_id": "signal", "name": "Benchmark_Event_01"},
    ]
    prop_curves = [
        _curve("transform.infinite_offset.position.x", [(0.0, -2.0)]),
        _curve("transform.infinite_offset.position.y", [(0.0, 0.5)]),
        _curve("transform.infinite_offset.position.z", [(0.0, -5.0)]),
        _curve("transform.position.x", [(2.0, 0.0), (7.0, 4.0)]),
    ]
    character_curves = [
        _curve("", [(0.0, 0.0), (3.25, 0.1)], "RootT.x"),
        _curve("", [(0.0, 1.0), (3.25, 1.0)], "RootT.y"),
        _curve("", [(0.0, 0.0), (3.25, -1.5)], "RootT.z"),
    ]
    camera_curves = [
        _curve("transform.infinite_offset.position.x", [(0.0, 4.0)]),
        _curve("transform.infinite_offset.position.y", [(0.0, 1.2)]),
        _curve("transform.infinite_offset.position.z", [(0.0, -3.0)]),
        _curve("transform.infinite_offset.rotation.x", [(0.0, 0.0)]),
        _curve("transform.infinite_offset.rotation.y", [(0.0, 0.0)]),
        _curve("transform.infinite_offset.rotation.z", [(0.0, 0.0)]),
        _curve("transform.infinite_offset.rotation.w", [(0.0, 1.0)]),
        _curve(
            "transform.rotation.euler_native",
            [(5.0, 0.0), (10.0, 0.0)],
            "localEulerAnglesRaw.x",
        ),
        _curve(
            "transform.rotation.euler_native",
            [(5.0, 0.0), (10.0, 0.0)],
            "localEulerAnglesRaw.y",
        ),
        _curve(
            "transform.rotation.euler_native",
            [(5.0, 0.0), (10.0, 5.0)],
            "localEulerAnglesRaw.z",
        ),
        _curve("", [(5.0, 35.0), (10.0, 25.0)], "field of view"),
    ]
    csir = {
        "schema_version": "0.1.0",
        "source": {"engine": "unity", "adapter_version": "0.1.3"},
        "timing": {
            "source_rate": {"numerator": 60, "denominator": 1},
            "duration_seconds": 10.0,
        },
        "assets": assets,
        "entities": [
            {"entity_id": prop_id, "name": "MOVING_PROP", "ced_type": "entity.prop"},
            {
                "entity_id": character_id,
                "name": "CHARACTER_Guard",
                "ced_type": "entity.character",
            },
            {
                "entity_id": camera_id,
                "name": "CAM_B_Close",
                "ced_type": "entity.camera",
                "metadata": {
                    "camera": {
                        "orthographic": False,
                        "field_of_view_degrees": 35.0,
                        "aspect": 4.93486166,
                        "near_clip": 0.3,
                        "far_clip": 1000.0,
                    }
                },
            },
        ],
        "tracks": [
            {
                "name": "CHARACTER_Animation",
                "ced_type": "animation.track",
                "binding_entity_id": character_id,
                "sections": [
                    {
                        "start": _rt(0.0),
                        "end": _rt(3.25),
                        "source_offset": _rt(0.0),
                        "time_scale": 1.0,
                        "payload": {
                            "asset_id": "anim",
                            "animation": {"curves": character_curves},
                        },
                    }
                ],
            },
            {
                "name": "MOVING_PROP_Movement",
                "ced_type": "animation.track",
                "binding_entity_id": prop_id,
                "sections": [
                    {
                        "start": _rt(0.0),
                        "end": _rt(7.0),
                        "payload": {"animation": {"curves": prop_curves}},
                    }
                ],
            },
            {
                "name": "CAM_B_Animation",
                "ced_type": "camera.transform",
                "binding_entity_id": camera_id,
                "sections": [
                    {
                        "start": _rt(0.0),
                        "end": _rt(10.0),
                        "payload": {"animation": {"curves": camera_curves}},
                    }
                ],
            },
            {
                "name": "CAM_B_Cut",
                "ced_type": "camera.cut",
                "binding_entity_id": camera_id,
                "sections": [{"start": _rt(5.0), "end": _rt(10.0)}],
            },
            {
                "name": "EVENT_Main",
                "ced_type": "event.trigger",
                "binding_entity_id": "",
                "sections": [
                    {
                        "start": _rt(6.5),
                        "end": _rt(6.5),
                        "payload": {"signal": {"signal_asset_id": "signal"}},
                    }
                ],
            },
        ],
    }
    mapping = {
        "entities": {
            "CHARACTER_Guard": {"actor_label": "CHARACTER_Guard"},
            "MOVING_PROP": {"actor_label": "MOVING_PROP"},
            "CAM_B_Close": {"actor_label": "CAM_B_Close"},
        },
        "assets": {"mixamo.com": "/Game/A", "ominous": "/Game/S"},
    }
    return csir, mapping


def test_prop_relative_keys_are_resolved_against_infinite_offset() -> None:
    csir, mapping = _fixture()
    plan = csir_plan.build_plan(csir, mapping)
    action = next(
        item for item in plan["actions"] if item.get("track_name") == "MOVING_PROP_Movement"
    )

    assert action["keys"][0]["frame"] == 120
    assert action["keys"][0]["location_cm"] == (500.0, -200.0, 50.0)
    assert action["keys"][-1]["frame"] == 420
    assert action["keys"][-1]["location_cm"] == (500.0, 200.0, 50.0)


def test_camera_fov_and_cut_timing_are_preserved() -> None:
    csir, mapping = _fixture()
    plan = csir_plan.build_plan(csir, mapping)

    setup = next(item for item in plan["actions"] if item["kind"] == "camera_setup")
    fov = next(item for item in plan["actions"] if item["kind"] == "camera_fov")
    cut = next(item for item in plan["actions"] if item["kind"] == "camera_cut")

    assert setup["field_of_view_degrees"] == 35.0
    assert setup["source_fov_axis"] == "vertical"
    assert abs(setup["target_output_aspect"] - (16.0 / 9.0)) < 1e-9
    assert abs(setup["observed_source_aspect"] - 4.93486166) < 1e-9
    assert fov["source_fov_axis"] == "vertical"
    assert abs(fov["target_output_aspect"] - (16.0 / 9.0)) < 1e-9
    assert abs(fov["observed_source_aspect"] - 4.93486166) < 1e-9
    assert fov["keys"] == [{"frame": 300, "value": 35.0}, {"frame": 600, "value": 25.0}]
    assert cut["start_frame"] == 300
    assert cut["end_frame"] == 600


def test_event_at_six_point_five_seconds_becomes_frame_390() -> None:
    csir, mapping = _fixture()
    plan = csir_plan.build_plan(csir, mapping)
    marker = next(item for item in plan["actions"] if item["kind"] == "marker")

    assert marker["label"] == "Benchmark_Event_01"
    assert marker["frame"] == 390


def test_identity_rotation_maps_to_zero_unreal_rotator() -> None:
    roll, pitch, yaw = csir_plan.canonical_quat_to_unreal_rotator((0.0, 0.0, 0.0, 1.0))
    assert abs(roll) < 1e-9
    assert abs(pitch) < 1e-9
    assert abs(yaw) < 1e-9


def test_character_root_motion_and_final_pose_policy_are_planned() -> None:
    csir, mapping = _fixture()
    plan = csir_plan.build_plan(csir, mapping)
    action = next(item for item in plan["actions"] if item["kind"] == "skeletal_animation")

    assert action["completion_mode"] == "keep_state"
    assert action["completion_provenance"] == "legacy_csir_missing_post_extrapolation"
    assert action["hold_end_frame"] == 600
    assert action["hold_strategy"] == "post_roll_last_frame"
    assert action["source_start_seconds"] == 0.0
    assert action["source_end_seconds"] == 3.25
    assert action["expected_root_delta_cm"] == [-150.0, 10.0, 0.0]
    assert action["root_motion_source_profile"]["horizontal_end_distance_cm"] > 100.0
    assert action["root_motion_source_profile"]["vertical_excursion_cm"] >= 0.0
    assert action["root_motion_source_profile"]["sample_count"] >= 2.0


def test_root_motion_yaw_alignment_corrects_opposite_direction() -> None:
    yaw = csir_plan.root_motion_yaw_alignment_degrees(
        (-150.0, 0.0, 0.0),
        (150.0, 0.0, 0.0),
    )
    assert yaw is not None
    assert abs(abs(yaw) - 180.0) < 1e-9

    aligned = csir_plan.root_motion_yaw_alignment_degrees(
        (-150.0, 0.0, 0.0),
        (-150.0, 0.0, 0.0),
    )
    assert aligned == 0.0


def test_output_gate_does_not_reuse_live_unity_camera_aspect() -> None:
    csir, mapping = _fixture()
    plan = csir_plan.build_plan(csir, mapping)
    assert plan["output_resolution"] == [1920, 1080]
    assert abs(plan["output_aspect"] - (16.0 / 9.0)) < 1e-9
    assert plan["output_profile_source"] == "benchmark_default_1920x1080"
