"""Fail-closed source-baked camera motion contract before native mutation.

Camera transformations are compiled from original Unity-authored curves to
every display-rate frame. This verifier is PURE Python and is called before
the Unreal builder touches actors or assets. It is NOT a rendered fidelity
measurement, and cannot authorize an AI-originated native repair.
"""
from __future__ import annotations

import math
from typing import Any

STRATEGY = "source_frame_baked_camera_transform_v1"
MAX_KEYS = 100_001
MAX_ANGLE_STEP_DEGREES = 150.0


class CameraMotionContractError(ValueError):
    """Source-bound camera key grid cannot be safely realized in Sequencer."""


def _finite_triplet(row: Any, label: str, *, magnitude: float) -> tuple[float, float, float]:
    if (not isinstance(row, (tuple, list)) or len(row) != 3
            or any(type(x) not in (float, int)
                   or not math.isfinite(x) or abs(x) > magnitude for x in row)):
        raise CameraMotionContractError(
            "Animated camera " + label + " must have three bounded finite axes."
        )
    return tuple(float(x) for x in row)


def _rotation_forward(rpy: tuple[float, ...]) -> tuple[float, float, float]:
    _roll, pitch, yaw = (math.radians(v) for v in rpy)
    return (math.cos(pitch)*math.cos(yaw),
            math.cos(pitch)*math.sin(yaw), math.sin(pitch))


def _orientation_delta(a: tuple[float,...], b: tuple[float,...]) -> float:
    # Relative rotation angle from native Unreal Roll/Pitch/Yaw matrices:
    # using both the camera forward and right/up avoids ignoring barrel roll.
    def matrix(rpy: tuple[float, ...]) -> tuple[tuple[float, ...], ...]:
        roll, pitch, yaw = (math.radians(v) for v in rpy)
        cr,sr=math.cos(roll),math.sin(roll)
        cp,sp=math.cos(pitch),math.sin(pitch)
        cy,sy=math.cos(yaw),math.sin(yaw)
        return (
            (cp*cy, -sy*cr-sp*cy*sr, sy*sr-sp*cy*cr),
            (cp*sy, cy*cr-sp*sy*sr, -cy*sr-sp*sy*cr),
            (sp, cp*sr, cp*cr),
        )
    x, y = matrix(a), matrix(b)
    trace = sum(x[r][c]*y[r][c] for r in range(3) for c in range(3))
    return math.degrees(math.acos(max(-1., min(1., (trace-1.)/2.))))


def validate_action(action: dict[str, Any], *, duration_frames: int) -> dict[str, Any]:
    """Check one actual compiled camera source action, never a model proposal."""
    if (not isinstance(action, dict)
            or action.get("kind") != "transform"
            or action.get("source_behavior_strategy") != STRATEGY
            or action.get("baked_source_curves") is not True
            or action.get("native_transform_channels_required") != 9
            or not isinstance(action.get("entity_name"), str)
            or not action.get("entity_name")
            or not isinstance(action.get("actor_label"), str)
            or not action.get("actor_label")
            or type(duration_frames) is not int
            or not 1 <= duration_frames <= 100_000):
        raise CameraMotionContractError(
            "Animated camera action is not a source-authored nine-channel bake."
        )
    keys = action.get("keys")
    start = action.get("frame_grid_first")
    end = action.get("frame_grid_last")
    count = action.get("frame_grid_sample_count")
    if (not isinstance(keys, list)
            or not 2 <= len(keys) <= MAX_KEYS
            or any(type(x) is not int for x in (start,end,count))
            or start < 0 or start >= end or end > duration_frames
            or count != len(keys) or end-start+1 != count):
        raise CameraMotionContractError(
            "Animated camera source display-frame coverage has gaps or invalid bounds."
        )
    previous_rotation = None
    for frame, sample in enumerate(keys, start=start):
        if (not isinstance(sample, dict)
                or type(sample.get("frame")) is not int
                or sample["frame"] != frame):
            raise CameraMotionContractError(
                "Native camera frame indices are duplicated, missing or reordered."
            )
        location = _finite_triplet(
            sample.get("location_cm"), "world location", magnitude=10_000_000,
        )
        rotation = _finite_triplet(
            sample.get("rotation_rpy_degrees"), "world rotation", magnitude=100_000,
        )
        if previous_rotation is not None and (
                _orientation_delta(previous_rotation, rotation)
                > MAX_ANGLE_STEP_DEGREES):
            raise CameraMotionContractError(
                "Camera rotation exceeds reliable per-frame interpolation coverage."
            )
        previous_rotation = rotation
        if any(abs(v) > 10_000_000 for v in location):
            raise CameraMotionContractError("Camera world position is unbounded.")
    return {
        "kind": "cutsceneai.studio.camera_motion_preflight",
        "strategy": STRATEGY,
        "status": "SOURCE_GRID_VALIDATED_NATIVE_UNVERIFIED",
        "sample_count": count,
        "source_frame_first": start,
        "source_frame_last": end,
        "camera_motion_reopened_verified": False,
        "rendered_shot_fidelity_verified": False,
    }


def validate_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(plan, dict) or not isinstance(plan.get("actions"), list):
        raise CameraMotionContractError("Original prepared source action plan is missing.")
    duration = plan.get("duration_frames")
    checked = []
    actors = set()
    for action in plan["actions"]:
        if not isinstance(action, dict):
            raise CameraMotionContractError("Prepared native action is malformed.")
        if action.get("source_behavior_strategy") == STRATEGY:
            identity = action.get("entity_name")
            if identity in actors:
                raise CameraMotionContractError(
                    "Multiple prepared camera transform actions own one native actor."
                )
            actors.add(identity)
            checked.append(validate_action(action,duration_frames=duration))
    return checked
