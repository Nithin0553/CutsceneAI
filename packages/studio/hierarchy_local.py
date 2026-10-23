"""Safe source-derived parent-local transform baking for Unreal actor attachments.

A world-space Sequencer transform cannot be applied directly to an actor
attached to a moving parent: Sequencer transforms bind in the parent's local
space. Convert independently captured source child+parent world poses to
parent-local keys. Refuse unsupported scale, incomplete evidence and
unsupported source parenting rather than silently doubling transforms.
"""
from __future__ import annotations

import math
from typing import Any

import csir_plan
from hierarchy_plan import HierarchyPlanError, plan_actor_hierarchy


class HierarchyLocalError(ValueError):
    pass


def _vector(value: Any, n: int, label: str) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != n:
        raise HierarchyLocalError(f"{label} must have {n} components")
    try:
        values = tuple(float(x) for x in value)
    except (ValueError, TypeError) as exc:
        raise HierarchyLocalError(f"{label} has nonnumeric components") from exc
    if any(not math.isfinite(x) for x in values):
        raise HierarchyLocalError(f"{label} contains nonfinite components")
    return values


def _unit_quaternion(values: Any, label: str) -> tuple[float, float, float, float]:
    x, y, z, w = _vector(values, 4, label)
    norm = math.sqrt(x*x + y*y + z*z + w*w)
    if norm < 0.95 or norm > 1.05:
        raise HierarchyLocalError(f"{label} is not a valid unit quaternion")
    return (x / norm, y / norm, z / norm, w / norm)


def _inverse(q: tuple[float, float, float, float]) -> tuple[float, ...]:
    x, y, z, w = q
    return (-x, -y, -z, w)


def _rotate(q: tuple[float, ...], v: tuple[float, ...]) -> tuple[float, float, float]:
    """Rotate a vector with a unit quaternion; preserves Euclidean magnitude."""
    x, y, z, w = q
    vx, vy, vz = v
    tx, ty, tz = (2*(y*vz-z*vy), 2*(z*vx-x*vz), 2*(x*vy-y*vx))
    return (
        vx + w*tx + (y*tz-z*ty),
        vy + w*ty + (z*tx-x*tz),
        vz + w*tz + (x*ty-y*tx),
    )


def _multiply(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, float, float, float]:
    x, y, z, w = a
    bx, by, bz, bw = b
    return _unit_quaternion(
        (w*bx + x*bw + y*bz - z*by,
         w*by - x*bz + y*bw + z*bx,
         w*bz + x*by - y*bx + z*bw,
         w*bw - x*bx - y*by - z*bz),
        "relative quaternion",
    )


def _relative(parent: dict[str, Any], child: dict[str, Any]) -> tuple[
    tuple[float, float, float], tuple[float, float, float, float]
]:
    parent_pos = _vector(parent["position_m"], 3, "parent world position")
    child_pos = _vector(child["position_m"], 3, "child world position")
    parent_scale = _vector(parent["scale_xyz"], 3, "parent world scale")
    child_scale = _vector(child["scale_xyz"], 3, "child world scale")
    # Unreal's Sequence TransformTrack animates translation and rotation only.
    # Unsupported animated child scaling requires a separate scale transfer.
    if any(abs(v) < 1e-8 for v in parent_scale):
        raise HierarchyLocalError("Cannot invert a parent with zero world scale")
    if any(abs(v) < 1e-8 for v in child_scale):
        raise HierarchyLocalError("Child has a zero world scale; cannot guarantee hierarchy")
    p_quat = _unit_quaternion(parent["rotation_xyzw"], "parent world rotation")
    c_quat = _unit_quaternion(child["rotation_xyzw"], "child world rotation")
    relative_m = _rotate(_inverse(p_quat), tuple(
        child_pos[i] - parent_pos[i] for i in range(3)
    ))
    relative_m = tuple(relative_m[i]/parent_scale[i] for i in range(3))
    relative_quat = _multiply(_inverse(p_quat), c_quat)
    return relative_m, relative_quat


def _unwrap(previous: float, current: float) -> float:
    return previous + ((current - previous + 180.0) % 360.0) - 180.0


def bake_parent_local(
    csir: dict[str, Any],
    capture: dict[str, Any],
    *,
    child_id: str,
    parent_id: str,
    child_name: str,
    actor_label: str,
) -> dict[str, Any]:
    """Build child local keys at every source playback frame, with no guessing."""
    rate = csir["timing"].get("display_rate") or csir["timing"]["source_rate"]
    hz = float(rate["numerator"]) / float(rate["denominator"])
    start = csir_plan.rational_seconds(csir["timing"]["playback_start"])
    end = csir_plan.rational_seconds(csir["timing"]["playback_end"])
    count = int(math.floor((end-start)*hz + 1e-7))
    if count <= 0:
        raise HierarchyLocalError("No playback frames to bake")
    by_time = {
        round(float(s["time_seconds"]), 8): s for s in capture["samples"]
    }
    keys: list[dict[str, Any]] = []
    previous = None
    for frame in range(count):
        time = start + frame/hz
        sample = by_time.get(round(time, 8))
        if sample is None:
            raise HierarchyLocalError(f"Missing source frame {frame} at {time:.9f}s")
        entities = {e["entity_id"]: e for e in sample["entities"]}
        if parent_id not in entities or child_id not in entities:
            raise HierarchyLocalError(f"Missing evaluated world pose for {child_name} or its parent")
        parent = entities[parent_id]["world_transform"]
        child = entities[child_id]["world_transform"]
        position, quat = _relative(parent, child)
        roll, pitch, yaw = csir_plan.canonical_quat_to_unreal_rotator(quat)
        rpy = (roll, pitch, yaw)
        if previous is not None:
            rpy = tuple(_unwrap(a,b) for a,b in zip(previous,rpy))
        previous = rpy
        keys.append({
            "frame": frame,
            "location_cm": list(csir_plan.canonical_position_to_unreal_cm(position)),
            "rotation_rpy_degrees": list(rpy),
        })
    return {
        "kind": "transform",
        "entity_name": child_name,
        "actor_label": actor_label,
        "track_name": "CineTwin Evaluated Parent-Local Motion",
        "keys": keys,
        "baked_source_curves": True,
        "transform_space": "PARENT_LOCAL",
        "source_behavior_strategy": "captured_parent_child_relative_trs",
        "source_parent_entity_id": parent_id,
    }


def reconcile_hierarchy(
    csir: dict[str, Any],
    mapping: dict[str, Any],
    actions: list[dict[str, Any]],
    capture: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return safe actions and explicit hierarchy tradeoffs, no source mutation.

    Only synthetic static source-pose tracks may be omitted because KEEP_WORLD
    attachment reproduces inherited parent motion. Any independently animated
    child MUST be baked from evaluated source parent+child poses or be blocked.
    """
    try:
        hierarchy = plan_actor_hierarchy(csir, mapping)
    except HierarchyPlanError as exc:
        raise HierarchyLocalError(str(exc)) from exc
    by_id = {str(e["entity_id"]): e for e in csir.get("entities", [])}
    final = list(actions)
    results: list[dict[str, Any]] = []
    for edge in hierarchy["planned_actor_attachments"]:
        name = edge["entity_name"]
        child_actions = [
            a for a in final
            if a.get("entity_name") == name and a.get("kind") == "transform"
        ]
        other = [
            a for a in final
            if a.get("entity_name") == name and a.get("kind") == "skeletal_animation"
            and a.get("root_motion_correction_samples")
        ]
        if other:
            raise HierarchyLocalError(
                f"{name}: skeletal root correction with attached parent has "
                "no verified parent-local retargeting policy"
            )
        if not child_actions:
            results.append({
                "entity_name": name, "outcome": "INHERITED_NO_CHILD_WORLD_TRACK",
                "source_parent_name": edge["source_parent_name"],
            })
            continue
        if all(
            a.get("source_behavior_strategy") == "source_static_world_pose"
            for a in child_actions
        ):
            final = [a for a in final if a not in child_actions]
            results.append({
                "entity_name": name,
                "outcome": "STATIC_CHILD_INHERITS_PARENT",
                "source_parent_name": edge["source_parent_name"],
                "removed_synthetic_world_pose_tracks": len(child_actions),
            })
            continue
        if capture is None:
            raise HierarchyLocalError(
                f"{name}: independently animated child requires verified CineTwin "
                "capture to convert world motion to parent-local space"
            )
        # A CineTwin capture is a world-transform authority, NOT a substitute
        # for skeletal animation/bones or time-changing parent attachments.
        action = bake_parent_local(
            csir, capture,
            child_id=str(edge["entity_id"]),
            parent_id=str(edge["source_parent_entity_id"]),
            child_name=name,
            actor_label=str(edge["actor_label"]),
        )
        final = [a for a in final if a not in child_actions]
        final.append(action)
        results.append({
            "entity_name": name,
            "outcome": "CAPTURED_PARENT_LOCAL_BEST_EFFORT",
            "source_parent_name": edge["source_parent_name"],
            "replaced_world_transform_tracks": len(child_actions),
            "sampled_frames": len(action["keys"]),
            "limitations": [
                "Actor transform only; no skeletal bone/rig equivalence",
                "Source evaluated motion may differ from Unreal target parent dynamics",
                "TRS decomposition does not represent arbitrary shear",
            ],
        })
    return final, results
