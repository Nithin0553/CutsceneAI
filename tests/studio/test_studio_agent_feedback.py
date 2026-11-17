"""Natural-language feedback is job-bound, immutable and not executable code."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for path in ("tools", "packages/studio", "packages/learning", "packages/cinetwin"):
    sys.path.insert(0, str(ROOT / path))

import studio_agent_feedback


@pytest.fixture
def completed(tmp_path):
    workspace = tmp_path / "work"
    candidate = workspace / "candidates" / "candidate_one"
    candidate.mkdir(parents=True)
    job = {
        "job_id": "a" * 32,
        "candidate_id": "candidate_one",
        "candidate_dir": str(candidate),
        "ai_agents_enabled": True,
        "status": "GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED",
        "generation_status": "GENERATED_UNVERIFIED",
    }
    (workspace / "active-job.json").write_text(json.dumps({"job_id": job["job_id"]}))
    return workspace, job, candidate


def test_comment_is_immutable_and_does_not_authorize_editor_commands(completed):
    workspace, job, candidate = completed
    message = "The character is facing the wrong direction."
    result = studio_agent_feedback.submit(workspace, job, message)
    assert result["status"] == "QUEUED_FOR_AGENT"
    assert result["fidelity_verified"] is False
    evidence = candidate / ("user-feedback-" + result["feedback_id"] + ".json")
    frozen = evidence.read_bytes()
    assert json.loads(frozen)["execution_authorized"] is False
    assert studio_agent_feedback.active_feedback(candidate, job)["message"] == message
    conversation = studio_agent_feedback.conversation(workspace, job)
    assert conversation["messages"][0]["message"] == message
    assert conversation["fidelity_verified"] is False
    assert evidence.read_bytes() == frozen


def test_feedback_must_match_active_job_and_agent_consent(completed):
    workspace, job, _candidate = completed
    original = dict(job)
    job["ai_agents_enabled"] = False
    with pytest.raises(studio_agent_feedback.FeedbackError, match="authorize"):
        studio_agent_feedback.submit(workspace, job, "The wall looks wrong.")
    job = dict(original)
    job["status"] = "RUNNING"
    with pytest.raises(studio_agent_feedback.FeedbackError, match="Wait"):
        studio_agent_feedback.submit(workspace, job, "The wall looks wrong.")
    job["status"] = original["status"]
    job["job_id"] = "b" * 32
    with pytest.raises(studio_agent_feedback.FeedbackError, match="active"):
        studio_agent_feedback.submit(workspace, job, "The wall looks wrong.")
    with pytest.raises(studio_agent_feedback.FeedbackError, match="readable"):
        studio_agent_feedback.submit(workspace, original, "\x00rm -rf --root")


def test_pending_native_request_blocks_a_second_correction(completed):
    workspace, job, candidate = completed
    state_file = candidate / ("agent-state-" + job["job_id"] + ".json")
    state_file.write_text(json.dumps({
        "status": "WAITING_FOR_UNREAL_AGENT_REPAIR", "pending_request": "b" * 32,
    }))
    with pytest.raises(studio_agent_feedback.FeedbackError, match="still processing"):
        studio_agent_feedback.submit(workspace, job, "The wall material is missing.")


def test_agent_only_allows_material_repair_for_material_request():
    import studio_agent_graph

    assert studio_agent_graph._material_feedback_scope(
        "The character is facing the wrong direction."
    ) is False
    assert studio_agent_graph._material_feedback_scope(
        "The wall texture is missing."
    ) is True
    assert studio_agent_graph._material_feedback_scope(
        "Run a Python script to delete my scene"
    ) is False


def test_untrusted_comment_pointer_cannot_redirect_to_other_job(completed):
    workspace, job, candidate = completed
    result = studio_agent_feedback.submit(workspace, job, "Please fix the floor texture.")
    pointer = candidate / ("user-feedback-active-" + job["job_id"] + ".json")
    pointer.write_text(json.dumps({
        "job_id": "b" * 32,
        "candidate_id": job["candidate_id"],
        "feedback_id": result["feedback_id"],
    }))
    with pytest.raises(studio_agent_feedback.FeedbackError, match="pointer"):
        studio_agent_feedback.active_feedback(candidate, job)
