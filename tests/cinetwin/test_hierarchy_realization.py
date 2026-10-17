"""Test safe, engine-independent actor-attachment realization planning."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))

from hierarchy_realization import (
    HierarchyRealizationError,
    build_attachment_operations,
)


def _source():
    return {
        "cutscene_id": "fixture",
        "entities": [
            {"entity_id": "platform", "name": "Platform", "parent_entity_id": None},
            {"entity_id": "child", "name": "Child", "parent_entity_id": "platform"},
            {"entity_id": "nested", "name": "Nested", "parent_entity_id": "child"},
            {"entity_id": "unresolved", "name": "Camera", "parent_entity_id": "unknown"},
        ],
    }


def _inputs():
    src = _source()
    src["entities"].pop()
    mapping = {"entities": {
        "Platform": {"actor_label": "P"},
        "Child": {"actor_label": "C"},
        "Nested": {"actor_label": "N"},
    }}
    return src, mapping


def test_direct_parent_edges_topologically_sorted_and_keep_world():
    source, mapping = _inputs()
    operations = build_attachment_operations(source, mapping, [])
    assert [
        (item["actor_label"], item["parent_actor_label"])
        for item in operations["attachments"]
    ] == [("C", "P"), ("N", "C")]
    assert operations["policy"] == "KEEP_WORLD_AT_PARENT_INITIAL_KEY"
    assert operations["parent_initializations"] == []
    assert operations["requires_level_save"] is True


def test_parent_animated_world_keys_initialize_before_child_attach():
    source, mapping = _inputs()
    actions = [{
        "kind": "transform",
        "entity_name": "Platform",
        "keys": [
            {"frame": 24, "time_seconds": 1.0,
             "location_cm": [-100, 0, 0], "rotation_rpy_degrees": [0, 0, 0]},
            {"frame": 0, "time_seconds": 0.0,
             "location_cm": [-5, 10, 0], "rotation_rpy_degrees": [0, 0, 0]},
        ],
    }]
    result = build_attachment_operations(source, mapping, actions)
    first = result["parent_initializations"][0]
    assert first["entity_name"] == "Platform"
    assert first["first_frame"] == 0
    assert first["location_cm"] == [-5, 10, 0]


def test_static_child_world_transform_track_blocks_double_transform():
    source, mapping = _inputs()
    actions = [{
        "kind": "transform",
        "entity_name": "Child",
        "keys": [{"frame": 0}],
    }]
    with pytest.raises(HierarchyRealizationError, match="parent-local space"):
        build_attachment_operations(source, mapping, actions)


def test_child_skeletal_root_correction_blocks_unverified_composition():
    source, mapping = _inputs()
    actions = [{
        "kind": "skeletal_animation",
        "entity_name": "Child",
        "root_motion_correction_samples": [{"frame": 0}],
    }]
    with pytest.raises(HierarchyRealizationError, match="parent-local space"):
        build_attachment_operations(source, mapping, actions)


def test_multiple_parent_world_tracks_block_initialization():
    source, mapping = _inputs()
    a = {
        "kind": "transform", "entity_name": "Platform",
        "keys": [{"frame": 0, "time_seconds": 0.0,
                  "location_cm": [0, 0, 0],
                  "rotation_rpy_degrees": [0, 0, 0]}],
    }
    with pytest.raises(HierarchyRealizationError, match="multiple"):
        build_attachment_operations(source, mapping, [a, a])


def test_omits_unresolved_parent_without_changing_source_relationships():
    source, mapping = _inputs()
    source["entities"].append({
        "entity_id": "groupchild", "name": "Extra",
        "parent_entity_id": "nested",
    })
    mapping["entities"]["Extra"] = {"actor_label": "ExtraActor"}
    del mapping["entities"]["Nested"]
    result = build_attachment_operations(source, mapping, [])
    assert len(result["unresolved_source_parents"]) == 1
    assert result["unresolved_source_parents"][0]["entity_name"] == "Extra"


def test_cycle_is_blocked_before_actor_mutation():
    source, mapping = _inputs()
    source["entities"][0]["parent_entity_id"] = "nested"
    with pytest.raises(HierarchyRealizationError, match="Cycle"):
        build_attachment_operations(source, mapping, [])


def test_builder_feature_flag_and_exception_rollback_are_explicit():
    builder = (
        ROOT / "integrations" / "unreal" / "build_level_sequence.py"
    ).read_text(encoding="utf-8")
    runtime = (
        ROOT / "integrations" / "unreal" / "cinetwin_hierarchy_runtime.py"
    ).read_text(encoding="utf-8")
    ast.parse(builder)
    ast.parse(runtime)
    assert 'mapping.get("enable_cinetwin_hierarchy", False)' in builder
    assert builder.index("build_attachment_operations(") < builder.index("_apply_scene_prep(csir")
    assert "rollback_hierarchy(attachment_changes)" in builder
    assert "get_attach_parent_actor()" in runtime
    assert "unreal.AttachmentRule.KEEP_WORLD" in runtime
    assert "weld_simulated_bodies=False" in runtime
    assert "False\\n            )" not in runtime  # explicit positional False is used
    assert "save_current_level" not in runtime
    assert "save_loaded_asset" not in runtime
