"""AI conversion decision is auditable independently of success claims."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import studio_ai_transfer_audit as audit


def _write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


@pytest.fixture
def run(tmp_path):
    root = tmp_path / "runs"
    job_id = "a" * 32
    candidate_id = "20261118T030649Z_deadbeef"
    candidate = root / "candidates" / candidate_id
    candidate.mkdir(parents=True)
    sequence = "/Game/CutSceneAI/LS_Benchmark"
    mapping_file = candidate.with_suffix(".mapping.json")
    mapping = {
        "sequence_asset_path": sequence,
        "enable_actor_visibility_fallback": True,
        "enable_fbx_embedded_material_import": True,
        "overwrite_sequence": False,
    }
    _write(mapping_file, mapping)
    _write(candidate / "session.json", {
        "target": {
            "mapping_path": str(mapping_file),
            "mapping_sha256": hashlib.sha256(mapping_file.read_bytes()).hexdigest(),
            "sequence_asset_path": sequence,
        },
        "source": {"sha256": "source-proof"},
        "source_capture": {"sha256": "capture-proof"},
    })
    _write(candidate / "transfer-plan.json", {
        "sequence_asset_path": sequence,
        "actions": [{
            "kind": "actor_visibility",
            "source_behavior_strategy": "visual_visibility_approximation",
        }, {"kind": "camera_cut"}],
    })
    _write(candidate / "ai-conversion-decision.json", {
        "kind": "cutsceneai.studio.ai_conversion_decision",
        "schema_version": "1",
        "strategy": "visual_activation_partial",
        "model_invoked": True,
        "reason": "Eligible source ActivationTrack; visual-only partial conversion.",
        "conversion_options": {
            "enable_actor_visibility_fallback": True,
            "enable_fbx_embedded_material_import": True,
        },
    })
    project = tmp_path / "TestProject.uproject"
    project.write_text("{}", encoding="utf-8")
    job = {
        "job_id": job_id,
        "candidate_id": candidate_id,
        "candidate_dir": str(candidate),
        "status": "QUEUED",
        "generation_status": "NOT_STARTED",
        "sequence_path": sequence,
        "mapping": str(mapping_file),
        "expected_project": str(project),
        "expected_level": "/Game/AI_Test02",
        "ai_conversion_decision_sha256": hashlib.sha256(
            (candidate / "ai-conversion-decision.json").read_bytes()).hexdigest(),
    }
    _write(root / "jobs" / (job_id + ".json"), job)
    return root, candidate, job


def _update_job(root: Path, job: dict) -> None:
    _write(root / "jobs" / (job["job_id"] + ".json"), job)


def _native_receipt(candidate: Path, job: dict) -> None:
    plan = candidate / "transfer-plan.json"
    _write(candidate / ("unreal-runtime-receipt-" + job["job_id"] + ".json"), {
        "kind": "cutsceneai.unreal.best_effort_receipt",
        "status": "GENERATED_UNVERIFIED", "stage": "complete",
        "verified_project": job["expected_project"],
        "verified_level": job["expected_level"],
        "transfer_plan_sha256": hashlib.sha256(plan.read_bytes()).hexdigest(),
        "generated_sequence": job["sequence_path"] + "." + job[
            "sequence_path"].rsplit("/", 1)[-1],
    })


def _native_diagnostic(candidate: Path, job: dict) -> str:
    report_file = candidate / "CineTwin_WorldPose_Diagnosis_20261118.json"
    _write(report_file, {
        "kind": "cutsceneai.cinetwin.unreal_world_pose_diagnostic",
        "status": "DIAGNOSTIC_NOT_FIDELITY_VERIFIED",
        "target": {"project": job["expected_project"],
                   "sequence_path": job["sequence_path"] + ".LS_Benchmark"},
        "source": {"csir_sha256": "source-proof", "capture_sha256": "capture-proof",
                   "missing_source_frames": []},
        "entities": {
            "Ch31": {
                "status": "READY",
                "actor_world": {"max_absolute_error_cm": 295.4967},
                "skeletal_root_world": {"max_absolute_error_cm": 379.6814},
            },
            "Ch26": {
                "status": "READY",
                "actor_world": {"max_absolute_error_cm": 0.1},
                "skeletal_root_world": {"max_absolute_error_cm": 14.7157},
            },
        },
        "errors": [],
    })
    return str(report_file)


def test_model_plan_does_not_imply_native_execution(run):
    root, _, job = run
    output = audit.assess(root, job["job_id"])
    assert output["available"] is True
    assert output["model_decision_recorded"] is True
    assert output["strategy"] == "visual_activation_partial"
    assert output["native_visibility_actions_planned"] == 1
    assert output["status"] == "AI_PLAN_QUEUED"
    assert output["native_builder_completed"] is False
    assert output["cinetwin"]["status"] == "NOT_MEASURED"
    assert output["fidelity_verified"] is False
    assert not any("sk-" in str(value) for value in output.values())


def test_native_build_receipt_and_diagnostic_are_independent(run):
    root, candidate, job = run
    job.update({
        "status": "GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED",
        "generation_status": "GENERATED_UNVERIFIED",
        "generated_sequence": job["sequence_path"] + ".LS_Benchmark",
    })
    job["diagnostic_file"] = _native_diagnostic(candidate, job)
    _update_job(root, job)
    without = audit.assess(root, job["job_id"])
    assert without["native_builder_completed"] is False
    assert without["cinetwin"]["status"] == "NOT_MEASURED"
    _native_receipt(candidate, job)
    result = audit.assess(root, job["job_id"])
    assert result["status"] == "AI_NATIVE_GENERATED_UNVERIFIED"
    assert result["native_receipt_present"] is True
    assert result["native_builder_completed"] is True
    assert result["cinetwin"]["max_actor_error_cm"] == pytest.approx(295.4967)
    assert result["cinetwin"]["max_root_error_cm"] == pytest.approx(379.6814)
    assert result["cinetwin"]["position_tolerance_cm"] == 2.0
    assert result["fidelity_verified"] is False


def test_tampered_ai_decision_is_rejected_even_when_native_generated(run):
    root, candidate, job = run
    file = candidate / "ai-conversion-decision.json"
    changed = json.loads(file.read_text())
    changed["strategy"] = "native_source"
    _write(file, changed)
    with pytest.raises(audit.AITransferAuditError, match="bytes differ"):
        audit.assess(root, job["job_id"])


def test_wrong_candidate_cannot_read_external_receipt(run, tmp_path):
    root, _, job = run
    job["candidate_dir"] = str(tmp_path)
    _update_job(root, job)
    with pytest.raises(audit.AITransferAuditError, match="escapes"):
        audit.assess(root, job["job_id"])


def test_ineligible_ai_visibility_has_no_native_plan_action(run):
    root, candidate, job = run
    _write(candidate / "transfer-plan.json", {
        "sequence_asset_path": job["sequence_path"],
        "actions": [{"kind": "camera_cut"}],
    })
    with pytest.raises(audit.AITransferAuditError, match="no native action"):
        audit.assess(root, job["job_id"])


def test_early_builder_failure_is_not_a_generated_cutscene(run):
    root, candidate, job = run
    job.update({"status": "BLOCKED_OR_FAILED", "generation_status": "NOT_STARTED"})
    _update_job(root, job)
    _write(candidate / ("unreal-runtime-receipt-" + job["job_id"] + ".json"), {
        "kind": "cutsceneai.unreal.best_effort_receipt",
        "status": "BLOCKED", "stage": "source_verification",
        "scene_modified": False,
    })
    out = audit.assess(root, job["job_id"])
    assert out["status"] == "AI_NATIVE_BLOCKED"
    assert out["native_receipt_present"] is True
    assert out["native_builder_completed"] is False


def test_rejects_different_unreal_project_diagnostic(run, tmp_path):
    root, candidate, job = run
    job.update({
        "status": "GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED",
        "generation_status": "GENERATED_UNVERIFIED",
        "generated_sequence": job["sequence_path"] + ".LS_Benchmark",
    })
    job["diagnostic_file"] = _native_diagnostic(candidate, job)
    report_file = Path(job["diagnostic_file"])
    other = json.loads(report_file.read_text())
    other["target"]["project"] = str(tmp_path / "OtherProject.uproject")
    _write(report_file, other)
    _update_job(root, job)
    _native_receipt(candidate, job)
    with pytest.raises(audit.AITransferAuditError, match="different Unreal project"):
        audit.assess(root, job["job_id"])


def test_unrelated_deterministic_transfer_returns_not_ai(run):
    root, _, job = run
    job["ai_conversion_decision_sha256"] = ""
    _update_job(root, job)
    out = audit.assess(root, job["job_id"])
    assert out["available"] is False
    assert out["status"] == "NO_AI_CONVERSION_DECISION"


def _animation_setup(root: Path, candidate: Path, job: dict) -> dict:
    """Fabricate immutable *mock* evidence, not a real engine acceptance."""
    report = {
        "kind": "cutsceneai.studio.character_compatibility_report",
        "schema_version": "1",
        "character_count": 1,
        "characters": [{
            "id": "character-01",
            "source_entity_id": "source-ch",
            "status": "COMPATIBLE_AFTER_APPROVED_RETARGET",
        }],
    }
    report_file = candidate / "character-compatibility.json"
    _write(report_file, report)
    canonical = hashlib.sha256(json.dumps(
        report, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()
    animation = {
        "kind": "cutsceneai.studio.ai_animation_conversion_decision",
        "choice_id": "character-01",
        "action_id": "use_approved_ik_retarget_profile",
        "source_entity_id": "source-ch",
        "compatibility_report_sha256": canonical,
    }
    decision_file = candidate / "ai-conversion-decision.json"
    decision = json.loads(decision_file.read_text())
    decision["character_compatibility_sha256"] = canonical
    decision["animation_conversion"] = animation
    _write(decision_file, decision)
    mapping_path = Path(job["mapping"])
    mapping = json.loads(mapping_path.read_text())
    mapping["ai_character_animation"] = animation
    _write(mapping_path, mapping)
    plan_path = candidate / "transfer-plan.json"
    plan = json.loads(plan_path.read_text())
    plan["ai_character_animation"] = animation
    _write(plan_path, plan)
    session_file = candidate / "session.json"
    session = json.loads(session_file.read_text())
    session["target"]["mapping_sha256"] = hashlib.sha256(
        mapping_path.read_bytes()).hexdigest()
    _write(session_file, session)
    job["character_compatibility_sha256"] = hashlib.sha256(
        report_file.read_bytes()).hexdigest()
    job["ai_conversion_decision_sha256"] = hashlib.sha256(
        decision_file.read_bytes()).hexdigest()
    _update_job(root, job)
    return animation


def _animation_readback(candidate: Path, job: dict, *, status="PASS") -> None:
    _write(candidate / "character-native-execution.json", {
        "kind": "cutsceneai.studio.character_native_readback",
        "schema_version": "1",
        "status": status,
        "job_id": job["job_id"],
        "sequence_path": job["sequence_path"],
        "source_entity_id": "source-ch",
        "decision_file_sha256": job["ai_conversion_decision_sha256"],
        "compatibility_file_sha256": job["character_compatibility_sha256"],
        "skeleton": {"status": "PASS"},
        "duration_match": True,
        "observed_sections": [{"clip": "/Game/NewClip"}],
        "expected_sections": [{"clip": "/Game/NewClip"}],
        "fidelity_verified": False,
    })


def test_friday_approved_retarget_requires_native_receipt(run):
    root, candidate, job = run
    _animation_setup(root, candidate, job)
    planned = audit.assess(root, job["job_id"])
    assert planned["character_conversion"]["selected"] is True
    assert planned["character_conversion"]["native_readback_status"] == "NOT_EXECUTED"
    assert not planned["character_conversion"]["native_readback_passed"]
    assert planned["character_conversion"]["character_count"] == 1
    assert planned["character_conversion"]["compatibility_outcomes"] == {
        "COMPATIBLE_AFTER_APPROVED_RETARGET": 1
    }
    _animation_readback(candidate, job)
    orphan = audit.assess(root, job["job_id"])
    assert orphan["character_conversion"]["native_readback_status"] == "UNCONFIRMED_PASS"
    assert not orphan["character_conversion"]["native_readback_passed"]


def test_friday_native_readback_requires_both_job_and_builder_confirmation(run):
    root, candidate, job = run
    _animation_setup(root, candidate, job)
    job.update({
        "status": "GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED",
        "generation_status": "GENERATED_UNVERIFIED",
        "generated_sequence": job["sequence_path"] + ".LS_Benchmark",
        "character_native_readback_status": "PASS",
    })
    _update_job(root, job)
    _animation_readback(candidate, job)
    # A claim in a readback file does not replace a verified Unreal receipt.
    assert not audit.assess(root, job["job_id"])[
        "character_conversion"]["native_readback_passed"]
    _native_receipt(candidate, job)
    output = audit.assess(root, job["job_id"])
    assert output["character_conversion"]["native_readback_status"] == "PASS"
    assert output["character_conversion"]["native_readback_passed"] is True
    assert output["native_builder_completed"] is True
    assert output["fidelity_verified"] is False


def test_friday_tampered_retarget_and_wrong_native_job_are_blocked(run):
    root, candidate, job = run
    _animation_setup(root, candidate, job)
    plan = json.loads((candidate / "transfer-plan.json").read_text())
    plan["ai_character_animation"]["choice_id"] = "character-02"
    _write(candidate / "transfer-plan.json", plan)
    with pytest.raises(audit.AITransferAuditError, match="animation plan"):
        audit.assess(root, job["job_id"])
    plan["ai_character_animation"]["choice_id"] = "character-01"
    _write(candidate / "transfer-plan.json", plan)
    _animation_readback(candidate, job)
    report_file = candidate / "character-native-execution.json"
    native = json.loads(report_file.read_text())
    native["job_id"] = "f" * 32
    _write(report_file, native)
    with pytest.raises(audit.AITransferAuditError, match="Native IK retarget readback"):
        audit.assess(root, job["job_id"])


def test_friday_failed_readback_cannot_be_reported_as_success(run):
    root, candidate, job = run
    _animation_setup(root, candidate, job)
    _animation_readback(candidate, job, status="FAIL")
    job["character_native_readback_status"] = "FAIL"
    _update_job(root, job)
    out = audit.assess(root, job["job_id"])["character_conversion"]
    assert out["native_readback_status"] == "FAIL"
    assert out["native_readback_passed"] is False


def test_friday_incompatible_source_report_is_rejected_before_display(run):
    root, candidate, job = run
    _animation_setup(root, candidate, job)
    path = candidate / "character-compatibility.json"
    changed = json.loads(path.read_text())
    changed["characters"][0]["status"] = "INCOMPATIBLE"
    _write(path, changed)
    with pytest.raises(audit.AITransferAuditError, match="job-bound source evidence"):
        audit.assess(root, job["job_id"])
