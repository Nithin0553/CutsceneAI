"""Reopen-stage native persistence and tick-synchronized CineTwin evidence."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
for directory in (HERE, HERE.parents[1] / 'packages' / 'studio',
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


def start(workspace=None, *, job_id=None):
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

    def finish(target):
        import unreal

        prepared_transfer.verify(candidate)
        if (target['target']['editor_pid'] != os.getpid()
                or target['target']['sequence_asset_path'].split('.', 1)[0] != job['sequence_path']
                or persistence._loaded_level(unreal) != job['expected_level']):
            raise ValueError('Unreal observations do not belong to the reopened Studio scene.')
        comparison = compare(plan, source, target)
        evaluation = comparison['evaluation']
        joints = [row['joint_positions']['status'] for row in comparison['rig_motion_diagnostics']]
        if evaluation['status'] == 'DIFFERENCES_DETECTED' or native['native_structure_status'] == 'FAIL':
            status = 'DIFFERENCES_DETECTED'
        elif (not native['restart_verified'] or evaluation['unmapped_entity_count']
              or 'INCOMPLETE' in joints or target['quality']['status'] == 'SUSPECT'):
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
        })
        unreal.log('[CutSceneAI Studio] ' + status + ' — ' + str(output))

    import cinetwin_tick_evaluator

    request = cinetwin_tick_evaluator.start(
        str(sampling_path), job['mapping'], job['sequence_path'], str(observed_path),
        probe_times=None, on_complete=finish,
    )
    return {**request, 'evidence_folder': str(folder), 'native_persistence_status': native['status']}
