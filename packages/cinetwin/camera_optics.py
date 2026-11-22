"""Source-aligned physical camera optics readback and comparison.

Unreal uses a CineCamera filmback sensor and focal length; Unity's camera
capture reports vertical field of view. Derive the *target* vertical FOV from
observed native physical lens properties, never from an assumed viewport
aspect ratio or a horizontal-FOV value. This does not verify framing, aperture,
post-processing, cut order or rendered image equivalence.
"""
from __future__ import annotations

import math
from typing import Any

NATIVE_BASIS = "UNREAL_CINE_CAMERA_SENSOR_HEIGHT_AND_FOCAL_LENGTH"
LENS_TOLERANCE_DEGREES = 0.25


class CameraOpticsError(ValueError):
    """Invalid or altered lens evidence; comparison must fail closed."""


def _positive(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise CameraOpticsError(field + " must be finite and positive.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CameraOpticsError(field + " must be numeric.") from exc
    if not math.isfinite(result) or result <= 0:
        raise CameraOpticsError(field + " must be finite and positive.")
    return result


def _vertical_fov(height: float, focal: float) -> float:
    result = math.degrees(2.0 * math.atan(height / (2.0 * focal)))
    if not 0.1 <= result < 179.0:
        raise CameraOpticsError("Physical lens produced an unsupported vertical FOV.")
    return result


def observe_native_camera(actor: Any) -> dict[str, Any]:
    """Read an actual Unreal CineCameraComponent without changing anything.

    Unsupported native actor/API shapes are explicitly UNAVAILABLE, not
    reinterpreted as a verified camera from a guessed aspect ratio.
    """
    get_component = getattr(actor, "get_cine_camera_component", None)
    if not callable(get_component):
        return {"status": "UNAVAILABLE", "reason": "NOT_NATIVE_CINE_CAMERA_ACTOR"}
    try:
        component = get_component()
        if component is None:
            return {"status": "UNAVAILABLE", "reason": "CINE_CAMERA_COMPONENT_MISSING"}
        filmback = component.get_editor_property("filmback")
        sensor_height = _positive(
            filmback.get_editor_property("sensor_height"), "native sensor height"
        )
        focal = _positive(
            component.get_editor_property("current_focal_length"), "native focal length"
        )
        vertical = _vertical_fov(sensor_height, focal)
    except (AttributeError, TypeError, ValueError, CameraOpticsError):
        return {"status": "UNAVAILABLE", "reason": "NATIVE_LENS_PROPERTIES_UNVERIFIED"}
    return {
        "status": "OBSERVED",
        "lens_basis": NATIVE_BASIS,
        "sensor_height_mm": sensor_height,
        "focal_length_mm": focal,
        "vertical_fov_degrees": vertical,
    }


def compare_camera_optics(
    plan: dict[str, Any],
    source_samples: list[dict[str, Any]],
    target_samples: list[dict[str, Any]],
    *,
    tolerance_degrees: float = LENS_TOLERANCE_DEGREES,
) -> dict[str, Any]:
    """Measure camera lens differences at the *already-verified* source grid.

    Caller must have verified sample count/times, source capture, and target
    entity identity. A missing camera is incomplete, never a matching lens.
    Native physical lens fields are cross-checked against the claimed FOV.
    """
    tolerance = _positive(tolerance_degrees, "lens tolerance")
    cameras = [e for e in plan["entities"] if e.get("ced_type") == "entity.camera"]
    if len({e["entity_id"] for e in cameras}) != len(cameras):
        raise CameraOpticsError("Repeated source camera identity.")
    if len(source_samples) != len(target_samples):
        raise CameraOpticsError("Lens samples are not frame-aligned.")
    rows = []
    for entity in cameras:
        entity_id = entity["entity_id"]
        errors = []
        missing = []
        for index, (source, target) in enumerate(zip(source_samples, target_samples)):
            original = next((e for e in source["entities"] if e["entity_id"] == entity_id), None)
            sampled = next((e for e in target["entities"] if e["entity_id"] == entity_id), None)
            if original is None:
                raise CameraOpticsError("Verified source camera disappeared at a sample.")
            fov = _positive(
                (original.get("camera") or {}).get("vertical_fov_degrees"),
                "source camera vertical FOV",
            )
            if not fov < 179.0:
                raise CameraOpticsError("Source camera vertical FOV is outside valid bounds.")
            observed = sampled.get("camera") if sampled is not None else None
            if observed is None:
                missing.append("UNMAPPED_OR_MISSING_NATIVE_CAMERA")
                continue
            if not isinstance(observed, dict) or observed.get("status") != "OBSERVED":
                missing.append(
                    str(observed.get("reason") or "UNVERIFIED_NATIVE_CAMERA")
                    if isinstance(observed, dict) else "INVALID_NATIVE_CAMERA_RECORD"
                )
                continue
            if observed.get("lens_basis") != NATIVE_BASIS:
                raise CameraOpticsError("Unapproved or missing native physical lens basis.")
            height = _positive(observed.get("sensor_height_mm"), "target sensor height")
            focal = _positive(observed.get("focal_length_mm"), "target focal length")
            reported = _positive(
                observed.get("vertical_fov_degrees"), "target vertical FOV"
            )
            physical = _vertical_fov(height, focal)
            if abs(reported - physical) > 1e-4:
                raise CameraOpticsError("Target FOV conflicts with sampled native lens properties.")
            errors.append((abs(fov - physical), float(source["time_seconds"])))
        maximum = max((item[0] for item in errors), default=None)
        if maximum is not None and maximum > tolerance:
            status = "FAIL"
        elif missing or len(errors) != len(source_samples):
            status = "INCOMPLETE"
        else:
            status = "PASS"
        worst = max(errors, default=None)
        rows.append({
            "source_entity_id": entity_id,
            "status": status,
            "requested_frames": len(source_samples),
            "comparable_frames": len(errors),
            "missing_frames": len(source_samples) - len(errors),
            "max_vertical_fov_error_degrees": round(maximum, 6) if maximum is not None else None,
            "worst_time_seconds": worst[1] if worst is not None else None,
            "unavailable_reasons": sorted(set(missing)),
        })
    if not rows:
        status = "NOT_APPLICABLE"
    elif any(row["status"] == "FAIL" for row in rows):
        status = "FAIL"
    elif all(row["status"] == "PASS" for row in rows):
        status = "PASS"
    else:
        status = "INCOMPLETE"
    return {
        "status": status,
        "source_camera_count": len(rows),
        "sample_count": len(source_samples),
        "vertical_fov_tolerance_degrees": tolerance,
        "lens_basis": NATIVE_BASIS,
        "per_camera": rows,
        "independent_native_lens_observation_required": True,
        "rendered_projection_verified": False,
        "shot_cut_timing_verified": False,
    }
