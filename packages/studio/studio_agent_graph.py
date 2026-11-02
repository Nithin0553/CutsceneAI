"""Opt-in LangGraph orchestrator: evidence -> reason -> guarded repair -> verify.

Runs in the LOCAL Studio Python service, never Unreal's embedded Python runtime.
Only whitelisted source-backed repair requests cross the editor file queue.
The LLM only chooses a strategy from the already vetted set; it cannot write
Python, arbitrary files, modify audio, or declare cinematic fidelity.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from pathlib import Path
from typing import Any, Callable, TypedDict

MAX_REPAIRS = 2
ALLOWED_STRATEGIES = {"restore_source_albedo", "report_only"}


class AgentError(RuntimeError):
    pass


class AgentState(TypedDict, total=False):
    job_id: str
    candidate_id: str
    status: str
    iterations: int
    pending_request: str
    baseline_fallback: int
    last_fallback: int
    issue_count: int
    issues: list[dict[str, Any]]
    chosen_strategy: str
    reasoning: str
    history: list[dict[str, Any]]
    failure: str
    fidelity_verified: bool
    source_evidence_sha256: str


def _json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise AgentError("Expected an object evidence file.")
    return data


def _atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _candidate(workspace: Path, job: dict[str, Any]) -> Path:
    candidate = (workspace / "candidates" / str(job["candidate_id"])).resolve()
    if candidate != Path(job["candidate_dir"]).resolve() or not candidate.is_relative_to(
        (workspace / "candidates").resolve()
    ):
        raise AgentError("Job candidate path or identity mismatch.")
    return candidate


def _evidence(candidate: Path, job_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    feedback_file = candidate / ("closed-loop-evaluation-" + job_id + ".json")
    if not feedback_file.is_file():
        raise AgentError("Independent CineTwin/visual evaluation is missing.")
    feedback = _json(feedback_file)
    if feedback.get("kind") != "cutsceneai.studio.closed_loop_evaluation":
        raise AgentError("Unexpected source-to-target evaluation.")
    # Any later observed visual audit supersedes earlier material counts.
    audits = sorted(
        (p for p in candidate.glob("visual-audit-" + job_id + "-*.json")
         if p.resolve().parent == candidate),
        key=lambda p: p.stat().st_mtime_ns, reverse=True,
    )
    visual = _json(audits[0]) if audits else {}
    return feedback, visual


def _valid_fallback(visual: dict[str, Any]) -> int:
    raw = visual.get("character_material_slots_engine_default",
                     visual.get("material_slots_engine_default", 0))
    if type(raw) is not int or raw < 0:
        raise AgentError("Invalid visual audit material count.")
    return raw


def _source_materials(candidate: Path) -> bool:
    manifest = candidate / "automatic-setup.json"
    if not manifest.is_file():
        return False
    document = _json(manifest)
    return bool(document.get("source_albedo_material_candidates"))


def _model_reasoner(summary: dict[str, Any]) -> dict[str, str]:
    if not os.environ.get("OPENAI_API_KEY"):
        raise AgentError("OPENAI_API_KEY is not configured in the local Studio process.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AgentError('Install pip install -e ".[agents]" in the Studio Python environment.') from exc
    # Only the diagnostic summary is sent, never source asset bytes, paths,
    # API keys, user scripts or arbitrary file content.
    response = OpenAI(timeout=25.0, max_retries=0).responses.create(
        model=os.environ.get("CUTSCENEAI_AGENT_MODEL", "gpt-5-mini"),
        instructions=(
            "You are a diagnostic repair selector in CutSceneAI Studio. "
            "Return only JSON. Choose strategy restore_source_albedo ONLY if "
            "that strategy is eligible from independently verified source GUID "
            "texture provenance and current Unreal character fallback slots; "
            "otherwise choose report_only. Do not create new commands or claim "
            "full visual/animation/camera/audio parity. The deterministic "
            "executor independently validates every action."
        ),
        input="Evaluate this bounded CED/CineTwin evidence and output JSON: " +
              json.dumps(summary, sort_keys=True)[:12000],
        text={"format": {"type": "json_schema", "name": "cutsceneai_agent_choice",
                         "strict": True, "schema": {
                             "type": "object", "additionalProperties": False,
                             "properties": {
                                 "strategy": {"type": "string", "enum": sorted(ALLOWED_STRATEGIES)},
                                 "reason": {"type": "string"},
                             },
                             "required": ["strategy", "reason"],
                         }}},
    )
    result = json.loads(response.output_text)
    return {"strategy": result["strategy"], "reason": result["reason"]}


def build_graph(workspace: Path, job: dict[str, Any],
                reasoner: Callable[[dict[str, Any]], dict[str, str]] | None = None):
    """Return an actual compiled LangGraph StateGraph with conditional retry loop."""
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise AgentError('LangGraph is not installed: pip install -e ".[agents]".') from exc

    candidate = _candidate(workspace, job)
    job_id = str(job["job_id"])
    choose = reasoner or _model_reasoner

    def inspect(state: AgentState) -> dict[str, Any]:
        if state.get("pending_request"):
            return {"status": "CHECKING_EDITOR_RECEIPT"}
        feedback, visual = _evidence(candidate, job_id)
        count = _valid_fallback(visual)
        issues = feedback.get("issues") or []
        if not isinstance(issues, list):
            raise AgentError("Invalid independent issue list.")
        eligible = bool(
            job.get("generation_status") == "GENERATED_UNVERIFIED"
            and job.get("automatic_setup") and _source_materials(candidate)
            and count > 0 and state.get("iterations", 0) < MAX_REPAIRS
        )
        base = {
            "issues": issues[:100], "issue_count": len(issues),
            "last_fallback": count,
            "baseline_fallback": state.get("baseline_fallback", count),
            "source_evidence_sha256": hashlib.sha256(json.dumps(
                feedback, sort_keys=True).encode()).hexdigest(),
        }
        if not issues:
            return {**base, "status": "NO_DETECTED_GAPS_FIDELITY_UNVERIFIED"}
        if not eligible:
            return {**base, "status": "UNRESOLVED_NO_SAFE_STRATEGY"}
        return {**base, "status": "REASONING"}

    def route_inspect(state: AgentState) -> str:
        if state["status"] == "CHECKING_EDITOR_RECEIPT":
            return "observe"
        if state["status"] == "REASONING":
            return "reason"
        return END

    def reason(state: AgentState) -> dict[str, Any]:
        summary = {
            "ced_domains": ["material", "rendering", "animation", "camera", "lighting",
                            "hierarchy", "audio", "events"],
            "unreal_character_fallback_slots": state["last_fallback"],
            "source_guid_backed_albedo": _source_materials(candidate),
            "safe_strategies": sorted(ALLOWED_STRATEGIES),
            "remaining_repairs": MAX_REPAIRS - state.get("iterations", 0),
            "issues": state["issues"][:30],
        }
        try:
            suggestion = choose(summary)
            if not isinstance(suggestion, dict) or suggestion.get("strategy") not in ALLOWED_STRATEGIES:
                raise AgentError("Agent suggested an unsupported repair strategy.")
            strategy = suggestion["strategy"]
            message = str(suggestion.get("reason") or "")[:700]
        except Exception as exc:
            return {"status": "AGENT_REASONING_UNAVAILABLE",
                    "failure": str(exc)[:500], "chosen_strategy": "report_only"}
        if strategy == "restore_source_albedo" and not (
            state["last_fallback"] > 0 and _source_materials(candidate)
        ):
            return {"status": "REJECTED_UNSUPPORTED_STRATEGY",
                    "failure": "LLM proposal failed deterministic provenance guard.",
                    "chosen_strategy": "report_only"}
        return {
            "status": "REPAIR_SELECTED" if strategy == "restore_source_albedo"
                      else "UNRESOLVED_NO_SAFE_STRATEGY",
            "chosen_strategy": strategy, "reasoning": message,
        }

    def dispatch(state: AgentState) -> dict[str, Any]:
        if state.get("chosen_strategy") != "restore_source_albedo":
            return {"status": "UNRESOLVED_NO_SAFE_STRATEGY"}
        request_id = uuid.uuid4().hex
        request = {
            "kind": "cutsceneai.studio.agent_repair_request",
            "schema_version": "1",
            "job_id": job_id, "candidate_id": job["candidate_id"],
            "sequence_path": job["sequence_path"],
            "expected_project": job["expected_project"],
            "expected_level": job["expected_level"],
            "request_id": request_id,
            "strategy": "restore_source_albedo",
            "iteration": state.get("iterations", 0) + 1,
            "baseline_fallback": state.get("last_fallback", 0),
        }
        path = candidate / ("agent-request-" + request_id + ".json")
        with path.open("x", encoding="utf-8") as stream:
            json.dump(request, stream, sort_keys=True, indent=2)
        return {"pending_request": request_id, "status": "WAITING_FOR_UNREAL_AGENT_REPAIR"}

    def observe(state: AgentState) -> dict[str, Any]:
        request_id = state.get("pending_request", "")
        if not request_id or len(request_id) != 32 or any(c not in "0123456789abcdef" for c in request_id):
            raise AgentError("Unexpected agent request ID.")
        receipt = candidate / ("agent-receipt-" + request_id + ".json")
        if not receipt.is_file():
            return {"status": "WAITING_FOR_UNREAL_AGENT_REPAIR"}
        result = _json(receipt)
        if (result.get("kind") != "cutsceneai.studio.agent_repair_receipt"
                or result.get("request_id") != request_id
                or result.get("job_id") != job_id
                or result.get("candidate_id") != job["candidate_id"]):
            raise AgentError("Stale or mismatched Unreal repair receipt.")
        old_count = state.get("last_fallback", 0)
        new_count = result.get("fallback_after")
        if type(new_count) is not int or new_count < 0:
            raise AgentError("Invalid native re-audit count.")
        entry = {
            "request_id": request_id, "strategy": "restore_source_albedo",
            "status": str(result.get("status", "UNKNOWN")),
            "fallback_before": old_count, "fallback_after": new_count,
            "changes": result.get("changes", 0),
        }
        history = (state.get("history") or []) + [entry]
        common = {
            "history": history,
            "pending_request": "",
            "last_fallback": new_count,
            "iterations": state.get("iterations", 0) + 1,
        }
        # Never loop after zero improvement, failed save or malformed evidence.
        if result.get("status") != "REPAIR_SAVED_AND_REAUDITED":
            return {**common, "status": "REPAIR_FAILED_OR_INCOMPLETE",
                    "failure": str(result.get("error", "Repair did not persist"))[:500]}
        if new_count >= old_count:
            return {**common, "status": "STOPPED_NO_MEASURABLE_PROGRESS"}
        # The original closed-loop report is immutable; we can only claim the
        # improved material slots, never wider visual parity.
        if new_count == 0:
            return {**common, "status": "MATERIAL_FALLBACK_RESOLVED_OTHER_DOMAINS_UNVERIFIED"}
        if common["iterations"] >= MAX_REPAIRS:
            return {**common, "status": "MAX_SAFE_REPAIRS_REACHED"}
        return {**common, "status": "RECHECK_FOR_MORE_REPAIRS"}

    graph = StateGraph(AgentState)
    graph.add_node("inspect", inspect)
    graph.add_node("reason", reason)
    graph.add_node("dispatch", dispatch)
    graph.add_node("observe", observe)
    graph.add_edge(START, "inspect")
    graph.add_conditional_edges("inspect", route_inspect,
                                {"reason": "reason", "observe": "observe", END: END})
    graph.add_conditional_edges("reason", lambda s: "dispatch" if
                                s["status"] == "REPAIR_SELECTED" else END,
                                {"dispatch": "dispatch", END: END})
    graph.add_edge("dispatch", END)
    graph.add_conditional_edges("observe", lambda s: "inspect" if
                                s["status"] == "RECHECK_FOR_MORE_REPAIRS" else END,
                                {"inspect": "inspect", END: END})
    return graph.compile()


FINISHED = {
    "NO_DETECTED_GAPS_FIDELITY_UNVERIFIED", "UNRESOLVED_NO_SAFE_STRATEGY",
    "AGENT_REASONING_UNAVAILABLE", "REJECTED_UNSUPPORTED_STRATEGY",
    "REPAIR_FAILED_OR_INCOMPLETE", "STOPPED_NO_MEASURABLE_PROGRESS",
    "MATERIAL_FALLBACK_RESOLVED_OTHER_DOMAINS_UNVERIFIED", "MAX_SAFE_REPAIRS_REACHED",
    "EVIDENCE_UNAVAILABLE",
}


def run_once(workspace: Path, job: dict[str, Any],
             reasoner: Callable[[dict[str, Any]], dict[str, str]] | None = None) -> dict[str, Any]:
    """Advance/resume one authorized job. Idempotent while awaiting Unreal."""
    if job.get("ai_agents_enabled") is not True:
        return {"status": "DISABLED", "fidelity_verified": False}
    candidate = _candidate(workspace, job)
    location = candidate / ("agent-state-" + job["job_id"] + ".json")
    state = _json(location) if location.is_file() else {
        "job_id": job["job_id"], "candidate_id": job["candidate_id"],
        "iterations": 0, "history": [], "pending_request": "",
        "status": "NEW", "fidelity_verified": False,
    }
    if state["job_id"] != job["job_id"] or state["candidate_id"] != job["candidate_id"]:
        raise AgentError("Agent state identity mismatch.")
    if state.get("status") in FINISHED:
        return state
    if job.get("status") in {"RUNNING", "QUEUED"}:
        return {**state, "status": "WAITING_FOR_STANDARD_CONVERSION"}
    try:
        new_state = build_graph(workspace, job, reasoner).invoke(state, config={"recursion_limit": 12})
    except AgentError as exc:
        new_state = {**state, "status": "EVIDENCE_UNAVAILABLE",
                     "failure": str(exc)[:500], "fidelity_verified": False}
    new_state["fidelity_verified"] = False
    _atomic(location, new_state)
    return new_state
