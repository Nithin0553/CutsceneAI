"""Plan deterministic target-level actor placement from CSIR scene context.

This module is Unreal-independent so placement math can be tested in CI.  The Unreal
builder applies the resulting operations to already-mapped target actors before it
creates the Level Sequence.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
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
    track: dict[str, Any],
    entity: dict[str, Any],
    actor_label: str,
    entities: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    sections = track.get("sections", [])
    if not sections:
        return None
    curves = _curve_map(sections[0])
    if not any(key.startswith("transform.clip_offset.") for key in curves):
        return None

    position, rotation, scale = csir_plan.character_section_world_transform(
        sections[0], entity, entities
    )
    return _transform_operation(
        entity["name"],
        actor_label,
        position,
        rotation,
        scale,
        "animation_clip_offset",
    )


def _observed_first_frame_scene_prep(
    csir: dict[str, Any], mapping: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """Use source-evaluated world poses when a verified CineTwin capture is provided.

    This is an opt-in mapping input, not an edit to the canonical CSIR.
    It deliberately uses evaluated frame zero, including Unity Timeline offsets
    and the current attachment hierarchy, instead of an arbitrary editor pose.
    """
    source_path = mapping.get("source_behavior_capture_path")
    if not source_path:
        return None
    capture = json.loads(Path(source_path).read_text(encoding="utf-8"))
    if capture.get("kind") != "cinetwin.behavior_capture":
        raise csir_plan.PlanError("Expected a CineTwin Unity source behavior capture.")
    if capture.get("cutscene_id") != csir.get("cutscene_id"):
        raise csir_plan.PlanError("CineTwin capture cutscene ID differs from frozen CSIR.")
    for key in ("sequence_ref", "project_fingerprint"):
        expected = csir.get("source", {}).get(key)
        observed = capture.get("source", {}).get(key)
        if not expected or expected != observed:
            raise csir_plan.PlanError(f"CineTwin frame-zero provenance mismatch: {key}.")
    samples = capture.get("samples", [])
    if not samples:
        raise csir_plan.PlanError("CineTwin behavior capture has no samples.")
    zero = samples[0]
    expected_start = csir_plan.rational_seconds(
        csir.get("timing", {}).get("playback_start", {
            "value": 0, "rate": {"numerator": 1, "denominator": 1}
        }))
    if abs(float(zero.get("time_seconds", -1000)) - expected_start) > 1e-7:
        raise csir_plan.PlanError("CineTwin source capture does not start at playback frame zero.")
    observations: dict[str, dict[str, Any]] = {}
    for observed in zero.get("entities", []):
        identifier = str(observed.get("entity_id", ""))
        if not identifier or identifier in observations:
            raise csir_plan.PlanError("Duplicate or missing source entity ID in first-frame capture.")
        observations[identifier] = observed
    placements: list[dict[str, Any]] = []
    for entity in csir.get("entities", []):
        name = entity.get("name")
        if name not in mapping.get("entities", {}) or entity.get("ced_type") == "entity.audio_source":
            continue
        record = observations.get(str(entity["entity_id"]))
        if record is None:
            raise csir_plan.PlanError(f"Source first-frame observation missing mapped entity: {name}.")
        transform = record.get("world_transform", {})
        position = transform.get("position_m")
        rotation = transform.get("rotation_xyzw")
        scale = transform.get("scale_xyz")
        if (not isinstance(position, list) or len(position) != 3
                or not isinstance(rotation, list) or len(rotation) != 4
                or not isinstance(scale, list) or len(scale) != 3):
            raise csir_plan.PlanError(f"Invalid source first-frame world transform for {name}.")
        values = [float(x) for x in [*position, *rotation, *scale]]
        if not all(math.isfinite(x) for x in values):
            raise csir_plan.PlanError(f"Nonfinite source first-frame transform for {name}.")
        placements.append(_transform_operation(
            str(name),
            str(mapping["entities"][name]["actor_label"]),
            tuple(values[:3]), tuple(values[3:7]), tuple(values[7:10]),
            "cinetwin.source_evaluated_first_frame",
        ))
    return placements


def build_scene_prep(csir: dict[str, Any], mapping: dict[str, Any]) -> list[dict[str, Any]]:
    observed = _observed_first_frame_scene_prep(csir, mapping)
    if observed is not None:
        return observed
    entities = {entity["entity_id"]: entity for entity in csir.get("entities", [])}
    rate = csir.get("timing", {}).get("source_rate", {"numerator": 24, "denominator": 1})
    mapped_names = set(mapping.get("entities", {}))
    dynamically_transformed: set[str] = set()
    operations: list[dict[str, Any]] = []

    for track in csir.get("tracks", []):
        entity = entities.get(track.get("binding_entity_id", ""))
        if not entity or entity.get("name") not in mapped_names:
            continue
        ced_type = track.get("ced_type")
        if ced_type == "camera.transform":
            action = csir_plan._transform_action(
                track, entity, str(mapping["entities"][entity["name"]]["actor_label"]),
                int(rate["numerator"]), int(rate["denominator"]), entities,
            ) if track.get("sections") else None
            if action is not None:
                dynamically_transformed.add(entity["name"])
        elif ced_type == "animation.track":
            if entity.get("ced_type") == "entity.character":
                op = _character_clip_transform(
                    track,
                    entity,
                    str(mapping["entities"][entity["name"]]["actor_label"]),
                    entities,
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
