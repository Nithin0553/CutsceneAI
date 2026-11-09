"""Verify the guarded Unreal stage with a fake editor, not an engine fidelity test."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

STAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(STAGE_ROOT / "tools"))
import studio_fresh_target_assets as source_plan
from test_studio_fresh_target_assets import fixture

spec = importlib.util.spec_from_file_location(
    "studio_import_fresh_target", STAGE_ROOT / "integrations" / "unreal" / "studio_import_fresh_target.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ObjectType:
    def __init__(self, name):
        self.name = name

    def get_name(self):
        return self.name


class FakeAsset:
    def __init__(self, class_name):
        self.class_name = class_name

    def get_class(self):
        return ObjectType(self.class_name)


class Settable:
    def __init__(self):
        self.props = {}

    def set_editor_property(self, name, value):
        self.props[name] = value


class FakeTools:
    def __init__(self, editor):
        self.editor = editor

    def get_asset_tools(self):
        return self

    def import_asset_tasks(self, tasks):
        self.editor.import_runs += 1
        for task in tasks:
            props = task.props
            dest = props["destination_path"] + "/" + props["destination_name"]
            ext = Path(props["filename"]).suffix.lower()
            self.editor.imported[dest] = FakeAsset("SkeletalMesh" if ext == ".fbx" else "Texture2D")


class FakeUnreal:
    class UnrealEditorSubsystem:
        pass

    class FBXImportType:
        FBXIT_SKELETAL_MESH = 1

    def __init__(self, project, level):
        self.project = str(project)
        self.level = level
        self.import_runs = 0
        self.imported = {}
        self.Paths = SimpleNamespace(get_project_file_path=lambda: self.project,
                                     convert_relative_path_to_full=lambda x: x)
        self.EditorAssetLibrary = SimpleNamespace(
            does_directory_exist=lambda _: False,
            does_asset_exist=lambda name: name in self.imported,
        )
        self.AssetToolsHelpers = FakeTools(self)
        self.AssetImportTask = Settable
        self.FbxImportUI = Settable

    def get_editor_subsystem(self, _):
        return SimpleNamespace(get_editor_world=lambda: SimpleNamespace(
            get_path_name=lambda: self.level + "." + self.level.split("/")[-1]
        ))

    def load_asset(self, path):
        return self.imported.get(path)


def _input(tmp_path):
    opts, _ = fixture(tmp_path)
    plan = source_plan.compose(**opts)
    file = tmp_path / "plan.json"
    file.write_text(source_plan._canonical_json(plan))
    api = FakeUnreal(opts["target_project"], "/Game/CutSceneAI/Tests/L_NewTarget")
    return opts, file, api


def test_editor_stage_preflights_rights_before_any_mutation(tmp_path):
    opts, plan, api = _input(tmp_path)
    receipt = tmp_path / "no_rights.json"
    with pytest.raises(module.FreshTargetImportError, match="rights"):
        module.run(str(plan), str(receipt),
                   expected_project_path=str(opts["target_project"]),
                   expected_level_path=api.level, unreal_api=api)
    doc = json.loads(receipt.read_text())
    assert doc["status"] == "BLOCKED"
    assert doc["engine_changes_possible"] is False
    assert api.import_runs == 0


def test_editor_stage_blocks_wrong_level_before_mutation(tmp_path):
    opts, plan, api = _input(tmp_path)
    receipt = tmp_path / "wrong_level.json"
    with pytest.raises(module.FreshTargetImportError, match="Wrong or unsaved"):
        module.run(str(plan), str(receipt),
                   expected_project_path=str(opts["target_project"]),
                   expected_level_path="/Game/Elsewhere", rights_confirmed=True, unreal_api=api)
    assert api.import_runs == 0


def test_editor_stage_imports_only_models_and_unique_textures(tmp_path):
    opts, plan, api = _input(tmp_path)
    receipt_file = tmp_path / "success.json"
    receipt = module.run(str(plan), str(receipt_file),
                         expected_project_path=str(opts["target_project"]),
                         expected_level_path=api.level, rights_confirmed=True, unreal_api=api)
    assert receipt["status"] == "IMPORTED_ASSETS_UNVERIFIED"
    assert api.import_runs == 2
    assert sorted(x["target_class"] for x in receipt["imported"]) == ["SkeletalMesh", "Texture2D"]
    assert len(receipt["deferred"]) == 3
    assert receipt["scene_modified"] is False
    assert receipt["fidelity_verified"] is False
    assert json.loads(receipt_file.read_text()) == receipt
