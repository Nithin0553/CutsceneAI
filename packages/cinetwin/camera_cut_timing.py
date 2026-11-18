"""Independent Unreal camera-cut section timing against exact source CSIR.

This compares the source-bound authored camera/section schedule with native
Sequencer *readback*, not a replay of the generated transfer plan. Matching
sections do not establish viewport switching or rendered-frame parity.
"""
from __future__ import annotations

from collections import Counter
from typing import Any


class CameraCutEvidenceError(ValueError):
    pass


def compare_camera_cut_sections(
    plan: dict[str, Any],
    native: dict[str, Any] | None,
    bound: dict[str, str],
) -> dict[str, Any]:
    """Fail closed on missing camera binding IDs, section bounds and overlap."""
    source = plan.get("camera_cuts") or []
    if not isinstance(source, list):
        raise CameraCutEvidenceError("Source cut inventory must be an array.")
    if not source:
        sections = native.get("sections") if isinstance(native, dict) else None
        return {
            "status": "FAIL" if native and native.get("status") == "OBSERVED"
            and sections else "NOT_APPLICABLE",
            "expected_section_count": 0,
            "native_section_count": len(sections) if isinstance(sections, list) else None,
            "matched_sections": 0,
            "source_frame_alignment": "NOT_APPLICABLE",
            "native_sequence_binding_verified": False,
            "rendered_cut_equivalence_verified": False,
        }

    camera_ids = {
        str(row["entity_id"]) for row in plan.get("entities", [])
        if row.get("ced_type") == "entity.camera"
    }
    expected = []
    reasons = []
    for cut in source:
        if not isinstance(cut, dict):
            raise CameraCutEvidenceError("Malformed source camera cut.")
        identifier = cut.get("source_entity_id")
        start, end = cut.get("start_frame"), cut.get("end_frame")
        if (type(start) is not int or type(end) is not int
                or start < 0 or end <= start):
            reasons.append("INVALID_SOURCE_FRAME_INTERVAL")
            continue
        if identifier not in camera_ids or identifier not in bound:
            reasons.append("SOURCE_CAMERA_UNMAPPED_OR_INVALID")
            continue
        if cut.get("status") != "FRAME_ALIGNED":
            reasons.append(str(cut.get("status") or "SOURCE_FRAME_UNVERIFIED"))
        expected.append((bound[identifier], start, end))
    if not isinstance(native, dict) or native.get("status") != "OBSERVED":
        return {
            "status": "INCOMPLETE",
            "expected_section_count": len(source),
            "native_section_count": None,
            "matched_sections": 0,
            "source_frame_alignment": "UNVERIFIED" if reasons else "FRAME_ALIGNED",
            "unavailable_reasons": sorted(set(reasons + [
                str(native.get("reason") or "NATIVE_CUT_READBACK_UNAVAILABLE")
                if isinstance(native, dict) else "NATIVE_CUT_READBACK_MISSING",
            ])),
            "native_sequence_binding_verified": False,
            "rendered_cut_equivalence_verified": False,
        }
    if native.get("binding_provenance") != "NATIVE_SEQUENCE_CAMERA_BINDING_ID":
        raise CameraCutEvidenceError("Native camera sections lack binding provenance.")
    rows = native.get("sections")
    if not isinstance(rows, list) or len(rows) > 10000:
        raise CameraCutEvidenceError("Native camera-cut section inventory is malformed.")
    actual = []
    for item in rows:
        if not isinstance(item, dict):
            raise CameraCutEvidenceError("Malformed native cut section.")
        label = item.get("actor_label")
        start, end = item.get("start_frame"), item.get("end_frame")
        if (not isinstance(label, str) or not label
                or type(start) is not int or type(end) is not int
                or start < 0 or end <= start):
            raise CameraCutEvidenceError("Native cut section lacks a valid bound actor or frame interval.")
        actual.append((label, start, end))
    planned, measured = Counter(expected), Counter(actual)
    matched = sum(min(count, measured[key]) for key, count in planned.items())
    overlap = sorted({(a[0], a[1], a[2]) for a in expected if sum(
        1 for b in expected if b is not a and a[1] < b[2] and b[1] < a[2]
    )})
    if overlap:
        reasons.append("OVERLAPPING_SOURCE_CAMERA_CUTS")
    if measured != planned:
        status = "FAIL"
        reasons.append("NATIVE_CAMERA_BINDING_OR_SECTION_DIFFERENCE")
    elif reasons:
        status = "INCOMPLETE"
    else:
        status = "PASS"
    return {
        "status": status,
        "expected_section_count": len(source),
        "native_section_count": len(rows),
        "matched_sections": matched,
        "source_frame_alignment": "UNVERIFIED" if reasons else "FRAME_ALIGNED",
        "unavailable_reasons": sorted(set(reasons)),
        "native_sequence_binding_verified": status == "PASS",
        "rendered_cut_equivalence_verified": False,
    }
