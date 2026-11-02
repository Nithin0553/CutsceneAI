"""Release gating tests: generated != verified; evidence belongs to one job."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "studio"))
import studio_release_gate as gate


def put(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def fixture(tmp_path):
    workspace = tmp_path / "runs"
    candidate_id = "candidate0001"
    job_id = "a" * 32
    candidate = workspace / "candidates" / candidate_id
    csir = tmp_path / "source.csir.json"
    put(csir, {"kind": "cutsceneai.csir", "source": {"engine": "unity"}})
    put(candidate / "transfer-plan.json",
        {"sequence_asset_path": "/Game/CutSceneAI/LS_Stage"})
    job = {
        "kind": "cutsceneai.studio.local_unreal_job",
        "job_id": job_id,
        "candidate_id": candidate_id, "candidate_dir": str(candidate),
        "status": "GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED",
        "generation_status": "GENERATED_UNVERIFIED",
        "generated_sequence": "/Game/CutSceneAI/LS_Stage",
        "sequence_path": "/Game/CutSceneAI/LS_Stage",
        "csir": str(csir),
    }
    put(workspace / "jobs" / (job_id + ".json"), job)
    return workspace, candidate, job


def test_generated_sequence_alone_never_release_ready(tmp_path):
    workspace, _candidate, job = fixture(tmp_path)
    result = gate.assess(workspace, job["job_id"])
    assert result["release_ready"] is False
    assert result["status"] == "INCOMPLETE"
    assert result["checks"]["native_generation"]["status"] == "PASS"
    assert result["checks"]["source_and_plan"]["status"] == "PASS"
    assert "independent_editor_restart" in result["incomplete"]
    assert "rendered_frame_parity" in result["incomplete"]
    assert "learned_policy_generalization" in result["incomplete"]
    assert "heldout_project_validation" in result["incomplete"]
    assert not result["fidelity_verified"]
    assert len(result["checks"]) >= 10


def test_real_native_failed_audit_blocks_release(tmp_path):
    workspace, candidate, job = fixture(tmp_path)
    put(candidate / ("visual-audit-" + job["job_id"] + "-deadbeef.json"), {
        "kind": "cutsceneai.studio.visual_readback_audit",
        "job_id": job["job_id"], "candidate_id": job["candidate_id"],
        "status": "VISUAL_COMPLETENESS_REVIEW_REQUIRED",
        "visual_issues": ["RENDER_MATERIALS_MISSING_OR_ENGINE_DEFAULT"],
        "character_material_slots_engine_default": 4,
    })
    result = gate.assess(workspace, job["job_id"])
    assert result["status"] == "BLOCKED"
    assert "native_visual_prerequisites" in result["failed"]
    assert result["checks"]["native_visual_prerequisites"]["character_default_slots"] == 4


def test_foreign_job_evidence_rejected_not_trusted(tmp_path):
    workspace, candidate, job = fixture(tmp_path)
    put(candidate / ("visual-audit-" + job["job_id"] + "-deadbeef.json"), {
        "kind": "cutsceneai.studio.visual_readback_audit",
        "job_id": "b" * 32,
        "candidate_id": job["candidate_id"], "visual_issues": [],
    })
    with pytest.raises(gate.ReleaseEvidenceError, match="another job_id"):
        gate.assess(workspace, job["job_id"])


def test_untrusted_candidate_path_blocked(tmp_path):
    workspace, _candidate, job = fixture(tmp_path)
    job["candidate_dir"] = str(tmp_path)
    put(workspace / "jobs" / (job["job_id"] + ".json"), job)
    with pytest.raises(gate.ReleaseEvidenceError, match="Candidate path"):
        gate.assess(workspace, job["job_id"])


def test_bad_plan_sequence_identity_fails(tmp_path):
    workspace, candidate, job = fixture(tmp_path)
    put(candidate / "transfer-plan.json",
        {"sequence_asset_path": "/Game/Other/LS_Spoofed"})
    result = gate.assess(workspace, job["job_id"])
    assert result["status"] == "BLOCKED"
    assert "source_and_plan" in result["failed"]


def test_same_session_persistence_audit_is_not_reopen_proof(tmp_path):
    workspace, candidate, job = fixture(tmp_path)
    put(candidate / ("post-reopen-audit-" + job["job_id"] + ".json"), {
        "kind": "cutsceneai.studio.persistence_audit",
        "status": "STRUCTURAL_READBACK_PASS_RESTART_UNVERIFIED",
        "native_structure_status": "PASS",
        "sequence_persisted": True,
        "provenance_status": "COMPLETE",
        "restart_verified": False,
        "assets_class_and_disk_verified": 18,
        "asset_count": 18,
    })
    result = gate.assess(workspace, job["job_id"])
    assert result["checks"]["native_structure_and_save"]["status"] == "PASS"
    assert result["checks"]["independent_editor_restart"]["status"] == "INCOMPLETE"
    assert result["release_ready"] is False


def test_measured_motion_mismatch_blocks_release(tmp_path):
    workspace, candidate, job = fixture(tmp_path)
    put(candidate / ("closed-loop-evaluation-" + job["job_id"] + ".json"), {
        "kind": "cutsceneai.studio.closed_loop_evaluation",
        "issues": [{"category": "CED_ANIMATION_TRANSFORM_FIDELITY",
                    "error_cm": 280.7}],
        "cinetwin_measured": True,
    })
    result = gate.assess(workspace, job["job_id"])
    assert result["checks"]["cinetwin_measured_behavior"]["status"] == "FAIL"
    assert "cinetwin_measured_behavior" in result["failed"]


def test_unexpected_kind_is_not_silently_audit_pass(tmp_path):
    workspace, candidate, job = fixture(tmp_path)
    put(candidate / ("hierarchy-audit-" + job["job_id"] + "-deadbeef.json"), {
        "kind": "different.validation.audit", "status": "PASS",
    })
    with pytest.raises(gate.ReleaseEvidenceError, match="Unexpected"):
        gate.assess(workspace, job["job_id"])
