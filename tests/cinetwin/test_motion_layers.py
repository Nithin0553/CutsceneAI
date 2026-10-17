"""Unit tests for carrier-aware CineTwin evaluated motion evidence."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))

from motion_layers import MotionLayerEvidenceError, analyze_motion_layers


def _data(
    *,
    actor_moves: bool = False,
    component_moves: bool = False,
    bone_moves: bool = False,
    attached: bool = True,
):
    plan = {
        "entities": [
            {"entity_id": "parent", "name": "Parent", "parent_entity_id": None},
            {"entity_id": "child", "name": "Child", "parent_entity_id": "parent"},
        ]
    }
    rigs = [{
        "entity_id": "child",
        "native_target_bones": [
            {"bone_name": "root", "parent_bone_name": None},
            {"bone_name": "hip", "parent_bone_name": "root"},
        ],
    }]
    samples = []
    for index in range(3):
        x = float(index)
        samples.append({
            "entities": [
                {
                    "entity_id": "parent", "actor_label": "ParentActor",
                    "world_transform": {"position_m": [0, 0, 0]},
                },
                {
                    "entity_id": "child", "actor_label": "ChildActor",
                    "world_transform": {
                        "position_m": [x if actor_moves else 0.0, 0.0, 0.0]
                    },
                },
            ],
            "motion_layers": [
                {
                    "entity_id": "parent", "actor_label": "ParentActor",
                    "attached_to_actor_label": None,
                    "components": [],
                },
                {
                    "entity_id": "child", "actor_label": "ChildActor",
                    "attached_to_actor_label": "ParentActor" if attached else None,
                    "components": [{
                        "component_path": "/World/Child/Body",
                        "world_transform": {
                            "position_m": [
                                x if component_moves else 0.0, 0.0, 0.0
                            ],
                        },
                    }],
                },
            ],
            "skeletal_poses": [{
                "entity_id": "child",
                "bones": [
                    {
                        "bone_name": "root",
                        "world_position_m": [
                            x if bone_moves else 0.0, 0.0, 0.0
                        ],
                    },
                    {
                        "bone_name": "hip",
                        "world_position_m": [0.0, 1.0, 0.0],
                    },
                ],
            }],
        })
    return plan, samples, rigs


def _child(*args, **kwargs):
    plan, samples, rigs = _data(*args, **kwargs)
    return next(
        item for item in analyze_motion_layers(plan, samples, rigs)
        if item["entity_id"] == "child"
    )


def test_component_motion_with_stationary_actor_is_detected():
    result = _child(component_moves=True)
    assert result["actor_motion_cm"] == 0.0
    assert result["max_component_motion_cm"] == 200.0
    assert result["motion_carrier_diagnostic"] == "COMPONENT_MOVES_ACTOR_STATIC"
    assert result["attachment_diagnostic"] == "ACTOR_ATTACHMENT_MATCH"


def test_root_bone_motion_with_stationary_actor_and_component():
    result = _child(bone_moves=True)
    assert result["skeletal_root_bone_motion_cm"]["root"] == 200.0
    assert result["motion_carrier_diagnostic"] == "SKELETAL_ROOT_MOVES_ACTOR_STATIC"


def test_actor_motion_precedes_component_and_bone_motion():
    result = _child(actor_moves=True, component_moves=True, bone_moves=True)
    assert result["motion_carrier_diagnostic"] == "ACTOR_TRANSFORM_MOVES"


def test_missing_expected_parent_actor_attachment_is_flagged():
    result = _child(attached=False)
    assert result["attachment_diagnostic"] == "ACTOR_ATTACHMENT_DIFFERS_FROM_SOURCE"


def test_all_static_is_not_misreported_as_animated():
    result = _child()
    assert (
        result["motion_carrier_diagnostic"]
        == "NO_TRANSLATION_OBSERVED_ON_ACTOR_COMPONENT_OR_ROOT_BONE"
    )


def test_component_topology_change_is_blocked():
    plan, samples, rigs = _data()
    samples[1]["motion_layers"][1]["components"][0]["component_path"] = "changed"
    with pytest.raises(MotionLayerEvidenceError, match="topology"):
        analyze_motion_layers(plan, samples, rigs)


def test_missing_native_root_bone_is_blocked():
    plan, samples, rigs = _data()
    samples[1]["skeletal_poses"][0]["bones"] = []
    with pytest.raises(MotionLayerEvidenceError, match="root bones"):
        analyze_motion_layers(plan, samples, rigs)


def test_nonfinite_component_observation_is_blocked():
    plan, samples, rigs = _data()
    samples[1]["motion_layers"][1]["components"][0]["world_transform"][
        "position_m"
    ][0] = float("nan")
    with pytest.raises(MotionLayerEvidenceError, match="nonfinite"):
        analyze_motion_layers(plan, samples, rigs)


def test_runtime_probe_is_read_only_and_optional():
    script = (
        ROOT / "integrations/unreal/cinetwin_tick_evaluator.py"
    ).read_text(encoding="utf-8")
    helper = (
        ROOT / "integrations/unreal/cinetwin_motion_layers.py"
    ).read_text(encoding="utf-8")
    ast.parse(script)
    ast.parse(helper)
    assert "capture_motion_layers: bool = False" in script
    assert "observe_actor_motion_layers" in script
    assert "analyze_motion_layers" in script
    assert "get_components_by_class(unreal.SceneComponent)" in helper
    assert "get_attach_parent_actor()" in helper
    assert "get_world_location()" in helper
    for name in ("set_editor_property(", "attach_to_actor(", "save_loaded_asset("):
        assert name not in helper
