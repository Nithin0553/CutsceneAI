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


def start(workspace=None, *, job_id=None, baseline_target=None):
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
    folder = Path(tempfile.mkdtemp(prefix='native-acceptance-', dir=candidate))
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
        comparison = compare(plan, source, target)
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
        evaluation = comparison['evaluation']
        joints = [row['joint_positions']['status'] for row in comparison['rig_motion_diagnostics']]
        character_status = character_proof['reopened_character_readback_status'] if character_proof else 'PASS'
        lens_status = comparison.get('camera_optics', {}).get('status')
        cuts_status = comparison.get('camera_cut_timing', {}).get('status')
        if (evaluation['status'] == 'DIFFERENCES_DETECTED' or native['native_structure_status'] == 'FAIL'
                or character_status == 'FAIL' or lens_status == 'FAIL' or cuts_status == 'FAIL'):
            status = 'DIFFERENCES_DETECTED'
        elif (not native['restart_verified'] or evaluation['unmapped_entity_count']
              or 'INCOMPLETE' in joints or target['quality']['status'] == 'SUSPECT' or character_status != 'PASS'
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
            **({'character_conversion': character_proof} if character_proof else {}),
        })
        unreal.log('[CutSceneAI Studio] ' + status + ' — ' + str(output))

    import cinetwin_tick_evaluator

    request = cinetwin_tick_evaluator.start(
        str(sampling_path), job['mapping'], job['sequence_path'], str(observed_path),
        probe_times=None, on_complete=finish,
    )
    return {**request, 'evidence_folder': str(folder), 'native_persistence_status': native['status']}
