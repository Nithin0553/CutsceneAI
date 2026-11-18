"""Release gate must never declare parity from a model or mocked native receipt."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import studio_release_gate as gate
from test_studio_ai_transfer_audit import (
    _native_receipt, _update_job, _write, run as mock_transfer,
)


def test_ai_plan_alone_is_not_release_ready(mock_transfer):
    root, _candidate, job = mock_transfer
    output = gate.assess(root, job["job_id"])
    assert output["status"] == "ENGINE_ACCEPTANCE_PENDING"
    assert output["model_decision_recorded"]
    assert not output["native_builder_completed"]
    assert not output["release_ready"]
    assert not output["fidelity_verified"]
    assert any("Native Unreal" in message for message in output["incomplete"])


def test_generated_unverified_is_not_reopened_parity(mock_transfer):
    root, candidate, job = mock_transfer
    job.update({
        "generation_status": "GENERATED_UNVERIFIED",
        "status": "GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED",
        "generated_sequence": job["sequence_path"] + ".LS_Benchmark",
    })
    _update_job(root, job)
    _native_receipt(candidate, job)
    output = gate.assess(root, job["job_id"])
    assert output["native_builder_completed"]
    assert not output["automated_native_scope_passed"]
    assert output["native_measurement"]["status"] == (
        "REOPENED_EDITOR_ACCEPTANCE_NOT_RECORDED"
    )
    assert output["release_ready"] is False


def _reopened_evidence(candidate, job, root):
    folder = candidate / "native-acceptance-mock"
    capture = root / "source-capture.json"
    capture.write_text('{"source":"unity"}')
    job["capture"] = str(capture)
    job["generation_editor_pid"] = 100
    native = {
        "kind": "cutsceneai.studio.persistence_audit",
        "status": "STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS",
        "restart_verified": True,
        "native_structure_status": "PASS",
        "provenance_status": "COMPLETE",
        "expected_project": job["expected_project"],
        "expected_level": job["expected_level"],
    }
    _write(folder / "persistence.json", native)
    _write(folder / "target-behavior.json", {"kind": "target-observation"})
    _write(folder / "sampling-plan.json", {"kind": "sampling-plan"})
    compare = {
        "job_id": job["job_id"],
        "acceptance_status": "STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE",
        "native_persistence_status": native["status"],
        "generation_editor_pid": 100, "observation_editor_pid": 101,
        "persistence_sha256": hashlib.sha256(
            (folder / "persistence.json").read_bytes()).hexdigest(),
        "target_observation_sha256": hashlib.sha256(
            (folder / "target-behavior.json").read_bytes()).hexdigest(),
        "sampling_plan_sha256": hashlib.sha256(
            (folder / "sampling-plan.json").read_bytes()).hexdigest(),
        "source_capture_sha256": hashlib.sha256(capture.read_bytes()).hexdigest(),
    }
    _write(folder / "comparison.json", compare)
    return folder


def test_even_reopened_measured_motion_is_not_full_cinematic_release(mock_transfer):
    root, candidate, job = mock_transfer
    job.update({
        "generation_status": "GENERATED_UNVERIFIED",
        "status": "GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED",
        "generated_sequence": job["sequence_path"] + ".LS_Benchmark",
    })
    folder = _reopened_evidence(candidate, job, root)
    _update_job(root, job)
    _native_receipt(candidate, job)
    output = gate.assess(root, job["job_id"])
    assert output["automated_native_scope_passed"]
    assert output["status"] == "MEASURED_SCOPE_READY_HUMAN_REVIEW_REQUIRED"
    assert not output["release_ready"]
    assert not output["fidelity_verified"]
    assert len(output["incomplete"]) >= 3
    compare = gate._read(folder / "comparison.json")
    compare["observation_editor_pid"] = job["generation_editor_pid"]
    _write(folder / "comparison.json", compare)
    assert not gate.assess(root, job["job_id"])["automated_native_scope_passed"]


def test_mismatched_reopened_source_capture_refuses_release_evidence(mock_transfer):
    root, candidate, job = mock_transfer
    job.update({
        "generation_status": "GENERATED_UNVERIFIED",
        "status": "GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED",
        "generated_sequence": job["sequence_path"] + ".LS_Benchmark",
    })
    folder = _reopened_evidence(candidate, job, root)
    _update_job(root, job)
    _native_receipt(candidate, job)
    compare = gate._read(folder / "comparison.json")
    compare["source_capture_sha256"] = "b" * 64
    _write(folder / "comparison.json", compare)
    with pytest.raises(ValueError, match="does not belong to this job"):
        gate.assess(root, job["job_id"])


def test_cannot_read_arbitrary_job_or_outside_workspace(mock_transfer, tmp_path):
    root, _candidate, job = mock_transfer
    with pytest.raises(ValueError, match="Invalid release job"):
        gate.assess(root, "../../outside")
    job["candidate_dir"] = str(tmp_path / "different")
    _update_job(root, job)
    with pytest.raises(ValueError, match="escapes"):
        gate.assess(root, job["job_id"])
