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


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
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
            return float(left["value"]) + (float(right["value"]) - float(left["value"])) * alpha
    return default


def _source_root_delta_unreal_cm(section: dict[str, Any]) -> tuple[float, float, float] | None:
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
    return canonical_position_to_unreal_cm(canonical_delta)


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


def _transform_action(
    track: dict[str, Any], entity: dict[str, Any], actor_label: str, fps_n: int, fps_d: int
) -> dict[str, Any] | None:
    if not track.get("sections"):
        return None
    section = track["sections"][0]
    curves = _curve_map(section)

    track_position = _vector_offset(curves, "transform.track_offset.position")
    infinite_position = _vector_offset(curves, "transform.infinite_offset.position")
    base_position = tuple(track_position[i] + infinite_position[i] for i in range(3))

    track_rotation = _quat_offset(curves, "transform.track_offset.rotation")
    infinite_rotation = _quat_offset(curves, "transform.infinite_offset.rotation")
    base_rotation = _quat_mul(track_rotation, infinite_rotation)

    position_curves = {
        "x": curves.get("transform.position.x"),
        "y": curves.get("transform.position.y"),
        "z": curves.get("transform.position.z"),
    }
    euler_curves = {
        "x": next((c for c in section["payload"]["animation"]["curves"] if c.get("property_name") == "localEulerAnglesRaw.x"), None),
        "y": next((c for c in section["payload"]["animation"]["curves"] if c.get("property_name") == "localEulerAnglesRaw.y"), None),
        "z": next((c for c in section["payload"]["animation"]["curves"] if c.get("property_name") == "localEulerAnglesRaw.z"), None),
    }

    times: set[float] = set()
    for curve in [*position_curves.values(), *euler_curves.values()]:
        if curve:
            times.update(float(key["time_seconds"]) for key in curve.get("keys", []))
    if not times:
        return None

    keys: list[dict[str, Any]] = []
    for time_seconds in sorted(times):
        relative_position = (
            _curve_value(position_curves["x"], time_seconds),
            _curve_value(position_curves["y"], time_seconds),
            _curve_value(position_curves["z"], time_seconds),
        )
        absolute_position = tuple(base_position[i] + relative_position[i] for i in range(3))

        delta_q = unity_euler_delta_to_canonical_quat(
            _curve_value(euler_curves["x"], time_seconds),
            _curve_value(euler_curves["y"], time_seconds),
            _curve_value(euler_curves["z"], time_seconds),
        )
        absolute_q = _quat_mul(base_rotation, delta_q)
        keys.append(
            {
                "frame": seconds_to_frame(time_seconds, fps_n, fps_d),
                "time_seconds": time_seconds,
                "location_cm": canonical_position_to_unreal_cm(absolute_position),
                "rotation_rpy_degrees": canonical_quat_to_unreal_rotator(absolute_q),
            }
        )

    return {
        "kind": "transform",
        "track_name": track.get("name", ""),
        "entity_name": entity["name"],
        "actor_label": actor_label,
        "keys": keys,
    }


def build_plan(csir: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    if csir.get("schema_version") != "0.1.0":
        raise PlanError(f"Unsupported CSIR schema: {csir.get('schema_version')}")
    if csir.get("source", {}).get("engine") != "unity":
        raise PlanError("Benchmark001 Unreal generator currently expects a Unity CSIR source.")

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
                    expected_root_delta = _source_root_delta_unreal_cm(section)
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
                        "time_scale": time_scale,
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
                    plan["actions"].append(action)
                continue

            transform = _transform_action(track, entity, actor_label, fps_n, fps_d)
            if transform:
                plan["actions"].append(transform)

            if ced_type == "camera.transform":
                for section in track.get("sections", []):
                    for curve in section.get("payload", {}).get("animation", {}).get("curves", []):
                        if str(curve.get("property_name", "")).lower() == "field of view":
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
                                            "frame": seconds_to_frame(float(key["time_seconds"]), fps_n, fps_d),
                                            "value": float(key["value"]),
                                        }
                                        for key in curve.get("keys", [])
                                    ],
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

        elif ced_type == "audio.track":
            for section in track.get("sections", []):
                asset_id = section.get("payload", {}).get("asset_id")
                asset = assets.get(asset_id)
                if not asset:
                    continue
                plan["actions"].append(
                    {
                        "kind": "audio",
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

    return plan


def build_plan_from_files(csir_path: str | Path, mapping_path: str | Path) -> dict[str, Any]:
    return build_plan(load_json(csir_path), load_json(mapping_path))
