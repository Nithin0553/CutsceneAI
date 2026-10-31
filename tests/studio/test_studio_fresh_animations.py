"""Stage 2 real-input planning and Unreal API mock regression tests."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'integrations/unreal'))
import studio_fresh_animation_plan as stage2
import studio_import_fresh_animations as engine


def dump(path, data):
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')
    return path


@pytest.fixture
def materials(tmp_path, monkeypatch):
    project = tmp_path / 'Target.uproject'
    project.write_text('{}')
    fbx = tmp_path / 'Walking.fbx'
    fbx.write_bytes(b'Kaydara FBX Binary not actually imported by unit tests')
    m = tmp_path / 'Ch31_nonPBR.fbx'
    m.write_bytes(b'not imported here')
    mesh_path = '/Game/CutSceneAI/FreshImport_01/Characters/CSAI_Ch31'
    skel_path = mesh_path + '_Skeleton.' + 'CSAI_Ch31_Skeleton'
    stage = {
        'target_project': str(project.resolve()),
        'target_folder': '/Game/CutSceneAI/FreshImport_01',
        'files': [
            {'role': 'CHARACTER_MODEL', 'status': 'CANDIDATE_SKELETAL_MODEL_UNVERIFIED',
             'target_asset_path': mesh_path, 'source_file': str(m),
             'source_path': 'Assets/Characters/Ch31_nonPBR.fbx',
             'sha256': stage2._digest(m)},
            {'role': 'ANIMATION_FBX', 'status': 'DEFERRED_SKELETON_COMPATIBILITY',
             'source_file': str(fbx), 'source_path': 'Assets/Animations/Walking.fbx',
             'sha256': stage2._digest(fbx)},
        ]
    }
    manifest = dump(tmp_path / 'manifest.json', stage)
    receipt = dump(tmp_path / 'receipt.json', {
        'kind': 'cutsceneai.studio.fresh_target_asset_import_receipt',
        'status': 'IMPORTED_ASSETS_UNVERIFIED',
        'manifest_path': str(manifest),
        'manifest_sha256': stage2._digest(manifest),
        'verified_project': str(project.resolve()),
        'imported': [{'target_asset_path': mesh_path, 'target_class': 'SkeletalMesh'}],
    })
    audit = dump(tmp_path / 'audit.json', {
        'kind': 'cutsceneai.studio.fresh_target_persistence_audit',
        'status': 'PERSISTED_ASSETS_AND_SKELETONS_READBACK',
        'receipt_path': str(receipt),
        'unreal_project': str(project.resolve()),
        'all_assets_readback': True, 'all_packages_saved': True,
        'skeletal_meshes_have_skeletons': True, 'skeleton_packages_saved': True,
        'rows': [{'target_asset_path': mesh_path, 'class_matches': True,
                  'package_file_exists': True, 'skeleton_package_file_exists': True,
                  'skeleton_asset_path': skel_path}],
    })
    assignments = dump(tmp_path / 'assignments.json', {'Walking.fbx': 'Ch31_nonPBR.fbx'})
    monkeypatch.setattr(stage2.stage1, 'verify', lambda path: stage)
    return SimpleNamespace(stage=stage, manifest=manifest, receipt=receipt,
                           audit=audit, assignments=assignments, fbx=fbx,
                           project=project, mesh=mesh_path, skeleton=skel_path)


def plan(m):
    return stage2.compose(m.manifest, m.receipt, m.audit, m.assignments,
                          m.stage['target_folder'] + '/Animations_trial01', '/Game/Tests/L_Test')


def test_plan_is_read_only_and_reverifiable(materials):
    m = materials
    p = plan(m)
    assert len(p['animations']) == 1
    assert p['animations'][0]['target_skeleton_path'] == m.skeleton
    path = dump(m.manifest.parent / 'animation_plan.json', p)
    assert stage2.verify(path) == p
    assert p['rig_compatibility_verified'] is False


def test_changed_animation_blocked(materials):
    m = materials
    p = plan(m)
    dump(m.manifest.parent / 'animation_plan.json', p)
    m.fbx.write_bytes(b'changed')
    with pytest.raises(stage2.Stage2Error, match='changed or missing'):
        stage2.verify(m.manifest.parent / 'animation_plan.json')


def test_missing_and_unknown_assignment_blocked(materials):
    m = materials
    for assignment in ({}, {'Walking.fbx':'Unknown.fbx'}):
        dump(m.assignments, assignment)
        with pytest.raises(stage2.Stage2Error, match='assignment|Assignment'):
            plan(m)


def test_wrong_stage1_provenance_blocked(materials):
    m = materials
    doc=json.loads(m.receipt.read_text())
    doc['manifest_sha256']='0'*64
    dump(m.receipt, doc)
    with pytest.raises(stage2.Stage2Error, match='manifest changed'):
        plan(m)


def test_unsafe_trial_folder_blocked(materials):
    m = materials
    with pytest.raises(stage2.Stage2Error, match='subfolder'):
        stage2.compose(m.manifest, m.receipt, m.audit, m.assignments,
                       '/Game/Elsewhere/Animations_trial', '/Game/Tests/L_Test')


class Object:
    def __init__(self, cls, path, skeleton=None):
        self.cls, self.path, self.skeleton = cls, path, skeleton
    def get_class(self):
        return SimpleNamespace(get_name=lambda: self.cls)
    def get_path_name(self):
        return self.path
    def get_editor_property(self, p):
        return self.skeleton if p == 'skeleton' else None
    def get_play_length(self):
        return 2.5


class Props:
    def __init__(self):
        self.values = {}
    def set_editor_property(self, k, v):
        self.values[k] = v


class FakeAPI:
    def __init__(self, m, expected):
        self.m = m
        self.assets = {m.skeleton: Object('Skeleton', m.skeleton)}
        self.assets[m.mesh] = Object('SkeletalMesh', m.mesh, self.assets[m.skeleton])
        self.project = str(m.project)
        self.level = '/Game/Tests/L_Test'
        self.invocations = 0
        self.Paths = SimpleNamespace(get_project_file_path=lambda: self.project)
        self.EditorAssetLibrary = SimpleNamespace(
            does_directory_exist=lambda path: False,
            does_asset_exist=lambda path: path in self.assets,
        )
        self.UnrealEditorSubsystem = object()
        self.AssetImportTask = Props
        self.FbxImportUI = Props
        self.FBXImportType = SimpleNamespace(FBXIT_ANIMATION=3)
        self.AssetToolsHelpers = SimpleNamespace(get_asset_tools=lambda: self)
        self.expected=expected

    def get_editor_subsystem(self, x):
        return SimpleNamespace(get_editor_world=lambda: SimpleNamespace(get_path_name=lambda: self.level + '.' + self.level.split('/')[-1]))

    def load_asset(self, target):
        return self.assets.get(target)

    def import_asset_tasks(self, tasks):
        self.invocations += 1
        opts = tasks[0].values['options'].values
        assert opts['import_mesh'] is False
        assert opts['import_animations'] is True
        assert opts['mesh_type_to_import'] == 3
        assert tasks[0].values['replace_existing'] is False
        assert opts['skeleton'] is self.assets[self.m.skeleton]
        if self.expected == 'success':
            task = tasks[0].values
            key = task['destination_path'] + '/' + task['destination_name']
            self.assets[key] = Object('AnimSequence', key, self.assets[self.m.skeleton])


def test_import_preflight_refuses_without_review(materials, monkeypatch):
    m = materials
    data = plan(m)
    monkeypatch.setattr(engine.stage2, 'verify', lambda _: data)
    api = FakeAPI(m, 'success')
    out = m.project.parent / 'stage2_receipt.json'
    with pytest.raises(engine.AnimationImportError, match='rights and reviewed'):
        engine.run('stub', str(out), unreal_api=api, rights_confirmed=False)
    assert json.loads(out.read_text())['status'] == 'BLOCKED'
    assert api.invocations == 0


def test_import_animation_only_with_verified_skeleton(materials, monkeypatch):
    m = materials
    data = plan(m)
    monkeypatch.setattr(engine.stage2, 'verify', lambda _: data)
    api = FakeAPI(m, 'success')
    out = m.project.parent / 'stage2_receipt.json'
    result = engine.run('stub', str(out), unreal_api=api, rights_confirmed=True,
                        assignments_reviewed=True)
    assert api.invocations == 1
    assert result['status'] == 'IMPORTED_ANIMATIONS_UNVERIFIED'
    assert result['imported'][0]['play_length_seconds'] == 2.5
    assert result['fidelity_verified'] is False


def test_native_import_failure_receipted_and_not_retried(materials, monkeypatch):
    m = materials
    data = plan(m)
    monkeypatch.setattr(engine.stage2, 'verify', lambda _: data)
    api = FakeAPI(m, 'fail')
    out = m.project.parent / 'stage2_receipt.json'
    with pytest.raises(engine.AnimationImportError, match='did not create'):
        engine.run('stub', str(out), unreal_api=api, rights_confirmed=True,
                   assignments_reviewed=True)
    doc = json.loads(out.read_text())
    assert doc['status'] == 'FAILED_MUST_INSPECT'
    assert doc['engine_changes_possible'] == 'POSSIBLE_MUST_INSPECT'
    assert api.invocations == 1
    with pytest.raises(engine.AnimationImportError, match='existing Stage 2 receipt'):
        engine.run('stub', str(out), unreal_api=api, rights_confirmed=True,
                   assignments_reviewed=True)
    assert api.invocations == 1


def test_wrong_editor_project_fails_before_import(materials, monkeypatch):
    m = materials
    data=plan(m)
    monkeypatch.setattr(engine.stage2, 'verify', lambda _: data)
    api=FakeAPI(m,'success')
    api.project=str(m.project.parent/'Wrong.uproject')
    out=m.project.parent/'wrong_receipt.json'
    with pytest.raises(engine.AnimationImportError, match='Wrong Unreal project'):
        engine.run('stub',str(out), unreal_api=api,rights_confirmed=True,assignments_reviewed=True)
    assert api.invocations==0
