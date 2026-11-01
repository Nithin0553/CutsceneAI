"""Exercise the automatic importer without requiring a running Unreal Editor."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'integrations'/'unreal'))
sys.path.insert(0,str(ROOT/'tools'))
import studio_auto_assets
import studio_auto_scene as scene
from test_studio_auto_assets import create


class Asset:
    def __init__(self,klass,path):
        self.klass,self.path=klass,path
        self.skeleton=None
    def get_class(self): return SimpleNamespace(get_name=lambda:self.klass)
    def get_editor_property(self,name):
        if name=='skeleton': return self.skeleton
        raise ValueError(name)
    def get_path_name(self): return self.path


class Task:
    def __init__(self): self.props={}
    def set_editor_property(self,name,value): self.props[name]=value


class Actor:
    def __init__(self,label=''):
        self.label=label
    def get_actor_label(self): return self.label
    def set_actor_label(self,label,mark_dirty=False): self.label=label


class Actors:
    def __init__(self): self.actors=[]
    def get_all_level_actors(self): return self.actors
    def spawn_actor_from_object(self,obj,loc,rot):
        x=Actor();self.actors.append(x);return x
    def spawn_actor_from_class(self,cls,loc,rot):
        x=Actor();self.actors.append(x);return x


class FakeUnreal:
    def __init__(self,project):
        self.project=project
        self.assets={}
        self.actor_sys=Actors()
        self.asset_tools=SimpleNamespace(import_asset_tasks=self.imports)
        self.Paths=SimpleNamespace(get_project_file_path=lambda:self.project)
        self.UnrealEditorSubsystem=object()
        self.EditorActorSubsystem=object()
        self.EditorAssetLibrary=SimpleNamespace(does_asset_exist=lambda p:p in self.assets)
        self.AssetToolsHelpers=SimpleNamespace(get_asset_tools=lambda:self.asset_tools)
        self.AssetImportTask=Task
        self.FbxImportUI=Task
        self.FBXImportType=SimpleNamespace(FBXIT_ANIMATION=1,FBXIT_SKELETAL_MESH=2,FBXIT_STATIC_MESH=3)
        self.CineCameraActor=object()
        self.PointLight=object()
        self.Actor=object()
        self.Vector=lambda *args:args
        self.Rotator=lambda *args:args
        self.LevelEditorSubsystem=object()
        self.levelsaver=SimpleNamespace(save_current_level=lambda:True)
        self.world=SimpleNamespace(get_path_name=lambda:'/Game/Tests/L_Test.L_Test')
    def get_editor_subsystem(self,kind):
        if kind is self.UnrealEditorSubsystem: return SimpleNamespace(get_editor_world=lambda:self.world)
        if kind is self.EditorActorSubsystem: return self.actor_sys
        if kind is self.LevelEditorSubsystem: return self.levelsaver
        raise AssertionError('Unknown subsystem')
    def load_asset(self,path): return self.assets.get(path)
    def imports(self,tasks):
        for task in tasks:
            opt=task.props.get('options')
            cls=('AnimSequence' if opt and opt.props.get('import_animations') else ('SkeletalMesh' if opt.props.get('import_as_skeletal') else 'StaticMesh') if opt else
                 'SoundWave' if task.props['filename'].endswith(('.wav', '.mp3')) else 'Texture2D')
            path=task.props['destination_path']+'/'+task.props['destination_name']
            asset=Asset(cls,path)
            if cls=='SkeletalMesh':
                skeleton=Asset('Skeleton',path+'_Skeleton')
                asset.skeleton=skeleton
            if cls=='AnimSequence': asset.skeleton=opt.props['skeleton']
            self.assets[path]=asset


def test_auto_setup_imports_and_spawns_without_prior_unreal_actors(tmp_path):
    root,files=create(tmp_path)
    stage=studio_auto_assets.inspect(*files,root,'Assets/Benchmark002','/Game/CutSceneAI/AutoTransfer/T_ABC')
    manifest=tmp_path/'auto-setup.json';manifest.write_text(json.dumps(stage))
    project=tmp_path/'NewProject.uproject';project.write_text('{}')
    unreal=FakeUnreal(str(project))
    receipt=scene.run(str(manifest),str(tmp_path/'auto-receipt.json'),
                      csir_path=str(files[0]),mapping_path=str(files[1]),plan_path=str(files[2]),
                      expected_project=str(project),expected_level='/Game/Tests/L_Test',unreal_api=unreal)
    assert receipt['status']=='SETUP_SAVED_UNVERIFIED'
    assert receipt['level_saved']
    assert len(receipt['actors_created'])==5
    assert len(receipt['assets_imported'])==6
    assert len(unreal.actor_sys.actors)==5
    assert receipt['fidelity_verified'] is False


def test_wrong_project_never_starts_import(tmp_path):
    root,files=create(tmp_path)
    stage=studio_auto_assets.inspect(*files,root,'Assets/Benchmark002','/Game/CutSceneAI/AutoTransfer/T_ABC')
    manifest=tmp_path/'auto-setup.json';manifest.write_text(json.dumps(stage))
    project=tmp_path/'NewProject.uproject';project.write_text('{}')
    fake=FakeUnreal(str(project))
    output=tmp_path/'auto-receipt.json'
    with pytest.raises(scene.AutomaticSetupError,match='Wrong Unreal project'):
        scene.run(str(manifest),str(output),csir_path=str(files[0]),mapping_path=str(files[1]),
                  plan_path=str(files[2]),expected_project=str(tmp_path/'Other.uproject'),
                  expected_level='/Game/Tests/L_Test',unreal_api=fake)
    assert json.loads(output.read_text())['status']=='BLOCKED'
    assert not fake.actor_sys.actors and not fake.assets


def test_collision_is_detected_before_any_mutation(tmp_path):
    root,files=create(tmp_path)
    stage=studio_auto_assets.inspect(*files,root,'Assets/Benchmark002','/Game/CutSceneAI/AutoTransfer/T_ABC')
    manifest=tmp_path/'auto-setup.json';manifest.write_text(json.dumps(stage))
    project=tmp_path/'NewProject.uproject';project.write_text('{}')
    fake=FakeUnreal(str(project))
    collision=stage['imports'][0]['target_asset_path'];fake.assets[collision]=Asset('SkeletalMesh',collision)
    output=tmp_path/'auto-receipt.json'
    with pytest.raises(scene.AutomaticSetupError,match='refuses existing target asset'):
        scene.run(str(manifest),str(output),csir_path=str(files[0]),mapping_path=str(files[1]),
                  plan_path=str(files[2]),expected_project=str(project),
                  expected_level='/Game/Tests/L_Test',unreal_api=fake)
    assert json.loads(output.read_text())['status']=='BLOCKED'
    assert not fake.actor_sys.actors


def test_prop_mesh_staged_as_static_mesh_when_source_is_identified(tmp_path):
    root, files = create(tmp_path)
    (root/'Assets'/'Benchmark002'/'Characters'/'PROP_MOVING.fbx').write_bytes(b'prop-mesh')
    stage=studio_auto_assets.inspect(*files,root,'Assets','/Game/CutSceneAI/AutoTransfer/T_ABC')
    manifest=tmp_path/'auto-setup.json';manifest.write_text(json.dumps(stage))
    project=tmp_path/'NewProject.uproject';project.write_text('{}')
    unreal=FakeUnreal(str(project))
    receipt=scene.run(str(manifest),str(tmp_path/'auto-receipt.json'),
                      csir_path=str(files[0]),mapping_path=str(files[1]),plan_path=str(files[2]),
                      expected_project=str(project),expected_level='/Game/Tests/L_Test',unreal_api=unreal)
    assert receipt['status']=='SETUP_SAVED_UNVERIFIED'
    assert any(a['kind']=='StaticMesh' for a in receipt['assets_imported'])


def test_mp3_source_imports_directly_without_ffmpeg(tmp_path):
    root, files=create(tmp_path, missing_audio=True)
    (root/'Assets'/'Benchmark002'/'Audio'/'Cue.mp3').write_bytes(b'ID3'+bytes(20))
    stage=studio_auto_assets.inspect(*files,root,'Assets/Benchmark002',
                                     '/Game/CutSceneAI/AutoTransfer/T_ABC')
    manifest=tmp_path/'auto-setup.json';manifest.write_text(json.dumps(stage))
    project=tmp_path/'NewProject.uproject';project.write_text('{}')
    fake=FakeUnreal(str(project))
    receipt=scene.run(str(manifest),str(tmp_path/'receipt.json'),
                      csir_path=str(files[0]),mapping_path=str(files[1]),
                      plan_path=str(files[2]),expected_project=str(project),
                      expected_level='/Game/Tests/L_Test',unreal_api=fake)
    assert receipt['status']=='SETUP_SAVED_UNVERIFIED'
    assert any(row['kind']=='SoundWave' for row in receipt['assets_imported'])
    assert len(fake.actor_sys.actors)==5


def test_duplicate_planned_label_blocks_before_any_import(tmp_path):
    root, files=create(tmp_path)
    plan=json.loads(files[2].read_text())
    plan['bindings']['CAM_A_Wide']=plan['bindings']['CAM_B_Move']
    files[2].write_text(json.dumps(plan))
    stage=studio_auto_assets.inspect(*files,root,'Assets/Benchmark002',
                                     '/Game/CutSceneAI/AutoTransfer/T_SAFE')
    assert not stage['ready']
    assert any('Duplicate planned Unreal actor label' in x for x in stage['blockers'])
    manifest=tmp_path/'setup.json';manifest.write_text(json.dumps(stage))
    project=tmp_path/'NewProject.uproject';project.write_text('{}')
    fake=FakeUnreal(str(project))
    receipt=tmp_path/'receipt.json'
    with pytest.raises(scene.AutomaticSetupError,match='cannot be automatically staged'):
        scene.run(str(manifest),str(receipt),csir_path=str(files[0]),
                  mapping_path=str(files[1]),plan_path=str(files[2]),
                  expected_project=str(project),expected_level='/Game/Tests/L_Test',
                  unreal_api=fake)
    assert not fake.assets and not fake.actor_sys.actors
    assert json.loads(receipt.read_text())['status']=='BLOCKED'


def test_existing_target_namespace_is_blocked_before_mutation(tmp_path):
    root,files=create(tmp_path)
    stage=studio_auto_assets.inspect(*files,root,'Assets/Benchmark002',
                                     '/Game/CutSceneAI/AutoTransfer/T_SAFE')
    manifest=tmp_path/'setup.json';manifest.write_text(json.dumps(stage))
    project=tmp_path/'NewProject.uproject';project.write_text('{}')
    fake=FakeUnreal(str(project))
    fake.EditorAssetLibrary.does_directory_exist=lambda path:path==stage['target_folder']
    receipt=tmp_path/'receipt.json'
    with pytest.raises(scene.AutomaticSetupError,match='namespace already exists'):
        scene.run(str(manifest),str(receipt),csir_path=str(files[0]),
                  mapping_path=str(files[1]),plan_path=str(files[2]),
                  expected_project=str(project),expected_level='/Game/Tests/L_Test',
                  unreal_api=fake)
    result=json.loads(receipt.read_text())
    assert result['status']=='BLOCKED' and not result['changes_possible']
    assert not fake.assets and not fake.actor_sys.actors


def test_partial_import_failure_keeps_precise_no_retry_receipt(tmp_path):
    root,files=create(tmp_path)
    stage=studio_auto_assets.inspect(*files,root,'Assets/Benchmark002',
                                     '/Game/CutSceneAI/AutoTransfer/T_SAFE')
    manifest=tmp_path/'setup.json';manifest.write_text(json.dumps(stage))
    project=tmp_path/'NewProject.uproject';project.write_text('{}')
    fake=FakeUnreal(str(project))
    native_import=fake.imports
    calls=[0]

    def fail_on_second(tasks):
        calls[0]+=1
        if calls[0]==2:
            raise RuntimeError('Native import failed halfway')
        return native_import(tasks)

    fake.asset_tools=SimpleNamespace(import_asset_tasks=fail_on_second)
    receipt_path=tmp_path/'partial.json'
    with pytest.raises(RuntimeError,match='failed halfway'):
        scene.run(str(manifest),str(receipt_path),csir_path=str(files[0]),
                  mapping_path=str(files[1]),plan_path=str(files[2]),
                  expected_project=str(project),expected_level='/Game/Tests/L_Test',
                  unreal_api=fake)
    receipt=json.loads(receipt_path.read_text())
    assert receipt['status']=='PARTIAL_SETUP_MUST_INSPECT'
    assert receipt['changes_possible']
    assert len(receipt['assets_imported'])==1
    assert receipt['asset_operations'][0]['status']=='NATIVE_CLASS_CHECKED'
    assert receipt['asset_operations'][1]['status']=='IMPORT_STARTED'
    assert len([x for x in receipt['asset_operations'] if x['status']=='NOT_STARTED'])==4
    assert all(x['status']=='NOT_STARTED' for x in receipt['actor_operations'])
    assert receipt['failed_step']['phase']=='asset_import'
    assert 'Do not rerun' in receipt['recovery']
    assert not fake.actor_sys.actors


def test_success_receipt_has_no_unreported_operations(tmp_path):
    root,files=create(tmp_path)
    stage=studio_auto_assets.inspect(*files,root,'Assets/Benchmark002',
                                     '/Game/CutSceneAI/AutoTransfer/T_SAFE')
    manifest=tmp_path/'setup.json';manifest.write_text(json.dumps(stage))
    project=tmp_path/'NewProject.uproject';project.write_text('{}')
    fake=FakeUnreal(str(project))
    receipt=scene.run(str(manifest),str(tmp_path/'receipt.json'),
                      csir_path=str(files[0]),mapping_path=str(files[1]),plan_path=str(files[2]),
                      expected_project=str(project),expected_level='/Game/Tests/L_Test',
                      unreal_api=fake)
    assert receipt['status']=='SETUP_SAVED_UNVERIFIED'
    assert receipt['failed_step'] is None
    assert all(x['status']=='NATIVE_CLASS_CHECKED' for x in receipt['asset_operations'])
    assert all(x['status']=='ACTOR_LABEL_CHECKED' for x in receipt['actor_operations'])
    assert len(receipt['assets_imported'])==len(receipt['asset_operations'])
    assert len(receipt['actors_created'])==len(receipt['actor_operations'])
