"""Bounded skeletal joint angular-motion signatures at matched source frames.

Unity canonical and Unreal native world bone quaternions do NOT share a
calibrated retarget/bind orientation basis. Angular displacement *magnitude*
between consecutive samples (and from the first frame) is invariant under a
fixed orthonormal change of basis. Matching those magnitudes can detect
incorrect timing/amplitude but cannot establish absolute joint orientation or
axis equivalence. Never use this report as proof of full skeletal pose parity.
"""
from __future__ import annotations

import math
from typing import Any

DEFAULT_TOLERANCE_DEGREES = 2.0


class JointMotionEvidenceError(ValueError):
    pass


def _quaternion(raw: Any) -> tuple[float, float, float, float]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4 or any(
        isinstance(value, bool) for value in raw
    ):
        raise JointMotionEvidenceError("Joint rotation must be an observed quaternion.")
    try:
        result = tuple(float(value) for value in raw)
    except (ValueError, TypeError) as exc:
        raise JointMotionEvidenceError("Joint quaternion contains invalid values.") from exc
    length = math.sqrt(sum(value * value for value in result))
    if not math.isfinite(length) or abs(length - 1.0) > 0.01:
        raise JointMotionEvidenceError("Joint quaternion must be finite and approximately unit-length.")
    return tuple(value / length for value in result)  # type: ignore[return-value]


def _angle(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    cosine = min(1.0, abs(sum(a * b for a, b in zip(left, right))))
    return math.degrees(2.0 * math.acos(cosine))


def _bones(sample: dict[str, Any], rig_id: str, *, source: bool) -> dict[str, dict[str, Any]]:
    rows = [row for row in sample.get("skeletal_poses", []) if row.get("entity_id") == rig_id]
    if len(rows) != 1:
        raise JointMotionEvidenceError("Missing or duplicated pose for selected rig.")
    key = "bone_id" if source else "bone_name"
    observed = rows[0].get("bones")
    if not isinstance(observed, list):
        raise JointMotionEvidenceError("Missing native skeletal joint samples.")
    pairs = [row.get(key) for row in observed]
    if len(set(pairs)) != len(pairs) or any(
        not isinstance(name, str) or not name for name in pairs
    ):
        raise JointMotionEvidenceError("Missing or duplicate native skeletal joint identities.")
    return {row[key]: row for row in observed}


def compare_joint_angular_motion(
    source_samples: list[dict[str, Any]],
    target_samples: list[dict[str, Any]],
    rig_id: str,
    joints: dict[str, Any],
    *,
    tolerance_degrees: float = DEFAULT_TOLERANCE_DEGREES,
) -> dict[str, Any]:
    if (not isinstance(tolerance_degrees, (float, int))
            or isinstance(tolerance_degrees, bool) or not math.isfinite(tolerance_degrees)
            or tolerance_degrees <= 0):
        raise JointMotionEvidenceError("Angular motion tolerance must be finite and positive.")
    common = {
        "scope": "BASIS_INVARIANT_ANGULAR_DISPLACEMENT_MAGNITUDES_ONLY",
        "tolerance_degrees": float(tolerance_degrees),
        "absolute_joint_orientation_verified": False,
        "joint_rotation_axis_verified": False,
    }
    if not isinstance(source_samples, list) or len(source_samples) < 2 or len(source_samples) != len(target_samples):
        raise JointMotionEvidenceError("Joint angular evidence requires a complete matched source frame grid.")
    if joints.get("status") not in {"PASS", "FAIL"} or not joints.get("bones"):
        return {
            **common, "status": "INCOMPLETE",
            "reason": "UNVERIFIED_NATIVE_BONE_CORRESPONDENCE",
            "paired_bones": 0, "sample_count": 0,
        }
    mapped = joints["bones"]
    if (not isinstance(mapped, list) or len(mapped) > 4096 or any(
        not isinstance(row.get("source_bone_id"), str)
        or not isinstance(row.get("target_bone_name"), str) for row in mapped
    ) or len({row["source_bone_id"] for row in mapped}) != len(mapped)
            or len({row["target_bone_name"] for row in mapped}) != len(mapped)):
        raise JointMotionEvidenceError("Native skeletal bone correspondence is ambiguous.")
    observed = []
    for left, right in zip(source_samples, target_samples):
        src, tgt = _bones(left, rig_id, source=True), _bones(right, rig_id, source=False)
        if any(row["source_bone_id"] not in src or row["target_bone_name"] not in tgt for row in mapped):
            return {
                **common, "status": "INCOMPLETE",
                "reason": "MAPPED_NATIVE_JOINT_ORIENTATION_SAMPLE_MISSING",
                "paired_bones": len(mapped), "sample_count": len(observed),
            }
        observed.append({
            row["source_bone_id"]: (
                _quaternion(src[row["source_bone_id"]]["world_transform"]["rotation_xyzw"]),
                _quaternion(tgt[row["target_bone_name"]].get("unreal_world_rotation_xyzw")),
            ) for row in mapped
        })
    rows = []
    for row in mapped:
        source_id = row["source_bone_id"]
        source_start, target_start = observed[0][source_id]
        first_source, first_target = source_start, target_start
        maximum = 0.0
        worst = float(source_samples[0]["time_seconds"])
        maximum_change = 0.0
        for index, frame in enumerate(observed):
            current_source, current_target = frame[source_id]
            mismatch = max(
                abs(_angle(source_start, current_source) - _angle(target_start, current_target)),
                abs(_angle(first_source, current_source) - _angle(first_target, current_target)),
            )
            if mismatch > maximum:
                maximum, worst = mismatch, float(source_samples[index]["time_seconds"])
            maximum_change = max(maximum_change, _angle(first_source, current_source))
            first_source, first_target = current_source, current_target
        rows.append({
            "source_bone_id": source_id,
            "target_bone_name": row["target_bone_name"],
            "max_angular_motion_magnitude_error_degrees": round(maximum, 6),
            "worst_time_seconds": worst,
            "source_max_step_rotation_degrees": round(maximum_change, 6),
        })
    maximum = max(row["max_angular_motion_magnitude_error_degrees"] for row in rows)
    return {
        **common,
        "status": "PASS" if maximum <= tolerance_degrees else "FAIL",
        "paired_bones": len(mapped),
        "sample_count": len(observed),
        "max_angular_motion_magnitude_error_degrees": maximum,
        "per_bone": rows,
    }
