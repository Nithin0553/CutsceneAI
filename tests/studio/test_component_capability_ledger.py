"""All Unity component families get explicit evidence stages, never fake parity."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "studio"))
import component_capability_ledger as ledger


def item(native_type, native_id, state):
    return {
        "scene_path": "Assets/Scenes/Example.unity",
        "hierarchy_path": "Example/Set/Tree",
        "source_entity_id": "tree",
        "native_component": native_type,
        "source_component_id": native_id,
        "state": state,
    }


def test_generic_unknown_and_known_components_keep_distinct_source_stages():
    values = [
        item("UnityEngine.Transform", "transform-1",
             "SOURCE_OBJECT_TRANSFORM_IDENTIFIED"),
        item("UnityEngine.MeshCollider", "collider-1",
             "SOURCE_COMPONENT_SNAPSHOT_PARTIAL_TARGET_UNVERIFIED"),
        item("UnityEngine.LODGroup", "lod-1",
             "SOURCE_COMPONENT_SNAPSHOT_PARTIAL_TARGET_UNVERIFIED"),
        item("Vendor.ProprietaryShader", "shader-1",
             "NATIVE_COMPONENT_EXTRACTION_OR_ADAPTER_REQUIRED"),
    ]
    result = ledger.from_source_findings(values)
    assert result["source_occurrence_count"] == 4
    assert [row["source_stage"] for row in result["records"]] == [
        "SOURCE_STRUCTURAL_RECORDED_TARGET_UNVERIFIED",
        "SOURCE_CAPTURED_PARTIAL_TARGET_UNVERIFIED",
        "SOURCE_CAPTURED_PARTIAL_TARGET_UNVERIFIED",
        "DISCOVERED_SOURCE_INCOMPLETE",
    ]
    assert result["records"][-1]["next_required_gate"] == (
        "IMPLEMENT_TYPED_SOURCE_EXTRACTION")
    assert not any(row["target_action_planned"] or row["native_target_verified"]
                   or row["behavior_verified"] for row in result["records"])
    assert result["no_full_fidelity_claim"]


def test_mismatched_or_duplicate_source_identity_never_gets_capture_credit():
    conflict = item("Vendor.Component", "component-x",
                    "SOURCE_COMPONENT_SNAPSHOT_PARTIAL_TARGET_UNVERIFIED")
    result = ledger.from_source_findings([conflict, conflict])
    assert result["records"][1]["source_stage"] == "SOURCE_IDENTITY_OR_SCOPE_INVALID"
    assert result["records"][1]["next_required_gate"] == "REPAIR_SOURCE_IDENTITY"
    different = item("Vendor.Component", "component-y",
                     "SOURCE_OBJECT_IDENTITY_MISMATCH")
    assert ledger.from_source_findings([different])["records"][0][
        "native_target_verified"] is False


def test_malformed_source_component_occurrence_is_rejected():
    with pytest.raises(ValueError, match="identity or state"):
        ledger.from_source_findings([{"native_component": "Vendor.Component"}])


def test_ledger_does_not_mutate_census_findings():
    rows = [item("Vendor.Component", "component-1",
                 "NATIVE_COMPONENT_EXTRACTION_OR_ADAPTER_REQUIRED")]
    before = [dict(x) for x in rows]
    ledger.from_source_findings(rows)
    assert rows == before
