from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
UNREAL_INTEGRATION = REPO_ROOT / "integrations" / "unreal"
sys.path.insert(0, str(UNREAL_INTEGRATION))

from cutsceneai_unreal.planner import PlanError, build_transfer_plan  # noqa: E402


CUTSCENE_ID = "unity:benchmark:11400000"
CHARACTER_ID = "entity:character"
PROP_ID = "entity:prop"
CAM_A_ID = "entity:cam-a"
CAM_B_ID = "entity:cam-b"
AUDIO_ID = "entity:audio"


def _time(seconds: float) -> dict[str, object]:
    return {
        "value": int(round(seconds * 1_000_000)),
        "rate": {"numerator": 1_000_000, "denominator": 1},
    }


def _curve(
    property_name: str,
    semantic: str,
    keys: list[tuple[float, float]],
) -> dict[str, object]:
    return {
        "path": "",
        "component_type": "UnityEngine.Transform",
        "property_name": property_name,
        "canonical_semantic": semantic,
        "conversion": "identity",
        "keys": [
            {
                "time_seconds": time,
                "value": value,
                "in_tangent": 0.0,
                "out_tangent": 0.0,
                "in_weight": 1 / 3,
                "out_weight": 1 / 3,
                "weighted_mode": 0,
            }
            for time, value in keys
        ],
        "native_keys": [],
    }


def _entity(
    entity_id: str,
    name: str,
    ced_type: str,
    native_ref: str,
    *,
    position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    controller_ref: str = "",
) -> dict[str, object]:
    return {
        "entity_id": entity_id,
        "name": name,
        "ced_type": ced_type,
        "native_ref": native_ref,
        "metadata": {
            "local_transform": {
                "position": {"x": position[0], "y": position[1], "z": position[2]},
                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
            },
            "animator": {"controller_ref": controller_ref},
        },
    }


def _section(
    section_id: str,
    ced_type: str,
    start: float,
    end: float,
    *,
    asset_id: str = "",
    curves: list[dict[str, object]] | None = None,
    signal_asset_id: str = "",
) -> dict[str, object]:
    return {
        "section_id": section_id,
        "ced_type": ced_type,
        "start": _time(start),
        "end": _time(end),
        "source_offset": _time(0.0),
        "time_scale": 1.0,
        "loop": False,
        "payload": {
            "display_name": section_id,
            "asset_id": asset_id,
            "animation": {
                "apply_foot_ik": True,
                "curves": curves or [],
                "object_reference_curves": [],
            },
            "audio": {},
            "activation": {},
            "signal": {
                "signal_asset_id": signal_asset_id,
                "emit_once": True,
                "retroactive": False,
            },
            "generic": {},
        },
        "native_payload": {},
    }


def _track(
    track_id: str,
    ced_type: str,
    name: str,
    binding_entity_id: str,
    sections: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "track_id": track_id,
        "ced_type": ced_type,
        "name": name,
        "binding_entity_id": binding_entity_id,
        "muted": False,
        "sections": sections,
        "metadata": {},
    }


def _csir() -> dict[str, object]:
    prop_curves = [
        _curve("m_LocalPosition.x", "transform.position.x", [(2.0, 0.0), (7.0, 4.0)]),
        _curve("m_LocalPosition.y", "transform.position.y", [(2.0, 0.0), (7.0, 0.0)]),
        _curve("m_LocalPosition.z", "transform.position.z", [(2.0, 0.0), (7.0, 0.0)]),
    ]
    camera_curves = [
        _curve(
            "localEulerAnglesRaw.x",
            "transform.rotation.euler_native",
            [(5.0, 0.0), (9.983333, 0.0)],
        ),
        _curve(
            "localEulerAnglesRaw.y",
            "transform.rotation.euler_native",
            [(5.0, 0.0), (9.983333, 0.0)],
        ),
        _curve(
            "localEulerAnglesRaw.z",
            "transform.rotation.euler_native",
            [(5.0, 0.0), (9.983333, 5.0)],
        ),
        {
            **_curve("field of view", "", [(5.0, 35.0), (9.983333, 25.0)]),
            "component_type": "UnityEngine.Camera",
        },
    ]

    return {
        "schema_version": "0.1.0",
        "cutscene_id": CUTSCENE_ID,
        "source": {"engine": "unity", "engine_version": "6000.3.8f1"},
        "timing": {
            "source_rate": {"numerator": 60, "denominator": 1},
            "display_rate": {"numerator": 60, "denominator": 1},
            "tick_resolution": {"numerator": 1_000_000, "denominator": 1},
            "playback_start": _time(0.0),
            "playback_end": _time(10.0),
            "duration_seconds": 10.0,
        },
        "assets": [
            {"asset_id": "a_anim", "name": "mixamo.com", "ced_type": "animation.clip"},
            {"asset_id": "a_audio", "name": "ominous", "ced_type": "audio.asset"},
            {"asset_id": "a_signal", "name": "Benchmark_Event_01", "ced_type": "event.trigger"},
        ],
        "entities": [
            _entity(CHARACTER_ID, "CHARACTER_Guard", "entity.character", "go:character"),
            _entity(PROP_ID, "MOVING_PROP", "entity.prop", "go:prop"),
            _entity(CAM_A_ID, "CAM_A_Wide", "entity.camera", "go:cam-a", position=(0, 2.6, 0.8)),
            _entity(CAM_B_ID, "CAM_B_Close", "entity.camera", "go:cam-b"),
            _entity(AUDIO_ID, "AUDIO_SOURCE", "entity.audio_source", "go:audio"),
        ],
        "tracks": [
            _track(
                "t_char",
                "animation.track",
                "CHARACTER_Animation",
                CHARACTER_ID,
                [_section("s_char", "animation.section", 0.0, 3.25, asset_id="a_anim")],
            ),
            _track(
                "t_prop",
                "animation.track",
                "MOVING_PROP_Movement",
                PROP_ID,
                [_section("s_prop", "animation.section", 0.0, 7.0, curves=prop_curves)],
            ),
            _track(
                "t_cam_a_cut",
                "camera.cut",
                "CAM_A_Cut",
                CAM_A_ID,
                [_section("s_cam_a_cut", "camera.cut", 0.0, 5.0)],
            ),
            _track(
                "t_cam_b_cut",
                "camera.cut",
                "CAM_B_Cut",
                CAM_B_ID,
                [_section("s_cam_b_cut", "camera.cut", 5.0, 10.0)],
            ),
            _track(
                "t_cam_b",
                "camera.transform",
                "CAM_B_Animation",
                CAM_B_ID,
                [_section("s_cam_b", "camera.transform", 0.0, 9.983333, curves=camera_curves)],
            ),
            _track(
                "t_audio",
                "audio.track",
                "AUDIO_Main",
                AUDIO_ID,
                [_section("s_audio", "audio.section", 4.958367, 10.0, asset_id="a_audio")],
            ),
            _track(
                "t_event",
                "event.trigger",
                "EVENT_Main",
                "",
                [
                    _section(
                        "s_event",
                        "event.trigger",
                        6.5,
                        6.5,
                        signal_asset_id="a_signal",
                    )
                ],
            ),
        ],
        "relationships": [],
        "provenance": {},
    }


def _source_track(
    track_id: str,
    binding: str,
    *,
    in_clip_mode: bool,
    track_position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    infinite_position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    clip_position: tuple[float, float, float] | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "track_id": track_id,
        "binding_global_object_id": binding,
        "binding_name": binding,
        "in_clip_mode": in_clip_mode,
        "track_offset_mode": "ApplyTransformOffsets",
        "track_position": {
            "x": track_position[0],
            "y": track_position[1],
            "z": track_position[2],
        },
        "track_rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        "infinite_clip_offset_position": {
            "x": infinite_position[0],
            "y": infinite_position[1],
            "z": infinite_position[2],
        },
        "infinite_clip_offset_rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        "clips": [],
        "infinite_clip_asset_id": "recorded" if not in_clip_mode else "",
    }
    if clip_position is not None:
        result["clips"] = [
            {
                "clip_offset_position": {
                    "x": clip_position[0],
                    "y": clip_position[1],
                    "z": clip_position[2],
                },
                "clip_offset_rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
            }
        ]
    return result


def _unity_source() -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "cutscene_id": CUTSCENE_ID,
        "engine": "unity",
        "exporter_version": "0.1.0",
        "animation_tracks": [
            _source_track(
                "t_char",
                "go:character",
                in_clip_mode=True,
                clip_position=(0.0, 0.0, -7.0),
            ),
            _source_track(
                "t_prop",
                "go:prop",
                in_clip_mode=False,
                track_position=(-2.0, 0.5, -5.0),
            ),
            _source_track(
                "t_cam_b",
                "go:cam-b",
                in_clip_mode=False,
                track_position=(4.0, 1.2, -3.0),
            ),
        ],
    }


def _mapping() -> dict[str, object]:
    return {
        "target": {
            "engine": "unreal",
            "sequence_name": "Benchmark001_Transferred_Staging",
            "sequence_path": "/Game/CutSceneAI/Benchmark001",
            "level_path": "/Game/Benchmark001/Maps/Benchmark001",
        },
        "entities": {
            "CHARACTER_Guard": {
                "kind": "skeletal_mesh",
                "skeletal_mesh": "/Game/Benchmark001/Characters/Ch31",
            },
            "MOVING_PROP": {
                "kind": "static_mesh",
                "static_mesh": "/Engine/BasicShapes/Cube.Cube",
            },
            "CAM_A_Wide": {"kind": "camera"},
            "CAM_B_Close": {"kind": "camera"},
        },
        "assets": {
            "mixamo.com": {"kind": "animation", "path": "/Game/Benchmark001/Animations/Catwalk"},
            "ominous": {"kind": "audio", "path": "/Game/Benchmark001/Audio/Ominous"},
        },
    }


def _operation(plan: dict[str, object], operation_type: str) -> dict[str, object]:
    operations = plan["operations"]
    assert isinstance(operations, list)
    return next(operation for operation in operations if operation["type"] == operation_type)


def _operations(plan: dict[str, object], operation_type: str) -> list[dict[str, object]]:
    operations = plan["operations"]
    assert isinstance(operations, list)
    return [operation for operation in operations if operation["type"] == operation_type]


def test_benchmark001_plan_preserves_timing_offsets_and_coordinate_conversion() -> None:
    plan = build_transfer_plan(_csir(), _unity_source(), _mapping())

    target = plan["target"]
    assert target["display_rate"] == {"numerator": 60, "denominator": 1}
    assert target["tick_resolution"] == {"numerator": 1_000_000, "denominator": 1}
    assert target["playback_end_tick"] == 10_000_000

    bindings = {item["source_name"]: item for item in plan["bindings"]}
    character_location = bindings["CHARACTER_Guard"]["initial_transform"]["location_cm"]
    assert character_location == pytest.approx({"x": 700.0, "y": 0.0, "z": 0.0})

    prop_location = bindings["MOVING_PROP"]["initial_transform"]["location_cm"]
    assert prop_location == pytest.approx({"x": 500.0, "y": -200.0, "z": 50.0})

    prop_transform = next(
        operation
        for operation in _operations(plan, "transform_animation")
        if operation["binding_entity_id"] == PROP_ID
    )
    assert prop_transform["location_keys"][0]["tick"] == 2_000_000
    assert prop_transform["location_keys"][0]["location_cm"] == pytest.approx(
        {"x": 500.0, "y": -200.0, "z": 50.0}
    )
    assert prop_transform["location_keys"][-1]["tick"] == 7_000_000
    assert prop_transform["location_keys"][-1]["location_cm"] == pytest.approx(
        {"x": 500.0, "y": 200.0, "z": 50.0}
    )

    cuts = _operations(plan, "camera_cut")
    assert [(item["start_tick"], item["end_tick"]) for item in cuts] == [
        (0, 5_000_000),
        (5_000_000, 10_000_000),
    ]

    fov = _operation(plan, "camera_fov")
    assert [(item["tick"], item["value"]) for item in fov["keys"]] == [
        (5_000_000, 35.0),
        (9_983_333, 25.0),
    ]

    audio = _operation(plan, "audio")
    assert audio["start_tick"] == 4_958_367
    assert audio["end_tick"] == 10_000_000

    marker = _operation(plan, "marker")
    assert marker["label"] == "Benchmark_Event_01"
    assert marker["tick"] == 6_500_000

    character_animation = _operation(plan, "skeletal_animation")
    assert character_animation["start_tick"] == 0
    assert character_animation["end_tick"] == 3_250_000
    assert character_animation["target_asset_path"] == "/Game/Benchmark001/Animations/Catwalk"


def test_mismatched_unity_source_snapshot_is_rejected() -> None:
    source = _unity_source()
    source["cutscene_id"] = "unity:different:11400000"

    with pytest.raises(PlanError, match="different cutscenes"):
        build_transfer_plan(_csir(), source, _mapping())
