import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNREAL_INTEGRATION = ROOT / "integrations" / "unreal"
sys.path.insert(0, str(UNREAL_INTEGRATION))

import scene_prep


def _curve(semantic: str, value: float) -> dict:
    return {
        "canonical_semantic": semantic,
        "keys": [{"time_seconds": 0.0, "value": value}],
    }


def test_static_environment_world_transform_maps_to_unreal_axes() -> None:
    csir = {
        "entities": [
            {
                "entity_id": "floor",
                "ced_type": "entity.prop",
                "name": "Floor",
                "metadata": {
                    "world_transform": {
                        "position": {"x": 0.0, "y": -0.1, "z": -5.0},
                        "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                        "scale": {"x": 8.0, "y": 0.2, "z": 12.0},
                    }
                },
            }
        ],
        "tracks": [],
    }
    mapping = {"entities": {"Floor": {"actor_label": "Floor"}}}

    operations = scene_prep.build_scene_prep(csir, mapping)

    assert len(operations) == 1
    assert operations[0]["location_cm"] == (500.0, 0.0, -10.0)
    assert operations[0]["scale_xyz"] == (12.0, 8.0, 0.2)


def test_character_uses_animation_playable_clip_offset_not_preview_transform() -> None:
    curves = [
        _curve("transform.track_offset.position.x", 0.0),
        _curve("transform.track_offset.position.y", 0.0),
        _curve("transform.track_offset.position.z", 0.0),
        _curve("transform.track_offset.rotation.x", 0.0),
        _curve("transform.track_offset.rotation.y", 0.0),
        _curve("transform.track_offset.rotation.z", 0.0),
        _curve("transform.track_offset.rotation.w", 1.0),
        _curve("transform.clip_offset.position.x", 0.0),
        _curve("transform.clip_offset.position.y", 0.0),
        _curve("transform.clip_offset.position.z", -7.0),
        _curve("transform.clip_offset.rotation.x", 0.0),
        _curve("transform.clip_offset.rotation.y", 0.0),
        _curve("transform.clip_offset.rotation.z", 0.0),
        _curve("transform.clip_offset.rotation.w", 1.0),
    ]
    csir = {
        "entities": [
            {
                "entity_id": "guard",
                "ced_type": "entity.character",
                "name": "CHARACTER_Guard",
                "metadata": {
                    "world_transform": {
                        "position": {"x": 99.0, "y": 99.0, "z": 99.0},
                        "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                        "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                    }
                },
            }
        ],
        "tracks": [
            {
                "ced_type": "animation.track",
                "binding_entity_id": "guard",
                "sections": [{"payload": {"animation": {"curves": curves}}}],
            }
        ],
    }
    mapping = {"entities": {"CHARACTER_Guard": {"actor_label": "CHARACTER_Guard"}}}

    operations = scene_prep.build_scene_prep(csir, mapping)

    assert len(operations) == 1
    assert operations[0]["source"] == "animation_clip_offset"
    assert operations[0]["location_cm"] == (700.0, 0.0, 0.0)


def test_static_unity_camera_pitch_remains_unreal_pitch_not_roll() -> None:
    csir = {
        "entities": [
            {
                "entity_id": "cam-a",
                "ced_type": "entity.camera",
                "name": "CAM_A_Wide",
                "metadata": {
                    "world_transform": {
                        "position": {"x": 0.0, "y": 2.6, "z": 0.8},
                        "rotation": {
                            "x": -0.2164396047592163,
                            "y": 0.0,
                            "z": 0.0,
                            "w": 0.976296067237854,
                        },
                        "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                    }
                },
            }
        ],
        "tracks": [],
    }
    mapping = {"entities": {"CAM_A_Wide": {"actor_label": "CAM_A_Wide"}}}

    operation = scene_prep.build_scene_prep(csir, mapping)[0]
    pitch, yaw, roll = operation["rotation_pitch_yaw_roll_degrees"]

    assert abs(pitch - 25.0) < 1e-4
    assert abs(yaw) < 1e-6
    assert abs(roll) < 1e-6
