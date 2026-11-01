import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import studio_auto_assets as auto


def create(tmp, *, ambiguous=False, missing_audio=False):
    root=tmp/'Unity'
    models=root/'Assets'/'Benchmark002'/'Characters'
    anim=root/'Assets'/'Benchmark002'/'Animations'
    sounds=root/'Assets'/'Benchmark002'/'Audio'
    for folder in (models,anim,sounds): folder.mkdir(parents=True,exist_ok=True)
    (models/'Ch31_nonPBR.fbx').write_bytes(b'character-fbx')
    (models/'Ch26_nonPBR.fbx').write_bytes(b'character-fbx-2')
    for name in ('Walking.fbx','Waving.fbx','Breathing Idle.fbx'):
        (anim/name).write_bytes(('clip-'+name).encode())
    if ambiguous: (models/'Ch31_nonPBR.FBX').write_bytes(b'conflict')
    if not missing_audio: (sounds/'Cue.wav').write_bytes(b'RIFF'+bytes(40))
    csir={'schema_version':'0.1.0','source':{'engine':'unity'},
          'assets':[{'asset_id':'walk','name':'A_Walk_RootMotion'},
                    {'asset_id':'wave','name':'B_Waving'},
                    {'asset_id':'idle','name':'A_BreathingIdle'},
                    {'asset_id':'cue','name':'Cue'}],
          'entities':[{'entity_id':'a','name':'Ch31_nonPBR','ced_type':'entity.character'},
                      {'entity_id':'b','name':'Ch26_nonPBR','ced_type':'entity.character'},
                      {'entity_id':'cam','name':'CAM_A_Wide','ced_type':'entity.camera'},
                      {'entity_id':'light','name':'LIGHT_KEY','ced_type':'entity.light'},
                      {'entity_id':'prop','name':'PROP_MOVING','ced_type':'entity.prop'}],
          'tracks':[{'ced_type':'animation.track','binding_entity_id':'a','sections':[
                        {'payload':{'asset_id':'walk'}},{'payload':{'asset_id':'idle'}}]},
                    {'ced_type':'animation.track','binding_entity_id':'b','sections':[
                        {'payload':{'asset_id':'wave'}}]}]}
    mapping={'sequence_asset_path':'/Game/Tests/LS_New','overwrite_sequence':False,
             'assets':{x['name']:'/Game/Tests/'+x['name'] for x in csir['assets']}}
    plan={'sequence_asset_path':mapping['sequence_asset_path'],
          'bindings':{x['name']:'CSAI_'+x['name'] for x in csir['entities']},
          'actions':[{'kind':'skeletal_animation','entity_name':n,'unreal_asset_path':mapping['assets'][a]}
                     for n,a in [('Ch31_nonPBR','A_Walk_RootMotion'),('Ch26_nonPBR','B_Waving'),('Ch31_nonPBR','A_BreathingIdle')]]+
                    [{'kind':'audio','unreal_asset_path':mapping['assets']['Cue']}]}
    paths=[]
    for name,obj in [('csir.json',csir),('mapping.json',mapping),('plan.json',plan)]:
        p=tmp/name;p.write_text(json.dumps(obj));paths.append(p)
    return root,paths


def test_resolves_real_source_files_with_source_track_bindings(tmp_path):
    root,files=create(tmp_path)
    result=auto.inspect(*files,root,'Assets/Benchmark002','/Game/CutSceneAI/AutoTransfer/T_ABCD')
    assert result['ready'] is True
    assert len(result['actors'])==5
    assert sum(a['kind']=='AnimSequence' for a in result['imports'])==3
    assert sum(a['kind']=='SkeletalMesh' for a in result['imports'])==2
    assert sum(a['kind']=='SoundWave' for a in result['imports'])==1
    assert result['fidelity_verified'] is False
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps(result))
    assert auto.verify(manifest,*files)==result


def test_ambiguous_source_model_blocks_before_import(tmp_path):
    root,files=create(tmp_path,ambiguous=True)
    result=auto.inspect(*files,root,'Assets/Benchmark002','/Game/CutSceneAI/AutoTransfer/T_ABCD')
    assert not result['ready']
    assert any('Ch31_nonPBR' in x for x in result['blockers'])


def test_missing_audio_blocks_before_import(tmp_path):
    root,files=create(tmp_path,missing_audio=True)
    result=auto.inspect(*files,root,'Assets/Benchmark002','/Game/CutSceneAI/AutoTransfer/T_ABCD')
    assert not result['ready']
    assert any('Cue' in x for x in result['blockers'])


def test_changes_to_source_assets_invalidate_ready_manifest(tmp_path):
    root,files=create(tmp_path)
    result=auto.inspect(*files,root,'Assets/Benchmark002','/Game/CutSceneAI/AutoTransfer/T_ABCD')
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps(result))
    (root/'Assets/Benchmark002/Animations/Walking.fbx').write_bytes(b'changed')
    with pytest.raises(auto.AutoAssetError,match='changed'):
        auto.verify(manifest,*files)


def test_no_assets_scope_escape(tmp_path):
    root,files=create(tmp_path)
    with pytest.raises(auto.AutoAssetError,match='scope'):
        auto.inspect(*files,root,'Assets/../elsewhere','/Game/CutSceneAI/AutoTransfer/T_ABCD')


def test_duplicate_target_asset_paths_does_not_guess(tmp_path):
    root,files=create(tmp_path)
    mapping=json.loads(files[1].read_text())
    mapping['assets']['B_Waving']=mapping['assets']['A_Walk_RootMotion']
    files[1].write_text(json.dumps(mapping))
    result=auto.inspect(*files,root,'Assets/Benchmark002','/Game/CutSceneAI/AutoTransfer/T_ABCD')
    assert not result['ready']
    assert any('unique Unity asset' in x for x in result['blockers'])
