"""Verify actual editor snapshot is used before generating Unreal sequence."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'integrations/unreal/studio_local_editor_worker.py').exists())


def test_worker_reports_missing_mapped_actors_without_modifying_scene(tmp_path, monkeypatch):
    class Skel: pass
    class Cam: pass
    class Actor:
        def get_actor_label(self): return 'CSAI_Old_CAM_A_Wide'
        def get_class(self): return SimpleNamespace(get_name=lambda:'CineCameraActor')
        def get_component_by_class(self, component):
            return object() if component == Cam else None
    class World:
        def get_path_name(self): return '/Game/Tests/L_Test.L_Test'
    class EditorActorSubsystem:
        def get_all_level_actors(self): return [Actor()]
    class UnrealEditorSubsystem:
        def get_editor_world(self): return World()
    class Assets:
        @staticmethod
        def does_asset_exist(path): return path=='/Game/Assets/Anim'
    fake = SimpleNamespace(
        SkeletalMeshComponent=Skel, CineCameraComponent=Cam,
        EditorAssetLibrary=Assets, EditorActorSubsystem=EditorActorSubsystem,
        UnrealEditorSubsystem=UnrealEditorSubsystem,
        get_editor_subsystem=lambda klass: klass(),
        load_asset=lambda path:SimpleNamespace(get_class=lambda:SimpleNamespace(get_name=lambda:'AnimSequence')),
        Paths=SimpleNamespace(get_project_file_path=lambda:str(tmp_path/'New.uproject')),
    )
    monkeypatch.setitem(sys.modules,'unreal',fake)
    folder=ROOT/'integrations/unreal'
    monkeypatch.syspath_prepend(str(folder))
    spec=importlib.util.spec_from_file_location('studio_local_editor_worker_for_test', folder/'studio_local_editor_worker.py')
    worker=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    worker.WORKSPACE=tmp_path/'runs'
    cid='20261031T123456Z_abcdef01'
    target=worker.WORKSPACE/'candidates'/cid
    target.mkdir(parents=True)
    (target/'transfer-plan.json').write_text(json.dumps({
        'sequence_asset_path':'/Game/Tests/LS_New',
        'bindings':{'CAM_A_Wide':'CSAI_Old_CAM_A_Wide','Ch26_nonPBR':'CSAI_Old_Ch26_nonPBR'},
        'actions':[{'kind':'camera_setup','entity_name':'CAM_A_Wide'},
                   {'kind':'skeletal_animation','entity_name':'Ch26_nonPBR','unreal_asset_path':'/Game/Assets/Anim'}],
    }))
    worker._save(worker.WORKSPACE/'active-candidate.json', {'candidate_id':cid,'sequence_path':'/Game/Tests/LS_New'})
    worker._save(worker.WORKSPACE/'connection.json', {'target_project':str(tmp_path/'New.uproject'),
                                                    'level_path':'/Game/Tests/L_Test'})
    worker._update_destination_readiness()
    result=worker._load(worker.WORKSPACE/'destination-readiness.json')
    assert result['status']=='SCENE_SETUP_REQUIRED'
    assert result['ready'] is False
    assert [x['entity_name'] for x in result['missing_actors']]==['Ch26_nonPBR']
    assert result['found_actor_count']==1
    assert result['scene_modified'] is False
    assert result['candidate_id']==cid
