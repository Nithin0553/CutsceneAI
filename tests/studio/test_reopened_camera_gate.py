"""Independent release-gate source/native camera evidence verification."""
from __future__ import annotations

import math
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in ("packages/studio", "packages/cinetwin", "tests/studio", "tests/cinetwin"):
    sys.path.insert(0, str(ROOT / folder))

import studio_release_gate as gate
from behavior_compare import compare
from camera_optics import NATIVE_BASIS
from test_behavior_compare import _fixtures
from test_release_gate import fixture, put


def _reopened(tmp_path):
    work, candidate, job = fixture(tmp_path)
    plan, source, target = _fixtures()
    plan["camera_cuts"] = [{
        "source_entity_id": "camera", "source_section_id": "shot-1",
        "start_frame": 0, "end_frame": 4,
        "start_seconds": 0, "end_seconds": 1, "status": "FRAME_ALIGNED",
    }]
    target["camera_cut_sections"] = {
        "status": "OBSERVED",
        "binding_provenance": "NATIVE_SEQUENCE_CAMERA_BINDING_ID",
        "sections": [{"actor_label": "CameraUnreal", "start_frame": 0, "end_frame": 4}],
    }
    for frame in target["samples"]:
        next(x for x in frame["entities"] if x["entity_id"] == "camera")["camera"] = {
            "status": "OBSERVED", "lens_basis": NATIVE_BASIS,
            "sensor_height_mm": 100 * math.tan(math.radians(20)),
            "focal_length_mm": 50.0, "vertical_fov_degrees": 40.0,
        }
    capture = tmp_path / "source.capture.json"
    put(capture, source)
    job.update(
        generation_editor_pid=101, expected_project=str(tmp_path / "Unreal/Staging.uproject"),
        expected_level="/Game/Stage/L_Test", capture=str(capture),
    )
    put(work / "jobs" / (job["job_id"] + ".json"), job)
    evidence = candidate / "native-acceptance-genuine-layout"
    persistence = evidence / "persistence.json"
    observation = evidence / "target-behavior.json"
    sampling = evidence / "sampling-plan.json"
    put(persistence, {
        "kind": "cutsceneai.studio.persistence_audit",
        "expected_project": job["expected_project"],
        "expected_level": job["expected_level"],
        "status": "STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS",
        "restart_verified": True,
        "native_structure_status": "PASS",
        "provenance_status": "COMPLETE",
    })
    put(observation, target)
    put(sampling, plan)
    comparison = {
        **compare(plan, source, target),
        "job_id": job["job_id"],
        "generation_editor_pid": 101, "observation_editor_pid": 202,
        "acceptance_status": "INCOMPLETE_MEASURED_SCOPE",
        "persistence_sha256": gate._sha(persistence),
        "target_observation_sha256": gate._sha(observation),
        "sampling_plan_sha256": gate._sha(sampling),
        "source_capture_sha256": gate._sha(capture),
    }
    put(evidence / "comparison.json", comparison)
    return work, job, evidence, comparison, target


def test_reopened_native_camera_domains_are_recomputed_and_scoped(tmp_path):
    work, job, _folder, _comparison, _target = _reopened(tmp_path)
    result = gate.assess(work, job["job_id"])
    assert result["checks"]["reopened_camera_optics"]["status"] == "PASS"
    assert result["checks"]["reopened_camera_cut_timing"]["status"] == "PASS"
    assert result["checks"]["reopened_temporal_acceptance"]["status"] == "INCOMPLETE"
    assert result["checks"]["rendered_frame_parity"]["status"] == "INCOMPLETE"
    assert result["release_ready"] is False
    assert result["fidelity_verified"] is False


def test_tampered_camera_lens_pass_claim_is_rejected_from_original_samples(tmp_path):
    work, job, folder, comparison, _target = _reopened(tmp_path)
    comparison["camera_optics"]["per_camera"][0]["max_vertical_fov_error_degrees"] = 0.1
    put(folder / "comparison.json", comparison)
    with pytest.raises(gate.ReleaseEvidenceError, match="differs from measured native evidence"):
        gate.assess(work, job["job_id"])


def test_tampered_cut_section_pass_claim_is_rejected(tmp_path):
    work, job, folder, comparison, _target = _reopened(tmp_path)
    comparison["camera_cut_timing"]["matched_sections"] = 2
    put(folder / "comparison.json", comparison)
    with pytest.raises(gate.ReleaseEvidenceError, match="differs from measured native evidence"):
        gate.assess(work, job["job_id"])


def test_bad_native_lens_cannot_be_hidden_by_rehashed_observation(tmp_path):
    work, job, folder, comparison, target = _reopened(tmp_path)
    camera = next(x for x in target["samples"][1]["entities"] if x["entity_id"] == "camera")
    camera["camera"]["vertical_fov_degrees"] = 52.0
    put(folder / "target-behavior.json", target)
    comparison["target_observation_sha256"] = gate._sha(folder / "target-behavior.json")
    put(folder / "comparison.json", comparison)
    with pytest.raises(gate.ReleaseEvidenceError, match="recomputed"):
        gate.assess(work, job["job_id"])


def test_forged_full_acceptance_rejects_actual_camera_section_difference(tmp_path):
    work, job, folder, comparison, target = _reopened(tmp_path)
    target["camera_cut_sections"]["sections"][0]["end_frame"] = 3
    put(folder / "target-behavior.json", target)
    comparison["target_observation_sha256"] = gate._sha(folder / "target-behavior.json")
    comparison["acceptance_status"] = "STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE"
    put(folder / "comparison.json", comparison)
    with pytest.raises(gate.ReleaseEvidenceError, match="claimed success"):
        gate.assess(work, job["job_id"])
