"""Regressions: root/Assets selection, broad source discovery and explicit ambiguity."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
import studio_project_discovery as discovery


def build(tmp_path, *, exported=True):
    u=tmp_path/'Unity'; (u/'Assets'/'Scenes').mkdir(parents=True); (u/'ProjectSettings').mkdir()
    (u/'Assets'/'Scenes'/'ActualScene.unity').write_text('native Unity file')
    p=tmp_path/'Unreal';(p/'Content'/'Cinematics').mkdir(parents=True)
    (p/'Example.uproject').write_text('{}')
    (p/'Content'/'Cinematics'/'Scene01.umap').write_bytes(b'fake')
    if exported:
        ex=u/'Assets'/'Custom'/'Deep'/'folder';ex.mkdir(parents=True)
        csir=ex/'anything.json'
        csir.write_text(json.dumps({'schema_version':'0.1.0','source':{'engine':'unity'},
            'cutscene_id':'example','name':'Scene One','tracks':[{'ced_type':'camera.cut','binding_entity_id':'cam','sections':[{}]}],
            'entities':[{'entity_id':'cam','name':'Camera','ced_type':'entity.camera'}], 'assets':[]}))
    return u,p


def test_assets_child_is_automatically_normalized_and_connects(tmp_path):
    u,p=build(tmp_path)
    x=discovery.discover(str(u/'Assets'),str(p/'Content'))
    assert x['ready']
    assert x['unity']['folder']==str(u.resolve())
    assert x['unreal']['folder']==str(p.resolve())
    scene=x['unity']['cutscenes'][0]
    assert scene['relative_path']=='Assets/Custom/Deep/folder/anything.json'
    c=discovery.build_connection(str(u/'Assets'),str(p/'Content'),scene['path'],x['unreal']['levels'][0],
                                workspace=tmp_path/'runs',source_rights_confirmed=True)
    assert c['unity_project']==str(u.resolve())
    assert Path(c['mapping']).is_file()


def test_multiple_projects_are_options_and_not_guessed(tmp_path):
    root=tmp_path/'Collection';root.mkdir()
    (root/'One').mkdir();(root/'Two').mkdir()
    for folder in (root/'One',root/'Two'):
        (folder/'Assets').mkdir();(folder/'ProjectSettings').mkdir()
    u,p=build(tmp_path)
    results=discovery.discover(str(root),str(p))
    assert len(results['unity_projects'])==2
    assert 'Select one' in results['errors']['unity']
    assert not results['ready']
    assert results['unreal']['project'].endswith('Example.uproject')


def test_multiple_cutscenes_and_maps_return_choices(tmp_path):
    u,p=build(tmp_path)
    (p/'Content'/'Cinematics'/'Second.umap').write_bytes(b'fake')
    # Same schema with different exported identity.
    orig=next((u/'Assets').rglob('anything.json'))
    other=json.loads(orig.read_text());other['cutscene_id']='second';other['name']='Another'
    (orig.parent/'export_alt.CSIR.json').write_text(json.dumps(other))
    d=discovery.discover(str(u),str(p))
    assert d['ready']
    assert len(d['unity']['cutscenes'])==2
    assert len(d['unreal']['levels'])==2


def test_no_export_explains_required_export_without_fake_success(tmp_path):
    u,p=build(tmp_path,exported=False)
    d=discovery.discover(str(u),str(p))
    assert not d['ready']
    assert 'Native Unity scene/Timeline files cannot yet be decoded' in d['unity']['message']
    assert d['unreal']['project']


def test_invalid_folder_keeps_valid_side_visible(tmp_path):
    u,p=build(tmp_path)
    d=discovery.discover(str(tmp_path/'NoSuchDir'),str(p))
    assert 'unity' in d['errors']
    assert d['unreal']['project']
    assert not d['ready']


def test_multiple_uprojects_require_choice(tmp_path):
    u,p=build(tmp_path)
    (p/'Another.uproject').write_text('{}')
    d=discovery.discover(str(u),str(p))
    assert d['unreal'] and not d['unreal']['project']
    assert len(d['unreal']['project_options'])==2 and not d['ready']
    selected=discovery.discover(str(u),str(p),unreal_project=str(p/'Example.uproject'))
    assert selected['ready']
    src=selected['unity']['cutscenes'][0]['path']
    connected=discovery.build_connection(str(u),str(p),src,selected['unreal']['levels'][0],
        workspace=tmp_path/'runs',unreal_project=str(p/'Example.uproject'))
    assert connected['target_project']==str((p/'Example.uproject').resolve())


def test_no_unreal_saved_level_still_connects_with_planned_new_level(tmp_path):
    u,p=build(tmp_path)
    (p/'Content'/'Cinematics'/'Scene01.umap').unlink()
    result=discovery.discover(str(u/'Assets'),str(p/'Content'))
    assert result['ready']
    assert result['unreal']['new_level_required'] is True
    assert result['unreal']['levels']==['/Game/CutSceneAI/AutoTransfer/L_Studio_Fresh']
    assert not (p/'Content'/'CutSceneAI'/'AutoTransfer'/'L_Studio_Fresh.umap').exists()
    selection=result['unity']['cutscenes'][0]['path']
    connected=discovery.build_connection(str(u/'Assets'),str(p),selection,
        result['unreal']['levels'][0],workspace=tmp_path/'runs')
    assert connected['auto_create_level'] is True
    assert not (p/'Content'/'CutSceneAI'/'AutoTransfer'/'L_Studio_Fresh.umap').exists()
