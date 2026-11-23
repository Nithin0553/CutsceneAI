"""Phase 10.2 — one cross-workstream, source-complete software audit.

This contract connects the seven original work areas to the *actual* CED
source-occurrence inventory and installed software analyzers. It never turns
an installed handler, a software test, or a model recommendation into live
Unity/Unreal, native persistence, or rendered fidelity certification.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

import feature_dispatch
import multi_character_sync
import phase10_2_effects_coverage
import timeline_blend_policy


KIND = "cutsceneai.studio.phase10_2.consolidated_software_audit"
VERSION = "1"
WORK_AREAS = (
    ("animated_camera","Autonomous animated-camera curve repair, native readback and rollback"),
    ("timeline","Complex Timeline blending, nested shots and multi-camera transitions"),
    ("moving_character","Moving-character positioning, facing and root-motion correction"),
    ("skeletal","Advanced skeletal retargeting and bone-pose calibration"),
    ("multi_character","Multi-character coordination and animated hierarchy handling"),
    ("effects","Lighting, shaders, audio, VFX, events and physics"),
    ("contracts","Production-contract audit, capability matrix and regression coverage"),
)
ADAPTER_SCOPE = (
    "restore_source_albedo","restore_constant_actor_offset",
    "restore_static_camera_lens","restore_single_camera_cut_timing",
    "restore_static_camera_position","restore_static_character_actor_yaw",
    "restore_two_shot_camera_switch","restore_static_camera_actor_yaw",
    "restore_single_animated_camera_position_key",
    "restore_two_animated_camera_position_keys",
    "restore_single_animated_camera_yaw_key",
)
SCOPES_UNSUPPORTED = (
    "arbitrary_multi_key_pitch_roll_or_quaternion_curve",
    "nested_time_warp_and_mixed_timeline_blends",
    "arbitrary_moving_skeletal_root_or_layered_ik_retarget",
    "unproven_animated_parent_hierarchy",
    "custom_shader_runtime_audio_event_vfx_physics_equivalence",
    "post_repair_reopened_native_and_rendered_cutscene_parity",
)


class Phase10_2AuditError(ValueError):
    """Untrusted original source or mismatched contract input."""


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value,sort_keys=True,separators=(",",":"),
                   allow_nan=False).encode("utf-8")
    ).hexdigest()


def _result(area: str, *, encountered: bool,
            evidence: dict[str,Any] | None = None,
            reasons: list[str] | None = None) -> dict[str,Any]:
    title=dict(WORK_AREAS)[area]
    return {
        "work_area_id":area,
        "title":title,
        "source_feature_encountered":bool(encountered),
        "software_contract_evidence":evidence or {},
        "acceptance_status":(
            "SOURCE_ABSENT_SCOPE_NOT_ENGINE_VALIDATED"
            if not encountered else
            "PARTIAL_SOFTWARE_SUPPORT_ENGINE_ACCEPTANCE_PENDING"
        ),
        "remaining_gates":sorted(set(reasons or [])),
        "real_editor_execution_verified":False,
        "reopened_native_persistence_verified":False,
        "independent_post_repair_cinetwin_verified":False,
        "rendered_fidelity_verified":False,
        "work_area_fully_complete":False,
    }


def audit(csir: dict[str,Any], mapping: dict[str,Any],
          plan: dict[str,Any], *,
          source_capture: dict[str,Any] | None = None,
          target_capture: dict[str,Any] | None = None) -> dict[str,Any]:
    """Audit every canonical source occurrence and all seven Phase 10.2 areas.

    The input can be synthetic or source-exported, so any source/target
    comparison here is **not** independently reopened engine evidence.
    """
    if (not isinstance(csir,dict) or not isinstance(mapping,dict)
            or not isinstance(plan,dict)
            or not isinstance(csir.get("entities",[]),list)
            or not isinstance(csir.get("tracks",[]),list)
            or not isinstance(plan.get("actions"),list)):
        raise Phase10_2AuditError("CSIR, mapping and compiled action plan are required.")
    if source_capture is not None and (
            not isinstance(source_capture,dict)
            or source_capture.get("cutscene_id") != csir.get("cutscene_id")):
        raise Phase10_2AuditError(
            "Original evaluated CineTwin source capture identity differs from CSIR."
        )
    if target_capture is not None and source_capture is None:
        raise Phase10_2AuditError(
            "Native target readback is meaningless without the matched source capture."
        )
    if target_capture is not None and (
            not isinstance(target_capture,dict)
            or target_capture.get("cutscene_id") != csir.get("cutscene_id")):
        raise Phase10_2AuditError(
            "Target CineTwin identity differs from original CSIR."
        )
    try:
        overall = feature_dispatch.audit(csir,plan)
        timeline = timeline_blend_policy.analyze_complex_timeline(csir,mapping)
        effects = phase10_2_effects_coverage.audit(csir,plan)
    except (feature_dispatch.FeatureDispatchError,
            timeline_blend_policy.TimelineBlendError,
            phase10_2_effects_coverage.EffectCoverageError,
            KeyError,ValueError,TypeError) as exc:
        raise Phase10_2AuditError(
            "Phase 10.2 source/action ownership and feature inventory cannot be reconciled."
        ) from exc
    if overall["unknown_action_kinds"]:
        raise Phase10_2AuditError("Unregistered native action is not an accepted capability.")
    source_counts=Counter(row["ced"] for row in overall["source_occurrences"])
    camera_source=sum(1 for row in csir["entities"]
                      if isinstance(row,dict) and row.get("ced_type")=="entity.camera")
    char_source=sum(1 for row in csir["entities"]
                    if isinstance(row,dict) and row.get("ced_type")=="entity.character")
    camera_actions=sum(a.get("kind") in ("transform","camera_fov","camera_cut")
                       for a in plan["actions"] if isinstance(a,dict))
    animation_actions=sum(a.get("kind") in (
        "skeletal_animation","skeletal_world_root_lock","transform")
        for a in plan["actions"] if isinstance(a,dict))
    skeletal_source=sum(1 for row in overall["source_occurrences"]
                        if row["ced"].startswith(("animation.","rig.","skeletal.","character.")))
    sync=None
    sync_error=None
    if char_source and source_capture is not None:
        try:
            sync=multi_character_sync.analyze(
                csir,source_capture,mapping=mapping,target=target_capture,
            )
        except (multi_character_sync.CharacterSyncError,
                KeyError,TypeError,ValueError) as exc:
            sync_error=str(exc)[:280]
    camera_evidence={
        "source_camera_count":camera_source,
        "source_camera_related_semantic_count":sum(
            v for k,v in source_counts.items() if k.startswith("camera.")
        ),
        "native_camera_action_candidates":camera_actions,
        "installed_bounded_software_adapters":[
            x for x in ADAPTER_SCOPE if "camera" in x or "shot" in x
        ],
    }
    timeline_evidence={
        "source_complex_timeline_track_count":timeline["source_track_count"],
        "camera_cut_sections":timeline["camera_cut_section_count"],
        "time_owners_with_blockers":timeline["source_time_owners_with_blockers"],
        "complex_timeline":timeline,
    }
    motion_evidence={
        "source_character_count":char_source,
        "native_animation_and_transform_candidates":animation_actions,
        "common_source_frame_grid_available":sync is not None,
        "source_capture_problem":sync_error,
    }
    skeletal_evidence={
        "source_skeletal_semantic_count":skeletal_source,
        "source_character_count":char_source,
        "approved_native_bone_reference_provided":False,
        "native_target_per_bone_pose_verified":False,
    }
    hierarchy_evidence={
        "source_character_count":char_source,
        "multi_character_source_grid":sync if char_source>=2 else None,
        "source_capture_problem":sync_error if char_source>=2 else None,
    }
    effects_evidence={
        "source_effect_occurrence_count":effects["effect_source_occurrence_count"],
        "effect_families":effects["effect_families"],
    }
    audit_evidence={
        "source_occurrences":overall["source_occurrence_count"],
        "accounted_source_occurrences":overall["accounted_occurrence_count"],
        "missing_adapter_count":overall["missing_adapter_count"],
        "unregistered_native_action_count":len(overall["unknown_action_kinds"]),
        "canonical_catalog_sha256":overall["catalog_sha256"],
        "exact_source_occurrences":overall["source_occurrences"],
    }
    effect_present=effects["effect_source_occurrence_count"]>0
    work = [
        _result("animated_camera",encountered=bool(camera_source),
                evidence=camera_evidence,reasons=[
                    "NATIVE_CURVE_AND_ROTATION_OWNERSHIP_PER_SUPPORTED_CASE",
                    "INDEPENDENT_EDITOR_KEY_READBACK_AND_ROLLBACK",
                    "RENDERED_FRAME_AND_BETWEEN_KEY_TRAJECTORY_COMPARISON",
                ]),
        _result("timeline",encountered=bool(timeline["source_track_count"]),
                evidence=timeline_evidence,reasons=[
                    "NATIVE_NESTED_SHOT_BLEND_AND_TIME_OWNER_ADAPTERS",
                    "SOURCE_TIME_GRID_AND_NATIVE_SECTION_REOPEN",
                    "CAMERA_CUT_RENDERED_CONTINUITY",
                ]),
        _result("moving_character",encountered=bool(char_source),
                evidence=motion_evidence,reasons=[
                    "APPROVED_SKELETAL_ROOT_MOTION_OWNER_AND_NATIVE_CORRECTION",
                    "FULL_SOURCE_TARGET_ACTOR_FACING_TRAJECTORY",
                    "REOPENED_CHARACTER_BONE_AND_ROOT_PARITY",
                ]),
        _result("skeletal",encountered=bool(skeletal_source or char_source),
                evidence=skeletal_evidence,reasons=[
                    "APPROVED_SOURCE_TARGET_REST_POSE_BONE_AXIS_AND_BONE_MAP",
                    "NATIVE_RETARGETED_POSE_AND_SKIN_DEFORMATION_READBACK",
                    "LAYERED_BLEND_IK_AND_ROOT_MOTION_PERSISTENCE",
                ]),
        _result("multi_character",encountered=char_source>=2,
                evidence=hierarchy_evidence,reasons=[
                    "SOURCE_MEASURED_MULTI_CHARACTER_HIERARCHY",
                    "NATIVE_MULTI_ACTOR_SYNC_AND_ATTACHMENT_OWNERS",
                    "INDEPENDENT_BONE_POSE_CONTACT_AND_RENDER_CHECK",
                ]),
        _result("effects",encountered=effect_present,
                evidence=effects_evidence,reasons=[
                    "NATIVE_PROPERTY_ASSET_EVENT_EFFECT_OWNER_READBACK",
                    "MATCHED_AUDIO_WAVEFORM_RENDERED_LIGHT_VFX_PHYSICS",
                    "CUSTOM_SHADER_SCRIPT_AND_MIDDLEWARE_CONTRACTS",
                ]),
        _result("contracts",encountered=True,
                evidence=audit_evidence,reasons=[
                    "ALL_REGISTERED_ADAPTERS_NATIVE_ENGINE_ACCEPTED",
                    "HELD_OUT_UNITY_UNREAL_CROSS_ENGINE_CASES",
                    "POST_REOPEN_ALL_SUPPORTED_FEATURE_MEASUREMENTS",
                ]),
    ]
    if len(work)!=len(WORK_AREAS):
        raise Phase10_2AuditError("Incomplete Phase 10.2 workstream matrix.")
    report={
        "kind":KIND,
        "schema_version":VERSION,
        "csir_snapshot_sha256":_digest(csir),
        "mapping_snapshot_sha256":_digest(mapping),
        "compiled_plan_snapshot_sha256":_digest(plan),
        "source_capture_snapshot_sha256":(
            _digest(source_capture) if source_capture is not None else None
        ),
        "target_capture_snapshot_sha256":(
            _digest(target_capture) if target_capture is not None else None
        ),
        "workstreams":work,
        "workstream_count":len(work),
        "fully_accepted_workstream_count":0,
        "known_guarded_repair_families":list(ADAPTER_SCOPE),
        "unsupported_or_unverified_scope":list(SCOPES_UNSUPPORTED),
        "source_occurrences_accounted":overall["accounted_occurrence_count"],
        "source_occurrences_total":overall["source_occurrence_count"],
        "native_mutation_authorized":False,
        "real_unity_editor_executed":False,
        "real_unreal_editor_executed":False,
        "full_phase10_2_accepted":False,
        "release_candidate_ready":False,
    }
    report["canonical_report_sha256"]=_digest(report)
    return report


def verify(report: dict[str,Any], csir: dict[str,Any],
           mapping: dict[str,Any], plan: dict[str,Any], *,
           source_capture: dict[str,Any] | None = None,
           target_capture: dict[str,Any] | None = None) -> bool:
    """Prevent a rehashed/rewritten synthetic audit from granting authority."""
    if not isinstance(report,dict):
        return False
    try:
        return report == audit(
            csir,mapping,plan,
            source_capture=source_capture,target_capture=target_capture,
        )
    except (Phase10_2AuditError,TypeError,ValueError,KeyError):
        return False
