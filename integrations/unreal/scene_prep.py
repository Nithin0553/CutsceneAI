"""Plan deterministic target-level actor placement from CSIR scene context.

This module is Unreal-independent so placement math can be tested in CI.  The Unreal
builder applies the resulting operations to already-mapped target actors before it
creates the Level Sequence.
"""

from __future__ import annotations

from typing import Any

import csir_plan


def _curve_map(section: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for curve in section.get("payload", {}).get("animation", {}).get("curves", []):
        semantic = curve.get("canonical_semantic")
        if semantic:
            result[str(semantic)] = curve
    return result


def _single(curves: dict[str, dict[str, Any]], semantic: str, default: float) -> float:
    curve = curves.get(semantic)
    if not curve:
        return default
    keys = curve.get("keys", [])
    return float(keys[0]["value"]) if keys else default


def _vector(curves: dict[str, dict[str, Any]], prefix: str) -> tuple[float, float, float]:
    return (
        _single(curves, prefix + ".x", 0.0),
        _single(curves, prefix + ".y", 0.0),
        _single(curves, prefix + ".z", 0.0),
    )


def _quat(curves: dict[str, dict[str, Any]], prefix: str) -> tuple[float, float, float, float]:
    return (
        _single(curves, prefix + ".x", 0.0),
        _single(curves, prefix + ".y", 0.0),
        _single(curves, prefix + ".z", 0.0),
        _single(curves, prefix + ".w", 1.0),
    )


def _add3(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def canonical_scale_to_unreal(scale: tuple[float, float, float]) -> tuple[float, float, float]:
    # Canonical +X/+Y/+Z map to Unreal +Y/+Z/-X respectively. Scale follows the
    # axis permutation; handedness sign does not negate scale magnitudes.
    x, y, z = scale
    return (z, x, y)


def _transform_operation(
    entity_name: str,
    actor_label: str,
    position: tuple[float, float, float],
    rotation: tuple[float, float, float, float],
    scale: tuple[float, float, float],
    source: str,
) -> dict[str, Any]:
    roll, pitch, yaw = csir_plan.canonical_quat_to_unreal_rotator(rotation)
    return {
        "kind": "actor_transform",
        "entity_name": entity_name,
        "actor_label": actor_label,
        "source": source,
        "location_cm": csir_plan.canonical_position_to_unreal_cm(position),
        "rotation_pitch_yaw_roll_degrees": (pitch, yaw, roll),
        "scale_xyz": canonical_scale_to_unreal(scale),
    }


def _world_transform(entity: dict[str, Any], actor_label: str) -> dict[str, Any] | None:
    transform = entity.get("metadata", {}).get("world_transform")
    if not isinstance(transform, dict):
        return None
    position = transform.get("position", {})
    rotation = transform.get("rotation", {})
    scale = transform.get("scale", {})
    return _transform_operation(
        entity["name"],
        actor_label,
        (
            float(position.get("x", 0.0)),
            float(position.get("y", 0.0)),
            float(position.get("z", 0.0)),
        ),
        (
            float(rotation.get("x", 0.0)),
            float(rotation.get("y", 0.0)),
            float(rotation.get("z", 0.0)),
            float(rotation.get("w", 1.0)),
        ),
        (
            float(scale.get("x", 1.0)),
            float(scale.get("y", 1.0)),
            float(scale.get("z", 1.0)),
        ),
        "entity.world_transform",
    )


def _character_clip_transform(
    track: dict[str, Any], entity: dict[str, Any], actor_label: str
) -> dict[str, Any] | None:
    sections = track.get("sections", [])
    if not sections:
        return None
    curves = _curve_map(sections[0])
    if not any(key.startswith("transform.clip_offset.") for key in curves):
        return None

    track_position = _vector(curves, "transform.track_offset.position")
    clip_position = _vector(curves, "transform.clip_offset.position")
    position = _add3(track_position, clip_position)

    track_rotation = _quat(curves, "transform.track_offset.rotation")
    clip_rotation = _quat(curves, "transform.clip_offset.rotation")
    rotation = csir_plan._quat_mul(track_rotation, clip_rotation)

    return _transform_operation(
        entity["name"],
        actor_label,
        position,
        rotation,
        (1.0, 1.0, 1.0),
        "animation_clip_offset",
    )


def build_scene_prep(csir: dict[str, Any], mapping: dict[str, Any]) -> list[dict[str, Any]]:
    entities = {entity["entity_id"]: entity for entity in csir.get("entities", [])}
    mapped_names = set(mapping.get("entities", {}))
    dynamically_transformed: set[str] = set()
    operations: list[dict[str, Any]] = []

    for track in csir.get("tracks", []):
        entity = entities.get(track.get("binding_entity_id", ""))
        if not entity or entity.get("name") not in mapped_names:
            continue
        ced_type = track.get("ced_type")
        if ced_type == "camera.transform":
            dynamically_transformed.add(entity["name"])
        elif ced_type == "animation.track":
            if entity.get("ced_type") == "entity.character":
                op = _character_clip_transform(
                    track,
                    entity,
                    str(mapping["entities"][entity["name"]]["actor_label"]),
                )
                if op:
                    operations.append(op)
                    dynamically_transformed.add(entity["name"])
            else:
                dynamically_transformed.add(entity["name"])

    prepared_names = {operation["entity_name"] for operation in operations}
    for entity in csir.get("entities", []):
        name = entity.get("name")
        if name not in mapped_names or name in dynamically_transformed or name in prepared_names:
            continue
        if entity.get("ced_type") == "entity.audio_source":
            continue
        actor_label = str(mapping["entities"][name]["actor_label"])
        op = _world_transform(entity, actor_label)
        if op:
            operations.append(op)

    return operations
