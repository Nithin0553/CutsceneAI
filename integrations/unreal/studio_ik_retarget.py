"""Use approved Unreal IK Retargeter assets to duplicate staged AnimSequences."""
from __future__ import annotations

from collections import Counter


class RetargetError(RuntimeError):
    pass


def _path(asset):
    return str(asset.get_path_name()).split('.', 1)[0] if asset is not None else ''


def _class(asset):
    return str(asset.get_class().get_name()) if asset is not None else ''


def _skeleton(asset):
    return asset.get_editor_property('skeleton')


def prepare(api, manifest):
    """Resolve already configured retargeters before importing or spawning."""
    profiles = manifest.get('skeletal_retarget_profiles', {})
    if not profiles:
        return {}
    if not all(callable(getattr(getattr(api, owner, None), name, None)) for owner, name in (
            ('IKRetargeterController', 'get_controller'),
            ('IKRetargetBatchOperation', 'duplicate_and_retarget'),
            ('EditorAssetLibrary', 'find_asset_data'),
            ('EditorAssetLibrary', 'save_loaded_asset'),
            ('AnimPoseExtensions', 'get_reference_pose'),
            ('AnimPoseExtensions', 'get_bone_names'),
            ('AnimPoseExtensions', 'get_bone_pose'))):
        raise RetargetError('Unreal IKRig Editor and reference-pose Python APIs are required.')
    roles = getattr(api, 'RetargetSourceOrTarget', None)
    if roles is None or not hasattr(roles, 'SOURCE') or not hasattr(roles, 'TARGET'):
        raise RetargetError('Unreal IKRig retarget source and target roles are unavailable.')
    occupied = {row['target_asset_path'].casefold() for row in manifest['imports']}
    for row in manifest['imports']:
        scratch = row.get('source_animation_path')
        if scratch is None:
            continue
        if scratch.casefold() in occupied or api.EditorAssetLibrary.does_asset_exist(scratch):
            raise RetargetError('IK retargeting refuses an occupied source clip path: ' + scratch)
        occupied.add(scratch.casefold())
    resolved = {}
    for character, profile in profiles.items():
        retargeter = api.load_asset(profile['retargeter_path'])
        if _class(retargeter) != 'IKRetargeter' or _path(retargeter) != profile['retargeter_path']:
            raise RetargetError('Cannot resolve approved Unreal IK Retargeter for ' + character)
        controller = api.IKRetargeterController.get_controller(retargeter)
        if controller is None:
            raise RetargetError('The approved IK Retargeter needs authored source and target rigs: ' + character)
        source_rig, target_rig = (controller.get_ik_rig(role) for role in (roles.SOURCE, roles.TARGET))
        if source_rig is None or target_rig is None:
            raise RetargetError('The approved IK Retargeter needs authored source and target rigs: ' + character)
        source = controller.get_preview_mesh(roles.SOURCE)
        target = controller.get_preview_mesh(roles.TARGET)
        if (_class(source) != 'SkeletalMesh' or _class(target) != 'SkeletalMesh'
                or _path(source) != profile['source_mesh_path'] or _path(target) != profile['target_mesh_path']
                or not _path(_skeleton(source)) or not _path(_skeleton(target))):
            raise RetargetError('Approved IK Retargeter preview meshes no longer match ' + character)
        resolved[character] = {'retargeter': retargeter, 'source': source, 'target': target,
                               'source_rig': source_rig, 'target_rig': target_rig}
    return resolved


def check_source(api, staged_mesh, approved_mesh):
    """Require the fresh import to match the reference rig used for calibration."""
    extension = api.AnimPoseExtensions
    fresh = extension.get_reference_pose(_skeleton(staged_mesh))
    reference = extension.get_reference_pose(_skeleton(approved_mesh))
    names = tuple(str(bone) for bone in extension.get_bone_names(fresh))
    if not names or set(names) != {str(bone) for bone in extension.get_bone_names(reference)}:
        raise RetargetError('Fresh Unity FBX bone names disagree with the approved source rig.')
    for bone in names:
        if (str(staged_mesh.get_bone_parent(bone)) != str(approved_mesh.get_bone_parent(bone))
                or extension.get_bone_pose(fresh, bone) != extension.get_bone_pose(reference, bone)):
            raise RetargetError('Fresh Unity FBX reference hierarchy or local pose differs at ' + bone)


def duplicate_clip(api, row, staged_mesh, approved):
    """Write a single editable clip using IKRig's fixed native operation."""
    source, dest = row['source_animation_path'], row['target_asset_path']
    assets = api.EditorAssetLibrary
    if assets.does_asset_exist(dest):
        raise RetargetError('IK retargeting refuses to overwrite ' + dest)
    created = api.IKRetargetBatchOperation.duplicate_and_retarget(
        [assets.find_asset_data(source)], staged_mesh, approved['target'], approved['retargeter'],
        target_path=dest.rsplit('/', 1)[0], use_source_path=False,
        include_referenced_assets=False, overwrite_existing_files=False,
    )
    if len(created) != 1:
        raise RetargetError('IK Retargeter did not create exactly one animation at ' + dest)
    clip = created[0].get_asset()
    if (_class(clip) != 'AnimSequence' or _path(clip) != dest
            or _path(_skeleton(clip)) != _path(_skeleton(approved['target']))):
        raise RetargetError('IK Retargeter output does not match the planned path and target skeleton: ' + dest)
    if not assets.save_loaded_asset(clip):
        raise RetargetError('Could not save the retargeted AnimSequence at ' + dest)


def inspect(api, profile, clip_paths, actor):
    """Read the exact skeletal mesh and animation skeletons from native assets."""
    mesh = api.load_asset(profile['target_mesh_path'])
    expected_skeleton = _path(_skeleton(mesh)) if _class(mesh) == 'SkeletalMesh' else ''
    component = actor.get_editor_property('skeletal_mesh_component') if actor is not None else None
    actual_mesh = _path(component.get_skeletal_mesh_asset()) if component is not None else ''
    clip_skeletons = {}
    for path in clip_paths:
        clip = api.load_asset(path)
        clip_skeletons[path] = _path(_skeleton(clip)) if _class(clip) == 'AnimSequence' else ''
    passed = (bool(expected_skeleton) and _path(mesh) == profile['target_mesh_path']
              and actual_mesh == profile['target_mesh_path'] and bool(clip_paths)
              and all(name == expected_skeleton for name in clip_skeletons.values()))
    return {'status': 'PASS' if passed else 'FAIL', 'expected_mesh': profile['target_mesh_path'],
            'observed_mesh': actual_mesh, 'expected_skeleton': expected_skeleton,
            'clip_skeletons': clip_skeletons}


def inspect_sections(api, sequence, actor, expected):
    """Measure saved animation asset references on the actual actor binding."""
    observed = []
    result = {'status': 'INCOMPLETE', 'expected_assets': expected, 'observed_assets': observed}
    try:
        extensions = api.MovieSceneSequenceExtensions
        world = api.get_editor_subsystem(api.UnrealEditorSubsystem).get_editor_world()
        for binding in extensions.get_bindings(sequence):
            owners = list(extensions.locate_bound_objects(sequence, binding, world))
            if len(owners) != 1 or owners[0].get_path_name() != actor.get_path_name():
                continue
            for track in binding.get_tracks():
                if _class(track) == 'MovieSceneSkeletalAnimationTrack':
                    for section in track.get_sections():
                        params = section.get_editor_property('params')
                        observed.append(_path(params.get_editor_property('animation')))
    except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
        return {**result, 'reason': str(exc)}
    return {**result, 'status': 'PASS' if expected and Counter(expected) == Counter(observed) else 'FAIL'}
