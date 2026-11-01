"""Explicit Unreal Editor opt-in worker for CutSceneAI Studio localhost bridge.

Load once with `studio_local_editor_worker.start()` inside a BACKED-UP Unreal
staging project. A file-queue (not arbitrary HTTP code execution) carries
immutable prepared transfers. All Unreal calls stay on the editor tick thread.
"""
from __future__ import annotations

import json
import hashlib
import hashlib
import os
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

import unreal

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / 'integrations/unreal') not in sys.path:
    sys.path.insert(0, str(ROOT / 'integrations/unreal'))

HANDLE = None
WORKSPACE = Path.home() / '.cutsceneai-studio' / 'runs'
LAST_TICK = 0.0
BUSY = False


def _load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _save(path, obj):
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(obj, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _loaded_project():
    return str(Path(unreal.Paths.get_project_file_path()).resolve())


def _loaded_level():
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    return str(world.get_path_name()).split('.')[0]


def _world_has_unsaved_changes():
    """Fail closed: UE new_level discards the currently open world without saving."""
    try:
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        package = world.get_outermost()
        return bool(package.is_dirty())
    except Exception as exc:
        raise RuntimeError('Cannot confirm current Unreal map is saved. Save it before automatic level creation.') from exc


def _ensure_target_level(job):
    """Create only the canonical fresh map after verifying the prepared job."""
    expected = str(job['expected_level'])
    if not job.get('create_level'):
        if _loaded_level() != expected:
            raise RuntimeError('Wrong Unreal level is loaded.')
        return
    if expected != '/Game/CutSceneAI/AutoTransfer/L_Studio_Fresh':
        raise RuntimeError('Refusing noncanonical automatic level path.')
    if unreal.EditorAssetLibrary.does_asset_exist(expected):
        raise RuntimeError('Target level already exists. Reconnect and use the existing map; no overwrite.')
    if _world_has_unsaved_changes():
        raise RuntimeError('Current Unreal map contains unsaved changes. Save it before automatic level creation.')
    # UE 5.8 supports LevelEditorSubsystem.new_level. It replaces the current
    # world without saving; the guard above prevents silent loss of edits.
    subsystem_type = getattr(unreal, 'LevelEditorSubsystem', None)
    editor_level = unreal.get_editor_subsystem(subsystem_type) if subsystem_type else None
    creator = getattr(editor_level, 'new_level', None)
    if not callable(creator):
        creator = getattr(getattr(unreal, 'EditorLevelLibrary', None), 'new_level', None)
    if not callable(creator):
        raise RuntimeError('Unreal level creation API unavailable; save an empty level manually and reconnect.')
    folder = '/Game/CutSceneAI/AutoTransfer'
    unreal.EditorAssetLibrary.make_directory(folder)
    succeeded = creator(expected)
    if succeeded is False or _loaded_level() != expected:
        raise RuntimeError('Unreal did not load the new level; setup halted before asset imports.')
    if not unreal.EditorAssetLibrary.does_asset_exist(expected):
        raise RuntimeError('The new map has not been saved to disk; setup halted.')
    unreal.log('[CutSceneAI Studio] Created new target map: ' + expected)


def _execute(job):
    """Only run a preprepared, verifiable, new-sequence job."""
    if job.get('kind') != 'cutsceneai.studio.local_unreal_job' or job.get('schema_version') != '0.1.0':
        raise RuntimeError('Unexpected editor job schema.')
    if os.path.normcase(_loaded_project()) != os.path.normcase(str(Path(job['expected_project']).resolve())):
        raise RuntimeError('Wrong Unreal staging project is loaded.')
    if not job.get('create_level') and _loaded_level() != job['expected_level']:
        raise RuntimeError('Wrong Unreal level is loaded.')
    candidate_dir = Path(job['candidate_dir']).resolve()
    if not candidate_dir.is_relative_to((WORKSPACE / 'candidates').resolve()):
        raise RuntimeError('Candidate is outside Studio working directory.')
    receipt = candidate_dir / ('unreal-runtime-receipt-' + job['job_id'] + '.json')
    if receipt.exists() or unreal.load_asset(job['sequence_path']) is not None:
        raise RuntimeError('Target already exists; refusing to overwrite or rerun.')
    # Avoid tools/transfer_readiness.py shadowing packages/cinetwin/transfer_readiness.py.
    for folder in (ROOT / 'integrations/unreal', ROOT / 'packages/studio', ROOT / 'packages/learning', ROOT / 'packages/cinetwin'):
        if str(folder) in sys.path:
            sys.path.remove(str(folder))
        sys.path.insert(0, str(folder))
    readiness = sys.modules.get('transfer_readiness')
    if readiness is not None and Path(getattr(readiness, '__file__', '')).resolve() != (ROOT / 'packages/cinetwin/transfer_readiness.py').resolve():
        raise RuntimeError('Unreal has stale transfer_readiness imported from tools/. Restart Unreal Editor, then start the Studio worker again.')
    import prepared_transfer
    prepared = prepared_transfer.verify(candidate_dir)
    if prepared['source']['csir_path'] != job['csir'] or prepared['target']['mapping_path'] != job['mapping']:
        raise RuntimeError('Prepared evidence does not match submitted job.')
    if prepared['target']['sequence_asset_path'] != job['sequence_path']:
        raise RuntimeError('Sequence identity mismatch.')
    _ensure_target_level(job)
    if job.get('automatic_setup'):
        # Source verification runs before ANY editor mutation. If an asset import
        # fails, the immutable receipt reports partial changes; do not retry.
        import studio_auto_scene
        setup_receipt = candidate_dir / ('automatic-setup-receipt-' + job['job_id'] + '.json')
        job['setup_status'] = 'IMPORTING_AND_CREATING_SCENE'
        _save(WORKSPACE / 'jobs' / (job['job_id'] + '.json'), job)
        try:
            staged = studio_auto_scene.run(
                job['automatic_setup_manifest'], str(setup_receipt),
                csir_path=job['csir'], mapping_path=job['mapping'],
                plan_path=str(candidate_dir / 'transfer-plan.json'),
                expected_project=job['expected_project'],
                expected_level=job['expected_level'])
        finally:
            if setup_receipt.is_file():
                job['setup_receipt_file'] = str(setup_receipt)
                job['setup_status'] = _load(setup_receipt).get('status')
                _save(WORKSPACE / 'jobs' / (job['job_id'] + '.json'), job)
        if staged['status'] != 'SETUP_SAVED_UNVERIFIED':
            raise RuntimeError('Automatic setup not saved; sequence generation blocked.')
    # Last-second check: an actor may have been removed after the UI approved
    # this job. Report a setup state, not a failed engine generation.
    _update_destination_readiness()
    latest = _load(WORKSPACE / 'destination-readiness.json')
    if latest.get('candidate_id') != job['candidate_id'] or not latest.get('ready'):
        job['status'] = ('SETUP_SAVED_BUT_NOT_READY' if job.get('setup_status') == 'SETUP_SAVED_UNVERIFIED'
                         else 'BLOCKED_SETUP')
        job['error'] = 'Destination setup not ready: ' + str(latest.get('next_action', 'Inspect target scene.'))
        job['generation_status'] = 'NOT_STARTED'
        return job
    import build_level_sequence
    result = build_level_sequence.build_prepared_files(
        job['csir'], job['mapping'], str(candidate_dir / 'transfer-plan.json'),
        str(candidate_dir / 'coverage-report.json'),
        str(candidate_dir / 'evidence.json'), str(receipt),
        expected_project_path=job['expected_project'],
        expected_level_path=job['expected_level'],
    )
    job['generation_status'] = 'GENERATED_UNVERIFIED'
    job['generated_sequence'] = result.get_path_name()
    if job.get('automatic_setup'):
        # The builder may change camera poses, root alignment and attachments
        # after the initial staging save. Persist those scene changes too.
        try:
            import studio_auto_scene
            studio_auto_scene._save_level(unreal, job['expected_level'])
        except Exception as save_error:
            job['status'] = 'GENERATED_LEVEL_NOT_SAVED_REVIEW_REQUIRED'
            job['error'] = 'Sequence exists, but the updated level could not be saved: ' + str(save_error)
            job['fidelity_verified'] = False
            return job
    job['receipt_file'] = str(receipt)
    _save(WORKSPACE / 'jobs' / (job['job_id'] + '.json'), job)
    # Diagnostic is read-only and independent of the builder's plan; it does
    # not prove image, camera lens, lighting, waveform or full joint parity.
    try:
        if not job.get('capture'):
            raise RuntimeError('Unity source CineTwin capture was not provided. Target generation can succeed, but behavioral parity cannot be measured yet.')
        import diagnose_cinetwin_parity
        before = set(candidate_dir.glob('CineTwin_WorldPose_Diagnosis_*.json'))
        report = diagnose_cinetwin_parity.run(
            csir_path=job['csir'], capture_path=job['capture'],
            mapping_path=job['mapping'], sequence_path=job['sequence_path'],
            output_dir=str(candidate_dir),
        )
        after = set(candidate_dir.glob('CineTwin_WorldPose_Diagnosis_*.json'))
        created = sorted(after - before)
        if not created or report.get('kind') != 'cutsceneai.cinetwin.unreal_world_pose_diagnostic':
            raise RuntimeError('Diagnostic returned without the expected report.')
        job['diagnostic_file'] = str(created[-1])
        job['status'] = 'GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED'
    except Exception as exc:
        job['status'] = 'GENERATED_DIAGNOSTIC_INCOMPLETE'
        job['error'] = 'CineTwin analysis unavailable: ' + str(exc)
    job['fidelity_verified'] = False
    return job



def _update_destination_readiness():
    """Inspect the loaded editor and candidate; never create an actor/asset."""
    active = WORKSPACE / 'active-candidate.json'
    report_file = WORKSPACE / 'destination-readiness.json'
    if not active.is_file():
        report_file.unlink(missing_ok=True)
        return
    info = _load(active)
    candidate_id = str(info['candidate_id'])
    candidate_dir = (WORKSPACE / 'candidates' / candidate_id).resolve()
    if not candidate_dir.is_relative_to((WORKSPACE / 'candidates').resolve()):
        raise RuntimeError('Unsafe candidate path in destination readiness.')
    plan_path = candidate_dir / 'transfer-plan.json'
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes.decode('utf-8-sig'))
    connection = _load(WORKSPACE / 'connection.json')
    # Use the same project's paths as job execution and never trust a stale
    # report for a different candidate or a different editor session.
    project = _loaded_project()
    level = _loaded_level()
    matches_project = os.path.normcase(os.path.abspath(project)) == os.path.normcase(os.path.abspath(connection['target_project']))
    matches_level = level == connection['level_path']
    lookup = []
    for actor in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        class_name = actor.get_class().get_name()
        if actor.get_component_by_class(unreal.SkeletalMeshComponent) is not None:
            kind = 'skeletal'
        elif actor.get_component_by_class(unreal.CineCameraComponent) is not None or class_name == 'CameraActor':
            kind = 'camera'
        elif class_name in ('PointLight', 'SpotLight', 'DirectionalLight'):
            kind = 'light'
        else:
            kind = 'actor'
        lookup.append({'label': str(actor.get_actor_label()), 'kind': kind})
    asset_paths = {
        str(a.get('unreal_asset_path')) for a in plan.get('actions', [])
        if a.get('kind') in ('skeletal_animation', 'audio')
        and a.get('unreal_asset_path')
    }
    registry = {}
    for asset in sorted(asset_paths):
        exists = bool(unreal.EditorAssetLibrary.does_asset_exist(asset))
        loaded = unreal.load_asset(asset) if exists else None
        registry[asset] = {'exists': exists, 'class_name': str(loaded.get_class().get_name()) if loaded else ('UNLOADABLE' if exists else '')}
    import studio_destination_preflight as dp
    output = dp.assess(
        plan, lookup, registry,
        sequence_exists=bool(unreal.EditorAssetLibrary.does_asset_exist(str(plan['sequence_asset_path']))),
        project_matches=matches_project, level_matches=matches_level,
    )
    output.update({
        'candidate_id': candidate_id,
        'sequence_path': str(plan['sequence_asset_path']),
        'plan_sha256': hashlib.sha256(plan_bytes).hexdigest(),
        'expected_project': str(connection['target_project']),
        'expected_level': str(connection['level_path']),
        'observed_project': project, 'observed_level': level,
        'checked_at': _now(),
    })
    _save(report_file, output)


def _report_inspection_failure(error):
    """Keep the UI informed when a live editor probe fails unexpectedly.

    This is a diagnostic, never evidence of readiness to modify Unreal.
    """
    active = WORKSPACE / 'active-candidate.json'
    connected = WORKSPACE / 'connection.json'
    if not active.is_file() or not connected.is_file():
        return
    info, config = _load(active), _load(connected)
    candidate_id = str(info['candidate_id'])
    root = (WORKSPACE / 'candidates').resolve()
    plan_file = (root / candidate_id / 'transfer-plan.json').resolve()
    if not plan_file.is_relative_to(root) or not plan_file.is_file():
        return
    _save(WORKSPACE / 'destination-readiness.json', {
        'kind': 'cutsceneai.studio.destination_readiness',
        'status': 'INSPECTION_FAILED', 'ready': False,
        'scene_modified': False,
        'next_action': 'Unreal scene inspection failed: ' + str(error) +
                       '. Review the Unreal Python log, then restart the Studio companion.',
        'candidate_id': candidate_id,
        'sequence_path': info['sequence_path'],
        'plan_sha256': hashlib.sha256(plan_file.read_bytes()).hexdigest(),
        'expected_project': str(config['target_project']),
        'expected_level': str(config['level_path']),
        'observed_project': _loaded_project(), 'observed_level': _loaded_level(),
        'checked_at': _now(),
    })


def _tick(_delta):
    global LAST_TICK, BUSY
    if BUSY or time.monotonic() - LAST_TICK < 1.0:
        return
    LAST_TICK = time.monotonic()
    try:
        WORKSPACE.mkdir(parents=True, exist_ok=True)
        _save(WORKSPACE / 'unreal-worker.json', {
            'heartbeat': _now(), 'project': _loaded_project(),
            'level': _loaded_level(), 'worker': 'studio-editor-v0.4'
        })
        try:
            _update_destination_readiness()
        except Exception as readiness_error:
            try:
                _report_inspection_failure(readiness_error)
            except Exception as report_error:
                unreal.log_error('[CutSceneAI Studio] Unable to record readiness failure: ' + str(report_error))
            unreal.log_warning('[CutSceneAI Studio] Destination inspection unavailable: ' + str(readiness_error))
        jobs_folder = WORKSPACE / 'jobs'
        if not jobs_folder.is_dir():
            return
        for path in sorted(jobs_folder.glob('*.json')):
            job = _load(path)
            if job.get('status') != 'QUEUED':
                continue
            BUSY = True
            try:
                job['status'] = 'RUNNING'
                _save(path, job)
                job = _execute(job)
            except Exception as exc:
                job['status'] = ('PARTIAL_SETUP_MUST_INSPECT'
                                 if job.get('setup_status') == 'PARTIAL_SETUP_MUST_INSPECT'
                                 else 'BLOCKED_OR_FAILED')
                job['error'] = str(exc)
                job['traceback'] = traceback.format_exc()
                job['fidelity_verified'] = False
                unreal.log_error('[CutSceneAI Studio] Job stopped: ' + str(exc))
            finally:
                _save(path, job)
                BUSY = False
            break
    except Exception as exc:
        unreal.log_error('[CutSceneAI Studio] Worker heartbeat/queue error: ' + str(exc))


def start(workspace=None):
    """Starts the worker; no jobs are processed until UI explicitly queues one."""
    global HANDLE, WORKSPACE
    if HANDLE is not None:
        return
    if workspace is not None:
        WORKSPACE = Path(workspace).expanduser().resolve()
    if not callable(getattr(unreal, 'register_slate_post_tick_callback', None)):
        raise RuntimeError('Unreal Editor does not support Python Slate tick callbacks.')
    # Explicit approval to modify a staging Unreal project remains the user's
    # responsibility. Never start this worker on the only project copy.
    HANDLE = unreal.register_slate_post_tick_callback(_tick)
    unreal.log_warning('[CutSceneAI Studio] Local worker listening for explicit prepared trial jobs.')


def stop():
    global HANDLE
    if HANDLE is None:
        return
    unreal.unregister_slate_post_tick_callback(HANDLE)
    HANDLE = None
