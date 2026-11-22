"""Phase 10.2: approved joint orientation cannot use duplicated frame data.

Native and source calibration evidence in this suite is synthetic only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "packages" / "cinetwin") not in sys.path:
    sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))

from rig_pose_calibration import RigCalibrationError, compare_reference_calibrated


def _fixture(times):
    source = []
    target = []
    for time in times:
        source.append({
            "time_seconds": time,
            "skeletal_poses": [{
                "entity_id": "guard",
                "bones": [{
                    "bone_id": "root",
                    "world_transform": {"rotation_xyzw": [0, 0, 0, 1]},
                }],
            }],
        })
        target.append({
            "time_seconds": time,
            "skeletal_poses": [{
                "entity_id": "guard",
                "bones": [{
                    "bone_name": "Root",
                    "unreal_world_rotation_xyzw": [0, 0, 0, 1],
                }],
            }],
        })
    reference = {
        "root": {
            "source_world_rotation_xyzw": [0, 0, 0, 1],
            "target_unreal_world_rotation_xyzw": [0, 0, 0, 1],
            "axis_alignment_xyzw": [0, 0, 0, 1],
        },
    }
    return source, target, {"root": "Root"}, reference


def test_complete_independent_calibration_grid_passes_measured_delta_scope():
    source, target, mapping, reference = _fixture([0, 1 / 30, 2 / 30])
    result = compare_reference_calibrated(
        source, target, "guard", mapping, reference,
    )
    assert result["status"] == "PASS"
    assert result["sample_count"] == 3
    assert result["max_orientation_delta_error_degrees"] == 0


@pytest.mark.parametrize("times", [
    [0.0, 0.0, 2 / 30],
    [0.0, 2 / 30, 1 / 30],
    [0.0, float("nan"), 2 / 30],
])
def test_repeated_reversed_and_nan_calibrated_times_are_never_a_pass(times):
    source, target, mapping, reference = _fixture(times)
    with pytest.raises(RigCalibrationError, match="strictly increasing"):
        compare_reference_calibrated(source, target, "guard", mapping, reference)


def test_wrong_time_or_bone_identity_remains_incomplete():
    source, target, mapping, reference = _fixture([0, 1 / 30])
    target[1]["time_seconds"] += 0.005
    with pytest.raises(RigCalibrationError, match="matched"):
        compare_reference_calibrated(source, target, "guard", mapping, reference)
    target[1]["time_seconds"] = 1 / 30
    target[1]["skeletal_poses"][0]["bones"][0]["bone_name"] = "Unknown"
    with pytest.raises(RigCalibrationError, match="incomplete"):
        compare_reference_calibrated(source, target, "guard", mapping, reference)
