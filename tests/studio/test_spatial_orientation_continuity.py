"""Spatial regression: native facing should not spin across a pitch pole.

All observations are synthetic and source-bound. These tests do not execute
Unreal/Unity APIs or claim engine playback fidelity.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in (ROOT / "integrations/unreal", ROOT / "packages/studio"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import csir_plan
import readback_math
import character_motion
import hierarchy_local
import transfer_backend


RATE = {"numerator": 30, "denominator": 1}


def _time(frame):
    return {"value": frame, "rate": RATE}


def _csir(frames=3):
    return {"timing": {
        "source_rate": RATE, "display_rate": RATE,
        "playback_start": _time(0), "playback_end": _time(frames),
        "duration_seconds": frames / 30,
    }}


def _q(pitch):
    # Unity +X pitch points downward, use negative to pitch up in Unreal.
    return list(csir_plan.unity_euler_delta_to_canonical_quat(-pitch, 0.0, 0.0))


def _pose(pitch, position=(0.0, 0.0, -2.0)):
    return {
        "position_m": list(position),
        "rotation_xyzw": _q(pitch),
        "scale_xyz": [1.0, 1.0, 1.0],
    }


def _capture(pitches, *, parent=False):
    samples = []
    for frame, pitch in enumerate(pitches):
        entities = [{"entity_id": "character", "world_transform": _pose(pitch)}]
        if parent:
            entities.append({
                "entity_id": "parent", "world_transform": _pose(0, (0, 0, 0)),
            })
        samples.append({"time_seconds": frame / 30, "entities": entities})
    return {"samples": samples}


def _rotation_distance(q1, q2):
    dot = abs(sum(float(a) * float(b) for a, b in zip(q1, q2)))
    dot = max(0.0, min(1.0, dot))
    return math.degrees(2 * math.acos(dot))


def _check_continuity(keys):
    # The 89 -> 91 degree source motion must not become a false 180-degree
    # roll/yaw spin at the midpoint between native Sequencer keys.
    first, second = [row["rotation_rpy_degrees"] for row in keys[:2]]
    assert max(abs(a - b) for a, b in zip(first, second)) < 5.0
    midpoint = [(a + b) * 0.5 for a, b in zip(first, second)]
    target = readback_math.unreal_rpy_to_canonical_quat(*midpoint)
    assert _rotation_distance(target, _q(90.0)) < 0.01
    for row in keys:
        frame = row["frame"]
        expected = _q(89.0 + frame * 2.0)
        reconstructed = readback_math.unreal_rpy_to_canonical_quat(
            *row["rotation_rpy_degrees"]
        )
        assert _rotation_distance(expected, reconstructed) < 1e-4


def test_quaternion_equivalent_euler_keys_cross_pitch_pole_continuously():
    raw = [csir_plan.canonical_quat_to_unreal_rotator(_q(angle))
           for angle in (89.0, 91.0, 93.0)]
    assert abs(raw[0][0] - raw[1][0]) > 170.0
    result = []
    for value in raw:
        result.append(csir_plan.continuous_unreal_rotator(
            result[-1] if result else None, value
        ))
    _check_continuity([{"frame": i, "rotation_rpy_degrees": rpy}
                       for i, rpy in enumerate(result)])


def test_world_bake_preserves_continuous_character_facing():
    source = _csir()
    character = {"entity_id": "character", "name": "Guard"}
    keys = transfer_backend._world_keys(source, _capture([89.0, 91.0, 93.0]), character)
    assert [row["frame"] for row in keys] == [0, 1, 2]
    assert keys[0]["location_cm"] == [200.0, 0.0, 0.0]
    _check_continuity(keys)


def test_moving_actor_trajectory_preserves_continuous_facing():
    # Actor-owned moving-character action also writes the observed end key.
    source = _csir(2)
    captured = _capture([89.0, 91.0, 93.0])
    trajectory = character_motion.trajectory(source, captured, "character")
    assert trajectory["duration_frames"] == 2
    _check_continuity(trajectory["keys"])


def test_parented_child_local_facing_preserves_pitch_continuity():
    source = _csir()
    captured = _capture([89.0, 91.0, 93.0], parent=True)
    action = hierarchy_local.bake_parent_local(
        source, captured, child_id="character", parent_id="parent",
        child_name="Guard", actor_label="Guard_Target",
    )
    assert action["transform_space"] == "PARENT_LOCAL"
    _check_continuity(action["keys"])


@pytest.mark.parametrize("invalid", [
    [0.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 0.0, 2.0],
    [0.0, float("nan"), 0.0, 1.0],
    [float("inf"), 0.0, 0.0, 1.0],
])
def test_invalid_source_facing_refuses_instead_of_generating_identity(invalid):
    with pytest.raises(csir_plan.PlanError, match="quaternion"):
        csir_plan.canonical_quat_to_unreal_rotator(invalid)
    source = _csir(1)
    capture = _capture([89.0])
    capture["samples"][0]["entities"][0]["world_transform"]["rotation_xyzw"] = invalid
    # The baked-actor layer can refuse nonfinite samples before the planner
    # gets to its separate unit-quaternion guard; both are safe refusals.
    with pytest.raises((csir_plan.PlanError, transfer_backend.TransferBackendError),
                       match="quaternion|Non-finite"):
        transfer_backend._world_keys(source, capture, {"entity_id": "character", "name": "Guard"})


def test_ambiguous_actor_pose_or_capture_timestamp_refuses_spatial_bake():
    source = _csir(1)
    character = {"entity_id": "character", "name": "Guard"}
    captured = _capture([89.0])
    captured["samples"].append(dict(captured["samples"][0]))
    with pytest.raises(transfer_backend.TransferBackendError, match="timestamp"):
        transfer_backend._world_keys(source, captured, character)
    captured = _capture([89.0])
    captured["samples"][0]["entities"].append(dict(captured["samples"][0]["entities"][0]))
    with pytest.raises(transfer_backend.TransferBackendError, match="ambiguous"):
        transfer_backend._world_keys(source, captured, character)


def test_quaternion_sign_does_not_change_facing():
    q = _q(47.0)
    pos = csir_plan.canonical_quat_to_unreal_rotator(q)
    neg = csir_plan.canonical_quat_to_unreal_rotator([-v for v in q])
    assert _rotation_distance(readback_math.unreal_rpy_to_canonical_quat(*pos),
                              readback_math.unreal_rpy_to_canonical_quat(*neg)) < 0.0001
