"""Automatic private learning is diagnostic until native measurement and human review."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "packages" / "studio"))

import studio_continual_learning as learning
import studio_local_bridge
import studio_release_gate


@pytest.fixture
def native_workspace(tmp_path):
    workspace = tmp_path / "studio"
    candidate = workspace / "candidates" / "candidate_demo"
    candidate.mkdir(parents=True)
    (workspace / "jobs").mkdir()
    source = tmp_path / "source.csir.json"
    source.write_text('{"source":{"engine":"unity","project_fingerprint":"private"},"tracks":[]}')
    mapping = tmp_path / "mapping.json"
    mapping.write_text('{"entities":{}}')
    job = {
        "job_id": "f" * 32, "candidate_id": "candidate_demo",
        "candidate_dir": str(candidate), "csir": str(source),
        "mapping": str(mapping), "status": "GENERATED_DIAGNOSTIC_INCOMPLETE",
        "generation_status": "GENERATED_UNVERIFIED",
        "kind": "cutsceneai.studio.local_unreal_job",
    }
    (workspace / "jobs" / (job["job_id"] + ".json")).write_text(json.dumps(job))
    return workspace, candidate, job


def test_job_status_automatically_records_private_unverified_trial(native_workspace):
    workspace, candidate, job = native_workspace
    result = studio_local_bridge.job_status(job["job_id"], workspace)
    assert result["status"] == "GENERATED_DIAGNOSTIC_INCOMPLETE"
    assert result["private_learning_trial"] == "RECORDED"
    assert result["private_native_measurement"] == "NO_INDEPENDENT_NATIVE_COMPARISON"
    stored = workspace / "learning" / "trials" / (job["job_id"] + ".json")
    assert stored.is_file()
    record = json.loads(stored.read_text())
    assert record["eligible_for_training"] is False
    assert record["fidelity_verified"] is False
    assert "private" not in stored.read_text()
    assert learning.report(workspace)["independent_measurement_records"] == 0
    assert studio_local_bridge.job_status(job["job_id"], workspace)[
        "private_learning_trial"] == "RECORDED"


def test_failure_is_preserved_without_raw_paths(native_workspace):
    workspace, _candidate, job = native_workspace
    job["status"] = "FAILED"
    job["failure_stage"] = "unknown/secret/path"
    job["error"] = "Client secret path C:/Private/Scene.unity could not import"
    path = workspace / "jobs" / (job["job_id"] + ".json")
    path.write_text(json.dumps(job))
    result = studio_local_bridge.job_status(job["job_id"], workspace)
    assert result["status"] == "FAILED"
    recorded = (workspace / "learning" / "trials" /
                (job["job_id"] + ".json")).read_text()
    assert "Client secret" not in recorded
    assert "C:/Private/" not in recorded
    row = json.loads(recorded)
    assert row["native_failure_category"] == "FAILED_NATIVE_STEP"
    assert row["failure_stage_class"] == "UNKNOWN"
    assert learning.report(workspace)["recorded_native_failures"] == 1


def test_independent_measured_outcome_is_not_miscredited_to_mapping(
        native_workspace, monkeypatch):
    workspace, candidate, job = native_workspace
    source_bound = candidate / "native-acceptance-heldout"
    source_bound.mkdir()
    (source_bound / "comparison.json").write_text(json.dumps({
        "kind": "cinetwin.behavior_comparison",
        "job_id": job["job_id"], "acceptance_status": "TEST_FIXTURE_ONLY",
    }))
    observed = []
    def verify(root, job_id):
        observed.append((root, job_id))
        # This mocked gate is strictly a test fixture; real runtime requires
        # the actual release assessor's source/readback/hash checks.
        return {"checks": {
            "source_and_plan": {"status": "PASS"},
            "reopened_temporal_acceptance": {"status": "PASS"},
        }}
    monkeypatch.setattr(studio_release_gate, "assess", verify)
    outcome = learning.record_measured_outcome(workspace, job)
    assert outcome["status"] == "PRIVATE_MEASUREMENT_RECORDED"
    assert outcome["eligible_for_training"] is False
    files = list((workspace / "learning" / "measured-outcomes").glob("*.json"))
    assert len(files) == 1
    evidence = json.loads(files[0].read_text())
    assert evidence["measured_reopened_status"] == "PASS"
    assert evidence["per_rule_success_attributed"] is False
    assert evidence["full_fidelity_verified"] is False
    assert learning.record_measured_outcome(workspace, job) == outcome
    assert len(list((workspace / "learning" / "measured-outcomes")
                    .glob("*.json"))) == 1
    assert observed == [(workspace.resolve(), job["job_id"])] * 2


def test_pending_native_jobs_are_not_learning_events(native_workspace):
    workspace, _candidate, job = native_workspace
    job["status"] = "RUNNING"
    (workspace / "jobs" / (job["job_id"] + ".json")).write_text(json.dumps(job))
    result = studio_local_bridge.job_status(job["job_id"], workspace)
    assert "private_learning_trial" not in result
    assert not (workspace / "learning").exists()
