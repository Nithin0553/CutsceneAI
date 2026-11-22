"""Pure-Python CSIR -> Unreal reconstruction planning.

This module deliberately does not import ``unreal`` so the transfer math and planning
can be unit-tested outside the editor.  ``build_level_sequence.py`` is the thin Unreal
realization layer.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


class PlanError(ValueError):
    pass


def timeline_clip_easing_seconds(native_payload: dict[str, Any], side: str) -> float:
    """Resolve Timeline blend/ease durations without leaking Unity's -1 sentinel.

    Unity reports -1 for a clip that is not currently blended. This is not a
    negative fade; an explicit ease duration may still apply instead. Keep
    actual positive blend durations, but reject other negative/nonfinite data.
    """
    if side not in {"in", "out"}:
        raise PlanError(f"Invalid Timeline easing direction: {side}")
    try:
        blend = float(native_payload.get(f"blend_{side}_seconds", 0.0))
        ease = float(native_payload.get(f"ease_{side}_seconds", 0.0))
    except (TypeError, ValueError) as exc:
        raise PlanError(f"Invalid Timeline {side} blend/ease duration.") from exc
    if not math.isfinite(blend) or not math.isfinite(ease):
        raise PlanError(f"Non-finite Timeline {side} blend/ease duration.")
    if blend < 0.0 and blend != -1.0:
        raise PlanError(f"Unsupported negative Timeline {side} blend duration: {blend}")
    if ease < 0.0:
        raise PlanError(f"Negative Timeline {side} ease duration: {ease}")
    return blend if blend > 0.0 else ease


def load_json(path: str | Path) -> dict[str, Any]:
    # Accept BOM-prefixed UTF-8 from Windows PowerShell and ordinary UTF-8 alike.
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def rational_seconds(value: dict[str, Any]) -> float:
    rate = value["rate"]
    return float(value["value"]) * float(rate["denominator"]) / float(rate["numerator"])


def seconds_to_frame(seconds: float, numerator: int, denominator: int) -> int:
    return int(round(seconds * numerator / denominator))


def _unique_source_index(csir: dict[str, Any], collection: str, field: str) -> dict[str, dict[str, Any]]:
    """Prevent duplicate native source identities from silently replacing evidence."""
    result: dict[str, dict[str, Any]] = {}
    for row in csir.get(collection, []):
        identifier = row.get(field)
        if not isinstance(identifier, str) or not identifier.strip() or identifier in result:
            raise PlanError(f"Missing or duplicated source {field} in {collection}.")
        result[identifier] = row
    return result


def _asset_index(csir: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _unique_source_index(csir, "assets", "asset_id")


def _entity_index(csir: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _unique_source_index(csir, "entities", "entity_id")


def validate_mapping_identity(
    csir: dict[str, Any], mapping: dict[str, Any]
) -> None:
    """An actor label or asset name must never stand for two source identities.

    The current mapping format keys source objects by name. A repeated mapped
    source name cannot be distinguished by the editor or receipt, and two
    mapped entities sharing a target label create competing Sequencer writers.
    Unsupported source names are allowed to repeat when they are not mapped.
    """
    source_entities = csir.get("entities", [])
    source_assets = csir.get("assets", [])
    actor_map = mapping.get("entities", {})
    asset_map = mapping.get("assets", {})
    if not isinstance(actor_map, dict) or not isinstance(asset_map, dict):
        raise PlanError("Target entity and asset mappings must be objects.")
    _entity_index(csir)
    _asset_index(csir)
    by_name: dict[str, int] = {}
    for entity in source_entities:
        name = str(entity.get("name", ""))
        if name in actor_map:
            by_name[name] = by_name.get(name, 0) + 1
    repeated = sorted(name for name, count in by_name.items() if count != 1)
    if repeated:
        raise PlanError("Ambiguous mapped source entity name(s): " + ", ".join(repeated))
    target_owners: dict[str, str] = {}
    for name in sorted(by_name):
        label = _mapping_actor(mapping, name)
        if label in target_owners:
            raise PlanError(
                f"Two source entities {target_owners[label]!r} and {name!r} "
                f"map to the same Unreal actor label {label!r}."
            )
        target_owners[label] = name
    asset_counts: dict[str, int] = {}
    for asset in source_assets:
        name = str(asset.get("name", ""))
        if name in asset_map:
            asset_counts[name] = asset_counts.get(name, 0) + 1
    repeated_assets = sorted(name for name, count in asset_counts.items() if count != 1)
    if repeated_assets:
        raise PlanError("Ambiguous mapped source asset name(s): " + ", ".join(repeated_assets))


def _mapping_asset(mapping: dict[str, Any], source_name: str) -> str:
    value = mapping.get("assets", {}).get(source_name)
    if not value:
        raise PlanError(f"No Unreal asset mapping for source asset: {source_name}")
    return str(value)


def _mapping_actor(mapping: dict[str, Any], entity_name: str) -> str:
    entry = mapping.get("entities", {}).get(entity_name)
    label = entry.get("actor_label") if isinstance(entry, dict) else None
    if not isinstance(label, str) or not label.strip() or label != label.strip():
        raise PlanError(f"No unambiguous Unreal actor label for source entity: {entity_name}")
    return label


def _curve_map(section: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Only root-bound Unity curves can drive an Unreal actor transform.

    Nested bone/child curves retain their CSIR path and must be handled by
    skeletal conversion. Flattening paths corrupts actor placement and facing.
    """
    curves = section.get("payload", {}).get("animation", {}).get("curves", [])
    result: dict[str, dict[str, Any]] = {}
    for curve in curves:
        if not isinstance(curve, dict):
            raise PlanError("Animation contains a non-object source curve.")
        if str(curve.get("path") or "").strip():
            continue
        semantic = curve.get("canonical_semantic") or curve.get("property_name")
        if semantic:
            name = str(semantic)
            # The extractor intentionally gives Unity Euler X/Y/Z ONE
            # placeholder semantic. Their native property names are resolved
            # axis-by-axis below, so this placeholder is not a unique channel.
            if name == "transform.rotation.euler_native":
                continue
            if name in result:
                raise PlanError("Ambiguous duplicate root-level animation curve: " + name)
            result[name] = curve
    return result


def _single_value(curves: dict[str, dict[str, Any]], semantic: str, default: float) -> float:
    curve = curves.get(semantic)
    if not curve:
        return default
    keys = curve.get("keys", [])
    return float(keys[0]["value"]) if keys else default


def _vector_offset(curves: dict[str, dict[str, Any]], prefix: str) -> tuple[float, float, float]:
    return (
        _single_value(curves, prefix + ".x", 0.0),
        _single_value(curves, prefix + ".y", 0.0),
        _single_value(curves, prefix + ".z", 0.0),
    )


def _quat_offset(curves: dict[str, dict[str, Any]], prefix: str) -> tuple[float, float, float, float]:
    names = [prefix + "." + axis for axis in "xyzw"]
    present = [name in curves for name in names]
    if any(present) and not all(present):
        raise PlanError(f"Partial source orientation offset for {prefix}; cannot infer missing axes.")
    if any(present) and any(len(curves[name].get("keys", [])) != 1 for name in names):
        raise PlanError(f"Source orientation offset for {prefix} requires one key per quaternion axis.")
    return _normalize_quat(
        (
            _single_value(curves, prefix + ".x", 0.0),
            _single_value(curves, prefix + ".y", 0.0),
            _single_value(curves, prefix + ".z", 0.0),
            _single_value(curves, prefix + ".w", 1.0),
        )
    )


def _curve_value(curve: dict[str, Any] | None, time_seconds: float, default: float = 0.0) -> float:
    """Evaluate a source curve; use authored Hermite tangents when native keys exist.

    Synthetic offset curves and older fixtures have no native_keys and retain
    the legacy linear behavior. Weighted Unity tangents are not equivalent to
    unweighted Hermite; reject them instead of silently altering motion.
    """
    if not curve or not curve.get("keys"):
        return default
    if not math.isfinite(float(time_seconds)):
        raise PlanError("Non-finite source animation sample time.")
    keys = curve["keys"]
    previous_time = -math.inf
    for key in keys:
        try:
            timestamp, value = float(key["time_seconds"]), float(key["value"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PlanError("Source curve has an invalid time or value.") from exc
        if not math.isfinite(timestamp) or not math.isfinite(value):
            raise PlanError("Non-finite source animation key.")
        if timestamp <= previous_time:
            raise PlanError("Source animation key times must be strictly increasing.")
        if curve.get("native_keys") and int(key.get("weighted_mode", 0)):
            raise PlanError("Weighted Unity curve tangents require a dedicated evaluator.")
        previous_time = timestamp
    if time_seconds <= float(keys[0]["time_seconds"]):
        return float(keys[0]["value"])
    if time_seconds >= float(keys[-1]["time_seconds"]):
        return float(keys[-1]["value"])
    for left, right in zip(keys, keys[1:]):
        t0 = float(left["time_seconds"])
        t1 = float(right["time_seconds"])
        if t0 <= time_seconds <= t1:
            alpha = 0.0 if t1 == t0 else (time_seconds - t0) / (t1 - t0)
            a, b = float(left["value"]), float(right["value"])
            if not curve.get("native_keys"):
                return a + (b - a) * alpha
            if int(left.get("weighted_mode", 0)) or int(right.get("weighted_mode", 0)):
                raise PlanError("Weighted Unity curve tangents require a dedicated evaluator.")
            m0 = float(left.get("out_tangent", 0.0))
            m1 = float(right.get("in_tangent", 0.0))
            if not all(math.isfinite(value) for value in (m0, m1)):
                raise PlanError("Nonfinite Unity curve tangents cannot be reconstructed.")
            span = t1 - t0
            return ((2 * alpha**3 - 3 * alpha**2 + 1) * a
                    + (alpha**3 - 2 * alpha**2 + alpha) * span * m0
                    + (-2 * alpha**3 + 3 * alpha**2) * b
                    + (alpha**3 - alpha**2) * span * m1)
    return default



def _source_root_delta_unreal_cm(
    section: dict[str, Any],
    world_rotation: tuple[float, float, float, float] | None = None,
) -> tuple[float, float, float] | None:
    """Resolve Unity Animator RootT displacement into Unreal world-axis centimeters."""
    curves = {
        name: curve for name, curve in _curve_map(section).items()
        if name.startswith("RootT.")
    }
    required = ("RootT.x", "RootT.y", "RootT.z")
    if not all(name in curves for name in required):
        return None

    source_start = rational_seconds(section.get("source_offset", {"value": 0, "rate": {"numerator": 1, "denominator": 1}}))
    timeline_duration = rational_seconds(section["end"]) - rational_seconds(section["start"])
    source_end = source_start + timeline_duration * float(section.get("time_scale", 1.0))

    dx = _curve_value(curves["RootT.x"], source_end) - _curve_value(curves["RootT.x"], source_start)
    dy = _curve_value(curves["RootT.y"], source_end) - _curve_value(curves["RootT.y"], source_start)
    dz = _curve_value(curves["RootT.z"], source_end) - _curve_value(curves["RootT.z"], source_start)

    # RootT is Unity-native: +X right, +Y up, +Z forward, meters. Convert the
    # displacement through the same canonical basis used for ordinary transforms.
    canonical_delta = (dx, dy, -dz)
    if world_rotation is not None:
        canonical_delta = _quat_rotate_vector(world_rotation, canonical_delta)
    return canonical_position_to_unreal_cm(canonical_delta)


def _source_root_samples_unreal_cm(
    section: dict[str, Any],
    world_rotation: tuple[float, float, float, float] | None = None,
) -> list[dict[str, Any]]:
    """Sample source RootT displacement at authored key times in Unreal world axes."""
    curves = {
        name: curve for name, curve in _curve_map(section).items()
        if name.startswith("RootT.")
    }
    required = ("RootT.x", "RootT.y", "RootT.z")
    if not all(name in curves for name in required):
        return []

    source_start = rational_seconds(
        section.get(
            "source_offset",
            {"value": 0, "rate": {"numerator": 1, "denominator": 1}},
        )
    )
    timeline_duration = rational_seconds(section["end"]) - rational_seconds(section["start"])
    time_scale = float(section.get("time_scale", 1.0))
    source_end = source_start + timeline_duration * time_scale

    times = {source_start, source_end}
    for curve in curves.values():
        for key in curve.get("keys", []):
            time_seconds = float(key["time_seconds"])
            if source_start <= time_seconds <= source_end:
                times.add(time_seconds)

    start_x = _curve_value(curves["RootT.x"], source_start)
    start_y = _curve_value(curves["RootT.y"], source_start)
    start_z = _curve_value(curves["RootT.z"], source_start)

    section_start_seconds = rational_seconds(section["start"])
    samples: list[dict[str, Any]] = []
    for source_time in sorted(times):
        dx = _curve_value(curves["RootT.x"], source_time) - start_x
        dy = _curve_value(curves["RootT.y"], source_time) - start_y
        dz = _curve_value(curves["RootT.z"], source_time) - start_z
        canonical_delta = (dx, dy, -dz)
        if world_rotation is not None:
            canonical_delta = _quat_rotate_vector(world_rotation, canonical_delta)
        timeline_time = section_start_seconds + (
            (source_time - source_start) / time_scale if abs(time_scale) > 1e-12 else 0.0
        )
        samples.append(
            {
                "source_time_seconds": float(source_time),
                "timeline_time_seconds": float(timeline_time),
                "delta_cm": list(canonical_position_to_unreal_cm(canonical_delta)),
            }
        )
    return samples


def _source_root_profile_unreal_cm(
    section: dict[str, Any],
    world_rotation: tuple[float, float, float, float] | None = None,
) -> dict[str, float] | None:
    """Summarize source RootT trajectory in Unreal world-axis centimeters.

    The profile is used for validation policy. It does not change the transferred
    animation. Vertical excursion is measured over source curve key times inside the
    section so a jump-like clip is not misclassified from a near-zero end displacement.
    """
    curves = {
        name: curve for name, curve in _curve_map(section).items()
        if name.startswith("RootT.")
    }
    required = ("RootT.x", "RootT.y", "RootT.z")
    if not all(name in curves for name in required):
        return None

    source_start = rational_seconds(
        section.get(
            "source_offset",
            {"value": 0, "rate": {"numerator": 1, "denominator": 1}},
        )
    )
    timeline_duration = rational_seconds(section["end"]) - rational_seconds(section["start"])
    source_end = source_start + timeline_duration * float(section.get("time_scale", 1.0))

    samples = _source_root_samples_unreal_cm(section, world_rotation)
    positions_unreal_cm = [
        tuple(float(value) for value in sample["delta_cm"])
        for sample in samples
    ]

    if not positions_unreal_cm:
        return None

    end = positions_unreal_cm[-1]
    horizontal_distance = math.hypot(float(end[0]), float(end[1]))
    vertical_values = [float(position[2]) for position in positions_unreal_cm]
    vertical_excursion = max(vertical_values) - min(vertical_values)

    return {
        "horizontal_end_distance_cm": horizontal_distance,
        "vertical_net_displacement_cm": float(end[2]),
        "vertical_excursion_cm": vertical_excursion,
        "sample_count": float(len(positions_unreal_cm)),
    }


def root_motion_yaw_alignment_degrees(
    expected_delta_cm: tuple[float, float, float],
    target_delta_cm: tuple[float, float, float],
    minimum_horizontal_cm: float = 1.0,
) -> float | None:
    """Return yaw needed to align target imported root travel with source travel."""
    expected_xy = math.hypot(float(expected_delta_cm[0]), float(expected_delta_cm[1]))
    target_xy = math.hypot(float(target_delta_cm[0]), float(target_delta_cm[1]))
    if expected_xy < minimum_horizontal_cm or target_xy < minimum_horizontal_cm:
        return None
    expected_angle = math.atan2(float(expected_delta_cm[1]), float(expected_delta_cm[0]))
    target_angle = math.atan2(float(target_delta_cm[1]), float(target_delta_cm[0]))
    degrees = math.degrees(expected_angle - target_angle)
    return (degrees + 180.0) % 360.0 - 180.0


def select_actor_root_motion_alignments(
    actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Choose at most one root-motion yaw calibration per target actor.

    Root-motion import orientation is an actor/skeleton-space calibration, not a
    per-section rotation to accumulate. When an actor has multiple animation
    sections, choose the section with the largest observed source horizontal travel;
    low-motion/idle drift must not apply a second yaw correction to the same actor.
    """
    selected: dict[str, tuple[float, dict[str, Any]]] = {}
    order: list[str] = []

    for action in actions:
        if str(action.get("kind")) != "skeletal_animation":
            continue
        if action.get("resolved_root_yaw_degrees") is None:
            continue
        expected = action.get("expected_root_delta_cm")
        if not isinstance(expected, (list, tuple)) or len(expected) < 2:
            continue
        actor_label = str(action.get("actor_label", "")).strip()
        if not actor_label:
            continue

        horizontal_cm = math.hypot(float(expected[0]), float(expected[1]))
        current = selected.get(actor_label)
        if current is None:
            selected[actor_label] = (horizontal_cm, action)
            order.append(actor_label)
        elif horizontal_cm > current[0]:
            selected[actor_label] = (horizontal_cm, action)

    return [selected[actor_label][1] for actor_label in order]


def _target_output_profile(mapping: dict[str, Any]) -> tuple[int, int, str]:
    value = mapping.get("output_resolution")
    if value is not None:
        if (not isinstance(value, (list, tuple)) or len(value) != 2
                or any(type(dimension) is not int for dimension in value)
                or any(dimension < 1 or dimension > 16384 for dimension in value)):
            raise PlanError("Explicit output_resolution must contain two positive integer pixels <= 16384.")
        return value[0], value[1], "mapping.output_resolution"
    # Only an omitted output gate uses the benchmark default. An explicitly
    # invalid mapping cannot silently change camera framing/aspect.
    return 1920, 1080, "benchmark_default_1920x1080"


def canonical_position_to_unreal_cm(position: tuple[float, float, float]) -> tuple[float, float, float]:
    # CSIR canonical: RH, +Y up, -Z forward, meters.
    # Unreal: LH, +Z up, +X forward, centimeters.
    x, y, z = position
    return (-z * 100.0, x * 100.0, y * 100.0)


def _normalize_quat(q: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    if len(q) != 4 or not all(math.isfinite(v) for v in q):
        raise PlanError("Canonical rotation quaternion must have four finite components.")
    length = math.sqrt(sum(component * component for component in q))
    if length <= 1e-12:
        raise PlanError("Zero-length source quaternion cannot determine facing direction.")
    return tuple(component / length for component in q)  # type: ignore[return-value]


def _quat_mul(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return _normalize_quat(
        (
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz,
        )
    )


def _axis_angle(axis: tuple[float, float, float], degrees: float) -> tuple[float, float, float, float]:
    radians = math.radians(degrees) * 0.5
    sine = math.sin(radians)
    return (axis[0] * sine, axis[1] * sine, axis[2] * sine, math.cos(radians))


def unity_euler_delta_to_canonical_quat(
    x_degrees: float, y_degrees: float, z_degrees: float
) -> tuple[float, float, float, float]:
    # Unity Quaternion.Euler uses Z-X-Y application order.  Construct the Unity-space
    # delta, then apply the same handedness conversion used by the Unity extractor.
    qx = _axis_angle((1.0, 0.0, 0.0), x_degrees)
    qy = _axis_angle((0.0, 1.0, 0.0), y_degrees)
    qz = _axis_angle((0.0, 0.0, 1.0), z_degrees)
    unity_q = _quat_mul(qy, _quat_mul(qx, qz))
    ux, uy, uz, uw = unity_q
    return _normalize_quat((-ux, -uy, uz, uw))


def _quat_to_matrix(q: tuple[float, float, float, float]) -> list[list[float]]:
    x, y, z, w = _normalize_quat(q)
    return [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]


def _quat_rotate_vector(
    q: tuple[float, float, float, float],
    vector: tuple[float, float, float],
) -> tuple[float, float, float]:
    matrix = _quat_to_matrix(q)
    return tuple(
        sum(float(matrix[row][col]) * float(vector[col]) for col in range(3))
        for row in range(3)
    )  # type: ignore[return-value]


def parent_world_transform(
    entity: dict[str, Any],
    entities: dict[str, dict[str, Any]],
) -> tuple[
    tuple[float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float],
]:
    """Return the source parent's canonical world transform, or identity."""
    parent_id = entity.get("parent_entity_id")
    if not parent_id:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0)
    parent = entities.get(str(parent_id))
    if parent is None:
        raise PlanError("Parent entity is missing; cannot reconstruct child world position or facing.")

    transform = parent.get("metadata", {}).get("world_transform")
    if not isinstance(transform, dict):
        raise PlanError("Parent world transform is missing; cannot assume an identity parent.")

    position = transform.get("position")
    rotation = transform.get("rotation")
    scale = transform.get("scale")
    if not all(isinstance(part, dict) for part in (position, rotation, scale)):
        raise PlanError("Incomplete parent world transform; cannot place the attached child.")
    if any(axis not in position or axis not in scale or axis not in rotation
           for axis in "xyz") or "w" not in rotation:
        raise PlanError("Missing parent position, scale or facing component.")
    return (
        (
            float(position.get("x", 0.0)),
            float(position.get("y", 0.0)),
            float(position.get("z", 0.0)),
        ),
        _normalize_quat(
            (
                float(rotation.get("x", 0.0)),
                float(rotation.get("y", 0.0)),
                float(rotation.get("z", 0.0)),
                float(rotation.get("w", 1.0)),
            )
        ),
        (
            float(scale.get("x", 1.0)),
            float(scale.get("y", 1.0)),
            float(scale.get("z", 1.0)),
        ),
    )


def compose_canonical_transform(
    parent_position: tuple[float, float, float],
    parent_rotation: tuple[float, float, float, float],
    parent_scale: tuple[float, float, float],
    local_position: tuple[float, float, float],
    local_rotation: tuple[float, float, float, float],
    local_scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> tuple[
    tuple[float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float],
]:
    """Compose a canonical local transform under a canonical parent world transform."""
    scaled_local = tuple(
        float(local_position[i]) * float(parent_scale[i]) for i in range(3)
    )
    rotated_local = _quat_rotate_vector(parent_rotation, scaled_local)
    world_position = tuple(
        float(parent_position[i]) + float(rotated_local[i]) for i in range(3)
    )
    world_rotation = _quat_mul(parent_rotation, local_rotation)
    world_scale = tuple(
        float(parent_scale[i]) * float(local_scale[i]) for i in range(3)
    )
    return world_position, world_rotation, world_scale


def character_section_world_transform(
    section: dict[str, Any],
    entity: dict[str, Any],
    entities: dict[str, dict[str, Any]],
) -> tuple[
    tuple[float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float],
]:
    """Resolve Timeline track/clip offsets into source world space."""
    curves = _curve_map(section)
    track_position = _vector_offset(curves, "transform.track_offset.position")
    clip_position = _vector_offset(curves, "transform.clip_offset.position")
    local_position = tuple(
        float(track_position[i]) + float(clip_position[i]) for i in range(3)
    )
    track_rotation = _quat_offset(curves, "transform.track_offset.rotation")
    clip_rotation = _quat_offset(curves, "transform.clip_offset.rotation")
    local_rotation = _quat_mul(track_rotation, clip_rotation)
    parent_position, parent_rotation, parent_scale = parent_world_transform(
        entity, entities
    )
    return compose_canonical_transform(
        parent_position,
        parent_rotation,
        parent_scale,
        local_position,
        local_rotation,
    )


def rotate_unreal_delta_yaw(
    delta_cm: tuple[float, float, float],
    yaw_degrees: float,
) -> tuple[float, float, float]:
    """Rotate an Unreal-space displacement around world-up Z."""
    radians = math.radians(float(yaw_degrees))
    cosine = math.cos(radians)
    sine = math.sin(radians)
    x, y, z = (float(value) for value in delta_cm)
    return (
        cosine * x - sine * y,
        sine * x + cosine * y,
        z,
    )


def _mat_mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)] for r in range(3)]


def _transpose(matrix: list[list[float]]) -> list[list[float]]:
    return [[matrix[c][r] for c in range(3)] for r in range(3)]


def canonical_quat_to_unreal_rotator(
    q: tuple[float, float, float, float]
) -> tuple[float, float, float]:
    """Convert canonical orientation into Unreal semantic Roll/Pitch/Yaw degrees.

    CSIR canonical axes are +X right, +Y up, -Z forward. Unreal actor axes are
    +Y right, +Z up, +X forward. The basis transform below produces the target
    orientation matrix. We then recover Unreal semantics from the transformed
    forward/right basis rather than applying a generic Euler decomposition.

    Unreal Pitch is positive when looking up, so a Unity camera with +X=25°
    (looking down) correctly becomes Unreal Pitch=-25°.
    """
    # An invalid source rotation must never silently become "facing forward".
    # Unity's serialized capture is normalized; allow only small float error.
    try:
        raw = tuple(float(v) for v in q)
    except (TypeError, ValueError) as exc:
        raise PlanError("Canonical rotation quaternion is not numeric.") from exc
    if len(raw) != 4 or not all(math.isfinite(v) for v in raw):
        raise PlanError("Canonical rotation quaternion must have four finite components.")
    norm = math.sqrt(sum(v * v for v in raw))
    if not 0.95 <= norm <= 1.05:
        raise PlanError("Canonical source facing quaternion is not unit length.")

    # Canonical +X -> UE +Y, +Y -> UE +Z, +Z -> UE -X.
    basis = [[0.0, 0.0, -1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    rotation = _mat_mul(_mat_mul(basis, _quat_to_matrix(raw)), _transpose(basis))

    # Matrix columns are the rotated Unreal local X/Y/Z axes in world space.
    forward = (rotation[0][0], rotation[1][0], rotation[2][0])
    right = (rotation[0][1], rotation[1][1], rotation[2][1])

    horizontal = math.hypot(forward[0], forward[1])
    pitch = math.atan2(forward[2], horizontal)
    yaw = math.atan2(forward[1], forward[0])

    sin_pitch = math.sin(pitch)
    cos_pitch = math.cos(pitch)
    sin_yaw = math.sin(yaw)
    cos_yaw = math.cos(yaw)

    # Zero-roll target basis for the resolved forward direction.
    zero_roll_right = (-sin_yaw, cos_yaw, 0.0)
    zero_roll_up = (
        -sin_pitch * cos_yaw,
        -sin_pitch * sin_yaw,
        cos_pitch,
    )

    right_dot_up = sum(right[i] * zero_roll_up[i] for i in range(3))
    right_dot_right = sum(right[i] * zero_roll_right[i] for i in range(3))
    roll = math.atan2(right_dot_up, right_dot_right)

    return (math.degrees(roll), math.degrees(pitch), math.degrees(yaw))


def continuous_unreal_rotator(
    previous: tuple[float, float, float] | None,
    current: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Choose equivalent Roll/Pitch/Yaw angles closest to the previous key.

    Unreal's standard decomposition restricts pitch to [-90, 90]. Crossing
    that pole changes *both* roll and yaw by 180 degrees. Unwrapping each
    channel independently creates a false half-turn between two neighboring
    keys even though the source direction changed only a few degrees.

    The alternate (roll+180, 180-pitch, yaw+180) represents the SAME 3D
    orientation. Choose the closest equivalent triple; no source orientation
    or native actor basis is guessed or calibrated.
    """
    if len(current) != 3 or not all(math.isfinite(float(v)) for v in current):
        raise PlanError("Cannot bake a non-finite Unreal facing rotation.")
    values = tuple(float(v) for v in current)
    if previous is None:
        return values
    if len(previous) != 3 or not all(math.isfinite(float(v)) for v in previous):
        raise PlanError("Previous native facing direction is invalid.")

    def near(value: float, old: float) -> float:
        return old + (value - old + 180.0) % 360.0 - 180.0

    alternatives = (values, (values[0] + 180.0, 180.0 - values[1], values[2] + 180.0))
    candidates = [tuple(near(v, float(p)) for v, p in zip(option, previous))
                  for option in alternatives]
    return min(candidates, key=lambda option: sum(
        (v - float(p)) ** 2 for v, p in zip(option, previous)
    ))


def _section_curve_channels(section: dict[str, Any]) -> tuple[
    dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]
]:
    curves = _curve_map(section)
    position = {axis: curves.get("transform.position." + axis) for axis in "xyz"}
    quaternion = {axis: curves.get("transform.rotation." + axis) for axis in "xyzw"}
    euler = {
        axis: next((c for c in section.get("payload", {}).get("animation", {}).get("curves", [])
                    if not str(c.get("path") or "").strip()
                    and str(c.get("property_name", "")).lower() in {
                        "localeuleranglesraw." + axis,
                        "m_localeulerangleshint." + axis,
                    }), None)
        for axis in "xyz"
    }
    return position, quaternion, euler


def _validate_camera_curve_ownership(section: dict[str, Any]) -> None:
    """Reject unsupported, duplicate or nested camera curve owners.

    Historical conversion silently ignored nested or unknown curves. A
    source-bound full-frame camera trajectory may never omit them.
    """
    curves = section.get("payload", {}).get("animation", {}).get("curves", [])
    if not isinstance(curves, list) or len(curves) > 4096:
        raise PlanError("Camera curve inventory is absent or unbounded.")
    seen = set()
    euler_names = {"localeuleranglesraw."+axis for axis in "xyz"} | {
        "m_localeulerangleshint."+axis for axis in "xyz"
    }
    for curve in curves:
        if not isinstance(curve, dict):
            raise PlanError("Malformed camera source animation curve.")
        if str(curve.get("path") or "").strip():
            raise PlanError("Nested camera/rig curve requires a separate native owner.")
        semantic = str(curve.get("canonical_semantic") or "")
        native = str(curve.get("property_name") or "").lower()
        euler = native if native in euler_names else ""
        allowed = (
            semantic.startswith(("transform.position.", "transform.rotation.",
                                 "transform.track_offset.",
                                 "transform.clip_offset.",
                                 "transform.infinite_offset."))
            or semantic == "camera.vertical_fov_degrees"
            or native == "field of view" or bool(euler)
        )
        if not allowed:
            raise PlanError(
                "Unrecognized animated camera property is not safe to omit: "
                + str(semantic or native)[:100]
            )
        if semantic == "transform.rotation.euler_native" and not euler:
            raise PlanError("Camera native Euler curve has no known source axis.")
        if euler and semantic not in {"", "transform.rotation.euler_native"}:
            raise PlanError("Camera Euler channel semantic and source axis conflict.")
        key = "euler:"+euler if euler else (
            semantic if semantic else "property:"+native
        )
        if key in seen:
            raise PlanError("Duplicate camera source transform property: " + key)
        seen.add(key)
        if any("weighted_mode" in k and int(k["weighted_mode"]) != 0
               for k in curve.get("keys", [])):
            raise PlanError(
                "Weighted camera animation tangents need a dedicated evaluator."
            )


def _sample_section_transform(
    section: dict[str, Any],
    entity: dict[str, Any],
    entities: dict[str, dict[str, Any]],
    fps_n: int,
    fps_d: int,
    *,
    camera_frame_bake: bool = False,
) -> tuple[list[dict[str, Any]], bool]:
    if camera_frame_bake:
        _validate_camera_curve_ownership(section)
    curves = _curve_map(section)
    position_curves, quaternion_curves, euler_curves = _section_curve_channels(section)
    active_curves = [c for c in [*position_curves.values(),
                                 *quaternion_curves.values(), *euler_curves.values()] if c]
    if not active_curves:
        return [], False

    has_quat = any(quaternion_curves.values())
    if has_quat and not all(quaternion_curves.values()):
        raise PlanError("Partial quaternion animation cannot be reconstructed safely.")
    if camera_frame_bake and has_quat and any(euler_curves.values()):
        raise PlanError(
            "Camera quaternion and Euler rotation channels conflict; do not guess an owner."
        )

    source_start = rational_seconds(section.get(
        "source_offset", {"value": 0, "rate": {"numerator": 1, "denominator": 1}}))
    time_scale = float(section.get("time_scale", 1.0))
    if not math.isfinite(time_scale) or time_scale <= 0:
        raise PlanError("Nonfinite or non-positive transform clip speed is unsupported.")
    section_start = rational_seconds(section["start"])
    section_end = rational_seconds(section["end"])
    source_end = source_start + (section_end - section_start) * time_scale
    if (not all(math.isfinite(t) for t in (
            source_start, source_end, section_start, section_end))
            or section_start < 0 or section_end <= section_start):
        raise PlanError("Animated camera source or timeline interval is invalid.")
    bake = camera_frame_bake or any(c.get("native_keys") for c in active_curves)
    if camera_frame_bake:
        # One source-authoritative transform per display frame. Sparse Unity
        # channel keys must not be interpolated again with Unreal auto tangents.
        # Rounding arbitrary Timeline boundaries would silently shift a shot.
        first = seconds_to_frame(section_start, fps_n, fps_d)
        last = seconds_to_frame(section_end, fps_n, fps_d)
        if (last <= first or last-first > 100_000
                or abs(first * fps_d / fps_n - section_start) > 1e-6
                or abs(last * fps_d / fps_n - section_end) > 1e-6):
            raise PlanError(
                "Camera transform clip endpoints must align to source display frames."
            )
    sample_source_times = set()
    for curve in active_curves:
        for key in curve.get("keys", []):
            time_value = float(key["time_seconds"])
            if source_start <= time_value <= source_end:
                sample_source_times.add(time_value)
    if camera_frame_bake:
        sample_source_times = {
            source_start + (frame * fps_d / fps_n - section_start) * time_scale
            for frame in range(first, last + 1)
        }
        # Source-key times MAY be off the display grid. The evaluator uses
        # authored Hermite/legacy-linear values at every actual display frame;
        # never round off-grid authored keys into duplicate native frames.
    else:
        if bake:
            start_frame = seconds_to_frame(section_start, fps_n, fps_d)
            end_frame = seconds_to_frame(section_end, fps_n, fps_d)
            for frame in range(start_frame, end_frame + 1):
                timeline_time = frame * fps_d / fps_n
                if section_start <= timeline_time <= section_end:
                    sample_source_times.add(
                        source_start + (timeline_time - section_start) * time_scale
                    )
            sample_source_times.update((source_start, source_end))
        # Unity holds endpoint values for trimmed clips, even when no authored
        # key falls within their source-time window.
        sample_source_times.update((source_start, source_end))

    track_position = _vector_offset(curves, "transform.track_offset.position")
    infinite_position = _vector_offset(curves, "transform.infinite_offset.position")
    track_rotation = _quat_offset(curves, "transform.track_offset.rotation")
    infinite_rotation = _quat_offset(curves, "transform.infinite_offset.rotation")
    clip_position = (
        _vector_offset(curves, "transform.clip_offset.position")
        if camera_frame_bake else (0.0, 0.0, 0.0)
    )
    clip_rotation = (
        _quat_offset(curves, "transform.clip_offset.rotation")
        if camera_frame_bake else (0.0, 0.0, 0.0, 1.0)
    )
    base_position = tuple(
        track_position[i] + infinite_position[i] + clip_position[i]
        for i in range(3)
    )
    base_rotation = _quat_mul(_quat_mul(track_rotation, clip_rotation), infinite_rotation)
    parent_position, parent_rotation, parent_scale = parent_world_transform(entity, entities)
    fallback_position: tuple[float, float, float] | None = None
    if camera_frame_bake:
        # Track/clip/infinite offsets are static authoring state, not curves
        # whose first key can be quietly substituted for later varying keys.
        for semantic, curve in curves.items():
            if semantic.startswith(("transform.track_offset.",
                                    "transform.clip_offset.",
                                    "transform.infinite_offset.")):
                if len(curve.get("keys", [])) != 1:
                    raise PlanError(
                        "Animated camera offsets need dedicated track-aware ownership."
                    )
        metadata = entity.get("metadata", {}).get("world_transform")
        no_position_offsets = not any(
            semantic.startswith((
                "transform.track_offset.position.",
                "transform.clip_offset.position.",
                "transform.infinite_offset.position.",
            )) for semantic in curves
        )
        no_rotation_offsets = not any(
            semantic.startswith((
                "transform.track_offset.rotation.",
                "transform.clip_offset.rotation.",
                "transform.infinite_offset.rotation.",
            )) for semantic in curves
        )
        needs_position_baseline = (
            no_position_offsets and not all(position_curves.values())
        )
        needs_rotation_baseline = (
            no_rotation_offsets and not has_quat
            and not any(euler_curves.values())
        )
        if needs_position_baseline or needs_rotation_baseline:
            if entity.get("parent_entity_id"):
                raise PlanError(
                    "Parented camera has missing authored local channels; "
                    "cannot substitute a world-space baseline."
                )
            if not isinstance(metadata, dict):
                raise PlanError(
                    "Source camera static world transform is missing for unanimated axes."
                )
            if needs_position_baseline:
                location = metadata.get("position")
                if (not isinstance(location, dict)
                        or any(k not in location for k in "xyz")):
                    raise PlanError(
                        "Source camera baseline position lacks a complete world transform."
                    )
                fallback_position = tuple(float(location[k]) for k in "xyz")
                if any(not math.isfinite(v) for v in fallback_position):
                    raise PlanError("Source camera baseline position is nonfinite.")
            if needs_rotation_baseline:
                orientation = metadata.get("rotation")
                if (not isinstance(orientation, dict)
                        or any(k not in orientation for k in "xyzw")):
                    raise PlanError(
                        "Source camera baseline rotation lacks a complete quaternion."
                    )
                base_rotation = _normalize_quat(
                    tuple(float(orientation[k]) for k in "xyzw")
                )
        if any(abs(v-1) > 1e-5 for v in parent_scale):
            raise PlanError(
                "Animated camera parent scale needs separate native scale calibration."
            )

    by_frame: dict[int, dict[str, Any]] = {}
    for source_time in sorted(sample_source_times):
        timeline_time = section_start + (source_time - source_start) / time_scale
        frame = seconds_to_frame(timeline_time, fps_n, fps_d)
        relative = tuple(_curve_value(position_curves[axis], source_time) for axis in "xyz")
        local_position = tuple(
            base_position[i] + (
                relative[i] if position_curves["xyz"[i]]
                else fallback_position[i] if fallback_position is not None
                else 0.0
            )
            for i in range(3)
        )
        if has_quat:
            sampled = _normalize_quat(tuple(
                _curve_value(quaternion_curves[axis], source_time, 1.0 if axis == "w" else 0.0)
                for axis in "xyzw"))
            delta_q = sampled
        else:
            delta_q = unity_euler_delta_to_canonical_quat(*(
                _curve_value(euler_curves[axis], source_time) for axis in "xyz"))
        local_rotation = _quat_mul(base_rotation, delta_q)
        world_position, world_rotation, _ = compose_canonical_transform(
            parent_position, parent_rotation, parent_scale, local_position, local_rotation)
        if (camera_frame_bake and (
                frame in by_frame
                or frame < first or frame > last
                or not math.isfinite(timeline_time))):
            raise PlanError(
                "Camera sampling collided or escaped exact native display frames."
            )
        by_frame[frame] = {
            "frame": frame,
            "time_seconds": timeline_time,
            "location_cm": canonical_position_to_unreal_cm(world_position),
            "rotation_rpy_degrees": canonical_quat_to_unreal_rotator(world_rotation),
        }
    # Preserve a continuous native facing trajectory across pitch poles.
    # The keys' original quaternion-equivalent directions remain unchanged.
    previous_rpy = None
    result = []
    for frame in sorted(by_frame):
        key = by_frame[frame]
        current_rpy = continuous_unreal_rotator(previous_rpy, key["rotation_rpy_degrees"])
        key["rotation_rpy_degrees"] = current_rpy
        previous_rpy = current_rpy
        result.append(key)
    return result, bake


def _quat_to_matrix_for_rpy(rpy: tuple[float,float,float] | list[float]) -> tuple[float, ...]:
    # A local pure-python matrix avoids guessing Euler equivalence at poles.
    roll, pitch, yaw = (math.radians(v) for v in rpy)
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return (
        cp*cy, -sy*cr - sp*cy*sr, sy*sr - sp*cy*cr,
        cp*sy, cy*cr - sp*sy*sr, -cy*sr - sp*sy*cr,
        sp, cp*sr, cp*cr,
    )


def _transform_action(
    track: dict[str, Any],
    entity: dict[str, Any],
    actor_label: str,
    fps_n: int,
    fps_d: int,
    entities: dict[str, dict[str, Any]],
    *,
    camera_frame_bake: bool = False,
) -> dict[str, Any] | None:
    """Compile every non-overlapping animated section in timeline coordinates."""
    keys_by_frame: dict[int, dict[str, Any]] = {}
    baked = False
    last_end: float | None = None
    sections = sorted(track.get("sections", []), key=lambda s: rational_seconds(s["start"]))
    for section in sections:
        start, end = rational_seconds(section["start"]), rational_seconds(section["end"])
        if last_end is not None and start < last_end - 1e-8:
            raise PlanError(f"Overlapping transform clips on {entity['name']} need explicit blending.")
        if camera_frame_bake and last_end is not None and abs(start-last_end) > 1e-6:
            raise PlanError(
                "Camera clip gaps need explicit hold or extrapolation; never interpolate across gaps."
            )
        section_keys, section_baked = _sample_section_transform(
            section, entity, entities, fps_n, fps_d,
            camera_frame_bake=camera_frame_bake,
        )
        if section_keys:
            baked = baked or section_baked
            for key in section_keys:
                frame = int(key["frame"])
                previous = keys_by_frame.get(frame)
                if previous is not None and camera_frame_bake:
                    if (math.dist(previous["location_cm"], key["location_cm"]) > 1e-4
                            or any(abs(a-b) > 1e-4 for a,b in zip(
                                _quat_to_matrix_for_rpy(
                                    previous["rotation_rpy_degrees"]
                                ),
                                _quat_to_matrix_for_rpy(
                                    key["rotation_rpy_degrees"]
                                ),
                            ))):
                        raise PlanError(
                            "Adjacent camera clips have a discontinuous shared pose; "
                            "a dedicated blend or cut is required."
                        )
                keys_by_frame[frame] = key
        last_end = end
    if not keys_by_frame:
        return None
    sorted_keys = [keys_by_frame[frame] for frame in sorted(keys_by_frame)]
    if camera_frame_bake:
        # Continuous equivalent Euler values must be selected ACROSS sections,
        # not only within each clip, to avoid a pitch-pole 180-degree flip.
        previous_rotation = None
        for key in sorted_keys:
            key["rotation_rpy_degrees"] = continuous_unreal_rotator(
                previous_rotation, key["rotation_rpy_degrees"]
            )
            previous_rotation = key["rotation_rpy_degrees"]
        if sorted_keys[-1]["frame"] - sorted_keys[0]["frame"] + 1 != len(sorted_keys):
            raise PlanError("Animated camera display-frame coverage contains a gap.")
    action = {
        "kind": "transform",
        "track_name": track.get("name", ""),
        "entity_name": entity["name"],
        "actor_label": actor_label,
        "keys": sorted_keys,
        "baked_source_curves": baked,
    }
    if camera_frame_bake:
        action.update({
            "source_behavior_strategy": "source_frame_baked_camera_transform_v1",
            "camera_source_track_id": track.get("track_id"),
            "frame_grid_first": sorted_keys[0]["frame"],
            "frame_grid_last": sorted_keys[-1]["frame"],
            "frame_grid_sample_count": len(sorted_keys),
            "native_transform_channels_required": 9,
            "reopened_cinetwin_verified": False,
            "rendered_camera_motion_verified": False,
        })
    return action



def build_plan(csir: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    if csir.get("schema_version") != "0.1.0":
        raise PlanError(f"Unsupported CSIR schema: {csir.get('schema_version')}")
    if csir.get("source", {}).get("engine") != "unity":
        raise PlanError("Unity-to-Unreal adapter requires a Unity CSIR source; other sources need their own engine adapter.")

    source_rate = csir["timing"]["source_rate"]
    fps_n = int(source_rate["numerator"])
    fps_d = int(source_rate["denominator"])
    duration = float(csir["timing"]["duration_seconds"])
    if (fps_n <= 0 or fps_d <= 0 or not math.isfinite(duration)
            or duration <= 0 or duration > 36000
            or not (1 <= seconds_to_frame(duration, fps_n, fps_d) <= 100_000)):
        raise PlanError("Invalid or unbounded source timeline duration/display rate.")
    validate_mapping_identity(csir, mapping)
    assets = _asset_index(csir)
    entities = _entity_index(csir)
    output_width, output_height, output_profile_source = _target_output_profile(mapping)
    output_aspect = float(output_width) / float(output_height)

    plan: dict[str, Any] = {
        "sequence_asset_path": mapping.get("sequence_asset_path", "/Game/CutSceneAI/Benchmark001/LS_Benchmark001"),
        "overwrite_sequence": bool(mapping.get("overwrite_sequence", False)),
        "display_rate": {"numerator": fps_n, "denominator": fps_d},
        "duration_seconds": duration,
        "duration_frames": seconds_to_frame(duration, fps_n, fps_d),
        "output_resolution": [output_width, output_height],
        "output_aspect": output_aspect,
        "output_profile_source": output_profile_source,
        "bindings": {},
        "actions": [],
    }

    for entity in csir.get("entities", []):
        if entity["name"] in mapping.get("entities", {}):
            plan["bindings"][entity["name"]] = _mapping_actor(mapping, entity["name"])

    for entity_index, entity in enumerate(csir.get("entities", [])):
        if entity.get("ced_type") != "entity.camera":
            continue
        if entity["name"] not in mapping.get("entities", {}):
            continue
        camera = entity.get("metadata", {}).get("camera", {})
        if not isinstance(camera, dict):
            continue
        fov = float(camera.get("field_of_view_degrees", 0.0))
        observed_aspect = float(camera.get("aspect", 0.0))
        if fov <= 0.0:
            continue
        plan["actions"].append(
            {
                "kind": "camera_setup",
                # This action is authored exclusively from this source camera
                # occurrence, not guessed by matching an Unreal actor name.
                "source_location": f"entities[{entity_index}]",
                "source_ced": "entity.camera",
                "entity_name": entity["name"],
                "actor_label": _mapping_actor(mapping, entity["name"]),
                "projection": "orthographic" if bool(camera.get("orthographic", False)) else "perspective",
                "source_fov_axis": "vertical",
                "field_of_view_degrees": fov,
                "target_output_aspect": output_aspect,
                "observed_source_aspect": observed_aspect if observed_aspect > 0.0 else None,
                "near_clip": float(camera.get("near_clip", 0.0)),
                "far_clip": float(camera.get("far_clip", 0.0)),
            }
        )

    # One native camera transform owner per camera. Two separate Unity
    # animation tracks would create competing native transform sections even
    # if their authored curve samples happen to match.
    camera_track_owners: set[str] = set()
    for owner in csir.get("tracks", []):
        if owner.get("muted") is True:
            continue
        ident = owner.get("binding_entity_id")
        camera_entity = entities.get(ident)
        if (camera_entity and camera_entity.get("ced_type") == "entity.camera"
                and owner.get("ced_type") in {"camera.transform", "animation.track"}):
            if ident in camera_track_owners:
                raise PlanError(
                    "Multiple active source camera transform tracks require ownership/blend resolution."
                )
            camera_track_owners.add(ident)

    for track in csir.get("tracks", []):
        # A muted source Timeline track contributes no evaluated behavior.
        # Skipping it must happen in the generator itself, not just in the
        # transfer-readiness report.
        if track.get("muted") is True:
            continue
        entity = entities.get(track.get("binding_entity_id", ""))
        ced_type = track.get("ced_type")

        if ced_type in {"animation.track", "camera.transform"} and entity:
            actor_label = _mapping_actor(mapping, entity["name"])
            if ced_type == "animation.track" and entity.get("ced_type") == "entity.character":
                for section in track.get("sections", []):
                    asset_id = section.get("payload", {}).get("asset_id")
                    asset = assets.get(asset_id)
                    if not asset:
                        continue
                    source_offset_seconds = rational_seconds(section["source_offset"])
                    timeline_duration_seconds = (
                        rational_seconds(section["end"]) - rational_seconds(section["start"])
                    )
                    time_scale = float(section.get("time_scale", 1.0))
                    (
                        _source_world_position,
                        source_world_rotation,
                        _source_world_scale,
                    ) = character_section_world_transform(section, entity, entities)
                    expected_root_delta = _source_root_delta_unreal_cm(
                        section, source_world_rotation
                    )
                    base_roll, base_pitch, base_yaw = canonical_quat_to_unreal_rotator(
                        source_world_rotation
                    )
                    action: dict[str, Any] = {
                        "kind": "skeletal_animation",
                        "track_name": track.get("name", ""),
                        "entity_name": entity["name"],
                        "actor_label": actor_label,
                        "unreal_asset_path": _mapping_asset(mapping, asset["name"]),
                        "start_frame": seconds_to_frame(rational_seconds(section["start"]), fps_n, fps_d),
                        "end_frame": seconds_to_frame(rational_seconds(section["end"]), fps_n, fps_d),
                        "source_start_seconds": source_offset_seconds,
                        "source_end_seconds": source_offset_seconds + timeline_duration_seconds * time_scale,
                        "blend_in_seconds": timeline_clip_easing_seconds(
                            section.get("native_payload", {}), "in"
                        ),
                        "blend_out_seconds": timeline_clip_easing_seconds(
                            section.get("native_payload", {}), "out"
                        ),
                        "time_scale": time_scale,
                        "source_offset_seconds": source_offset_seconds,
                        "base_actor_rotation_rpy_degrees": [
                            float(base_roll),
                            float(base_pitch),
                            float(base_yaw),
                        ],
                        "base_actor_yaw_degrees": float(base_yaw),
                        # CSIR 0.1.5 does not yet preserve Timeline clip extrapolation.
                        # Keep the last evaluated pose rather than inventing a target T-pose.
                        "completion_mode": "keep_state",
                        "completion_provenance": "legacy_csir_missing_post_extrapolation",
                        # KeepState alone does not make a skeletal section evaluate its
                        # final pose after the section range. Unreal post-roll explicitly
                        # holds the last animation frame, so carry the desired hold end.
                        "hold_end_frame": seconds_to_frame(duration, fps_n, fps_d),
                        "hold_strategy": "post_roll_last_frame",
                    }
                    if expected_root_delta is not None:
                        action["expected_root_delta_cm"] = list(expected_root_delta)
                        source_profile = _source_root_profile_unreal_cm(
                            section, source_world_rotation
                        )
                        if source_profile is not None:
                            action["root_motion_source_profile"] = source_profile
                        source_samples = _source_root_samples_unreal_cm(
                            section, source_world_rotation
                        )
                        if source_samples:
                            action["root_motion_source_samples"] = source_samples
                    plan["actions"].append(action)
                continue

            is_camera_transform = (
                entity.get("ced_type") == "entity.camera"
                and ced_type in {"camera.transform", "animation.track"}
            )
            transform = _transform_action(
                track, entity, actor_label, fps_n, fps_d, entities,
                camera_frame_bake=is_camera_transform,
            )
            if transform:
                plan["actions"].append(transform)

            if ced_type == "camera.transform":
                for section in track.get("sections", []):
                    for curve in section.get("payload", {}).get("animation", {}).get("curves", []):
                        if str(curve.get("canonical_semantic", "")) == "camera.vertical_fov_degrees" or str(curve.get("property_name", "")).lower() == "field of view":
                            plan["actions"].append(
                                {
                                    "kind": "camera_fov",
                                    "entity_name": entity["name"],
                                    "actor_label": actor_label,
                                    "source_fov_axis": "vertical",
                                    "target_output_aspect": output_aspect,
                                    "observed_source_aspect": float(
                                        entity.get("metadata", {}).get("camera", {}).get("aspect", 0.0)
                                    )
                                    or None,
                                    "keys": [
                                        {
                                            "frame": frame,
                                            "value": _curve_value(
                                                curve,
                                                rational_seconds(section.get(
                                                    "source_offset", {"value": 0, "rate": {"numerator": 1, "denominator": 1}}
                                                )) + (frame * fps_d / fps_n - rational_seconds(section["start"]))
                                                * float(section.get("time_scale", 1.0)),
                                            ),
                                        }
                                        for frame in (
                                            range(
                                                seconds_to_frame(rational_seconds(section["start"]), fps_n, fps_d),
                                                seconds_to_frame(rational_seconds(section["end"]), fps_n, fps_d) + 1
                                            ) if curve.get("native_keys") else
                                            [seconds_to_frame(float(key["time_seconds"]), fps_n, fps_d)
                                             for key in curve.get("keys", [])]
                                        )
                                    ],
                                    "baked_source_curves": bool(curve.get("native_keys")),
                                }
                            )

        elif ced_type == "camera.cut" and entity:
            for section in track.get("sections", []):
                plan["actions"].append(
                    {
                        "kind": "camera_cut",
                        "entity_name": entity["name"],
                        "actor_label": _mapping_actor(mapping, entity["name"]),
                        "start_frame": seconds_to_frame(rational_seconds(section["start"]), fps_n, fps_d),
                        "end_frame": seconds_to_frame(rational_seconds(section["end"]), fps_n, fps_d),
                    }
                )

        elif ced_type == "light.animation" and entity:
            actor_label = _mapping_actor(mapping, entity["name"])
            for section in track.get("sections", []):
                intensity = next((
                    curve for curve in section.get("payload", {}).get("animation", {}).get("curves", [])
                    if str(curve.get("canonical_semantic", "")) == "light.intensity"
                    or str(curve.get("property_name", "")).lower() in {"m_intensity", "intensity"}
                ), None)
                if intensity is None:
                    raise PlanError(f"Light animation on {entity['name']} has no transferable intensity curve.")
                start = rational_seconds(section["start"])
                end = rational_seconds(section["end"])
                offset = rational_seconds(section.get(
                    "source_offset", {"value": 0, "rate": {"numerator": 1, "denominator": 1}}))
                speed = float(section.get("time_scale", 1.0))
                by_frame: dict[int, dict[str, float | int]] = {}
                for frame in range(seconds_to_frame(start, fps_n, fps_d),
                                   seconds_to_frame(end, fps_n, fps_d) + 1):
                    time = frame * fps_d / fps_n
                    source_time = offset + (time - start) * speed
                    by_frame[frame] = {"frame": frame, "value": _curve_value(intensity, source_time)}
                plan["actions"].append({
                    "kind": "light_intensity",
                    "entity_name": entity["name"],
                    "actor_label": actor_label,
                    "keys": list(by_frame.values()),
                })

        elif ced_type == "audio.track":
            for section in track.get("sections", []):
                asset_id = section.get("payload", {}).get("asset_id")
                asset = assets.get(asset_id)
                if not asset:
                    continue
                plan["actions"].append(
                    {
                        "kind": "audio",
                        "fade_in_seconds": float(section.get("payload", {}).get("audio", {}).get("fade_in", {}).get("duration_seconds", 0.0) or 0.0),
                        "fade_out_seconds": float(section.get("payload", {}).get("audio", {}).get("fade_out", {}).get("duration_seconds", 0.0) or 0.0),
                        "unreal_asset_path": _mapping_asset(mapping, asset["name"]),
                        "start_frame": seconds_to_frame(rational_seconds(section["start"]), fps_n, fps_d),
                        "end_frame": seconds_to_frame(rational_seconds(section["end"]), fps_n, fps_d),
                        "loop": bool(section.get("loop", False)),
                    }
                )

        elif ced_type == "event.trigger":
            for section in track.get("sections", []):
                signal_id = section.get("payload", {}).get("signal", {}).get("signal_asset_id")
                signal = assets.get(signal_id)
                label = signal["name"] if signal else track.get("name", "CutSceneAI_Event")
                plan["actions"].append(
                    {
                        "kind": "marker",
                        "label": label,
                        "frame": seconds_to_frame(rational_seconds(section["start"]), fps_n, fps_d),
                    }
                )

    # Only the final clip of a skeletal binding should hold its last pose.
    # Holding every section through the entire sequence allows post-roll from
    # an earlier clip to compete with later authored animation sections.
    skeletal: dict[str, list[dict[str, Any]]] = {}
    for action in plan["actions"]:
        if action.get("kind") == "skeletal_animation":
            skeletal.setdefault(str(action["entity_name"]), []).append(action)
    for clips in skeletal.values():
        clips.sort(key=lambda action: (int(action["start_frame"]), int(action["end_frame"])))
        for clip in clips[:-1]:
            clip["hold_end_frame"] = int(clip["end_frame"])
            clip["completion_mode"] = "project_default"
            clip["hold_strategy"] = "next_source_clip_controls_pose"

    return plan


def build_plan_from_files(csir_path: str | Path, mapping_path: str | Path) -> dict[str, Any]:
    return build_plan(load_json(csir_path), load_json(mapping_path))
