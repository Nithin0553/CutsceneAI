import copy
import hashlib
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'integrations' / 'unreal'))
import studio_stage4_layout as stage4
import studio_stage4_apply as apply


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2), encoding='utf-8')
    return str(path)


def fixtures(tmp_path, monkeypatch):
    source = {
        'schema_version': '0.1.0', 'source':{'engine':'unity'},
        'timing': {'source_rate': {'numerator':24,'denominator':1}},
        'entities': [{'entity_id':'e1','name':'Ch31_nonPBR','ced_type':'entity.character', 'metadata':{}},
                     {'entity_id':'e2','name':'CAM_A_Wide','ced_type':'entity.camera','metadata':{}}],
        'tracks': []
    }
    src = write(tmp_path / 'source.json', source)
    mapping = {'entities':{'Ch31_nonPBR':{'actor_label':'CSAI_Character'},'CAM_A_Wide':{'actor_label':'CSAI_Camera'}},'assets':{}}
    mapping_path = write(tmp_path/'mapping.json', mapping)
    actors = [{'source_name': name,'actor_label': info['actor_label'], 'kind':'camera' if name=='CAM_A_Wide' else 'character', 'mesh_path':'/Game/Characters/Test'} for name,info in mapping['entities'].items()]
    actors += [{'source_name':f'prop{i}', 'actor_label':f'CSAI_prop{i}', 'kind':'prop'} for i in range(6)]
    st3 = {'kind':'cutsceneai.studio.stage3_scene_plan',
           'target_project':str(tmp_path/'NewTarget.uproject'),
           'target_level':'/Game/CutSceneAI/L_NewTarget', 'csir_path':src,
           'csir_sha256':stage4.sha(src), 'mapping_output_path':mapping_path, 'mapping':mapping, 'actors':actors}
    st3_path = write(tmp_path/'stage3.json',st3)
    receipt={'kind':'cutsceneai.studio.stage3_scene_receipt',
             'status':'ACTORS_CREATED_LEVEL_NOT_YET_VERIFIED',
             'plan_path':st3_path, 'mapping_path':mapping_path,
             'actors_created':[{'source_name':x['source_name']} for x in actors]}
    receipt_path = write(tmp_path/'receipt.json',receipt)
    audit = {'kind':'cutsceneai.studio.stage3_scene_persistence_audit',
             'status':'STAGE3_SAVED_ACTORS_READBACK', 'project':str(tmp_path/'NewTarget.uproject'),
             'level':'/Game/CutSceneAI/L_NewTarget', 'receipt_path':receipt_path,
             'mapping_exists':True, 'mapping_matches_plan':True,
             'readback_count':8, 'expected_count':8,
             'rows':[{'readback_ready':True} for _ in actors]}
    audit_path=write(tmp_path/'audit.json',audit)
    def fake_prep(src, mapping):
        return [{'actor_label':'CSAI_Character','entity_name':'Ch31_nonPBR',
                 'source':'entity.world_transform','location_cm':[100,200,300],
                 'rotation_pitch_yaw_roll_degrees':[0,90,0], 'scale_xyz':[1,1,1]}]
    monkeypatch.setitem(sys.modules,'scene_prep',types.SimpleNamespace(build_scene_prep=fake_prep))
    monkeypatch.setattr(stage4,'_candidate_from_first_transform',lambda a,b: ({},[],[]))
    monkeypatch.setitem(sys.modules,'hierarchy_realization',types.SimpleNamespace(
        build_attachment_operations=lambda a,b,c: {'attachments':[], 'parent_initializations':[],
                                                    'unresolved_source_parents':[], 'policy':'KEEP_WORLD'}))
    return st3_path, receipt_path, audit_path


def test_compose_and_verify_includes_evidence_and_no_unreal_changes(tmp_path,monkeypatch):
    paths=fixtures(tmp_path,monkeypatch)
    data=stage4.compose(*paths)
    assert len(data['placements']) == 1
    assert len(data['missing_source_poses']) == 7
    assert data['placements'][0]['rotation_rpy_degrees'] == [0.0,0.0,90.0]
    assert data['level_modified'] is False
    out=tmp_path/'plan4.json'; stage4.new_json(out,data)
    assert stage4.verify(out) == data


def test_stale_csir_refused(tmp_path,monkeypatch):
    paths=fixtures(tmp_path,monkeypatch)
    p=stage4.compose(*paths)
    target=tmp_path/'stage4.json'; stage4.new_json(target,p)
    Path(stage4.read(paths[0])['csir_path']).write_text('{}')
    with pytest.raises(stage4.LayoutError,match='Stale source input'):
        stage4.verify(target)


def test_wrong_project_readback_refused(tmp_path,monkeypatch):
    paths=fixtures(tmp_path,monkeypatch)
    audit=stage4.read(paths[2]); audit['project']='D:/someother.uproject'; write(Path(paths[2]),audit)
    with pytest.raises(stage4.LayoutError,match='different project'):
        stage4.compose(*paths)


def test_missing_actor_in_readback_refused(tmp_path,monkeypatch):
    paths=fixtures(tmp_path,monkeypatch)
    audit=stage4.read(paths[2]); audit['rows'][0]['readback_ready']=False; write(Path(paths[2]),audit)
    with pytest.raises(stage4.LayoutError,match='readbacks failed'):
        stage4.compose(*paths)


def test_mutated_plan_refused(tmp_path,monkeypatch):
    paths=fixtures(tmp_path,monkeypatch)
    p=stage4.compose(*paths)
    p['placements'][0]['location_cm'][0]=9999
    target=tmp_path/'tampered.json'; stage4.new_json(target,p)
    with pytest.raises(stage4.LayoutError,match='does not match'):
        stage4.verify(target)


def test_new_json_cannot_overwrite(tmp_path):
    p=tmp_path/'report.json'
    stage4.new_json(p, {'a':1})
    with pytest.raises(FileExistsError):
        stage4.new_json(p, {'a':2})


def test_path_normalization_windows_mixed_separators():
    assert stage4.path_key('D:/Research/Unreal/Test.uproject') == stage4.path_key('d:\\Research\\Unreal\\Test.uproject')

class FakeVector:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z

class FakeRotation:
    def __init__(self, pitch=0, yaw=0, roll=0):
        self.pitch, self.yaw, self.roll = pitch, yaw, roll

class FakeWorld:
    def __init__(self, level): self.level=level
    def get_path_name(self): return self.level+'.'+self.level.rsplit('/',1)[-1]

class FakeActor:
    def __init__(self, label, mesh=None):
        self.label, self.mesh = label, mesh
        self.pos=FakeVector(0,0,0); self.rot=FakeRotation(); self.scale=FakeVector(1,1,1)
        self.parent=None
    def get_actor_label(self): return self.label
    def get_actor_location(self): return self.pos
    def get_actor_rotation(self): return self.rot
    def get_actor_scale3d(self): return self.scale
    def get_actor_transform(self): return (copy.deepcopy(self.pos),copy.deepcopy(self.rot),copy.deepcopy(self.scale))
    def set_actor_transform(self, t, *args): self.pos,self.rot,self.scale=copy.deepcopy(t)
    def set_actor_location(self, v, *args): self.pos=v
    def set_actor_rotation(self, r, *args): self.rot=r
    def set_actor_scale3d(self, s): self.scale=s
    def get_editor_property(self, key):
        assert key == 'skeletal_mesh_component'
        return types.SimpleNamespace(get_editor_property=lambda name:types.SimpleNamespace(get_path_name=lambda :self.mesh+'.Test'))
    def get_attach_parent_actor(self): return self.parent


def fake_api(project,level,actors):
    class API:
        UnrealEditorSubsystem=object()
        EditorActorSubsystem=type('EAS',(),{})
        Vector=FakeVector
        Paths=types.SimpleNamespace(get_project_file_path=lambda : project,convert_relative_path_to_full=lambda s:s)
        @staticmethod
        def get_editor_subsystem(cls):
            if cls is API.UnrealEditorSubsystem: return types.SimpleNamespace(get_editor_world=lambda :FakeWorld(level))
            return types.SimpleNamespace(get_all_level_actors=lambda :actors)
    return API


def test_editor_guarded_apply_and_nonoverwrite(tmp_path, monkeypatch):
    paths=fixtures(tmp_path,monkeypatch)
    p=stage4.compose(*paths)
    out=tmp_path/'stage4.json'; stage4.new_json(out,p)
    actors=[]
    for row in stage4.read(paths[0])['actors']:
        actors.append(FakeActor(row['actor_label'],row.get('mesh_path')))
    monkeypatch.setitem(sys.modules,'unreal_compat',types.SimpleNamespace(
        make_rotator_semantic=lambda roll,pitch,yaw:FakeRotation(pitch,yaw,roll)))
    api=fake_api(p['target_project'],p['target_level'],actors)
    receipt=tmp_path/'executed.json'
    result=apply.run(str(out),str(receipt),unreal_api=api)
    assert result['status']=='STAGE4_SOURCE_LAYOUT_APPLIED_LEVEL_NOT_SAVED'
    assert result['level_saved'] is False
    assert len(result['placements_applied'])==1
    assert actors[0].pos.x==100
    with pytest.raises(apply.PlacementError,match='Receipt already exists'):
        apply.run(str(out),str(receipt),unreal_api=api)


def test_editor_blocks_wrong_project_before_mutation(tmp_path,monkeypatch):
    paths=fixtures(tmp_path,monkeypatch)
    p=stage4.compose(*paths); out=tmp_path/'stage4.json'; stage4.new_json(out,p)
    actors=[FakeActor(r['actor_label'],r.get('mesh_path')) for r in stage4.read(paths[0])['actors']]
    api=fake_api('D:/Other.uproject',p['target_level'],actors)
    receipt=tmp_path/'wrong.json'
    with pytest.raises(apply.PlacementError,match='Wrong Unreal project'):
        apply.run(str(out),str(receipt),unreal_api=api)
    assert stage4.read(receipt)['status']=='BLOCKED'
    assert all(a.pos.x==0 for a in actors)


def test_editor_blocks_manual_moved_actor_before_mutation(tmp_path,monkeypatch):
    paths=fixtures(tmp_path,monkeypatch)
    p=stage4.compose(*paths); out=tmp_path/'stage4.json'; stage4.new_json(out,p)
    actors=[FakeActor(r['actor_label'],r.get('mesh_path')) for r in stage4.read(paths[0])['actors']]
    actors[0].pos.x=42
    api=fake_api(p['target_project'],p['target_level'],actors)
    receipt=tmp_path/'moved.json'
    with pytest.raises(apply.PlacementError,match='no longer at Stage 3 placeholder'):
        apply.run(str(out),str(receipt),unreal_api=api)
    assert stage4.read(receipt)['status']=='BLOCKED'
    assert actors[0].pos.x==42
