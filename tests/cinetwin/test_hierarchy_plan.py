"""CineTwin actor hierarchy transfer planning regression tests."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))

from hierarchy_plan import HierarchyPlanError, plan_actor_hierarchy


def _csir():
    return {
        "cutscene_id": "generic-scene",
        "entities": [
            {"entity_id": "parent", "name": "Platform", "parent_entity_id": None},
            {"entity_id": "child", "name": "Prop", "parent_entity_id": "parent"},
            {"entity_id": "other", "name": "Character", "parent_entity_id": None},
        ],
    }


def _mapping():
    return {"entities": {
        "Platform": {"actor_label": "TargetPlatform"},
        "Prop": {"actor_label": "TargetProp"},
        "Character": {"actor_label": "TargetCharacter"},
    }}


def test_direct_parent_attachment_is_planned_without_asset_changes():
    src, mapping = _csir(), _mapping()
    result = plan_actor_hierarchy(src, mapping)
    assert result["kind"] == "cinetwin.target_hierarchy_plan"
    assert result["mapped_source_entity_count"] == 3
    assert result["planned_actor_attachments"] == [
        {
            "entity_id": "child",
            "entity_name": "Prop",
            "actor_label": "TargetProp",
            "source_parent_entity_id": "parent",
            "source_parent_name": "Platform",
            "parent_actor_label": "TargetPlatform",
            "attachment_rule": "KEEP_WORLD",
            "socket": "",
        }
    ]
    assert result["unresolved_source_parents"] == []
    assert len(result["mapped_source_roots"]) == 2
    assert src == _csir()
    assert mapping == _mapping()


def test_unmapped_parent_does_not_silently_attach_to_a_grandparent():
    src = _csir()
    src["entities"].insert(
        1, {"entity_id": "intermediate", "name": "Group", "parent_entity_id": "parent"}
    )
    src["entities"][2]["parent_entity_id"] = "intermediate"
    result = plan_actor_hierarchy(src, _mapping())
    assert result["planned_actor_attachments"] == []
    assert result["unresolved_source_parents"][0]["reason"] == (
        "SOURCE_PARENT_NOT_MAPPED_AS_ACTOR"
    )


def test_missing_source_parent_is_a_hard_error():
    src = _csir()
    src["entities"][1]["parent_entity_id"] = "missing"
    with pytest.raises(HierarchyPlanError, match="missing source parent"):
        plan_actor_hierarchy(src, _mapping())


def test_cyclic_hierarchy_is_blocked_before_planning():
    src = _csir()
    src["entities"][0]["parent_entity_id"] = "child"
    with pytest.raises(HierarchyPlanError, match="Cycle"):
        plan_actor_hierarchy(src, _mapping())


def test_duplicate_mapped_actor_is_blocked():
    mapping = _mapping()
    mapping["entities"]["Prop"]["actor_label"] = "TargetPlatform"
    with pytest.raises(HierarchyPlanError, match="one target actor"):
        plan_actor_hierarchy(_csir(), mapping)


def test_duplicate_source_id_and_mapped_name_are_blocked():
    src = _csir()
    src["entities"].append({
        "entity_id": "parent", "name": "OtherParent",
        "parent_entity_id": None,
    })
    with pytest.raises(HierarchyPlanError, match="unique"):
        plan_actor_hierarchy(src, _mapping())
    src["entities"][-1]["entity_id"] = "duplicate"
    src["entities"][-1]["name"] = "Prop"
    with pytest.raises(HierarchyPlanError, match="ambiguous"):
        plan_actor_hierarchy(src, _mapping())


def test_unmapped_source_entities_do_not_require_target_actors():
    mapping = _mapping()
    del mapping["entities"]["Character"]
    result = plan_actor_hierarchy(_csir(), mapping)
    assert result["mapped_source_entity_count"] == 2
    assert len(result["planned_actor_attachments"]) == 1
