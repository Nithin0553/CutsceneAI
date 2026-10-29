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


def _asset_index(csir: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {asset["asset_id"]: asset for asset in csir.get("assets", [])}


def _entity_index(csir: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entity["entity_id"]: entity for entity in csir.get("entities", [])}


def _mapping_asset(mapping: dict[str, Any], source_name: str) -> str:
    value = mapping.get("assets", {}).get(source_name)
    if not value:
        raise PlanError(f"No Unreal asset mapping for source asset: {source_name}")
    return str(value)


def _mapping_actor(mapping: dict[str, Any], entity_name: str) -> str:
    entry = mapping.get("entities", {}).get(entity_name)
    if not isinstance(entry, dict) or not entry.get("actor_label"):
        raise PlanError(f"No Unreal actor mapping for source entity: {entity_name}")
    return str(entry["actor_label"])


def _curve_map(section: dict[str, Any]) -> dict[str, dict[str, Any]]:
    curves = section.get("payload", {}).get("animation", {}).get("curves", [])
    result: dict[str, dict[str, Any]] = {}
    for curve in curves:
        semantic = curve.get("canonical_semantic") or curve.get("property_name")
        if semantic:
            result[str(semantic)] = curve
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
    keys = curve["keys"]
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
        str(curve.get("property_name")): curve
        for curve in section.get("payload", {}).get("animation", {}).get("curves", [])
        if str(curve.get("property_name", "")).startswith("RootT.")
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
        str(curve.get("property_name")): curve
        for curve in section.get("payload", {}).get("animation", {}).get("curves", [])
        if str(curve.get("property_name", "")).startswith("RootT.")
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
        str(curve.get("property_name")): curve
        for curve in section.get("payload", {}).get("animation", {}).get("curves", [])
        if str(curve.get("property_name", "")).startswith("RootT.")
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
    if isinstance(value, (list, tuple)) and len(value) == 2:
        width = int(value[0])
        height = int(value[1])
        if width > 0 and height > 0:
            return width, height, "mapping.output_resolution"
    # Benchmark validation needs a stable output gate. Do not reuse Unity Camera.aspect:
    # it is commonly derived from the current editor/game view rather than camera intent.
    return 1920, 1080, "benchmark_default_1920x1080"


def canonical_position_to_unreal_cm(position: tuple[float, float, float]) -> tuple[float, float, float]:
    # CSIR canonical: RH, +Y up, -Z forward, meters.
    # Unreal: LH, +Z up, +X forward, centimeters.
    x, y, z = position
    return (-z * 100.0, x * 100.0, y * 100.0)


def _normalize_quat(q: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    length = math.sqrt(sum(component * component for component in q))
    if length <= 1e-12:
        return (0.0, 0.0, 0.0, 1.0)
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
    parent = entities.get(str(entity.get("parent_entity_id", "")))
    if not parent:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0)

    transform = parent.get("metadata", {}).get("world_transform")
    if not isinstance(transform, dict):
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0)

    position = transform.get("position", {})
    rotation = transform.get("rotation", {})
    scale = transform.get("scale", {})
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
    # Canonical +X -> UE +Y, +Y -> UE +Z, +Z -> UE -X.
    basis = [[0.0, 0.0, -1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    rotation = _mat_mul(_mat_mul(basis, _quat_to_matrix(q)), _transpose(basis))

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


def _section_curve_channels(section: dict[str, Any]) -> tuple[
    dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]
]:
    curves = _curve_map(section)
    position = {axis: curves.get("transform.position." + axis) for axis in "xyz"}
    quaternion = {axis: curves.get("transform.rotation." + axis) for axis in "xyzw"}
    euler = {
        axis: next((c for c in section.get("payload", {}).get("animation", {}).get("curves", [])
                    if str(c.get("property_name", "")).lower() in {
                        "localeuleranglesraw." + axis,
                        "m_localeulerangleshint." + axis,
                    }), None)
        for axis in "xyz"
    }
    return position, quaternion, euler


def _sample_section_transform(
    section: dict[str, Any],
    entity: dict[str, Any],
    entities: dict[str, dict[str, Any]],
    fps_n: int,
    fps_d: int,
) -> tuple[list[dict[str, Any]], bool]:
    curves = _curve_map(section)
    position_curves, quaternion_curves, euler_curves = _section_curve_channels(section)
    active_curves = [c for c in [*position_curves.values(),
                                 *quaternion_curves.values(), *euler_curves.values()] if c]
    if not active_curves:
        return [], False

    has_quat = any(quaternion_curves.values())
    if has_quat and not all(quaternion_curves.values()):
        raise PlanError("Partial quaternion animation cannot be reconstructed safely.")

    source_start = rational_seconds(section.get(
        "source_offset", {"value": 0, "rate": {"numerator": 1, "denominator": 1}}))
    time_scale = float(section.get("time_scale", 1.0))
    if time_scale <= 0:
        raise PlanError("Non-positive transform clip speed is unsupported.")
    section_start = rational_seconds(section["start"])
    section_end = rational_seconds(section["end"])
    source_end = source_start + (section_end - section_start) * time_scale
    bake = any(c.get("native_keys") for c in active_curves)
    sample_source_times = set()
    for curve in active_curves:
        for key in curve.get("keys", []):
            time_value = float(key["time_seconds"])
            if source_start <= time_value <= source_end:
                sample_source_times.add(time_value)
    if bake:
        start_frame = seconds_to_frame(section_start, fps_n, fps_d)
        end_frame = seconds_to_frame(section_end, fps_n, fps_d)
        for frame in range(start_frame, end_frame + 1):
            timeline_time = frame * fps_d / fps_n
            if section_start <= timeline_time <= section_end:
                sample_source_times.add(source_start + (timeline_time - section_start) * time_scale)
        sample_source_times.update((source_start, source_end))
    if not sample_source_times:
        return [], False

    track_position = _vector_offset(curves, "transform.track_offset.position")
    infinite_position = _vector_offset(curves, "transform.infinite_offset.position")
    base_position = tuple(track_position[i] + infinite_position[i] for i in range(3))
    track_rotation = _quat_offset(curves, "transform.track_offset.rotation")
    infinite_rotation = _quat_offset(curves, "transform.infinite_offset.rotation")
    base_rotation = _quat_mul(track_rotation, infinite_rotation)
    parent_position, parent_rotation, parent_scale = parent_world_transform(entity, entities)

    by_frame: dict[int, dict[str, Any]] = {}
    for source_time in sorted(sample_source_times):
        timeline_time = section_start + (source_time - source_start) / time_scale
        frame = seconds_to_frame(timeline_time, fps_n, fps_d)
        relative = tuple(_curve_value(position_curves[axis], source_time) for axis in "xyz")
        local_position = tuple(base_position[i] + relative[i] for i in range(3))
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
        by_frame[frame] = {
            "frame": frame,
            "time_seconds": timeline_time,
            "location_cm": canonical_position_to_unreal_cm(world_position),
            "rotation_rpy_degrees": canonical_quat_to_unreal_rotator(world_rotation),
        }
    return [by_frame[frame] for frame in sorted(by_frame)], bake


def _transform_action(
    track: dict[str, Any],
    entity: dict[str, Any],
    actor_label: str,
    fps_n: int,
    fps_d: int,
    entities: dict[str, dict[str, Any]],
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
        section_keys, section_baked = _sample_section_transform(
            section, entity, entities, fps_n, fps_d)
        if section_keys:
            baked = baked or section_baked
            for key in section_keys:
                keys_by_frame[int(key["frame"])] = key
        last_end = end
    if not keys_by_frame:
        return None
    return {
        "kind": "transform",
        "track_name": track.get("name", ""),
        "entity_name": entity["name"],
        "actor_label": actor_label,
        "keys": [keys_by_frame[frame] for frame in sorted(keys_by_frame)],
        "baked_source_curves": baked,
    }



def build_plan(csir: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    if csir.get("schema_version") != "0.1.0":
        raise PlanError(f"Unsupported CSIR schema: {csir.get('schema_version')}")
    if csir.get("source", {}).get("engine") != "unity":
        raise PlanError("Unity-to-Unreal adapter requires a Unity CSIR source; other sources need their own engine adapter.")

    source_rate = csir["timing"]["source_rate"]
    fps_n = int(source_rate["numerator"])
    fps_d = int(source_rate["denominator"])
    duration = float(csir["timing"]["duration_seconds"])
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

    for entity in csir.get("entities", []):
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

            transform = _transform_action(
                track, entity, actor_label, fps_n, fps_d, entities
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
