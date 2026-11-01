"""Engine-native feature introspection contracts, read-only and cross-version safe."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[2]
UNITY = (ROOT / "integrations" / "unity" / "com.cutsceneai.extractor"
         / "Editor" / "CutSceneAIFeatureSurfaceScanner.cs")
UNREAL = ROOT / "integrations" / "unreal" / "studio_feature_surface.py"
spec = importlib.util.spec_from_file_location("studio_feature_surface", UNREAL)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_unity_scanner_enumerates_types_scenes_and_assets_without_scene_mutation():
    content = UNITY.read_text(encoding="utf-8")
    for fragment in (
        'TypeCache.GetTypesDerivedFrom<Component>()',
        'TypeCache.GetTypesDerivedFrom<ScriptableObject>()',
        'TypeCache.GetTypesDerivedFrom<PlayableAsset>()',
        'TypeCache.GetTypesDerivedFrom<TrackAsset>()',
        'AssetDatabase.GetAllAssetPaths()',
        'AssetDatabase.GetMainAssetTypeAtPath(path)',
        'GlobalObjectId.GetGlobalObjectIdSlow(component)',
        'GetComponentsInChildren<Component>(true)',
        'MISSING_MONOBEHAVIOUR_SCRIPT',
        'FileMode.CreateNew',
        'SOURCE_DISCOVERY_ONLY_NOT_TRANSFER_VERIFIED',
    ):
        assert fragment in content
    for unsafe in ('SaveAssets(', 'SaveScene(', 'LoadAssetAtPath(', 'DestroyImmediate(',
                   'PlayableDirector.Evaluate(', 'AssetDatabase.ImportAsset('):
        assert unsafe not in content


class Actor:
    def __init__(self, label, native_type):
        self.label = label
        self.native_type = native_type

    def get_actor_label(self):
        return self.label

    def get_path_name(self):
        return "/Game/Scratch/L_Test:PersistentLevel." + self.label

    def get_class(self):
        return NS(get_name=lambda: self.native_type)


def test_unreal_census_dynamic_native_types_and_loaded_level_actors(tmp_path):
    fake = NS(
        Camera=type("Camera", (), {}),
        CustomNiagara=type("VendorType", (type("BaseType", (), {}),), {}),
        Paths=NS(get_project_file_path=lambda: "B:/Testing/Project.uproject"),
        SystemLibrary=NS(get_engine_version=lambda: "5.8.3"),
        EditorActorSubsystem=type("EditorActorSubsystem", (), {}),
        get_editor_subsystem=lambda _target: NS(get_all_level_actors=lambda: [
            Actor("CAM_Wide", "CineCameraActor"), Actor("FX_01", "NiagaraActor")
        ]),
    )
    result = module.census(fake)
    assert result["engine"] == "unreal"
    assert result["engine_version"] == "5.8.3"
    assert result["verification"] == "TARGET_CAPABILITY_DISCOVERY_ONLY_NOT_TRANSFER_VERIFIED"
    assert {x["native_type"] for x in result["registered_types"]} >= {
        "Camera", "CustomNiagara"}
    assert {x["native_type"] for x in result["loaded_level_actors"]} == {
        "CineCameraActor", "NiagaraActor"}
    before = json.dumps(result, sort_keys=True)
    output = module.save_latest(fake, root=tmp_path)
    data = json.loads(output.read_text(encoding="utf-8"))
    assert len(data["registered_types"]) >= 2
    assert data["verification"].endswith("NOT_TRANSFER_VERIFIED")
    assert before
    assert len(list(tmp_path.glob("unreal-feature-surface-*.json"))) == 1


def test_unreal_census_gracefully_records_unavailable_editor_subsystem():
    class Minimal:
        Camera = type("Camera", (), {})

    result = module.census(Minimal())
    assert result["loaded_level_actors"] == [{
        "inspection_status": "ACTOR_SUBSYSTEM_UNAVAILABLE"}]
    assert result["verification"].endswith("NOT_TRANSFER_VERIFIED")
