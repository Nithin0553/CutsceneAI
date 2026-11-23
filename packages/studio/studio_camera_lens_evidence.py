"""Source-bound static CineCamera focal-length repair eligibility (read-only).

A fully sampled, user-requested camera FOV mismatch may have a safe static
property correction. It is NEVER enough to guess animation key edits, change
filmback, rewrite cuts, or claim rendered equivalence. Exact Element 7/8
evidence and the original immutable source/target compiler are authority.
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

KIND = "cutsceneai.studio.static_camera_lens_review"
MAX_FOV_DELTA = 35.0
MAX_SOURCE_FOV_DRIFT = 0.05
MAX_NATIVE_FOCAL_DRIFT_MM = 0.05
MAX_SENSOR_DRIFT_MM = 0.01
MAX_ALLOWED_FOCAL_MM = 400.0
TOLERANCE_DEGREES = 0.25
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_USER_LENS = re.compile(r"\b(?:fov|field of view|focal|lens|zoom)\b", re.IGNORECASE)
_USER_FIX = re.compile(r"\b(?:fix|repair|correct|adjust|restore)\b", re.IGNORECASE)
_USER_NEGATE = re.compile(r"\b(?:do not|don't|dont|without)\s+"
                          r"(?:modify|edit|change|fix|repair|correct|adjust)",
                          re.IGNORECASE)
# The user must request ONLY static lens correction, not a multi-domain shot,
# camera cut or animation rewrite that this single component cannot solve.
_UNSUPPORTED_REQUEST = re.compile(
    r"\b(?:cuts?|shots?|timing|switch|switching|blend|blending|"
    r"animation|animate|keyframes?|movement|moving|rotate|rotation)\b", re.I,
)


class CameraLensEvidenceError(ValueError):
    """No exact-source bounded static-lens repair is permitted."""


def _hash(data: Any) -> str:
    return hashlib.sha256(json.dumps(
        data, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _finite(number: Any, field: str) -> float:
    if type(number) not in (int, float) or not math.isfinite(number):
        raise CameraLensEvidenceError("Missing finite " + field + " observation.")
    return float(number)


def message_requests_lens(message: Any) -> bool:
    return (
        isinstance(message, str) and 0 < len(message) <= 1200
        and bool(_USER_LENS.search(message) and _USER_FIX.search(message))
        and not bool(_USER_NEGATE.search(message)
                     or _UNSUPPORTED_REQUEST.search(message))
        and "\x00" not in message
    )


def _latest_folders(workspace: Path, job_id: str) -> list[Path]:
    # The canonical Element 9 discoverer refuses partial native folders.
    # Filtering only files ending in 'element7-readback.json' would silently
    # ignore a failed/incomplete capture and reuse an older clean baseline.
    try:
        folders = outcome.discover(workspace, job_id)
    except (outcome.OutcomeError, OSError, ValueError) as exc:
        raise CameraLensEvidenceError(
            "Native camera baseline includes incomplete or foreign captures."
        ) from exc
    if not folders:
        raise CameraLensEvidenceError(
            "A source-bound reopened CineTwin capture is required."
        )
    return folders


def build(workspace: Path, job: dict[str, Any]) -> dict[str, Any]:
    """Derive one static lens correction from measured source frames alone.

    No model/user-controlled offsets, source camera selection, actor labels,
    FOV, filmback or focal length are accepted as executable parameters.
    """
    if not isinstance(job, dict):
        raise CameraLensEvidenceError("Malformed native job.")
    job_id = job.get("job_id")
    root, candidate, canonical, csir, mapping, compiled = _context(
        workspace, job_id,
    )
    if job != canonical:
        raise CameraLensEvidenceError("Native job changed before camera review.")
    folders = _latest_folders(root, job_id)
    try:
        bounded = repair.build(root, job_id, folders)
        native = readback.build(root, job_id, folders[-1])
        if (bounded["status"] in {
            "STOP_MEASURED_REGRESSION_OR_NO_PROGRESS",
            "STOP_REMEASUREMENT_BUDGET_EXHAUSTED",
        } or native["camera_lens_status"] != "FAIL"):
            raise CameraLensEvidenceError(
                "The bounded native comparison does not permit a static lens change."
            )
        source, _ = readback._safe_json(Path(job["capture"]))
        target, _ = readback._safe_json(folders[-1] / "target-behavior.json")
    except (repair.BoundedRepairError, readback.Element7ReadbackError,
            ValueError, KeyError, TypeError, OSError) as exc:
        raise CameraLensEvidenceError(
            "Source-to-target camera evidence cannot be independently reproduced."
        ) from exc
    candidates = [
        row for row in csir.get("entities", [])
        if isinstance(row, dict) and row.get("ced_type") == "entity.camera"
    ]
    if len(candidates) != 1:
        raise CameraLensEvidenceError(
            "Only one source-provenanced static camera is supported per repair."
        )
    camera = candidates[0]
    name = camera.get("name")
    entity_id = camera.get("entity_id")
    if (not isinstance(name, str) or not name or not isinstance(entity_id, str)
            or not entity_id or len(name) > 128):
        raise CameraLensEvidenceError("The source camera identity is ambiguous.")
    mapping_entry = (mapping.get("entities") or {}).get(name)
    label = mapping_entry.get("actor_label") if isinstance(mapping_entry, dict) else None
    if not isinstance(label, str) or not label or len(label) > 256:
        raise CameraLensEvidenceError("Missing exact target CineCamera actor label.")
    # A track, property-float override or imported alternate camera can
    # supersede the static component value; never fix its base property.
    if any(
        action.get("kind") in {"camera_fov", "property_float"}
        for action in compiled.get("actions", [])
        if isinstance(action, dict)
    ):
        raise CameraLensEvidenceError(
            "A native FOV/property animation action owns the lens; static correction is unsafe."
        )
    if (not isinstance(source.get("samples"), list)
            or not isinstance(target.get("samples"), list)
            or len(source["samples"]) != len(target["samples"])
            or len(source["samples"]) < 2):
        raise CameraLensEvidenceError("No complete source/target lens time grid.")
    src_fovs, observed_fovs, native_focals, heights = [], [], [], []
    for expected, observed in zip(source["samples"], target["samples"]):
        if expected.get("time_seconds") != observed.get("time_seconds"):
            raise CameraLensEvidenceError("Source camera observation grid changed.")
        original = [
            x for x in expected.get("entities", [])
            if x.get("entity_id") == entity_id
        ]
        actual = [
            x for x in observed.get("entities", [])
            if x.get("entity_id") == entity_id
        ]
        if (len(original) != 1 or len(actual) != 1
                or actual[0].get("actor_label") != label):
            raise CameraLensEvidenceError("Measured native camera identity changed.")
        lens = actual[0].get("camera")
        if (not isinstance(lens, dict) or lens.get("status") != "OBSERVED"
                or lens.get("lens_basis")
                != "UNREAL_CINE_CAMERA_SENSOR_HEIGHT_AND_FOCAL_LENGTH"):
            raise CameraLensEvidenceError("Only native physical CineCamera lens is supported.")
        source_fov = _finite(
            (original[0].get("camera") or {}).get("vertical_fov_degrees"),
            "Unity vertical FOV",
        )
        observed_fov = _finite(lens.get("vertical_fov_degrees"), "Unreal vertical FOV")
        focal = _finite(lens.get("focal_length_mm"), "Unreal focal length")
        height = _finite(lens.get("sensor_height_mm"), "Unreal filmback sensor height")
        if (not 1 <= source_fov <= 170 or not 1 <= observed_fov <= 170
                or not 0 < focal <= MAX_ALLOWED_FOCAL_MM
                or not 0 < height <= 100):
            raise CameraLensEvidenceError("Unsupported physical lens measurement.")
        derived = math.degrees(2 * math.atan(height / (2 * focal)))
        if abs(derived - observed_fov) > 1e-4:
            raise CameraLensEvidenceError("Native physical lens does not match its FOV.")
        src_fovs.append(source_fov)
        observed_fovs.append(observed_fov)
        native_focals.append(focal)
        heights.append(height)
    if (max(src_fovs) - min(src_fovs) > MAX_SOURCE_FOV_DRIFT
            or max(native_focals) - min(native_focals) > MAX_NATIVE_FOCAL_DRIFT_MM
            or max(heights) - min(heights) > MAX_SENSOR_DRIFT_MM):
        raise CameraLensEvidenceError(
            "Animated camera zoom or filmback is not a static component repair."
        )
    expected_fov = src_fovs[0]
    measured_error = max(abs(a - b) for a, b in zip(src_fovs, observed_fovs))
    if not TOLERANCE_DEGREES < measured_error <= MAX_FOV_DELTA:
        raise CameraLensEvidenceError("Native lens mismatch is absent or outside safe bounds.")
    # Element 8 must have measured this exact source camera rather than a
    # global camera failure with an unrelated camera/track.
    workflow = repair._snapshot(candidate)
    if workflow is None:
        raise CameraLensEvidenceError("Source occurrence workflow is missing.")
    camera_occurrences = [
        x["occurrence_id"] for x in workflow["element_plan"]["elements"]
        if x.get("source_kind") == "entities"
        and x.get("source_location") == (
            "entities[" + str(csir["entities"].index(camera)) + "]"
        )
    ]
    matching = [
        row for row in bounded["per_occurrence"]
        if row["occurrence_id"] in camera_occurrences
    ]
    if (len(camera_occurrences) != 1 or len(matching) != 1
            or matching[0]["latest_status"] != "DIRECT_MEASURED_DIFFERENCE"
            or matching[0]["latest_discrepancy_flags"]
            != ["CAMERA_NATIVE_LENS_DIFFERENCE"]):
        raise CameraLensEvidenceError(
            "Measured discrepancy is not an isolated source camera lens mismatch."
        )
    new_focal = heights[0] / (2 * math.tan(math.radians(expected_fov) / 2))
    if not 0 < new_focal <= MAX_ALLOWED_FOCAL_MM:
        raise CameraLensEvidenceError("Source FOV cannot fit a safe native focal length.")
    snapshot = {
        "kind": KIND,
        "eligible": True,
        "job_id_sha256": _hash(job_id),
        "source_camera_occurrence_id": camera_occurrences[0],
        "source_entity_id": entity_id,
        "source_camera_name": name,
        "target_actor_label": label,
        "target_source_fov_degrees": expected_fov,
        "native_sensor_height_mm": heights[0],
        "native_focal_before_mm": native_focals[0],
        "native_focal_after_mm": new_focal,
        "measured_native_fov_error_degrees": measured_error,
        "sample_count": len(src_fovs),
        "element8_repair_sha256": bounded["repair_plan_sha256"],
        "element7_latest_sha256": native["readback_sha256"],
        "native_actor_or_sequencer_edited": False,
        "user_authorization_required": True,
        "full_cutscene_fidelity_verified": False,
    }
    snapshot["camera_repair_sha256"] = _hash(snapshot)
    return snapshot


def _context(workspace: Path, job_id: str):
    try:
        return outcome._context(workspace, job_id)
    except (outcome.OutcomeError, KeyError, TypeError, OSError) as exc:
        raise CameraLensEvidenceError(
            "Prepared camera repair is not bound to the original source and job."
        ) from exc
