"""Exact-source, single-shot camera-cut timing repair eligibility (read-only).

Only a source-authored frame-aligned, uniquely mapped single camera-cut
section with an independently observed wrong start/end (<= 8 frames) may
become a candidate. The AI cannot invent times, choose a camera, retarget
bindings, edit animation tracks, or infer rendered shot equivalence.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import studio_element7_readback as readback
import studio_element8_repair as repair
import studio_element9_outcome as outcome

KIND = "cutsceneai.studio.single_camera_cut_repair_review"
MAX_FRAME_SHIFT = 8
FIX = re.compile(r"\b(?:fix|correct|repair|adjust|restore|align)\b", re.I)
CAMERA = re.compile(r"\b(?:camera|shot)\b", re.I)
CUT = re.compile(r"\b(?:cut|cuts|timing|boundary|switch)\b", re.I)
NEGATION = re.compile(
    r"\b(?:do not|don't|dont|without)\s+"
    r"(?:modify|edit|change|fix|repair|correct|adjust|move)", re.I,
)


class CameraCutEvidenceError(ValueError):
    """Camera cut correction is ambiguous, stale, or outside registered scope."""


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def message_requests_cut(message: Any) -> bool:
    return (
        isinstance(message, str) and 0 < len(message) <= 1200
        and bool(FIX.search(message) and CAMERA.search(message)
                 and CUT.search(message))
        and not bool(NEGATION.search(message))
        and "\x00" not in message
    )


def build(workspace: Path, job: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(job, dict):
        raise CameraCutEvidenceError("A source-bound native job is required.")
    try:
        root, candidate, current, csir, mapping, _compiled = outcome._context(
            workspace, job.get("job_id"),
        )
        if job != current:
            raise CameraCutEvidenceError("A stale native job cannot own a cut edit.")
        folders = outcome.discover(root, job["job_id"])
        if not folders:
            raise CameraCutEvidenceError("No saved reopened native camera-cut evidence.")
        bounded = repair.build(root, job["job_id"], folders)
        native = readback.build(root, job["job_id"], folders[-1])
        sampling, _ = readback._safe_json(
            folders[-1] / "sampling-plan.json"
        )
        target, _ = readback._safe_json(
            folders[-1] / "target-behavior.json"
        )
    except (readback.Element7ReadbackError, repair.BoundedRepairError,
            outcome.OutcomeError, ValueError, KeyError, TypeError, OSError) as exc:
        raise CameraCutEvidenceError(
            "Independent source/native camera-cut evidence is missing or altered."
        ) from exc
    if (bounded["status"] in {
            "STOP_MEASURED_REGRESSION_OR_NO_PROGRESS",
            "STOP_REMEASUREMENT_BUDGET_EXHAUSTED",
        } or native["camera_cuts_status"] != "FAIL"
            or native["camera_lens_status"] != "PASS"):
        raise CameraCutEvidenceError(
            "The bounded native cut mismatch or camera lens is not eligible."
        )
    expected = sampling.get("camera_cuts")
    observed = target.get("camera_cut_sections")
    if (not isinstance(expected, list) or len(expected) != 1
            or not isinstance(observed, dict)
            or observed.get("status") != "OBSERVED"
            or observed.get("binding_provenance")
            != "NATIVE_SEQUENCE_CAMERA_BINDING_ID"
            or not isinstance(observed.get("sections"), list)
            or len(observed["sections"]) != 1):
        raise CameraCutEvidenceError(
            "Only one frame-aligned source cut with one native binding is supported."
        )
    source_cut, native_cut = expected[0], observed["sections"][0]
    if (source_cut.get("status") != "FRAME_ALIGNED"
            or type(source_cut.get("start_frame")) is not int
            or type(source_cut.get("end_frame")) is not int
            or type(native_cut.get("start_frame")) is not int
            or type(native_cut.get("end_frame")) is not int):
        raise CameraCutEvidenceError(
            "Source or native cut boundaries are not exact integer frames."
        )
    first, last = source_cut["start_frame"], source_cut["end_frame"]
    before_first, before_last = (
        native_cut["start_frame"], native_cut["end_frame"],
    )
    if (first < 0 or last <= first
            or before_first < 0 or before_last <= before_first
            or not (
                0 < max(abs(first - before_first), abs(last - before_last))
                <= MAX_FRAME_SHIFT
            )):
        raise CameraCutEvidenceError("Native cut timing is within tolerance or too far off.")
    ident = source_cut.get("source_entity_id")
    cameras = [
        row for row in csir.get("entities", [])
        if isinstance(row, dict) and row.get("entity_id") == ident
        and row.get("ced_type") == "entity.camera"
    ]
    if len(cameras) != 1:
        raise CameraCutEvidenceError("Source cut does not bind one real Unity camera.")
    name = cameras[0].get("name")
    mapping_entry = (mapping.get("entities") or {}).get(name)
    actor_label = (
        mapping_entry.get("actor_label")
        if isinstance(mapping_entry, dict) else None
    )
    if (not isinstance(name, str) or not isinstance(actor_label, str)
            or not actor_label or len(name) > 128
            or len(actor_label) > 256
            or actor_label != native_cut.get("actor_label")):
        raise CameraCutEvidenceError(
            "Unreal native camera-cut binding differs from exact source mapping."
        )
    # Only source-owned global camera-cut track; mixed sub-scenes, overlapping
    # schedules, multiple cameras or ambiguous ownership are report-only.
    track_ids = {
        row.get("track_id") for row in csir.get("tracks", [])
        if isinstance(row, dict) and row.get("ced_type") == "camera.cut"
    }
    if len(track_ids) != 1:
        raise CameraCutEvidenceError("Multiple source camera-cut tracks are not supported.")
    result = {
        "kind": KIND,
        "eligible": True,
        "job_id_sha256": _hash(job["job_id"]),
        "target_camera_actor_label": actor_label,
        "source_camera_name": name,
        "source_entity_id": ident,
        "expected_start_frame": first,
        "expected_end_frame": last,
        "native_start_frame": before_first,
        "native_end_frame": before_last,
        "maximum_frame_boundary_error": max(
            abs(first - before_first), abs(last - before_last),
        ),
        "source_section_id_sha256": _hash(source_cut.get("source_section_id")),
        "element7_readback_sha256": native["readback_sha256"],
        "element8_repair_sha256": bounded["repair_plan_sha256"],
        "native_edit_authorized": False,
        "full_cutscene_fidelity_verified": False,
    }
    result["camera_cut_repair_sha256"] = _hash(result)
    return result
