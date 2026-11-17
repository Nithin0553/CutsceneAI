"""Unverified transfer outcomes never become positive training labels."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from studio_continual_learning import (  # noqa: E402
    LearningLedgerError,
    record_terminal,
    report,
)


@pytest.fixture
def run(tmp_path):
    work = tmp_path / "run"
    candidate = work / "candidates" / "one"
    candidate.mkdir(parents=True)
    csir = tmp_path / "source.csir.json"
    csir.write_text('{"source":{"engine":"unity","project_fingerprint":"A"},"tracks":[]}')
    mapping = tmp_path / "mapping.json"
    mapping.write_text('{"entities":{}}')
    job = {"job_id": "a" * 32, "candidate_id": "one",
           "candidate_dir": str(candidate), "csir": str(csir),
           "mapping": str(mapping), "status": "GENERATED_DIAGNOSTIC_INCOMPLETE",
           "generation_status": "GENERATED_UNVERIFIED"}
    return work, job


def test_terminal_record_is_immutable_and_unverified(run):
    work, job = run
    result = record_terminal(work, job)
    assert result["recorded"]
    path = work / "learning" / "trials" / (job["job_id"] + ".json")
    saved = json.loads(path.read_text())
    assert saved["fidelity_verified"] is False
    assert saved["eligible_for_training"] is False
    assert "source.csir.json" not in path.read_text()
    before = path.read_bytes()
    assert record_terminal(work, job)["recorded"]
    assert path.read_bytes() == before
    assert report(work)["completed_trials_recorded"] == 1
    assert report(work)["verified_mapping_cases"] == 0


def test_pending_job_is_not_learned(run):
    work, job = run
    job["status"] = "RUNNING"
    assert record_terminal(work, job)["recorded"] is False
    assert not (work / "learning").exists()


def test_cross_workspace_candidate_is_rejected(run, tmp_path):
    work, job = run
    job["candidate_dir"] = str(tmp_path)
    with pytest.raises(LearningLedgerError, match="candidate"):
        record_terminal(work, job)


def test_bad_job_identity_is_rejected(run):
    work, job = run
    job["job_id"] = "../other-job"
    with pytest.raises(LearningLedgerError, match="identity"):
        record_terminal(work, job)


def test_report_defaults_to_no_verified_cases(run):
    work, job = run
    info = report(work)
    assert info["proposal_only"] is True
    assert info["model_weights_updated"] is False
    assert info["suggestions"] == []
