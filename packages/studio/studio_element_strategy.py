"""Element 3.3: evidence-scoped, non-executable native action comparisons.

Reuse CED's existing contextual rule ranking and its independent held-out
experience guard. Do not manufacture source features, positive experience,
native permissions, or a second mapping/retargeting authority. Every proposed
alternative still requires native preflight and current-project CineTwin proof.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import feature_dispatch
import studio_element_plan as element_plan
import studio_element_schedule as element_schedule

VERSION = "1"
_BLOCKERS = frozenset({
    "SOURCE_DEPENDENCY_MISSING", "DEPENDENCY_CYCLE", "UPSTREAM_BLOCKED",
    "OWNERSHIP_CONFLICT",
})
_REVIEW_LEVELS = frozenset({
    "MULTI_PROJECT_REVIEWED", "NEGATIVE_OBSERVATION",
    "INSUFFICIENT_INDEPENDENT_EVIDENCE",
})
_CAPS = element_plan._ACTION_CAPABILITY


class AdaptiveStrategyError(ValueError):
    """An action comparison cannot be independently grounded in source evidence."""


def _native_route(row: dict[str, Any], by_id: dict[str, dict[str, Any]],
                  source: dict[str, Any]) -> str | None:
    """Match the installed Unreal csir_plan animation.track actor branch.

    A character-bound animation.track maps to skeletal sections; other
    resolved entity bindings map to the actor-transform branch. Only the
    track and its immediate sections have this routing restriction. Curves,
    unknown bindings and asset preflight have separate semantics.
    """
    owner = row
    if row["source_kind"] == "sections":
        parents = [by_id[d] for d in row["dependencies"]
                   if by_id[d]["source_kind"] == "tracks"]
        if len(parents) != 1:
            return None
        owner = parents[0]
    if owner["source_kind"] != "tracks" or owner["ced"] != "animation.track":
        return None
    location = owner["source_location"]
    # Track presence and muted state are checked against exact source; no raw
    # entity identifier is ever returned by this function.
    try:
        index = int(location.removeprefix("tracks[").removesuffix("]"))
        track = source["tracks"][index]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AdaptiveStrategyError("Source track is not at its bound location.") from exc
    if not isinstance(track, dict) or track.get("muted") is True:
        return None
    entity = [by_id[d] for d in owner["dependencies"]
              if by_id[d]["source_kind"] == "entities"]
    if len(entity) != 1:
        return None
    if entity[0]["ced"] == "entity.character":
        return "skeletal_animation"
    if entity[0]["state"] == "UNKNOWN_SEMANTIC_INVESTIGATE":
        return None
    return "transform"


def _evidence(rules: list[dict[str, Any]], action: str) -> tuple[int, str, int, int, int, list[str]]:
    """Use the CED service's scores as-is; never infer positive review."""
    best: int | None = None
    tier = "INSUFFICIENT_INDEPENDENT_EVIDENCE"
    passed = failed = conflicting = 0
    flags: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise AdaptiveStrategyError("CED strategy rule is malformed.")
        recipe = rule.get("strategy_recipe")
        ranking = rule.get("advisory_ranking")
        if not isinstance(recipe, dict) or not isinstance(ranking, dict):
            raise AdaptiveStrategyError("CED strategy rule lacks registered recipe/ranking.")
        required = recipe.get("required_native_actions")
        if (not isinstance(required, list)
                or any(not isinstance(v, str) or v not in feature_dispatch.BUILDER_ACTIONS
                       for v in required)):
            raise AdaptiveStrategyError("CED candidate advertises unregistered native actions.")
        if action not in required:
            continue
        score = ranking.get("context_score")
        prior = ranking.get("independent_experience")
        if type(score) is not int or not isinstance(prior, dict):
            raise AdaptiveStrategyError("CED ranking lacks exact independent evidence.")
        level = prior.get("evidence_level")
        if level not in _REVIEW_LEVELS:
            raise AdaptiveStrategyError("CED independent evidence level is invalid.")
        counts = [prior.get(k) for k in (
            "reviewed_success_project_groups", "failed_project_groups",
            "conflicting_project_groups",
        )]
        if any(type(n) is not int or not 0 <= n <= 8000 for n in counts):
            raise AdaptiveStrategyError("CED independent project counts are invalid.")
        if (best is None or score > best):
            best = score
            tier = level
            passed, failed, conflicting = counts
        if counts[1] or counts[2]:
            flags.add("RECORDED_FAILED_OR_CONFLICTING_PROJECT_EVIDENCE")
        if level == "MULTI_PROJECT_REVIEWED" and counts[0] >= 3:
            flags.add("INDEPENDENTLY_REVIEWED_PROJECT_GROUPS")
        if rule.get("status") == "CAPABILITY_EVIDENCE_MISSING":
            flags.add("CED_RULE_CAPABILITY_EVIDENCE_GAP")
        if rule.get("source_capability_check") == "NOT_INSPECTED":
            flags.add("CED_SOURCE_CAPABILITIES_NOT_INSPECTED")
    if best is None:
        flags.add("NO_ACTION_SPECIFIC_CED_RULE")
        return 0, tier, 0, 0, 0, sorted(flags)
    # Existing CED ranking is an advisory heuristic, not probability.
    return max(-100, min(100, best)), tier, passed, failed, conflicting, sorted(flags)


def build(plan: dict[str, Any], schedule: dict[str, Any],
          knowledge: dict[str, Any], csir: dict[str, Any],
          target_capabilities: dict[str, bool]) -> dict[str, Any]:
    """Compare registered actions in context; fail closed for unproven routes."""
    if (not isinstance(knowledge, dict)
            or knowledge.get("retrieval_complete") is not True
            or knowledge.get("no_native_write_permission") is not True
            or not isinstance(target_capabilities, dict)
            or any(not isinstance(k, str) or type(v) is not bool
                   for k, v in target_capabilities.items())):
        raise AdaptiveStrategyError("Complete CED and observed native capabilities required.")
    try:
        element_plan.verify(plan, csir, knowledge, target_capabilities)
        element_schedule.verify(schedule, plan, csir)
    except (element_plan.ElementPlanError,
            element_schedule.ElementScheduleError) as exc:
        raise AdaptiveStrategyError("Adaptive comparison requires exact source-bound evidence.") from exc
    rows = plan["elements"]
    if schedule["source_occurrence_count"] != len(rows):
        raise AdaptiveStrategyError("Adaptive strategy inventory is incomplete.")
    by_id = {row["occurrence_id"]: row for row in rows}
    statuses = {node["occurrence_id"]: node["status"] for node in schedule["nodes"]}
    entries = {row["ced"]: row for row in knowledge["entries"]}
    if len(entries) != len(knowledge["entries"]):
        raise AdaptiveStrategyError("Duplicate CED concepts are not strategy evidence.")
    comparisons = []
    for item in rows:
        ident = item["occurrence_id"]
        entry = entries.get(item["ced"])
        known = isinstance(entry, dict) and entry.get("semantic_known") is True
        ced = item["ced"] if known else "unknown.unclassified"
        rules = entry.get("rules", []) if known else []
        if not isinstance(rules, list):
            raise AdaptiveStrategyError("Malformed source semantic strategy rules.")
        native_route = _native_route(item, by_id, csir)
        blocked = statuses[ident] in _BLOCKERS
        alternative_rows = []
        for action in item["candidate_actions"]:
            if action not in feature_dispatch.BUILDER_ACTIONS:
                raise AdaptiveStrategyError("Nonregistered native alternative.")
            score, tier, passed, failed, conflicting, flags = _evidence(rules, action)
            required = _CAPS.get(action)
            # Phase 3.1 candidates may allow an unobserved optional capability;
            # Phase 3.3 does not silently upgrade that to a supported strategy.
            cap_known = required is None or target_capabilities.get(required) is True
            native_match = native_route is None or (
                action not in {"skeletal_animation", "transform"}
                or action == native_route
            )
            eligible = (not blocked and cap_known and native_match)
            if blocked:
                flags.append("SOURCE_GRAPH_OR_OWNERSHIP_BLOCKED")
            if not cap_known:
                flags.append("TARGET_CAPABILITY_NOT_OBSERVED")
            if not native_match:
                flags.append("INSTALLED_NATIVE_SOURCE_BRANCH_MISMATCH")
            if native_route is not None and action == native_route:
                # The only action-dependent preference is grounded in the
                # existing deterministic Unreal csir_plan track branch.
                score += 8
                flags.append("MATCHES_INSTALLED_NATIVE_TRACK_ROUTE")
            # Never model these as calibrated success probabilities.
            alternative_rows.append({
                "action": action,
                "advisory_score": max(-100, min(100, score)),
                "eligible_for_model_proposal": eligible,
                "independent_evidence_level": tier,
                "reviewed_success_project_groups": passed,
                "failed_project_groups": failed,
                "conflicting_project_groups": conflicting,
                "signals": sorted(set(flags)),
                "native_preflight_required": True,
                "current_cutscene_fidelity_verified": False,
            })
        alternative_rows.sort(key=lambda x: (-int(x["eligible_for_model_proposal"]),
                                             -x["advisory_score"], x["action"]))
        eligible = [x for x in alternative_rows if x["eligible_for_model_proposal"]]
        if not eligible:
            suggested, reason = "report_only", "NO_EVIDENCE_GROUNDED_ALTERNATIVE"
        elif len(eligible) == 1 or eligible[0]["advisory_score"] > eligible[1]["advisory_score"]:
            suggested, reason = eligible[0]["action"], "HIGHEST_ADVISORY_EVIDENCE_SCORE"
        else:
            suggested, reason = "report_only", "UNDISTINGUISHED_CED_ALTERNATIVES"
        comparisons.append({
            "occurrence_id": ident,
            "ced": ced,
            "source_kind": item["source_kind"],
            "source_schedule_status": statuses[ident],
            "alternatives": alternative_rows,
            "suggested_action": suggested,
            "suggestion_reason": reason,
            "selected_action": item["selected_action"],
            "model_reviewed": item["model_reviewed"],
            "native_execution_authorized": False,
        })
    result = {
        "kind": "cutsceneai.studio.adaptive_element_strategy_comparison",
        "schema_version": VERSION,
        "source_csir_sha256": plan["source_csir_sha256"],
        "ced_knowledge_sha256": plan["ced_knowledge_sha256"],
        "target_capabilities_sha256": plan["target_capabilities_sha256"],
        "element_plan_sha256": plan["element_plan_sha256"],
        "dependency_schedule_sha256": schedule["schedule_sha256"],
        "source_occurrence_count": len(rows),
        "native_execution_authorized": False,
        "full_cutscene_fidelity_verified": False,
        "comparisons": comparisons,
    }
    result["comparison_sha256"] = element_plan._digest(result)
    return result


def verify(comparison: dict[str, Any], plan: dict[str, Any],
           schedule: dict[str, Any], knowledge: dict[str, Any],
           csir: dict[str, Any], target_capabilities: dict[str, bool]) -> None:
    """Recompute *every* comparison, not only its caller-recomputed checksum."""
    if not isinstance(comparison, dict) or comparison != build(
        plan, schedule, knowledge, csir, target_capabilities,
    ):
        raise AdaptiveStrategyError("Adaptive strategy comparison is stale, incomplete or tampered.")


def proposal_hints(comparison: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Only the redacted, bounded advisory payload subset goes to the model."""
    if not isinstance(comparison, dict) or comparison.get("native_execution_authorized") is not False:
        raise AdaptiveStrategyError("Untrusted adaptive strategy hints.")
    rows = comparison.get("comparisons")
    if not isinstance(rows, list) or len(rows) != comparison.get("source_occurrence_count"):
        raise AdaptiveStrategyError("Incomplete adaptive strategy comparison.")
    hints = {}
    for row in rows:
        options = [item for item in row["alternatives"]
                   if item["eligible_for_model_proposal"] is True]
        if row["occurrence_id"] in hints:
            raise AdaptiveStrategyError("Repeated occurrence strategy comparison.")
        hints[row["occurrence_id"]] = {
            "suggested_action": row["suggested_action"],
            "suggestion_reason": row["suggestion_reason"],
            "alternatives": [{
                "action": option["action"],
                "advisory_score": option["advisory_score"],
                "independent_evidence_level": option["independent_evidence_level"],
                "reviewed_success_project_groups": option["reviewed_success_project_groups"],
                "failed_project_groups": option["failed_project_groups"],
                "signals": option["signals"],
            } for option in options],
        }
    return hints
