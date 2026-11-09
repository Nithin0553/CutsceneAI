"""Unreal Editor Stage 2: guarded animation-only FBX import into verified Skeletons.

No mesh reimport, retargeting, actor spawning, or cutscene generation. Only an
attempt to import source clips onto a chosen Skeleton (which is NOT evidence of
animation bone/motion compatibility). Writes an immutable receipt on failure.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import traceback
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / 'tools') not in sys.path:
    sys.path.insert(0, str(ROOT / 'tools'))
import studio_fresh_animation_plan as stage2


class AnimationImportError(RuntimeError):
    pass


def _project_path(api):
    raw = str(api.Paths.get_project_file_path())
    fn = getattr(api.Paths, 'convert_relative_path_to_full', None)
    return os.path.normcase(os.path.abspath(str(fn(raw)) if callable(fn) else raw))


def _level_path(api):
    world = api.get_editor_subsystem(api.UnrealEditorSubsystem).get_editor_world()
    return str(world.get_path_name()).split('.')[0]


def _class_name(asset):
    return str(asset.get_class().get_name()) if asset else ''


def _animation_task(api: Any, row: dict, skeleton: Any):
    task = api.AssetImportTask()
    target = row['target_asset_path']
    for prop, value in (
        ('filename', row['source_file']),
        ('destination_path', target.rsplit('/', 1)[0]),
        ('destination_name', target.rsplit('/', 1)[-1]),
        ('automated', True), ('replace_existing', False),
        ('save', True), ('async_', False),
    ):
        task.set_editor_property(prop, value)
    options = api.FbxImportUI()
    for prop, value in (
        ('automated_import_should_detect_type', False),
        ('mesh_type_to_import', api.FBXImportType.FBXIT_ANIMATION),
        ('import_as_skeletal', True), ('import_mesh', False),
        ('import_animations', True), ('import_materials', False),
        ('import_textures', False), ('skeleton', skeleton),
    ):
        options.set_editor_property(prop, value)
    task.set_editor_property('options', options)
    return task


def run(plan_path: str, receipt_path: str, *,
        rights_confirmed: bool = False, assignments_reviewed: bool = False,
        unreal_api: Any = None) -> dict:
    api = unreal_api
    if api is None:
        import unreal as api
    output = Path(receipt_path)
    if output.exists() or output.is_symlink():
        raise AnimationImportError('Refusing to replace an existing Stage 2 receipt.')
    if not output.parent.is_dir():
        raise AnimationImportError('Receipt parent directory missing.')
    receipt = {
        'kind': 'cutsceneai.studio.fresh_animation_import_receipt',
        'schema_version': '0.1.0', 'stage': 'preflight', 'status': 'BLOCKED',
        'plan_path': str(Path(plan_path).resolve()),
        'engine_changes_possible': False, 'scene_modified': False,
        'cutscene_generated': False, 'animation_motion_compatibility_verified': False,
        'retargeting_performed': False, 'fidelity_verified': False,
        'imported': [], 'created_utc': datetime.now(timezone.utc).isoformat(),
    }
    mutation_started = False
    try:
        if not rights_confirmed or not assignments_reviewed:
            raise AnimationImportError('Import rights and reviewed source-to-skeleton assignments must both be confirmed.')
        plan = stage2.verify(plan_path)
        if _project_path(api) != os.path.normcase(os.path.abspath(plan['target_project'])):
            raise AnimationImportError('Wrong Unreal project open.')
        if _level_path(api) != plan['target_level']:
            raise AnimationImportError('Wrong or unsaved level open.')
        receipt['verified_project'] = plan['target_project']
        receipt['verified_level'] = plan['target_level']
        folder = plan['target_folder']
        if api.EditorAssetLibrary.does_directory_exist(folder):
            raise AnimationImportError('Trial folder already exists; a new plan/folder is required.')
        for required in ('AssetImportTask', 'FbxImportUI', 'FBXImportType', 'AssetToolsHelpers'):
            if not hasattr(api, required):
                raise AnimationImportError('Unreal FBX import API unavailable: ' + required)
        if not hasattr(api.FBXImportType, 'FBXIT_ANIMATION'):
            raise AnimationImportError('Animation-only FBX import enum unavailable in this Unreal version.')
        verified_skeletons = {}
        for row in plan['animations']:
            if api.EditorAssetLibrary.does_asset_exist(row['target_asset_path']):
                raise AnimationImportError('Target animation already exists: ' + row['target_asset_path'])
            skeleton = api.load_asset(row['target_skeleton_path'])
            if _class_name(skeleton) != 'Skeleton':
                raise AnimationImportError('Verified source Skeleton missing in current Unreal project: ' + row['target_skeleton_path'])
            mesh = api.load_asset(row['target_mesh_path'])
            if _class_name(mesh) != 'SkeletalMesh':
                raise AnimationImportError('Persisted source SkeletalMesh missing: ' + row['target_mesh_path'])
            mesh_skeleton = mesh.get_editor_property('skeleton')
            if not mesh_skeleton or str(mesh_skeleton.get_path_name()) != row['target_skeleton_path']:
                raise AnimationImportError('SkeletalMesh now references a different Skeleton; stop import.')
            verified_skeletons[row['target_skeleton_path']] = skeleton
        receipt['stage'] = 'native_fbx_animation_import'
        for row in plan['animations']:
            task = _animation_task(api, row, verified_skeletons[row['target_skeleton_path']])
            mutation_started = True
            api.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
            asset = api.load_asset(row['target_asset_path'])
            if _class_name(asset) != 'AnimSequence':
                raise AnimationImportError('Animation-only FBX import did not create the expected AnimSequence: '
                                           + row['source_path'])
            imported_skeleton = asset.get_editor_property('skeleton')
            imported_skeleton_path = str(imported_skeleton.get_path_name()) if imported_skeleton else None
            if imported_skeleton_path != row['target_skeleton_path']:
                raise AnimationImportError('Imported AnimSequence references a different Skeleton: '
                                           + row['source_path'])
            play_length = None
            method = getattr(asset, 'get_play_length', None)
            if callable(method):
                try:
                    play_length = float(method())
                except Exception:
                    pass
            if play_length is not None and play_length <= 0.0:
                raise AnimationImportError('Imported animation has no playback duration: ' + row['source_path'])
            receipt['imported'].append({
                'source_path': row['source_path'], 'source_sha256': row['source_sha256'],
                'target_asset_path': row['target_asset_path'],
                'target_skeleton_path': imported_skeleton_path,
                'target_class': 'AnimSequence', 'play_length_seconds': play_length,
                'status': 'IMPORTED_ASSIGNED_SKELETON_UNVERIFIED',
            })
        receipt['stage'] = 'complete'
        receipt['status'] = 'IMPORTED_ANIMATIONS_UNVERIFIED'
        receipt['engine_changes_possible'] = True
        return receipt
    except Exception as exc:
        receipt['status'] = 'FAILED_MUST_INSPECT' if mutation_started else 'BLOCKED'
        receipt['engine_changes_possible'] = 'POSSIBLE_MUST_INSPECT' if mutation_started else False
        receipt['error'] = {
            'type': type(exc).__name__, 'message': str(exc),
            'traceback': traceback.format_exc(),
        }
        raise
    finally:
        with output.open('x', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + '\n')
