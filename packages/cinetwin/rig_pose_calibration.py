"""Reference-bound cross-engine joint-orientation comparison.

This is a *verification* gate, not an IK solver or an automatic offset guess.
A reviewed per-bone native reference pose and explicitly approved local axis
alignment are required. No source/target first animation frame is silently
treated as bind pose.
"""
from __future__ import annotations

import math
from typing import Any


class RigCalibrationError(ValueError):
    """Unverifiable reference pose or orientation sample."""


def _quat(values: Any, label: str) -> tuple[float, float, float, float]:
    if not isinstance(values, (tuple, list)) or len(values) != 4:
        raise RigCalibrationError(f"{label}: expected four quaternion components.")
    try:
        q = tuple(float(x) for x in values)
    except (TypeError, ValueError) as error:
        raise RigCalibrationError(f"{label}: nonnumeric quaternion.") from error
    if not all(math.isfinite(v) for v in q):
        raise RigCalibrationError(f"{label}: nonfinite quaternion.")
    length = math.sqrt(sum(v * v for v in q))
    if abs(length - 1.0) > 0.01:
        raise RigCalibrationError(f"{label}: quaternion must be unit length.")
    return tuple(v / length for v in q)


def _mul(a, b):
    x, y, z, w = a
    u, v, t, r = b
    return (w*u+x*r+y*t-z*v, w*v-x*t+y*r+z*u,
            w*t+x*v-y*u+z*r, w*r-x*u-y*v-z*t)


def _inverse(q):
    x, y, z, w = q
    return (-x, -y, -z, w)


def _angle(a, b) -> float:
    dot = min(1.0, abs(sum(v * u for v, u in zip(a, b))))
    return math.degrees(2.0 * math.acos(dot))


def unreal_to_canonical_quat(unreal_quat):
    """Reflect Unreal's native quaternion into the shared CSIR world basis.

    Canonical position (x,y,z) -> Unreal (-z,x,y) has determinant -1.
    Quaternion vector components are axial (pseudovectors), so the transform
    is -B.T rather than the ordinary position mapping B.T.
    """
    ux, uy, uz, uw = _quat(unreal_quat, "Unreal world bone")
    return (-uy, -uz, ux, uw)


def compare_reference_calibrated(
    source_samples: list[dict],
    target_samples: list[dict],
    entity_id: str,
    mapped_bones: dict[str, str],
    reference: dict[str, Any],
    *,
    tolerance_degrees: float = 2.0,
) -> dict[str, Any]:
    """Compare independent local-reference orientation DELTAS in canonical axes.

    Reference input by source bone ID:
    source_world_rotation_xyzw -- Unity reference pose in canonical basis
    target_unreal_world_rotation_xyzw -- native Unreal reference pose
    axis_alignment_xyzw -- reviewed source-delta to target-delta frame rotation
    Conjugation maps local rotation axes; reference orientations remove the
    different bind-pose orientations. World parent/actor motion still matters
    and is independently checked by the CineTwin actor-motion comparator.
    """
    if (not isinstance(mapped_bones, dict) or not mapped_bones
            or len(set(mapped_bones.values())) != len(mapped_bones)
            or not isinstance(reference, dict)
            or set(reference) != set(mapped_bones)):
        raise RigCalibrationError("Reference calibration must cover exactly one mapped target per source bone.")
    if (not source_samples or len(source_samples) != len(target_samples)
            or len(source_samples) > 100001
            or not math.isfinite(tolerance_degrees) or tolerance_degrees <= 0):
        raise RigCalibrationError("Invalid calibrated rig sample grid or tolerance.")
    inspected = {}
    for bone_id, native_name in sorted(mapped_bones.items()):
        if not isinstance(bone_id, str) or not bone_id or not isinstance(native_name, str) or not native_name:
            raise RigCalibrationError("Invalid source/target bone identity.")
        row = reference[bone_id]
        if not isinstance(row, dict) or set(row) != {
                "source_world_rotation_xyzw", "target_unreal_world_rotation_xyzw",
                "axis_alignment_xyzw"}:
            raise RigCalibrationError("Reference row requires both independent reference orientations and axis alignment.")
        inspected[bone_id] = (
            _quat(row["source_world_rotation_xyzw"], "source reference"),
            unreal_to_canonical_quat(row["target_unreal_world_rotation_xyzw"]),
            _quat(row["axis_alignment_xyzw"], "approved axis alignment"),
        )

    per_bone = {bone: {"source_bone_id": bone, "target_bone_name": target,
                       "max_orientation_delta_error_degrees": 0.0, "worst_time_seconds": None}
                for bone, target in sorted(mapped_bones.items())}
    previous_time = None
    for index, (left, right) in enumerate(zip(source_samples, target_samples)):
        try:
            time_a, time_b = float(left["time_seconds"]), float(right["time_seconds"])
            if (not math.isfinite(time_a) or not math.isfinite(time_b)
                    or abs(time_a - time_b) > 1e-7
                    or (previous_time is not None and time_a <= previous_time)):
                raise RigCalibrationError(
                    "Source and target calibrated pose grids must be matched "
                    "and strictly increasing."
                )
            previous_time = time_a
            src_poses = [p for p in left["skeletal_poses"] if p["entity_id"] == entity_id]
            dst_poses = [p for p in right["skeletal_poses"] if p["entity_id"] == entity_id]
            if len(src_poses) != 1 or len(dst_poses) != 1:
                raise RigCalibrationError("Missing or ambiguous skeletal pose for calibrated rig.")
            src_bones = src_poses[0]["bones"]
            dst_bones = dst_poses[0]["bones"]
            src = {p["bone_id"]: p for p in src_bones}
            dst = {p["bone_name"]: p for p in dst_bones}
            if len(src) != len(src_bones) or len(dst) != len(dst_bones):
                raise RigCalibrationError("Duplicate source/target bone in measured frame.")
            for bone_id, native_name in mapped_bones.items():
                src_ref, tgt_ref, alignment = inspected[bone_id]
                sq = _quat(src[bone_id]["world_transform"]["rotation_xyzw"], "source measured world")
                tq = unreal_to_canonical_quat(dst[native_name]["unreal_world_rotation_xyzw"])
                source_delta = _mul(_inverse(src_ref), sq)
                target_delta = _mul(_inverse(tgt_ref), tq)
                predicted = _mul(_mul(alignment, source_delta), _inverse(alignment))
                error = _angle(predicted, target_delta)
                record = per_bone[bone_id]
                if record["worst_time_seconds"] is None or error > record["max_orientation_delta_error_degrees"]:
                    record["max_orientation_delta_error_degrees"] = error
                    record["worst_time_seconds"] = time_a
        except (KeyError, TypeError, IndexError, ValueError) as exc:
            if isinstance(exc, RigCalibrationError):
                raise
            raise RigCalibrationError(
                f"Calibrated rig has incomplete source/target frame {index}."
            ) from exc
    peak = max(row["max_orientation_delta_error_degrees"] for row in per_bone.values())
    return {
        "status": "PASS" if peak <= tolerance_degrees else "FAIL",
        "scope": "APPROVED_REFERENCE_CALIBRATED_JOINT_ORIENTATION_DELTA",
        "bone_count": len(mapped_bones), "sample_count": len(source_samples),
        "max_orientation_delta_error_degrees": round(peak, 6),
        "tolerance_degrees": tolerance_degrees,
        "bone_errors": list(per_bone.values()),
        "reference_note": (
            "References and axis frames must be independently observed and approved; "
            "world-parent motion and retargeted skin deformation remain separate checks."
        ),
    }


def bind_reference(calibration: dict, plan: dict, target: dict, entity_id: str,
                   expected_mapping: dict[str, str]) -> dict:
    """Pin reviewed calibration to the exact native project and source identities."""
    if not isinstance(calibration, dict) or calibration.get("kind") != "cutsceneai.rig_pose_calibration":
        raise RigCalibrationError("Expected reviewed rig pose calibration artifact.")
    if calibration.get("schema_version") != "1" or calibration.get("reference_kind") != "INDEPENDENT_APPROVED_REST_POSE":
        raise RigCalibrationError("Rig calibration needs independently approved reference poses.")
    source_id = {key: plan.get("source", {}).get(key) for key in (
        "csir_sha256", "sequence_ref", "project_fingerprint")}
    target_info = target.get("target", {})
    target_id = {key: target_info.get(key) for key in (
        "engine_version", "project_identity_sha256", "sequence_asset_path")}
    if (not all(source_id.values()) or not all(target_id.values())
            or calibration.get("source_identity") != source_id
            or calibration.get("target_identity") != target_id):
        raise RigCalibrationError("Rig calibration refers to a different source or target project/sequence.")
    rigs = calibration.get("rigs", {})
    row = rigs.get(entity_id) if isinstance(rigs, dict) else None
    if (not isinstance(row, dict) or row.get("bone_map") != expected_mapping
            or not isinstance(row.get("reference"), dict)):
        raise RigCalibrationError("Calibrated bone map differs from independent observed rig map.")
    return row["reference"]
