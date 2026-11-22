"""Element 3.4: bounded, source-grounded investigation and alternative discovery.

Investigations are diagnostic suggestions, never native reads/writes or approvals.
The only proposed conversion alternatives come from Element 3.3's installed,
source-qualified builder action set. Unknown semantics stay unknown; neither
lexical matches nor model output may manufacture a native adapter.
"""
from __future__ import annotations

import copy
import re
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import studio_element_plan as element_plan
import studio_element_schedule as element_schedule
import studio_element_strategy as element_strategy

VERSION = "1"
BATCH_SIZE = 12
MAX_INVESTIGATIONS = element_plan.MAX_OCCURRENCES
MODEL_STEP_SET = frozenset({
    "inspect_source_references", "inspect_target_capabilities",
    "review_ced_knowledge", "inspect_timeline_ownership",
    "validate_native_preflight", "collect_native_readback",
    "review_registered_alternatives", "compare_cinetwin_capture",
})
_GRAPH_BLOCKERS = {
    "SOURCE_DEPENDENCY_MISSING": ("SOURCE_REFERENCE_UNRESOLVED", "inspect_source_references"),
    "DEPENDENCY_CYCLE": ("CYCLIC_SOURCE_RELATIONSHIP", "inspect_source_references"),
    "UPSTREAM_BLOCKED": ("UPSTREAM_OCCURRENCE_BLOCKED", "inspect_source_references"),
    "OWNERSHIP_CONFLICT": ("TIMELINE_OWNERSHIP_UNPROVEN", "inspect_timeline_ownership"),
    "UPSTREAM_NOT_PLANNED": ("UPSTREAM_ACTION_NOT_PLANNED", "inspect_source_references"),
}
_PLAN_GAPS = {
    "UNKNOWN_SEMANTIC_INVESTIGATE": ("UNKNOWN_CED_CONCEPT", "review_ced_knowledge"),
    "CED_KNOWLEDGE_MISSING": ("CED_KNOWLEDGE_UNAVAILABLE", "review_ced_knowledge"),
    "TARGET_CAPABILITY_MISSING": ("TARGET_CAPABILITY_MISSING", "inspect_target_capabilities"),
    "NO_REGISTERED_NATIVE_ACTION": ("NO_REGISTERED_NATIVE_ACTION", "review_ced_knowledge"),
    "UNRESOLVED_SOURCE_DEPENDENCY": ("SOURCE_REFERENCE_UNRESOLVED", "inspect_source_references"),
}


class ElementInvestigationError(ValueError):
    """Source evidence, model choices or a checkpoint are not trustworthy."""


def _digest(value: Any) -> str:
    return element_plan._digest(value)


def _validate_inputs(plan: dict, schedule: dict, strategy: dict,
                     knowledge: dict, csir: dict, capabilities: dict) -> None:
    try:
        element_strategy.verify(strategy, plan, schedule, knowledge, csir, capabilities)
    except (element_plan.ElementPlanError, element_schedule.ElementScheduleError,
            element_strategy.AdaptiveStrategyError) as exc:
        raise ElementInvestigationError(
            "Investigation requires complete exact-source registered strategy evidence."
        ) from exc


def build(plan: dict[str, Any], schedule: dict[str, Any],
          strategy: dict[str, Any], knowledge: dict[str, Any],
          csir: dict[str, Any], target_capabilities: dict[str, bool]) -> dict[str, Any]:
    """Explain every occurrence; never silently omit unsupported elements."""
    _validate_inputs(plan, schedule, strategy, knowledge, csir, target_capabilities)
    by_status = {node["occurrence_id"]: node["status"] for node in schedule["nodes"]}
    by_strategy = {row["occurrence_id"]: row for row in strategy["comparisons"]}
    if (len(by_status) != plan["source_occurrence_count"]
            or len(by_strategy) != plan["source_occurrence_count"]):
        raise ElementInvestigationError("Incomplete per-occurrence investigation coverage.")
    findings = []
    for row in plan["elements"]:
        ident = row["occurrence_id"]
        comparison = by_strategy[ident]
        reasons: set[str] = set()
        next_steps: set[str] = set()
        evidence: set[str] = set()
        state = row["state"]
        scheduled = by_status[ident]
        if state in _PLAN_GAPS:
            reason, step = _PLAN_GAPS[state]
            reasons.add(reason)
            next_steps.add(step)
        if row["unresolved_dependencies"]:
            reasons.add("SOURCE_REFERENCE_UNRESOLVED")
            next_steps.add("inspect_source_references")
        if scheduled in _GRAPH_BLOCKERS:
            reason, step = _GRAPH_BLOCKERS[scheduled]
            reasons.add(reason)
            next_steps.add(step)
        for gap in row["missing_target_capabilities"]:
            # Never emit raw vendor/native capability names outside the
            # established schema's approved vocabulary.
            if gap in {"cine_camera_actor", "sequencer_skeletal_animation_track",
                       "sequencer_visibility_track"}:
                reasons.add("TARGET_CAPABILITY_MISSING")
                next_steps.add("inspect_target_capabilities")
        registered = []
        for alternative in comparison["alternatives"]:
            if alternative["eligible_for_model_proposal"] is True:
                registered.append(alternative["action"])
            signals = set(alternative["signals"])
            if "RECORDED_FAILED_OR_CONFLICTING_PROJECT_EVIDENCE" in signals:
                reasons.add("NEGATIVE_OR_CONFLICTING_CED_EXPERIENCE")
                next_steps.add("review_ced_knowledge")
            if "CED_SOURCE_CAPABILITIES_NOT_INSPECTED" in signals:
                reasons.add("SOURCE_CAPABILITY_EVIDENCE_UNOBSERVED")
                next_steps.add("inspect_source_references")
            if "CED_RULE_CAPABILITY_EVIDENCE_GAP" in signals:
                reasons.add("CED_RULE_CAPABILITY_EVIDENCE_GAP")
                next_steps.add("inspect_target_capabilities")
            if "NO_ACTION_SPECIFIC_CED_RULE" in signals:
                reasons.add("ACTION_SPECIFIC_CED_RULE_UNAVAILABLE")
                next_steps.add("review_ced_knowledge")
            if "TARGET_CAPABILITY_NOT_OBSERVED" in signals:
                reasons.add("TARGET_CAPABILITY_UNOBSERVED")
                next_steps.add("inspect_target_capabilities")
            if "INSTALLED_NATIVE_SOURCE_BRANCH_MISMATCH" in signals:
                reasons.add("NATIVE_SOURCE_ROUTE_MISMATCH")
                next_steps.add("review_registered_alternatives")
        # Only eligible alternatives are safe even to *suggest* for review.
        # Never reinterpret CED lexical similarity as registered native support.
        registered = sorted(set(registered))
        if registered:
            if row["selected_action"] == "report_only":
                reasons.add("REGISTERED_ALTERNATIVE_NOT_SELECTED")
                next_steps.add("review_registered_alternatives")
            else:
                reasons.add("NATIVE_PREFLIGHT_NOT_VERIFIED")
                next_steps.add("validate_native_preflight")
                next_steps.add("collect_native_readback")
                next_steps.add("compare_cinetwin_capture")
        elif not reasons:
            reasons.add("NO_EVIDENCE_GROUNDED_NATIVE_ALTERNATIVE")
            next_steps.add("review_ced_knowledge")
        if scheduled in {"OWNERSHIP_CONFLICT", "DEPENDENCY_CYCLE",
                         "SOURCE_DEPENDENCY_MISSING", "UPSTREAM_BLOCKED"}:
            # Investigation may describe available candidates, but cannot
            # assert a source-blocked action can be submitted.
            registered = []
        if "SOURCE_REFERENCE_UNRESOLVED" in reasons or "CYCLIC_SOURCE_RELATIONSHIP" in reasons:
            evidence.add("SOURCE_IDENTITY_AND_RELATIONSHIPS")
        if "TIMELINE_OWNERSHIP_UNPROVEN" in reasons:
            evidence.add("SOURCE_TRACK_BINDING_AND_BLEND_TIMING")
        if any(reason.startswith("TARGET_CAPABILITY") for reason in reasons):
            evidence.add("FRESH_UNREAL_CAPABILITY_PROBE")
        if any("CED" in reason or "REGISTERED" in reason or "NATIVE_SOURCE_ROUTE" in reason
               for reason in reasons):
            evidence.add("REVIEWED_CED_AND_INSTALLED_ACTION_REGISTRY")
        if "NATIVE_PREFLIGHT_NOT_VERIFIED" in reasons:
            evidence.add("NATIVE_PREFLIGHT_AND_TARGET_READBACK")
            evidence.add("CINETWIN_SOURCE_TARGET_COMPARISON")
        # Fixed, redacted reason/action vocabularies. No raw CSIR values,
        # project-specific names or file paths leave the investigator.
        findings.append({
            "occurrence_id": ident,
            "source_kind": row["source_kind"],
            "ced": comparison["ced"],
            "state": (
                "BLOCKED_SOURCE" if scheduled in {
                    "SOURCE_DEPENDENCY_MISSING", "DEPENDENCY_CYCLE",
                    "UPSTREAM_BLOCKED", "OWNERSHIP_CONFLICT",
                } else
                "INVESTIGATION_REQUIRED" if state != "NATIVE_ACTION_CANDIDATES_REQUIRE_PREFLIGHT"
                or not registered else
                "NATIVE_PREFLIGHT_REQUIRED" if row["selected_action"] != "report_only"
                else "REGISTERED_ALTERNATIVES_UNVERIFIED"
            ),
            "source_schedule_status": scheduled,
            "reason_codes": sorted(reasons),
            "required_evidence": sorted(evidence),
            "registered_alternatives": registered,
            "available_investigation_steps": sorted(next_steps),
            "selected_step": "report_only",
            "model_reviewed": False,
            "native_execution_authorized": False,
            "current_cutscene_fidelity_verified": False,
        })
    result = {
        "kind": "cutsceneai.studio.element_investigation",
        "schema_version": VERSION,
        "source_csir_sha256": plan["source_csir_sha256"],
        "ced_knowledge_sha256": plan["ced_knowledge_sha256"],
        "target_capabilities_sha256": plan["target_capabilities_sha256"],
        "element_plan_sha256": plan["element_plan_sha256"],
        "dependency_schedule_sha256": schedule["schedule_sha256"],
        "adaptive_strategy_sha256": strategy["comparison_sha256"],
        "source_occurrence_count": len(findings),
        "model_reviewed_count": 0,
        "native_execution_authorized": False,
        "source_and_target_fidelity_verified": False,
        "findings": findings,
    }
    result["investigation_sha256"] = _digest(result)
    return result


def _validate_checksum(report: dict[str, Any]) -> None:
    if (not isinstance(report, dict)
            or report.get("native_execution_authorized") is not False
            or report.get("source_and_target_fidelity_verified") is not False
            or report.get("investigation_sha256") != _digest({
                key: value for key, value in report.items()
                if key != "investigation_sha256"
            })):
        raise ElementInvestigationError("Investigation evidence or read-only checksum is invalid.")


def verify(report: dict, plan: dict, schedule: dict,
           strategy: dict, knowledge: dict, csir: dict,
           target_capabilities: dict) -> None:
    """Independently rebuild every issue and allowed step from fresh evidence."""
    _validate_checksum(report)
    baseline = build(plan, schedule, strategy, knowledge, csir, target_capabilities)
    if set(report) != set(baseline):
        raise ElementInvestigationError("Investigation contract fields were changed.")
    fixed_keys = set(baseline) - {
        "model_reviewed_count", "findings", "investigation_sha256",
    }
    if any(report[key] != baseline[key] for key in fixed_keys):
        raise ElementInvestigationError("Investigation belongs to stale or foreign evidence.")
    if (not isinstance(report["findings"], list)
            or len(report["findings"]) != len(baseline["findings"])):
        raise ElementInvestigationError("Investigation omitted source occurrences.")
    count = 0
    for row, expected in zip(report["findings"], baseline["findings"]):
        if (not isinstance(row, dict) or set(row) != set(expected)
                or any(row[k] != expected[k] for k in expected
                       if k not in {"selected_step", "model_reviewed"})):
            raise ElementInvestigationError("Investigation altered a source finding or known evidence gap.")
        if type(row["model_reviewed"]) is not bool:
            raise ElementInvestigationError("Invalid investigation review flag.")
        if (row["selected_step"] != "report_only"
                and (not row["model_reviewed"]
                     or row["selected_step"] not in expected["available_investigation_steps"])):
            raise ElementInvestigationError("An unregistered investigation step was selected.")
        count += row["model_reviewed"]
    if (type(report["model_reviewed_count"]) is not int
            or count != report["model_reviewed_count"]):
        raise ElementInvestigationError("Investigation model review accounting is inconsistent.")


def apply_choices(report: dict, choices: list[dict], *, expected_ids: list[str]) -> dict:
    """Require one exact fixed-vocabulary diagnostic recommendation per case."""
    _validate_checksum(report)
    findings = report.get("findings")
    if (not isinstance(findings, list) or not isinstance(choices, list)
            or not isinstance(expected_ids, list)
            or len(expected_ids) != len(set(expected_ids))
            or len(choices) != len(expected_ids)):
        raise ElementInvestigationError("Investigation review omitted or duplicated source cases.")
    by_id = {r["occurrence_id"]: r for r in findings}
    if len(by_id) != len(findings) or not set(expected_ids) <= set(by_id):
        raise ElementInvestigationError("Unknown occurrence in investigation review.")
    selected: dict[str, str] = {}
    for row in choices:
        if not isinstance(row, dict) or set(row) != {"occurrence_id", "action"}:
            raise ElementInvestigationError("Unexpected model investigation fields.")
        ident, action = row["occurrence_id"], row["action"]
        if (ident not in expected_ids or ident in selected
                or type(action) is not str):
            raise ElementInvestigationError("Model invented or duplicated an investigation occurrence.")
        original = by_id[ident]
        if (original["model_reviewed"]
                or (action != "report_only"
                    and (action not in MODEL_STEP_SET
                         or action not in original["available_investigation_steps"]))):
            raise ElementInvestigationError("Model selected an unsupported diagnostic operation.")
        selected[ident] = action
    if set(selected) != set(expected_ids):
        raise ElementInvestigationError("Model silently omitted an investigation case.")
    updated = copy.deepcopy(report)
    for row in updated["findings"]:
        if row["occurrence_id"] in selected:
            row["selected_step"] = selected[row["occurrence_id"]]
            row["model_reviewed"] = True
    updated["model_reviewed_count"] = sum(
        r["model_reviewed"] for r in updated["findings"]
    )
    updated.pop("investigation_sha256")
    updated["investigation_sha256"] = _digest(updated)
    return updated


def review_with_model(report: dict, *,
                      plan: dict, schedule: dict, strategy: dict,
                      knowledge: dict, csir: dict, target_capabilities: dict,
                      provider: Any, checkpoint_path: Path | None = None,
                      model_identity: str = "unspecified",
                      max_new_pages: int | None = None,
                      ) -> tuple[dict, list[str]]:
    """Resumable, exact-membership model investigation with NO engine actions."""
    from studio_element_review_checkpoint import ReviewCheckpoint

    verify(report, plan, schedule, strategy, knowledge, csir, target_capabilities)
    if not callable(getattr(provider, "complete_json", None)):
        raise ElementInvestigationError("Investigation requires a configured JSON model.")
    if (max_new_pages is not None
            and (type(max_new_pages) is not int or max_new_pages < 1)):
        raise ElementInvestigationError("Invalid bounded investigation page limit.")
    # All reported cases stay in the manifest; only cases with permitted
    # diagnostic next steps incur extra model calls.
    cases = [row for row in report["findings"] if row["available_investigation_steps"]]
    if len(cases) > MAX_INVESTIGATIONS:
        raise ElementInvestigationError("Investigation review budget exceeded.")
    context = (ReviewCheckpoint(
        checkpoint_path, plan_sha256=report["investigation_sha256"],
        batch_size=BATCH_SIZE, model_identity=model_identity,
    ) if checkpoint_path is not None else nullcontext(None))
    output = report
    digests: list[str] = []
    new_pages = 0
    with context as checkpoint:
        pages = (len(cases) + BATCH_SIZE - 1) // BATCH_SIZE
        if checkpoint is not None and len(checkpoint.pages) > pages:
            raise ElementInvestigationError("Checkpoint exceeds source investigation pages.")
        for position in range(0, len(cases), BATCH_SIZE):
            page = position // BATCH_SIZE
            batch = cases[position:position + BATCH_SIZE]
            ids = [item["occurrence_id"] for item in batch]
            if checkpoint is not None and page < len(checkpoint.pages):
                cached = checkpoint.pages[page]
                choices, digest = cached["choices"], cached["model_response_sha256"]
            else:
                if max_new_pages is not None and new_pages >= max_new_pages:
                    raise ElementInvestigationError(
                        "Bounded investigation is incomplete. Validated pages can "
                        "resume; no native job was authorized."
                    )
                response = provider.complete_json(
                    task="cutsceneai_element_investigation_next_step",
                    instructions=(
                        "You are a read-only cinematic conversion investigator. "
                        "For every case choose one listed diagnostic next step "
                        "or report_only, using the exact occurrence IDs. "
                        "Steps are RECOMMENDATIONS ONLY, never actual tool calls. "
                        "Known registered alternatives are suggestions requiring "
                        "native preflight. Unknown semantics, lexical hints and "
                        "missing capabilities MUST NOT become invented Unreal "
                        "commands. Never assert a native transfer, fidelity pass "
                        "or executed repair. Output only the exact JSON choices."
                    ),
                    payload={
                        "source_case_count": len(cases),
                        "page_index": page,
                        "cases": [{
                            "occurrence_id": item["occurrence_id"],
                            "source_kind": item["source_kind"],
                            "ced": item["ced"],
                            "state": item["state"],
                            "reason_codes": item["reason_codes"],
                            "required_evidence": item["required_evidence"],
                            "registered_alternatives": item["registered_alternatives"],
                            "available_investigation_steps":
                                item["available_investigation_steps"],
                        } for item in batch],
                    },
                    schema={
                        "type": "object", "additionalProperties": False,
                        "properties": {"choices": {
                            "type": "array", "items": {
                                "type": "object", "additionalProperties": False,
                                "properties": {
                                    "occurrence_id": {"type": "string"},
                                    "action": {"type": "string"},
                                },
                                "required": ["occurrence_id", "action"],
                            },
                        }},
                        "required": ["choices"],
                    },
                )
                answer = getattr(response, "answer", None)
                if not isinstance(answer, dict) or set(answer) != {"choices"}:
                    raise ElementInvestigationError("Malformed investigation model response.")
                choices = answer["choices"]
                digest = getattr(response, "response_sha256", None)
            output = apply_choices(output, choices, expected_ids=ids)
            if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise ElementInvestigationError("Investigation response digest is missing.")
            if checkpoint is not None and page >= len(checkpoint.pages):
                checkpoint.add_page(
                    page_index=page, choices=choices,
                    model_response_sha256=digest,
                )
                new_pages += 1
            digests.append(digest)
    if output["model_reviewed_count"] != len(cases):
        raise ElementInvestigationError("Investigation did not cover all eligible source cases.")
    verify(output, plan, schedule, strategy, knowledge, csir, target_capabilities)
    return output, digests
