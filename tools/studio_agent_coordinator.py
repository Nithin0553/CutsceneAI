"""Local Studio LangGraph lifecycle; never runs in the Unreal Python interpreter."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_RUN_LOCK = threading.Lock()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def status(workspace: Path) -> dict[str, Any]:
    active = workspace / "active-job.json"
    if not active.is_file():
        return {"status": "NOT_STARTED", "enabled": False}
    job_id = str(_load(active).get("job_id") or "")
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        return {"status": "INVALID_JOB", "enabled": False}
    job_file = workspace / "jobs" / (job_id + ".json")
    if not job_file.is_file():
        return {"status": "INVALID_JOB", "enabled": False}
    job = _load(job_file)
    if job.get("ai_agents_enabled") is not True:
        return {"status": "DISABLED", "enabled": False}
    candidate = (workspace / "candidates" / str(job.get("candidate_id") or "")).resolve()
    if (candidate != Path(job.get("candidate_dir") or "").resolve()
            or not candidate.is_relative_to((workspace / "candidates").resolve())):
        return {"status": "INVALID_CANDIDATE", "enabled": True}
    report = candidate / ("agent-state-" + job_id + ".json")
    if not report.is_file():
        return {"status": "WAITING_FOR_STANDARD_CONVERSION", "enabled": True}
    state = _load(report)
    if state.get("job_id") != job_id or state.get("candidate_id") != job.get("candidate_id"):
        return {"status": "INVALID_STATE", "enabled": True}
    return {
        "enabled": True, "status": state.get("status"),
        "iterations": state.get("iterations", 0),
        "history": state.get("history", [])[:2],
        "failure": state.get("failure", ""),
        "reasoning": state.get("reasoning", ""),
        "issue_count": state.get("issue_count"),
        "fidelity_verified": False,
    }


def advance(workspace: Path, *, reasoner=None) -> dict[str, Any]:
    """Progress one consented active job; safely resume after a server restart."""
    if not _RUN_LOCK.acquire(blocking=False):
        return status(workspace)
    try:
        active = workspace / "active-job.json"
        if not active.is_file():
            return {"status": "NOT_STARTED", "enabled": False}
        job_id = str(_load(active).get("job_id") or "")
        if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
            return {"status": "INVALID_JOB", "enabled": False}
        path = workspace / "jobs" / (job_id + ".json")
        if not path.is_file():
            return {"status": "INVALID_JOB", "enabled": False}
        job = _load(path)
        if job.get("ai_agents_enabled") is not True:
            return {"status": "DISABLED", "enabled": False}
        if job.get("status") in {"QUEUED", "RUNNING"}:
            return {"status": "WAITING_FOR_STANDARD_CONVERSION", "enabled": True}
        from studio_agent_graph import run_once
        try:
            run_once(workspace, job, reasoner=reasoner)
        except Exception as exc:
            # Agent-only runtime errors are never propagated into or allowed
            # to change the already generated cutscene's native job status.
            return {"status": "AGENT_RUNTIME_ERROR", "enabled": True,
                    "failure": str(exc)[:500], "fidelity_verified": False}
        return status(workspace)
    finally:
        _RUN_LOCK.release()


def start_daemon(workspace: Path, *, interval: float = 2.0) -> threading.Event:
    """Server-owned daemon; the active-job record is the durable queue."""
    stop = threading.Event()

    def run() -> None:
        while not stop.is_set():
            try:
                advance(workspace)
            except Exception:
                # Only active-job opt-in is ever examined. Status reads remain
                # safe even if one workspace file is partially corrupted.
                pass
            stop.wait(interval)

    threading.Thread(target=run, name="cutsceneai-langgraph", daemon=True).start()
    return stop
