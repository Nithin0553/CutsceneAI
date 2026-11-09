"""Generation-time audits must be independent, source-bound and never imply restart."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "integrations" / "unreal"))
import studio_generation_readback as readback


def _fixture(tmp_path):
    workspace = tmp_path / "runs"
    job_id = "a" * 32
    candidate_id = "candidate1234"
    candidate = workspace / "candidates" / candidate_id
    candidate.mkdir(parents=True)
    job = {
        "kind": "cutsceneai.studio.local_unreal_job", "job_id": job_id,
        "candidate_id": candidate_id, "candidate_dir": str(candidate),
        "sequence_path": "/Game/Test/LS_One",
        "generation_status": "GENERATED_UNVERIFIED",
    }
    job_file = workspace / "jobs" / (job_id + ".json")
    job_file.parent.mkdir(parents=True)
    job_file.write_text(json.dumps(job))
    (candidate / "transfer-plan.json").write_text("{}")
    receipt = candidate / "builder-receipt.json"
    receipt.write_text("{}")
    job["receipt_file"] = str(receipt)
    job_file.write_text(json.dumps(job))
    return workspace, candidate, job


def test_generation_time_native_and_hierarchy_are_recorded_separately(
    tmp_path, monkeypatch,
):
    workspace, candidate, job = _fixture(tmp_path)
    calls = []

    def native(job_file, out, *, unreal_api):
        calls.append(("native", str(out), unreal_api))
        document = {
            "kind": "cutsceneai.studio.persistence_audit",
            "native_structure_status": "PASS",
            "restart_verified": False,
        }
        Path(out).write_text(json.dumps(document))
        return document

    def hierarchy(job_file, out, *, unreal_api):
        calls.append(("hierarchy", str(out), unreal_api))
        document = {
            "kind": "cutsceneai.studio.hierarchy_persistence_audit",
            "status": "INCOMPLETE",
        }
        Path(out).write_text(json.dumps(document))
        return document

    monkeypatch.setitem(sys.modules, "studio_persistence_audit",
                        SimpleNamespace(audit=native))
    monkeypatch.setitem(sys.modules, "studio_hierarchy_audit",
                        SimpleNamespace(audit=hierarchy))
    api = object()
    result = readback.capture(workspace, job, unreal_api=api)
    assert result["native_structure"] == "PASS"
    assert result["source_hierarchy"] == "INCOMPLETE"
    assert result["restart_verified"] is False
    assert result["fidelity_verified"] is False
    assert all(row[-1] is api for row in calls)
    assert (candidate / ("generation-readback-audit-" + job["job_id"] + ".json")).is_file()
    assert not (candidate / ("post-reopen-audit-" + job["job_id"] + ".json")).exists()
    with pytest.raises(AssertionError):
        assert result["restart_verified"] is True


def test_generation_readback_failure_never_claims_native_pass(tmp_path, monkeypatch):
    workspace, candidate, job = _fixture(tmp_path)

    def native(*args, **kwargs):
        raise RuntimeError("Native Unreal binding enumeration failed")

    def hierarchy(*args, **kwargs):
        raise ValueError("Parent actor missing")

    monkeypatch.setitem(sys.modules, "studio_persistence_audit",
                        SimpleNamespace(audit=native))
    monkeypatch.setitem(sys.modules, "studio_hierarchy_audit",
                        SimpleNamespace(audit=hierarchy))
    result = readback.capture(workspace, job, unreal_api=object())
    assert result["native_structure"] == "INCOMPLETE"
    assert result["source_hierarchy"] == "INCOMPLETE"
    assert "binding enumeration failed" in result["native_structure_error"]
    assert "Parent actor missing" in result["source_hierarchy_error"]
    assert not list(candidate.glob("*readback-audit*"))


def test_generation_readback_refuses_wrong_candidate_or_job(tmp_path):
    workspace, _candidate, job = _fixture(tmp_path)
    other = dict(job, candidate_dir=str(tmp_path / "unsafe"))
    with pytest.raises(readback.GenerationReadbackError, match="candidate path"):
        readback.capture(workspace, other, unreal_api=object())
    stale = dict(job, sequence_path="/Game/Test/Unrelated")
    with pytest.raises(readback.GenerationReadbackError, match="not the current"):
        readback.capture(workspace, stale, unreal_api=object())
