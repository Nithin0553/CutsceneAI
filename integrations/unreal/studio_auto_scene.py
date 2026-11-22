"""Opt-in automatic Unreal setup from an immutable, source-verified Unity plan.

Handles supported skeletal FBX, animation FBX, WAV/MP3 and PNG, plus source
characters/cameras/lights/transform props. Approved IK Retargeters can stage
native animation variants. A receipt records partial mutations.
"""
from __future__ import annotations

import json
import os
import re
import sys
import traceback
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT/'tools') not in sys.path:
    sys.path.insert(0,str(ROOT/'tools'))
import studio_auto_assets as assets_plan
import studio_collider_shapes
import studio_ik_retarget
import studio_material_restore


class AutomaticSetupError(RuntimeError):
    pass


def _project(api):
    raw=str(api.Paths.get_project_file_path())
    conv=getattr(api.Paths,'convert_relative_path_to_full',None)
    return os.path.normcase(os.path.abspath(str(conv(raw)) if callable(conv) else raw))


def _level(api):
    return str(api.get_editor_subsystem(api.UnrealEditorSubsystem).get_editor_world().get_path_name()).split('.')[0]


def _klass(asset):
    return str(asset.get_class().get_name()) if asset is not None else ''


def _static_import_stage(expected):
    """Use a unique import directory so repeated FBX mesh node names never collide."""
    parent, name = expected.rsplit('/', 1)
    return parent + '/_CutSceneAI_FbxImports/' + name + '/' + name


def _materialize_static_mesh(api, task, source, expected, stage):
    """Promote only a deterministically identified FBX mesh to its planned asset.

    Multi-mesh FBX files may ignore destination_name. In particular, Unity's
    Tree_02.fbx imports as Tree_02_LOD0 and Tree_02_LOD1 under UE 5.8.
    The source LOD0 mesh can supply the base StaticMesh, but a separate LOD1
    asset is NOT proof that the target mesh contains a corresponding LOD.
    """
    folder = stage.rsplit('/', 1)[0]
    if api.EditorAssetLibrary.does_asset_exist(expected):
        raise AutomaticSetupError('Refusing to overwrite planned prop mesh: ' + expected)
    direct = api.load_asset(stage)
    selected = stage if _klass(direct) == 'StaticMesh' else None
    other_lods = []
    if selected is None:
        try:
            paths = list(task.get_editor_property('imported_object_paths'))
        except (AttributeError, RuntimeError, ValueError, TypeError) as exc:
            raise AutomaticSetupError(
                'Unreal did not expose source-bound FBX imported object paths for ' + expected
            ) from exc
        stems = {
            Path(source).stem.casefold(),
            expected.rsplit('/', 1)[-1].casefold(),
            (expected.rsplit('/', 1)[-1] + '_' + Path(source).stem).casefold(),
        }
        lods = {}
        static_count = 0
        for value in paths:
            path = str(value).split('.', 1)[0]
            if path.rsplit('/', 1)[0] != folder:
                continue
            asset = api.load_asset(path)
            if _klass(asset) != 'StaticMesh':
                continue
            static_count += 1
            name = path.rsplit('/', 1)[-1]
            match = re.fullmatch(r'(.+)_LOD([0-9]+)', name, re.IGNORECASE)
            if match is None or match.group(1).casefold() not in stems:
                raise AutomaticSetupError(
                    'FBX contains an unrecognized separate mesh, not a source-approved LOD: '
                    + path
                )
            index = int(match.group(2))
            if index in lods:
                raise AutomaticSetupError('Ambiguous duplicate source FBX LOD index: ' + path)
            lods[index] = path
        if not lods or 0 not in lods or static_count != len(lods):
            raise AutomaticSetupError(
                'FBX did not provide exactly one identifiable source LOD0 StaticMesh: '
                + str(source)
            )
        selected = lods[0]
        other_lods = [lods[i] for i in sorted(lods) if i != 0]
    duplicator = getattr(api.EditorAssetLibrary, 'duplicate_asset', None)
    if not callable(duplicator):
        raise AutomaticSetupError('Unreal asset duplication API is unavailable for source FBX staging.')
    copied = duplicator(selected, expected)
    canonical = api.load_asset(expected)
    if not copied or _klass(canonical) != 'StaticMesh':
        raise AutomaticSetupError('Could not stage source-bound StaticMesh at ' + expected)
    return canonical, {
        'expected_asset': expected,
        'source_fbx': str(source),
        'source_mesh_path': selected,
        'separate_unverified_lod_meshes': other_lods,
        'lod_chain_verified': False,
    }


def _task(api, source, dest, kind, skeleton=None, embedded_materials=False):
    task=api.AssetImportTask()
    for name,val in (('filename',str(source)),('destination_path',dest.rsplit('/',1)[0]),
                     ('destination_name',dest.rsplit('/',1)[-1]),('replace_existing',False),
                     ('automated',True),('save',True),('async_',False)):
        task.set_editor_property(name,val)
    if kind in ('SkeletalMesh','AnimSequence','StaticMesh'):
        opts=api.FbxImportUI()
        for key,val in (('automated_import_should_detect_type',False),
                        ('mesh_type_to_import',api.FBXImportType.FBXIT_ANIMATION if kind=='AnimSequence' else api.FBXImportType.FBXIT_STATIC_MESH if kind=='StaticMesh' else api.FBXImportType.FBXIT_SKELETAL_MESH),
                        ('import_as_skeletal',kind=='SkeletalMesh'),('import_mesh',kind in ('SkeletalMesh','StaticMesh')),
                        ('import_animations',kind=='AnimSequence'),
                        ('import_materials',bool(embedded_materials) and kind in ('SkeletalMesh','StaticMesh')),
                        ('import_textures',bool(embedded_materials) and kind in ('SkeletalMesh','StaticMesh'))):
            opts.set_editor_property(key,val)
        if kind=='AnimSequence':
            opts.set_editor_property('skeleton',skeleton)
        elif kind=='SkeletalMesh':
            opts.set_editor_property('create_physics_asset',False)
        task.set_editor_property('options',opts)
    return task


def _save_level(api, level):
    ed=api.get_editor_subsystem(getattr(api,'LevelEditorSubsystem')) if hasattr(api,'LevelEditorSubsystem') else None
    saver=getattr(ed,'save_current_level',None)
    if callable(saver) and saver():
        return
    old=getattr(getattr(api,'EditorLevelLibrary',None),'save_current_level',None)
    if callable(old) and old():
        return
    raise AutomaticSetupError('Cannot persist the staged actors in this Unreal version. Inspect the scene and Save All manually; no sequence will be generated.')


def run(manifest_path, receipt_path, *,csir_path,mapping_path,plan_path,
        expected_project,expected_level, unreal_api=None):
    api=unreal_api
    if api is None:
        import unreal as api
    output=Path(receipt_path)
    if output.exists() or not output.parent.is_dir():
        raise AutomaticSetupError('Setup receipt already exists or its folder is missing.')
    receipt={'kind':'cutsceneai.studio.automatic_setup_receipt','schema_version':'0.1.0',
             'status':'BLOCKED','actors_created':[],'assets_imported':[],
             'asset_operations':[],'actor_operations':[],'failed_step':None,
             'level_saved':False,'changes_possible':False,'fidelity_verified':False,
              'material_restoration':[],
             'unsupported':['Custom shader graphs, textured PBR and translucent materials need separate adapters',
                            'Unity particle/VFX/constraints/scripts and signal payloads are not reconstructed',
                            'Imported animation bone correspondence and audio playback are not verified']}
    mutation=False
    try:
        manifest=assets_plan.verify(manifest_path,csir_path,mapping_path,plan_path)
        receipt['source_manifest_sha256']=assets_plan.digest(manifest_path)
        if not manifest['ready']:
            raise AutomaticSetupError('Source cannot be automatically staged: '+'; '.join(manifest['blockers'][:8]))
        if _project(api)!=os.path.normcase(os.path.abspath(str(expected_project))) or _level(api)!=expected_level:
            raise AutomaticSetupError('Wrong Unreal project or level; no changes made.')
        for required in ('AssetImportTask','AssetToolsHelpers','FbxImportUI','FBXImportType','EditorActorSubsystem'):
            if not hasattr(api,required):
                raise AutomaticSetupError('Unreal Python import capability unavailable: '+required)
        data=json.loads(Path(plan_path).read_text(encoding='utf-8-sig'))
        collider_actions = studio_collider_shapes.from_plan(data)
        pbr_candidates = manifest.get('source_pbr_actor_candidates') or {}
        studio_material_restore.preflight_constant_surfaces(api, pbr_candidates)
        sequence=data['sequence_asset_path']
        receipt['target_namespace']=manifest['target_folder']
        receipt['fbx_embedded_material_import_requested'] = (
            manifest.get('fbx_embedded_material_import_requested') is True
        )
        receipt['target_sequence']=sequence
        receipt['asset_operations']=[
            {'kind':row['kind'], 'path':row['target_asset_path'],
             'source_sha256':row['source_sha256'], 'status':'NOT_STARTED'}
            for row in manifest['imports']]
        receipt['actor_operations']=[
            {'name':row['name'], 'label':row['label'], 'status':'NOT_STARTED'}
            for row in manifest['actors']]
        planned_labels=[str(row['label']) for row in manifest['actors']]
        if len(planned_labels)!=len(set(planned_labels)):
            raise AutomaticSetupError('Automatic setup has duplicate planned actor labels; no changes made.')
        planned_paths=[str(row['target_asset_path']).casefold() for row in manifest['imports']]
        if len(planned_paths)!=len(set(planned_paths)):
            raise AutomaticSetupError('Automatic setup has duplicate target import paths; no changes made.')
        # Even unplanned assets in a reused staging namespace are dangerous.
        # Refuse before mutation when this Unreal API supports directory lookup.
        directory_exists=getattr(api.EditorAssetLibrary,'does_directory_exist',None)
        if callable(directory_exists) and directory_exists(manifest['target_folder']):
            raise AutomaticSetupError('Automatic setup target namespace already exists; choose a fresh candidate: '+manifest['target_folder'])
        if api.EditorAssetLibrary.does_asset_exist(sequence):
            raise AutomaticSetupError('Level Sequence path already occupied: '+sequence)
        # Resolve all source-backed light classes before importing an asset or
        # spawning any actor. Unknown types are never mapped to PointLight.
        light_classes = {'PointLight', 'SpotLight', 'DirectionalLight'}
        for row in manifest['actors']:
            if row['kind'] != 'entity.light':
                continue
            target_class = row.get('target_light_class') or 'PointLight'
            if target_class not in light_classes or not hasattr(api, target_class):
                raise AutomaticSetupError('Required Unreal native light class unavailable: '+
                                          str(target_class))
        ed=api.get_editor_subsystem(api.EditorActorSubsystem)
        current={}
        for actor in ed.get_all_level_actors():
            current.setdefault(str(actor.get_actor_label()),[]).append(actor)
        studio_collider_shapes.preflight(api, collider_actions, (*current, *planned_labels))
        for row in manifest['actors']:
            label=row['label']
            if len(current.get(label,[]))>1:
                raise AutomaticSetupError('Ambiguous existing actor label: '+label)
            if current.get(label):
                raise AutomaticSetupError('Existing scene actor uses automatic setup label; refusing to reuse or overwrite: '+label)
        if manifest['imports'] and not hasattr(api.AssetToolsHelpers,'get_asset_tools'):
            raise AutomaticSetupError('Unreal asset importer not available.')
        # Detect unsafe target collisions before any import or actor spawn.
        for row in manifest['imports']:
            if api.EditorAssetLibrary.does_asset_exist(row['target_asset_path']):
                raise AutomaticSetupError('Automatic setup refuses existing target asset: '+row['target_asset_path'])
        if any(row['kind'] == 'StaticMesh' for row in manifest['imports']):
            if not callable(getattr(api.EditorAssetLibrary, 'duplicate_asset', None)):
                raise AutomaticSetupError('Unreal asset duplication API is required for safe prop FBX staging.')
        retargeting = studio_ik_retarget.prepare(api, manifest)
        # Unreal Engine 5.8 supports importing MP3 and WAV directly into
        # SoundWave assets. Let the native importer validate the file and
        # verify the resulting Unreal asset class after import.
        asset_ops={row['path']:row for row in receipt['asset_operations']}
        actor_ops={row['name']:row for row in receipt['actor_operations']}
        meshes={}
        props={}
        receipt['static_mesh_imports'] = []
        groups=[('SkeletalMesh',manifest['imports']),('StaticMesh',manifest['imports']),('AnimSequence',manifest['imports']),
                ('SoundWave',manifest['imports']),('Texture2D',manifest['imports'])]
        for kind,records in groups:
            for row in records:
                if row['kind']!=kind:
                    continue
                source=row['source_file']
                character=row.get('character')
                approved=retargeting.get(character)
                import_path=row.get('source_animation_path', row['target_asset_path'])
                skeleton=None
                if kind=='AnimSequence':
                    mesh=meshes.get(character)
                    if mesh is None:
                        raise AutomaticSetupError('No newly imported character mesh for animation '+row['source_file'])
                    skeleton=mesh.get_editor_property('skeleton')
                    if skeleton is None:
                        raise AutomaticSetupError('Imported mesh has no skeleton: '+row.get('character',''))
                stage_path = (_static_import_stage(import_path)
                              if kind == 'StaticMesh' else import_path)
                task=_task(
                    api,source,stage_path,kind,skeleton,
                    embedded_materials=(
                        manifest.get('fbx_embedded_material_import_requested') is True
                    ),
                )
                operation=asset_ops[row['target_asset_path']]
                operation['status']='IMPORT_STARTED'
                receipt['failed_step']={'phase':'asset_import','kind':kind,
                                        'path':import_path}
                mutation=True
                api.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
                if kind == 'StaticMesh':
                    result, native = _materialize_static_mesh(
                        api, task, source, import_path, stage_path,
                    )
                    receipt['static_mesh_imports'].append(native)
                    if native['separate_unverified_lod_meshes']:
                        receipt['unsupported'].append(
                            'Imported ' + import_path +
                            ' from source LOD0; other FBX LOD meshes remain separate '
                            'and their native LOD chain is not verified.'
                        )
                else:
                    result=api.load_asset(import_path)
                if _klass(result)!=kind:
                    raise AutomaticSetupError('Import did not create '+kind+' at '+import_path)
                if kind=='SkeletalMesh':
                    meshes[character]=result
                    if approved:
                        receipt['failed_step']['phase']='retarget_source_reference_pose'
                        studio_ik_retarget.check_source(api, result, approved['source'])
                if kind=='StaticMesh':
                    props[row['target_asset_path']]=result
                if kind=='AnimSequence':
                    imported_skeleton = result.get_editor_property('skeleton')
                    if imported_skeleton is None or str(imported_skeleton.get_path_name()) != str(skeleton.get_path_name()):
                        raise AutomaticSetupError('Animation imported onto wrong skeleton: '+import_path)
                    if approved:
                        receipt['failed_step']={'phase':'ik_retarget','path':row['target_asset_path'],
                                                'source_animation_path':import_path}
                        studio_ik_retarget.duplicate_clip(api, row, meshes[character], approved)
                        operation['source_animation_path']=import_path
                operation['status']='NATIVE_CLASS_CHECKED'
                receipt['assets_imported'].append({'kind':kind,'path':row['target_asset_path']})
                receipt['failed_step']=None
        zero=api.Vector(0.0,0.0,0.0)
        rotation=api.Rotator(0.0,0.0,0.0)
        created_by_label={}
        for row in manifest['actors']:
            operation=actor_ops[row['name']]
            kind=row['kind']
            if kind=='entity.character':
                approved=retargeting.get(row['name'])
                obj=approved['target'] if approved else meshes.get(row['name'])
                if obj is None:
                    raise AutomaticSetupError('Missing source character: '+row['name'])
                operation['status']='SPAWN_STARTED'
                receipt['failed_step']={'phase':'actor_spawn','name':row['name'],
                                        'label':row['label']}
                mutation=True
                actor=ed.spawn_actor_from_object(obj,zero,rotation)
            elif kind=='entity.prop' and row.get('mesh_path'):
                obj=props.get(row['mesh_path'])
                if obj is None:
                    raise AutomaticSetupError('Missing imported static prop mesh: '+row['name'])
                operation['status']='SPAWN_STARTED'
                receipt['failed_step']={'phase':'actor_spawn','name':row['name'],
                                        'label':row['label']}
                mutation=True
                actor=ed.spawn_actor_from_object(obj,zero,rotation)
            else:
                cls = (getattr(api, row.get('target_light_class') or 'PointLight')
                       if kind == 'entity.light' else
                       api.CineCameraActor if kind == 'entity.camera' else api.Actor)
                operation['status']='SPAWN_STARTED'
                receipt['failed_step']={'phase':'actor_spawn','name':row['name'],
                                        'label':row['label']}
                mutation=True
                actor=ed.spawn_actor_from_class(cls,zero,rotation)
            if actor is None:
                raise AutomaticSetupError('Could not create '+row['name'])
            actor.set_actor_label(row['label'],mark_dirty=True)
            if actor.get_actor_label()!=row['label']:
                raise AutomaticSetupError('Unreal renamed actor unexpectedly: '+row['name'])
            operation['status']='ACTOR_LABEL_CHECKED'
            staged_identity={'name':row['name'],'label':row['label'],'kind':kind}
            # Exact native object identity is optional for historical
            # material/camera consumers, but REQUIRED by the new static
            # character yaw writer. An actor with the same display label
            # must not silently replace the originally staged character.
            get_path=getattr(actor,'get_path_name',None)
            if callable(get_path):
                native_actor_path=str(get_path())
                if native_actor_path and len(native_actor_path)<=1024:
                    staged_identity['native_actor_path']=native_actor_path
            receipt['actors_created'].append(staged_identity)
            created_by_label[row['label']]=actor
            receipt['failed_step']=None
        if retargeting:
            receipt['retargeted_rigs'] = []
            for row in manifest['actors']:
                profile = manifest['skeletal_retarget_profiles'].get(row['name'])
                if not profile:
                    continue
                receipt['failed_step']={'phase':'retarget_native_readback','name':row['name']}
                paths = [item['target_asset_path'] for item in manifest['imports']
                         if item.get('source_animation_path') and item['character'] == row['name']]
                observation = studio_ik_retarget.inspect(api, profile, paths, created_by_label[row['label']])
                receipt['retargeted_rigs'].append(dict(observation, actor=row['label']))
                if observation['status'] != 'PASS':
                    raise AutomaticSetupError('Retargeted actor or animation failed native readback: ' + row['name'])
                receipt['failed_step']=None
        actor_materials = manifest.get('source_albedo_actor_candidates')
        if actor_materials is not None and not isinstance(actor_materials, dict):
            raise AutomaticSetupError('Invalid actor-scoped source material manifest.')
        if (actor_materials or manifest.get('source_albedo_material_candidates')):
            material_cache = {}
            # Only the source renderer's exact .mat path may supply an actor's
            # slot. A global match on "Body" could give one actor the wrong
            # texture or discard both actors as ambiguous. Old manifests without
            # this field retain their conservative global matching behavior.
            for row in manifest['actors']:
                if row['kind'] not in ('entity.character', 'entity.prop'):
                    continue
                candidates = (actor_materials.get(row['name'], [])
                              if actor_materials is not None
                              else manifest['source_albedo_material_candidates'])
                if not candidates:
                    continue
                created = next((a for a in ed.get_all_level_actors()
                                if str(a.get_actor_label()) == row['label']), None)
                if created is None:
                    raise AutomaticSetupError('Newly spawned actor missing before material assignment: ' + row['name'])
                receipt['failed_step']={'phase':'material_restoration','name':row['name']}
                receipt['material_restoration'].extend(
                    dict(item, actor=row['name']) for item in studio_material_restore.restore(
                        api, created, candidates, existing_assets=material_cache)
                )
                receipt['failed_step']=None
        if pbr_candidates:
            material_cache={}
            receipt['constant_materials']=[]
            for row in manifest['actors']:
                candidates=pbr_candidates.get(row['name'], [])
                if not candidates:
                    continue
                receipt['failed_step']={'phase':'constant_material_staging','name':row['name']}
                receipt['constant_materials'].extend(
                    dict(item, actor=row['name']) for item in studio_material_restore.stage_constant_surfaces(
                        api, created_by_label[row['label']], candidates, material_cache)
                )
                receipt['failed_step']=None
        if collider_actions:
            receipt['failed_step'] = {'phase': 'native_collider_staging'}
            receipt['component_operations'] = []
            mutation = True
            studio_collider_shapes.stage(api, ed, collider_actions, receipt['component_operations'],
                                         owned_actors=created_by_label)
        receipt['failed_step']={'phase':'level_save','level':expected_level}
        _save_level(api,expected_level)
        receipt['level_saved']=True
        receipt['failed_step']=None
        receipt['status']='SETUP_SAVED_UNVERIFIED'
        receipt['changes_possible']=True
        receipt['source_assets_modified']=False
        return receipt
    except Exception as exc:
        receipt['status']='PARTIAL_SETUP_MUST_INSPECT' if mutation else 'BLOCKED'
        receipt['changes_possible']=bool(mutation)
        receipt['recovery']='Do not rerun this candidate. Inspect recorded Unreal assets and actors, save/copy the staging project for diagnosis, then prepare a NEW unique candidate.' if mutation else 'No editor mutation was attempted; fix the preflight issue before preparing another candidate.'
        receipt['error']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        raise
    finally:
        with output.open('x',encoding='utf-8') as fh:
            json.dump(receipt,fh,indent=2,ensure_ascii=False)
            fh.write('\n')
