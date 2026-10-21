"""Mock Unreal regressions for explicitly saving one hierarchy level package."""
from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "integrations/unreal/cinetwin_hierarchy_persistence.py"
PROJECT = r"D:\Research\Unreal\UnrealProjects\CutSceneAIStudio_CineTwin_Test"
LEVEL = "/Game/Test/Level"


class _Package:
    def get_path_name(self):
        return LEVEL


class _Actor:
    def __init__(self, name: str):
        self.name = name
        self.package = _Package()
        self.parent = None
        self.position = (0.0, 0.0, 0.0)

    def get_actor_label(self):
        return self.name

    def get_package(self):
        return self.package

    def get_attach_parent_actor(self):
        return self.parent

    def get_actor_transform(self):
        return self.position

    def set_actor_location(self, pos, _sweep, _teleport):
        self.position = tuple(pos)

    def set_actor_rotation(self, _rotation, _teleport):
        pass

    def set_actor_scale3d(self, _scale):
        pass

    def set_actor_transform(self, transform, _sweep, _teleport):
        self.position = transform


class _Saving:
    saved_packages = []
    result = True

    @classmethod
    def save_packages(cls, packages, only_dirty):
        cls.saved_packages.append((list(packages), only_dirty))
        return cls.result


def _load(monkeypatch, *, project=PROJECT, existing=True):
    parent = _Actor("Parent")
    child = _Actor("Child")
    unreal = types.ModuleType("unreal")
    unreal.Paths = types.SimpleNamespace(
        project_dir=lambda: project,
        convert_relative_path_to_full=lambda p: p,
    )
    unreal.EditorAssetLibrary = types.SimpleNamespace(
        does_asset_exist=lambda _: existing
    )
    unreal.EditorLoadingAndSavingUtils = _Saving
    unreal.EditorActorSubsystem = object()
    unreal.get_editor_subsystem = lambda _: types.SimpleNamespace(
        get_all_level_actors=lambda: [parent, child]
    )
    unreal.log = lambda _: None
    unreal.Vector = lambda *p: p
    monkeypatch.setitem(sys.modules, "unreal", unreal)

    csir_module = types.ModuleType("csir_plan")
    csir_module.load_json = lambda path: {
        "cutscene_id": "fixture",
        "entities": [
            {"entity_id": "p", "name": "Parent"},
            {"entity_id": "c", "name": "Child", "parent_entity_id": "p"},
        ],
    } if path == "source" else {
        "enable_cinetwin_hierarchy": True,
        "overwrite_sequence": False,
        "sequence_asset_path": "/Game/Test/GeneratedSequence",
    }
    csir_module.build_plan = lambda *_: {"actions": []}
    monkeypatch.setitem(sys.modules, "csir_plan", csir_module)

    hierarchy_module = types.ModuleType("hierarchy_realization")
    hierarchy_module.build_attachment_operations = lambda *_: {
        "attachments": [{
            "actor_label": "Child", "parent_actor_label": "Parent",
        }],
        "unresolved_source_parents": [],
    }
    monkeypatch.setitem(sys.modules, "hierarchy_realization", hierarchy_module)

    runtime_module = types.ModuleType("cinetwin_hierarchy_runtime")
    def apply(_ops):
        child.parent = parent
        return [{"kind": "new_attachment", "child": child}]
    def rollback(_changes):
        child.parent = None
    runtime_module.apply_hierarchy = apply
    runtime_module.rollback_hierarchy = rollback
    monkeypatch.setitem(sys.modules, "cinetwin_hierarchy_runtime", runtime_module)

    prep = types.ModuleType("scene_prep")
    prep.build_scene_prep = lambda *_: [{
        "actor_label": "Child",
        "location_cm": (3, 4, 5),
        "rotation_pitch_yaw_roll_degrees": (0, 0, 0),
        "scale_xyz": (1, 1, 1),
    }]
    monkeypatch.setitem(sys.modules, "scene_prep", prep)
    compat = types.ModuleType("unreal_compat")
    compat.make_rotator_semantic = lambda **_: None
    monkeypatch.setitem(sys.modules, "unreal_compat", compat)

    _Saving.saved_packages = []
    _Saving.result = True
    spec = importlib.util.spec_from_file_location(
        "_cinetwin_persistence_regression", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, parent, child


def _run(module):
    return module.apply_and_save_existing(
        "source",
        "mapping",
        expected_project_directory=PROJECT,
        expected_level_package=LEVEL,
    )


def test_saved_only_expected_package_with_dirty_filter_disabled(monkeypatch):
    module, parent, child = _load(monkeypatch)
    result = _run(module)
    assert child.parent is parent
    assert child.position == (3, 4, 5)
    assert result["status"] == "SAVED_AWAITING_REOPEN"
    assert len(_Saving.saved_packages) == 1
    packages, only_dirty = _Saving.saved_packages[0]
    assert packages[0].get_path_name() == LEVEL
    assert only_dirty is False


def test_wrong_project_stops_before_any_mutation_or_save(monkeypatch):
    module, _, child = _load(monkeypatch, project="D:/OtherOriginalProject")
    with pytest.raises(module.HierarchyPersistenceError, match="another Unreal project"):
        _run(module)
    assert child.parent is None
    assert _Saving.saved_packages == []


def test_missing_generated_sequence_is_a_hard_preflight_error(monkeypatch):
    module, _, child = _load(monkeypatch, existing=False)
    with pytest.raises(module.HierarchyPersistenceError, match="Level Sequence must exist"):
        _run(module)
    assert child.parent is None
    assert _Saving.saved_packages == []


def test_save_failure_rolls_back_live_attachment_and_child_pose(monkeypatch):
    module, _, child = _load(monkeypatch)
    _Saving.result = False
    with pytest.raises(module.HierarchyPersistenceError, match="did not confirm saving"):
        _run(module)
    assert child.parent is None
    assert child.position == (0.0, 0.0, 0.0)


def test_wrong_level_package_is_rejected_before_changes(monkeypatch):
    module, _, child = _load(monkeypatch)
    with pytest.raises(module.HierarchyPersistenceError, match="expected level"):
        module.apply_and_save_existing(
            "source", "mapping",
            expected_project_directory=PROJECT,
            expected_level_package="/Game/Other/Level",
        )
    assert child.parent is None
    assert _Saving.saved_packages == []


def test_no_sequence_overwrite_and_targeted_saving_contract():
    source = SCRIPT.read_text(encoding="utf-8")
    ast.parse(source)
    assert "save_packages(" in source
    assert "only_dirty=False" in source
    assert "does_asset_exist(asset_path)" in source
    assert "get_package()" in source
    assert "expected_project_directory" in source
    assert "save_dirty_packages(" not in source
    assert "delete_asset(" not in source
    assert "save_current_level(" not in source
