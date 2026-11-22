"""Element 3 native-dispatch authorization for the EXISTING Unreal builder.

Approvals bind the complete prepared transfer action list to the active
candidate and native operator consent. They never select executable Python,
change action arguments, bypass the builder's source recomputation/preflight,
or establish per-element target fidelity.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import feature_dispatch
import studio_element_plan

KIND = "cutsceneai.studio.element_native_dispatch_authorization"
RECEIPT_KIND = "cutsceneai.studio.element_native_dispatch_receipt"
MAX_ACTIONS = 30000
SHA = re.compile(r"[a-f0-9]{64}\Z")


class ElementNativeExecutionError(ValueError):
    """An action is unregistered, unapproved or not bound to its exact plan."""


def digest(value: Any) -> str:
    return studio_element_plan._digest(value)


def sha(path: Path) -> str:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 64 * 1024 * 1024:
        raise ElementNativeExecutionError("Prepared native plan file missing or unsafe.")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(plan: dict, element_plan: dict) -> dict:
    """One immutable ledger row per installed native builder action.

    Source attribution is intentionally conservative. Legacy CSIR actions
    without explicit exact-source locations are marked UNATTRIBUTED; matching
    names or timestamps heuristically is never native provenance.
    """
    feature_dispatch.verify_executable_actions(plan)
    actions = plan["actions"]
    if len(actions) > MAX_ACTIONS:
        raise ElementNativeExecutionError("Native action inventory exceeds safe bound.")
    if (element_plan.get("kind") != "cutsceneai.studio.element_conversion_plan"
            or element_plan.get("no_native_execution_permission") is not True):
        raise ElementNativeExecutionError("A source-bound Element 3 inventory is required.")
    locations = {
        row["source_location"]: row
        for row in element_plan["elements"]
    }
    if len(locations) != element_plan["source_occurrence_count"]:
        raise ElementNativeExecutionError("Duplicated source occurrence in native action ledger.")
    rows = []
    for index, action in enumerate(actions):
        kind = action["kind"]
        provided = action.get("source_location")
        linked = []
        if provided is not None:
            if not isinstance(provided, str) or provided not in locations:
                raise ElementNativeExecutionError(
                    "Native action asserts a foreign source occurrence location."
                )
            element = locations[provided]
            if kind not in element["candidate_actions"]:
                raise ElementNativeExecutionError(
                    "Native action has no source-eligible registered CED mapping."
                )
            if (action.get("source_ced") is not None
                    and action["source_ced"] != element["ced"]):
                raise ElementNativeExecutionError(
                    "Native source semantic differs from the exact occurrence."
                )
            linked = [element["occurrence_id"]]
        covered = action.get("covered_source_locations")
        if covered is not None:
            if (not isinstance(covered, list)
                    or not covered
                    or len(covered) != len(set(covered))
                    or any(not isinstance(v, str) or v not in locations
                           for v in covered)):
                raise ElementNativeExecutionError(
                    "Native source-coverage proof is incomplete or ambiguous."
                )
            for location in covered:
                row = locations[location]
                if row["occurrence_id"] not in linked:
                    linked.append(row["occurrence_id"])
        rows.append({
            "action_id": f"A{index:05d}",
            "index": index,
            "kind": kind,
            "action_sha256": digest(action),
            "source_occurrence_ids": sorted(linked),
            "source_attribution": (
                "EXPLICIT_REGISTERED_SOURCE_LOCATION"
                if linked else "LEGACY_ACTION_SOURCE_ATTRIBUTION_UNVERIFIED"
            ),
            "native_preflight_required": True,
            "native_execution_verified": False,
            "cinematic_fidelity_verified": False,
        })
    return {
        "kind": "cutsceneai.studio.element_native_action_inventory",
        "schema_version": "1",
        "sequence_asset_path": plan["sequence_asset_path"],
        "element_plan_sha256": element_plan["element_plan_sha256"],
        "action_count": len(rows),
        "unattributed_count": sum(not row["source_occurrence_ids"] for row in rows),
        "registered_action_counts": dict(sorted(Counter(row["kind"] for row in rows).items())),
        "native_execution_authorized": False,
        "full_cutscene_fidelity_verified": False,
        "actions": rows,
    }


def authorize(inventory_doc: dict, *, candidate_id: str,
              workflow_sha256: str, transfer_plan_sha256: str,
              approved_action_ids: list[str],
              accept_legacy_unattributed: bool) -> dict:
    """Exact all-actions operator consent: never synthesize a partial plan."""
    if (inventory_doc.get("kind") != "cutsceneai.studio.element_native_action_inventory"
            or type(accept_legacy_unattributed) is not bool
            or type(candidate_id) is not str
            or type(workflow_sha256) is not str or not SHA.fullmatch(workflow_sha256)
            or type(transfer_plan_sha256) is not str
            or not SHA.fullmatch(transfer_plan_sha256)):
        raise ElementNativeExecutionError("Native operator authorization lacks exact source identity.")
    if (not isinstance(approved_action_ids, list)
            or len(approved_action_ids) != inventory_doc["action_count"]
            or any(type(v) is not str for v in approved_action_ids)
            or approved_action_ids != [row["action_id"] for row in inventory_doc["actions"]]):
        raise ElementNativeExecutionError(
            "The entire immutable prepared action set must be explicitly reviewed. "
            "Partial selections require preparing a different source-authenticated candidate."
        )
    if inventory_doc["unattributed_count"] and not accept_legacy_unattributed:
        raise ElementNativeExecutionError(
            "Legacy native actions lack source-occurrence provenance. "
            "A separate explicit acknowledgment is required."
        )
    result = {
        "kind": KIND,
        "schema_version": "1",
        "candidate_id": candidate_id,
        "workflow_sha256": workflow_sha256,
        "transfer_plan_sha256": transfer_plan_sha256,
        "action_inventory_sha256": digest(inventory_doc),
        "action_count": inventory_doc["action_count"],
        "unattributed_count": inventory_doc["unattributed_count"],
        "accept_legacy_unattributed": accept_legacy_unattributed,
        "approved_action_ids": approved_action_ids,
        "scope": "EXACT_PREPARED_NATIVE_ACTIONS_ONLY",
        "runtime_dispatched": False,
        "native_readback_verified": False,
        "full_cutscene_fidelity_verified": False,
    }
    result["authorization_sha256"] = digest(result)
    return result


def verify_authorization(approval: dict, inventory_doc: dict,
                         *, candidate_id: str, workflow_sha256: str,
                         transfer_plan_sha256: str) -> None:
    if not isinstance(approval, dict):
        raise ElementNativeExecutionError("Native action approval missing.")
    try:
        expected = authorize(
            inventory_doc, candidate_id=candidate_id,
            workflow_sha256=workflow_sha256,
            transfer_plan_sha256=transfer_plan_sha256,
            approved_action_ids=approval["approved_action_ids"],
            accept_legacy_unattributed=approval["accept_legacy_unattributed"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ElementNativeExecutionError("Native action approval invalid.") from exc
    if expected != approval:
        raise ElementNativeExecutionError(
            "Native action approval is stale, altered, or belongs to another candidate."
        )


def receipt(approval: dict, inventory_doc: dict, runtime_receipt: dict,
            *, job_id: str, native_receipt_sha256: str) -> dict:
    """Record that the exact approved builder completed, NOT per-element parity."""
    if (runtime_receipt.get("kind") != "cutsceneai.unreal.best_effort_receipt"
            or runtime_receipt.get("status") != "GENERATED_UNVERIFIED"
            or runtime_receipt.get("stage") != "complete"
            or runtime_receipt.get("transfer_plan_sha256") != approval.get("transfer_plan_sha256")
            or type(job_id) is not str or not re.fullmatch(r"[a-f0-9]{32}", job_id)
            or type(native_receipt_sha256) is not str
            or not SHA.fullmatch(native_receipt_sha256)):
        raise ElementNativeExecutionError(
            "Only a completed exact-plan native receipt may be linked to Element 3."
        )
    rows = []
    for action in inventory_doc["actions"]:
        rows.append({
            "action_id": action["action_id"],
            "action_sha256": action["action_sha256"],
            "kind": action["kind"],
            "source_occurrence_ids": action["source_occurrence_ids"],
            "status": "REGISTERED_BUILDER_COMPLETED_READBACK_NOT_PER_ACTION_VERIFIED",
        })
    result = {
        "kind": RECEIPT_KIND,
        "schema_version": "1",
        "candidate_id": approval["candidate_id"],
        "job_id": job_id,
        "workflow_sha256": approval["workflow_sha256"],
        "native_authorization_sha256": approval["authorization_sha256"],
        "runtime_receipt_sha256": native_receipt_sha256,
        "transfer_plan_sha256": approval["transfer_plan_sha256"],
        "action_count": len(rows),
        "native_builder_completed": True,
        "individual_native_action_readbacks_verified": False,
        "full_cutscene_fidelity_verified": False,
        "actions": rows,
    }
    result["dispatch_receipt_sha256"] = digest(result)
    return result
