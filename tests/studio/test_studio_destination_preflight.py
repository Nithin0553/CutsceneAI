"""Regression tests for Generate readiness on a new/empty Unreal scene."""
import importlib.util
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'integrations/unreal/studio_destination_preflight.py').exists())
spec = importlib.util.spec_from_file_location('studio_destination_preflight', ROOT/'integrations/unreal/studio_destination_preflight.py')
dp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dp)


def plan():
    return {'sequence_asset_path': '/Game/Tests/LS_New',
            'bindings': {'CAM_A_Wide': 'CSAI_Old_CAM_A_Wide', 'Ch26_nonPBR': 'CSAI_Old_Ch26_nonPBR'},
            'actions': [
                {'kind': 'camera_setup', 'entity_name': 'CAM_A_Wide'},
                {'kind': 'skeletal_animation', 'entity_name': 'Ch26_nonPBR', 'unreal_asset_path': '/Game/Assets/Wave'},
            ]}


def assess(actors, assets=None, **kwargs):
    if assets is None:
        assets = {'/Game/Assets/Wave': {'exists': True, 'class_name': 'AnimSequence'}}
    return dp.assess(plan(), actors, assets, sequence_exists=kwargs.get('sequence_exists', False),
                     project_matches=kwargs.get('project_matches', True), level_matches=kwargs.get('level_matches', True))


def test_empty_scene_blocks_with_all_missing_actor_names():
    r = assess([])
    assert r['status'] == 'SCENE_SETUP_REQUIRED'
    assert r['ready'] is False
    assert r['expected_actor_count'] == 2
    assert r['found_actor_count'] == 0
    assert {x['actor_label'] for x in r['missing_actors']} == {'CSAI_Old_CAM_A_Wide', 'CSAI_Old_Ch26_nonPBR'}
    assert r['scene_modified'] is False


def test_ready_only_with_real_labels_and_assets():
    actors = [{'label': 'CSAI_Old_CAM_A_Wide','kind':'camera'}, {'label':'CSAI_Old_Ch26_nonPBR','kind':'skeletal'}]
    r = assess(actors)
    assert r['status'] == 'READY' and r['ready'] is True
    assert r['found_actor_count'] == 2
    assert r['required_asset_count'] == 1


def test_missing_asset_blocks_even_when_actors_exist():
    actors = [{'label':'CSAI_Old_CAM_A_Wide','kind':'camera'}, {'label':'CSAI_Old_Ch26_nonPBR','kind':'skeletal'}]
    r = assess(actors, {'/Game/Assets/Wave': {'exists':False}})
    assert r['status'] == 'ASSETS_REQUIRED' and r['ready'] is False
    assert len(r['missing_assets']) == 1


def test_wrong_actor_type_blocks_before_execution():
    actors = [{'label':'CSAI_Old_CAM_A_Wide','kind':'actor'}, {'label':'CSAI_Old_Ch26_nonPBR','kind':'skeletal'}]
    r = assess(actors)
    assert r['status']=='SCENE_SETUP_REQUIRED'
    assert r['wrong_actor_types'][0]['entity_name']=='CAM_A_Wide'


def test_duplicate_label_and_existing_sequence_block():
    actors = [{'label':'CSAI_Old_CAM_A_Wide','kind':'camera'}, {'label':'CSAI_Old_CAM_A_Wide','kind':'camera'},
              {'label':'CSAI_Old_Ch26_nonPBR','kind':'skeletal'}]
    r = assess(actors)
    assert len(r['duplicate_actors'])==1 and r['ready'] is False
    clean = actors[1:]
    r2 = assess(clean, sequence_exists=True)
    assert r2['status'] == 'TARGET_EXISTS'


def test_wrong_target_blocks_even_if_actors_ready():
    actors = [{'label':'CSAI_Old_CAM_A_Wide','kind':'camera'}, {'label':'CSAI_Old_Ch26_nonPBR','kind':'skeletal'}]
    r=assess(actors, project_matches=False)
    assert r['status']=='WRONG_TARGET'
