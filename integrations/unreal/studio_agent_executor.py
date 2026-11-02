"""Guarded Unreal editor adapter for optional host LangGraph repair requests.

No arbitrary code execution. One exact source-backed material restoration per
request, editor thread only, bounded to two receipts per generated job.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def execute(api: Any, workspace: Path, job: dict[str, Any],
            request: dict[str, Any], *, project: str, level: str) -> dict[str, Any]:
    candidate = (workspace / "candidates" / str(job["candidate_id"])).resolve()
    if candidate != Path(job["candidate_dir"]).resolve() or not candidate.is_relative_to(
        (workspace / "candidates").resolve()
    ):
        raise ValueError("Unsafe agent candidate path.")
    if (job.get("ai_agents_enabled") is not True
            or job.get("generation_status") != "GENERATED_UNVERIFIED"
            or not job.get("automatic_setup")
            or request.get("kind") != "cutsceneai.studio.agent_repair_request"
            or request.get("schema_version") != "1"
            or request.get("job_id") != job["job_id"]
            or request.get("candidate_id") != job["candidate_id"]
            or request.get("strategy") != "restore_source_albedo"
            or request.get("sequence_path") != job["sequence_path"]
            or request.get("expected_project") != job["expected_project"]
            or request.get("expected_level") != job["expected_level"]):
        raise ValueError("Agent action not authorized by this job.")
    if (os.path.normcase(str(Path(project).resolve())) !=
            os.path.normcase(str(Path(job["expected_project"]).resolve())) or
            level != job["expected_level"]):
        raise ValueError("Agent request editor identity mismatch.")
    if not api.EditorAssetLibrary.does_asset_exist(job["sequence_path"]):
        raise ValueError("Generated target sequence missing.")
    active = _load(workspace / "active-job.json")
    if active.get("job_id") != job["job_id"]:
        raise ValueError("Agent request refers to inactive job.")
    if len(list(candidate.glob("agent-receipt-*.json"))) >= 2:
        raise ValueError("Exceeded two guarded repair receipts.")
    import studio_visual_audit
    before = studio_visual_audit.audit_latest(workspace, api=api)
    old_count = before.get("character_material_slots_engine_default")
    if type(old_count) is not int or old_count != request.get("baseline_fallback"):
        raise ValueError("Stale native visual baseline; no repair attempted.")
    setup_path = Path(job.get("setup_receipt_file") or "").resolve()
    if setup_path.parent != candidate or not setup_path.is_file():
        raise ValueError("Source-provenanced setup receipt unavailable.")
    import studio_visual_repair
    outcome = studio_visual_repair.attempt(job, _load(setup_path), api)
    if outcome.get("changed", 0):
        import studio_auto_scene
        studio_auto_scene._save_level(api, job["expected_level"])
    after = studio_visual_audit.audit_latest(workspace, api=api)
    count = after.get("character_material_slots_engine_default")
    if type(count) is not int:
        raise ValueError("Fresh character material count missing.")
    return {"status": "REPAIR_SAVED_AND_REAUDITED", "changes": outcome.get("changed", 0),
            "fallback_before": old_count, "fallback_after": count,
            "visual_audit_status": after.get("status")}


def service_one(api: Any, workspace: Path, *, project: str, level: str,
                save) -> bool:
    """Consume a single valid candidate-bound request, never replay receipts."""
    active_path = workspace / "active-job.json"
    if not active_path.is_file():
        return False
    active = _load(active_path)
    job_id = str(active.get("job_id") or "")
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        return False
    job_path = workspace / "jobs" / (job_id + ".json")
    if not job_path.is_file():
        return False
    job = _load(job_path)
    if job.get("ai_agents_enabled") is not True or job.get("status") in ("QUEUED", "RUNNING"):
        return False
    candidate = (workspace / "candidates" / str(job.get("candidate_id") or "")).resolve()
    if candidate != Path(job.get("candidate_dir") or "").resolve() or not candidate.is_relative_to(
        (workspace / "candidates").resolve()
    ):
        return False
    for path in sorted(candidate.glob("agent-request-*.json")):
        if not path.is_file() or path.resolve().parent != candidate:
            continue
        request_id = path.name.removeprefix("agent-request-").removesuffix(".json")
        if len(request_id) != 32 or any(c not in "0123456789abcdef" for c in request_id):
            continue
        receipt_path = candidate / ("agent-receipt-" + request_id + ".json")
        if receipt_path.exists():
            continue
        # The host writes the request file before persisting its graph state.
        # Ignore uncommitted/orphaned requests: an editor must never execute
        # a command that LangGraph cannot subsequently verify or resume.
        state_path = candidate / ("agent-state-" + job_id + ".json")
        if not state_path.is_file():
            continue
        try:
            committed = _load(state_path)
        except (ValueError, OSError, json.JSONDecodeError):
            continue
        if (committed.get("job_id") != job_id
                or committed.get("candidate_id") != job["candidate_id"]
                or committed.get("pending_request") != request_id
                or committed.get("status") != "WAITING_FOR_UNREAL_AGENT_REPAIR"):
            continue
        claim_path = candidate / ("agent-claim-" + request_id + ".json")
        request = None
        try:
            request = _load(path)
            if request.get("request_id") != request_id:
                raise ValueError("Agent request file identity mismatch.")
            if claim_path.exists():
                # Unreal may have crashed after modifying actors but before
                # persisting the receipt. Replaying would double-apply a
                # potentially non-idempotent repair. Require manual inspection.
                raise ValueError(
                    "Interrupted prior repair: no automatic replay; inspect staged editor assets."
                )
            # Durable write-ahead claim occurs BEFORE any Unreal mutation.
            # Existing claims are never replaced even on recovery.
            with claim_path.open("x", encoding="utf-8") as handle:
                json.dump({
                    "kind": "cutsceneai.studio.agent_repair_claim",
                    "request_id": request_id,
                    "job_id": job_id,
                    "candidate_id": job["candidate_id"],
                }, handle, sort_keys=True)
                handle.write("\n")
            result = execute(api, workspace, job, request, project=project, level=level)
        except Exception as exc:
            result = {
                "status": "REPAIR_FAILED_OR_BLOCKED", "changes": 0,
                "error": str(exc)[:500],
                "fallback_after": request.get("baseline_fallback", 0) if
                isinstance(request, dict) else 0,
            }
            api.log_warning("[CutSceneAI Studio] Agent repair blocked: " + str(exc))
        save(receipt_path, {"kind": "cutsceneai.studio.agent_repair_receipt",
                            "request_id": request_id, "job_id": job_id,
                            "candidate_id": job["candidate_id"], **result})
        return True
    return False
