"""Regression: real scene scenery is not implicitly Timeline-bound.

Source identity must come from the same Unity scene and a uniquely evidenced
FBX. LOD child meshes, duplicate names, unrelated levels and primitives are
never guessed into target actors.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import studio_auto_assets as auto_assets
import studio_project_discovery as discovery
from test_studio_auto_assets import create

SCENE = "Assets/CutSceneAI/Benchmark002/Scenes/Benchmark002.unity"


def entity(eid, name, *, parent="", rendered=True, lod=False, source=None,
           scene=SCENE, kind="entity.prop"):
    return {
        "entity_id": eid, "name": name, "ced_type": kind, "parent_entity_id": parent,
        "metadata": {
            "scene_path": scene, "hierarchy_path": "Benchmark002/ENVIRONMENT/" + name,
            "scene_renderable_root": rendered, "source_lod_group_root": lod,
            "active_self": True,
            "source_model_assets": [{"asset_path": p} for p in (source or [])],
        },
    }


def sample():
    root = entity("root", "ENVIRONMENT", rendered=False, source=[
        "Assets/Models/Tree_05.fbx", "Assets/Models/Rock_04.fbx"])
    tree = entity("treeR", "ENV_TREE_RIGHT", parent="root", lod=True,
                  source=["Assets/Models/Tree_05.fbx"])
    tree_left = entity("treeL", "ENV_TREE_LEFT", parent="root", lod=True,
                       source=["Assets/Models/Tree_05.fbx"])
    rock = entity("rock", "ENV_ROCK_RIGHT", parent="root",
                  source=["Assets/Models/Rock_04.fbx"])
    return {
        "schema_version": "0.1.0",
        "source": {"engine": "unity"},
        "source_snapshot": {"director_scene_path": SCENE},
        "entities": [
            entity("char", "CHARACTER_A", rendered=False, kind="entity.character"),
            root, tree, tree_left, rock,
            entity("tree-r-lod0", "Tree_05_LOD0", parent="treeR",
                   source=["Assets/Models/Tree_05.fbx"]),
            entity("tree-l-lod0", "Tree_05_LOD0", parent="treeL",
                   source=["Assets/Models/Tree_05.fbx"]),
            entity("tree-r-lod1", "Tree_05_LOD1", parent="treeR",
                   source=["Assets/Models/Tree_05.fbx"]),
            entity("ground", "ENV_GROUND", parent="root",
                   source=["Resources/unity_builtin_extra"]),
            entity("foreign", "ForeignRock", scene="Assets/Another.unity",
                   source=["Assets/Models/Rock_04.fbx"]),
            entity("other", "OtherRock", source=["Assets/Models/Other.obj"]),
        ],
        "tracks": [{"binding_entity_id": "char", "ced_type": "animation.track",
                    "sections": [{"payload": {"asset_id": "walk"}}]}],
        "assets": [{"asset_id": "walk", "name": "Walking"}],
    }


def mapped(data):
    return discovery._source_mapping(
        data, json.dumps(data, sort_keys=True).encode(),
        "C:/Unreal/Dest.uproject", "/Game/Studio/L_Fresh")["entities"]


def test_untracked_static_environment_with_unique_fbx_enters_actor_mapping():
    m = mapped(sample())
    assert {"CHARACTER_A", "ENV_TREE_RIGHT", "ENV_TREE_LEFT",
            "ENV_ROCK_RIGHT"} == set(m)
    assert all(m[name]["actor_label"].startswith("CSAI_") for name in m)
    assert "Tree_05_LOD0" not in m  # Never double-spawn LOD geometry.
    assert "ENV_GROUND" not in m  # Built-in primitive has no FBX source.
    assert "ForeignRock" not in m
    assert "OtherRock" not in m


def test_ambiguous_multi_file_lod_cannot_turn_children_into_separate_actors():
    data = sample()
    next(x for x in data["entities"] if x["entity_id"] == "treeR")["metadata"][
        "source_model_assets"] = [
            {"asset_path": "Assets/Models/Tree_LOD0.fbx"},
            {"asset_path": "Assets/Models/Tree_LOD1.fbx"},
        ]
    m = mapped(data)
    assert "ENV_TREE_RIGHT" not in m
    assert "Tree_05_LOD0" not in m  # Source LOD root is unresolved, not split.
    assert "ENV_TREE_LEFT" in m


def test_duplicate_visible_source_names_not_silently_assigned_to_wrong_objects():
    data = sample()
    data["entities"].append(entity("duplicate", "ENV_ROCK_RIGHT",
                                   source=["Assets/Models/Rock_05.fbx"]))
    m = mapped(data)
    assert "ENV_ROCK_RIGHT" not in m
    assert "ENV_TREE_LEFT" in m


def test_unverified_old_csir_without_scene_root_flag_keeps_previous_mapping():
    data = sample()
    for x in data["entities"]:
        x["metadata"].pop("scene_renderable_root", None)
    assert set(mapped(data)) == {"CHARACTER_A"}


def test_newly_mapped_static_prop_is_imported_as_unreal_static_mesh(tmp_path):
    root, paths = create(tmp_path)
    rock = root / "Assets" / "Benchmark002" / "Characters" / "ENV_ROCK_RIGHT.fbx"
    rock.write_bytes(b"rock-mesh-fbx-source")
    csir = json.loads(paths[0].read_text())
    csir["source_snapshot"] = {"director_scene_path": SCENE}
    csir["entities"].append(entity(
        "new-scene-rock", "ENV_ROCK_RIGHT",
        source=["Assets/Benchmark002/Characters/ENV_ROCK_RIGHT.fbx"]))
    paths[0].write_text(json.dumps(csir))
    m = mapped(csir)
    assert "ENV_ROCK_RIGHT" in m
    prepared = json.loads(paths[2].read_text())
    prepared["bindings"]["ENV_ROCK_RIGHT"] = m["ENV_ROCK_RIGHT"]["actor_label"]
    paths[2].write_text(json.dumps(prepared))
    stage = auto_assets.inspect(
        *paths, root, "Assets/Benchmark002",
        "/Game/CutSceneAI/AutoTransfer/T_SCENE"
    )
    assert stage["ready"] is True
    assert any(a["name"] == "ENV_ROCK_RIGHT" and a["kind"] == "entity.prop"
               and a.get("mesh_path") for a in stage["actors"])
    assert any(row["kind"] == "StaticMesh" and row["source_file"] == str(rock.resolve())
               for row in stage["imports"])
    assert stage["fidelity_verified"] is False


def test_unsupported_source_scene_renderer_has_specific_incomplete_warning(tmp_path):
    root, paths = create(tmp_path)
    csir = json.loads(paths[0].read_text())
    csir["entities"].append(entity(
        "unsupported-LOD", "ENV_TREE_NEEDS_LOD_ADAPTER", lod=True,
        source=["Assets/Models/LOD0.fbx", "Assets/Models/LOD1.fbx"]
    ))
    paths[0].write_text(json.dumps(csir))
    stage = auto_assets.inspect(
        *paths, root, "Assets/Benchmark002",
        "/Game/CutSceneAI/AutoTransfer/T_INCOMPLETE"
    )
    assert stage["ready"] is True
    assert any("ENV_TREE_NEEDS_LOD_ADAPTER" in w
               and "NOT mapped" in w for w in stage["warnings"])
    assert not any(x["name"] == "ENV_TREE_NEEDS_LOD_ADAPTER"
                   for x in stage["actors"])
