"""The Transfer click drives a durable, one-job-at-a-time native workflow."""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "packages" / "studio"))

import studio_autopilot


@pytest.fixture
def rig(tmp_path, monkeypatch):
    work = tmp_path / "studio"
    work.mkdir()
    project = tmp_path / "unity"
    project.mkdir()
    (project / "Assets").mkdir()
    (project / "ProjectSettings").mkdir()
    target = tmp_path / "unreal"
    target.mkdir()
    (target / "Target.uproject").write_text("{}")
    state = {"job_status": "QUEUED"}
    ticket = "a" * 32

    monkeypatch.setattr(studio_autopilot.discovery, "project_roots", lambda path, kind: [
        str(project if kind == "unity" else target)
    ])
    monkeypatch.setattr(studio_autopilot.discovery, "scan_unreal", lambda *args, **kwargs: {
        "project": str(target / "Target.uproject"),
        "new_level_required": False, "active_level": "/Game/Trial",
        "levels": ["/Game/Trial"],
    })
    monkeypatch.setattr(studio_autopilot.unity_bridge, "request_snapshot",
                        lambda _: {"request_id": ticket, "instruction": "Open Unity"})
    monkeypatch.setattr(studio_autopilot.unity_bridge, "snapshot_status",
                        lambda *args: {"status": "WAITING_FOR_UNITY"})
    monkeypatch.setattr(studio_autopilot.discovery, "build_connection", lambda *args, **kwargs: {
        "csir": str(project / "source.csir.json"), "target_project": str(target / "Target.uproject"),
        "unity_project": str(project), "level_path": "/Game/Trial",
    })
    import studio_ui_features
    monkeypatch.setattr(studio_ui_features, "validate_options",
                        lambda config, opts: opts)

    def read(path):
        return json.loads(Path(path).read_text())

    def save(path, value):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(value))

    def prepare(workspace, opts):
        assert opts["require_complete_source_features"] is False
        candidate = {"candidate_id": "candidate1", "automatic_setup": {
            "available": True, "ready": True, "blockers": [],
        }}
        save(workspace / "active-candidate.json", candidate)
        return candidate

    def approve(candidate, workspace, *, enable_ai_agents):
        assert candidate == "candidate1"
        assert enable_ai_agents is True
        return {"approved": True}

    def queue(candidate, workspace):
        assert candidate == "candidate1"
        return {"job_id": "b" * 32}

    service = SimpleNamespace(
        lock=threading.RLock(),
        job_status=lambda job_id, workspace: {
            "status": state["job_status"],
            "generation_status": "GENERATED_UNVERIFIED" if
            state["job_status"] == "GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED"
            else "NOT_STARTED",
        },
        worker_connected=lambda workspace: {
            "connected": True, "project": str(target / "Target.uproject"),
            "level": "/Game/Trial",
        },
        config_check=lambda value: value,
        load_json=read,
        atomic_json=save,
        prepare=prepare,
        approve_one_click=approve,
        queue_trial=queue,
        destination_readiness=lambda workspace: {"ready": True},
    )
    return work, project, target, service, state


def test_one_transfer_advances_through_all_stages_without_extra_user_calls(rig, monkeypatch):
    workspace, project, target, service, state = rig
    with pytest.raises(studio_autopilot.AutopilotError, match="rights"):
        studio_autopilot.begin(workspace, unity_folder=str(project),
                               unreal_folder=str(target), source_rights_confirmed=False,
                               service=service)
    begin = studio_autopilot.begin(
        workspace, unity_folder=str(project), unreal_folder=str(target),
        source_rights_confirmed=True, service=service,
    )
    assert begin["status"] == "WAITING_FOR_UNITY"
    with pytest.raises(studio_autopilot.AutopilotError, match="already active"):
        studio_autopilot.begin(workspace, unity_folder=str(project),
                               unreal_folder=str(target), source_rights_confirmed=True,
                               service=service)
    waiting = studio_autopilot.advance(workspace, service=service)
    assert waiting["status"] == "WAITING_FOR_UNITY"
    csir = project / "source.csir.json"
    census = project / "feature-census.json"
    csir.write_text('{"source":{"engine":"unity"}}')
    census.write_text('{"engine":"unity"}')
    monkeypatch.setattr(studio_autopilot.unity_bridge, "snapshot_status",
                        lambda *args: {
                            "status": "SUCCEEDED",
                            "csir_path": str(csir), "census_path": str(census),
                        })
    assert studio_autopilot.advance(workspace, service=service)["status"] == "CONNECTING"
    assert studio_autopilot.advance(workspace, service=service)["status"] == "PREPARING"
    assert studio_autopilot.advance(workspace, service=service)["status"] == "WAITING_FOR_UNREAL"
    assert studio_autopilot.advance(workspace, service=service)["status"] == "UNREAL_RUNNING"
    state["job_status"] = "GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED"
    complete = studio_autopilot.advance(workspace, service=service)
    assert complete["status"] == "GENERATED_UNVERIFIED"
    assert complete["fidelity_verified"] is False
    assert complete["agent_enabled"] is True
    assert studio_autopilot.advance(workspace, service=service) == complete


def test_bad_source_receipt_blocks_without_preparing_anything(rig, monkeypatch):
    workspace, project, target, service, _ = rig
    studio_autopilot.begin(workspace, unity_folder=str(project), unreal_folder=str(target),
                           source_rights_confirmed=True, service=service)
    monkeypatch.setattr(studio_autopilot.unity_bridge, "snapshot_status",
                        lambda *args: {"status": "BLOCKED",
                                       "reason": "Ambiguous Unity Timeline selection."})
    result = studio_autopilot.advance(workspace, service=service)
    assert result["status"] == "BLOCKED"
    assert "Ambiguous" in result["error"]
    assert not (workspace / "active-candidate.json").exists()
    assert not (workspace / "active-job.json").exists()


def test_missing_native_worker_does_not_guess_target_editor_level(rig, monkeypatch):
    workspace, project, target, service, _ = rig
    service.worker_connected = lambda workspace: {"connected": False}
    studio_autopilot.begin(workspace, unity_folder=str(project), unreal_folder=str(target),
                           source_rights_confirmed=True, service=service)
    monkeypatch.setattr(studio_autopilot.unity_bridge, "snapshot_status",
                        lambda *args: {
                            "status": "SUCCEEDED", "csir_path": str(project / "source.csir.json"),
                            "census_path": str(project / "census.json"),
                        })
    assert studio_autopilot.advance(workspace, service=service)["status"] == "CONNECTING"
    result = studio_autopilot.advance(workspace, service=service)
    assert result["status"] == "CONNECTING"
    assert "Unreal" in result["message"]
    assert not (workspace / "connection.json").exists()
