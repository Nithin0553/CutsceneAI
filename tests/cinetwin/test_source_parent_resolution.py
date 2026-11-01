"""Source-only Unity container reasoning; these are NOT Unreal parity proofs."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))

from source_parent_resolution import analyze


def _world():
    return {"position": {"x": 3, "y": 0, "z": -2},
            "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
            "scale": {"x": 1, "y": 1, "z": 1}}


def _scene():
    group = {"entity_id": "group", "name": "SceneRoot", "ced_type": "entity.prop",
             "parent_entity_id": "", "metadata": {
                 "active_self": True, "hierarchy_path": "SceneRoot",
                 "world_transform": _world(),
                 "animator": {"apply_root_motion": False, "has_avatar": False}}}
    child = {"entity_id": "cam", "name": "CAM", "ced_type": "entity.camera",
             "parent_entity_id": "group", "metadata": {"world_transform": _world()}}
    return {"entities": [group, child], "tracks": []}, {
        "entities": {"CAM": {"actor_label": "CSAI_CAM"}}}


def test_static_world_pose_strategy_preserves_source_group_identity():
    scene, mapping = _scene()
    actions = [{"kind": "transform", "entity_name": "CAM",
                "source_behavior_strategy": "source_static_world_pose",
                "keys": [{"frame": 0}]}]
    result = analyze(scene, mapping, actions)
    assert result["total"] == 1
    assert result["static_pose_candidates"] == 1
    assert result["rows"][0]["ancestor_chain"][0]["name"] == "SceneRoot"
    assert result["rows"][0]["native_parent_actor_reconstructed"] is False
    assert result["rows"][0]["group_editability_preserved"] is False
    assert result["fidelity_verified"] is False


def test_captured_world_motion_is_explicitly_not_fidelity_verified():
    scene, mapping = _scene()
    actions = [{"kind": "transform", "entity_name": "CAM",
                "source_behavior_strategy": "verified_cinetwin_camera_world_pose",
                "keys": [{"frame": 0}, {"frame": 1}]}]
    result = analyze(scene, mapping, actions)
    assert result["captured_world_motion_candidates"] == 1
    assert result["rows"][0]["strategy"] == "CAPTURED_WORLD_MOTION_PLANNED_UNVERIFIED"


def test_animated_ancestor_requires_source_behavior_validation():
    scene, mapping = _scene()
    scene["tracks"] = [{"binding_entity_id": "group", "muted": False,
                         "sections": [{"start": 0, "end": 2}]}]
    actions = [{"kind": "transform", "entity_name": "CAM",
                "source_behavior_strategy": "source_static_world_pose",
                "keys": [{"frame": 0}]}]
    out = analyze(scene, mapping, actions)
    assert out["rows"][0]["strategy"] == "PARENT_BEHAVIOR_UNVERIFIED"


def test_missing_and_malformed_source_transform_never_qualifies_as_static():
    scene, mapping = _scene()
    scene["entities"][0]["metadata"]["world_transform"]["scale"]["z"] = 0
    out = analyze(scene, mapping, [])
    assert out["rows"][0]["strategy"] == "PARENT_BEHAVIOR_UNVERIFIED"


def test_missing_world_action_is_not_silently_laundered_as_converted():
    scene, mapping = _scene()
    out = analyze(scene, mapping, [{"kind": "camera_cut", "entity_name": "CAM"}])
    assert out["static_pose_candidates"] == 0
    assert out["rows"][0]["strategy"] == "CHILD_WORLD_BEHAVIOR_UNVERIFIED"


def test_scripted_group_does_not_count_as_static_even_without_timeline_tracks():
    scene, mapping = _scene()
    scene["entities"][0]["metadata"]["scripts"] = ["TimeDrivenMotion"]
    assert analyze(scene, mapping, [])["rows"][0]["strategy"] == "PARENT_BEHAVIOR_UNVERIFIED"


def test_two_level_source_hierarchy_is_kept_as_exact_ancestor_chain():
    scene, mapping = _scene()
    extra = {"entity_id": "character_parent", "name": "CHARACTER_A",
             "parent_entity_id": "group", "ced_type": "entity.prop",
             "metadata": {"active_self": True, "hierarchy_path": "SceneRoot/CHARACTER_A",
                          "world_transform": _world()}}
    scene["entities"].append(extra)
    scene["entities"][1]["parent_entity_id"] = "character_parent"
    row = analyze(scene, mapping, [])["rows"][0]
    assert [x["name"] for x in row["ancestor_chain"]] == ["CHARACTER_A", "SceneRoot"]
    assert row["strategy"] == "CHILD_WORLD_BEHAVIOR_UNVERIFIED"


def test_benchmark002_eight_unmapped_links_reduce_to_three_source_group_nodes():
    scene, mapping = _scene()
    scene["entities"] = [
        {"entity_id": "root", "name": "Benchmark002", "ced_type": "entity.prop",
         "parent_entity_id": "", "metadata": {
             "active_self": True, "hierarchy_path": "Benchmark002",
             "world_transform": _world()}},
        {"entity_id": "a", "name": "CHARACTER_A", "ced_type": "entity.prop",
         "parent_entity_id": "root", "metadata": {
             "active_self": True, "hierarchy_path": "Benchmark002/CHARACTER_A",
             "world_transform": _world()}},
        {"entity_id": "b", "name": "CHARACTER_B", "ced_type": "entity.prop",
         "parent_entity_id": "root", "metadata": {
             "active_self": True, "hierarchy_path": "Benchmark002/CHARACTER_B",
             "world_transform": _world()}},
    ]
    mapped = [
        ("Ch31_nonPBR", "a"), ("Ch26_nonPBR", "b"),
        ("CAM_A_Wide", "root"), ("CAM_B_Move", "root"),
        ("CAM_C_Close", "root"), ("CUTSCENE_DIRECTOR", "root"),
        ("LIGHT_KEY", "root"), ("PROP_MOVING", "root"),
    ]
    for name, parent in mapped:
        scene["entities"].append({
            "entity_id": name, "name": name, "parent_entity_id": parent,
            "ced_type": "entity.camera", "metadata": {"world_transform": _world()}})
    mapping = {"entities": {name: {"actor_label": "CSAI_" + name}
                            for name, _ in mapped}}
    result = analyze(scene, mapping, [])
    assert result["total"] == 8
    assert {n["name"] for row in result["rows"]
            for n in row["ancestor_chain"]} == {
                "Benchmark002", "CHARACTER_A", "CHARACTER_B"}
    assert all(not row["native_parent_actor_reconstructed"] for row in result["rows"])
    assert all(row["strategy"] == "CHILD_WORLD_BEHAVIOR_UNVERIFIED"
               for row in result["rows"])
