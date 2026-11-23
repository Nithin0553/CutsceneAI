"""Element 4: independently validated strategy gate + bounded alternative reasoning.

The diagram's "Validated strategy?" is a source/knowledge/capability-bound
decision gate. A rejected model preference can return ONLY to a bounded,
read-only, registered-alternatives planner. It never runs the native builder,
modifies a source, grants Unreal permissions, or declares cinematic fidelity.
"""
from __future__ import annotations

import copy
import re
from typing import Any

import studio_element_investigation as investigation
import studio_element_plan as element_plan
import studio_element_schedule as schedule
import studio_element_strategy as strategy

VERSION = "1"
BATCH_SIZE = element_plan.MODEL_BATCH_SIZE
MAX_REASONING_ROUNDS = 2
REGISTERED_GLOBAL_STRATEGIES = frozenset({
    "native_source", "source_materials", "visual_activation_partial",
})
BLOCKED_STATUSES = frozenset({
    "SOURCE_DEPENDENCY_MISSING", "DEPENDENCY_CYCLE", "UPSTREAM_BLOCKED",
    "UPSTREAM_NOT_PLANNED", "OWNERSHIP_CONFLICT",
})
HEX = re.compile(r"[a-f0-9]{64}\Z")
# Stable public reason codes, not exception/source strings.
REASON_UNSUPPORTED = "SELECTED_ACTION_NOT_ELIGIBLE_IN_SOURCE_CONTEXT"
REASON_BLOCKED = "SOURCE_DEPENDENCY_OR_OWNERSHIP_BLOCKED"
REASON_UNREVIEWED = "NON_REPORT_ACTION_WITHOUT_MODEL_REVIEW"


class StrategyValidationError(ValueError):
    """Selected AI strategy is not proven safe for source-bound planning."""


def _inputs(
    plan: dict, dependency: dict, adaptive: dict, investigation_report: dict,
    knowledge: dict, csir: dict, target_capabilities: dict,
    global_strategy: str, allowed_strategies: list[str],
) -> None:
    if (not isinstance(global_strategy, str)
            or not isinstance(allowed_strategies, list)
            or len(allowed_strategies) != len(set(allowed_strategies))
            or not allowed_strategies
            or any(not isinstance(item, str)
                   or item not in REGISTERED_GLOBAL_STRATEGIES
                   for item in allowed_strategies)
            or global_strategy not in allowed_strategies):
        raise StrategyValidationError(
            "Global planning strategy is not explicitly registered and allowed."
        )
    try:
        element_plan.verify(plan, csir, knowledge, target_capabilities)
        schedule.verify(dependency, plan, csir)
        strategy.verify(
            adaptive, plan, dependency, knowledge, csir, target_capabilities,
        )
        investigation.verify(
            investigation_report, plan, dependency, adaptive,
            knowledge, csir, target_capabilities,
        )
    except (element_plan.ElementPlanError, schedule.ElementScheduleError,
            strategy.AdaptiveStrategyError,
            investigation.ElementInvestigationError) as exc:
        raise StrategyValidationError(
            "Element 4 rejected stale, incomplete or forged source-bound evidence."
        ) from exc
    if (plan["no_native_execution_permission"] is not True
            or plan["native_conversion_executed"] is not False
            or adaptive["native_execution_authorized"] is not False
            or dependency["native_execution_permitted"] is not False):
        raise StrategyValidationError("Element 4 cannot inherit native execution authority.")


def build(
    plan: dict, dependency: dict, adaptive: dict, investigation_report: dict,
    knowledge: dict, csir: dict, target_capabilities: dict,
    *, global_strategy: str, allowed_strategies: list[str],
) -> dict[str, Any]:
    """Recompute the complete, exact-source VALIDATED/NO gate.

    A native action is only an ADVISORY candidate after this stage. The
    downstream deterministic CSIR compiler still constructs its own plan,
    and the user/native preflight remain the execution authorities.
    """
    _inputs(
        plan, dependency, adaptive, investigation_report, knowledge, csir,
        target_capabilities, global_strategy, allowed_strategies,
    )
    nodes = {row["occurrence_id"]: row for row in dependency["nodes"]}
    comparisons = {
        row["occurrence_id"]: row for row in adaptive["comparisons"]
    }
    cases = {
        row["occurrence_id"]: row for row in investigation_report["findings"]
    }
    if (len(nodes) != plan["source_occurrence_count"]
            or len(comparisons) != plan["source_occurrence_count"]
            or len(cases) != plan["source_occurrence_count"]):
        raise StrategyValidationError("Validation gate omitted source occurrences.")

    validated = reported = 0
    problems = []
    decisions = []
    for element in plan["elements"]:
        ident, selected = element["occurrence_id"], element["selected_action"]
        node = nodes[ident]
        cmp = comparisons[ident]
        case = cases[ident]
        safe_options = sorted({
            item["action"] for item in cmp["alternatives"]
            if item["eligible_for_model_proposal"] is True
        })
        reason = None
        if selected != "report_only":
            if not element["model_reviewed"]:
                reason = REASON_UNREVIEWED
            elif node["status"] in BLOCKED_STATUSES:
                reason = REASON_BLOCKED
            elif (selected not in safe_options
                    or selected not in element["candidate_actions"]):
                reason = REASON_UNSUPPORTED
        if reason:
            # An explicit source-dependent block can ONLY be recovered with
            # report_only; never recommend an unregistered native alternative.
            alternatives = ([] if reason == REASON_BLOCKED else safe_options)
            problems.append({
                "occurrence_id": ident, "reason_code": reason,
                "current_action": selected,
                "allowed_alternatives": ["report_only", *alternatives],
            })
            state = "REJECTED"
        elif selected == "report_only":
            state = "LIMITATION_RECORDED"
            reported += 1
        else:
            state = "ADVISORY_NATIVE_PREFLIGHT_REQUIRED"
            validated += 1
        decisions.append({
            "occurrence_id": ident,
            "source_kind": element["source_kind"],
            "ced": cmp["ced"],
            "selected_action": selected,
            "validation": state,
            "schedule_status": node["status"],
            "investigation_status": case["state"],
            "native_execution_verified": False,
            "full_cutscene_fidelity_verified": False,
        })
    if problems:
        status = "REJECTED_BOUNDED_ALTERNATIVE_REQUIRED"
    elif reported:
        status = "VALIDATED_WITH_REPORTED_LIMITATIONS"
    else:
        status = "VALIDATED_FOR_SOURCE_BOUND_PLANNING"
    result = {
        "kind": "cutsceneai.studio.element4_strategy_validation",
        "schema_version": VERSION,
        "global_strategy": global_strategy,
        "allowed_strategies": list(allowed_strategies),
        "source_csir_sha256": plan["source_csir_sha256"],
        "ced_knowledge_sha256": plan["ced_knowledge_sha256"],
        "target_capabilities_sha256": plan["target_capabilities_sha256"],
        "element_plan_sha256": plan["element_plan_sha256"],
        "dependency_schedule_sha256": dependency["schedule_sha256"],
        "adaptive_strategy_sha256": adaptive["comparison_sha256"],
        "investigation_sha256": investigation_report["investigation_sha256"],
        "source_occurrence_count": len(decisions),
        "validated_candidate_count": validated,
        "reported_limitation_count": reported,
        "rejected_count": len(problems),
        "validation_status": status,
        "accepted_for_source_bound_plan": not problems,
        "native_execution_authorized": False,
        "full_cutscene_fidelity_verified": False,
        "decisions": decisions,
        "rejections": problems,
    }
    result["validation_sha256"] = element_plan._digest(result)
    return result


def verify(
    validation: dict, plan: dict, dependency: dict,
    adaptive: dict, investigation_report: dict, knowledge: dict, csir: dict,
    target_capabilities: dict, *, global_strategy: str,
    allowed_strategies: list[str],
) -> None:
    """All claims are rebuilt from source, not trusted from a self-hashed JSON."""
    expected = build(
        plan, dependency, adaptive, investigation_report, knowledge, csir,
        target_capabilities, global_strategy=global_strategy,
        allowed_strategies=allowed_strategies,
    )
    if not isinstance(validation, dict) or validation != expected:
        raise StrategyValidationError(
            "Element 4 strategy validation was modified or is no longer current."
        )


def reason_bounded(
    plan: dict, knowledge: dict, csir: dict,
    target_capabilities: dict, *, global_strategy: str,
    allowed_strategies: list[str], provider: Any,
    max_rounds: int = MAX_REASONING_ROUNDS,
) -> tuple[dict, dict, dict, dict, dict, list[dict]]:
    """No -> bounded alternatives -> revalidate, at most two complete rounds.

    Only currently rejected occurrences are reconsidered. Model proposals
    are strict JSON with EXACT anonymized IDs and currently registered
    alternatives. Missing/forged/ineligible replies stop, without fallback
    to an unsafe strategy or edits to the existing native compiler.
    """
    if (type(max_rounds) is not int or not 0 <= max_rounds <= MAX_REASONING_ROUNDS
            or not callable(getattr(provider, "complete_json", None))):
        raise StrategyValidationError(
            "Bounded alternative reasoning requires a configured JSON model and a 0–2 round budget."
        )
    # Rebuild all dependent evidence in every iteration: model revisions may
    # change upstream schedule statuses and adaptive eligibility.
    current_plan = plan
    audit: list[dict] = []
    for round_index in range(max_rounds + 1):
        dep = schedule.build(current_plan, csir)
        adaptive = strategy.build(
            current_plan, dep, knowledge, csir, target_capabilities,
        )
        cases = investigation.build(
            current_plan, dep, adaptive, knowledge, csir,
            target_capabilities,
        )
        gate = build(
            current_plan, dep, adaptive, cases, knowledge, csir,
            target_capabilities, global_strategy=global_strategy,
            allowed_strategies=allowed_strategies,
        )
        if gate["accepted_for_source_bound_plan"]:
            return current_plan, dep, adaptive, cases, gate, audit
        if round_index == max_rounds:
            raise StrategyValidationError(
                "Bounded alternatives exhausted without a valid source-bound strategy."
            )
        # Conservative step: a blocked dependent can be reported, but no
        # generated native action may be attached to an unmet dependency.
        by_id = {row["occurrence_id"]: row for row in gate["rejections"]}
        revised: dict[str, str] = {}
        responses = []
        for index in range(0, len(gate["rejections"]), BATCH_SIZE):
            batch = gate["rejections"][index:index + BATCH_SIZE]
            payload = {
                "round": round_index + 1,
                "page_index": index // BATCH_SIZE,
                "source_occurrence_count": gate["source_occurrence_count"],
                "validation_sha256": gate["validation_sha256"],
                "rejected": [{
                    "occurrence_id": row["occurrence_id"],
                    "reason_code": row["reason_code"],
                    "allowed_alternatives": row["allowed_alternatives"],
                } for row in batch],
            }
            try:
                output = provider.complete_json(
                    task="cutsceneai_element4_bounded_alternatives",
                    instructions=(
                        "You are the read-only CutSceneAI alternative planner. "
                        "An independent exact-source validator rejected these "
                        "selected native action candidates. For EACH anonymous "
                        "occurrence choose exactly one listed registered alternative "
                        "or report_only. Respect unresolved dependencies, "
                        "ownership, missing evidence and capability blockers. "
                        "Do not invent source identifiers, API calls, Python, "
                        "tool invocations, permissions or fidelity claims. "
                        "Return only the required JSON."
                    ),
                    payload=payload,
                    schema={
                        "type": "object", "additionalProperties": False,
                        "properties": {"choices": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
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
            except Exception as exc:
                raise StrategyValidationError(
                    "Bounded alternative model unavailable; no native plan authorized."
                ) from exc
            answer = getattr(output, "answer", None)
            sha = getattr(output, "response_sha256", None)
            if (not isinstance(answer, dict) or set(answer) != {"choices"}
                    or not isinstance(answer["choices"], list)
                    or len(answer["choices"]) != len(batch)
                    or not isinstance(sha, str) or not HEX.fullmatch(sha)):
                raise StrategyValidationError(
                    "Bounded alternative response has incomplete structured provenance."
                )
            batch_ids = {row["occurrence_id"] for row in batch}
            for choice in answer["choices"]:
                if (not isinstance(choice, dict)
                        or set(choice) != {"occurrence_id", "action"}):
                    raise StrategyValidationError("Alternative model returned unregistered fields.")
                ident, action = choice["occurrence_id"], choice["action"]
                if (not isinstance(ident, str) or ident not in batch_ids
                        or ident in revised or type(action) is not str
                        or action not in by_id[ident]["allowed_alternatives"]):
                    raise StrategyValidationError(
                        "Alternative model invented, duplicated or selected a prohibited native action."
                    )
                revised[ident] = action
            if set(revised).intersection(batch_ids) != batch_ids:
                raise StrategyValidationError(
                    "Alternative reasoning silently omitted a rejected source occurrence."
                )
            responses.append({
                "page_index": index // BATCH_SIZE,
                "response_sha256": sha,
                "reviewed_count": len(batch),
            })
        if len(revised) != len(by_id):
            raise StrategyValidationError("Alternative review omitted source occurrences.")
        if not any(revised[ident] != by_id[ident]["current_action"]
                   for ident in revised):
            raise StrategyValidationError(
                "Bounded alternative reasoning made no progress."
            )
        updated = copy.deepcopy(current_plan)
        for row in updated["elements"]:
            if row["occurrence_id"] in revised:
                row["selected_action"] = revised[row["occurrence_id"]]
                row["model_reviewed"] = True
        updated["model_reviewed_count"] = sum(
            row["model_reviewed"] for row in updated["elements"]
        )
        updated.pop("element_plan_sha256", None)
        updated["element_plan_sha256"] = element_plan._digest(updated)
        element_plan.verify(updated, csir, knowledge, target_capabilities)
        current_plan = updated
        audit.append({
            "round": round_index + 1,
            "rejected_count": len(by_id),
            "validated_replacement_count": len(revised),
            "previous_validation_sha256": gate["validation_sha256"],
            "new_plan_sha256": current_plan["element_plan_sha256"],
            "responses": responses,
            "native_execution_authorized": False,
        })
    raise StrategyValidationError("Unexpected bounded reasoning termination.")
