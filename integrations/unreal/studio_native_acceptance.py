"""Reopen-stage native persistence and tick-synchronized CineTwin evidence."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
for directory in (HERE, HERE.parents[1] / 'tools', HERE.parents[1] / 'packages' / 'studio',
                  HERE.parents[1] / 'packages' / 'cinetwin', HERE.parents[1] / 'packages' / 'learning'):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import prepared_transfer
import studio_persistence_audit as persistence
from behavior_compare import compare
from sampling_plan import plan_file, validate_capture


def _write(path, document):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(document, stream, indent=2, allow_nan=False)
        stream.write('\n')


def _character_metrics(report, identifier):
    actor, = [row for row in report['entities'] if row['entity_id'] == identifier]
    rig, = [row for row in report['rig_motion_diagnostics'] if row['entity_id'] == identifier]
    return {
        'actor_world_position_error_cm': actor['max_world_position_error_cm'],
        'actor_world_rotation_error_degrees': actor['max_world_rotation_error_degrees'],
        'root_world_position_error_cm': rig['skeletal_root_world'].get('max_world_position_error_cm'),
        'root_rotation_excursion': {key: rig['skeletal_root_world'].get(key) for key in (
            'source_world_rotation_excursion_degrees', 'target_world_rotation_excursion_degrees')},
        'joint_world_position_error_cm': rig['joint_positions'].get('maximum_error_cm'),
    }


def _character_facing_ownership_report(api, job, comparison, approved_axes,
                                       source_sha256, target_sha256):
    """Reopened-editor READ-ONLY native rotation owner inspection.

    The approval is required to identify the actual imported skeletal mesh.
    No report may authorize an actor rotation based on a UI or model guess.
    Failures here are recorded as incomplete diagnostics, not as permission
    to infer that an uninspectable owner is absent.
    """
    import studio_character_facing_ownership as ownership

    report = {
        'kind': 'cutsceneai.studio.native_character_facing_ownership',
        'schema_version': '1',
        'job_id': job['job_id'],
        'candidate_id': job['candidate_id'],
        'source_capture_sha256': source_sha256,
        'target_observation_sha256': target_sha256,
        'sequence_asset_path': job['sequence_path'],
        'reopened_editor_pid': os.getpid(),
        'status': 'READ_ONLY_NATIVE_OWNER_UNVERIFIED',
        'native_edit_authorized': False,
        'full_cutscene_fidelity_verified': False,
        'characters': [],
    }
    native_rigs = comparison.get('rig_motion_diagnostics') or []
    actors = comparison.get('entities') or []
    approval = approved_axes.get('characters') if isinstance(approved_axes, dict) else {}
    approval = approval if isinstance(approval, dict) else {}
    by_id = {row.get('entity_id'): row for row in actors if isinstance(row, dict)}
    try:
        subsystem = api.get_editor_subsystem(api.EditorActorSubsystem)
        scene_actors = list(subsystem.get_all_level_actors())
        sequence = api.load_asset(job['sequence_path'])
        if sequence is None:
            raise ValueError('The exact generated Unreal sequence is missing.')
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        scene_actors = []
        sequence = None
        global_failure = type(exc).__name__
    else:
        global_failure = ''
    for rig in native_rigs[:64]:
        ident = rig.get('entity_id') if isinstance(rig, dict) else None
        mapping = by_id.get(ident) if isinstance(ident, str) else None
        label = mapping.get('target_actor_label') if isinstance(mapping, dict) else None
        entry = approval.get(ident) if isinstance(ident, str) else None
        mesh = entry.get('target_mesh_asset_path') if isinstance(entry, dict) else None
        row = {
            'entity_id': ident,
            'status': 'BLOCKED_UNVERIFIED_OWNER',
            'native_edit_authorized': False,
            'blocking_reasons': [],
        }
        if not isinstance(label, str) or not label or not isinstance(mesh, str):
            row['blocking_reasons'] = ['SOURCE_BOUND_MESH_APPROVAL_OR_ACTOR_BINDING_MISSING']
        elif global_failure:
            row['blocking_reasons'] = ['NATIVE_EDITOR_OWNER_INSPECTION_FAILED_' + global_failure]
        else:
            try:
                matches = [actor for actor in scene_actors
                           if str(actor.get_actor_label()) == label]
                if len(matches) != 1:
                    row['blocking_reasons'] = ['AMBIGUOUS_NATIVE_CHARACTER_ACTOR']
                else:
                    row = {'entity_id': ident, **ownership.inspect(
                        api, sequence, matches[0],
                        expected_actor_label=label,
                        expected_mesh_asset_path=mesh,
                        all_level_actors=scene_actors,
                    )}
            except (AttributeError, TypeError, ValueError, RuntimeError):
                row['blocking_reasons'] = [
                    'READ_ONLY_NATIVE_CHARACTER_INSPECTION_FAILED'
                ]
        report['characters'].append(row)
    if len(native_rigs) > 64:
        report['status'] = 'NATIVE_CHARACTER_INVENTORY_EXCEEDS_BUDGET'
    elif report['characters']:
        report['status'] = 'READ_ONLY_NATIVE_OWNER_INSPECTED_NOT_AUTHORIZED'
    return report


def start(workspace=None, *, job_id=None, baseline_target=None,
          rig_calibration_path=None, mesh_forward_approval_path=None):
    """Run after opening the generated map in a different Unreal process."""
    root = Path(workspace).resolve() if workspace is not None else Path.home() / '.cutsceneai-studio' / 'runs'
    if job_id is None:
        job_id = persistence._json(root / 'active-job.json')['job_id']
    if not isinstance(job_id, str) or not re.fullmatch('[0-9a-f]{32}', job_id):
        raise ValueError('Expected a Studio job ID.')
    job_path = root / 'jobs' / (job_id + '.json')
    job = persistence._json(job_path)
    if job.get('kind') != 'cutsceneai.studio.local_unreal_job' or job.get('job_id') != job_id:
        raise ValueError('Studio job identity could not be verified.')
    generation_pid = job.get('generation_editor_pid')
    if type(generation_pid) is not int or generation_pid <= 0 or generation_pid == os.getpid():
        raise ValueError('Close the generating Unreal Editor, then open the saved level in a fresh Editor process.')
    candidate = Path(job['candidate_dir']).resolve()
    if candidate.parent != (root / 'candidates').resolve() or candidate.name != job['candidate_id']:
        raise ValueError('Studio job and prepared candidate identity do not agree.')
    session = prepared_transfer.verify(candidate)
    capture = session.get('source_capture')
    if not capture:
        raise ValueError('This candidate lacks a Unity CineTwin capture. Prepare the next run with one.')
    if (job.get('csir') != session['source']['csir_path']
            or job.get('capture') != capture['path']
            or job.get('mapping') != session['target']['mapping_path']
            or job.get('sequence_path') != session['target']['sequence_asset_path']):
        raise ValueError('Studio job does not use the prepared source, capture, mapping and sequence.')
    source = persistence._json(Path(capture['path']))
    calibration = None
    calibration_sha = None
    if rig_calibration_path is not None:
        calibration_file = Path(rig_calibration_path)
        if (calibration_file.is_symlink() or not calibration_file.is_file()
                or calibration_file.stat().st_size > 4 * 1024 * 1024):
            raise ValueError('Native rig calibration evidence is missing, linked or too large.')
        calibration = persistence._json(calibration_file)
        calibration_sha = persistence._sha(calibration_file)
    forward_approval = None
    forward_approval_sha = None
    if mesh_forward_approval_path is not None:
        forward_file = Path(mesh_forward_approval_path)
        if (forward_file.is_symlink() or not forward_file.is_file()
                or forward_file.stat().st_size > 4 * 1024 * 1024):
            raise ValueError('Mesh forward approval is missing, linked or too large.')
        forward_approval = persistence._json(forward_file)
        forward_approval_sha = persistence._sha(forward_file)
    folder = Path(tempfile.mkdtemp(prefix='native-acceptance-', dir=candidate))
    # Preserve optional rig/forward evidence BYTE FOR BYTE so Element 7 can
    # re-run the original calibrated comparator offline. A source filename
    # or arbitrary JSON digest alone would not prove the same input was used.
    for original, local_name in (
        (rig_calibration_path, 'rig-calibration.json'),
        (mesh_forward_approval_path, 'mesh-forward-approval.json'),
    ):
        if original is not None:
            source_file = Path(original)
            destination = folder / local_name
            with destination.open('xb') as stream:
                stream.write(source_file.read_bytes())
    sampling_path = folder / 'sampling-plan.json'
    plan = plan_file(job['csir'], sampling_path)
    validation = validate_capture(plan, source)
    if validation['failures']:
        raise ValueError('Unity CineTwin capture did not validate. ' + '; '.join(validation['failures'][:3]))
    native_path = folder / 'persistence.json'
    native = persistence.audit(job_path, native_path)
    observed_path = folder / 'target-behavior.json'
    baseline = persistence._json(Path(baseline_target)) if baseline_target is not None else None

    def finish(target):
        import unreal

        prepared_transfer.verify(candidate)
        if (target['target']['editor_pid'] != os.getpid()
                or target['target']['sequence_asset_path'].split('.', 1)[0] != job['sequence_path']
                or persistence._loaded_level(unreal) != job['expected_level']):
            raise ValueError('Unreal observations do not belong to the reopened Studio scene.')
        extra_evidence = {}
        if calibration is not None:
            extra_evidence['pose_calibration'] = calibration
        if forward_approval is not None:
            extra_evidence['mesh_forward_approval'] = forward_approval
        comparison = compare(plan, source, target, **extra_evidence)
        # Inspect the ACTUAL reopened actor and SkeletalMeshComponent owners.
        # The findings are independent diagnostic evidence only; the engine
        # has not authorized a character yaw edit or any cutscene fidelity.
        facing_path = folder / 'native-character-facing-ownership.json'
        facing = _character_facing_ownership_report(
            unreal, job, comparison, forward_approval,
            capture['sha256'], persistence._sha(observed_path),
        )
        _write(facing_path, facing)
        # Independently inspect ALL mapped native character bindings/parents
        # after real editor reopening. This is a structural check; it cannot
        # substitute for independent bone, attachment-motion or render parity.
        multi_character_path = None
        source_csir_path = Path(job['csir'])
        # A legacy acceptance callback can have no original entity census.
        # Such a run must never be labeled independently verified multi-
        # character coordination; only inspect when immutable source exists.
        if source_csir_path.is_file() and not source_csir_path.is_symlink():
            source_csir = persistence._json(source_csir_path)
            mapped_characters = [
                row for row in source_csir.get('entities', [])
                if isinstance(row, dict) and row.get('ced_type') == 'entity.character'
            ]
        else:
            source_csir = None
            mapped_characters = []
        if len(mapped_characters) >= 2:
            import studio_multi_character_native
            multi_character_path = folder / 'native-multi-character-coordination.json'
            try:
                report = studio_multi_character_native.inspect(
                    unreal,
                    unreal.load_asset(job['sequence_path']),
                    source_csir,
                    persistence._json(Path(job['mapping'])),
                    persistence._json(candidate / 'transfer-plan.json'),
                )
            except (ValueError, AttributeError, TypeError, RuntimeError) as exc:
                report = {
                    'kind': 'cutsceneai.studio.native_multi_character_coordination',
                    'status': 'NATIVE_CHARACTER_COORDINATION_INCOMPLETE',
                    'reason': type(exc).__name__,
                    'native_bone_pose_and_contact_verified': False,
                    'reopened_independent_editor_verified': False,
                    'rendered_interaction_fidelity_verified': False,
                }
            _write(multi_character_path, report)
        character_proof = None
        if job.get('character_native_readback_status') == 'PASS':
            import animation_conversion_policy as policy
            import studio_character_execution

            compatibility_file = candidate / policy.REPORT_FILE
            decision_file = candidate / 'ai-conversion-decision.json'
            if (persistence._sha(compatibility_file) != job['character_compatibility_sha256']
                    or persistence._sha(decision_file) != job['ai_conversion_decision_sha256']):
                raise ValueError('Reopened character evidence does not match the submitted job.')
            decision = persistence._json(decision_file)['animation_conversion']
            selected = policy.selected(persistence._json(compatibility_file), decision)
            native_character_report = studio_character_execution.record(
                unreal, job, persistence._json(candidate / 'transfer-plan.json'), selected,
                unreal.load_asset(job['sequence_path']), path=folder / 'character-reopened.json', reopened=True,
            )
            identifier = selected['source_entity_id']
            character_proof = {
                'action_id': decision['action_id'], 'source_entity_id': identifier,
                'evidence_ids': decision['evidence_ids'], 'tolerances': {
                    'position_cm': comparison['evaluation']['position_tolerance_cm'],
                    'rotation_degrees': comparison['evaluation']['orientation_tolerance_degrees']},
                'after': _character_metrics(comparison, identifier),
                'before': None, 'baseline_status': 'BASELINE_TARGET_OBSERVATIONS_NOT_PROVIDED',
                'reopened_character_readback_status': native_character_report['status'],
            }
            if baseline is not None:
                current = target['target']
                previous = baseline.get('target', {})
                if (previous.get('sequence_asset_path') == current['sequence_asset_path']
                        or previous.get('project_file_sha256') != current.get('project_file_sha256')
                        or not current.get('project_identity_sha256')
                        or previous.get('project_identity_sha256') != current['project_identity_sha256']
                        or previous.get('engine_version') != current['engine_version']):
                    raise ValueError('Baseline requires a distinct sequence with matching Unreal project and version.')
                character_proof['before'] = _character_metrics(compare(plan, source, baseline), identifier)
                character_proof['baseline_status'] = 'MATCHED_SOURCE_GRID_AND_UNREAL_PROJECT'
                character_proof['baseline_sha256'] = persistence._sha(Path(baseline_target))
        # Reopened native acceptance records source-bound intent/provenance,
        # not a fake per-element parity result. The Studio host (which has
        # JSON-schema/CED dependencies) recomputes per-occurrence CineTwin
        # attribution from these ACTUAL tick-synchronized native samples.
        element_permission = None
        element_source_count = None
        if (candidate / 'element-workflow-active.json').is_file():
            import studio_element_native_gate
            import studio_local_editor_worker as editor_worker
            element_permission, _ = studio_element_native_gate.verify_job(
                root, job, editor_worker._native_level_inventory(),
            )
            saved_pointer = persistence._json(
                candidate / 'element-workflow-active.json',
            )
            snapshot = persistence._json(
                candidate / ('element-workflow-' +
                             saved_pointer['workflow_sha256'] + '.json')
            )
            element_source_count = snapshot['element_plan']['source_occurrence_count']
        evaluation = comparison['evaluation']
        joints = [row['joint_positions']['status'] for row in comparison['rig_motion_diagnostics']]
        calibration_results = [
            row.get('joint_reference_orientation', {}).get('status', 'INCOMPLETE')
            for row in comparison['rig_motion_diagnostics']
        ]
        forward_results = [
            row.get('anatomical_mesh_forward', {}).get('status', 'INCOMPLETE')
            for row in comparison['rig_motion_diagnostics']
        ]
        character_status = character_proof['reopened_character_readback_status'] if character_proof else 'PASS'
        lens_status = comparison.get('camera_optics', {}).get('status')
        cuts_status = comparison.get('camera_cut_timing', {}).get('status')
        if (evaluation['status'] == 'DIFFERENCES_DETECTED' or native['native_structure_status'] == 'FAIL'
                or character_status == 'FAIL' or lens_status == 'FAIL' or cuts_status == 'FAIL'):
            status = 'DIFFERENCES_DETECTED'
        elif (not native['restart_verified'] or evaluation['unmapped_entity_count']
              or 'INCOMPLETE' in joints
              or (calibration is not None and (not calibration_results or 'INCOMPLETE' in calibration_results))
              or (forward_approval is not None and (not forward_results or 'INCOMPLETE' in forward_results))
              or target['quality']['status'] == 'SUSPECT' or character_status != 'PASS'
              or lens_status == 'INCOMPLETE' or cuts_status == 'INCOMPLETE'):
            status = 'INCOMPLETE_MEASURED_SCOPE'
        else:
            status = 'STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE'
        output = folder / 'comparison.json'
        _write(output, {
            **comparison, 'job_id': job_id, 'acceptance_status': status,
            'generation_editor_pid': generation_pid, 'observation_editor_pid': os.getpid(),
            'native_persistence_status': native['status'], 'source_capture_sha256': capture['sha256'],
            'target_observation_sha256': persistence._sha(observed_path),
            'persistence_sha256': persistence._sha(native_path),
            'sampling_plan_sha256': persistence._sha(sampling_path),
            'rig_calibration_sha256': calibration_sha,
            'rig_calibration_statuses': calibration_results,
            'mesh_forward_approval_sha256': forward_approval_sha,
            'mesh_forward_statuses': forward_results,
            'native_facing_ownership_sha256': persistence._sha(facing_path),
            'native_multi_character_coordination_sha256': (
                persistence._sha(multi_character_path)
                if multi_character_path is not None else None
            ),
            'native_multi_character_coordination_status': (
                'NOT_SOURCE_VERIFIED' if source_csir is None
                else 'NOT_APPLICABLE' if len(mapped_characters) < 2
                else persistence._json(multi_character_path)['status']
            ),
            'element3_workflow_sha256': (
                element_permission['workflow_sha256']
                if element_permission is not None else None
            ),
            'element3_native_authorization_sha256': (
                element_permission['authorization_sha256']
                if element_permission is not None else None
            ),
            'element3_source_occurrence_count': element_source_count,
            'full_cutscene_fidelity_verified': False,
            **({'character_conversion': character_proof} if character_proof else {}),
        })
        # Element 7 independently reconstructs EVERY compared native domain
        # from immutable source + actual reopened editor target bytes. It is
        # read-only and does not promote builder completion to cutscene fidelity.
        # Legacy synthetic fixture payloads (without a real sampling contract)
        # cannot masquerade as Element 7 native readback.
        if plan.get('kind') == 'cinetwin.sampling_plan':
            import studio_element7_readback
            evidence = studio_element7_readback.build(root, job_id, folder)
            _write(folder / 'element7-readback.json', evidence)
            unreal.log(
                '[CutSceneAI Studio] Element 7 ' + evidence['measured_scope_status']
                + ' — ' + str(folder / 'element7-readback.json')
            )
        unreal.log('[CutSceneAI Studio] ' + status + ' — ' + str(output))

    import cinetwin_tick_evaluator

    request = cinetwin_tick_evaluator.start(
        str(sampling_path), job['mapping'], job['sequence_path'], str(observed_path),
        probe_times=None, on_complete=finish,
    )
    return {**request, 'evidence_folder': str(folder), 'native_persistence_status': native['status']}
