"""CineTwin source-vs-target measured behavior comparison (pure Python).

Only compare observations with compatible semantics: canonical world actor
transforms for explicitly mapped entities. Native skeletal bone names/orientations,
camera optics, lights, render frames, audio and events are NOT compared here.
Never claim a cutscene passes based solely on these partial measurements.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from sampling_plan import validate_capture
from target_observation_plan import prepare_observation


class BehavioralComparisonError(ValueError):
    """Observed evidence is inconsistent; comparison must fail closed."""


def _finite(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise BehavioralComparisonError(f"{label}: expected a number.") from exc
    if not math.isfinite(result):
        raise BehavioralComparisonError(f"{label}: non-finite measurement.")
    return result


def _vector(values: Any, size: int, label: str) -> tuple[float, ...]:
    if not isinstance(values, (list, tuple)) or len(values) != size:
        raise BehavioralComparisonError(f"{label}: expected {size} numeric values.")
    return tuple(_finite(value, label) for value in values)


def _position(transform: dict[str, Any], label: str) -> tuple[float, float, float]:
    return _vector(transform.get("position_m"), 3, label)  # type: ignore[return-value]


def _distance_m(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return math.dist(a, b)


def _rotation_error_degrees(
    left: tuple[float, ...], right: tuple[float, ...]
) -> float:
    # Double-cover property: q and -q represent the same orientation.
    la = math.sqrt(sum(x * x for x in left))
    lb = math.sqrt(sum(x * x for x in right))
    if abs(la - 1.0) > 0.05 or abs(lb - 1.0) > 0.05:
        raise BehavioralComparisonError(
            "A sampled quaternion is not approximately unit length."
        )
    cos_half = abs(sum(a * b for a, b in zip(left, right)) / (la * lb))
    return math.degrees(2.0 * math.acos(min(1.0, max(-1.0, cos_half))))


def _index_entities(
    sample: dict[str, Any], sample_index: int, side: str
) -> dict[str, dict[str, Any]]:
    entities = sample.get("entities", [])
    if not isinstance(entities, list):
        raise BehavioralComparisonError(f"{side} sample {sample_index}: no entity list.")
    by_id: dict[str, dict[str, Any]] = {}
    for entity in entities:
        identifier = entity.get("entity_id")
        if not isinstance(identifier, str) or not identifier or identifier in by_id:
            raise BehavioralComparisonError(
                f"{side} sample {sample_index}: invalid or repeated entity identity."
            )
        by_id[identifier] = entity
    return by_id


def _pose_motion_cm(
    samples: list[dict[str, Any]], rig_id: str, *, target: bool
) -> dict[str, Any]:
    """Motion-presence diagnostic, NOT cross-rig pose equivalence."""
    initial: dict[str, tuple[float, float, float]] = {}
    maximum_cm = 0.0
    expected_bones: set[str] | None = None
    for i, sample in enumerate(samples):
        poses = sample.get("skeletal_poses", [])
        matching = [item for item in poses if item.get("entity_id") == rig_id]
        if len(matching) != 1:
            raise BehavioralComparisonError(
                f"Sample {i} rig {rig_id}: missing or repeated skeletal pose."
            )
        bones = matching[0].get("bones", [])
        current: dict[str, tuple[float, float, float]] = {}
        for bone in bones:
            bone_id = bone.get("bone_name") if target else bone.get("bone_id")
            if not isinstance(bone_id, str) or not bone_id or bone_id in current:
                raise BehavioralComparisonError(
                    f"Sample {i} rig {rig_id}: invalid native bone identifier."
                )
            point = (
                _vector(bone.get("world_position_m"), 3, "target bone world position")
                if target
                else _position(bone.get("world_transform", {}), "source bone world position")
            )
            current[bone_id] = point  # type: ignore[assignment]
        if not current:
            raise BehavioralComparisonError(f"Rig {rig_id} has no captured bones.")
        if expected_bones is None:
            expected_bones = set(current)
            initial = current
        elif set(current) != expected_bones:
            raise BehavioralComparisonError(
                f"Sample {i} rig {rig_id}: bone list changed across observations."
            )
        maximum_cm = max(
            maximum_cm,
            *(_distance_m(point, initial[name]) * 100.0
              for name, point in current.items()),
        )
    return {"bone_count": len(initial), "maximum_bone_displacement_from_start_cm": round(maximum_cm, 4)}


def _check_identity(
    plan: dict[str, Any],
    source: dict[str, Any],
    target: dict[str, Any],
) -> None:
    if target.get("kind") != "cinetwin.target_behavior_observation":
        raise BehavioralComparisonError("Target file is not CineTwin target observations.")
    if source.get("kind") != "cinetwin.behavior_capture":
        raise BehavioralComparisonError("Source file is not CineTwin behavior capture.")
    for document in (source, target):
        if document.get("cutscene_id") != plan.get("cutscene_id"):
            raise BehavioralComparisonError("A capture has a different source cutscene ID.")
        for key in (
            "csir_sha256", "sequence_ref", "project_fingerprint",
        ):
            if document.get("source", {}).get(key) != plan.get("source", {}).get(key):
                raise BehavioralComparisonError(
                    f"Capture source identity {key} does not match sampling plan."
                )


def _validate_times(plan: dict[str, Any], target: dict[str, Any]) -> None:
    times = [_finite(x["time_seconds"], "sampling plan time") for x in plan["samples"]]
    observed = target.get("samples", [])
    if len(observed) != len(times):
        raise BehavioralComparisonError(
            f"Expected {len(times)} target samples, got {len(observed)}. "
            "A smoke capture is not a full comparable target."
        )
    for i, (expected, sample) in enumerate(zip(times, observed)):
        measured = _finite(sample.get("time_seconds"), f"target sample {i} time")
        if abs(expected - measured) > 1e-7:
            raise BehavioralComparisonError(
                f"Target sample {i} does not match source timestamp: "
                f"{measured} vs {expected}."
            )
    coverage = target.get("coverage", {})
    if coverage.get("full_temporal_coverage") is not True:
        raise BehavioralComparisonError("Target did not report full temporal coverage.")
    if coverage.get("sample_count") != len(times):
        raise BehavioralComparisonError("Target coverage sample count is inconsistent.")


def compare(
    plan: dict[str, Any],
    source: dict[str, Any],
    target: dict[str, Any],
    *,
    position_tolerance_cm: float = 1.0,
    orientation_tolerance_degrees: float = 2.0,
) -> dict[str, Any]:
    """Compare mapped native actors in common canonical world coordinates.

    Positions are in meters in both files, errors returned in centimeters.
    Unmapped entities or unavailable domains are always kept as incomplete.
    """
    position_limit = _finite(position_tolerance_cm, "position tolerance")
    orientation_limit = _finite(orientation_tolerance_degrees, "rotation tolerance")
    if position_limit <= 0.0 or orientation_limit <= 0.0:
        raise BehavioralComparisonError("Thresholds must be positive.")

    _check_identity(plan, source, target)
    src_validation = validate_capture(plan, source)
    if src_validation["failures"]:
        raise BehavioralComparisonError(
            "Source capture failed verification: "
            + "; ".join(src_validation["failures"][:3])
        )
    _validate_times(plan, target)

    source_samples = source["samples"]
    target_samples = target["samples"]
    expected_ids = {entry["entity_id"] for entry in plan["entities"]}
    if len(expected_ids) != len(plan["entities"]):
        raise BehavioralComparisonError("Sampling plan has repeated entity identities.")
    unmapped = target.get("coverage", {}).get("unmapped_source_entities", [])
    missing_ids = [entry.get("entity_id") for entry in unmapped]
    if len(set(missing_ids)) != len(missing_ids):
        raise BehavioralComparisonError("Target has duplicate unmapped entity identities.")
    if not set(missing_ids) <= expected_ids:
        raise BehavioralComparisonError("Target lists unknown unmapped entities.")

    # The target actor bindings are inferred from its saved observation at every
    # sample. A mapped actor must remain present with a stable actor label.
    first_target = _index_entities(target_samples[0], 0, "target")
    bound = {
        eid: str(record["actor_label"])
        for eid, record in first_target.items()
    }
    if not bound or (set(bound) & set(missing_ids)):
        raise BehavioralComparisonError("Invalid or overlapping mapped actor coverage.")
    if set(bound) | set(missing_ids) != expected_ids:
        raise BehavioralComparisonError("Mapped + unmapped entities do not cover the plan.")
    if len(set(bound.values())) != len(bound):
        raise BehavioralComparisonError("Duplicated target actor label.")

    by_id = {entry["entity_id"]: entry for entry in plan["entities"]}
    trajectory = {
        eid: {"position_errors_cm": [], "rotation_errors_degrees": [],
              "source_positions": [], "target_positions": []}
        for eid in bound
    }
    for index, (src_frame, tgt_frame) in enumerate(zip(source_samples, target_samples)):
        source_entities = _index_entities(src_frame, index, "source")
        target_entities = _index_entities(tgt_frame, index, "target")
        if set(source_entities) != expected_ids or set(target_entities) != set(bound):
            raise BehavioralComparisonError(
                f"Sample {index}: actor identities missing or changed."
            )
        for eid, label in bound.items():
            record = target_entities[eid]
            if record.get("actor_label") != label:
                raise BehavioralComparisonError(
                    f"Sample {index}: actor label changed for {eid}."
                )
            src_transform = source_entities[eid]["world_transform"]
            tgt_transform = record["world_transform"]
            src_pos = _position(src_transform, "source position")
            tgt_pos = _position(tgt_transform, "target position")
            src_quat = _vector(src_transform.get("rotation_xyzw"), 4, "source rotation")
            tgt_quat = _vector(tgt_transform.get("rotation_xyzw"), 4, "target rotation")
            _vector(src_transform.get("scale_xyz"), 3, "source scale")
            _vector(tgt_transform.get("scale_xyz"), 3, "target scale")
            details = trajectory[eid]
            details["source_positions"].append(src_pos)
            details["target_positions"].append(tgt_pos)
            details["position_errors_cm"].append(_distance_m(src_pos, tgt_pos) * 100.0)
            details["rotation_errors_degrees"].append(
                _rotation_error_degrees(src_quat, tgt_quat)
            )

    results = []
    for eid, measures in trajectory.items():
        epos = measures["position_errors_cm"]
        erot = measures["rotation_errors_degrees"]
        src_pos = measures["source_positions"]
        tgt_pos = measures["target_positions"]
        src_start, tgt_start = src_pos[0], tgt_pos[0]
        source_motion = max(_distance_m(p, src_start) * 100 for p in src_pos)
        target_motion = max(_distance_m(p, tgt_start) * 100 for p in tgt_pos)
        relative_errors = [
            _distance_m(
                tuple(p[k] - src_start[k] for k in range(3)),
                tuple(q[k] - tgt_start[k] for k in range(3)),
            ) * 100.0
            for p, q in zip(src_pos, tgt_pos)
        ]
        max_index = max(range(len(epos)), key=lambda i: epos[i])
        max_rotation_index = max(range(len(erot)), key=lambda i: erot[i])
        flags = []
        if max(epos) > position_limit:
            flags.append("WORLD_POSITION_OUTSIDE_TOLERANCE")
        if max(erot) > orientation_limit:
            flags.append("WORLD_ROTATION_OUTSIDE_TOLERANCE")
        if source_motion > 1.0 and target_motion < 0.1:
            flags.append("SOURCE_MOVES_BUT_TARGET_ACTOR_STATIC")
        results.append({
            "entity_id": eid,
            "source_name": by_id[eid].get("name", ""),
            "ced_type": by_id[eid].get("ced_type", ""),
            "target_actor_label": bound[eid],
            "sample_count": len(epos),
            "mean_world_position_error_cm": round(sum(epos) / len(epos), 4),
            "max_world_position_error_cm": round(max(epos), 4),
            "max_world_position_error_time_s": target_samples[max_index]["time_seconds"],
            "end_world_position_error_cm": round(epos[-1], 4),
            "initial_world_offset_cm": [
                round((tgt_start[k] - src_start[k]) * 100.0, 4)
                for k in range(3)
            ],
            "initial_world_position_error_cm": round(epos[0], 4),
            "max_relative_trajectory_error_cm": round(max(relative_errors), 4),
            "end_relative_trajectory_error_cm": round(relative_errors[-1], 4),
            "source_max_motion_from_start_cm": round(source_motion, 4),
            "target_max_motion_from_start_cm": round(target_motion, 4),
            "max_world_rotation_error_degrees": round(max(erot), 4),
            "max_world_rotation_error_time_s":
                target_samples[max_rotation_index]["time_seconds"],
            "flags": flags,
        })
    results.sort(
        key=lambda item: (
            -item["max_world_position_error_cm"],
            -item["max_world_rotation_error_degrees"],
            item["source_name"],
        )
    )

    rig_ids = set(plan.get("skeletal_entity_ids", []))
    if not rig_ids <= set(bound):
        raise BehavioralComparisonError("Target observation omitted mapped skeletal rigs.")
    target_native_rigs = target.get("native_rigs", [])
    if {rig.get("entity_id") for rig in target_native_rigs} != rig_ids:
        raise BehavioralComparisonError("Target native rig definitions are incomplete.")
    rig_diagnostics = []
    for eid in sorted(rig_ids):
        src_motion = _pose_motion_cm(source_samples, eid, target=False)
        tgt_motion = _pose_motion_cm(target_samples, eid, target=True)
        flags = []
        if (
            src_motion["maximum_bone_displacement_from_start_cm"] > 1.0
            and tgt_motion["maximum_bone_displacement_from_start_cm"] < 0.1
        ):
            flags.append("SOURCE_BONES_MOVE_BUT_TARGET_BONES_STATIC")
        rig_diagnostics.append({
            "entity_id": eid, "source_name": by_id[eid].get("name", ""),
            "source": src_motion, "target": tgt_motion,
            "flags": flags,
            "comparison_policy": "MOTION_PRESENCE_ONLY_NO_BONE_RETARGET_MAP",
        })
    # A large absolute difference can be a fixed world-space placement
    # offset, while a moving source actor and stationary Unreal actor can
    # indicate a different motion carrier (bones/components vs actor).
    # These are *diagnostic hypotheses*, never proof of matching animation.
    rig_by_id = {entry["entity_id"]: entry for entry in rig_diagnostics}
    for item in results:
        source_motion = item["source_max_motion_from_start_cm"]
        target_motion = item["target_max_motion_from_start_cm"]
        relative_error = item["max_relative_trajectory_error_cm"]
        initial_error = item["initial_world_position_error_cm"]
        if source_motion <= 0.1 and target_motion <= 0.1:
            category = (
                "STATIC_PLACEMENT_MISMATCH" if initial_error > position_limit
                else "STATIC_ACTOR_TRANSFORM_MATCH"
            )
        elif source_motion > 1.0 and target_motion < 0.1:
            rig = rig_by_id.get(item["entity_id"])
            native_bones_move = (
                rig is not None
                and rig["target"]["maximum_bone_displacement_from_start_cm"] > 1.0
            )
            category = (
                "MOTION_MAY_BE_CARRIED_BY_SKELETON"
                if native_bones_move else "MOTION_NOT_OBSERVED_ON_TARGET_ACTOR"
            )
        elif relative_error <= position_limit and initial_error > position_limit:
            category = "INITIAL_PLACEMENT_OFFSET_DOMINATES"
        elif relative_error > position_limit:
            category = "RELATIVE_TRAJECTORY_MISMATCH"
        else:
            category = "ACTOR_TRAJECTORY_WITHIN_TOLERANCE"
        item["motion_diagnostic"] = category
        if category == "MOTION_MAY_BE_CARRIED_BY_SKELETON":
            item["motion_hypothesis_note"] = (
                "Actor stays stationary but native target bones move. "
                "Possible motion ownership difference; this does not prove "
                "that source trajectory or final pose matches."
            )
    flags_present = any(item["flags"] for item in results + rig_diagnostics)

    return {
        "schema_version": "0.1.0",
        "kind": "cinetwin.behavior_comparison",
        "cutscene_id": plan["cutscene_id"],
        "evaluation": {
            "status": "DIFFERENCES_DETECTED" if flags_present else "NO_FLAGGED_DIFFERENCES",
            "overall_cutscene_fidelity": "NOT_ESTABLISHED",
            "sampling_times": len(target_samples),
            "mapped_actor_count": len(bound),
            "source_entity_count": len(expected_ids),
            "unmapped_entity_count": len(missing_ids),
            "position_tolerance_cm": position_limit,
            "orientation_tolerance_degrees": orientation_limit,
        },
        "entities": results,
        "rig_motion_diagnostics": rig_diagnostics,
        "unmapped_source_entities": unmapped,
        "motion_ownership_policy": (
            "ACTOR_VS_NATIVE_SKELETON_DIAGNOSTIC_ONLY;"
            "NO_AUTOMATIC_ROOT_MOTION_REPAIR"
        ),
        "unverified_domains": [
            "skeletal_pose_correspondence",
            "camera_optics",
            "light_appearance",
            "audio_output",
            "event_execution",
            "rendered_frame",
            "physics_state",
            "semantic_entity_coverage",
        ],
        "notes": [
            "Only mapped actor world transforms have directly comparable semantics.",
            "Native source and target bones are not paired; pose diagnostics measure "
            "presence of motion only and cannot establish pose accuracy.",
            "An apparently static actor may contain skeletal root motion; examine "
            "bone motion diagnostics before diagnosing a missing translation.",
            "Source and target observation methods may not evaluate external script "
            "side effects or frame-dependent physics identically.",
            "This diagnostic report does not modify any source or target asset.",
        ],
    }


def compare_files(
    plan_path: str | Path,
    source_path: str | Path,
    target_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8-sig"))
    source = json.loads(Path(source_path).read_text(encoding="utf-8-sig"))
    target = json.loads(Path(target_path).read_text(encoding="utf-8-sig"))
    report = compare(plan, source, target)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
