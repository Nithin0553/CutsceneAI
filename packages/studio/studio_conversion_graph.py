"""LangGraph-controlled pre-transfer agent: ground, decide, validate, retry.

Autopilot manages durable editor communications and job locking; this graph
owns the reasoning/alternative-selection loop. AI may choose *only* already
registered actions. It cannot execute a native tool or declare fidelity.
"""
from __future__ import annotations

from typing import Any, Callable, TypedDict

MAX_PLANNING_ATTEMPTS = 2


class ConversionAgentError(ValueError):
    pass


class ConversionState(TypedDict, total=False):
    evidence: dict[str, Any]
    result: dict[str, Any]
    attempts: int
    error: str
    status: str


def _validate(evidence: dict[str, Any], answer: Any) -> dict[str, Any]:
    if not isinstance(answer, dict):
        raise ConversionAgentError("AI conversion decision must be structured JSON.")
    allowed_fields = {
        "strategy", "reason", "animation_choice_id",
        "_provider_response_id", "_provider_name", "_provider_model",
        "_provider_response_sha256",
    }
    if set(answer) - allowed_fields:
        raise ConversionAgentError("AI returned unregistered conversion data.")
    strategy = answer.get("strategy")
    if strategy not in {"native_source", "source_materials", "visual_activation_partial"}:
        raise ConversionAgentError("AI returned an unregistered conversion strategy.")
    if strategy not in evidence.get("allowed_strategies", []):
        raise ConversionAgentError("AI selected a strategy not supported by the Unity source.")
    reason = answer.get("reason", "")
    if not isinstance(reason, str) or len(reason) > 1200:
        raise ConversionAgentError("AI decision must include a bounded explanation.")
    animation = answer.get("animation_choice_id", "keep_native")
    if animation != "keep_native" and animation not in evidence.get("animation_choices", []):
        raise ConversionAgentError(
            "AI chose an animation action without native source/target eligibility."
        )
    if (strategy == "visual_activation_partial"
            and not evidence["summary"].get("safe_partial_visibility_adapter_available")):
        raise ConversionAgentError("Unsafe visual activation strategy was not eligible.")
    # Retrieval metadata is advisory and may not grant any additional tools.
    if evidence.get("ced_knowledge", {}).get("no_native_write_permission") is not True:
        raise ConversionAgentError("CED retrieval lost its read-only provenance gate.")
    return answer


def select(evidence: dict[str, Any], *, reasoner: Callable[[dict[str, Any]], dict],
           attempts: int = MAX_PLANNING_ATTEMPTS) -> dict[str, Any]:
    """Bounded model retries only, never native retries or hidden fallbacks."""
    if not callable(reasoner):
        raise ConversionAgentError("Planning requires a real configured model reasoner.")
    if type(attempts) is not int or not 1 <= attempts <= MAX_PLANNING_ATTEMPTS:
        raise ConversionAgentError("Invalid planning retry budget.")
    try:
        from langgraph.graph import StateGraph, START, END
    except ImportError as exc:
        raise ConversionAgentError(
            "LangGraph is required to orchestrate adaptive conversion decisions."
        ) from exc

    def ground(state: ConversionState) -> dict[str, Any]:
        knowledge = state["evidence"].get("ced_knowledge") or {}
        if (knowledge.get("no_native_write_permission") is not True
                or not isinstance(knowledge.get("knowledge_sha256"), str)
                or not state["evidence"].get("allowed_strategies")):
            raise ConversionAgentError("CED knowledge or native strategy evidence is missing.")
        return {"status": "GROUNDED"}

    def decide(state: ConversionState) -> dict[str, Any]:
        prompt = dict(state["evidence"])
        if state.get("error"):
            prompt["planning_feedback"] = (
                "Your prior decision was rejected by an independent schema/capability "
                "validator: " + state["error"][:400] +
                ". Select another registered strategy without inventing tools."
            )
        try:
            output = reasoner(prompt)
        except Exception as exc:
            return {
                "status": "MODEL_UNAVAILABLE", "error": str(exc)[:400],
                "attempts": state.get("attempts", 0) + 1,
            }
        return {
            "status": "PROPOSED", "result": output,
            "attempts": state.get("attempts", 0) + 1,
        }

    def validate(state: ConversionState) -> dict[str, Any]:
        if state["status"] == "MODEL_UNAVAILABLE":
            return {}
        try:
            _validate(state["evidence"], state.get("result"))
        except ConversionAgentError as exc:
            return {"status": "REJECTED", "error": str(exc)[:400]}
        return {"status": "VALIDATED", "error": ""}

    def route(state: ConversionState) -> str:
        if state["status"] == "VALIDATED":
            return END
        if state["status"] == "REJECTED" and state["attempts"] < attempts:
            return "decide"
        return END

    graph = StateGraph(ConversionState)
    graph.add_node("ground", ground)
    graph.add_node("decide", decide)
    graph.add_node("validate", validate)
    graph.add_edge(START, "ground")
    graph.add_edge("ground", "decide")
    graph.add_edge("decide", "validate")
    graph.add_conditional_edges("validate", route, {"decide": "decide", END: END})
    state = graph.compile().invoke(
        {"evidence": evidence, "attempts": 0, "status": "NEW", "error": ""},
        config={"recursion_limit": 10},
    )
    if state["status"] != "VALIDATED":
        raise ConversionAgentError(
            "AI planning failed without native mutation after "
            + str(state["attempts"]) + " bounded attempt(s): "
            + str(state.get("error") or state.get("status"))
        )
    return state["result"]
