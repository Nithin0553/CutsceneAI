"""Phase 10.2: conservative source-bound *static* character yaw eligibility.

No model numbers or user prose influence the correction. Every candidate is
recomputed from immutable original source capture, independently reopened
Unreal ticks, explicitly reviewed mesh anatomy, reference-calibrated bones and
the read-only native actor/component ownership receipt.

This function does not grant permission to execute, and cannot certify
rendered fidelity. The Unreal editor must recheck active animation, attachments
and transform ownership immediately before attempting one reversible edit.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import studio_character_facing_review as facing
import studio_element7_readback as readback
import studio_element8_repair as repair
import studio_element9_outcome as outcome
from mesh_forward_basis import MeshForwardError, bind_profile
from rig_pose_calibration import RigCalibrationError, _angle, _quat, unreal_to_canonical_quat

KIND = "cutsceneai.studio.static_character_yaw_review"
MIN_CORRECTION_DEGREES = 5.0
MAX_CORRECTION_DEGREES = 180.0
STATIC_DRIFT_CM = 0.1
STATIC_ROTATION_DEGREES = 0.25
POSITION_TOLERANCE_CM = 1.0
NATIVE_ROTATION_TOLERANCE_DEGREES = 0.25
_SOURCE_BAD_TRACKS = frozenset({
    "animation.track", "animation.section", "transform.track", "transform.section",
})
_FIX = re.compile(r"\b(?:fix|correct|repair|restore|align|rotate|turn|adjust)\b", re.I)
_NEGATE = re.compile(r"\b(?:don't|dont|do not|without|never|stop|avoid)\b", re.I)
_UNSAFE = re.compile(
    r"\b(?:moving|walk|walking|run|running|animated|animating|"
    r"root.motion|retarget|ik|bone|skeletal|rig|camera|lens|cut|"
    r"translate|position|move|physics|material|mesh.asset|import)\b", re.I,
)


class StaticCharacterYawError(ValueError):
    """A static actor yaw edit would not be independently justified."""


def message_requests_static_yaw(message: Any) -> bool:
    return bool(
        facing.relevant_feedback(message) and _FIX.search(message)
        and not _NEGATE.search(message) and not _UNSAFE.search(message)
        and not re.search(r"\b(?:all|every|multiple|both)\s+(?:characters|actors)\b",
                          message, re.I)
    )


def _one(rows: Any, entity_id: str, collection: str, *, label: str | None = None) -> dict:
    if not isinstance(rows, list):
        raise StaticCharacterYawError("Native character sample collection missing.")
    matches = [row for row in rows
               if isinstance(row, dict) and row.get("entity_id") == entity_id]
    if len(matches) != 1:
        raise StaticCharacterYawError("One exact source-mapped character sample required.")
    row = matches[0]
    if label is not None and row.get("actor_label") != label:
        raise StaticCharacterYawError("Native character actor label changed.")
    if collection not in row or not isinstance(row[collection], dict):
        raise StaticCharacterYawError("Character sample transform is incomplete.")
    return row


def _vector(row: dict, name: str, count: int) -> tuple[float, ...]:
    value = row.get(name)
    if not isinstance(value, (tuple, list)) or len(value) != count:
        raise StaticCharacterYawError("Source/native character vector is incomplete.")
    try:
        vec = tuple(float(v) for v in value)
    except (ValueError, TypeError) as exc:
        raise StaticCharacterYawError("Invalid source/native character vector.") from exc
    if not all(math.isfinite(v) and abs(v) < 100000 for v in vec):
        raise StaticCharacterYawError("Source/native character vector is not finite.")
    return vec


def _upright_yaw(canonical_quat: Any) -> float:
    try:
        q = _quat(canonical_quat, "Canonical world actor quaternion")
    except RigCalibrationError as exc:
        raise StaticCharacterYawError(str(exc)) from exc
    if abs(q[0]) > 0.002 or abs(q[2]) > 0.002:
        raise StaticCharacterYawError(
            "A pitched/rolled character requires a non-yaw native correction."
        )
    return _wrap(math.degrees(2 * math.atan2(-q[1], q[3])))


def _wrap(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


def _row_pose(frame: dict, entity_id: str, *, source: bool) -> list[tuple]:
    poses = [row for row in frame.get("skeletal_poses", [])
             if isinstance(row, dict) and row.get("entity_id") == entity_id]
    if len(poses) != 1:
        raise StaticCharacterYawError("Character skeletal pose is missing or ambiguous.")
    bones = poses[0].get("bones")
    if not isinstance(bones, list) or not bones or len(bones) > 512:
        raise StaticCharacterYawError("Character skeletal bone inventory unsupported.")
    pairs = []
    for bone in bones:
        key = bone.get("bone_id" if source else "bone_name")
        if not isinstance(key, str) or not key:
            raise StaticCharacterYawError("Missing unique skeletal bone identity.")
        try:
            if source:
                world = bone["world_transform"]
                pos = _vector(world, "position_m", 3)
                q = _quat(world["rotation_xyzw"], "Source skeletal bone")
            else:
                pos = _vector(bone, "world_position_m", 3)
                q = unreal_to_canonical_quat(bone["unreal_world_rotation_xyzw"])
        except (KeyError, TypeError, ValueError, RigCalibrationError) as exc:
            raise StaticCharacterYawError(
                "Native/source full skeletal bone transform is unavailable."
            ) from exc
        pairs.append((key, pos, q))
    if len({row[0] for row in pairs}) != len(pairs):
        raise StaticCharacterYawError("Duplicate observed skeletal bone.")
    return sorted(pairs, key=lambda x: x[0])


def _static_pose_grid(frames: list[dict], ident: str, source: bool) -> None:
    first = None
    for frame in frames:
        bones = _row_pose(frame, ident, source=source)
        if first is None:
            first = bones
        if [p[0] for p in bones] != [p[0] for p in first]:
            raise StaticCharacterYawError("Skeletal bone identities changed during cut.")
        if any(
            math.dist(row[1], base[1]) * 100 > STATIC_DRIFT_CM
            or _angle(row[2], base[2]) > STATIC_ROTATION_DEGREES
            for row, base in zip(bones, first)
        ):
            raise StaticCharacterYawError(
                "Moving or rotating skeletal bones cannot use actor base yaw."
            )


def build(workspace: Path, job: dict[str, Any]) -> dict[str, Any]:
    try:
        root, candidate, original, csir, mapping, compiled = outcome._context(
            workspace, job.get("job_id")
        )
        if original != job:
            raise StaticCharacterYawError("Stale job identity.")
        folders = outcome.discover(root, job["job_id"])
        if not folders:
            raise StaticCharacterYawError("Independent reopened native evidence missing.")
        bounded = repair.build(root, job["job_id"], folders)
        native = readback.build(root, job["job_id"], folders[-1])
        comparison, _ = readback._safe_json(folders[-1] / "comparison.json")
        source, _ = readback._safe_json(Path(job["capture"]))
        target, _ = readback._safe_json(folders[-1] / "target-behavior.json")
        approval, _ = readback._safe_json(folders[-1] / "mesh-forward-approval.json")
        calibration, _ = readback._safe_json(folders[-1] / "rig-calibration.json")
        owner, _ = readback._safe_json(
            folders[-1] / "native-character-facing-ownership.json"
        )
    except StaticCharacterYawError:
        raise
    except (outcome.OutcomeError, repair.BoundedRepairError,
            readback.Element7ReadbackError, OSError, ValueError,
            TypeError, KeyError) as exc:
        raise StaticCharacterYawError(
            "Independent source/native yaw and pose evidence is missing or stale."
        ) from exc
    if (bounded.get("status") in {
            "STOP_MEASURED_REGRESSION_OR_NO_PROGRESS",
            "STOP_REMEASUREMENT_BUDGET_EXHAUSTED",
        }
            or bounded.get("element3_workflow_sha256") is None
            or native.get("native_attempt", {}).get("native_builder_completed") is not True
            or native.get("distinct_reopened_editor_observed") is not True
            or native.get("target_tick_sampling_status")
            != "TICK_SYNCHRONIZED_FULL_GRID_CLAIMED"
            or comparison.get("rig_calibration_sha256") is None
            or comparison.get("mesh_forward_approval_sha256") is None
            or comparison.get("native_facing_ownership_sha256") is None):
        raise StaticCharacterYawError(
            "Source-authorized original full-grid, rig and owner proof is required."
        )
    characters = [e for e in csir.get("entities", [])
                  if isinstance(e, dict) and e.get("ced_type") == "entity.character"]
    if len(characters) != 1:
        raise StaticCharacterYawError("Exactly one source character is supported.")
    char = characters[0]
    name, ident = char.get("name"), char.get("entity_id")
    mapped = (mapping.get("entities") or {}).get(name)
    label = mapped.get("actor_label") if isinstance(mapped, dict) else None
    if not all(isinstance(x, str) and x for x in (name, ident, label)):
        raise StaticCharacterYawError("Unique source character target mapping required.")
    if any(
        t.get("binding_entity_id") == ident or
        t.get("ced_type") in _SOURCE_BAD_TRACKS and
        (t.get("binding_entity_id") == ident or t.get("binding_entity_id") is None)
        for t in csir.get("tracks", []) if isinstance(t, dict)
    ):
        raise StaticCharacterYawError("Source-authored character animation or transform owner.")
    if any(
        a.get("source_entity_id") == ident
        and a.get("kind") not in {"spawn_actor", "material_override"}
        for a in compiled.get("actions", []) if isinstance(a, dict)
    ):
        raise StaticCharacterYawError("Compiled character action owns a transform/property.")
    rigs = comparison.get("rig_motion_diagnostics") or []
    rig = next((r for r in rigs if r.get("entity_id") == ident), None)
    actor_metrics = next((e for e in comparison.get("entities", [])
                          if e.get("entity_id") == ident), None)
    owners = [row for row in owner.get("characters", [])
              if row.get("entity_id") == ident]
    if (rig is None or actor_metrics is None or len(owners) != 1
            or owner.get("native_edit_authorized") is not False
            or owners[0].get("native_edit_authorized") is not False
            or owners[0].get("status")
            != "STATIC_NATIVE_OWNER_CANDIDATE_REQUIRES_SOURCE_PROOF"
            or owners[0].get("blocking_reasons") != []
            or owners[0].get("target_actor_label") != label):
        raise StaticCharacterYawError("Native skeletal component/actor owner is unresolved.")
    if (rig.get("joint_reference_orientation", {}).get("status") != "PASS"
            or rig.get("joint_angular_motion", {}).get("status") != "PASS"
            or rig.get("joint_positions", {}).get("status") != "PASS"
            or rig.get("flags") != ["CHARACTER_MESH_ANATOMICAL_FORWARD_MISMATCH"]
            or set(actor_metrics.get("flags", [])) -
            {"WORLD_ROTATION_OUTSIDE_TOLERANCE"}
            or any(r.get("flags") for r in rigs if r.get("entity_id") != ident)
            or any(e.get("flags") for e in comparison.get("entities", [])
                   if e.get("entity_id") != ident)):
        raise StaticCharacterYawError(
            "A different rig/actor/scene discrepancy requires separate analysis."
        )
    forward = rig.get("anatomical_mesh_forward") or {}
    if (forward.get("status") != "FAIL"
            or forward.get("constant_yaw_diagnostic_status")
            != "STABLE_SAMPLED_YAW_DIAGNOSTIC_ONLY"
            or forward.get("suggestion_applied") is not False
            or forward.get("native_actor_yaw_repair_authorized") is not False
            or forward.get("requires_original_full_grid_validation") is not True):
        raise StaticCharacterYawError("Anatomical forward mismatch lacks stable yaw proof.")
    yaw = forward.get("suggested_target_actor_yaw_correction_degrees")
    if (type(yaw) not in (int, float) or not math.isfinite(yaw)
            or not MIN_CORRECTION_DEGREES <= abs(yaw) <= MAX_CORRECTION_DEGREES
            or forward.get("max_sampled_yaw_variation_degrees", 999) > 0.5
            or forward.get("max_yaw_only_residual_degrees", 999) > 2.0):
        raise StaticCharacterYawError("Static yaw difference is absent or unsafe.")
    frames_a, frames_b = source.get("samples"), target.get("samples")
    if (not isinstance(frames_a, list) or not isinstance(frames_b, list)
            or len(frames_a) != len(frames_b) or len(frames_a) < 2
            or len(frames_a) != forward.get("sample_count")):
        raise StaticCharacterYawError("Source/native complete frame grid differs.")
    first_a = first_b = None
    first_native_yaw = None
    previous_time = None
    approved = bind_profile(approval, readback._safe_json(
        folders[-1] / "sampling-plan.json"
    )[0], target, ident)
    if approved["target_mesh_asset_path"] != owners[0].get("native_skeletal_mesh_asset_path"):
        raise StaticCharacterYawError("Approved mesh source/native identity differs.")
    for src_frame, tgt_frame in zip(frames_a, frames_b):
        t, native_t = src_frame.get("time_seconds"), tgt_frame.get("time_seconds")
        if (type(t) not in (float, int) or type(native_t) not in (float, int)
                or not math.isfinite(t) or not math.isfinite(native_t)
                or abs(t - native_t) > 1e-7
                or (previous_time is not None and t <= previous_time)):
            raise StaticCharacterYawError("Static character source/native sample time grid differs.")
        previous_time = t
        a = _one(src_frame.get("entities"), ident, "world_transform")["world_transform"]
        b = _one(tgt_frame.get("entities"), ident, "world_transform",
                 label=label)["world_transform"]
        pa, pb = _vector(a, "position_m", 3), _vector(b, "position_m", 3)
        if math.dist(pa, pb) * 100 > POSITION_TOLERANCE_CM:
            raise StaticCharacterYawError("Actor placement differs; yaw-only edit cannot help.")
        qa, qb = _quat(a["rotation_xyzw"], "source actor"), _quat(
            b["rotation_xyzw"], "native target actor"
        )
        a_yaw, b_yaw = _upright_yaw(qa), _upright_yaw(qb)
        if any(
            max(abs(v - 1) for v in _vector(row, "scale_xyz", 3)) > 0.01
            for row in (a, b)
        ):
            raise StaticCharacterYawError("Non-unit actor scale blocks static yaw.")
        bases = [row for row in tgt_frame.get("skeletal_mesh_component_bases", [])
                 if row.get("entity_id") == ident]
        if (len(bases) != 1 or bases[0].get("status") != "OBSERVED"
                or bases[0].get("target_mesh_asset_path")
                != approved["target_mesh_asset_path"] or _angle(
                    qb,
                    unreal_to_canonical_quat(
                        bases[0]["unreal_component_world_rotation_xyzw"]
                    )
                ) > NATIVE_ROTATION_TOLERANCE_DEGREES):
            raise StaticCharacterYawError(
                "Native mesh world forward does not follow actor base rotation."
            )
        if first_a is None:
            first_a = (pa, qa, a_yaw)
            first_b = (pb, qb, b_yaw)
            first_native_yaw = b_yaw
        elif (math.dist(pa, first_a[0]) * 100 > STATIC_DRIFT_CM
              or math.dist(pb, first_b[0]) * 100 > STATIC_DRIFT_CM
              or _angle(qa, first_a[1]) > STATIC_ROTATION_DEGREES
              or _angle(qb, first_b[1]) > STATIC_ROTATION_DEGREES):
            raise StaticCharacterYawError(
                "A moving/rotating character cannot use actor static yaw."
            )
    _static_pose_grid(frames_a, ident, source=True)
    _static_pose_grid(frames_b, ident, source=False)
    if abs(_wrap(first_native_yaw - owners[0][
            "native_actor_roll_pitch_yaw_degrees"][2])) > NATIVE_ROTATION_TOLERANCE_DEGREES:
        raise StaticCharacterYawError("Reopened native actor yaw differs from sampled rotation.")
    report = {
        "kind": KIND, "eligible": True,
        "source_entity_id": ident, "source_character_name": name,
        "target_actor_label": label,
        "target_mesh_asset_path": approved["target_mesh_asset_path"],
        "native_yaw_before_degrees": round(first_native_yaw, 6),
        "derived_yaw_correction_degrees": round(yaw, 6),
        "native_yaw_after_degrees": round(_wrap(first_native_yaw+yaw), 6),
        "element7_readback_sha256": native["readback_sha256"],
        "element8_repair_sha256": bounded["repair_plan_sha256"],
        "native_facing_ownership_sha256": comparison["native_facing_ownership_sha256"],
        "sample_count": len(frames_a),
        "native_edit_authorized": False,
        "full_cutscene_fidelity_verified": False,
    }
    report["character_yaw_repair_sha256"] = repair._hash(report)
    return report
