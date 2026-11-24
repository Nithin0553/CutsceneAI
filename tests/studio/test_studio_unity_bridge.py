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
    CAPTURE_ACTION,
    UnityBridgeError,
    _evidence,
    behavior_capture_status,
    request_behavior_capture,
    request_snapshot,
    snapshot_status,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "cinetwin"))
from test_sampling_plan import _capture, _csir


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



def _valid_native_snapshot(project):
    ticket = request_snapshot(project)["request_id"]
    evidence = project / "CutSceneAI" / "StudioBridge" / "evidence"
    evidence.mkdir(exist_ok=True)
    csir = evidence / (ticket + ".csir.json")
    source = _csir()
    source["schema_version"] = "0.1.0"
    csir.write_text(json.dumps(source))
    census = evidence / "fresh-census.json"
    census.write_text(json.dumps({
        "kind": "cutsceneai.engine.feature_surface", "engine": "unity",
        "project_fingerprint": source["source"]["project_fingerprint"],
    }))
    _receipt(
        project, ticket,
        csir_path="CutSceneAI/StudioBridge/evidence/" + ticket + ".csir.json",
        csir_sha256=hashlib.sha256(csir.read_bytes()).hexdigest(),
        census_path="CutSceneAI/StudioBridge/evidence/fresh-census.json",
        census_sha256=hashlib.sha256(census.read_bytes()).hexdigest(),
    )
    return ticket


def test_one_click_prepares_source_bound_plan_without_faking_unity_play_mode(project):
    ticket = _valid_native_snapshot(project)
    request = request_behavior_capture(project, ticket)
    assert request["status"] == "WAITING_FOR_UNITY_PLAY_MODE"
    assert request["sample_count"] > 50
    bridge = project / "CutSceneAI" / "StudioBridge"
    raw = json.loads((bridge / "requests" / (request["request_id"] + ".json")).read_text())
    assert raw["action"] == CAPTURE_ACTION
    assert raw["source_request_id"] == ticket
    assert raw["source_csir_sha256"] == snapshot_status(project, ticket)["csir_sha256"]
    assert raw["plan_sha256"] == hashlib.sha256(
        (project / raw["plan_path"]).read_bytes()
    ).hexdigest()
    assert behavior_capture_status(project, request["request_id"])["status"] == "WAITING_FOR_UNITY_PLAY_MODE"
    assert not list(bridge.glob("evidence/*.cinetwin.behavior.json"))


def test_real_native_capture_receipt_is_checked_against_source_and_plan(project):
    ticket = _valid_native_snapshot(project)
    request = request_behavior_capture(project, ticket)
    bridge = project / "CutSceneAI" / "StudioBridge"
    raw = json.loads((bridge / "requests" / (request["request_id"] + ".json")).read_text())
    plan = json.loads((project / raw["plan_path"]).read_text())
    capture = _capture(plan)
    path = bridge / "evidence" / (request["request_id"] + ".cinetwin.behavior.json")
    path.write_text(json.dumps(capture))
    _receipt(
        project, request["request_id"], plan_sha256=raw["plan_sha256"],
        capture_path="CutSceneAI/StudioBridge/evidence/" + path.name,
        capture_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    received = behavior_capture_status(project, request["request_id"])
    assert received["status"] == "SUCCEEDED"
    assert received["source_capture_validated"] is True
    assert received["capture_path"] == str(path.resolve())
    assert received["fidelity_verified"] is False

    # Hash checks are on bytes at time of use, not a stale receipt label.
    capture["samples"].pop()
    path.write_text(json.dumps(capture))
    with pytest.raises(UnityBridgeError, match="changed"):
        behavior_capture_status(project, request["request_id"])


def test_forged_capture_path_and_wrong_cutscene_are_rejected(project):
    ticket = _valid_native_snapshot(project)
    request = request_behavior_capture(project, ticket)
    bridge = project / "CutSceneAI" / "StudioBridge"
    raw = json.loads((bridge / "requests" / (request["request_id"] + ".json")).read_text())
    plan = json.loads((project / raw["plan_path"]).read_text())
    capture = _capture(plan)
    capture["cutscene_id"] = "other-timeline"
    path = bridge / "evidence" / (request["request_id"] + ".cinetwin.behavior.json")
    path.write_text(json.dumps(capture))
    native_receipt = _receipt(
        project, request["request_id"], plan_sha256=raw["plan_sha256"],
        capture_path="CutSceneAI/StudioBridge/evidence/" + path.name,
        capture_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    with pytest.raises(UnityBridgeError, match="validation"):
        behavior_capture_status(project, request["request_id"])

    receipt = json.loads(native_receipt.read_text())
    receipt["capture_path"] = "../external.cinetwin.behavior.json"
    native_receipt.write_text(json.dumps(receipt))
    with pytest.raises(UnityBridgeError, match="path"):
        behavior_capture_status(project, request["request_id"])


def test_studio_unity_companion_never_silently_starts_scripts_or_saves_scene():
    source = (Path(__file__).resolve().parents[2] /
              "integrations/unity/com.cutsceneai.extractor/Editor/CutsceneAIStudioBridge.cs")
    text = source.read_text()
    assert "CAPTURE_SELECTED_TIMELINE_BEHAVIOR" in text
    assert "CineTwinBehaviorCapture.CaptureForStudio" in text
    assert "EditorApplication.isPlaying" in text
    assert "EditorApplication.EnterPlaymode" not in text
    assert "EditorApplication.isPlayingOrWillChangePlaymode" in text
    assert "SaveScene(" not in text
    assert "SaveAssets(" not in text
    bridge_asmdef = source.parent / "CutsceneAI.UnityExtractor.Editor.asmdef"
    assembly = json.loads(bridge_asmdef.read_text())
    assert "CutSceneAI.CineTwin.Capture.Editor" in assembly["references"]
    capture_code = (source.parents[1] / "CineTwin/Editor/CineTwinBehaviorCapture.cs").read_text()
    assert "public static class CineTwinBehaviorCapture" in capture_code
    assert "public static void CaptureForStudio(" in capture_code
    assert "FileMode.CreateNew" in capture_code



def test_unity_heartbeat_retries_windows_replace_without_truncating_published_file():
    """Source contract: transient Win32 sharing conflicts cannot corrupt a heartbeat.

    Compilation and actual Windows File.Replace contention remain native editor tests.
    """
    bridge = (Path(__file__).resolve().parents[2] /
              "integrations/unity/com.cutsceneai.extractor/Editor/CutsceneAIStudioBridge.cs")
    code = bridge.read_text()
    heartbeat = code.split("private static bool WritePresence(bool enabled)", 1)[1].split(
        "[Serializable]", 1)[0]
    assert 'Guid.NewGuid().ToString("N")' in heartbeat
    assert 'File.WriteAllText(temporary,' in heartbeat
    assert 'File.Replace(temporary, target, null)' in heartbeat
    assert 'File.Move(temporary, target)' in heartbeat
    assert 'for (var attempt = 0; attempt < 4; attempt++)' in heartbeat
    assert 'catch (IOException) when (attempt < 3)' in heartbeat
    assert 'System.Threading.Thread.Sleep(25 * (attempt + 1))' in heartbeat
    assert 'if (File.Exists(temporary))' in heartbeat
    assert 'File.Delete(temporary)' in heartbeat
    assert 'File.WriteAllText(target,' not in heartbeat
    assert 'File.Delete(target)' not in heartbeat
    assert 'File.Copy(temporary, target' not in heartbeat
    assert 'return false;' in heartbeat


def test_evidence_hash_streams_without_loading_large_file_into_memory(
        project, monkeypatch):
    directory = project / "CutSceneAI" / "StudioBridge" / "evidence"
    directory.mkdir(parents=True)
    data = (b'{"kind":"example","samples":[]}') * 1000
    path = directory / "capture.cinetwin.behavior.json"
    path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    original_read_bytes = Path.read_bytes

    def fail_unbounded_read(self):
        if self == path:
            pytest.fail("Evidence hash attempted to read an entire CineTwin file")
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", fail_unbounded_read)
    assert _evidence(
        project, "CutSceneAI/StudioBridge/evidence/" + path.name,
        sha, ".cinetwin.behavior.json",
    ) == str(path.resolve())


def test_oversized_sparse_capture_rejected_before_hashing(project, monkeypatch):
    directory = project / "CutSceneAI" / "StudioBridge" / "evidence"
    directory.mkdir(parents=True)
    path = directory / "oversized.cinetwin.behavior.json"
    with path.open("wb") as handle:
        handle.truncate(129 * 1024 * 1024)
    # The sparse file is intentionally untrusted. Reading/hash-processing any
    # bytes would be unnecessary and dangerously memory/cpu-expensive.
    original_open = Path.open

    def reject_read(self, *args, **kwargs):
        if self == path and (not args or args[0] == "rb"):
            pytest.fail("Oversized CineTwin evidence was read before size validation")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_read)
    with pytest.raises(UnityBridgeError, match="128 MiB"):
        _evidence(
            project, "CutSceneAI/StudioBridge/evidence/" + path.name,
            "0" * 64, ".cinetwin.behavior.json",
        )



def test_malformed_source_identity_is_classified_without_unhandled_attribute_error(project):
    ticket = request_snapshot(project)["request_id"]
    directory = project / "CutSceneAI" / "StudioBridge" / "evidence"
    directory.mkdir(exist_ok=True)
    csir = directory / (ticket + ".csir.json")
    census = directory / (ticket + ".census.json")
    csir.write_text(json.dumps({
        "schema_version": "0.1.0", "source": ["malformed", "not an identity"],
    }))
    census.write_text(json.dumps({
        "kind": "cutsceneai.engine.feature_surface",
        "engine": "unity", "project_fingerprint": "source-1",
    }))
    _receipt(
        project, ticket,
        csir_path="CutSceneAI/StudioBridge/evidence/" + csir.name,
        csir_sha256=hashlib.sha256(csir.read_bytes()).hexdigest(),
        census_path="CutSceneAI/StudioBridge/evidence/" + census.name,
        census_sha256=hashlib.sha256(census.read_bytes()).hexdigest(),
    )
    with pytest.raises(UnityBridgeError, match="not a supported Unity source"):
        snapshot_status(project, ticket)
