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


# Phase 10.2 — source-complete cut/shot/warp classification. This is a
# READ-ONLY owner census; source capture does not install a generic native
# Sequencer timewarp, subsequence, crossfade or skeletal mixer.
_COMPLEX_TRACKS = frozenset({
    "camera.cut","cinematic.shot","camera.blend",
    "time.warp","animation.track","camera.transform",
})
_UNKNOWN_TIME_PROPERTIES = frozenset({
    "time_warp","timewarp","time_scale_curve","subsequence",
    "nested_sequence","camera_rig","weighted_blend",
})


def analyze_complex_timeline(csir: dict[str, Any],
                             mapping: dict[str, Any]) -> dict[str, Any]:
    """Exhaustively distinguish source-authored cuts, overlaps and nested time owners.

    A resolved source shot is *not* a verified native shot. Unknown nested
    ownership and overlapping cuts remain non-executable until a separate
    source-measured native time and binding adapter is installed.
    """
    if not isinstance(csir,dict) or not isinstance(csir.get("tracks"),list):
        raise TimelineBlendError("Source Timeline track inventory is missing.")
    if not isinstance(mapping,dict) or not isinstance(mapping.get("entities",{}),dict):
        raise TimelineBlendError("Camera/source target mapping is missing.")
    mapped = mapping.get("entities") or {}
    entities = {r.get("entity_id"): r for r in csir.get("entities",[])
                if isinstance(r,dict)}
    rows = []
    cuts = []
    for index,track in enumerate(csir["tracks"]):
        if not isinstance(track,dict):
            raise TimelineBlendError("Invalid source Timeline track.")
        kind = track.get("ced_type")
        if kind not in _COMPLEX_TRACKS and not any(
                label in track for label in _UNKNOWN_TIME_PROPERTIES):
            continue
        source_id = track.get("binding_entity_id")
        camera = entities.get(source_id)
        native_mapping = (mapped.get(camera.get("name"))
                          if isinstance(camera,dict) else None)
        sections = track.get("sections",[])
        if not isinstance(sections,list):
            raise TimelineBlendError("Source Timeline section inventory is missing.")
        blockers = []
        if kind in {"cinematic.shot","time.warp","camera.blend"}:
            blockers.append("UNSUPPORTED_NESTED_OR_BLENDED_TIME_OWNER")
        if any(track.get(k) not in (None,False,0,"") for k in
               _UNKNOWN_TIME_PROPERTIES):
            blockers.append("SOURCE_NESTED_OR_RETIMED_TRACK_METADATA")
        if track.get("muted") is True:
            rows.append({
                "source_track_index":index,"source_kind":kind,
                "section_count":len(sections),"reason_codes":["MUTED_SOURCE_TRACK"],
                "native_edit_allowed":False,
            })
            continue
        if kind in {"animation.track","camera.transform"} and native_mapping is None:
            blockers.append("UNMAPPED_SOURCE_MOTION_BINDING")
        intervals = []
        for section_index,section in enumerate(sections):
            if not isinstance(section,dict):
                raise TimelineBlendError("Invalid source section.")
            if "start" not in section or "end" not in section:
                raise TimelineBlendError("Incomplete source cut/shot section timing.")
            start = _seconds(section["start"],"complex section start")
            end = _seconds(section["end"],"complex section end")
            if not 0 <= start < end:
                raise TimelineBlendError("Invalid complex Timeline section duration.")
            payload = section.get("native_payload") or {}
            if not isinstance(payload,dict):
                raise TimelineBlendError("Malformed Timeline source payload.")
            if any(payload.get(k) not in (None,False,0,"") for k in
                   _UNKNOWN_TIME_PROPERTIES):
                blockers.append("SOURCE_NESTED_OR_RETIMED_SECTION_METADATA")
            if any(payload.get(k) not in (None,False,0,"") for k in (
                    "blend_in_seconds","blend_out_seconds","ease_in_seconds",
                    "ease_out_seconds")):
                blockers.append("SOURCE_SECTION_EASING_OR_CROSSFADE")
            intervals.append((start,end,section_index))
            if kind == "camera.cut":
                cuts.append((start,end,index,section_index,source_id))
        if any(y[0] < x[1]-1e-7 for j,x in enumerate(intervals)
               for y in intervals[j+1:]):
            blockers.append("OVERLAPPING_SOURCE_TRACK_SECTIONS")
        rows.append({
            "source_track_index":index,
            "source_kind":kind,
            "section_count":len(sections),
            "source_binding_id":source_id,
            "reason_codes":sorted(set(blockers)),
            "native_edit_allowed":False,
        })
    for i,a in enumerate(cuts):
        for b in cuts[i+1:]:
            if a[0]<b[1]-1e-7 and b[0]<a[1]-1e-7:
                for row in rows:
                    if row["source_track_index"] in (a[2],b[2]):
                        row["reason_codes"]=sorted(set(
                            row["reason_codes"]+["OVERLAPPING_CAMERA_CUT_OWNERS"]
                        ))
    return {
        "kind":"cutsceneai.studio.phase10_2.complex_timeline_owner_census",
        "schema_version":"1",
        "source_track_count":len(rows),
        "camera_cut_section_count":len(cuts),
        "tracks":rows,
        "source_time_owners_with_blockers":sum(
            bool(row["reason_codes"]) for row in rows
        ),
        "native_repair_authorized":False,
        "native_subsequence_fidelity_verified":False,
        "rendered_camera_transition_verified":False,
    }
