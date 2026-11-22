"""Independent character anatomical-forward versus Unreal mesh basis audit.

A mesh's visual front is NOT generally its actor/armature +X/+Z axis.
This module accepts separately approved source/target anatomy directions and
native per-frame target skeletal-component orientations. It never guesses an
FBX import correction or automatically mutates a character's root transform.
"""
from __future__ import annotations

import math
from typing import Any

from rig_pose_calibration import (
    RigCalibrationError, _quat, unreal_to_canonical_quat,
)


class MeshForwardError(ValueError):
    pass


def _unit_vector(value: Any, label: str) -> tuple[float, float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise MeshForwardError(f"{label}: expected a 3D direction.")
    try:
        vector = tuple(float(x) for x in value)
    except (TypeError, ValueError) as error:
        raise MeshForwardError(f"{label}: nonnumeric direction.") from error
    if not all(math.isfinite(x) for x in vector):
        raise MeshForwardError(f"{label}: nonfinite direction.")
    norm = math.sqrt(sum(x*x for x in vector))
    if norm <= 1e-9 or abs(norm - 1.0) > 0.01:
        raise MeshForwardError(f"{label}: approved anatomical axis must be unit length.")
    return tuple(x/norm for x in vector)


def _rotate(q, v) -> tuple[float, float, float]:
    """Rotate a unit direction using a source/target canonical world quaternion."""
    x, y, z, w = q
    u, v0, t = v
    tx, ty, tz = (2*(y*t-z*v0), 2*(z*u-x*t), 2*(x*v0-y*u))
    return (
        u + w*tx + (y*tz-z*ty),
        v0 + w*ty + (z*tx-x*tz),
        t + w*tz + (x*ty-y*tx),
    )


def unreal_vector_to_canonical(value: Any) -> tuple[float, float, float]:
    x, y, z = _unit_vector(value, "Unreal anatomical forward")
    # Unreal vector (-canonical_z, canonical_x, canonical_y).
    return (y, z, -x)


def _angle(a, b):
    dot = min(1.0, max(-1.0, sum(x*y for x, y in zip(a, b))))
    return math.degrees(math.acos(dot))


def _yaw_to_align_in_unreal(target_canonical, source_canonical) -> float | None:
    # Unreal horizontal XY coordinates of canonical direction.
    tx, ty = -target_canonical[2], target_canonical[0]
    sx, sy = -source_canonical[2], source_canonical[0]
    mt, ms = math.hypot(tx, ty), math.hypot(sx, sy)
    if min(mt, ms) < 0.05:
        return None
    tx, ty, sx, sy = tx/mt, ty/mt, sx/ms, sy/ms
    return round(math.degrees(math.atan2(tx*sy-ty*sx, tx*sx+ty*sy)), 6)


def bind_profile(profile: dict, plan: dict, target: dict, entity_id: str) -> dict:
    if (not isinstance(profile, dict)
            or profile.get("kind") != "cutsceneai.mesh_forward_approval"
            or profile.get("schema_version") != "1"
            or profile.get("reviewed_anatomical_axes") is not True):
        raise MeshForwardError("Mesh local anatomical front requires explicit reviewed approval.")
    source_id = {key: plan.get("source", {}).get(key) for key in (
        "csir_sha256", "sequence_ref", "project_fingerprint")}
    native = target.get("target", {})
    target_id = {key: native.get(key) for key in (
        "engine_version", "project_identity_sha256", "sequence_asset_path")}
    if (not all(source_id.values()) or not all(target_id.values())
            or profile.get("source_identity") != source_id
            or profile.get("target_identity") != target_id):
        raise MeshForwardError("Mesh anatomy approval is stale for this source or Unreal candidate.")
    characters = profile.get("characters")
    entry = characters.get(entity_id) if isinstance(characters, dict) else None
    if (not isinstance(entry, dict) or set(entry) != {
            "source_forward_actor_local_canonical_xyz",
            "target_forward_mesh_local_unreal_xyz", "target_mesh_asset_path"}):
        raise MeshForwardError("Character mesh approval lacks exact source/target local anatomical axes.")
    mesh = entry["target_mesh_asset_path"]
    if not isinstance(mesh, str) or not mesh.startswith("/Game/") or ".." in mesh:
        raise MeshForwardError("Mesh anatomy approval has an invalid target mesh path.")
    return entry


def compare_mesh_forward(
    source_samples: list[dict], target_samples: list[dict],
    entity_id: str, profile: dict, *, tolerance_degrees: float = 2.0,
) -> dict:
    if (not source_samples or len(source_samples) != len(target_samples)
            or len(source_samples) > 100001 or not math.isfinite(tolerance_degrees)
            or tolerance_degrees <= 0):
        raise MeshForwardError("Invalid mesh facing sample grid or tolerance.")
    source_axis = _unit_vector(profile["source_forward_actor_local_canonical_xyz"],
                               "Source reviewed actor-local anatomical forward")
    target_axis = unreal_vector_to_canonical(profile["target_forward_mesh_local_unreal_xyz"])
    expected_mesh = profile["target_mesh_asset_path"]
    maximum, worst_time, yaw = 0.0, None, None
    for index, (left, right) in enumerate(zip(source_samples, target_samples)):
        try:
            t = float(left["time_seconds"])
            if not math.isfinite(t) or abs(t-float(right["time_seconds"])) > 1e-7:
                raise MeshForwardError("Source/target mesh facing time mismatch.")
            source_actors = [x for x in left["entities"] if x.get("entity_id") == entity_id]
            bases = [x for x in right.get("skeletal_mesh_component_bases", [])
                     if x.get("entity_id") == entity_id]
            if len(source_actors) != 1 or len(bases) != 1:
                raise MeshForwardError(f"Missing or ambiguous independently observed mesh component at frame {index}.")
            basis = bases[0]
            if (basis.get("status") != "OBSERVED"
                    or basis.get("target_mesh_asset_path") != expected_mesh):
                raise MeshForwardError("Native target mesh/component differs from approved anatomy evidence.")
            source_q = _quat(source_actors[0]["world_transform"]["rotation_xyzw"],
                             "source actor orientation")
            target_q = unreal_to_canonical_quat(
                basis["unreal_component_world_rotation_xyzw"])
            source_world = _rotate(source_q, source_axis)
            target_world = _rotate(target_q, target_axis)
            error = _angle(source_world, target_world)
            if worst_time is None or error > maximum:
                maximum = error
                worst_time = t
                yaw = _yaw_to_align_in_unreal(target_world, source_world)
        except RigCalibrationError as exc:
            raise MeshForwardError(str(exc)) from exc
        except (TypeError, KeyError, IndexError, ValueError) as exc:
            if isinstance(exc, MeshForwardError):
                raise
            raise MeshForwardError(f"Incomplete observed mesh orientation at frame {index}.") from exc
    return {
        "status": "PASS" if maximum <= tolerance_degrees else "FAIL",
        "scope": "APPROVED_MESH_ANATOMICAL_FORWARD_VS_SOURCE",
        "max_world_forward_error_degrees": round(maximum, 6),
        "worst_time_seconds": worst_time,
        "tolerance_degrees": tolerance_degrees,
        "suggested_target_actor_yaw_correction_degrees": (
            yaw if maximum > tolerance_degrees else 0.0
        ),
        "suggestion_applied": False,
        "requires_native_recheck_and_explicit_approval": maximum > tolerance_degrees,
        "sample_count": len(source_samples),
        "warning": (
            "A suggested yaw is diagnostic only. A nonplanar axis/mesh/rig mismatch "
            "or changing facing error cannot be corrected safely with an actor yaw guess."
        ),
    }
