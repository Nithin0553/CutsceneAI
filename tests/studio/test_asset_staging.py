"""Supported audio import: dependency closure, source integrity, editor preflight."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "studio"))
sys.path.insert(0, str(ROOT / "integrations" / "unreal"))

import asset_staging
import stage_asset_import


def setup_source(tmp_path, *, unsupported=False):
    project = tmp_path / "UnityProject"
    audio = project / "Assets" / "Sfx" / "whoosh.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"RIFF" + (40).to_bytes(4, "little") + b"WAVE" + b"\x00" * 40)
    assets = [{
        "asset_id": "asset:a1", "name": "Whoosh", "ced_type": "audio.asset",
        "source_ref": "unity-asset:a1", "metadata": {
            "asset_path": "Assets/Sfx/whoosh.wav", "asset_type": "UnityEngine.AudioClip",
        },
    }]
    sections = [{"payload": {"asset_id": "asset:a1"}, "section_id": "audio1"}]
    if unsupported:
        (project / "Assets" / "Walk.anim").write_bytes(b"unity-native")
        assets.append({
            "asset_id": "anim", "name": "Walk", "ced_type": "animation.clip",
            "source_ref": "unity-asset:anim", "metadata": {
                "asset_path": "Assets/Walk.anim", "asset_type": "UnityEngine.AnimationClip"
            },
        })
        sections.append({"payload": {"asset_id": "anim"}, "section_id": "anim1"})
    source = {
        "schema_version": "0.1.0", "cutscene_id": "scene:test",
        "source": {"engine": "unity", "project_fingerprint": "source-project"},
        "entities": [], "assets": assets,
        "tracks": [{"track_id": "t", "ced_type": "audio.track", "sections": sections}],
    }
    mapping = {"entities": {}, "assets": {},
               "sequence_asset_path": "/Game/Studio/LS_Unique",
               "overwrite_sequence": False}
    csir_path = tmp_path / "scene.csir.json"
    mapping_path = tmp_path / "mapping.json"
    csir_path.write_text(json.dumps(source))
    mapping_path.write_text(json.dumps(mapping))
    return project, csir_path, mapping_path, audio


def make_manifest(tmp_path, *, unsupported=False):
    project, src, mapping, audio = setup_source(tmp_path, unsupported=unsupported)
    manifest = asset_staging.compose_files(
        src, mapping, source_project=project,
        target_folder="/Game/CutSceneAI/NewImportedAssets",
    )
    path = tmp_path / "assets.json"
    asset_staging.write_new(path, manifest)
    return manifest, path, src, mapping, audio


class FakeSound:
    def __init__(self, name="SoundWave"):
        self.name = name

    def get_class(self):
        return self

    def get_name(self):
        return self.name


class FakeTask:
    def __init__(self):
        self.properties = {}

    def set_editor_property(self, key, value):
        self.properties[key] = value

    def get_editor_property(self, key):
        return self.properties.get(key)


class FakeLibrary:
    def __init__(self, api):
        self.api = api

    def does_directory_exist(self, folder):
        return folder in self.api.folders

    def does_asset_exist(self, path):
        return path in self.api.objects


class FakeToolset:
    def __init__(self, api):
        self.api = api

    def import_asset_tasks(self, tasks):
        self.api.import_calls += 1
        for task in tasks:
            props = task.properties
            assert props["automated"] is True
            assert props["save"] is True
            assert props["replace_existing"] is False
            assert props["replace_existing_settings"] is False
            path = props["destination_path"] + "/" + props["destination_name"]
            self.api.objects[path] = FakeSound()
            task.set_editor_property("imported_object_paths", [path + "." + props["destination_name"]])


class FakeAPI:
    AssetImportTask = FakeTask

    def __init__(self, project_path):
        self.project_path = str(project_path)
        self.objects = {}
        self.folders = set()
        self.import_calls = 0
        api = self

        class Paths:
            @staticmethod
            def get_project_file_path():
                return api.project_path

        class AssetToolsHelpers:
            @staticmethod
            def get_asset_tools():
                return FakeToolset(api)

        self.Paths = Paths
        self.AssetToolsHelpers = AssetToolsHelpers
        self.EditorAssetLibrary = FakeLibrary(self)

    def load_asset(self, path):
        return self.objects.get(path)


def import_run(tmp_path, api, manifest_path, src, mapping, *, rights=True):
    return stage_asset_import.run(
        manifest_path, src, mapping, expected_project_path=api.project_path,
        resolved_mapping_path=tmp_path / "resolved.json",
        runtime_receipt_path=tmp_path / "receipt.json",
        rights_confirmed=rights, unreal_api=api,
    )


def test_wav_import_generates_new_mapping_and_truthful_partial_receipt(tmp_path):
    manifest, path, src, mapping, audio = make_manifest(tmp_path, unsupported=True)
    assert manifest["status_counts"] == {
        "READY_WAV_IMPORT": 1, "UNSUPPORTED_FORMAT": 1
    }
    assert manifest["engine_import_executed"] is False
    api = FakeAPI(tmp_path / "Target.uproject")
    receipt = import_run(tmp_path, api, path, src, mapping)
    assert receipt["status"] == "IMPORTED_PARTIAL"
    assert receipt["target_assets_modified"] is True
    assert len(receipt["imported"]) == len(api.objects) == api.import_calls == 1
    assert receipt["blocked"][0]["asset_id"] == "anim"
    new_mapping = json.loads((tmp_path / "resolved.json").read_text())
    assert new_mapping["assets"]["Whoosh"] == manifest["assets"][1]["target_asset_path"]
    assert new_mapping["overwrite_sequence"] is False
    assert json.loads(mapping.read_text())["assets"] == {}
    assert audio.read_bytes().startswith(b"RIFF")
    assert (tmp_path / "receipt.json").exists()


def test_source_change_invalidates_manifest_prior_to_import(tmp_path):
    _manifest, path, src, mapping, audio = make_manifest(tmp_path)
    audio.write_bytes(b"tampered")
    api = FakeAPI(tmp_path / "Target.uproject")
    with pytest.raises(asset_staging.AssetStagingError, match="changed"):
        import_run(tmp_path, api, path, src, mapping)
    assert api.import_calls == 0
    assert not (tmp_path / "resolved.json").exists()
    assert json.loads((tmp_path / "receipt.json").read_text())["target_assets_modified"] is False


def test_rights_and_wrong_unreal_project_block_before_import(tmp_path):
    _manifest, path, src, mapping, _audio = make_manifest(tmp_path)
    api = FakeAPI(tmp_path / "Target.uproject")
    with pytest.raises(stage_asset_import.UnrealImportError, match="rights_confirmed"):
        import_run(tmp_path, api, path, src, mapping, rights=False)
    assert api.import_calls == 0
    (tmp_path / "receipt.json").unlink()
    with pytest.raises(stage_asset_import.UnrealImportError, match="Wrong target"):
        stage_asset_import.run(
            path, src, mapping, expected_project_path=str(tmp_path / "Other.uproject"),
            resolved_mapping_path=tmp_path / "resolved.json",
            runtime_receipt_path=tmp_path / "receipt.json",
            rights_confirmed=True, unreal_api=api,
        )
    assert api.import_calls == 0


def test_existing_destination_folder_or_asset_blocks_without_mutation(tmp_path):
    manifest, path, src, mapping, _audio = make_manifest(tmp_path)
    api = FakeAPI(tmp_path / "Target.uproject")
    api.folders.add(manifest["target_folder"])
    with pytest.raises(stage_asset_import.UnrealImportError, match="directory already exists"):
        import_run(tmp_path, api, path, src, mapping)
    assert api.import_calls == 0
    (tmp_path / "receipt.json").unlink()
    api.folders.clear()
    api.objects[manifest["assets"][0]["target_asset_path"]] = FakeSound()
    with pytest.raises(stage_asset_import.UnrealImportError, match="already exists"):
        import_run(tmp_path, api, path, src, mapping)
    assert api.import_calls == 0


def test_missing_dependency_blocks_that_import_safely(tmp_path):
    project, src, mapping, _audio = setup_source(tmp_path)
    doc = json.loads(src.read_text())
    doc["assets"][0]["metadata"]["dependency_asset_ids"] = ["missing"]
    src.write_text(json.dumps(doc))
    manifest = asset_staging.compose_files(
        src, mapping, source_project=project, target_folder="/Game/Studio/Unique"
    )
    assert manifest["status_counts"] == {
        "MISSING_CSIR_RECORD": 1, "READY_WAV_IMPORT": 1
    }
    path = tmp_path / "manifest.json"
    asset_staging.write_new(path, manifest)
    api = FakeAPI(tmp_path / "Target.uproject")
    with pytest.raises(stage_asset_import.UnrealImportError, match="Required dependency"):
        import_run(tmp_path, api, path, src, mapping)
    assert api.import_calls == 0


def test_traversal_symlink_or_ambiguous_name_is_never_importable(tmp_path):
    project, src, mapping, _audio = setup_source(tmp_path)
    doc = json.loads(src.read_text())
    doc["assets"][0]["metadata"]["asset_path"] = "../secret.wav"
    src.write_text(json.dumps(doc))
    manifest = asset_staging.compose_files(
        src, mapping, source_project=project, target_folder="/Game/Studio/Test"
    )
    assert manifest["assets"][0]["status"] == "MISSING_SOURCE_FILE"
    doc["assets"][0]["metadata"]["asset_path"] = "Assets/Sfx/whoosh.wav"
    doc["assets"].append({
        "asset_id": "other", "name": "Whoosh", "ced_type": "audio.asset",
        "metadata": {"asset_path": "Assets/Sfx/whoosh.wav"},
    })
    doc["tracks"][0]["sections"].append({"payload": {"asset_id": "other"}})
    src.write_text(json.dumps(doc))
    manifest = asset_staging.compose_files(
        src, mapping, source_project=project, target_folder="/Game/Studio/Test"
    )
    assert manifest["status_counts"] == {"AMBIGUOUS_SOURCE_NAME": 2}


def test_manifest_and_target_directory_are_immutable(tmp_path):
    manifest, path, src, mapping, _audio = make_manifest(tmp_path)
    asset_staging.verify_files(manifest, src, mapping)
    with pytest.raises(asset_staging.AssetStagingError, match="overwrite"):
        asset_staging.write_new(path, manifest)
    for bad in ("Game/Missing", "/Game/../Bad", "/Game/Space Name"):
        with pytest.raises(asset_staging.AssetStagingError):
            asset_staging.compose_files(
                src, mapping, source_project=tmp_path / "UnityProject",
                target_folder=bad,
            )


def test_invalid_wav_header_is_not_native_import_candidate(tmp_path):
    project, src, mapping, audio = setup_source(tmp_path)
    audio.write_bytes(b"not a valid wave file")
    manifest = asset_staging.compose_files(
        src, mapping, source_project=project, target_folder="/Game/Studio/Fresh"
    )
    assert manifest["status_counts"] == {"UNSUPPORTED_WAV_CONTAINER": 1}
