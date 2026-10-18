"""Independent CineTwin verification of sampled parent/child world trajectories.

Checks direct source hierarchy edges against an evaluated Unreal observation.
No source/target engine dependency, mutations or inferred retargeted assets.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


class HierarchyVerificationError(ValueError):
    """Invalid evidence: cannot assert even sampled hierarchy fidelity."""


def _vec(value: Any, n: int, label: str) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != n:
        raise HierarchyVerificationError(f"{label} must contain {n} numbers.")
    try:
        values = tuple(float(x) for x in value)
    except (ValueError, TypeError) as exc:
        raise HierarchyVerificationError(f"{label} is not numeric.") from exc
    if any(not math.isfinite(x) for x in values):
        raise HierarchyVerificationError(f"{label} contains non-finite values.")
    return values


def _relative_point(
    parent: dict[str, Any], child: dict[str, Any]
) -> tuple[float, float, float]:
    """Parent-local translation from canonical world transforms.

    Quaternion inverse rotates (child - parent), then divides by scale.
    This follows a TRS model; shear is not reconstructible from lossy scale.
    """
    p = _vec(parent.get("position_m"), 3, "parent.position_m")
    c = _vec(child.get("position_m"), 3, "child.position_m")
    q = _vec(parent.get("rotation_xyzw"), 4, "parent.rotation_xyzw")
    scale = _vec(parent.get("scale_xyz"), 3, "parent.scale_xyz")
    norm = math.sqrt(sum(x * x for x in q))
    if not 0.95 <= norm <= 1.05:
        raise HierarchyVerificationError("Parent quaternion is not unit length.")
    if any(abs(value) < 1e-8 for value in scale):
        raise HierarchyVerificationError("Cannot invert parent with zero scale.")
    dx, dy, dz = (c[k] - p[k] for k in range(3))
    # Inverse unit quaternion rotates from world into parent local axes.
    x, y, z, w = (-q[0] / norm, -q[1] / norm, -q[2] / norm, q[3] / norm)
    tx, ty, tz = (
        2.0 * (y * dz - z * dy),
        2.0 * (z * dx - x * dz),
        2.0 * (x * dy - y * dx),
    )
    rotated = (
        dx + w * tx + (y * tz - z * ty),
        dy + w * ty + (z * tx - x * tz),
        dz + w * tz + (x * ty - y * tx),
    )
    return tuple(rotated[i] / scale[i] for i in range(3))  # type: ignore[return-value]


def _index(
    sample: dict[str, Any], label: str
) -> dict[str, dict[str, Any]]:
    entities = sample.get("entities")
    if not isinstance(entities, list):
        raise HierarchyVerificationError(f"{label} has no entities.")
    indexed: dict[str, dict[str, Any]] = {}
    for row in entities:
        identifier = row.get("entity_id")
        if not isinstance(identifier, str) or not identifier or identifier in indexed:
            raise HierarchyVerificationError(f"{label} has duplicate/invalid entity IDs.")
        indexed[identifier] = row
    return indexed


def _time(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise HierarchyVerificationError(f"{label} must be numeric.") from exc
    if not math.isfinite(result):
        raise HierarchyVerificationError(f"{label} must be finite.")
    return result


def _validate_provenance(plan: dict, source: dict, target: dict, hierarchy: dict) -> None:
    if plan.get("kind") != "cinetwin.sampling_plan":
        raise HierarchyVerificationError("Expected source sampling plan.")
    if source.get("kind") != "cinetwin.behavior_capture":
        raise HierarchyVerificationError("Expected source behavior capture.")
    if target.get("kind") != "cinetwin.target_behavior_observation":
        raise HierarchyVerificationError("Expected Unreal target observation.")
    if hierarchy.get("kind") != "cinetwin.target_hierarchy_plan":
        raise HierarchyVerificationError("Expected source-driven hierarchy plan.")
    for doc in (source, target, hierarchy):
        if doc.get("cutscene_id") != plan.get("cutscene_id"):
            raise HierarchyVerificationError("Evidence belongs to a different cutscene.")
    for doc in (source, target):
        for key in ("csir_sha256", "sequence_ref", "project_fingerprint"):
            if doc.get("source", {}).get(key) != plan.get("source", {}).get(key):
                raise HierarchyVerificationError(
                    f"Source provenance mismatch: {key}."
                )
    if source.get("errors"):
        raise HierarchyVerificationError("Source evaluator reported errors.")


def _source_and_target_samples(
    plan: dict, source: dict, target: dict
) -> list[tuple[dict[str, Any], dict[str, Any], float]]:
    # Avoid treating smoke measurements as comprehensive timeline coverage.
    planned = [_time(s["time_seconds"], "plan timestamp") for s in plan["samples"]]
    src_rows = source.get("samples", [])
    tgt_rows = target.get("samples", [])
    if len(src_rows) != len(planned):
        raise HierarchyVerificationError("Source capture is not complete.")
    if not (2 <= len(tgt_rows) <= len(planned)):
        raise HierarchyVerificationError("Need at least two target samples.")
    if target.get("coverage", {}).get("sample_count") != len(tgt_rows):
        raise HierarchyVerificationError("Target coverage count is inconsistent.")
    for i, (sample, expected) in enumerate(zip(src_rows, planned)):
        if abs(_time(sample.get("time_seconds"), f"source time {i}") - expected) > 1e-7:
            raise HierarchyVerificationError("Source timestamps disagree with plan.")
    pairs = []
    last_time = -math.inf
    for i, sample in enumerate(tgt_rows):
        stamp = _time(sample.get("time_seconds"), f"target time {i}")
        if stamp <= last_time:
            raise HierarchyVerificationError("Target timestamps must increase.")
        nearest = min(range(len(planned)), key=lambda j: abs(planned[j] - stamp))
        if abs(planned[nearest] - stamp) > 1e-7:
            raise HierarchyVerificationError("Target timestamp not in source plan.")
        pairs.append((src_rows[nearest], sample, stamp))
        last_time = stamp
    return pairs


def verify_hierarchy(
    plan: dict[str, Any],
    source: dict[str, Any],
    target: dict[str, Any],
    hierarchy: dict[str, Any],
    *,
    world_tolerance_cm: float = 1.0,
    relative_tolerance_cm: float = 1.0,
) -> dict[str, Any]:
    """Compare actual parent/child world points and parent-local offsets.

    This verifies only sampled direct actor attachments, NOT entire cutscene
    equivalence or successful Unreal asset persistence.
    """
    world_limit = _time(world_tolerance_cm, "world tolerance")
    relative_limit = _time(relative_tolerance_cm, "relative tolerance")
    if world_limit <= 0 or relative_limit <= 0:
        raise HierarchyVerificationError("Comparison tolerances must be positive.")
    _validate_provenance(plan, source, target, hierarchy)
    pairs = _source_and_target_samples(plan, source, target)
    edges = hierarchy.get("planned_actor_attachments", [])
    if not edges:
        raise HierarchyVerificationError("No directly mapped actor attachments.")
    source_entity_ids = {row["entity_id"] for row in plan.get("entities", [])}
    outputs = []
    for edge in edges:
        child_id = edge["entity_id"]
        parent_id = edge["source_parent_entity_id"]
        expected_parent = edge["parent_actor_label"]
        expected_child = edge["actor_label"]
        if child_id not in source_entity_ids or parent_id not in source_entity_ids:
            raise HierarchyVerificationError("Hierarchy references unknown source entity.")
        series = []
        attachment_matches = []
        for src_frame, tgt_frame, stamp in pairs:
            src = _index(src_frame, "source sample")
            tgt = _index(tgt_frame, "target sample")
            for who in (parent_id, child_id):
                if who not in src or who not in tgt:
                    raise HierarchyVerificationError(
                        f"Missing mapped parent or child entity: {who}"
                    )
            if (
                tgt[parent_id].get("actor_label") != expected_parent
                or tgt[child_id].get("actor_label") != expected_child
            ):
                raise HierarchyVerificationError("Target actor mapping changed.")
            layers = [
                item for item in tgt_frame.get("motion_layers", [])
                if item.get("entity_id") == child_id
            ]
            if len(layers) != 1:
                raise HierarchyVerificationError(
                    "Expected one target child attachment observation at each time."
                )
            matched = layers[0].get("attached_to_actor_label") == expected_parent
            attachment_matches.append(matched)
            src_parent = src[parent_id]["world_transform"]
            src_child = src[child_id]["world_transform"]
            tgt_parent = tgt[parent_id]["world_transform"]
            tgt_child = tgt[child_id]["world_transform"]
            src_local = _relative_point(src_parent, src_child)
            tgt_local = _relative_point(tgt_parent, tgt_child)
            src_child_pos = _vec(src_child.get("position_m"), 3, "source child position")
            tgt_child_pos = _vec(tgt_child.get("position_m"), 3, "target child position")
            src_parent_pos = _vec(src_parent.get("position_m"), 3, "source parent position")
            tgt_parent_pos = _vec(tgt_parent.get("position_m"), 3, "target parent position")
            world_error = math.dist(src_child_pos, tgt_child_pos) * 100.0
            local_error = math.dist(src_local, tgt_local) * 100.0
            series.append({
                "time_seconds": stamp,
                "attachment_matches": matched,
                "source_parent_local_child_m": [round(x, 6) for x in src_local],
                "target_parent_local_child_m": [round(x, 6) for x in tgt_local],
                "relative_offset_error_cm": round(local_error, 4),
                "child_world_position_error_cm": round(world_error, 4),
                "parent_world_position_error_cm": round(
                    math.dist(src_parent_pos, tgt_parent_pos) * 100.0, 4
                ),
            })
        max_world = max(row["child_world_position_error_cm"] for row in series)
        max_local = max(row["relative_offset_error_cm"] for row in series)
        flags = []
        if not all(attachment_matches):
            flags.append("TARGET_PARENT_ATTACHMENT_MISMATCH")
        if max_local > relative_limit:
            flags.append("PARENT_RELATIVE_OFFSET_MISMATCH")
        if max_world > world_limit:
            flags.append("CHILD_WORLD_POSITION_MISMATCH")
        outputs.append({
            "source_child_entity_id": child_id,
            "source_parent_entity_id": parent_id,
            "target_child_actor_label": expected_child,
            "target_parent_actor_label": expected_parent,
            "sample_count": len(series),
            "sampled_times_seconds": [row["time_seconds"] for row in series],
            "max_parent_relative_offset_error_cm": max_local,
            "max_child_world_position_error_cm": max_world,
            "max_parent_world_position_error_cm": max(
                row["parent_world_position_error_cm"] for row in series
            ),
            "flags": flags,
            "samples": series,
        })

    issues = any(edge["flags"] for edge in outputs)
    return {
        "schema_version": "0.1.0",
        "kind": "cinetwin.sampled_hierarchy_verification",
        "cutscene_id": plan["cutscene_id"],
        "status": "MISMATCH_DETECTED" if issues else "MATCH_AT_SAMPLED_TIMES",
        "sample_count": len(pairs),
        "total_source_sample_count": len(plan["samples"]),
        "verified_direct_attachment_count": len(outputs),
        "unresolved_source_parent_count": len(
            hierarchy.get("unresolved_source_parents", [])
        ),
        "world_tolerance_cm": world_limit,
        "relative_tolerance_cm": relative_limit,
        "attachments": outputs,
        "limitations": [
            "Sampled timestamps only; not proof of all-frame animation equivalence.",
            "TRS local-offset approximation cannot represent sheared transforms.",
            "Only independently mapped direct actor attachments are checked.",
            "Target level attachment exists in editor memory; persistence not checked.",
            "Camera, skeletal pose, rendering, audio and events remain unverified.",
        ],
    }


def verify_files(
    plan_path: str | Path,
    source_path: str | Path,
    target_path: str | Path,
    hierarchy_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    def load(path: str | Path) -> dict[str, Any]:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    result = verify_hierarchy(
        load(plan_path), load(source_path), load(target_path), load(hierarchy_path)
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
