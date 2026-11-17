"""Pure Python validation of the opt-in Unity source snapshot queue."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from studio_unity_bridge import (
    BRIDGE_KIND,
    UnityBridgeError,
    request_snapshot,
    snapshot_status,
)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "Assets").mkdir()
    (tmp_path / "ProjectSettings").mkdir()
    return tmp_path


def test_request_requires_real_project_and_is_not_a_fake_export(tmp_path, project):
    with pytest.raises(UnityBridgeError):
        request_snapshot(tmp_path / "not-a-unity-project")
    result = request_snapshot(project)
    assert result["status"] == "WAITING_FOR_UNITY"
    assert snapshot_status(project, result["request_id"])["status"] == "WAITING_FOR_UNITY"
    payload = json.loads((project / "CutSceneAI" / "StudioBridge" / "requests" /
                          (result["request_id"] + ".json")).read_text())
    assert payload["action"] == "EXPORT_SELECTED_TIMELINE_AND_CENSUS"
    assert payload["kind"] == BRIDGE_KIND
    assert not list((project / "Assets").iterdir())


def _receipt(project, ticket, **fields):
    p = project / "CutSceneAI" / "StudioBridge" / "receipts"
    p.mkdir(parents=True, exist_ok=True)
    value = {"kind": BRIDGE_KIND, "schema_version": "1",
             "request_id": ticket, "status": "SUCCEEDED", **fields}
    (p / (ticket + ".json")).write_text(json.dumps(value))
    return p / (ticket + ".json")


def test_valid_receipt_checks_evidence_bytes_and_provenance(project):
    ticket = request_snapshot(project)["request_id"]
    evidence = project / "CutSceneAI" / "StudioBridge" / "evidence"
    evidence.mkdir()
    csir = evidence / (ticket + ".csir.json")
    census = evidence / "census.json"
    csir.write_text(json.dumps({
        "schema_version": "0.1.0",
        "source": {"engine": "unity", "project_fingerprint": "project_123"},
    }))
    census.write_text(json.dumps({
        "kind": "cutsceneai.engine.feature_surface",
        "engine": "unity",
        "project_fingerprint": "project_123",
    }))
    fields = {
        "csir_path": f"CutSceneAI/StudioBridge/evidence/{ticket}.csir.json",
        "census_path": "CutSceneAI/StudioBridge/evidence/census.json",
        "csir_sha256": hashlib.sha256(csir.read_bytes()).hexdigest(),
        "census_sha256": hashlib.sha256(census.read_bytes()).hexdigest(),
    }
    _receipt(project, ticket, **fields)
    result = snapshot_status(project, ticket)
    assert result["status"] == "SUCCEEDED"
    assert result["csir_path"] == str(csir.resolve())
    assert result["fidelity_verified"] is False
    csir.write_text("{}")
    with pytest.raises(UnityBridgeError, match="changed"):
        snapshot_status(project, ticket)


def test_untrusted_receipt_does_not_escape_selected_project(project, tmp_path):
    ticket = request_snapshot(project)["request_id"]
    outside = tmp_path.parent / "other.csir.json"
    outside.write_text("{}")
    _receipt(project, ticket, csir_path="../other.csir.json",
             csir_sha256=hashlib.sha256(outside.read_bytes()).hexdigest(),
             census_path="nope.json", census_sha256="0" * 64)
    with pytest.raises(UnityBridgeError):
        snapshot_status(project, ticket)


def test_mismatched_receipt_and_invalid_ticket_are_rejected(project):
    ticket = request_snapshot(project)["request_id"]
    _receipt(project, ticket, request_id="f" * 32)
    with pytest.raises(UnityBridgeError, match="mismatched"):
        snapshot_status(project, ticket)
    with pytest.raises(UnityBridgeError, match="identity"):
        snapshot_status(project, "../../fake")


def test_blocked_native_export_returns_user_action(project):
    ticket = request_snapshot(project)["request_id"]
    _receipt(project, ticket, status="BLOCKED", reason="Select a saved Timeline.")
    result = snapshot_status(project, ticket)
    assert result["status"] == "BLOCKED"
    assert "saved Timeline" in result["reason"]


def test_bridge_rejects_symlinked_request_root(project, tmp_path):
    folder = project / "CutSceneAI"
    try:
        folder.symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not available")
    with pytest.raises(UnityBridgeError, match="Unsafe"):
        request_snapshot(project)


def test_matching_byte_hashes_cannot_hide_wrong_source_identity(project):
    ticket = request_snapshot(project)["request_id"]
    evidence = project / "CutSceneAI" / "StudioBridge" / "evidence"
    evidence.mkdir()
    csir = evidence / (ticket + ".csir.json")
    census = evidence / "census.json"
    csir.write_text(json.dumps({
        "schema_version": "0.1.0",
        "source": {"engine": "unity", "project_fingerprint": "project_one"},
    }))
    census.write_text(json.dumps({
        "kind": "cutsceneai.engine.feature_surface",
        "engine": "unity",
        "project_fingerprint": "project_two",
    }))
    _receipt(
        project, ticket,
        csir_path=f"CutSceneAI/StudioBridge/evidence/{ticket}.csir.json",
        csir_sha256=hashlib.sha256(csir.read_bytes()).hexdigest(),
        census_path="CutSceneAI/StudioBridge/evidence/census.json",
        census_sha256=hashlib.sha256(census.read_bytes()).hexdigest(),
    )
    with pytest.raises(UnityBridgeError, match="identity"):
        snapshot_status(project, ticket)
