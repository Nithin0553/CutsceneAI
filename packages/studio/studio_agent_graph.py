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
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, TypedDict

import agent_intent_router
from closed_loop_evaluation import redact_component_catalog

MAX_REPAIRS = 2
MAX_USER_COMMENT = 1200
ALLOWED_STRATEGIES = {"restore_source_albedo", "restore_constant_actor_offset", "report_only"}


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
    eligible_repair: bool
    issue_count: int
    issues: list[dict[str, Any]]
    component_adapter_catalog: list[dict[str, Any]]
    chosen_strategy: str
    reasoning: str
    history: list[dict[str, Any]]
    failure: str
    fidelity_verified: bool
    source_evidence_sha256: str
    feedback_id: str
    intent_routing: dict[str, Any]
    transform_candidate: dict[str, Any]


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


def _ced_policy() -> dict[str, Any]:
    """Compatibility-only taxonomy view for earlier research checks.

    Model prompts now use _ced_knowledge_for_agent instead of the flat list.
    """
    path = Path(__file__).resolve().parents[1] / (
        "contracts/dictionary/cutscene-elements-v0.2.json"
    )
    document = _json(path)
    categories = document.get("categories") or {}
    names = (
        "material", "texture", "shader", "animation", "character",
        "transform", "camera", "light", "environment", "event",
        "audio", "render", "scene", "relationship",
    )
    return {
        "ced_version": document.get("version"),
        "categories": {
            name: categories[name][:18] for name in names
            if isinstance(categories.get(name), list)
        },
    }


def _ced_knowledge_for_agent(workspace: Path, job: dict[str, Any]) -> dict[str, Any]:
    """Retrieve job-specific CED rules; do not dump the complete taxonomy.

    A missing source yields an explicit gap. It does not grant repair rights
    or replace the independently measured CineTwin/native audit.
    """
    source_file = job.get("csir")
    if not isinstance(source_file, str) or not source_file:
        return {"status": "SOURCE_SEMANTIC_EVIDENCE_UNAVAILABLE", "entries": []}
    import ced_agent_knowledge
    source = _json(Path(source_file))
    target_caps = job.get("native_capabilities")
    if not isinstance(target_caps, dict):
        target_caps = {}
    result = ced_agent_knowledge.retrieve(
        source, target_capabilities=target_caps,
        source_version=str(
            (source.get("source") if isinstance(source.get("source"), dict) else
             {}).get("engine_version") or ""
        ),
        target_version=str(job.get("target_engine_version") or ""),
        approved_store=workspace.parent / "ced-knowledge",
    )
    # Retrieval is advisory: all native permission checks run later.
    return {
        "status": "RETRIEVED_CED_EVIDENCE_UNVERIFIED",
        "knowledge_sha256": result["knowledge_sha256"],
        "source_ced_count": result["source_ced_count"],
        "entries": result["entries"][:12],
        "no_native_write_permission": True,
    }

def _approved_precedents(workspace: Path, job: dict[str, Any]) -> list[dict[str, Any]]:
    """Give the reasoning model *redacted* verified CED mapping precedents.

    Case lookup has no engine mutation permission. Candidate paths, source
    asset bytes and executable parameters never enter the LLM summary.
    """
    store = workspace / "learning" / "approved-cases"
    if not store.is_dir() or store.is_symlink():
        return []
    package = str(Path(__file__).resolve().parents[1] / "learning")
    if package not in sys.path:
        sys.path.insert(0, package)
    try:
        from case_memory import list_cases, read_json, suggest
        source = read_json(Path(str(job["csir"])))
        fingerprint = str(source.get("source", {}).get("project_fingerprint") or "")
        proposals = suggest(
            source, list_cases(store),
            exclude_project_fingerprint=fingerprint,
            limit=3,
        )
    except (OSError, ValueError, KeyError, TypeError):
        return []

    def identifier(value: Any) -> str:
        text = str(value or "")
        return text if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,95}", text) else ""

    precedents = []
    for item in proposals:
        labels = []
        for raw in item.get("candidate_resolutions", [])[:6]:
            if not isinstance(raw, dict):
                continue
            entry = {key: identifier(raw.get(key)) for key in
                     ("ced", "resolver", "outcome")}
            if all(entry.values()):
                labels.append(entry)
        if labels:
            precedents.append({
                "case_id": item.get("case_id"),
                "similarity": item.get("similarity"),
                "ced_mapping_labels": labels,
                "proposal_only": True,
                "can_execute_tools": False,
                "full_fidelity_verified": False,
            })
    return precedents



def _approved_ced_rulebook_precedents(workspace: Path, job: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose only redacted, QA-approved CED mapping identities to the agent.

    These are informative precedents. They grant no native execution authority
    and never include user source paths, rule parameters or evidence files.
    """
    store = workspace.parent / "ced-knowledge"
    if not store.exists():
        return []
    package = str(Path(__file__).resolve().parents[1] / "readiness")
    if package not in sys.path:
        sys.path.insert(0, package)
    from ced_rulebook import approved_rules

    try:
        rules = approved_rules(store)
        source = _json(Path(str(job["csir"])))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AgentError("QA-approved CED mapping book failed integrity review.") from exc
    known = set()
    for category in ("entities", "assets", "tracks"):
        for row in source.get(category, []):
            if not isinstance(row, dict):
                continue
            known.add(str(row.get("ced_type") or ""))
            for section in row.get("sections", []):
                if isinstance(section, dict):
                    known.add(str(section.get("ced_type") or ""))
    choices = []
    for rule in sorted(rules, key=lambda x: x["rule_id"]):
        if rule["ced"] not in known:
            continue
        choices.append({
            "ced": rule["ced"], "rule_id": rule["rule_id"],
            "resolver": rule["resolution"]["resolver"],
            "quality_gate": "QA_APPROVED_WITH_PER_JOB_PREFLIGHT",
            "no_automatic_native_permission": True,
        })
    return choices[:12]


def _model_reasoner(summary: dict[str, Any]) -> dict[str, str]:
    """Use the same local/cloud model policy as the conversion planning agent."""
    import studio_model_provider as provider
    response = provider.complete_json(
        task="cutsceneai_agent_choice",
        instructions=(
            "You are CutSceneAI's diagnostic repair agent. Analyze the bounded "
            "native CineTwin discrepancy, user feedback, installed adapters and "
            "retrieved CED knowledge. The knowledge base is advisory and does "
            "not grant engine write privileges. A user's observation is "
            "unverified until native readback confirms it. Choose only from "
            "the listed independently safe repair options. "
            "restore_source_albedo requires known Unity material provenance "
            "and measured Unreal fallback slots. "
            "restore_constant_actor_offset requires exact one-character "
            "source/target world-position evidence and independent native "
            "remeasurement. If evidence is insufficient or the discrepancy "
            "is outside an installed repair adapter, choose report_only. "
            "Never invent engine commands, source paths, executable code, "
            "new mapping rules, or claims of visual/skeletal parity."
        ),
        payload={"diagnostic_summary": summary},
        schema={
            "type": "object", "additionalProperties": False,
            "properties": {
                "strategy": {"type": "string", "enum": sorted(ALLOWED_STRATEGIES)},
                "reason": {"type": "string"},
            },
            "required": ["strategy", "reason"],
        },
    )
    answer = response.answer
    if (answer.get("strategy") not in ALLOWED_STRATEGIES
            or not isinstance(answer.get("reason"), str)
            or len(answer["reason"]) > 1200
            or set(answer) != {"strategy", "reason"}):
        raise AgentError("Model returned a malformed or unregistered repair strategy.")
    return {"strategy": answer["strategy"], "reason": answer["reason"]}

def _current_user_feedback(candidate: Path, job: dict[str, Any]) -> dict[str, Any] | None:
    """Read an immutable, job-bound user correction without authorizing execution."""
    tools_path = str(Path(__file__).resolve().parents[2] / "tools")
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)
    import studio_agent_feedback
    return studio_agent_feedback.active_feedback(candidate, job)


def _material_feedback_scope(message: str) -> bool:
    """Conservative executable guard for the only installed repair strategy.

    Unknown user language is still sent for diagnosis but cannot trigger an
    unrelated material edit merely because the model suggests it.
    """
    return bool(re.search(
        r"\b(material|materials|texture|textures|albedo|base.colou?r|"
        r"material.slot|missing.texture|pink.material|checkerboard.texture)\b",
        message.casefold(),
    ))


def build_graph(workspace: Path, job: dict[str, Any],
                reasoner: Callable[[dict[str, Any]], dict[str, str]] | None = None):
    """Return an actual compiled LangGraph StateGraph with conditional retry loop."""
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise AgentError('LangGraph missing: python -m pip install "langgraph>=1.0,<2".') from exc

    candidate = _candidate(workspace, job)
    job_id = str(job["job_id"])
    choose = reasoner or _model_reasoner
    comment = _current_user_feedback(candidate, job)
    user_message = str(comment.get("message") or "") if comment else ""
    relevant_material_request = not comment or _material_feedback_scope(user_message)

    def inspect(state: AgentState) -> dict[str, Any]:
        if state.get("pending_request"):
            return {"status": "CHECKING_EDITOR_RECEIPT"}
        try:
            feedback, visual = _evidence(candidate, job_id)
        except AgentError:
            # A failed native conversion may never produce a CineTwin report.
            # The agent still diagnoses the stage, without receiving raw
            # project files or attempting to replay a partially mutated level.
            if job.get("generation_status") == "GENERATED_UNVERIFIED":
                raise
            feedback, visual = ({
                "kind": "cutsceneai.studio.closed_loop_evaluation",
                "issues": [{
                    "category": "NATIVE_TRANSFER_FAILED_NO_PARITY",
                    "status": str(job.get("status") or "FAILED")[:100],
                    "stage": str(job.get("generation_status") or "NOT_GENERATED")[:100],
                }],
            }, {})
        count = _valid_fallback(visual)
        transform_proof = None
        if (comment and agent_intent_router.recognize(user_message)["domains"] == ["transform"]):
            import agent_transform_evidence
            try:
                native_report = agent_transform_evidence.source_bound_report(job, candidate)
                named = agent_transform_evidence.requested_character_correction(
                    user_message, native_report
                )
                if named:
                    transform_proof = agent_transform_evidence.review(native_report, named)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                transform_proof = {
                    "eligible": False,
                    "reason": "Missing trusted native evidence: " + str(exc)[:250],
                }
        issues = feedback.get("issues") or []
        if not isinstance(issues, list):
            raise AgentError("Invalid independent issue list.")
        issues = list(issues)
        try:
            routing = agent_intent_router.route(
                user_message if comment else None,
                generation_complete=job.get("generation_status") == "GENERATED_UNVERIFIED",
                native_material_fallback_slots=count,
                source_albedo_provenance=_source_materials(candidate),
                completed_repairs=state.get("iterations", 0),
                repair_budget=MAX_REPAIRS,
                independent_issues=issues,
                transform_repair_evidence=transform_proof,
                adapter_catalog=feedback.get("component_adapter_catalog"),
                fallback_observation_scope=(
                    "character" if "character_material_slots_engine_default" in visual
                    else "global"
                ),
            )
        except agent_intent_router.IntentError as exc:
            raise AgentError("Agent feedback routing blocked: " + str(exc)) from exc
        if transform_proof and not transform_proof.get("eligible"):
            routing["reason"] += " Translation repair blocked: " + str(
                transform_proof.get("reason") or "insufficient measurements"
            )[:260]
        if comment:
            # A user's observation is valuable, but is not an independently
            # measured CineTwin mismatch until native evidence confirms it.
            issues.append({
                "category": "USER_REPORTED_UNVERIFIED_DISCREPANCY",
                "comment": user_message[:MAX_USER_COMMENT],
                "verified": False,
            })
        eligible = bool(
            job.get("generation_status") == "GENERATED_UNVERIFIED"
            and job.get("automatic_setup") and _source_materials(candidate)
            and count > 0 and state.get("iterations", 0) < MAX_REPAIRS
        )
        base = {
            "issues": issues[:100], "issue_count": len(issues),
            "component_adapter_catalog": redact_component_catalog(
                feedback.get("component_adapter_catalog")
            ),
            "last_fallback": count,
            "baseline_fallback": state.get("baseline_fallback", count),
            "source_evidence_sha256": hashlib.sha256(json.dumps(
                feedback, sort_keys=True).encode()).hexdigest(),
            "eligible_repair": eligible,
            "intent_routing": routing,
            "transform_candidate": transform_proof or {},
        }
        if not issues:
            return {**base, "status": "NO_DETECTED_GAPS_FIDELITY_UNVERIFIED"}
        # The model may explain all incomplete CED/CineTwin domains, but the
        # only actionable strategy remains source-backed material restoration.
        # An unsupported issue is never converted into a guessed engine edit.
        if state.get("iterations", 0) >= MAX_REPAIRS:
            return {**base, "status": "MAX_SAFE_REPAIRS_REACHED"}
        return {**base, "status": "REASONING"}

    def route_inspect(state: AgentState) -> str:
        if state["status"] == "CHECKING_EDITOR_RECEIPT":
            return "observe"
        if state["status"] == "REASONING":
            return "reason"
        return END

    def reason(state: AgentState) -> dict[str, Any]:
        summary = {
            "ced_knowledge": _ced_knowledge_for_agent(workspace, job),
            "component_adapter_catalog": state.get("component_adapter_catalog", [])[:32],
            "unreal_character_fallback_slots": state["last_fallback"],
            "source_guid_backed_albedo": _source_materials(candidate),
            "safe_strategies": state["intent_routing"]["safe_strategies"],
            "interpreted_request": state["intent_routing"]["intent"],
            "capability_decision": state["intent_routing"]["disposition"],
            "capability_evidence": state["intent_routing"]["reason"],
            "registered_adapters_informational":
                state["intent_routing"]["registered_adapters_informational"],
            "user_feedback": user_message[:MAX_USER_COMMENT] if comment else "",
            "user_feedback_is_unverified": bool(comment),
            "remaining_repairs": MAX_REPAIRS - state.get("iterations", 0),
            "issues": state["issues"][:30],
            "verified_ced_precedents": _approved_precedents(workspace, job),
            "approved_ced_rulebook_precedents": _approved_ced_rulebook_precedents(workspace, job),
            "verified_transform_candidate": state.get("transform_candidate", {}),
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
        if strategy not in state["intent_routing"]["safe_strategies"]:
            return {"status": "REJECTED_UNSUPPORTED_STRATEGY",
                    "failure": "LLM proposal is not in the evidence-backed capability route.",
                    "chosen_strategy": "report_only"}
        if strategy == "restore_constant_actor_offset" and not (
            comment and state.get("transform_candidate", {}).get("eligible")
            and "restore_constant_actor_offset" in
            state["intent_routing"]["safe_strategies"]
        ):
            return {"status": "REJECTED_UNSUPPORTED_STRATEGY",
                    "failure": "Transform proposal was not independently authorized.",
                    "chosen_strategy": "report_only"}
        if strategy == "restore_source_albedo" and not (
            state.get("eligible_repair") and relevant_material_request and
            state["last_fallback"] > 0 and _source_materials(candidate)
        ):
            return {"status": "REJECTED_UNSUPPORTED_STRATEGY",
                    "failure": "LLM proposal failed deterministic provenance guard.",
                    "chosen_strategy": "report_only"}
        return {
            "status": "REPAIR_SELECTED" if strategy != "report_only"
                      else "UNRESOLVED_NO_SAFE_STRATEGY",
            "chosen_strategy": strategy,
            "reasoning": (
                state["intent_routing"]["reason"] + " " + message
                if comment and strategy == "report_only" else message
            ),
        }

    def dispatch(state: AgentState) -> dict[str, Any]:
        strategy = state.get("chosen_strategy")
        if strategy not in {"restore_source_albedo", "restore_constant_actor_offset"}:
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
            "strategy": strategy,
            "iteration": state.get("iterations", 0) + 1,
            "baseline_fallback": state.get("last_fallback", 0),
        }
        if strategy == "restore_constant_actor_offset":
            proof = state.get("transform_candidate") or {}
            if not proof.get("eligible") or not state.get("feedback_id"):
                raise AgentError("Missing user-authorized actor translation proof.")
            origin = Path(job["diagnostic_file"]).resolve()
            if origin.parent != candidate or not origin.is_file():
                raise AgentError("Original native transform evidence is missing.")
            request.update({
                "target_entity": proof["entity"],
                "feedback_id": state["feedback_id"],
                "original_report_sha256": hashlib.sha256(origin.read_bytes()).hexdigest(),
            })
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
        if state.get("chosen_strategy") == "restore_constant_actor_offset":
            expected_entity = (state.get("transform_candidate") or {}).get("entity")
            actor_after = result.get("actor_error_after_cm")
            root_after = result.get("root_error_after_cm")
            verified = bool(
                result.get("status") == "TRANSFORM_OFFSET_SAVED_AND_REAUDITED"
                and result.get("target_entity") == expected_entity
                and all(
                    type(v) in (float, int) and math.isfinite(v)
                    and 0 <= v <= 2.0
                    for v in (actor_after, root_after)
                )
            )
            entry = {
                "request_id": request_id, "strategy": "restore_constant_actor_offset",
                "status": str(result.get("status") or "UNKNOWN"),
                "target_entity": result.get("target_entity"),
                "actor_error_after_cm": actor_after,
                "root_error_after_cm": root_after,
            }
            common = {
                "history": (state.get("history") or []) + [entry],
                "pending_request": "",
                "iterations": state.get("iterations", 0) + 1,
            }
            if not verified:
                return {**common, "status": "REPAIR_FAILED_OR_INCOMPLETE",
                        "failure": str(result.get("error") or
                                       "Actor/root native verification did not pass")[:500]}
            return {
                **common,
                "status": "ACTOR_TRANSLATION_IMPROVED_OTHER_DOMAINS_UNVERIFIED",
                "reasoning": (
                    str(state.get("reasoning") or "")[:350]
                    + f" Native actor/root errors after translation: "
                    + f"{actor_after:.3f} cm / {root_after:.3f} cm. "
                    + "Reopened-project persistence and full parity remain unverified."
                ),
            }
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
    "ACTOR_TRANSLATION_IMPROVED_OTHER_DOMAINS_UNVERIFIED",
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
    comment = _current_user_feedback(candidate, job)
    if comment and state.get("feedback_id") != comment["feedback_id"]:
        if state.get("pending_request"):
            raise AgentError("Cannot restart a correction while a native repair is pending.")
        # New user feedback starts a fresh diagnosis for the same generated
        # candidate, but NEVER resets the global repair budget or history.
        state = {
            **state,
            "feedback_id": comment["feedback_id"],
            "pending_request": "",
            "status": "NEW",
            "reasoning": "",
            "failure": "",
        }
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
