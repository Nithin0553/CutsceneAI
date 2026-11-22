"""Source-bound eligibility for a static, unparented CineCamera placement repair.

Pure evidence review. A user may request one measured constant camera offset;
the AI never supplies a position, actor identity, executable script or native
permission. A later reopened CineTwin comparison remains mandatory.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import studio_element7_readback as readback
import studio_element8_repair as repair
import studio_element9_outcome as outcome

KIND = "cutsceneai.studio.static_camera_position_review"
POSITION_TOLERANCE_CM = 2.0
MAX_TRANSLATION_CM = 500.0
STATIC_DRIFT_CM = 0.1
ROTATION_TOLERANCE_DEGREES = 0.5
_FIX = re.compile(r"\b(?:fix|correct|repair|adjust|restore|align|reposition|move)\b", re.I)
_CAMERA = re.compile(r"\b(?:camera|cinecamera)\b", re.I)
_PLACE = re.compile(r"\b(?:position|placement|location|translation|offset)\b", re.I)
_UNSAFE = re.compile(
    r"\b(?:cut|cuts|shot|shots|fov|zoom|lens|focus|exposure|"
    r"rotation|rotate|facing|orientation|animation|animated|keyframe|"
    r"trajectory|tracking|moving|dolly|pan|rig|character|skeletal)\b", re.I,
)
_NEGATE = re.compile(r"\b(?:do not|don't|dont|without)\s+"
                     r"(?:modify|edit|move|fix|repair|correct|adjust)", re.I)


class StaticCameraPositionError(ValueError):
    """Position correction lacks independent source/native authorization."""


def _hash(data: Any) -> str:
    return hashlib.sha256(json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def message_requests_position(message: Any) -> bool:
    return (
        isinstance(message, str) and 0 < len(message) <= 1200
        and bool(_FIX.search(message) and _CAMERA.search(message)
                 and _PLACE.search(message))
        and not bool(_UNSAFE.search(message) or _NEGATE.search(message))
        and "\x00" not in message
    )


def _vector(record: Any, key: str, count: int) -> tuple[float, ...]:
    value = record.get(key) if isinstance(record, dict) else None
    if (not isinstance(value, (tuple, list)) or len(value) != count
            or any(type(v) not in (int, float) for v in value)
            or any(not math.isfinite(v) or abs(v) > 100000 for v in value)):
        raise StaticCameraPositionError("Invalid sampled " + key + ".")
    return tuple(float(x) for x in value)


def _angle(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    norms = (math.sqrt(sum(v*v for v in x)) for x in (a, b))
    la, lb = norms
    if abs(la-1) > 0.02 or abs(lb-1) > 0.02:
        raise StaticCameraPositionError("Camera quaternion is not normalized.")
    cosine = abs(sum(x*y for x, y in zip(a, b))/(la*lb))
    return math.degrees(2 * math.acos(min(1.0, max(-1.0, cosine))))


def _one_camera(frame: Any, entity_id: str, *, label: str | None = None) -> dict:
    rows = [item for item in frame.get("entities", [])
            if isinstance(item, dict) and item.get("entity_id") == entity_id]
    if len(rows) != 1 or (label is not None and rows[0].get("actor_label") != label):
        raise StaticCameraPositionError("Exactly one mapped camera is required at each frame.")
    return rows[0]


def build(workspace: Path, job: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(job, dict):
        raise StaticCameraPositionError("Missing native job.")
    try:
        root, candidate, canonical, csir, mapping, compiled = outcome._context(
            workspace, job.get("job_id"),
        )
        if job != canonical:
            raise StaticCameraPositionError("Stale camera job.")
        folders = outcome.discover(root, job["job_id"])
        if not folders:
            raise StaticCameraPositionError("Reopened native CineTwin baseline is missing.")
        bounded = repair.build(root, job["job_id"], folders)
        native = readback.build(root, job["job_id"], folders[-1])
        source, _ = readback._safe_json(Path(job["capture"]))
        target, _ = readback._safe_json(folders[-1] / "target-behavior.json")
    except (outcome.OutcomeError, repair.BoundedRepairError,
            readback.Element7ReadbackError, OSError, ValueError, KeyError,
            TypeError) as exc:
        raise StaticCameraPositionError(
            "Independent source/native camera placement evidence failed."
        ) from exc
    if (bounded.get("status") in {
            "STOP_MEASURED_REGRESSION_OR_NO_PROGRESS",
            "STOP_REMEASUREMENT_BUDGET_EXHAUSTED",
        } or native.get("camera_lens_status") != "PASS"
            or native.get("camera_cuts_status") not in {"PASS", "NOT_APPLICABLE"}):
        raise StaticCameraPositionError(
            "Another cinematic domain is unresolved or the repair budget stopped."
        )
    cameras = [row for row in csir.get("entities", [])
               if isinstance(row, dict) and row.get("ced_type") == "entity.camera"]
    if len(cameras) != 1:
        raise StaticCameraPositionError("One source camera is required.")
    camera = cameras[0]
    name, ident = camera.get("name"), camera.get("entity_id")
    mapping_entry = (mapping.get("entities") or {}).get(name)
    label = mapping_entry.get("actor_label") if isinstance(mapping_entry, dict) else None
    if (not isinstance(name, str) or not name or len(name) > 128
            or not isinstance(ident, str) or not ident
            or not isinstance(label, str) or not label or len(label) > 256):
        raise StaticCameraPositionError("Camera source/target binding is ambiguous.")
    # Reject even static-looking source curves and known native transform
    # actions: a constant observed frame grid is NOT proof of track ownership.
    if any(
        row.get("binding_entity_id") == ident
        and row.get("ced_type") != "camera.cut"
        for row in csir.get("tracks", []) if isinstance(row, dict)
    ) or any(
        row.get("kind") in {"transform", "actor_transform", "camera_transform",
                             "property_float", "camera_fov"}
        for row in compiled.get("actions", []) if isinstance(row, dict)
    ):
        raise StaticCameraPositionError(
            "Authored/native property or transform track may own the camera placement."
        )
    src_frames, dst_frames = source.get("samples"), target.get("samples")
    if (not isinstance(src_frames, list) or not isinstance(dst_frames, list)
            or len(src_frames) != len(dst_frames) or len(src_frames) < 2):
        raise StaticCameraPositionError("Complete camera time grid is required.")
    first_src = first_dst = None
    offsets = []
    for src_frame, dst_frame in zip(src_frames, dst_frames):
        if src_frame.get("time_seconds") != dst_frame.get("time_seconds"):
            raise StaticCameraPositionError("Camera time grid no longer matches.")
        src = _one_camera(src_frame, ident)["world_transform"]
        dst = _one_camera(dst_frame, ident, label=label)["world_transform"]
        a, b = _vector(src, "position_m", 3), _vector(dst, "position_m", 3)
        ar, br = _vector(src, "rotation_xyzw", 4), _vector(dst, "rotation_xyzw", 4)
        sa, sb = _vector(src, "scale_xyz", 3), _vector(dst, "scale_xyz", 3)
        if (_angle(ar, br) > ROTATION_TOLERANCE_DEGREES
                or max(abs(x-y) for x, y in zip(sa, sb)) > 0.01):
            raise StaticCameraPositionError(
                "Camera rotation/scale mismatch cannot be repaired by translation."
            )
        if first_src is None:
            first_src, first_dst = a, b
        if (math.dist(a, first_src)*100 > STATIC_DRIFT_CM
                or math.dist(b, first_dst)*100 > STATIC_DRIFT_CM):
            raise StaticCameraPositionError(
                "Moving/animated cameras require a separate track-aware repair."
            )
        offsets.append(tuple((x-y)*100 for x, y in zip(a, b)))
    offset = offsets[0]
    magnitude = math.dist(offset, (0, 0, 0))
    if (not POSITION_TOLERANCE_CM < magnitude <= MAX_TRANSLATION_CM
            or max(math.dist(offset, row) for row in offsets) > STATIC_DRIFT_CM):
        raise StaticCameraPositionError(
            "Camera offset is small, changing over time or outside safe limits."
        )
    workflow = repair._snapshot(candidate)
    if workflow is None:
        raise StaticCameraPositionError("Missing source-occurrence identity.")
    occurrence = [
        row["occurrence_id"] for row in workflow["element_plan"]["elements"]
        if row.get("source_kind") == "entities"
        and row.get("source_location")
        == "entities[" + str(csir["entities"].index(camera)) + "]"
    ]
    measured = [
        row for row in bounded["per_occurrence"]
        if row["occurrence_id"] in occurrence
    ]
    if (len(occurrence) != 1 or len(measured) != 1
            or measured[0]["latest_status"] != "DIRECT_MEASURED_DIFFERENCE"
            or measured[0]["latest_discrepancy_flags"]
            != ["WORLD_POSITION_OUTSIDE_TOLERANCE"]):
        raise StaticCameraPositionError(
            "CineTwin does not attribute an isolated position mismatch to this camera."
        )
    # Canonical XYZ -> Unreal centimeters: (-Z, X, Y). No model-authored
    # numbers or imported camera-local offsets enter the native write.
    before = (-first_dst[2]*100, first_dst[0]*100, first_dst[1]*100)
    ue_delta = (-offset[2], offset[0], offset[1])
    report = {
        "kind": KIND, "eligible": True,
        "source_camera_name": name, "source_entity_id": ident,
        "target_actor_label": label,
        "source_camera_occurrence_id": occurrence[0],
        "native_world_before_cm": [round(v, 6) for v in before],
        "unreal_offset_cm": [round(v, 6) for v in ue_delta],
        "max_world_offset_cm": magnitude,
        "element7_latest_sha256": native["readback_sha256"],
        "element8_repair_sha256": bounded["repair_plan_sha256"],
        "sample_count": len(src_frames),
        "native_edit_authorized": False,
        "cinetwin_reopened_verified": False,
        "full_cutscene_fidelity_verified": False,
    }
    report["camera_position_repair_sha256"] = _hash(report)
    return report
