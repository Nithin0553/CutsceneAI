"""Registered package adapters consume typed authoring evidence from the census."""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for relative in ("integrations/unreal", "packages/cinetwin", "packages/studio"):
    sys.path.insert(0, str(ROOT / relative))

import closed_loop_evaluation
import feature_dispatch
import source_surface_gap
import transfer_backend
from test_adaptive_components import _native_light_inputs
from test_static_collider_adapters import _plan

FIXTURE_CLASS = "Demo.Cinematic.ShadowIntent"
PACKAGE = "com.demo.cinematic"


def _package_inputs(tmp_path):
    paths, (csir, mapping, census) = _native_light_inputs(tmp_path)
    census["installed_packages"] = [{"name": PACKAGE, "version": "1.2.3"}]
    row = census["loaded_scene_components"][-1]
    row.update({
        "component_type": FIXTURE_CLASS, "component_assembly": "Demo.Cinematic",
        "component_assembly_version": "1.0.0.0", "component_package": PACKAGE,
        "component_package_version": "1.2.3",
        "feature": {
            "extraction": "SERIALIZED_COMPONENT_AUTHORING_SNAPSHOT_V1",
            "native_properties_truncated": False, "has_behaviour_enabled": True,
            "behaviour_enabled": True, "game_object_active": True,
            "native_properties": [
                {"path": "cast", "native_type": "bool", "bool_value": True},
                {"path": "offset", "native_type": "vector3",
                 "vector_value": {"x": 0, "y": 1, "z": 2}},
                {"path": "color", "native_type": "color",
                 "color_value": {"r": 0.25, "g": 0.5, "b": 2, "a": 1}},
                {"path": "refs", "native_type": "array", "array_size": 1},
                {"path": "refs.Array.data[0]", "native_type": "object_reference",
                 "object_reference_is_null": False, "object_reference_missing": False,
                 "object_reference_global_id": "mesh-native-id",
                 "object_reference_asset_path": "Assets/Meshes/Stand.fbx",
                 "object_reference_guid": "a" * 32},
            ],
        },
    })
    return paths, (csir, mapping, census)


def _install_fixture_adapter(monkeypatch):
    original = transfer_backend._installed_ced_handlers

    def planner(csir, mapping, row, target):
        if not source_surface_gap.source_capture_valid(row):
            raise feature_dispatch.ComponentEvidenceError("INVALID_SERIALIZED_SHADOW_INTENT")
        feat = row["feature"]
        rows = [p for p in feat["native_properties"] if p["path"] == "cast"]
        if len(rows) != 1 or rows[0]["native_type"] != "bool" or not feat["behaviour_enabled"]:
            raise feature_dispatch.ComponentEvidenceError("MISSING_AUTHORED_SHADOW_INTENT")
        spec = original().component_for("UnityEngine.Light")
        return spec.planner(csir, mapping, {**row, "feature": {
            "has_cast_shadows": True, "cast_shadows": rows[0]["bool_value"],
        }}, target)

    def registry():
        installed = original()
        native = installed.component_for("UnityEngine.Light")
        installed.register_component(dataclasses.replace(
            native, source_type=FIXTURE_CLASS, source_assembly="Demo.Cinematic",
            source_package=PACKAGE, source_package_versions=("1.2.3",),
            adapter_id="demo_cinematic_shadow_intent", required_fields=("native_properties",),
            planner=planner,
        ))
        return installed

    monkeypatch.setattr(transfer_backend, "_installed_ced_handlers", registry)


def test_unregistered_package_capture_retains_exact_identity_and_no_action(tmp_path):
    plan, report, _ = _plan(*_package_inputs(tmp_path))
    assert not any(action.get("source_component_id") for action in plan["actions"])
    records = report["component_transfer_ledger"]["records"]
    captured = records[-1]
    assert captured["source_component_package"] == PACKAGE
    assert captured["source_component_package_version"] == "1.2.3"
    assert captured["source_component_assembly"] == "Demo.Cinematic"
    assert captured["next_required_gate"] == "INSTALL_NATIVE_ADAPTER_AND_VERIFY"
    assert not captured["target_action_planned"]


def test_adapter_registration_converts_installed_package_without_transfer_core_changes(
    tmp_path, monkeypatch,
):
    _install_fixture_adapter(monkeypatch)
    plan, report, _ = _plan(*_package_inputs(tmp_path))
    action, = [action for action in plan["actions"] if action.get("source_component_id")]
    assert action["kind"] == "property_bool"
    assert action["source_component_type"] == FIXTURE_CLASS
    assert action["keys"] == [{"frame": 0, "value": True}]
    assert report["component_transfer_ledger"]["records"][-1]["target_action_planned"]
    assert not action["behavior_fidelity_verified"]


@pytest.mark.parametrize(("changed", "state"), [
    ("package", "SOURCE_COMPONENT_PACKAGE_OR_VERSION_UNSUPPORTED"),
    ("uninstalled", "INSTALLED_SOURCE_PACKAGE_IDENTITY_REQUIRED"),
    ("target", "TARGET_ENGINE_VERSION_UNSUPPORTED"),
    ("missing_reference", "INVALID_SERIALIZED_SHADOW_INTENT"),
])
def test_package_scope_and_invalid_dependency_keep_actions_unplanned(
    tmp_path, monkeypatch, changed, state,
):
    _install_fixture_adapter(monkeypatch)
    paths, (csir, mapping, census) = _package_inputs(tmp_path)
    mapping["require_complete_source_features"] = False
    row = census["loaded_scene_components"][-1]
    if changed == "package":
        row["component_package_version"] = "2.0.0"
    elif changed == "uninstalled":
        census["installed_packages"].clear()
    elif changed == "target":
        mapping["target_engine_version"] = "5.3.2"
    else:
        row["feature"]["native_properties"][-1]["object_reference_missing"] = True
    plan, report, _ = _plan(paths, (csir, mapping, census))
    assert not any(action.get("source_component_id") for action in plan["actions"])
    assert report["adaptive_components"]["decisions"][-1]["status"] == state
    if changed == "missing_reference":
        assert report["source_feature_surface"]["component_counts"][
            "CUSTOM_COMPONENT_REFERENCE_UNRESOLVED"
        ] == 1


def test_agent_catalog_omits_raw_package_data_and_does_not_authorize_repairs():
    records = [{
        "adapter_id": "vendor.shadow", "version": "1.2.3", "semantic": "light.shadow",
        "source_path": "private/asset", "source_payload": "a script",
        "can_request_repair": True, "behavior_verified": True,
    }, {"adapter_id": "invalid/untrusted", "version": "1.0", "semantic": "shader.custom"}]
    report = closed_loop_evaluation.evaluate(None, None, coverage={
        "adaptive_components": {
            "installed_component_adapters": records,
            "decisions": [{"adapter_id": "vendor.shadow", "actions": ["property_bool"]}],
        },
    })
    assert report["component_adapter_catalog"] == [{
        "adapter_id": "vendor.shadow", "version": "1.2.3", "semantic": "light.shadow",
        "planned_occurrences": 1, "can_request_repair": False, "behavior_verified": False,
    }]
