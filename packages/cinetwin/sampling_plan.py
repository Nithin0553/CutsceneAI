"""Plan repeatable source-engine behavior measurements from an immutable CSIR.

The plan is independent of Unity/Unreal imports. It does not approximate clips:
frame samples are supplemented with authored boundaries and transition samples.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from typing import Any


class SamplingPlanError(ValueError):
    """The requested source evidence cannot safely be scheduled."""


def _seconds(value: dict[str, Any]) -> Fraction:
    rate = value["rate"]
    n = int(rate["numerator"])
    d = int(rate["denominator"])
    if n <= 0 or d <= 0:
        raise SamplingPlanError("Time rate must be positive.")
    seconds = Fraction(int(value["value"]) * d, n)
    subframe = value.get("subframe")
    if isinstance(subframe, dict):
        seconds += Fraction(
            int(subframe["numerator"]) * d,
            int(subframe["denominator"]) * n,
        )
    return seconds


def _as_fraction(value: float) -> Fraction:
    if not math.isfinite(value):
        raise SamplingPlanError("Source section contains non-finite blend time.")
    return Fraction(str(value))


def _timestamp(value: Fraction) -> float:
    return round(float(value), 9)


def _entity_scope(csir: dict[str, Any]) -> list[dict[str, Any]]:
    entities = []
    seen: set[str] = set()
    for item in csir.get("entities", []):
        entity_id = str(item.get("entity_id", ""))
        if not entity_id or entity_id in seen:
            raise SamplingPlanError("Every source entity requires a unique nonempty ID.")
        seen.add(entity_id)
        entities.append({
            "entity_id": entity_id,
            "name": str(item.get("name", "")),
            "ced_type": str(item.get("ced_type", "")),
            "hierarchy_path": str(item.get("metadata", {}).get("hierarchy_path", "")),
            "parent_entity_id": item.get("parent_entity_id"),
        })
    return entities


CAPTURED_LAYERS = ("world_transform", "camera_state", "light_state", "skeletal_pose")
UNIMPLEMENTED_LAYERS = (
    "audio_output",
    "event_execution",
    "rendered_frame",
    "physics_state",
)


def _skeletal_entity_ids(csir: dict[str, Any]) -> list[str]:
    """Derive actual animated characters, not every renderer tagged as a character.

    The structural source extractor can emit separate character entities for
    individual mesh parts; only Timeline-bound skeletal animation targets are
    requested as pose-capture rigs.
    """
    by_id = {str(entity["entity_id"]): entity for entity in csir.get("entities", [])}
    result: set[str] = set()
    for track in csir.get("tracks", []):
        if str(track.get("ced_type")) != "animation.track":
            continue
        if not any(
            str(section.get("ced_type")) == "animation.section"
            for section in track.get("sections", [])
        ):
            continue
        entity_id = str(track.get("binding_entity_id") or "")
        if by_id.get(entity_id, {}).get("ced_type") == "entity.character":
            result.add(entity_id)
    return sorted(result)


def build_plan(csir: dict[str, Any], *, csir_sha256: str = "") -> dict[str, Any]:
    """Make one generic frame+transition sampling request from source CSIR."""
    timing = csir["timing"]
    rate = timing.get("display_rate") or timing["source_rate"]
    fps_n = int(rate["numerator"])
    fps_d = int(rate["denominator"])
    if fps_n <= 0 or fps_d <= 0:
        raise SamplingPlanError("Display frame rate must be positive.")

    start = _seconds(timing["playback_start"])
    end = _seconds(timing["playback_end"])
    if start < 0 or end <= start:
        raise SamplingPlanError("Expected finite positive source playback range.")

    fps = Fraction(fps_n, fps_d)
    total_frames = int(math.floor((end - start) * fps))
    if total_frames > 100_000:
        raise SamplingPlanError("Excessive capture sample count; split source first.")

    reasons: dict[Fraction, set[str]] = defaultdict(set)

    def add(moment: Fraction, reason: str) -> None:
        if start <= moment <= end:
            reasons[moment].add(reason)

    for frame in range(total_frames + 1):
        add(start + Fraction(frame, 1) / fps, "source_frame")
    add(end, "playback_end")

    for track in csir.get("tracks", []):
        track_id = str(track.get("track_id", ""))
        for section in track.get("sections", []):
            section_id = str(section.get("section_id", ""))
            key = section_id or track_id
            a, b = _seconds(section["start"]), _seconds(section["end"])
            if b < a:
                raise SamplingPlanError(f"Section {key} ends before it starts.")
            add(a, "section_start:" + key)
            add(b, "section_end:" + key)

            native = section.get("native_payload", {})
            if not isinstance(native, dict):
                native = {}
            duration = max(Fraction(0), b - a)
            for direction, edge in (("in", a), ("out", b)):
                raw = native.get("blend_" + direction + "_seconds")
                if raw is None or float(raw) <= 0:
                    continue
                interval = min(duration, _as_fraction(float(raw)))
                boundary = edge + interval if direction == "in" else edge - interval
                add(boundary, "blend_" + direction + "_boundary:" + key)
                # Subframe samples resolve sudden weight/pose changes near transitions.
                for quarter in (Fraction(1, 4), Fraction(1, 2), Fraction(3, 4)):
                    moment = (
                        a + interval * quarter if direction == "in"
                        else b - interval * quarter
                    )
                    add(moment, "blend_" + direction + "_interior:" + key)

            if str(track.get("ced_type")) == "event.trigger":
                add(a, "event:" + key)

    # Unity often stores microsecond-rounded clip boundaries alongside higher
    # precision editor blend durations. Merge times that become equal at the
    # exported precision; otherwise the Play Mode evaluator sees duplicate instants.
    rounded_reasons: dict[float, set[str]] = defaultdict(set)
    for moment, tags in sorted(reasons.items()):
        rounded_reasons[_timestamp(moment)].update(tags)
    samples = [
        {"time_seconds": moment, "reasons": sorted(tags)}
        for moment, tags in sorted(rounded_reasons.items())
    ]
    capabilities = [
        {"layer": layer, "status": "PLANNED"}
        for layer in CAPTURED_LAYERS
    ] + [
        {"layer": layer, "status": "NOT_IMPLEMENTED"}
        for layer in UNIMPLEMENTED_LAYERS
    ]

    return {
        "schema_version": "0.1.0",
        "kind": "cinetwin.sampling_plan",
        "cutscene_id": str(csir["cutscene_id"]),
        "source": {
            "engine": str(csir["source"]["engine"]),
            "engine_version": str(csir["source"]["engine_version"]),
            "sequence_ref": str(csir["source"]["sequence_ref"]),
            "project_fingerprint": str(csir["source"]["project_fingerprint"]),
            "csir_sha256": csir_sha256,
        },
        "timing": {
            "display_rate": {"numerator": fps_n, "denominator": fps_d},
            "playback_start_seconds": _timestamp(start),
            "playback_end_seconds": _timestamp(end),
        },
        "entities": _entity_scope(csir),
        "skeletal_entity_ids": _skeletal_entity_ids(csir),
        "capabilities": capabilities,
        "samples": samples,
    }


def plan_file(csir_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    csir_bytes = Path(csir_path).read_bytes()
    csir = json.loads(csir_bytes.decode("utf-8-sig"))
    plan = build_plan(csir, csir_sha256=hashlib.sha256(csir_bytes).hexdigest())
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return plan


def validate_capture(plan: dict[str, Any], capture: dict[str, Any]) -> dict[str, Any]:
    """Fail closed on missing requested source observations.

    This validates observable capture completeness, NOT cross-engine equivalence.
    """
    failures: list[str] = []
    if capture.get("kind") != "cinetwin.behavior_capture":
        failures.append("Unexpected behavior capture kind.")
    for field in ("cutscene_id",):
        if capture.get(field) != plan.get(field):
            failures.append(f"Capture {field} differs from sampling plan.")
    if capture.get("source", {}).get("csir_sha256") != plan["source"].get("csir_sha256"):
        failures.append("Capture is not tied to the requested CSIR bytes.")

    expected_times = [s["time_seconds"] for s in plan["samples"]]
    observed_samples = capture.get("samples", [])
    if len(observed_samples) != len(expected_times):
        failures.append("Capture sample count does not match the sampling plan.")
    expected_entities = {item["entity_id"]: item for item in plan["entities"]}
    ids = set(expected_entities)
    requested_rig_ids = set(plan.get("skeletal_entity_ids", []))
    rig_records = capture.get("rigs", [])
    rig_lookup = {rig.get("entity_id"): rig for rig in rig_records}
    if (
        len(rig_records) != len(rig_lookup)
        or set(rig_lookup) != requested_rig_ids
    ):
        failures.append("Missing, unexpected or repeated skeletal rig definitions.")
    bone_ids_by_rig: dict[str, set[str]] = {}
    for rig_id in requested_rig_ids & rig_lookup.keys():
        rig = rig_lookup[rig_id]
        bones = rig.get("bones", [])
        bone_ids = [bone.get("bone_id", "") for bone in bones]
        if not bones or not all(bone_ids) or len(bone_ids) != len(set(bone_ids)):
            failures.append(f"Skeletal rig {rig_id} has no bones or duplicate bone IDs.")
            continue
        bone_set = set(bone_ids)
        bone_ids_by_rig[rig_id] = bone_set
        for bone in bones:
            parent = bone.get("parent_bone_id")
            if parent and parent not in bone_set:
                failures.append(f"Unknown skeletal parent bone in rig {rig_id}.")
    declared_layers = {
        str(item.get("layer")): str(item.get("status"))
        for item in capture.get("capture_layers", [])
    }
    for item in plan["capabilities"]:
        expected_status = (
            "CAPTURED" if item["status"] == "PLANNED" else "NOT_IMPLEMENTED"
        )
        if declared_layers.get(item["layer"]) != expected_status:
            failures.append(
                "Capture claims unsupported or missing layer: " + item["layer"]
            )
    for index, expected_time in enumerate(expected_times):
        if index >= len(observed_samples):
            break
        sample = observed_samples[index]
        if not math.isfinite(float(sample.get("time_seconds", float("nan")))):
            failures.append(f"Sample {index} has non-finite time.")
            continue
        if abs(float(sample["time_seconds"]) - expected_time) > 1e-7:
            failures.append(f"Sample {index} time differs from plan.")
        poses = sample.get("skeletal_poses", [])
        pose_by_rig = {pose.get("entity_id"): pose for pose in poses}
        if (
            len(poses) != len(pose_by_rig)
            or set(pose_by_rig) != requested_rig_ids
        ):
            failures.append(f"Sample {index} skeletal rig observations incomplete.")
        for rig_id in requested_rig_ids & pose_by_rig.keys():
            bones = pose_by_rig[rig_id].get("bones", [])
            bone_by_id = {bone.get("bone_id"): bone for bone in bones}
            expected_bones = bone_ids_by_rig.get(rig_id)
            if (
                expected_bones is None
                or len(bones) != len(bone_by_id)
                or set(bone_by_id) != expected_bones
            ):
                failures.append(f"Sample {index} rig {rig_id} missing or extra bones.")
                continue
            for bone in bones:
                for transform_key in ("local_transform", "world_transform"):
                    transform = bone.get(transform_key, {})
                    for field, length in (
                        ("position_m", 3), ("rotation_xyzw", 4), ("scale_xyz", 3)
                    ):
                        values = transform.get(field, [])
                        if len(values) != length or any(
                            not math.isfinite(float(value)) for value in values
                        ):
                            failures.append(
                                f"Sample {index} rig {rig_id} bone "
                                f"{bone['bone_id']} invalid {transform_key}.{field}."
                            )
                            break
        states = sample.get("entities", [])
        state_ids = [str(item.get("entity_id", "")) for item in states]
        if len(state_ids) != len(set(state_ids)) or set(state_ids) != ids:
            failures.append(f"Sample {index} has missing, extra, or repeated entities.")
            continue
        for state in states:
            semantic_type = expected_entities[state["entity_id"]]["ced_type"]
            if semantic_type == "entity.camera":
                camera = state.get("camera")
                if not isinstance(camera, dict) or not math.isfinite(
                    float(camera.get("vertical_fov_degrees", float("nan")))
                ):
                    failures.append(
                        f"Sample {index} entity {state['entity_id']} missing camera state."
                    )
            if semantic_type == "entity.light":
                light = state.get("light")
                if not isinstance(light, dict) or not math.isfinite(
                    float(light.get("intensity", float("nan")))
                ):
                    failures.append(
                        f"Sample {index} entity {state['entity_id']} missing light state."
                    )
            transform = state.get("world_transform", {})
            for field, length in (("position_m", 3), ("rotation_xyzw", 4), ("scale_xyz", 3)):
                values = transform.get(field, [])
                if len(values) != length or any(
                    not math.isfinite(float(value)) for value in values
                ):
                    failures.append(
                        f"Sample {index} entity {state['entity_id']} invalid {field}."
                    )
                    break
    for problem in capture.get("errors", []):
        failures.append("Source evaluator reported: " + str(problem))

    pending = [
        entry["layer"] for entry in plan["capabilities"]
        if entry["status"] != "PLANNED"
    ]
    return {
        "schema_version": "0.1.0",
        "status": "FAIL" if failures else ("INCOMPLETE" if pending else "PASS"),
        "expected_samples": len(expected_times),
        "observed_samples": len(observed_samples),
        "entity_count": len(ids),
        "skeletal_rig_count": len(requested_rig_ids),
        "failures": failures[:100],
        "not_verified": pending,
    }
