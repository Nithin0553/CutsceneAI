import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integrations/unreal'))
import studio_stage3_scene as s

KINDS = {'Ch31_nonPBR':'entity.character', 'Ch26_nonPBR':'entity.character',
         'CAM_A_Wide':'entity.camera','CAM_B_Move':'entity.camera','CAM_C_Close':'entity.camera',
         'LIGHT_KEY':'entity.light','PROP_MOVING':'entity.prop','PROP_PARENTED':'entity.prop'}


def jwrite(path, value):
    path.write_text(json.dumps(value))
    return path


def fixtures(root):
    root.mkdir(exist_ok=True)
    project = str(root / 'CutSceneAI_Test.uproject')
    level = '/Game/CutSceneAI/Tests/L_NewTarget_Test01'
    csir = jwrite(root/'csir.json', {'source':{'engine':'unity'},'schema_version':'0.1.0',
        'entities':[{'name':n,'entity_id':f'unity-object:{n}', 'ced_type':t} for n,t in KINDS.items()]+[{'name':'Ch31_Hair','ced_type':'entity.character','entity_id':'sub'}],
        'assets':[{'name':n} for n in ('A_Walk_RootMotion','A_BreathingIdle','B_Waving')]})
    manifest=jwrite(root/'manifest.json',{'source_csir_sha256':s.sha(csir)})
    a = jwrite(root/'stage1.json',{'manifest_path':str(manifest),'manifest_sha256':s.sha(manifest),'kind':'cutsceneai.studio.fresh_target_asset_import_receipt',
        'status':'IMPORTED_ASSETS_UNVERIFIED','verified_project':project,'verified_level':level,
        'imported':[{'source_path':f'Assets/Characters/{name}', 'target_asset_path':f'/Game/Mesh/{name[:-4]}', 'target_class':'SkeletalMesh'}
          for name in ('Ch31_nonPBR.fbx','Ch26_nonPBR.fbx')]})
    stage2plan=jwrite(root/'stage2plan.json',{'stage1_receipt_sha256':s.sha(a)})
    b = jwrite(root/'stage2.json',{'plan_path':str(stage2plan),'kind':'cutsceneai.studio.fresh_animation_import_receipt',
        'status':'IMPORTED_ANIMATIONS_UNVERIFIED','verified_project':project,'verified_level':level,
        'imported':[{'source_path':f'Assets/Anim/{name}', 'target_asset_path':f'/Game/Anim/{name[:-4]}', 'target_class':'AnimSequence'}
          for name in ('Walking.fbx','Breathing Idle.fbx','Waving.fbx')]})
    audit = jwrite(root/'audit.json',{'kind':'cutsceneai.studio.animation_readback_audit',
        'status':'PERSISTED_AND_SAMPLED_MOTION_OBSERVED','unreal_project':project,
        'all_structural_trials_ready':True,'rows':[{'structural_trial_ready': True} for _ in range(3)], 'source_receipt':str(b), 'source_receipt_sha256':s.sha(b)})
    out = root/'trial.json'; mapping = root/'trial_mapping.json'
    return {'csir_path':str(csir),'stage1_receipt_path':str(a),'stage2_receipt_path':str(b),
            'stage2_audit_path':str(audit),'expected_project_path':project,'target_level':level,
            'output_path':str(out),'mapping_output_path':str(mapping)}


def test_planning_is_read_only_selects_only_top_level_actors(tmp_path):
    values=fixtures(tmp_path)
    plan=s.plan(**values)
    assert len(plan['actors']) == 8
    assert plan['skipped_source_entities']==['Ch31_Hair']
    assert plan['mapping']['assets']['A_Walk_RootMotion']=='/Game/Anim/Walking'
    assert plan['mapping']['overwrite_sequence'] is False
    assert not Path(values['mapping_output_path']).exists()
    assert s.verify(values['output_path']) == plan


def test_reuse_and_changed_receipts_fail(tmp_path):
    values=fixtures(tmp_path); s.plan(**values)
    with pytest.raises(s.SceneStageError,match='overwrite'):
        s.plan(**values)
    p=Path(values['stage2_receipt_path']); p.write_text(p.read_text()+' ')
    with pytest.raises(s.SceneStageError,match='changed'):
        s.verify(values['output_path'])


def test_incomplete_audit_blocks_plan_without_output(tmp_path):
    values=fixtures(tmp_path)
    audit=Path(values['stage2_audit_path']); value=s.read(audit)
    value['all_structural_trials_ready']=False; jwrite(audit,value)
    with pytest.raises(s.SceneStageError,match='not ready'):
        s.plan(**values)
    assert not Path(values['output_path']).exists()


class Cls:
    def __init__(self, typ):self.typ=typ
    def get_name(self):return self.typ
class Asset:
    def __init__(self, typ):self.typ=typ
    def get_class(self):return Cls(self.typ)
class Actor:
    def __init__(self): self.label=''
    def set_actor_label(self,label,mark_dirty=True):self.label=label
    def get_actor_label(self):return self.label
    def get_path_name(self):return '/Game/Level.'+self.label
class FakeActors:
    def __init__(self):self.actors=[]
    def get_all_level_actors(self):return self.actors
    def spawn_actor_from_object(self,*_):
        a=Actor();self.actors.append(a);return a
    def spawn_actor_from_class(self,*_):
        a=Actor();self.actors.append(a);return a
class FakeAPI:
    class Paths:
        @staticmethod
        def get_project_file_path():return FakeAPI.project
    class UnrealEditorSubsystem:pass
    class EditorActorSubsystem:pass
    class CineCameraActor:pass
    class PointLight:pass
    class Actor:pass
    @staticmethod
    def Vector(*a):return a
    @staticmethod
    def Rotator(*a):return a
    class EditorAssetLibrary:
        @staticmethod
        def does_asset_exist(path):return False
    def __init__(self,project,level):
        FakeAPI.project=project;self.level=level;self.actors=FakeActors()
    def get_editor_subsystem(self,typ):
        if typ is self.EditorActorSubsystem:return self.actors
        return SimpleNamespace(get_editor_world=lambda: SimpleNamespace(get_path_name=lambda:self.level+'.World'))
    def load_asset(self,path):return Asset('SkeletalMesh')


def test_actual_spawning_requires_matching_level_and_creates_receipt(tmp_path):
    values=fixtures(tmp_path);s.plan(**values)
    api=FakeAPI(values['expected_project_path'], values['target_level'])
    receipt=tmp_path/'stage3_receipt.json'
    result=s.run(values['output_path'],str(receipt),unreal_api=api)
    assert result['status']=='ACTORS_CREATED_LEVEL_NOT_YET_VERIFIED'
    assert len(api.actors.actors)==8
    assert len(s.read(receipt)['actors_created'])==8
    assert len(s.read(values['mapping_output_path'])['entities'])==8


def test_wrong_unreal_level_rejects_without_mutation(tmp_path):
    values=fixtures(tmp_path);s.plan(**values)
    api=FakeAPI(values['expected_project_path'],'/Temp/Untitled')
    receipt=tmp_path/'blocked_receipt.json'
    with pytest.raises(s.SceneStageError,match='Wrong target level'):
        s.run(values['output_path'],str(receipt),unreal_api=api)
    assert len(api.actors.actors)==0
    assert s.read(receipt)['scene_modified'] is False


def test_existing_actor_label_prevents_partial_stage(tmp_path):
    values=fixtures(tmp_path);p=s.plan(**values)
    api=FakeAPI(values['expected_project_path'], values['target_level'])
    a=Actor();a.set_actor_label(p['actors'][0]['actor_label']);api.actors.actors.append(a)
    with pytest.raises(s.SceneStageError, match='already exists'):
        s.run(values['output_path'],str(tmp_path/'blocked.json'),unreal_api=api)
    assert len(api.actors.actors)==1
