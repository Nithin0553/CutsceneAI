"""Guarded new-level initialization never overwrites existing maps."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[2]


def _worker(monkeypatch):
    state={'exists':False, 'loaded':'/Temp/Untitled_1', 'created':[], 'folders':[]}
    expected='/Game/CutSceneAI/AutoTransfer/L_Studio_Fresh'
    def create(path):
        state['created'].append(path)
        state['exists']=True
        state['loaded']=path
        return True
    fake=SimpleNamespace(
        EditorAssetLibrary=SimpleNamespace(
            does_asset_exist=lambda p:state['exists'] if p==expected else False,
            make_directory=lambda p:state['folders'].append(p)),
        EditorLevelLibrary=SimpleNamespace(new_level=create),
        LevelEditorSubsystem=type('LevelEditorSubsystem',(),{}),
        get_editor_subsystem=lambda klass:SimpleNamespace(new_level=create),
        log=lambda text:None,
    )
    monkeypatch.setitem(sys.modules,'unreal',fake)
    spec=importlib.util.spec_from_file_location('worker_v07_test',ROOT/'integrations/unreal/studio_local_editor_worker.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    monkeypatch.setattr(mod,'_loaded_level',lambda:state['loaded'])
    monkeypatch.setattr(mod,'_world_has_unsaved_changes',lambda:False)
    return mod,state,expected


def test_new_level_created_only_at_explicit_worker_phase(monkeypatch):
    mod,state,expected=_worker(monkeypatch)
    mod._ensure_target_level({'create_level':True,'expected_level':expected})
    assert state['created']==[expected]
    assert state['folders']==['/Game/CutSceneAI/AutoTransfer']


def test_existing_target_map_is_not_overwritten(monkeypatch):
    mod,state,expected=_worker(monkeypatch)
    state['exists']=True
    with pytest.raises(RuntimeError,match='already exists'):
        mod._ensure_target_level({'create_level':True,'expected_level':expected})
    assert not state['created']


def test_arbitrary_create_map_path_is_rejected(monkeypatch):
    mod,state,expected=_worker(monkeypatch)
    with pytest.raises(RuntimeError,match='noncanonical'):
        mod._ensure_target_level({'create_level':True,'expected_level':'/Game/Other/L_Map'})
    assert not state['created']


def test_regular_sequence_run_requires_preexisting_loaded_level(monkeypatch):
    mod,state,expected=_worker(monkeypatch)
    with pytest.raises(RuntimeError,match='Wrong Unreal level'):
        mod._ensure_target_level({'create_level':False,'expected_level':expected})
    assert not state['created']


def test_unsaved_current_level_blocks_automatic_creation(monkeypatch):
    mod,state,expected=_worker(monkeypatch)
    monkeypatch.setattr(mod,'_world_has_unsaved_changes',lambda:True)
    with pytest.raises(RuntimeError,match='unsaved changes'):
        mod._ensure_target_level({'create_level':True,'expected_level':expected})
    assert not state['created']
