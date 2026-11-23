"""Element 5: immutable source-to-native conversion-plan reconciliation.

This is NOT a second CSIR->Unreal compiler. The existing deterministic
compiler is the only author of action payloads. Element 5 relates that exact
native plan to every anonymous source occurrence and to Element 4's
independently validated *read-only* planning decision.

Only explicit native source_location / covered_source_locations can establish
per-action origin; guessing from actor names, time ranges or lexical CED
similarity would fabricate source attribution. All others remain LEGACY.
The implementation deliberately uses stdlib + registered action policy so
the Unreal embedded Python process can reverify the unchanged evidence.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

import feature_dispatch
import studio_element_native_execution as native

VERSION = "1"
KIND = "cutsceneai.studio.element5_source_bound_conversion_plan"
MAX_OCCURRENCES = 30000
MAX_ACTIONS = native.MAX_ACTIONS
_BLOCKED = frozenset({
    "SOURCE_DEPENDENCY_MISSING", "DEPENDENCY_CYCLE",
    "OWNERSHIP_CONFLICT", "UPSTREAM_BLOCKED",
    "UPSTREAM_NOT_PLANNED",
})


class SourceBoundPlanError(ValueError):
    """The prepared native plan is not reconciled with exact source evidence."""


def _digest(document: Any) -> str:
    return hashlib.sha256(json.dumps(
        document, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _mapped(row: dict, mapping: dict) -> str:
    """Only existence of a source name->target reference, not target readback."""
    kind = row["kind"]
    if kind not in {"entities", "assets"}:
        return "NOT_DIRECTLY_APPLICABLE"
    source = row["_source_payload"]
    name = source.get("name") if isinstance(source, dict) else None
    destination = mapping.get(kind)
    if (not isinstance(name, str) or not name
            or not isinstance(destination, dict)
            or name not in destination):
        return "NO_TARGET_REFERENCE"
    item = destination[name]
    if kind == "entities":
        valid = isinstance(item, dict) and isinstance(item.get("actor_label"), str)
        valid = valid and bool(item["actor_label"])
    else:
        valid = isinstance(item, str) and bool(item)
        if isinstance(item, dict):
            valid = bool(item.get("unreal_asset_path") or item.get("asset_path"))
    return "TARGET_REFERENCE_DECLARED_UNVERIFIED" if valid else "NO_TARGET_REFERENCE"


def build(
    csir: dict, mapping: dict, native_plan: dict,
    element_plan: dict, element_schedule: dict,
    element_strategy: dict, element4_validation: dict,
) -> dict[str, Any]:
    """Reconcile complete source and installed native plan without writes.

    Does not approve AI alternatives, reorder native actions, infer unsupported
    semantics, or label a compiled action as an executed/verified conversion.
    """
    if (not isinstance(csir, dict) or not isinstance(mapping, dict)
            or not isinstance(native_plan, dict)
            or not isinstance(element_plan, dict)
            or not isinstance(element_schedule, dict)
            or not isinstance(element_strategy, dict)
            or not isinstance(element4_validation, dict)):
        raise SourceBoundPlanError("Exact source, target and Element 4 records are required.")
    if (mapping.get("overwrite_sequence") is True
            or native_plan.get("overwrite_sequence") is True
            or mapping.get("sequence_asset_path") != native_plan.get("sequence_asset_path")
            or not isinstance(mapping.get("sequence_asset_path"), str)
            or not mapping["sequence_asset_path"].startswith("/Game/")):
        raise SourceBoundPlanError("Prepared native sequence is missing, foreign or overwritable.")
    if (element_plan.get("kind") != "cutsceneai.studio.element_conversion_plan"
            or element_plan.get("no_native_execution_permission") is not True
            or element_plan.get("native_conversion_executed") is not False
            or element_plan.get("source_csir_sha256") != _digest(csir)
            or element_plan.get("element_plan_sha256") != _digest({
                key: value for key, value in element_plan.items()
                if key != "element_plan_sha256"
            })):
        raise SourceBoundPlanError("Element 3 source plan is missing or altered.")
    if (element_schedule.get("element_plan_sha256")
            != element_plan["element_plan_sha256"]
            or element_schedule.get("schedule_sha256") != _digest({
                key: value for key, value in element_schedule.items()
                if key != "schedule_sha256"
            })
            or element_schedule.get("native_execution_permitted") is not False):
        raise SourceBoundPlanError("Dependency ownership schedule is missing or altered.")
    if (element_strategy.get("element_plan_sha256")
            != element_plan["element_plan_sha256"]
            or element_strategy.get("dependency_schedule_sha256")
            != element_schedule["schedule_sha256"]
            or element_strategy.get("comparison_sha256") != _digest({
                key: value for key, value in element_strategy.items()
                if key != "comparison_sha256"
            })
            or element_strategy.get("native_execution_authorized") is not False):
        raise SourceBoundPlanError("Contextual CED conversion strategy is missing or altered.")
    if (element4_validation.get("kind") != "cutsceneai.studio.element4_strategy_validation"
            or element4_validation.get("element_plan_sha256")
            != element_plan["element_plan_sha256"]
            or element4_validation.get("dependency_schedule_sha256")
            != element_schedule["schedule_sha256"]
            or element4_validation.get("adaptive_strategy_sha256")
            != element_strategy["comparison_sha256"]
            or element4_validation.get("validation_sha256") != _digest({
                key: value for key, value in element4_validation.items()
                if key != "validation_sha256"
            })
            or element4_validation.get("source_csir_sha256")
            != element_plan["source_csir_sha256"]
            or element4_validation.get("accepted_for_source_bound_plan") is not True
            or element4_validation.get("native_execution_authorized") is not False
            or element4_validation.get("full_cutscene_fidelity_verified") is not False):
        raise SourceBoundPlanError("Element 4 has not validated the selected source plan.")
    rows = feature_dispatch._source_rows(csir)
    elements = element_plan.get("elements")
    if (not isinstance(elements, list)
            or len(rows) != len(elements)
            or len(rows) != element_plan.get("source_occurrence_count")
            or len(rows) > MAX_OCCURRENCES):
        raise SourceBoundPlanError("The source conversion inventory is incomplete.")
    actual_locations: dict[str, dict] = {}
    for index, (source, element) in enumerate(zip(rows, elements)):
        if (not isinstance(element, dict)
                or element.get("occurrence_id") != f"E{index:05d}"
                or element.get("source_location") != source["source_location"]
                or element.get("source_kind") != source["kind"]):
            raise SourceBoundPlanError("An occurrence was added, omitted or reordered.")
        if (source["source_location"] in actual_locations):
            raise SourceBoundPlanError("A duplicate source location cannot own native actions.")
        actual_locations[source["source_location"]] = element

    try:
        registered = native.inventory(native_plan, element_plan, element_strategy)
    except (native.ElementNativeExecutionError, feature_dispatch.FeatureDispatchError,
            TypeError, KeyError, ValueError) as exc:
        raise SourceBoundPlanError(
            "Compiled native action list contains unregistered or ungrounded operations."
        ) from exc
    if registered["action_count"] > MAX_ACTIONS:
        raise SourceBoundPlanError("Native action budget exceeded.")
    if registered["action_count"] != len(native_plan["actions"]):
        raise SourceBoundPlanError("Native action ledger silently dropped builder actions.")
    actions = []
    links: dict[str, list[str]] = {
        e["occurrence_id"]: [] for e in elements
    }
    for row in registered["actions"]:
        action_id = row["action_id"]
        for source_id in row["source_occurrence_ids"]:
            if source_id not in links:
                raise SourceBoundPlanError("Native action refers to unknown source occurrence.")
            links[source_id].append(action_id)
        actions.append({
            "action_id": action_id,
            "builder_action_index": row["index"],
            "kind": row["kind"],
            "immutable_payload_sha256": row["action_sha256"],
            "source_occurrence_ids": list(row["source_occurrence_ids"]),
            "source_attribution": row["source_attribution"],
            "source_context_eligible": row["native_action_eligible"],
            "source_blocker": row["native_action_blocker"],
            "native_preflight_required": True,
            "native_execution_verified": False,
            "target_readback_verified": False,
            "cinematic_fidelity_verified": False,
        })
    statuses = {
        item["occurrence_id"]: item["status"]
        for item in element_schedule.get("nodes", [])
        if isinstance(item, dict)
    }
    if len(statuses) != len(elements):
        raise SourceBoundPlanError("Dependency schedule does not cover every source occurrence.")

    occurrence_rows = []
    for source, element in zip(rows, elements):
        ident = element["occurrence_id"]
        mapping_status = _mapped(source, mapping)
        attributed = links[ident]
        if attributed:
            state = "EXPLICIT_NATIVE_SOURCE_PROVENANCE_PREPARED_UNVERIFIED"
            if any(not actions[int(v[1:])]["source_context_eligible"] for v in attributed):
                state = "BLOCKED_SOURCE_CONTEXT_ACTION"
        elif element["state"] == "UNKNOWN_SEMANTIC_INVESTIGATE":
            state = "UNKNOWN_SEMANTIC_RETAINED_FOR_INVESTIGATION"
        elif element["unresolved_dependencies"] or statuses[ident] in _BLOCKED:
            state = "UNRESOLVED_SOURCE_GRAPH"
        elif mapping_status == "NO_TARGET_REFERENCE":
            state = "TARGET_REFERENCE_NOT_MAPPED"
        else:
            state = "NO_EXPLICIT_NATIVE_SOURCE_ACTION_PROVENANCE"
        occurrence_rows.append({
            "occurrence_id": ident,
            "source_kind": element["source_kind"],
            "ced": element["ced"],
            "source_location": element["source_location"],
            "dependencies": list(element["dependencies"]),
            "mapping_status": mapping_status,
            "source_graph_status": statuses[ident],
            "registered_candidate_actions": list(element["candidate_actions"]),
            "selected_advisory_action": element["selected_action"],
            "explicitly_attributed_action_ids": attributed,
            "conversion_plan_state": state,
            "native_execution_verified": False,
            "target_readback_verified": False,
            "cinematic_fidelity_verified": False,
        })
    counts = Counter(row["conversion_plan_state"] for row in occurrence_rows)
    result = {
        "kind": KIND,
        "schema_version": VERSION,
        "source_csir_sha256": _digest(csir),
        "target_mapping_sha256": _digest(mapping),
        "native_plan_sha256": _digest(native_plan),
        "target_sequence_identity_sha256": _digest(
            native_plan["sequence_asset_path"]
        ),
        "element_plan_sha256": element_plan["element_plan_sha256"],
        "element_schedule_sha256": element_schedule["schedule_sha256"],
        "adaptive_strategy_sha256": element_strategy["comparison_sha256"],
        "element4_validation_sha256": element4_validation["validation_sha256"],
        "element4_status": element4_validation["validation_status"],
        "element4_basis": "SOURCE_INVENTORY_BASELINE_VALIDATED_READ_ONLY",
        "native_action_inventory_sha256": native.digest(registered),
        "source_occurrence_count": len(occurrence_rows),
        "action_count": len(actions),
        "explicit_source_action_count": sum(
            bool(action["source_occurrence_ids"]) for action in actions
        ),
        "legacy_unattributed_action_count": registered["unattributed_count"],
        "blocked_action_count": registered["blocked_action_count"],
        "mapped_source_occurrence_count": sum(
            row["mapping_status"] == "TARGET_REFERENCE_DECLARED_UNVERIFIED"
            for row in occurrence_rows
        ),
        "missing_target_reference_count": sum(
            row["mapping_status"] == "NO_TARGET_REFERENCE"
            for row in occurrence_rows
        ),
        "source_plan_states": dict(sorted(counts.items())),
        "native_builder_action_order_preserved": True,
        "native_preflight_complete": False,
        "target_readback_verified": False,
        "native_execution_authorized": False,
        "full_cutscene_fidelity_verified": False,
        "source_occurrences": occurrence_rows,
        "native_actions": actions,
    }
    result["source_bound_plan_sha256"] = _digest(result)
    return result


def verify(
    document: dict, csir: dict, mapping: dict, native_plan: dict,
    element_plan: dict, element_schedule: dict,
    element_strategy: dict, element4_validation: dict,
) -> None:
    """Recompute the *entire* evidence, not only the caller's new checksum."""
    if not isinstance(document, dict) or document != build(
        csir, mapping, native_plan, element_plan, element_schedule,
        element_strategy, element4_validation,
    ):
        raise SourceBoundPlanError(
            "Source-bound conversion plan is stale, incomplete or altered."
        )
