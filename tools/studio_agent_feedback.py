"""User-directed natural-language feedback for one generated Studio transfer.

User comments are immutable and source-job bound. A comment may re-open the
bounded, allowlisted LangGraph diagnosis, but cannot authorize arbitrary Unreal
commands, overwrite an existing scene or certify the result.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ID = re.compile(r"[0-9a-f]{32}\Z")
MAX_COMMENT = 1200


class FeedbackError(ValueError):
    pass


def _json(path: Path) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 48 * 1024:
        raise FeedbackError("Missing or oversized agent feedback evidence.")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise FeedbackError("Feedback evidence must be a JSON object.")
    return value


def _candidate(workspace: Path, job: dict) -> Path:
    base = (workspace / "candidates").resolve()
    candidate_id = str(job.get("candidate_id") or "")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,96}", candidate_id):
        raise FeedbackError("Invalid candidate identity.")
    candidate = (base / candidate_id).resolve()
    if not candidate.is_relative_to(base) or candidate != Path(
        str(job.get("candidate_dir") or "")
    ).resolve():
        raise FeedbackError("Candidate is not owned by this transfer.")
    return candidate


def _pointer(candidate: Path, job_id: str) -> Path:
    return candidate / ("user-feedback-active-" + job_id + ".json")


def active_feedback(candidate: Path, job: dict) -> dict | None:
    """Return the immutable latest user comment only for this exact job."""
    job_id = str(job["job_id"])
    ptr = _pointer(candidate, job_id)
    if not ptr.is_file():
        return None
    pointer = _json(ptr)
    fid = str(pointer.get("feedback_id") or "")
    if (pointer.get("job_id") != job_id or
            pointer.get("candidate_id") != job.get("candidate_id") or
            ID.fullmatch(fid) is None):
        raise FeedbackError("Active feedback pointer does not match this job.")
    comment = _json(candidate / ("user-feedback-" + fid + ".json"))
    if (comment.get("kind") != "cutsceneai.studio.user_feedback"
            or comment.get("feedback_id") != fid
            or comment.get("job_id") != job_id
            or comment.get("candidate_id") != job["candidate_id"]):
        raise FeedbackError("User feedback identity mismatch.")
    return comment


def submit(workspace: Path, job: dict, message: str) -> dict[str, Any]:
    """Receive a user's correction. Native execution is controlled elsewhere."""
    job_id = str(job.get("job_id") or "")
    if ID.fullmatch(job_id) is None:
        raise FeedbackError("Invalid transfer job identity.")
    active = workspace / "active-job.json"
    if not active.is_file() or _json(active).get("job_id") != job_id:
        raise FeedbackError("Feedback must refer to the active transfer.")
    if job.get("ai_agents_enabled") is not True:
        raise FeedbackError("This transfer did not authorize AI corrections.")
    if job.get("status") in {"QUEUED", "RUNNING"}:
        raise FeedbackError("Wait until the native transfer finishes before requesting corrections.")
    if not isinstance(message, str):
        raise FeedbackError("A natural-language correction is required.")
    clean = message.strip()
    if not (4 <= len(clean) <= MAX_COMMENT) or any(
        (ord(c) < 32 and c not in "\n\t") for c in clean
    ):
        raise FeedbackError("Correction must be 4–1200 characters of readable text.")
    candidate = _candidate(workspace, job)
    if not candidate.is_dir():
        raise FeedbackError("Original candidate evidence no longer exists.")
    import studio_agent_graph
    state_file = candidate / ("agent-state-" + job_id + ".json")
    if state_file.is_file():
        graph_state = _json(state_file)
        if graph_state.get("status") not in studio_agent_graph.FINISHED:
            raise FeedbackError("The agent is still processing this transfer; retry after it finishes.")
    feedback_id = uuid.uuid4().hex
    record = {
        "kind": "cutsceneai.studio.user_feedback",
        "schema_version": "1",
        "feedback_id": feedback_id,
        "job_id": job_id,
        "candidate_id": job["candidate_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "message": clean,
        "execution_authorized": False,
        "native_fidelity_verified": False,
    }
    destination = candidate / ("user-feedback-" + feedback_id + ".json")
    with destination.open("x", encoding="utf-8") as output:
        json.dump(record, output, ensure_ascii=False, sort_keys=True)
        output.write("\n")
    # Atomic pointer update makes a comment visible only after its immutable
    # content is completely saved and uniquely bound to the active job.
    pointer = _pointer(candidate, job_id)
    tmp = pointer.with_suffix("." + uuid.uuid4().hex + ".tmp")
    try:
        tmp.write_text(json.dumps({
            "job_id": job_id, "candidate_id": job["candidate_id"],
            "feedback_id": feedback_id,
        }), encoding="utf-8")
        os.replace(tmp, pointer)
    finally:
        tmp.unlink(missing_ok=True)
    return {
        "status": "QUEUED_FOR_AGENT",
        "feedback_id": feedback_id,
        "message": clean,
        "fidelity_verified": False,
    }


def conversation(workspace: Path, job: dict | None) -> dict[str, Any]:
    if not job:
        return {"available": False, "messages": [], "agent_status": "NO_TRANSFER"}
    candidate = _candidate(workspace, job)
    if not candidate.is_dir():
        return {"available": False, "messages": [], "agent_status": "NO_CANDIDATE"}
    messages = []
    for path in candidate.glob("user-feedback-*.json"):
        if path.name.startswith("user-feedback-active-") or path.is_symlink():
            continue
        item = _json(path)
        if (item.get("kind") != "cutsceneai.studio.user_feedback"
                or item.get("job_id") != job.get("job_id")
                or item.get("candidate_id") != job.get("candidate_id")):
            continue
        messages.append({
            "feedback_id": item["feedback_id"],
            "message": item["message"],
            "created_at": item["created_at"],
        })
    messages.sort(key=lambda item: (item["created_at"], item["feedback_id"]))
    latest = active_feedback(candidate, job)
    state_path = candidate / ("agent-state-" + str(job["job_id"]) + ".json")
    state = _json(state_path) if state_path.is_file() else {}
    response = {}
    if latest and state.get("feedback_id") == latest["feedback_id"]:
        routing = state.get("intent_routing") or {}
        intent = routing.get("intent") or {}
        response = {
            "feedback_id": latest["feedback_id"],
            "status": state.get("status", "NEW"),
            "reasoning": str(state.get("reasoning") or routing.get("reason") or "")[:700],
            "failure": str(state.get("failure") or "")[:500],
            "interpreted_domains": [
                d for d in intent.get("domains", [])[:5]
                if isinstance(d, str)
            ],
            "capability_decision": str(routing.get("disposition") or ""),
            "repair_iterations": state.get("iterations", 0),
            "pending_native_repair": bool(state.get("pending_request")),
            "fidelity_verified": False,
        }
    return {
        "available": True,
        "messages": messages[-20:],
        "reply": response,
        "agent_status": state.get("status", "WAITING_FOR_AGENT"),
        "fidelity_verified": False,
    }
