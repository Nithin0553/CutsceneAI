"""Frame-matched skeletal motion magnitude checks without asserting cross-rig axes."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))

from behavior_compare import compare
from joint_motion_profile import JointMotionEvidenceError, compare_joint_angular_motion
from test_behavior_compare import _fixtures


def _rotation(degrees, *, axis="z"):
    angle = math.radians(degrees / 2)
    value = math.sin(angle)
    return {
        "x": [value, 0, 0, math.cos(angle)],
        "y": [0, value, 0, math.cos(angle)],
        "z": [0, 0, value, math.cos(angle)],
    }[axis]


def _mapped():
    plan, source, target = _fixtures()
    target["skeletal_bone_maps"] = {"character": {"hips": "pelvis"}}
    return plan, source, target


def _set_rotation(source, target, *, source_angles, target_angles, target_axis="z"):
    for index, (left, right) in enumerate(zip(source["samples"], target["samples"])):
        left["skeletal_poses"][0]["bones"][0]["world_transform"][
            "rotation_xyzw"
        ] = _rotation(source_angles[index])
        right["skeletal_poses"][0]["bones"][0][
            "unreal_world_rotation_xyzw"
        ] = _rotation(target_angles[index], axis=target_axis)


def test_joint_motion_profile_matches_animated_frame_changes():
    plan, source, target = _mapped()
    moments = [0, 15, 30, 45, 60]
    _set_rotation(source, target, source_angles=moments, target_angles=moments)
    report = compare(plan, source, target)
    profile = report["rig_motion_diagnostics"][0]["joint_angular_motion"]
    assert profile["status"] == "PASS"
    assert profile["paired_bones"] == 1
    assert profile["sample_count"] == len(plan["samples"])
    assert profile["max_angular_motion_magnitude_error_degrees"] == pytest.approx(0)
    assert profile["absolute_joint_orientation_verified"] is False
    assert profile["joint_rotation_axis_verified"] is False
    assert report["evaluation"]["overall_cutscene_fidelity"] == "NOT_ESTABLISHED"


def test_wrong_joint_rotation_amplitude_is_detected_on_exact_source_frame():
    plan, source, target = _mapped()
    angles = [0, 15, 30, 45, 60]
    changed = [0, 15, 65, 45, 60]
    _set_rotation(source, target, source_angles=angles, target_angles=changed)
    report = compare(plan, source, target)
    profile = report["rig_motion_diagnostics"][0]["joint_angular_motion"]
    assert profile["status"] == "FAIL"
    assert profile["max_angular_motion_magnitude_error_degrees"] >= 30
    assert report["evaluation"]["status"] == "DIFFERENCES_DETECTED"
    assert "SKELETAL_JOINT_ANGULAR_MOTION_PROFILE_MISMATCH" in report[
        "rig_motion_diagnostics"
    ][0]["flags"]


def test_same_angular_magnitude_about_wrong_axis_is_not_certified_as_orientation():
    plan, source, target = _mapped()
    angles = [0, 15, 30, 45, 60]
    _set_rotation(
        source, target, source_angles=angles, target_angles=angles, target_axis="x",
    )
    profile = compare(plan, source, target)["rig_motion_diagnostics"][0][
        "joint_angular_motion"
    ]
    assert profile["status"] == "PASS"
    assert profile["scope"] == "BASIS_INVARIANT_ANGULAR_DISPLACEMENT_MAGNITUDES_ONLY"
    assert not profile["joint_rotation_axis_verified"]
    assert not profile["absolute_joint_orientation_verified"]


def test_unmapped_bones_do_not_get_movement_pass():
    plan, source, target = _fixtures()
    profile = compare(plan, source, target)["rig_motion_diagnostics"][0][
        "joint_angular_motion"
    ]
    assert profile["status"] == "INCOMPLETE"
    assert profile["reason"] == "UNVERIFIED_NATIVE_BONE_CORRESPONDENCE"


@pytest.mark.parametrize("mutation", ["invalid_quat", "nonfinite", "missing_native", "duplicate_native"])
def test_invalid_native_joint_evidence_never_passes(mutation):
    plan, source, target = _mapped()
    frame = target["samples"][2]["skeletal_poses"][0]
    if mutation == "invalid_quat":
        frame["bones"][0]["unreal_world_rotation_xyzw"] = [0, 0, 0, 0]
    elif mutation == "nonfinite":
        frame["bones"][0]["unreal_world_rotation_xyzw"] = [float("nan"), 0, 0, 1]
    elif mutation == "missing_native":
        frame["bones"][0].pop("unreal_world_rotation_xyzw")
    else:
        frame["bones"].append(dict(frame["bones"][0]))
    with pytest.raises((JointMotionEvidenceError, ValueError, KeyError)):
        compare(plan, source, target)


def test_missing_matched_joint_returns_incomplete_without_false_positive():
    _plan, source, target = _mapped()
    joint_record = {"status": "PASS", "bones": [
        {"source_bone_id": "hips", "target_bone_name": "unknown"},
    ]}
    profile = compare_joint_angular_motion(
        source["samples"], target["samples"], "character", joint_record
    )
    assert profile["status"] == "INCOMPLETE"
    assert profile["reason"] == "MAPPED_NATIVE_JOINT_ORIENTATION_SAMPLE_MISSING"
