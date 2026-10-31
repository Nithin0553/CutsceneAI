"""Stage 3 guarded target scene staging for CutSceneAI Benchmark 002.

Read-only plan plus opt-in editor actor staging. No retargeting, asset import,
material authoring, Sequencer generation, or fidelity verification. Generic
importers should replace this benchmark-specific binding policy in the future.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import traceback
from typing import Any


class SceneStageError(ValueError):
    pass


def read(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise SceneStageError('Expected JSON object: ' + str(path))
    return data


def sha(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _new_json(path: str | Path, data: dict) -> None:
    target = Path(path)
    if not target.parent.is_dir():
        raise SceneStageError('Output parent missing: ' + str(target.parent))
    with target.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write('\n')


def _path_key(value: str) -> str:
    return os.path.normcase(os.path.abspath(str(value)))


def _get_json_checked(path: str | Path, expected_kind: str, statuses: set[str]) -> dict:
    data = read(path)
    if data.get('kind') != expected_kind or data.get('status') not in statuses:
        raise SceneStageError(f'Invalid {expected_kind} status or schema in {path}')
    return data


def plan(*, csir_path: str, stage1_receipt_path: str,
         stage2_receipt_path: str, stage2_audit_path: str, target_level: str,
         output_path: str, mapping_output_path: str,
         expected_project_path: str) -> dict[str, Any]:
    """Prepare a source-bound fresh actor staging. Does not call Unreal."""
    csir = read(csir_path)
    first = _get_json_checked(stage1_receipt_path,
                              'cutsceneai.studio.fresh_target_asset_import_receipt',
                              {'IMPORTED_ASSETS_UNVERIFIED'})
    second = _get_json_checked(stage2_receipt_path,
                               'cutsceneai.studio.fresh_animation_import_receipt',
                               {'IMPORTED_ANIMATIONS_UNVERIFIED'})
    audit = _get_json_checked(stage2_audit_path,
                              'cutsceneai.studio.animation_readback_audit',
                              {'PERSISTED_AND_SAMPLED_MOTION_OBSERVED'})
    if csir.get('schema_version') != '0.1.0' or csir.get('source', {}).get('engine') != 'unity':
        raise SceneStageError('Unsupported source CSIR')
    if _path_key(expected_project_path) != _path_key(first['verified_project']) or _path_key(expected_project_path) != _path_key(second['verified_project']):
        raise SceneStageError('Receipts belong to a different Unreal project.')
    if first['verified_level'] != target_level or second['verified_level'] != target_level:
        raise SceneStageError('Receipt level does not match requested target level.')
    if not target_level.startswith('/Game/'):
        raise SceneStageError('Target level must be a saved /Game asset.')
    # Tie the chain to the same original Unity export; otherwise successful
    # imports from an unrelated cutscene could be staged into this level.
    first_manifest = read(first['manifest_path'])
    if first_manifest.get('source_csir_sha256') != sha(csir_path):
        raise SceneStageError('Stage 1 source CSIR does not match this export.')
    if first.get('manifest_sha256') != sha(first['manifest_path']):
        raise SceneStageError('Stage 1 source manifest was modified after import.')
    second_plan = read(second['plan_path'])
    if second_plan.get('stage1_receipt_sha256') != sha(stage1_receipt_path):
        raise SceneStageError('Stage 2 used a different Stage 1 import receipt.')
    if not audit.get('all_structural_trials_ready') or _path_key(audit['unreal_project']) != _path_key(expected_project_path):
        raise SceneStageError('Animation persistence audit not ready for this project.')
    if len(audit.get('rows', [])) != 3 or not all(row.get('structural_trial_ready') for row in audit['rows']):
        raise SceneStageError('Stage 2 does not contain three verified animation readbacks.')
    if _path_key(audit['source_receipt']) != _path_key(stage2_receipt_path) or audit['source_receipt_sha256'] != sha(stage2_receipt_path):
        raise SceneStageError('Animation receipt changed since audit.')

    models = {Path(x['source_path']).name: x['target_asset_path']
              for x in first.get('imported', []) if x.get('target_class') == 'SkeletalMesh'}
    anims = {Path(x['source_path']).name: x['target_asset_path']
             for x in second.get('imported', []) if x.get('target_class') == 'AnimSequence'}
    if set(models) != {'Ch31_nonPBR.fbx', 'Ch26_nonPBR.fbx'}:
        raise SceneStageError('Expected two unique imported Benchmark 002 character models.')
    if set(anims) != {'Walking.fbx', 'Waving.fbx', 'Breathing Idle.fbx'}:
        raise SceneStageError('Expected three unique imported Benchmark 002 animations.')
    known = {str(x['name']): x for x in csir.get('entities', [])}
    characters = {'Ch31_nonPBR': models['Ch31_nonPBR.fbx'],
                  'Ch26_nonPBR': models['Ch26_nonPBR.fbx']}
    required = {'Ch31_nonPBR': 'character', 'Ch26_nonPBR': 'character',
                'CAM_A_Wide': 'camera', 'CAM_B_Move': 'camera',
                'CAM_C_Close': 'camera', 'LIGHT_KEY': 'light',
                'PROP_MOVING': 'prop', 'PROP_PARENTED': 'prop'}
    for name, kind in required.items():
        record = known.get(name)
        if not record or record.get('ced_type') != {'character':'entity.character','camera':'entity.camera','light':'entity.light','prop':'entity.prop'}[kind]:
            raise SceneStageError('Missing required source entity or changed type: ' + name)
    if Path(output_path).exists() or Path(mapping_output_path).exists():
        raise SceneStageError('Refusing to overwrite a prior plan or mapping.')
    token = re.sub('[^A-Za-z0-9_]', '_', Path(output_path).stem)[:54]
    actors = [
        {'source_name': name, 'source_entity_id': known[name]['entity_id'],
         'kind': kind, 'actor_label': f'CSAI_{token}_{name}',
         'mesh_path': characters.get(name)}
        for name, kind in required.items()
    ]
    expected_assets = {'A_Walk_RootMotion': anims['Walking.fbx'],
                       'A_BreathingIdle': anims['Breathing Idle.fbx'],
                       'B_Waving': anims['Waving.fbx']}
    asset_names = {x['name'] for x in csir.get('assets', [])}
    missing_anim_names = set(expected_assets).difference(asset_names)
    if missing_anim_names:
        raise SceneStageError('CSIR animation name mismatch: ' + ', '.join(sorted(missing_anim_names)))
    mapping = {
        'sequence_asset_path': '/Game/CutSceneAI/Tests/LS_' + token,
        'overwrite_sequence': False,
        'entities': {a['source_name']: {'actor_label': a['actor_label']} for a in actors},
        'assets': expected_assets,
    }
    transfer = {
        'kind': 'cutsceneai.studio.stage3_scene_plan',
        'schema_version': '0.1.0',
        'csir_path': str(Path(csir_path).resolve()), 'csir_sha256': sha(csir_path),
        'stage1_receipt_path': str(Path(stage1_receipt_path).resolve()),
        'stage1_receipt_sha256': sha(stage1_receipt_path),
        'stage2_receipt_path': str(Path(stage2_receipt_path).resolve()),
        'stage2_receipt_sha256': sha(stage2_receipt_path),
        'stage2_audit_path': str(Path(stage2_audit_path).resolve()),
        'stage2_audit_sha256': sha(stage2_audit_path),
        'target_project': str(Path(expected_project_path).resolve()),
        'target_level': target_level,
        'actors': actors,
        'mapping_output_path': str(Path(mapping_output_path).resolve()),
        'mapping': mapping,
        'skipped_source_entities': [x['name'] for x in csir.get('entities', []) if x['name'] not in required],
        'assets_not_staged': ['Ambience.mp3', 'Cue.mp3', 'materials', 'prop meshes', 'Unity signal payloads'],
        'generation_executed': False, 'level_modified': False,
        'source_target_fidelity_verified': False,
        'notes': ['Actor transforms are placeholders until source scene prep/capture is applied.',
                  'Props have no mesh representation yet. Camera optics and lighting parity remain unverified.',
                  'Only the 8 selected top-level entities are staged; source subcomponents are not blindly spawned.',
                  'Audio and event semantics need separate treatment.'],
    }
    _new_json(output_path, transfer)
    return transfer


def verify(plan_path: str | Path) -> dict:
    data = read(plan_path)
    if data.get('kind') != 'cutsceneai.studio.stage3_scene_plan' or data.get('schema_version') != '0.1.0':
        raise SceneStageError('Unknown Stage 3 plan schema.')
    for field, key in (
        ('csir_path', 'csir_sha256'), ('stage1_receipt_path', 'stage1_receipt_sha256'),
        ('stage2_receipt_path', 'stage2_receipt_sha256'), ('stage2_audit_path', 'stage2_audit_sha256')
    ):
        if sha(data[field]) != data[key]:
            raise SceneStageError(field + ' content changed; refuse stale plan.')
    if data.get('generation_executed') is not False or data.get('level_modified') is not False:
        raise SceneStageError('Plan falsely claims modifications.')
    if data['mapping'].get('overwrite_sequence') is not False:
        raise SceneStageError('Unsafe overwrite setting.')
    if not data['target_level'].startswith('/Game/'):
        raise SceneStageError('Unsafe level path')
    if len(data['actors']) != 8 or len({x['actor_label'] for x in data['actors']}) != 8:
        raise SceneStageError('Invalid actor selection.')
    return data


def run(plan_path: str, receipt_path: str, *, unreal_api=None) -> dict[str, Any]:
    """Opt-in Unreal Editor mutation; no engine execution in unit tests."""
    api = unreal_api
    if api is None:
        import unreal as api
    result = {'kind': 'cutsceneai.studio.stage3_scene_receipt',
              'schema_version': '0.1.0', 'status': 'BLOCKED',
              'plan_path': str(Path(plan_path).resolve()),
              'actors_created': [], 'scene_modified': False,
              'level_saved': False, 'cutscene_generated': False,
              'fidelity_verified': False}
    mutation = False
    try:
        if Path(receipt_path).exists() or Path(result['plan_path']).resolve() == Path(receipt_path).resolve():
            raise SceneStageError('Existing receipt or unsafe receipt path.')
        plan_data = verify(plan_path)
        raw = str(api.Paths.get_project_file_path())
        full = getattr(api.Paths, 'convert_relative_path_to_full', None)
        actual = str(full(raw)) if callable(full) else raw
        if _path_key(actual) != _path_key(plan_data['target_project']):
            raise SceneStageError(f'Wrong target Unreal project: {actual}')
        world = api.get_editor_subsystem(api.UnrealEditorSubsystem).get_editor_world()
        level = str(world.get_path_name()).split('.')[0]
        if level != plan_data['target_level']:
            raise SceneStageError(f'Wrong target level: {level}')
        subsystem = api.get_editor_subsystem(api.EditorActorSubsystem)
        labels = {a.get_actor_label() for a in subsystem.get_all_level_actors()}
        for row in plan_data['actors']:
            if row['actor_label'] in labels:
                raise SceneStageError('Actor label already exists: ' + row['actor_label'])
        if api.EditorAssetLibrary.does_asset_exist(plan_data['mapping']['sequence_asset_path']):
            raise SceneStageError('Target Level Sequence already exists; no overwrite.')
        if Path(plan_data['mapping_output_path']).exists():
            raise SceneStageError('Target mapping filename already exists.')
        for type_name in ('CineCameraActor', 'PointLight', 'Actor'):
            if not hasattr(api, type_name):
                raise SceneStageError(f'Missing target actor type: {type_name}')
        mesh_assets = {}
        for row in plan_data['actors']:
            if row['kind'] == 'character':
                asset = api.load_asset(row['mesh_path'])
                if not asset or str(asset.get_class().get_name()) != 'SkeletalMesh':
                    raise SceneStageError('Character SkeletalMesh unavailable: ' + row['mesh_path'])
                mesh_assets[row['source_name']] = asset
        result['status'] = 'SPAWNING_UNVERIFIED'
        zero = api.Vector(0.0, 0.0, 0.0)
        rot = api.Rotator(0.0, 0.0, 0.0)
        for row in plan_data['actors']:
            mutation = True
            if row['kind'] == 'character':
                actor = subsystem.spawn_actor_from_object(mesh_assets[row['source_name']], zero, rot)
            else:
                cls = {'camera': api.CineCameraActor, 'light': api.PointLight, 'prop': api.Actor}[row['kind']]
                actor = subsystem.spawn_actor_from_class(cls, zero, rot)
            if actor is None:
                raise SceneStageError('Unreal failed to spawn: ' + row['source_name'])
            actor.set_actor_label(row['actor_label'], mark_dirty=True)
            if str(actor.get_actor_label()) != row['actor_label']:
                raise SceneStageError('Unreal changed generated actor label: ' + row['source_name'])
            result['actors_created'].append({'source_name': row['source_name'],
                                             'actor_label': row['actor_label'],
                                             'actor_path': str(actor.get_path_name()),
                                             'expected_mesh_path': row.get('mesh_path')})
        result['scene_modified'] = True
        # The new mapping is written only after all required actors were spawned.
        _new_json(plan_data['mapping_output_path'], plan_data['mapping'])
        result['mapping_path'] = plan_data['mapping_output_path']
        result['status'] = 'ACTORS_CREATED_LEVEL_NOT_YET_VERIFIED'
        return result
    except Exception as exc:
        result['scene_modified'] = 'POSSIBLE_MUST_INSPECT' if mutation else False
        result['status'] = 'FAILED_MUST_INSPECT' if mutation else 'BLOCKED'
        result['error'] = {'type': type(exc).__name__, 'message': str(exc),
                           'traceback': traceback.format_exc()}
        raise
    finally:
        _new_json(receipt_path, result)
