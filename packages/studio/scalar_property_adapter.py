"""Explicit source linear float curve -> editable Unreal Sequencer property keys.

Generalized across light, camera, material and plugin scalar properties, but
ONLY with a user-authored type/property binding and independently proved linear
source interpolation. Omitted/weighted/stepped/ambiguous source curves fail
closed. Never infer a target property from a similar-looking native name.
"""
from __future__ import annotations

import math
import re
from typing import Any

import csir_plan


class ScalarPropertyError(ValueError):
    pass


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _number(value: Any, message: str) -> float:
    try:
        out = float(value)
    except (ValueError, TypeError) as exc:
        raise ScalarPropertyError(message) from exc
    if not math.isfinite(out):
        raise ScalarPropertyError(message)
    return out


def _mapping_specs(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    specs = mapping.get("scalar_property_mappings") or []
    if not isinstance(specs, list):
        raise ScalarPropertyError("scalar_property_mappings must be an explicit list.")
    seen = set()
    for row in specs:
        if not isinstance(row, dict):
            raise ScalarPropertyError("Invalid scalar property mapping entry.")
        for field in ("source_semantic", "source_component_type", "source_entity_name",
                      "target_class", "target_property_name", "target_property_path"):
            if not isinstance(row.get(field), str) or not row[field]:
                raise ScalarPropertyError("Missing explicit scalar mapping field: " + field)
        if not _IDENTIFIER.fullmatch(row["target_class"]):
            raise ScalarPropertyError("Unsafe Unreal target component class name.")
        if not _IDENTIFIER.fullmatch(row["target_property_name"]):
            raise ScalarPropertyError("Unsafe Unreal property name.")
        if not _PATH.fullmatch(row["target_property_path"]):
            raise ScalarPropertyError("Unsafe Unreal property path.")
        if row.get("target_scope") not in {"actor", "component"}:
            raise ScalarPropertyError("Scalar target scope must be actor or component.")
        scale = _number(row.get("value_scale", 1.0), "Invalid numeric value scale.")
        _number(row.get("value_offset", 0.0), "Invalid numeric value offset.")
        if abs(scale) < 1e-12:
            raise ScalarPropertyError("Source-to-Unreal scalar mapping scale cannot be zero.")
        token = (row["source_entity_name"], row["target_scope"],
                 row["target_class"], row["target_property_path"])
        if token in seen:
            raise ScalarPropertyError("Duplicate scalar property target binding.")
        seen.add(token)
    return specs


def _linear_samples(keys: list[dict[str, Any]], t0: float, t1: float
                    ) -> list[tuple[float, float]]:
    if len(keys) < 2:
        raise ScalarPropertyError("Linear property transfer requires two source keys.")
    ordered = []
    for key in keys:
        if not isinstance(key, dict):
            raise ScalarPropertyError("Malformed source property key.")
        time = _number(key.get("time_seconds"), "Nonfinite source key time.")
        value = _number(key.get("value"), "Nonfinite source key value.")
        incoming = _number(key.get("in_tangent"), "Source tangent evidence missing.")
        outgoing = _number(key.get("out_tangent"), "Source tangent evidence missing.")
        if int(key.get("weighted_mode", 0)) != 0:
            raise ScalarPropertyError(
                "Weighted Unity curve requires sampled-source baking; no blind linearization."
            )
        ordered.append((time, value, incoming, outgoing))
    ordered.sort(key=lambda row: row[0])
    for a, b in zip(ordered, ordered[1:]):
        dt = b[0] - a[0]
        if dt <= 1e-9:
            raise ScalarPropertyError("Duplicate/unsorted source curve times.")
        slope = (b[1] - a[1]) / dt
        if (not math.isclose(a[3], slope, rel_tol=1e-5, abs_tol=1e-5)
                or not math.isclose(b[2], slope, rel_tol=1e-5, abs_tol=1e-5)):
            raise ScalarPropertyError(
                "Unity source property uses non-linear or stepped interpolation; "
                "a source-evaluated bake adapter is required."
            )
    if t0 < ordered[0][0] - 1e-7 or t1 > ordered[-1][0] + 1e-7:
        raise ScalarPropertyError(
            "Authored linear curve does not cover the entire used Timeline clip."
        )

    def value_at(time: float) -> float:
        for first, second in zip(ordered, ordered[1:]):
            if first[0] - 1e-8 <= time <= second[0] + 1e-8:
                fraction = (time - first[0]) / (second[0] - first[0])
                return first[1] + fraction * (second[1] - first[1])
        raise ScalarPropertyError("Requested time outside source linear curve.")
    timestamps = sorted({t0, t1} | {row[0] for row in ordered if t0 < row[0] < t1})
    return [(time, value_at(time)) for time in timestamps]


def build_actions(csir: dict[str, Any], mapping: dict[str, Any],
                  track: dict[str, Any]) -> list[dict[str, Any]]:
    specs = _mapping_specs(mapping)
    if not specs or track.get("muted"):
        return []
    by_id = {str(e["entity_id"]): e for e in csir.get("entities", [])}
    entity = by_id.get(str(track.get("binding_entity_id") or ""))
    if entity is None:
        return []
    entity_name = str(entity.get("name") or "")
    specs = [x for x in specs if x["source_entity_name"] == entity_name]
    if not specs:
        return []
    sections = track.get("sections")
    if not isinstance(sections, list) or len(sections) != 1:
        raise ScalarPropertyError(
            "Explicit float property transfer requires one authored section; "
            "multiple/gapped sections need an evaluated source blend policy."
        )
    sec = sections[0]
    timing = csir.get("timing") or {}
    display = timing.get("display_rate") or timing.get("source_rate") or {}
    try:
        n, d = int(display["numerator"]), int(display["denominator"])
        start = float(csir_plan.rational_seconds(sec["start"]))
        end = float(csir_plan.rational_seconds(sec["end"]))
        source_offset = float(csir_plan.rational_seconds(sec["source_offset"]))
        scale_time = float(sec.get("time_scale", 1.0))
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise ScalarPropertyError("Missing source Timeline section/timebase contract.") from exc
    if n <= 0 or d <= 0 or end <= start or not math.isfinite(scale_time) or scale_time <= 0:
        raise ScalarPropertyError("Invalid source Timeline rate, section or time scale.")
    by_semantic: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for curve in (sec.get("payload") or {}).get("animation", {}).get("curves", []):
        if not isinstance(curve, dict):
            continue
        semantic = str(curve.get("canonical_semantic") or "")
        component_type = str(curve.get("component_type") or "")
        by_semantic.setdefault((semantic, component_type), []).append(curve)
    output = []
    fps = n / d
    for spec in specs:
        identity = (spec["source_semantic"], spec["source_component_type"])
        matches = by_semantic.get(identity, [])
        if not matches:
            continue
        if len(matches) != 1:
            raise ScalarPropertyError("Ambiguous matching source property curve: " +
                                      str(identity))
        source_end = source_offset + (end - start) * scale_time
        samples = _linear_samples(matches[0].get("keys", []), source_offset, source_end)
        conversion_scale = _number(spec.get("value_scale", 1.0), "Invalid value scale.")
        conversion_offset = _number(spec.get("value_offset", 0.0), "Invalid value offset.")
        keys = []
        for t, value in samples:
            time = start + (t - source_offset) / scale_time
            frames = time * fps
            frame = int(round(frames))
            if abs(frames - frame) > 1e-6:
                raise ScalarPropertyError(
                    "Subframe scalar source key cannot be snapped to Unreal "
                    "display frames; use a sampled-source adapter."
                )
            keys.append({
                "frame": frame,
                "value": _number(value * conversion_scale + conversion_offset,
                                 "Nonfinite converted property value."),
            })
        target = mapping.get("entities", {}).get(entity_name)
        if not isinstance(target, dict) or not target.get("actor_label"):
            raise ScalarPropertyError("Source property actor has no target mapping: " +
                                      entity_name)
        output.append({
            "kind": "property_float",
            "entity_name": entity_name,
            "actor_label": str(target["actor_label"]),
            "track_name": str(track.get("name") or ""),
            "target_scope": spec["target_scope"],
            "target_class": spec["target_class"],
            "target_property_name": spec["target_property_name"],
            "target_property_path": spec["target_property_path"],
            "source_semantic": spec["source_semantic"],
            "source_component_type": spec["source_component_type"],
            "source_behavior_strategy": "authored_linear_key_conversion",
            "keys": keys,
            "fidelity_status": "NATIVE_PROPERTY_READBACK_AND_BEHAVIOR_UNVERIFIED",
        })
    return output
