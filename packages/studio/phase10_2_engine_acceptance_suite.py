"""Phase 10.2 native seven-area acceptance bundle and held-out provenance.

This verifies a human-supervised workstation acceptance *evidence package*,
not its truth or real editor execution. Real Unity and Unreal logs, native
reopened assets, frame renders, audio traces and reviewer sign-off are
required separately. Synthetic tests always stay review-only.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import engine_acceptance_matrix
from phase10_2_consolidated_audit import WORK_AREAS


KIND="cutsceneai.studio.phase10_2.engine_acceptance_bundle"
VERSION="1"
_HEX=re.compile(r"[a-f0-9]{64}")


class Phase10_2EngineAcceptanceError(ValueError):
    pass


REQUIREMENTS={
    "animated_camera":("unreal_camera_curve_readback", "source_native_camera_frames",
                       "rendered_camera_comparison"),
    "timeline":("unreal_shot_sections", "native_timewarped_blend_readback",
                "rendered_camera_transition_comparison"),
    "moving_character":("native_root_actor_pose", "native_facing",
                        "reopened_root_world_cinetwin"),
    "skeletal":("native_retarget_pose", "native_reference_bone_calibration",
                "skinned_mesh_deformation_comparison"),
    "multi_character":("native_attachment_hierarchy", "native_character_timeline",
                       "rendered_interaction_comparison"),
    "effects":("native_lighting_material_shader_vfx", "native_audio_events_physics",
               "cross_engine_effect_measurements"),
    "contracts":("unity_export_logs", "unreal_reopen_logs", "heldout_project_comparison"),
}


def _sha(path:Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda:fh.read(1024*1024),b""):
            digest.update(block)
    return digest.hexdigest()


def evaluate(bundle:dict[str,Any], workspace:str|Path) -> dict[str,Any]:
    """Never promote source-only CI or generated receipt to real-engine parity."""
    if (not isinstance(bundle,dict) or bundle.get("kind")!=KIND
            or bundle.get("schema_version")!=VERSION
            or not isinstance(bundle.get("workstreams"),list)
            or len(bundle["workstreams"])!=len(WORK_AREAS)):
        raise Phase10_2EngineAcceptanceError(
            "The native acceptance bundle must enumerate all seven work areas."
        )
    root=Path(workspace).resolve()
    if not root.is_dir():
        raise Phase10_2EngineAcceptanceError("Native acceptance workspace missing.")
    names=[row.get("work_area_id") for row in bundle["workstreams"]
           if isinstance(row,dict)]
    if len(names)!=7 or names!=list(REQUIREMENTS):
        raise Phase10_2EngineAcceptanceError(
            "Native acceptance areas must be complete and in original order."
        )
    # The existing six-scenario engine acceptance matrix independently
    # checks exact source frames, two editor PIDs and the held-out source.
    matrix=bundle.get("baseline_engine_acceptance_matrix")
    if not isinstance(matrix,dict):
        raise Phase10_2EngineAcceptanceError(
            "Original six-scenario native acceptance matrix missing."
        )
    try:
        baseline=engine_acceptance_matrix.evaluate(matrix,root)
    except engine_acceptance_matrix.MatrixError as exc:
        raise Phase10_2EngineAcceptanceError(
            "Baseline native/reopened/held-out acceptance evidence incomplete."
        ) from exc
    reports=[]
    for row in bundle["workstreams"]:
        area=row["work_area_id"]
        files=row.get("native_evidence")
        if not isinstance(files,dict) or set(files)!=set(REQUIREMENTS[area]):
            raise Phase10_2EngineAcceptanceError(
                "Every required native behavior evidence artifact must be accounted for: "+area
            )
        items=[]
        for requirement in REQUIREMENTS[area]:
            entry=files[requirement]
            if not isinstance(entry,dict):
                raise Phase10_2EngineAcceptanceError("Malformed evidence location: "+requirement)
            relative=entry.get("path")
            expected=entry.get("sha256")
            if (not isinstance(relative,str) or not relative
                    or Path(relative).is_absolute()
                    or ".." in Path(relative).parts
                    or not isinstance(expected,str) or not _HEX.fullmatch(expected)):
                raise Phase10_2EngineAcceptanceError(
                    "Every acceptance evidence path/hash must be exact and safe."
                )
            file=root/relative
            if (file.is_symlink() or any(p.is_symlink() for p in file.parents)
                    or not file.is_file()
                    or not file.resolve().is_relative_to(root)
                    or not 0<file.stat().st_size<64*1024*1024
                    or _sha(file)!=expected):
                raise Phase10_2EngineAcceptanceError(
                    "Native evidence file absent, stale, linked or outside workspace: "+requirement
                )
            items.append({"requirement":requirement,
                          "evidence_sha256":expected,
                          "inspection_status":"FILE_HASH_RECORDED_HUMAN_REVIEW_PENDING"})
        reports.append({
            "work_area_id":area,
            "required_proof_count":len(items),
            "native_evidence":items,
            "independently_verified_engine_parity":False,
        })
    # Even a complete bundle can be synthetically assembled, so it is NEVER
    # itself authorization to claim fully automated cross-engine success.
    return {
        "kind":"cutsceneai.studio.phase10_2.engine_acceptance_review",
        "schema_version":"1",
        "status":"ALL_EVIDENCE_HASHES_PRESENT_INDEPENDENT_ENGINE_REVIEW_REQUIRED",
        "baseline_status":baseline["status"],
        "workstream_count":len(reports),
        "workstreams":reports,
        "acceptance_complete":False,
        "real_editor_execution_attested_by_this_tool":False,
        "native_engine_fidelity_proven":False,
        "missing_human_verification":[
            "Match Unity/Unreal process logs and source project fingerprints to original uploads.",
            "Rerun generated sequences after Unreal Editor close and reopen.",
            "Compare camera frames, full skeletal mesh deformation, audio, VFX, event/physics state.",
            "Review held-out scene that shares no copied acceptance/learning source assets.",
        ],
    }
