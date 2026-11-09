"""Guarded Stage 4 editor placement: source-derived actor poses + eligible attachments.

Does not generate a Level Sequence or save the level. Requires explicit operator
execution in the backed-up target Unreal project after a read-only Stage 4 plan.
"""
from __future__ import annotations
import json
import math
import ntpath
import sys
import traceback
from pathlib import Path
from typing import Any

TOOL_DIR = Path(__file__).resolve().parents[2] / 'tools'
CINETWIN_DIR = Path(__file__).resolve().parents[2] / 'packages' / 'cinetwin'
for folder in (TOOL_DIR, CINETWIN_DIR):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import studio_stage4_layout as planner

class PlacementError(ValueError):
    pass

def _project_key(value):
    return ntpath.normcase(ntpath.normpath(str(value).replace('/', '\\')))

def _one_actor(actors, label):
    found = [a for a in actors if str(a.get_actor_label()) == label]
    if len(found) != 1:
        raise PlacementError(f'Expected exactly one saved actor {label}, got {len(found)}')
    return found[0]

def _get_pose(actor):
    return actor.get_actor_transform()

def _safe_placeholder(actor):
    """Guard against replacing user-authored scene placements after Stage 3."""
    t = actor.get_actor_location()
    r = actor.get_actor_rotation()
    s = actor.get_actor_scale3d()
    values = [float(t.x),float(t.y),float(t.z),float(r.pitch),float(r.yaw),float(r.roll),float(s.x),float(s.y),float(s.z)]
    expected = [0,0,0,0,0,0,1,1,1]
    return all(math.isfinite(v) and abs(v-e) < 1e-3 for v,e in zip(values,expected))

def _unreal_project(api):
    raw = str(api.Paths.get_project_file_path())
    cv = getattr(api.Paths, 'convert_relative_path_to_full', None)
    return str(cv(raw)) if callable(cv) else raw

def run(plan_path: str, receipt_path: str, *, unreal_api: Any = None) -> dict:
    api = unreal_api
    if api is None:
        import unreal as api
    output = Path(receipt_path)
    if output.exists() or not output.parent.is_dir():
        raise PlacementError('Receipt already exists or output folder missing; use a new safe filename.')
    report = {
        'kind':'cutsceneai.studio.stage4_source_scene_layout_receipt',
        'schema_version':'0.1.0', 'stage':'preflight', 'status':'BLOCKED',
        'plan_path':str(Path(plan_path).resolve()),
        'placements_applied':[], 'attachments_applied':[],
        'scene_modified':False, 'level_saved':False,
        'sequence_generated':False, 'fidelity_verified':False,
    }
    snapshot = {}
    hierarchy_changes = []
    changes_possible = False
    try:
        plan = planner.verify(plan_path)
        if not plan['placements']:
            raise PlacementError('No source-derived placements; no level mutation allowed')
        live_project = _unreal_project(api)
        if _project_key(live_project) != _project_key(plan['target_project']):
            raise PlacementError(f'Wrong Unreal project: {live_project}')
        world = api.get_editor_subsystem(api.UnrealEditorSubsystem).get_editor_world()
        live_level = str(world.get_path_name()).split('.')[0]
        if live_level != plan['target_level']:
            raise PlacementError(f'Wrong level: {live_level}')
        report['verified_project'] = live_project
        report['verified_level'] = live_level
        subsystem = api.get_editor_subsystem(api.EditorActorSubsystem)
        all_actors = subsystem.get_all_level_actors()
        expected = planner.read(plan['stage3_plan_path'])['actors']
        actor_by_source = {}
        # Entire Stage 3 scene must still have exactly one instance of every actor.
        for row in expected:
            actor = _one_actor(all_actors, row['actor_label'])
            actor_by_source[row['source_name']] = actor
            if row['kind'] == 'character':
                component = actor.get_editor_property('skeletal_mesh_component')
                mesh = component.get_editor_property('skeletal_mesh_asset')
                if mesh is None or str(mesh.get_path_name()).split('.')[0] != row['mesh_path']:
                    raise PlacementError('Character mesh changed after Stage 3: ' + row['source_name'])
            # Stage 3 intentionally spawned actors at identity; protect user changes.
            if not _safe_placeholder(actor):
                raise PlacementError('Actor no longer at Stage 3 placeholder pose; stop instead of overwriting: ' + row['source_name'])
        for pose in plan['placements']:
            if pose['entity_name'] not in actor_by_source or actor_by_source[pose['entity_name']].get_actor_label() != pose['actor_label']:
                raise PlacementError('Unknown actor mapping in placement')
        attachments = plan['hierarchy'].get('attachments', [])
        hierarchy_runtime = None
        if attachments:
            import cinetwin_hierarchy_runtime as hierarchy_runtime
            # Preflight parent actors exist and foreign attachments are not replaced.
            for edge in attachments:
                child = _one_actor(all_actors, edge['actor_label'])
                parent = _one_actor(all_actors, edge['parent_actor_label'])
                old_parent = child.get_attach_parent_actor()
                if old_parent is not None and old_parent is not parent:
                    raise PlacementError('Existing unrelated attachment: ' + edge['actor_label'])
        # Capture all poses for rollback before the first change.
        snapshot = {name: (actor, _get_pose(actor)) for name, actor in actor_by_source.items()}
        report['stage'] = 'applying_source_layout'
        for pose in plan['placements']:
            actor = actor_by_source[pose['entity_name']]
            roll, pitch, yaw = pose['rotation_rpy_degrees']
            loc = pose['location_cm']
            changes_possible = True
            actor.set_actor_location(api.Vector(*loc), False, False)
            # Use production adapter semantic conversion to avoid Unreal Rotator argument-order confusion.
            import unreal_compat
            actor.set_actor_rotation(unreal_compat.make_rotator_semantic(
                roll=roll, pitch=pitch, yaw=yaw), False)
            scale = pose.get('scale_xyz')
            if scale is not None:
                actor.set_actor_scale3d(api.Vector(*scale))
            report['placements_applied'].append({'entity_name':pose['entity_name'],
                 'actor_label':pose['actor_label'],'source':pose['source']})
        if attachments:
            hierarchy_changes = hierarchy_runtime.apply_hierarchy(plan['hierarchy'])
            report['attachments_applied'] = [
                {'entity_name':e['entity_name'], 'parent_name':e['source_parent_name']}
                for e in attachments
            ]
        report['scene_modified'] = True
        report['status'] = 'STAGE4_SOURCE_LAYOUT_APPLIED_LEVEL_NOT_SAVED'
        report['stage'] = 'complete'
        report['missing_source_poses'] = plan['missing_source_poses']
        report['hierarchy_blocker'] = plan['hierarchy_blocker']
        return report
    except Exception as exc:
        report['error'] = {'type':type(exc).__name__, 'message':str(exc),
                           'traceback':traceback.format_exc()}
        if changes_possible:
            errors = []
            if hierarchy_changes:
                try:
                    hierarchy_runtime.rollback_hierarchy(hierarchy_changes)
                except Exception as rollback_error:
                    errors.append('hierarchy:' + str(rollback_error))
            for actor, prior in snapshot.values():
                try:
                    actor.set_actor_transform(prior, False, True)
                except Exception as rollback_error:
                    errors.append(str(rollback_error))
            report['status'] = ('FAILED_ROLLBACK_UNCERTAIN_MUST_INSPECT' if errors
                                else 'FAILED_RESTORED_IN_EDITOR_LEVEL_NOT_SAVED')
            report['rollback_errors'] = errors
            report['scene_modified'] = 'POSSIBLE_MUST_INSPECT'
        raise
    finally:
        planner.new_json(output, report)
        if unreal_api is None:
            if report['status'] == 'STAGE4_SOURCE_LAYOUT_APPLIED_LEVEL_NOT_SAVED':
                api.log('[CutSceneAI] STAGE 4: SOURCE LAYOUT APPLIED; SAVE ALL then audit after reopening.')
            else:
                api.log_warning('[CutSceneAI] STAGE 4: ' + report['status'] + '. Inspect receipt.')
