"""Regression for the two missing parented props in a Studio-generated sequence.

Exercise the real source-hierarchy planners, not a fake attachment flag.
These are source-to-plan tests; Unreal persistence still needs a fresh editor run.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for directory in ("integrations/unreal", "packages/cinetwin", "packages/studio"):
    entry = str(ROOT / directory)
    if entry not in sys.path:
        sys.path.insert(0, entry)

import hierarchy_local
import hierarchy_realization


def _source():
    return {
        "cutscene_id": "props-with-hierarchy",
        "entities": [
            {"entity_id": "parent", "name": "PROP_MOVING",
             "ced_type": "entity.prop", "parent_entity_id": None},
            {"entity_id": "child1", "name": "MovingPropMesh",
             "ced_type": "entity.prop", "parent_entity_id": "parent"},
            {"entity_id": "child2", "name": "PROP_PARENTED",
             "ced_type": "entity.prop", "parent_entity_id": "parent"},
        ],
    }


def _mapping():
    return {"entities": {
        "PROP_MOVING": {"actor_label": "CSAI_PROP_MOVING"},
        "MovingPropMesh": {"actor_label": "CSAI_MovingPropMesh"},
        "PROP_PARENTED": {"actor_label": "CSAI_PROP_PARENTED"},
    }, "enable_cinetwin_hierarchy": True}


def _actions():
    return [
        {"kind": "transform", "entity_name": "PROP_MOVING",
         "actor_label": "CSAI_PROP_MOVING",
         "source_behavior_strategy": "captured_untracked_world_motion",
         "keys": [{"frame": 0, "location_cm": [0, 0, 0],
                   "rotation_rpy_degrees": [0, 0, 0]},
                  {"frame": 24, "location_cm": [100, 0, 0],
                   "rotation_rpy_degrees": [0, 0, 0]}]},
        *[{"kind": "transform", "entity_name": name,
           "actor_label": label,
           "source_behavior_strategy": "source_static_world_pose",
           "keys": [{"frame": 0, "location_cm": [30, 0, 0],
                     "rotation_rpy_degrees": [0, 0, 0]}]}
          for name, label in (
              ("MovingPropMesh", "CSAI_MovingPropMesh"),
              ("PROP_PARENTED", "CSAI_PROP_PARENTED"))],
    ]


def test_two_source_child_props_are_prepared_for_real_unreal_attachments():
    actions, decisions = hierarchy_local.reconcile_hierarchy(
        _source(), _mapping(), _actions(), None
    )
    assert len([a for a in actions if a["kind"] == "transform"]) == 1
    assert {r["entity_name"] for r in decisions} == {
        "MovingPropMesh", "PROP_PARENTED"
    }
    assert all(r["outcome"] == "STATIC_CHILD_INHERITS_PARENT" for r in decisions)
    operations = hierarchy_realization.build_attachment_operations(
        _source(), _mapping(), actions
    )
    assert len(operations["attachments"]) == 2
    assert all(edge["parent_actor_label"] == "CSAI_PROP_MOVING"
               for edge in operations["attachments"])
    assert all(edge["attachment_rule"] == "KEEP_WORLD"
               for edge in operations["attachments"])
    assert operations["parent_initializations"][0]["entity_name"] == "PROP_MOVING"


def test_animated_child_without_parent_local_evidence_cannot_be_attached():
    actions = _actions()
    child = next(a for a in actions if a["entity_name"] == "PROP_PARENTED")
    child["source_behavior_strategy"] = "source_animated_world_transform"
    with pytest.raises(hierarchy_local.HierarchyLocalError,
                       match="requires verified CineTwin capture"):
        hierarchy_local.reconcile_hierarchy(_source(), _mapping(), actions, None)
    with pytest.raises(hierarchy_realization.HierarchyRealizationError,
                       match="requires conversion to parent-local"):
        hierarchy_realization.build_attachment_operations(_source(), _mapping(), actions)


def test_unmapped_intermediate_source_parent_is_never_silently_bypassed():
    src = _source()
    src["entities"].append(
        {"entity_id": "helper", "name": "Intermediate",
         "ced_type": "entity.prop", "parent_entity_id": "parent"}
    )
    src["entities"][1]["parent_entity_id"] = "helper"
    actions, decisions = hierarchy_local.reconcile_hierarchy(
        src, _mapping(), _actions(), None
    )
    operations = hierarchy_realization.build_attachment_operations(src, _mapping(), actions)
    assert not any(x["entity_name"] == "MovingPropMesh"
                   for x in operations["attachments"])
    assert any(x["entity_name"] == "MovingPropMesh"
               for x in operations["unresolved_source_parents"])
    assert len(decisions) == 1
