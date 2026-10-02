"""Pure-Python validation for CutSceneAI target readback snapshots."""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping


JsonObject = Mapping[str, Any]


DEFAULT_TOLERANCES = {
    "frame": 0,
    "position_m": 1e-4,
    "rotation_deg": 0.05,
    "scale": 1e-4,
    "fov_deg": 0.05,
    "root_motion_cm": 0.1,
}


def _check(
    checks: list[dict[str, Any]],
    check_id: str,
    layer: str,
    status: str,
    expected: Any,
    actual: Any,
    details: str,
    *,
    error: float | None = None,
) -> None:
    item: dict[str, Any] = {
        "id": check_id,
        "layer": layer,
        "status": status,
        "expected": expected,
        "actual": actual,
        "details": details,
    }
    if error is not None:
        item["error"] = float(error)
    checks.append(item)


def _status_from_bool(value: bool) -> str:
    return "PASS" if value else "FAIL"


def _max_abs(values: Iterable[float]) -> float:
    materialized = [abs(float(value)) for value in values]
    return max(materialized) if materialized else 0.0


def _position_error(expected: Iterable[float], actual: Iterable[float]) -> float:
    return _max_abs(float(a) - float(b) for a, b in zip(expected, actual))


def _scale_error(expected: Iterable[float], actual: Iterable[float]) -> float:
    return _position_error(expected, actual)


def _quat_normalize(q: Iterable[float]) -> tuple[float, float, float, float]:
    values = tuple(float(v) for v in q)
    if len(values) != 4:
        raise ValueError("Quaternion must contain four values")
    length = math.sqrt(sum(v * v for v in values))
    if length <= 1e-12:
        return (0.0, 0.0, 0.0, 1.0)
    return tuple(v / length for v in values)  # type: ignore[return-value]


def quaternion_angle_error_degrees(expected: Iterable[float], actual: Iterable[float]) -> float:
    a = _quat_normalize(expected)
    b = _quat_normalize(actual)
    dot = abs(sum(a[i] * b[i] for i in range(4)))
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(2.0 * math.acos(dot))


def _binding_index(snapshot: JsonObject) -> dict[str, JsonObject]:
    return {
        str(binding.get("name", "")): binding
        for binding in snapshot.get("bindings", [])
        if isinstance(binding, Mapping)
    }


def _track_index(binding: JsonObject, kind: str) -> list[JsonObject]:
    return [
        track
        for track in binding.get("tracks", [])
        if isinstance(track, Mapping) and str(track.get("kind", "")) == kind
    ]


def _match_section(
    tracks: list[JsonObject],
    *,
    start_frame: int | None = None,
    end_frame: int | None = None,
    asset_path: str | None = None,
) -> JsonObject | None:
    for track in tracks:
        if start_frame is not None and int(track.get("start_frame", -10**9)) != int(start_frame):
            continue
        if end_frame is not None and int(track.get("end_frame", -10**9)) != int(end_frame):
            continue
        if asset_path is not None and str(track.get("asset_path", "")) != str(asset_path):
            continue
        return track
    return None


def compare(
    expected: JsonObject,
    actual: JsonObject,
    *,
    benchmark: str = "Benchmark001",
    tolerances: JsonObject | None = None,
) -> dict[str, Any]:
    """Compare source-derived target expectations with an engine readback snapshot."""

    tol = dict(DEFAULT_TOLERANCES)
    if tolerances:
        tol.update({str(k): float(v) for k, v in tolerances.items()})

    checks: list[dict[str, Any]] = []

    exp_rate = expected.get("display_rate", {})
    act_rate = actual.get("display_rate", {})
    rate_ok = exp_rate == act_rate
    _check(
        checks,
        "timing.display_rate",
        "TIMING",
        _status_from_bool(rate_ok),
        exp_rate,
        act_rate,
        "Target display rate must preserve the source sequence rate.",
    )

    exp_playback = expected.get("playback", {})
    act_playback = actual.get("playback", {})
    playback_ok = (
        int(exp_playback.get("start_frame", -1)) == int(act_playback.get("start_frame", -2))
        and int(exp_playback.get("end_frame", -1)) == int(act_playback.get("end_frame", -2))
    )
    _check(
        checks,
        "timing.playback_range",
        "TIMING",
        _status_from_bool(playback_ok),
        exp_playback,
        act_playback,
        "Target sequence playback range must match source-derived frames exactly.",
    )

    expected_bindings = _binding_index(expected)
    actual_bindings = _binding_index(actual)

    for name, exp_binding in sorted(expected_bindings.items()):
        act_binding = actual_bindings.get(name)
        exists = act_binding is not None
        _check(
            checks,
            f"structural.binding.{name}",
            "STRUCTURAL",
            _status_from_bool(exists),
            True,
            exists,
            "Mapped source entity must exist as a target sequence binding.",
        )
        if act_binding is None:
            continue

        exp_transform = exp_binding.get("canonical_world_transform")
        act_transform = act_binding.get("canonical_world_transform")
        if isinstance(exp_transform, Mapping):
            if not isinstance(act_transform, Mapping):
                _check(
                    checks,
                    f"spatial.transform.{name}",
                    "SPATIAL",
                    "INCOMPLETE",
                    exp_transform,
                    act_transform,
                    "Target binding did not provide a canonical world transform.",
                )
            else:
                p_error = _position_error(
                    exp_transform.get("position_m", []),
                    act_transform.get("position_m", []),
                )
                _check(
                    checks,
                    f"spatial.position.{name}",
                    "SPATIAL",
                    _status_from_bool(p_error <= tol["position_m"]),
                    exp_transform.get("position_m"),
                    act_transform.get("position_m"),
                    "Canonical world-position comparison.",
                    error=p_error,
                )

                r_error = quaternion_angle_error_degrees(
                    exp_transform.get("rotation_xyzw", [0, 0, 0, 1]),
                    act_transform.get("rotation_xyzw", [0, 0, 0, 1]),
                )
                _check(
                    checks,
                    f"spatial.rotation.{name}",
                    "SPATIAL",
                    _status_from_bool(r_error <= tol["rotation_deg"]),
                    exp_transform.get("rotation_xyzw"),
                    act_transform.get("rotation_xyzw"),
                    "Canonical world-orientation angular error.",
                    error=r_error,
                )

                s_error = _scale_error(
                    exp_transform.get("scale_xyz", []),
                    act_transform.get("scale_xyz", []),
                )
                _check(
                    checks,
                    f"spatial.scale.{name}",
                    "SPATIAL",
                    _status_from_bool(s_error <= tol["scale"]),
                    exp_transform.get("scale_xyz"),
                    act_transform.get("scale_xyz"),
                    "Canonical scale comparison.",
                    error=s_error,
                )

        for exp_track in exp_binding.get("tracks", []):
            if not isinstance(exp_track, Mapping):
                continue
            kind = str(exp_track.get("kind", ""))
            candidates = _track_index(act_binding, kind)

            if kind == "skeletal_animation":
                match = _match_section(
                    candidates,
                    start_frame=int(exp_track["start_frame"]),
                    end_frame=int(exp_track["end_frame"]),
                    asset_path=str(exp_track["asset_path"]),
                )
                _check(
                    checks,
                    f"animation.section.{name}",
                    "ANIMATION",
                    _status_from_bool(match is not None),
                    dict(exp_track),
                    dict(match) if match else None,
                    "Skeletal animation asset and section range must match.",
                )
                if match is not None and "effective_root_delta_cm" in exp_track:
                    actual_delta = match.get("effective_root_delta_cm")
                    if actual_delta is None:
                        _check(
                            checks,
                            f"animation.root_motion.{name}",
                            "ANIMATION",
                            "INCOMPLETE",
                            exp_track.get("effective_root_delta_cm"),
                            None,
                            "Readback could not measure effective root-motion displacement.",
                        )
                    else:
                        root_error = _position_error(
                            exp_track["effective_root_delta_cm"], actual_delta
                        )
                        _check(
                            checks,
                            f"animation.root_motion.{name}",
                            "ANIMATION",
                            _status_from_bool(root_error <= tol["root_motion_cm"]),
                            exp_track["effective_root_delta_cm"],
                            actual_delta,
                            "Effective target root trajectory displacement.",
                            error=root_error,
                        )

            elif kind == "transform":
                match = candidates[0] if candidates else None
                _check(
                    checks,
                    f"spatial.transform_track.{name}",
                    "SPATIAL",
                    _status_from_bool(match is not None),
                    True,
                    match is not None,
                    "Expected transform track must be present.",
                )
                if match is not None:
                    exp_keys = list(exp_track.get("keys", []))
                    act_keys = list(match.get("keys", []))
                    frame_ok = [int(k.get("frame", -1)) for k in exp_keys] == [
                        int(k.get("frame", -2)) for k in act_keys
                    ]
                    _check(
                        checks,
                        f"timing.transform_keys.{name}",
                        "TIMING",
                        _status_from_bool(frame_ok),
                        [k.get("frame") for k in exp_keys],
                        [k.get("frame") for k in act_keys],
                        "Transform key times must be preserved.",
                    )
                    if frame_ok and len(exp_keys) == len(act_keys):
                        worst_position = 0.0
                        worst_rotation = 0.0
                        for exp_key, act_key in zip(exp_keys, act_keys):
                            worst_position = max(
                                worst_position,
                                _position_error(
                                    exp_key.get("position_m", []),
                                    act_key.get("position_m", []),
                                ),
                            )
                            worst_rotation = max(
                                worst_rotation,
                                quaternion_angle_error_degrees(
                                    exp_key.get("rotation_xyzw", [0, 0, 0, 1]),
                                    act_key.get("rotation_xyzw", [0, 0, 0, 1]),
                                ),
                            )
                        _check(
                            checks,
                            f"spatial.transform_key_positions.{name}",
                            "SPATIAL",
                            _status_from_bool(worst_position <= tol["position_m"]),
                            "source-derived canonical transform keys",
                            "target-readback canonical transform keys",
                            "Maximum canonical transform-key position error.",
                            error=worst_position,
                        )
                        _check(
                            checks,
                            f"spatial.transform_key_rotations.{name}",
                            "SPATIAL",
                            _status_from_bool(worst_rotation <= tol["rotation_deg"]),
                            "source-derived canonical rotation keys",
                            "target-readback canonical rotation keys",
                            "Maximum canonical transform-key angular error.",
                            error=worst_rotation,
                        )

            elif kind == "camera_lens":
                match = candidates[0] if candidates else None
                _check(
                    checks,
                    f"camera.lens_track.{name}",
                    "CAMERA",
                    _status_from_bool(match is not None),
                    True,
                    match is not None,
                    "Expected camera lens track must be present.",
                )
                if match is not None:
                    exp_keys = list(exp_track.get("keys", []))
                    act_keys = list(match.get("keys", []))
                    frames_ok = [int(k.get("frame", -1)) for k in exp_keys] == [
                        int(k.get("frame", -2)) for k in act_keys
                    ]
                    values_error = math.inf
                    if frames_ok and len(exp_keys) == len(act_keys):
                        values_error = _max_abs(
                            float(a.get("vertical_fov_degrees", 0.0))
                            - float(b.get("vertical_fov_degrees", 0.0))
                            for a, b in zip(exp_keys, act_keys)
                        )
                    _check(
                        checks,
                        f"camera.lens_keys.{name}",
                        "CAMERA",
                        _status_from_bool(frames_ok and values_error <= tol["fov_deg"]),
                        exp_keys,
                        act_keys,
                        "Camera lens keys compared in vertical-FOV semantic space.",
                        error=None if math.isinf(values_error) else values_error,
                    )

    def _sorted(items: Iterable[Mapping[str, Any]], fields: tuple[str, ...]) -> list[tuple[Any, ...]]:
        return sorted(tuple(item.get(field) for field in fields) for item in items)

    exp_cuts = _sorted(expected.get("camera_cuts", []), ("start_frame", "end_frame", "camera_binding"))
    act_cuts = _sorted(actual.get("camera_cuts", []), ("start_frame", "end_frame", "camera_binding"))
    _check(
        checks,
        "camera.cuts",
        "CAMERA",
        _status_from_bool(exp_cuts == act_cuts),
        exp_cuts,
        act_cuts,
        "Camera identity and cut ranges must match exactly.",
    )

    exp_audio = _sorted(expected.get("audio_sections", []), ("start_frame", "end_frame", "asset_path", "loop"))
    act_audio = _sorted(actual.get("audio_sections", []), ("start_frame", "end_frame", "asset_path", "loop"))
    _check(
        checks,
        "audio.sections",
        "AUDIO_EVENT",
        _status_from_bool(exp_audio == act_audio),
        exp_audio,
        act_audio,
        "Mapped audio asset and timing must match exactly.",
    )

    exp_markers = _sorted(expected.get("markers", []), ("frame", "label"))
    act_markers = _sorted(actual.get("markers", []), ("frame", "label"))
    _check(
        checks,
        "event.markers",
        "AUDIO_EVENT",
        _status_from_bool(exp_markers == act_markers),
        exp_markers,
        act_markers,
        "Event/marker identity and timing must match exactly.",
    )

    passed = sum(1 for item in checks if item["status"] == "PASS")
    failed = sum(1 for item in checks if item["status"] == "FAIL")
    incomplete = sum(1 for item in checks if item["status"] == "INCOMPLETE")
    status = "FAIL" if failed else ("INCOMPLETE" if incomplete else "PASS")

    return {
        "schema_version": "0.1.0",
        "benchmark": benchmark,
        "status": status,
        "summary": {
            "passed": passed,
            "failed": failed,
            "incomplete": incomplete,
        },
        "checks": checks,
    }
