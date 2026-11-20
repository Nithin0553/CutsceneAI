"""Conservative Unity Timeline blend ownership and source-capture requirements.

Unreal's per-track transform additions are not a Unity Timeline mixer. For
actor/world transforms, verified evaluated frames can be baked into ONE
source-bound native track. Skeletal layers still require a separate retargeted
pose-bake implementation and must not be labeled converted.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


class TimelineBlendError(ValueError):
    pass


TRANSFORM_TRACKS = {"animation.track", "camera.transform"}


def _seconds(value: dict, label: str) -> float:
    try:
        rate = value["rate"]
        fps = float(rate["numerator"]) / float(rate["denominator"])
        result = float(value["value"]) / fps
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise TimelineBlendError("Invalid Timeline " + label + " time.") from exc
    if not math.isfinite(result):
        raise TimelineBlendError("Nonfinite Timeline " + label + " time.")
    return result


def analyze(csir: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    """Return mapped actor IDs requiring a *single measured* blended track.

    A genuinely unsupported skeletal blend must be reported as unsafe, even
    if generic actor world positions were captured. A captured actor trajectory
    is never a substitute for independently retargeted joint pose blending.
    """
    entities = {row["entity_id"]: row for row in csir.get("entities", [])}
    mapped = mapping.get("entities") or {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for index, track in enumerate(csir.get("tracks", [])):
        if track.get("muted") is True or track.get("ced_type") not in TRANSFORM_TRACKS:
            continue
        eid = track.get("binding_entity_id")
        entity = entities.get(eid)
        if entity is None or entity.get("name") not in mapped:
            continue
        for section in track.get("sections", []):
            start = _seconds(section["start"], "section start")
            end = _seconds(section["end"], "section end")
            if start < 0 or end <= start:
                raise TimelineBlendError("Invalid active Timeline section range.")
            native = section.get("native_payload") or {}
            try:
                blend_in = float(native.get("blend_in_seconds") or 0.0)
                blend_out = float(native.get("blend_out_seconds") or 0.0)
            except (ValueError, TypeError) as exc:
                raise TimelineBlendError("Invalid source Timeline blend duration.") from exc
            if (not all(math.isfinite(x) for x in (blend_in, blend_out))
                    or blend_in < 0 or blend_out < 0 or
                    blend_in > end - start + 1e-7 or blend_out > end - start + 1e-7):
                raise TimelineBlendError("Unsupported or nonfinite Timeline blend envelope.")
            grouped[str(eid)].append({
                "start": start, "end": end,
                "track_index": index, "track_id": str(track.get("track_id") or ""),
                "section_id": str(section.get("section_id") or ""),
                "easing": blend_in > 0 or blend_out > 0,
                "track_kind": track["ced_type"],
            })
    requires = []
    for eid in sorted(grouped):
        clips = sorted(grouped[eid], key=lambda x: (x["start"], x["end"], x["track_index"]))
        overlapping = any(
            second["start"] < first["end"] - 1e-7
            for i, first in enumerate(clips)
            for second in clips[i + 1:]
            if second["start"] < first["end"]
        )
        multi_writers = len({row["track_index"] for row in clips}) > 1
        easing = any(row["easing"] for row in clips)
        if not (overlapping or multi_writers or easing):
            continue
        entity = entities[eid]
        requires.append({
            "entity_id": eid, "entity_name": entity["name"],
            "entity_type": entity.get("ced_type", ""),
            "reason_codes": [reason for enabled, reason in (
                (overlapping, "OVERLAPPING_SECTIONS"),
                (multi_writers, "MULTIPLE_ANIMATED_TRACKS"),
                (easing, "TIMELINE_BLEND_EASING"),
            ) if enabled],
            "source_track_indices": sorted({row["track_index"] for row in clips}),
            "source_section_ids": [row["section_id"] for row in clips],
            "policy": (
                "REQUIRES_NATIVE_SKELETAL_BLEND_BAKE"
                if entity.get("ced_type") == "entity.character"
                else "BAKE_EVALUATED_ACTOR_WORLD_POSES"
            ),
        })
    return {
        "kind": "cutsceneai.timeline.blend_analysis",
        "schema_version": "1",
        "requires_capture": requires,
        "source_feature_count": len(requires),
        "generated_motion_is_not_independent_render_fidelity": True,
    }
