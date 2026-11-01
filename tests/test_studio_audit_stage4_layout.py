import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'integrations' / 'unreal' / 'studio_audit_stage4_layout.py'
spec = importlib.util.spec_from_file_location('studio_audit_stage4_layout', SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
ROOT = Path('/mnt/data')


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding='utf-8')


def fake_case(tmp_path):
    # These tests replay developer-local Stage 4 evidence, not repo fixtures.
    # Never fabricate benchmark evidence just to make CI pass.
    fixtures = (
        ROOT/'stage4_layout_plan_20261031_163928.json',
        ROOT/'stage4_layout_receipt_stage4_layout_plan_20261031_163928_retry01.json',
        ROOT/'stage3_scene_plan_20261031_162326.json',
    )
    if not all(p.is_file() for p in fixtures):
        pytest.skip("Stage 4 evidence fixtures are external and unavailable; "
                    "run with the original local benchmark artifacts.")
    base_plan = json.loads((ROOT/'stage4_layout_plan_20261031_163928.json').read_text())
    base_receipt = json.loads((ROOT/'stage4_layout_receipt_stage4_layout_plan_20261031_163928_retry01.json').read_text())
    base_stage3 = json.loads((ROOT/'stage3_scene_plan_20261031_162326.json').read_text())
    project = tmp_path/'Demo.uproject'
    project.write_text('{}')
    level = tmp_path/'Content'/'CutSceneAI'/'Tests'/'L_NewTarget_Test01.umap'
    level.parent.mkdir(parents=True)
    level.write_bytes(b'umap')
    base_plan['target_project'] = str(project)
    base_stage3['target_project'] = str(project)
    base_receipt['verified_project'] = str(project)
    dependencies = [
        ('source_csir_path','source_csir_sha256',{}),
        ('stage3_plan_path','stage3_plan_sha256',base_stage3),
        ('stage3_receipt_path','stage3_receipt_sha256',{}),
        ('stage3_audit_path','stage3_audit_sha256',{}),
        ('mapping_path','mapping_sha256',{}),
    ]
    for i,(path_key,digest_key,data) in enumerate(dependencies):
        f = tmp_path/f'evidence{i}.json'
        write_json(f,data)
        base_plan[path_key]=str(f)
        base_plan[digest_key]=hashlib.sha256(f.read_bytes()).hexdigest()
    plan_path = tmp_path/'layout.json'
    receipt_path = tmp_path/'receipt.json'
    base_receipt['plan_path']=str(plan_path)
    write_json(plan_path,base_plan)
    write_json(receipt_path,base_receipt)
    return plan_path, receipt_path, base_plan, base_stage3


class Actor:
    def __init__(self, label, kind, pose, mesh=None):
        self.label=label; self.kind=kind; self.mesh=mesh; self.parent=None
        loc=pose['location_cm']; rot=pose['rotation_rpy_degrees']; scale=pose.get('scale_xyz') or [1,1,1]
        self.loc=NS(x=loc[0],y=loc[1],z=loc[2]); self.rot=NS(roll=rot[0],pitch=rot[1],yaw=rot[2]); self.scale=NS(x=scale[0],y=scale[1],z=scale[2])
    def get_actor_label(self): return self.label
    def get_actor_location(self): return self.loc
    def get_actor_rotation(self): return self.rot
    def get_actor_scale3d(self): return self.scale
    def get_attach_parent_actor(self): return self.parent
    def get_class(self):
        return NS(get_name=lambda:{'character':'SkeletalMeshActor','camera':'CineCameraActor','light':'PointLight','prop':'Actor'}[self.kind])
    def get_component_by_class(self, typ):
        if self.mesh is None: return None
        mesh=self.mesh
        return NS(get_editor_property=lambda key: NS(get_path_name=lambda:mesh+'.'+mesh.rsplit('/',1)[-1]))


def fake_unreal(plan, stage3):
    poses={p['entity_name']:p for p in plan['placements']}
    actors={r['source_name']:Actor(r['actor_label'],r['kind'],poses[r['source_name']], r.get('mesh_path')) for r in stage3['actors']}
    for edge in plan['hierarchy']['attachments']:
        actors[edge['entity_name']].parent=actors[edge['source_parent_name']]
    engine=type('FakeUnreal',(),{})()
    engine.Paths=NS(get_project_file_path=lambda:plan['target_project'], convert_relative_path_to_full=lambda x:x)
    engine.UnrealEditorSubsystem=type('Editor',(),{})
    engine.EditorActorSubsystem=type('Actors',(),{})
    engine.SkeletalMeshComponent=type('SkeletalMeshComponent',(),{})
    engine.get_editor_subsystem=lambda subsystem:(NS(get_editor_world=lambda:NS(get_path_name=lambda:plan['target_level']+'.L_NewTarget_Test01')) if subsystem is engine.UnrealEditorSubsystem else NS(get_all_level_actors=lambda:list(actors.values())))
    engine.log=lambda msg:None
    return engine,actors


def test_structural_readback_passes(tmp_path):
    plan_path,receipt_path,plan,stage3=fake_case(tmp_path)
    engine,_=fake_unreal(plan,stage3)
    result=audit.run(str(plan_path),str(receipt_path),unreal_api=engine)
    assert result['status']=='STAGE4_SAVED_LAYOUT_READBACK'
    assert result['readback_count']==8
    assert result['attachments_verified']==1
    assert result['saved_level_file_exists'] is True
    assert result['sequence_generated'] is False


def test_bad_parent_is_detected(tmp_path):
    pp,rp,p,s=fake_case(tmp_path)
    engine,actors=fake_unreal(p,s)
    actors['PROP_PARENTED'].parent=None
    result=audit.run(str(pp),str(rp),unreal_api=engine)
    assert result['status']=='STAGE4_LAYOUT_READBACK_INCOMPLETE'
    assert result['attachments_verified']==0


def test_location_drift_is_detected(tmp_path):
    pp,rp,p,s=fake_case(tmp_path)
    engine,actors=fake_unreal(p,s)
    actors['CAM_A_Wide'].loc.x+=1.0
    result=audit.run(str(pp),str(rp),unreal_api=engine)
    assert result['status']=='STAGE4_LAYOUT_READBACK_INCOMPLETE'
    assert result['readback_count']==7


def test_rotation_wrap_and_small_precision_noise(tmp_path):
    pp,rp,p,s=fake_case(tmp_path)
    engine,actors=fake_unreal(p,s)
    actors['Ch31_nonPBR'].rot.yaw=-180.0
    actors['CAM_C_Close'].rot.yaw+=0.00001
    result=audit.run(str(pp),str(rp),unreal_api=engine)
    assert result['status']=='STAGE4_SAVED_LAYOUT_READBACK'


def test_wrong_project_hard_fails(tmp_path):
    pp,rp,p,s=fake_case(tmp_path)
    engine,_=fake_unreal(p,s)
    engine.Paths.get_project_file_path=lambda:'D:/Other/Other.uproject'
    with pytest.raises(audit.Stage4AuditError,match='Wrong Unreal project'):
        audit.run(str(pp),str(rp),unreal_api=engine)


def test_modified_source_evidence_hard_fails(tmp_path):
    pp,rp,p,s=fake_case(tmp_path)
    Path(p['source_csir_path']).write_text('changed')
    engine,_=fake_unreal(p,s)
    with pytest.raises(audit.Stage4AuditError,match='evidence changed'):
        audit.run(str(pp),str(rp),unreal_api=engine)


def test_missing_saved_level_is_detected(tmp_path):
    pp,rp,p,s=fake_case(tmp_path)
    (tmp_path/'Content'/'CutSceneAI'/'Tests'/'L_NewTarget_Test01.umap').unlink()
    engine,_=fake_unreal(p,s)
    result=audit.run(str(pp),str(rp),unreal_api=engine)
    assert result['status']=='STAGE4_LAYOUT_READBACK_INCOMPLETE'
    assert result['readback_count']==8
    assert not result['saved_level_file_exists']
