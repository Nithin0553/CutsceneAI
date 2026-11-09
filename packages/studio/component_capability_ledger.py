"""Per-source-component capability accounting, independent of component class.

This is a source-side ledger, NOT proof of target reconstruction. Future
target adapters must supply their own immutable plan/native/behavior receipts.
Every component, including unknown vendor types, gets a deterministic row.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

_DISCOVERED = "DISCOVERED_SOURCE_INCOMPLETE"
_SOURCE_STRUCTURAL = "SOURCE_STRUCTURAL_RECORDED_TARGET_UNVERIFIED"
_SOURCE_PARTIAL = "SOURCE_CAPTURED_PARTIAL_TARGET_UNVERIFIED"
_INVALID = "SOURCE_IDENTITY_OR_SCOPE_INVALID"

_IDENTITY_STATES = frozenset({
    "SOURCE_OBJECT_IDENTITY_MISMATCH", "SOURCE_OBJECT_IDENTITY_UNVERIFIED",
    "DUPLICATE_SOURCE_ENTITY_PATH", "DUPLICATE_SOURCE_COMPONENT_IDENTITY",
})
_KNOWN_STATES = frozenset({
    "SOURCE_OBJECT_TRANSFORM_IDENTIFIED",
    "SOURCE_COMPONENT_SEMANTIC_REQUIRES_TARGET_EVIDENCE",
})


def from_source_findings(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Preserve every source occurrence without inferring unimplemented adapters."""
    if not isinstance(cases, list):
        raise ValueError("Component findings must be a list.")
    ledger = []
    seen = set()
    for position, item in enumerate(cases):
        if not isinstance(item, Mapping):
            raise ValueError("Source component finding must be an object.")
        scene = str(item.get("scene_path") or "")
        path = str(item.get("hierarchy_path") or "")
        component = str(item.get("native_component") or "")
        source_id = str(item.get("source_component_id") or "")
        raw_state = str(item.get("state") or "")
        if not scene or not path or not component or not raw_state:
            raise ValueError("Missing source component identity or state.")
        occurrence = (scene, path, component, source_id)
        identity_conflict = occurrence in seen or raw_state in _IDENTITY_STATES
        seen.add(occurrence)
        if identity_conflict:
            stage = _INVALID
            next_gate = "REPAIR_SOURCE_IDENTITY"
        elif raw_state == "SOURCE_COMPONENT_SNAPSHOT_PARTIAL_TARGET_UNVERIFIED":
            stage = _SOURCE_PARTIAL
            next_gate = "INSTALL_NATIVE_ADAPTER_AND_VERIFY"
        elif raw_state in _KNOWN_STATES:
            stage = _SOURCE_STRUCTURAL
            next_gate = "VERIFY_TARGET_ADAPTER_READBACK_AND_BEHAVIOR"
        else:
            stage = _DISCOVERED
            next_gate = "IMPLEMENT_TYPED_SOURCE_EXTRACTION"
        ledger.append({
            "source_occurrence_index": position,
            "source_scene": scene,
            "source_hierarchy_path": path,
            "source_entity_id": item.get("source_entity_id"),
            "source_component_id": source_id,
            "source_native_type": component,
            "source_finding": raw_state,
            "source_stage": stage,
            "next_required_gate": next_gate,
            "target_action_planned": False,
            "native_target_verified": False,
            "behavior_verified": False,
        })
    counts = Counter(row["source_stage"] for row in ledger)
    return {
        "kind": "cutsceneai.component_capability_ledger",
        "schema_version": "0.1.0",
        "records": ledger,
        "source_stage_counts": dict(sorted(counts.items())),
        "source_occurrence_count": len(ledger),
        "native_target_verified": False,
        "behavior_verified": False,
        "no_full_fidelity_claim": True,
    }
