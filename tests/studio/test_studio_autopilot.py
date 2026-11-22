"""The Transfer click drives a durable, one-job-at-a-time native workflow."""
from __future__ import annotations

import json
import sys
import threading
from datetime import UTC, datetime, timedelta
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
    monkeypatch.setattr(studio_autopilot.unity_bridge, "request_behavior_capture",
                        lambda *args: {"request_id": "c" * 32,
                                       "instruction": "Enter Unity Play Mode."})
    monkeypatch.setattr(studio_autopilot.unity_bridge, "behavior_capture_status",
                        lambda *args: {"status": "SUCCEEDED",
                                       "capture_path": str(project / "capture.json")})
    monkeypatch.setattr(studio_autopilot.discovery, "build_connection", lambda *args, **kwargs: {
        "csir": str(project / "source.csir.json"), "target_project": str(target / "Target.uproject"),
        "unity_project": str(project), "level_path": "/Game/Trial",
    })
    import studio_transfer_ai
    import studio_ui_features
    monkeypatch.setattr(studio_ui_features, "validate_options",
                        lambda config, opts: opts)
    monkeypatch.setattr(studio_transfer_ai, "decide", lambda config, census, worker: {
        "kind": studio_transfer_ai.SCHEMA,
        "schema_version": "1",
        "strategy": "source_materials",
        "conversion_options": {"enable_fbx_embedded_material_import": True,
                               "enable_actor_visibility_fallback": False},
    })
    monkeypatch.setattr(studio_transfer_ai, "verify",
                        lambda decision, config, census, worker:
                        decision["conversion_options"])

    def read(path):
        return json.loads(Path(path).read_text())

    def save(path, value):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(value))

    def prepare(workspace, opts):
        assert opts["require_complete_source_features"] is False
        candidate = {"candidate_id": "candidate1",
                     "candidate_dir": str(workspace / "candidates" / "candidate1"),
                     "automatic_setup": {
            "available": True, "ready": True, "blockers": [],
        }}
        save(workspace / "active-candidate.json", candidate)
        (workspace / "candidates" / "candidate1").mkdir(parents=True, exist_ok=True)
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
    assert studio_autopilot.advance(workspace, service=service)["status"] == "WAITING_FOR_UNITY_CAPTURE"
    assert studio_autopilot.advance(workspace, service=service)["status"] == "CONNECTING"
    assert studio_autopilot.advance(workspace, service=service)["status"] == "ANALYZING_PROJECTS"
    assert studio_autopilot.advance(workspace, service=service)["status"] == "PREPARING"
    assert studio_autopilot.advance(workspace, service=service)["status"] == "WAITING_FOR_UNREAL"
    assert json.loads((workspace / "candidates" / "candidate1" /
                       "ai-conversion-decision.json").read_text())["strategy"] == "source_materials"
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
    assert studio_autopilot.advance(workspace, service=service)["status"] == "WAITING_FOR_UNITY_CAPTURE"
    assert studio_autopilot.advance(workspace, service=service)["status"] == "CONNECTING"
    result = studio_autopilot.advance(workspace, service=service)
    assert result["status"] == "CONNECTING"
    assert "Unreal" in result["message"]
    assert not (workspace / "connection.json").exists()



def test_source_play_mode_capture_waits_without_faking_evidence(rig, monkeypatch):
    workspace, project, target, service, _ = rig
    studio_autopilot.begin(
        workspace, unity_folder=str(project), unreal_folder=str(target),
        source_rights_confirmed=True, service=service,
    )
    monkeypatch.setattr(studio_autopilot.unity_bridge, "snapshot_status",
                        lambda *args: {
                            "status": "SUCCEEDED",
                            "csir_path": str(project / "source.csir.json"),
                            "census_path": str(project / "census.json"),
                        })
    monkeypatch.setattr(studio_autopilot.unity_bridge, "behavior_capture_status",
                        lambda *args: {
                            "status": "WAITING_FOR_UNITY_PLAY_MODE",
                            "message": "Enter Play Mode; no source behavior was invented.",
                        })
    assert studio_autopilot.advance(workspace, service=service)["status"] == "WAITING_FOR_UNITY_CAPTURE"
    waiting = studio_autopilot.advance(workspace, service=service)
    assert waiting["status"] == "WAITING_FOR_UNITY_CAPTURE"
    assert "Play Mode" in waiting["message"]
    assert not (workspace / "connection.json").exists()
    assert not (workspace / "active-candidate.json").exists()


def test_blocked_native_source_capture_never_queues_unreal_job(rig, monkeypatch):
    workspace, project, target, service, _ = rig
    studio_autopilot.begin(
        workspace, unity_folder=str(project), unreal_folder=str(target),
        source_rights_confirmed=True, service=service,
    )
    monkeypatch.setattr(studio_autopilot.unity_bridge, "snapshot_status",
                        lambda *args: {
                            "status": "SUCCEEDED",
                            "csir_path": str(project / "source.csir.json"),
                            "census_path": str(project / "census.json"),
                        })
    monkeypatch.setattr(studio_autopilot.unity_bridge, "behavior_capture_status",
                        lambda *args: {
                            "status": "BLOCKED", "reason": "Mismatched Unity Timeline GUID.",
                        })
    assert studio_autopilot.advance(workspace, service=service)["status"] == "WAITING_FOR_UNITY_CAPTURE"
    blocked = studio_autopilot.advance(workspace, service=service)
    assert blocked["status"] == "BLOCKED"
    assert "Mismatched Unity Timeline" in blocked["error"]
    assert not (workspace / "active-job.json").exists()


def test_pre_execution_cancel_is_durable_and_keeps_existing_files(rig):
    workspace, project, target, service, _ = rig
    started = studio_autopilot.begin(
        workspace, unity_folder=str(project), unreal_folder=str(target),
        source_rights_confirmed=True, service=service,
    )
    assert started["status"] == "WAITING_FOR_UNITY"
    existing = workspace / "candidates" / "existing" / "receipt.json"
    existing.parent.mkdir(parents=True)
    existing.write_text('{"source":"preserve"}', encoding="utf-8")
    cancelled = studio_autopilot.cancel(workspace, service=service)
    assert cancelled["status"] == "CANCELLED"
    assert studio_autopilot.advance(workspace, service=service) == cancelled
    assert existing.read_text(encoding="utf-8") == '{"source":"preserve"}'
    assert not (workspace / "active-job.json").exists()
    again = studio_autopilot.begin(
        workspace, unity_folder=str(project), unreal_folder=str(target),
        source_rights_confirmed=True, service=service,
    )
    assert again["status"] == "WAITING_FOR_UNITY"


def test_native_execution_cannot_be_interrupted_by_autopilot_cancel(rig):
    workspace, project, target, service, state = rig
    studio_autopilot.begin(
        workspace, unity_folder=str(project), unreal_folder=str(target),
        source_rights_confirmed=True, service=service,
    )
    active = workspace / studio_autopilot.ACTIVE
    record = json.loads(active.read_text(encoding="utf-8"))
    record["status"] = "UNREAL_RUNNING"
    active.write_text(json.dumps(record), encoding="utf-8")
    job = workspace / "active-job.json"
    job.write_text(json.dumps({"job_id": "b" * 32}), encoding="utf-8")
    state["job_status"] = "QUEUED"
    with pytest.raises(studio_autopilot.AutopilotError, match="cannot be interrupted"):
        studio_autopilot.cancel(workspace, service=service)
    assert json.loads(active.read_text())["status"] == "UNREAL_RUNNING"
    assert json.loads(job.read_text())["job_id"] == "b" * 32


def test_unreal_disconnection_pauses_ai_analysis_and_preparation(rig, monkeypatch):
    workspace, project, target, service, _ = rig
    native_worker = service.worker_connected
    connected = {"value": True}
    service.worker_connected = lambda folder: (
        native_worker(folder) if connected["value"] else {"connected": False}
    )
    studio_autopilot.begin(
        workspace, unity_folder=str(project), unreal_folder=str(target),
        source_rights_confirmed=True, service=service,
    )
    csir = project / "source.csir.json"
    census = project / "census.json"
    csir.write_text('{"source":{"engine":"unity"}}', encoding="utf-8")
    census.write_text('{"source":"unity"}', encoding="utf-8")
    monkeypatch.setattr(studio_autopilot.unity_bridge, "snapshot_status",
                        lambda *_: {
                            "status": "SUCCEEDED",
                            "csir_path": str(csir),
                            "census_path": str(census),
                        })
    assert studio_autopilot.advance(workspace, service=service)[
        "status"] == "WAITING_FOR_UNITY_CAPTURE"
    assert studio_autopilot.advance(workspace, service=service)[
        "status"] == "CONNECTING"
    assert studio_autopilot.advance(workspace, service=service)[
        "status"] == "ANALYZING_PROJECTS"
    connected["value"] = False
    waiting = studio_autopilot.advance(workspace, service=service)
    assert waiting["status"] == "ANALYZING_PROJECTS"
    assert "Reconnect" in waiting["message"]
    assert not (workspace / "ai-conversion-decision.json").exists()
    connected["value"] = True
    assert studio_autopilot.advance(workspace, service=service)[
        "status"] == "PREPARING"
    decision_path = workspace / "ai-conversion-decision.json"
    previous = decision_path.read_bytes()
    connected["value"] = False
    waiting = studio_autopilot.advance(workspace, service=service)
    assert waiting["status"] == "PREPARING"
    assert "Reconnect" in waiting["message"]
    assert decision_path.read_bytes() == previous
    assert not (workspace / "active-candidate.json").exists()
    connected["value"] = True
    assert studio_autopilot.advance(workspace, service=service)[
        "status"] == "WAITING_FOR_UNREAL"
    assert decision_path.read_bytes() == previous


def _recovery_evidence(workspace, project, target, candidate_dir):
    config = {
        "csir": str(project / "source.csir.json"),
        "capture": str(project / "capture.json"),
        "target_project": str(target / "Target.uproject"),
        "level_path": "/Game/Trial",
    }
    (workspace / "connection.json").write_text(json.dumps(config))
    (workspace / "active-candidate.json").write_text(
        json.dumps({"candidate_id": "candidate1"})
    )
    (candidate_dir / "session.json").write_text(json.dumps({
        "source": {"csir_path": config["csir"]},
        "source_capture": {"path": config["capture"]},
        "target": {
            "project_path": config["target_project"],
            "sequence_asset_path": "/Game/CutSceneAI/LS_Candidate",
            "mapping_path": str(candidate_dir / "resolved-mapping.json"),
        },
    }))
    return {
        "csir": config["csir"],
        "capture": config["capture"],
        "expected_project": config["target_project"],
        "expected_level": config["level_path"],
        "sequence_path": "/Game/CutSceneAI/LS_Candidate",
        "mapping": str(candidate_dir / "resolved-mapping.json"),
    }


def test_crash_after_unreal_job_submission_recovers_without_requeue(rig):
    workspace, project, target, service, _ = rig
    studio_autopilot.begin(
        workspace, unity_folder=str(project), unreal_folder=str(target),
        source_rights_confirmed=True, service=service,
    )
    active = workspace / studio_autopilot.ACTIVE
    record = json.loads(active.read_text())
    record.update(status="WAITING_FOR_UNREAL", candidate_id="candidate1")
    active.write_text(json.dumps(record))
    candidate_dir = workspace / "candidates" / "candidate1"
    candidate_dir.mkdir(parents=True)
    metadata = _recovery_evidence(workspace, project, target, candidate_dir)
    job_id = "d" * 32
    job_path = workspace / "jobs" / (job_id + ".json")
    job_path.parent.mkdir()
    job_path.write_text(json.dumps({
        "kind": "cutsceneai.studio.local_unreal_job",
        "job_id": job_id, "candidate_id": "candidate1",
        "candidate_dir": str(candidate_dir), "status": "QUEUED",
        **metadata,
    }))
    service.queue_trial = lambda *_: pytest.fail("Never queue the already submitted job")
    recovered = studio_autopilot.advance(workspace, service=service)
    assert recovered["status"] == "UNREAL_RUNNING"
    assert recovered["job_id"] == job_id
    assert json.loads((workspace / "active-job.json").read_text())["job_id"] == job_id
    assert len(list((workspace / "jobs").glob("*.json"))) == 1


def test_native_job_recovery_rejects_wrong_level_after_crash(rig):
    workspace, project, target, service, _ = rig
    studio_autopilot.begin(
        workspace, unity_folder=str(project), unreal_folder=str(target),
        source_rights_confirmed=True, service=service,
    )
    active = workspace / studio_autopilot.ACTIVE
    record = json.loads(active.read_text())
    record.update(status="WAITING_FOR_UNREAL", candidate_id="candidate1")
    active.write_text(json.dumps(record))
    candidate_dir = workspace / "candidates" / "candidate1"
    candidate_dir.mkdir(parents=True)
    metadata = _recovery_evidence(workspace, project, target, candidate_dir)
    metadata["expected_level"] = "/Game/WrongTarget"
    job_id = "d" * 32
    jobs = workspace / "jobs"
    jobs.mkdir()
    (jobs / (job_id + ".json")).write_text(json.dumps({
        "kind": "cutsceneai.studio.local_unreal_job",
        "job_id": job_id, "candidate_id": "candidate1",
        "candidate_dir": str(candidate_dir), **metadata,
    }))
    service.queue_trial = lambda *_: pytest.fail("Never requeue a tampered job")
    result = studio_autopilot.advance(workspace, service=service)
    assert result["status"] == "BLOCKED"
    assert "source, target or mapping changed" in result["error"]
    assert not (workspace / "active-job.json").exists()


def test_crash_recovery_refuses_duplicate_jobs_and_conflicting_pointer(rig):
    workspace, project, target, service, _ = rig
    studio_autopilot.begin(
        workspace, unity_folder=str(project), unreal_folder=str(target),
        source_rights_confirmed=True, service=service,
    )
    active = workspace / studio_autopilot.ACTIVE
    state = json.loads(active.read_text())
    state.update(status="WAITING_FOR_UNREAL", candidate_id="candidate1")
    active.write_text(json.dumps(state))
    candidate_dir = workspace / "candidates" / "candidate1"
    candidate_dir.mkdir(parents=True)
    metadata = _recovery_evidence(workspace, project, target, candidate_dir)
    jobs = workspace / "jobs"
    jobs.mkdir()
    for letter in ("d", "e"):
        ident = letter * 32
        (jobs / (ident + ".json")).write_text(json.dumps({
            "kind": "cutsceneai.studio.local_unreal_job",
            "job_id": ident, "candidate_id": "candidate1",
            "candidate_dir": str(candidate_dir),
            **metadata,
        }))
    service.queue_trial = lambda *_: pytest.fail("Ambiguous jobs must not be replayed")
    blocked = studio_autopilot.advance(workspace, service=service)
    assert blocked["status"] == "BLOCKED"
    assert "Multiple jobs" in blocked["error"]
    assert not (workspace / "active-job.json").exists()

    (jobs / ("e" * 32 + ".json")).unlink()
    active.write_text(json.dumps(state))
    (workspace / "active-job.json").write_text(json.dumps({"job_id": "e" * 32}))
    blocked = studio_autopilot.advance(workspace, service=service)
    assert blocked["status"] == "BLOCKED"
    assert "Another Unreal job" in blocked["error"]


def test_orphaned_native_character_probe_times_out_without_ai_or_native_write(rig, monkeypatch):
    workspace, project, target, service, _ = rig
    studio_autopilot.begin(
        workspace, unity_folder=str(project), unreal_folder=str(target),
        source_rights_confirmed=True, service=service,
    )
    active = workspace / studio_autopilot.ACTIVE
    state = json.loads(active.read_text())
    state.update(status="ANALYZING_PROJECTS", census_path=str(project / "census.json"))
    active.write_text(json.dumps(state))
    (workspace / "connection.json").write_text(json.dumps({"source": "verified"}))
    import studio_transfer_ai
    monkeypatch.setattr(studio_transfer_ai, "target_probe",
                        lambda *args, **kwargs: (True, None))
    waiting = studio_autopilot.advance(workspace, service=service)
    assert waiting["status"] == "ANALYZING_PROJECTS"
    pending = json.loads(active.read_text())
    assert pending["native_probe_wait_started_at"]
    pending["native_probe_wait_started_at"] = (
        datetime.now(UTC) - timedelta(seconds=181)
    ).isoformat()
    active.write_text(json.dumps(pending))
    blocked = studio_autopilot.advance(workspace, service=service)
    assert blocked["status"] == "BLOCKED"
    assert "timed out" in blocked["error"]
    assert not (workspace / "ai-conversion-decision.json").exists()
    assert not (workspace / "active-candidate.json").exists()
    assert not (workspace / "active-job.json").exists()


def test_restart_during_partial_candidate_preparation_refuses_second_candidate(rig):
    workspace, project, target, service, _ = rig
    studio_autopilot.begin(
        workspace, unity_folder=str(project), unreal_folder=str(target),
        source_rights_confirmed=True, service=service,
    )
    active = workspace / studio_autopilot.ACTIVE
    state = json.loads(active.read_text())
    state.update(status="PREPARING")
    active.write_text(json.dumps(state))
    (workspace / "active-candidate.json").write_text(json.dumps({"candidate_id": "existing"}))
    service.prepare = lambda *_: pytest.fail("Never prepare a second candidate after crash")
    blocked = studio_autopilot.advance(workspace, service=service)
    assert blocked["status"] == "BLOCKED"
    assert "already prepared" in blocked["error"]


def test_stalled_unity_play_mode_capture_times_out_without_reissuing_requests(rig, monkeypatch):
    workspace, project, target, service, _ = rig
    studio_autopilot.begin(
        workspace, unity_folder=str(project), unreal_folder=str(target),
        source_rights_confirmed=True, service=service,
    )
    monkeypatch.setattr(studio_autopilot.unity_bridge, "snapshot_status",
                        lambda *_: {
                            "status": "SUCCEEDED", "csir_path": str(project / "source.csir.json"),
                            "census_path": str(project / "feature-census.json"),
                        })
    requests = {"count": 0}

    def request_capture(*_):
        requests["count"] += 1
        return {"request_id": "c" * 32, "instruction": "Enter Unity Play Mode."}

    monkeypatch.setattr(studio_autopilot.unity_bridge, "request_behavior_capture",
                        request_capture)
    monkeypatch.setattr(studio_autopilot.unity_bridge, "behavior_capture_status",
                        lambda *_: {
                            "status": "WAITING_FOR_UNITY_PLAY_MODE",
                            "message": "No source receipt yet.",
                        })
    assert studio_autopilot.advance(workspace, service=service)[
        "status"] == "WAITING_FOR_UNITY_CAPTURE"
    active = workspace / studio_autopilot.ACTIVE
    pending = json.loads(active.read_text())
    assert requests["count"] == 1
    assert pending["capture_wait_started_at"]
    pending["capture_wait_started_at"] = (
        datetime.now(UTC) - timedelta(seconds=3601)
    ).isoformat()
    active.write_text(json.dumps(pending))
    blocked = studio_autopilot.advance(workspace, service=service)
    assert blocked["status"] == "BLOCKED"
    assert "capture timed out" in blocked["error"]
    assert requests["count"] == 1
    assert not (workspace / "active-candidate.json").exists()
    assert not (workspace / "active-job.json").exists()


def test_completed_unity_capture_is_accepted_even_after_wait_limit(rig, monkeypatch):
    workspace, project, target, service, _ = rig
    studio_autopilot.begin(
        workspace, unity_folder=str(project), unreal_folder=str(target),
        source_rights_confirmed=True, service=service,
    )
    monkeypatch.setattr(studio_autopilot.unity_bridge, "snapshot_status",
                        lambda *_: {
                            "status": "SUCCEEDED", "csir_path": str(project / "source.csir.json"),
                            "census_path": str(project / "feature-census.json"),
                        })
    assert studio_autopilot.advance(workspace, service=service)[
        "status"] == "WAITING_FOR_UNITY_CAPTURE"
    active = workspace / studio_autopilot.ACTIVE
    pending = json.loads(active.read_text())
    pending["capture_wait_started_at"] = (
        datetime.now(UTC) - timedelta(seconds=3601)
    ).isoformat()
    active.write_text(json.dumps(pending))
    result = studio_autopilot.advance(workspace, service=service)
    assert result["status"] == "CONNECTING"
    assert "capture_wait_started_at" not in json.loads(active.read_text())



def test_model_disconnect_recovers_only_before_unreal_submission(rig, monkeypatch):
    workspace, project, target, service, _ = rig
    import studio_recovery_policy
    import studio_transfer_ai
    studio_autopilot.begin(
        workspace, unity_folder=str(project), unreal_folder=str(target),
        source_rights_confirmed=True, service=service,
    )
    state_file = workspace / "autopilot-active.json"
    state = json.loads(state_file.read_text())
    state.update({
        "status": "ANALYZING_PROJECTS",
        "csir_path": str(project / "source.csir.json"),
        "census_path": str(project / "census.json"),
        "capture_path": str(project / "capture.json"),
    })
    state_file.write_text(json.dumps(state))
    config = {
        "unity_project": str(project), "target_project": str(target / "Target.uproject"),
        "csir": state["csir_path"], "capture": state["capture_path"],
        "level_path": "/Game/Trial",
    }
    (workspace / "connection.json").write_text(json.dumps(config))

    def unavailable(*_args, **_kwargs):
        raise studio_transfer_ai.TransferAIError(
            "Pre-transfer AI reasoning failed: Local Ollama is unavailable."
        )

    monkeypatch.setattr(studio_transfer_ai, "decide", unavailable)
    waiting = studio_autopilot.advance(workspace, service=service)
    assert waiting["status"] == "WAITING_FOR_MODEL"
    assert waiting["failure_category"] == "MODEL_PROVIDER_UNAVAILABLE"
    assert waiting["model_retry_attempts"] == 0
    assert not (workspace / "active-job.json").exists()
    assert not (workspace / "active-candidate.json").exists()
    with pytest.raises(studio_autopilot.AutopilotError, match="already active"):
        studio_autopilot.begin(
            workspace, unity_folder=str(project), unreal_folder=str(target),
            source_rights_confirmed=True, service=service,
        )
    state = json.loads(state_file.read_text())
    state["next_model_retry_at"] = (datetime.now(UTC) - timedelta(seconds=2)).isoformat()
    state_file.write_text(json.dumps(state))
    resumed = studio_autopilot.advance(workspace, service=service)
    assert resumed["status"] == "ANALYZING_PROJECTS"
    assert resumed["model_retry_attempts"] == 1
    monkeypatch.setattr(studio_transfer_ai, "decide", lambda *args, **kwargs: {
        "kind": studio_transfer_ai.SCHEMA, "strategy": "native_source",
        "conversion_options": {"enable_fbx_embedded_material_import": False,
                               "enable_actor_visibility_fallback": False},
    })
    assert studio_autopilot.advance(workspace, service=service)["status"] == "PREPARING"
    assert not (workspace / "active-job.json").exists()
    assert studio_recovery_policy.MAX_MODEL_RETRIES == 3


def test_recovery_never_replays_native_job():
    import studio_recovery_policy as recovery
    result = recovery.classify(
        "Local Ollama is unavailable", phase="UNREAL_RUNNING", native_submitted=True,
    )
    assert result["safe_automatic_retry"] is False
    assert result["native_replay_authorized"] is False
    assert result["category"] == "NATIVE_JOB_NEEDS_INSPECTION"
