"""Pure-Python tests for development hot reload (no Unreal required)."""
from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_FILE = ROOT / "integrations" / "unreal" / "cutsceneai_hot_reload.py"
spec = importlib.util.spec_from_file_location(
    "_cutsceneai_hot_reload_test", MODULE_FILE
)
assert spec is not None and spec.loader is not None
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def _checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    parent = tmp_path / "integrations" / "unreal"
    parent.mkdir(parents=True)
    (parent / "build_level_sequence.py").write_text(
        "MINIMAL_TEST_MARKER = True\n", encoding="utf-8"
    )
    (tmp_path / "packages" / "cinetwin").mkdir(parents=True)
    (tmp_path / "packages" / "studio").mkdir(parents=True)
    monkeypatch.setattr(helper, "PROJECT_ROOT", tmp_path)
    return parent


def test_reimports_changed_python_files_without_changing_engine(tmp_path, monkeypatch):
    root = _checkout(tmp_path, monkeypatch)
    name = "_cutsceneai_fake_hot_reload_test_"
    file = root / (name + ".py")
    file.write_text("CURRENT_VALUE = 11\n", encoding="utf-8")
    monkeypatch.setattr(helper, "MODULE_ORDER", (name,))
    try:
        first = helper.reload_project_python()
        assert first["imported"] == [name]
        assert first["reloaded"] == []
        assert first["unreal_assets_modified"] is False
        assert sys.modules[name].CURRENT_VALUE == 11

        file.write_text("CURRENT_VALUE = 280\n", encoding="utf-8")
        # Timestamp-based pyc caches can hide a same-second source edit;
        # force a later mtime for this synthetic regression test.
        future = time.time() + 10
        os.utime(file, (future, future))
        second = helper.reload_project_python()
        assert second["imported"] == []
        assert second["reloaded"] == [name]
        assert sys.modules[name].CURRENT_VALUE == 280
    finally:
        sys.modules.pop(name, None)


def test_rejects_same_named_module_from_wrong_project(tmp_path, monkeypatch):
    import types

    _checkout(tmp_path, monkeypatch)
    name = "_cutsceneai_fake_foreign_module_"
    monkeypatch.setattr(helper, "MODULE_ORDER", (name,))
    foreign = types.ModuleType(name)
    foreign.__file__ = "/tmp/a-different-project/foreign_module.py"
    monkeypatch.setitem(sys.modules, name, foreign)
    with pytest.raises(helper.HotReloadError, match="not loaded from"):
        helper.reload_project_python()


def test_no_unreal_scene_mutation_calls_in_hot_reload_helper():
    source = MODULE_FILE.read_text(encoding="utf-8")
    assert "importlib.invalidate_caches()" in source
    assert "importlib.reload(module)" in source
    assert "import unreal\n" not in source
    assert "unreal.EditorAssetLibrary" not in source
    assert "save_loaded_asset" not in source
    assert "delete_asset(" not in source
    assert "build_prepared_files(" not in source



def test_validation_readback_modules_are_hot_reloaded_in_dependency_order():
    modules = helper.MODULE_ORDER
    for name in (
        "core", "readback_level_sequence", "validation_expectation",
        "validate_transfer",
    ):
        assert name in modules
    assert modules.index("core") < modules.index("validate_transfer")
    assert modules.index("readback_level_sequence") < modules.index("validate_transfer")
    assert modules.index("validation_expectation") < modules.index("validate_transfer")
    assert modules.index("unreal_compat") < modules.index("readback_level_sequence")
