"""Evaluate a source CSIR against a machine-readable benchmark specification."""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping


JsonObject = Mapping[str, Any]


def _rational_seconds(value: JsonObject) -> float:
    rate = value.get("rate", {})
    numerator = float(rate.get("numerator", 1))
    denominator = float(rate.get("denominator", 1))
    return float(value.get("value", 0)) * denominator / numerator


def _count_declared_ced(value: Any, counts: Counter[str]) -> None:
    if isinstance(value, Mapping):
        ced_type = value.get("ced_type")
        if isinstance(ced_type, str) and ced_type:
            counts[ced_type] += 1
        for child in value.values():
            _count_declared_ced(child, counts)
    elif isinstance(value, list):
        for child in value:
            _count_declared_ced(child, counts)


def _animation_sections(csir: JsonObject) -> list[JsonObject]:
    result: list[JsonObject] = []
    for track in csir.get("tracks", []):
        if not isinstance(track, Mapping):
            continue
        if str(track.get("ced_type", "")) != "animation.track":
            continue
        for section in track.get("sections", []):
            if isinstance(section, Mapping):
                result.append(section)
    return result


def _infer_root_motion(csir: JsonObject) -> int:
    count = 0
    for section in _animation_sections(csir):
        payload = section.get("payload", {})
        animation = payload.get("animation", {}) if isinstance(payload, Mapping) else {}
        curves = animation.get("curves", []) if isinstance(animation, Mapping) else []
        names = {
            str(curve.get("property_name", ""))
            for curve in curves
            if isinstance(curve, Mapping)
        }
        if {"RootT.x", "RootT.y", "RootT.z"} <= names:
            count += 1
    return count


def _infer_animation_blends(csir: JsonObject) -> int:
    overlaps = 0
    for track in csir.get("tracks", []):
        if not isinstance(track, Mapping):
            continue
        if str(track.get("ced_type", "")) != "animation.track":
            continue
        sections = [
            section
            for section in track.get("sections", [])
            if isinstance(section, Mapping)
        ]
        intervals = sorted(
            (
                _rational_seconds(section["start"]),
                _rational_seconds(section["end"]),
            )
            for section in sections
            if "start" in section and "end" in section
        )
        for index in range(1, len(intervals)):
            if intervals[index][0] < intervals[index - 1][1]:
                overlaps += 1
    return overlaps


def inventory(csir: JsonObject) -> dict[str, int]:
    counts: Counter[str] = Counter()
    _count_declared_ced(csir, counts)

    # Infer semantics that CSIR v0.1 may encode structurally rather than with a dedicated
    # ced_type on every node.
    parent_count = sum(
        1
        for entity in csir.get("entities", [])
        if isinstance(entity, Mapping) and entity.get("parent_entity_id")
    )
    counts["transform.parent"] = max(counts["transform.parent"], parent_count)
    counts["animation.root_motion"] = max(
        counts["animation.root_motion"],
        _infer_root_motion(csir),
    )
    counts["animation.blend"] = max(
        counts["animation.blend"],
        _infer_animation_blends(csir),
    )
    return dict(counts)


def evaluate_source(spec: JsonObject, csir: JsonObject) -> dict[str, Any]:
    counts = inventory(csir)
    checks: list[dict[str, Any]] = []

    timing = csir.get("timing", {})
    source_rate = timing.get("source_rate", {}) if isinstance(timing, Mapping) else {}
    required_rate = spec["timing"]["display_rate"]
    rate_ok = (
        int(source_rate.get("numerator", -1)) == int(required_rate["numerator"])
        and int(source_rate.get("denominator", -1)) == int(required_rate["denominator"])
    )
    checks.append(
        {
            "id": "timing.display_rate",
            "status": "PASS" if rate_ok else "FAIL",
            "expected": required_rate,
            "actual": source_rate,
        }
    )

    required_duration = float(spec["timing"]["duration_seconds"])
    tolerance = float(spec["timing"].get("duration_tolerance_seconds", 0.0))
    actual_duration = float(timing.get("duration_seconds", -1.0))
    duration_ok = abs(actual_duration - required_duration) <= tolerance
    checks.append(
        {
            "id": "timing.duration",
            "status": "PASS" if duration_ok else "FAIL",
            "expected": required_duration,
            "actual": actual_duration,
        }
    )

    for requirement in spec.get("requirements", []):
        ced = str(requirement["ced"])
        minimum = int(requirement["minimum_count"])
        actual = int(counts.get(ced, 0))
        checks.append(
            {
                "id": str(requirement["id"]),
                "ced": ced,
                "status": "PASS" if actual >= minimum else "NEEDS_EVIDENCE",
                "expected": minimum,
                "actual": actual,
                "details": str(requirement.get("notes", "")),
            }
        )

    failed = sum(1 for check in checks if check["status"] == "FAIL")
    missing = sum(1 for check in checks if check["status"] == "NEEDS_EVIDENCE")
    status = "FAIL" if failed else ("NEEDS_EVIDENCE" if missing else "READY")

    return {
        "benchmark": str(spec["benchmark"]),
        "status": status,
        "summary": {
            "passed": sum(1 for check in checks if check["status"] == "PASS"),
            "failed": failed,
            "needs_evidence": missing,
        },
        "inventory": counts,
        "checks": checks,
    }
