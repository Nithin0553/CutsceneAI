"""Regression: Unreal attachment compatibility restores mobility after failure."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "integrations" / "unreal" / "cinetwin_hierarchy_runtime.py"


class _FakeMobility:
    STATIC = 0
    STATIONARY = 1
    MOVABLE = 2


class _FakeComponent:
    def __init__(self, name: str, mobility: int):
        self.name = name
        self.mobility = mobility

    def get_path_name(self):
        return self.name

    def get_editor_property(self, name: str):
        assert name == "mobility"
        return self.mobility

    def set_mobility(self, mobility):
        self.mobility = mobility


class _FakeActor:
    def __init__(self, label: str, mobility: int):
        self.label = label
        self.root = _FakeComponent(label + "/Root", mobility)
        self.child = _FakeComponent(label + "/Mesh", mobility)

    def get_actor_label(self):
        return self.label

    def get_editor_property(self, name: str):
        assert name == "root_component"
        return self.root

    def get_components_by_class(self, _cls):
        return [self.root, self.child]


def _runtime(monkeypatch):
    unreal = types.ModuleType("unreal")
    unreal.ComponentMobility = _FakeMobility
    unreal.SceneComponent = _FakeComponent
    unreal.log = lambda *_a: None
    monkeypatch.setitem(sys.modules, "unreal", unreal)
    monkeypatch.setitem(sys.modules, "unreal_compat", types.ModuleType("unreal_compat"))
    spec = importlib.util.spec_from_file_location(
        "_cinetwin_mobility_regression", RUNTIME
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_static_child_components_become_movable_then_rollback(monkeypatch):
    runtime = _runtime(monkeypatch)
    actor = _FakeActor("Child", _FakeMobility.STATIC)
    changes = []
    runtime._ensure_movable(actor, changes)
    assert actor.root.mobility == _FakeMobility.MOVABLE
    assert actor.child.mobility == _FakeMobility.MOVABLE
    assert changes[0]["kind"] == "mobility_snapshot"
    runtime.rollback_hierarchy(changes)
    assert actor.root.mobility == _FakeMobility.STATIC
    assert actor.child.mobility == _FakeMobility.STATIC


def test_already_movable_child_is_not_mutated(monkeypatch):
    runtime = _runtime(monkeypatch)
    actor = _FakeActor("Child", _FakeMobility.MOVABLE)
    changes = []
    runtime._ensure_movable(actor, changes)
    assert changes == []


def test_partial_mobility_only_changes_required_components(monkeypatch):
    runtime = _runtime(monkeypatch)
    actor = _FakeActor("Child", _FakeMobility.MOVABLE)
    actor.child.mobility = _FakeMobility.STATIONARY
    changes = []
    runtime._ensure_movable(actor, changes)
    assert actor.child.mobility == _FakeMobility.MOVABLE
    runtime.rollback_hierarchy(changes)
    assert actor.root.mobility == _FakeMobility.MOVABLE
    assert actor.child.mobility == _FakeMobility.STATIONARY


def test_mobile_prep_refuses_missing_scene_component_root(monkeypatch):
    runtime = _runtime(monkeypatch)
    actor = _FakeActor("Child", _FakeMobility.STATIC)
    actor.root = None
    import pytest
    with pytest.raises(runtime.UnrealHierarchyError, match="root"):
        runtime._mobility_snapshot(actor)


def test_no_persistent_save_or_asset_overwrite_in_mobility_adapter():
    src = RUNTIME.read_text(encoding="utf-8")
    assert "get_editor_property(\"mobility\")" in src
    assert "set_mobility(unreal.ComponentMobility.MOVABLE)" in src
    assert "_restore_mobility(" in src
    assert "rollback_hierarchy(changes)" in src
    assert "save_current_level(" not in src
    assert "delete_asset(" not in src
