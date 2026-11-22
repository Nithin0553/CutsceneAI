"""Explicit Unreal Editor opt-in worker for CutSceneAI Studio localhost bridge.

Load once with `studio_local_editor_worker.start()` inside a BACKED-UP Unreal
staging project. A file-queue (not arbitrary HTTP code execution) carries
immutable prepared transfers. All Unreal calls stay on the editor tick thread.
"""
from __future__ import annotations

import json
import hashlib
import importlib
import os
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

import unreal

ROOT = Path(__file__).resolve().parents[2]
# Fixed at module IMPORT, not recomputed from disk on every heartbeat.
# A Python interpreter retaining an older worker across a git pull cannot
# falsely claim that its runtime code matches the new Studio host.
WORKER_PROTOCOL = 'studio-editor-v0.6'
WORKER_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
if str(ROOT / 'integrations/unreal') not in sys.path:
    sys.path.insert(0, str(ROOT / 'integrations/unreal'))

HANDLE = None
WORKSPACE = Path.home() / '.cutsceneai-studio' / 'runs'
LAST_TICK = 0.0
BUSY = False
# Only module-level Python updates are refreshed automatically. Never reset a
# native editor or an already-running/partially completed transfer.
LIVE_RELOAD_STATE = 'CURRENT'
LIVE_RELOAD_ERROR = ''
# Reloading the worker alone is insufficient after a git pull changes adapters.
# Capture a bounded fingerprint of code in the trusted repo at worker startup.
def _dependency_fingerprint():
    result = hashlib.sha256()
    checked = 0
    for relative in ('integrations/unreal', 'packages/studio', 'packages/cinetwin', 'tools'):
        folder = ROOT / relative
        for path in sorted(folder.glob('*.py')):
            if path.is_symlink():
                raise RuntimeError('A Studio Python dependency is a symlink: ' + relative)
            checked += 1
            if checked > 500 or path.stat().st_size > 4 * 1024 * 1024:
                raise RuntimeError('Studio Python dependency inventory is out of bounds.')
            result.update(str(path.relative_to(ROOT)).encode('utf-8'))
            result.update(hashlib.sha256(path.read_bytes()).digest())
    return result.hexdigest()


def _native_attempt_guard():
    """Canonical stdlib-only one-attempt barrier; never load from candidate paths."""
    package = str(ROOT / 'packages/studio')
    if package not in sys.path:
        sys.path.insert(0, package)
    import studio_element6_execution as guard
    expected = (ROOT / 'packages/studio/studio_element6_execution.py').resolve()
    if Path(getattr(guard, '__file__', '')).resolve() != expected:
        raise RuntimeError('Guarded native execution module is from another checkout.')
    return guard


DEPENDENCY_SOURCE_SHA256 = _dependency_fingerprint()
LAST_DEPENDENCY_CHECK = 0.0


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


def _native_level_inventory():
    """Read-only, bounded actor-class census of the loaded Unreal level."""
    try:
        actors = unreal.get_editor_subsystem(
            unreal.EditorActorSubsystem).get_all_level_actors()
        counts = {}
        for index, actor in enumerate(actors):
            if index >= 5000:
                break
            try:
                label = str(actor.get_class().get_name())[:72]
            except Exception:
                label = 'Unknown'
            counts[label] = counts.get(label, 0) + 1
        return {
            'available': True,
            'character_compatibility_probe': True,
            'actor_count': len(actors),
            'class_counts': dict(sorted(counts.items())[:32]),
            'native_capabilities': {
                'fbx_asset_import': bool(
                    getattr(unreal, 'AssetImportTask', None)
                    and getattr(unreal, 'FbxImportUI', None)),
                'sequencer_visibility_track': bool(
                    getattr(unreal, 'MovieSceneVisibilityTrack', None)),
                'sequencer_skeletal_animation_track': bool(
                    getattr(unreal, 'MovieSceneSkeletalAnimationTrack', None)),
                'cine_camera_actor': bool(
                    getattr(unreal, 'CineCameraActor', None)),
            },
            'truncated': len(actors) > 5000 or len(counts) > 32,
        }
    except Exception as exc:
        return {
            'available': False, 'reason': type(exc).__name__,
            'actor_count': 0, 'class_counts': {},
        }


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
    job['execution_stage'] = 'VALIDATING_UNREAL_PROJECT_AND_CANDIDATE'
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
    # The Unreal Editor Python VM survives git pulls. Refresh the *entire*
    # native planning dependency chain before verifying an immutable candidate,
    # so a previously imported 25-action backend cannot falsely compare
    # against a newly prepared 29-action adaptive CED plan.
    job['execution_stage'] = 'VERIFYING_PREPARED_TRANSFER'
    import studio_planner_sync
    expected_sync = (ROOT / 'integrations/unreal/studio_planner_sync.py').resolve()
    if Path(getattr(studio_planner_sync, '__file__', '')).resolve() != expected_sync:
        raise RuntimeError('Unreal planner sync is loaded from a different checkout. Restart Unreal Editor.')
    # The sync module itself may have been imported prior to a git pull.
    importlib.reload(studio_planner_sync)
    studio_planner_sync.synchronize()
    import prepared_transfer
    prepared = prepared_transfer.verify(candidate_dir)
    if prepared['source']['csir_path'] != job['csir'] or prepared['target']['mapping_path'] != job['mapping']:
        raise RuntimeError('Prepared evidence does not match submitted job.')
    if prepared['target']['sequence_asset_path'] != job['sequence_path']:
        raise RuntimeError('Sequence identity mismatch.')
    # Explicit Element 3 review requires a separate exact action-grant
    # checked again inside the live Unreal process BEFORE asset import,
    # level creation, actor mutation or Level Sequence construction.
    element_dispatch = None
    element_review_requested = (candidate_dir / 'element-workflow-active.json').is_file()
    if element_review_requested or job.get('element_native_authorization_sha256'):
        if not element_review_requested:
            raise RuntimeError('Native element authorization has no active source review.')
        import studio_element_native_gate
        element_dispatch = studio_element_native_gate.verify_job(
            WORKSPACE, job, _native_level_inventory(),
        )
        job['element_native_dispatch_status'] = 'EXACT_ACTIONS_AUTHORIZED_PREFLIGHT_PENDING'
    # A host AI conversion choice is a measured, source-bound option record,
    # not authority to write arbitrary Unreal commands. Match its bytes to
    # the job's approved hash BEFORE any native editor mutation.
    ai_decision = candidate_dir / 'ai-conversion-decision.json'
    ai_sha = job.get('ai_conversion_decision_sha256') or ''
    decision = {}
    if ai_sha or ai_decision.exists():
        if not (isinstance(ai_sha, str) and len(ai_sha) == 64
                and ai_decision.is_file() and not ai_decision.is_symlink()
                and hashlib.sha256(ai_decision.read_bytes()).hexdigest() == ai_sha
                and job.get('ai_agents_enabled') is True):
            raise RuntimeError('AI conversion provenance is missing or stale; do not import assets.')
        decision = _load(ai_decision)
        mapped = _load(Path(job['mapping']))
        options = decision.get('conversion_options') or {}
        if decision.get('kind') != 'cutsceneai.studio.ai_conversion_decision':
            raise RuntimeError('Unexpected AI conversion decision format.')
        for option in ('enable_fbx_embedded_material_import',
                       'enable_actor_visibility_fallback'):
            if (type(options.get(option)) is not bool
                    or bool(mapped.get(option)) != options[option]):
                raise RuntimeError('Unreal mapping no longer matches AI-approved option: ' + option)
    # Import the engine generator BEFORE creating a level, importing any FBX,
    # or spawning any actor. A missing/circular module must not leave behind
    # a saved but unusable automatic setup.
    import build_level_sequence
    import studio_collider_shapes
    import unreal_compat
    checked_plan = _load(candidate_dir / 'transfer-plan.json')
    character = None
    animation_choice = decision.get('animation_conversion')
    if bool(animation_choice) != ('ai_character_animation' in checked_plan) or (animation_choice and not job.get('automatic_setup')):
        raise RuntimeError('AI character animation requires its verified decision and automatic staging.')
    unreal_compat.validate_component_versions(checked_plan['actions'])
    collider_actions = studio_collider_shapes.from_plan(checked_plan)
    if collider_actions and not job.get('automatic_setup'):
        raise RuntimeError('Native collider geometry requires the guarded automatic scene setup.')
    studio_collider_shapes.preflight(unreal, collider_actions)
    # A durable exclusive claim was recorded by the queue before _execute.
    # Recheck the exact original job + source/target/action fingerprints here.
    # A changed claim, mapping or approval must not reach editor mutation.
    element6_guard = _native_attempt_guard()
    element6_claim = element6_guard.load_claim(
        WORKSPACE, job, editor_pid=os.getpid(),
    )
    element6_guard.step(
        WORKSPACE, job, element6_claim, 'PREPARED_SOURCE_AND_ACTIONS_VERIFIED',
    )
    if job.get('automatic_setup'):
        # Essential source-content and adapter verification MUST precede
        # _ensure_target_level, which can create an empty Unreal map.
        # This path runs before any editor mutation and provides a precise
        # error when the previously prepared manifest no longer matches.
        job['execution_stage'] = 'VERIFYING_SOURCE_ASSET_MANIFEST'
        import studio_auto_assets
        inspected = studio_auto_assets.verify(
            job['automatic_setup_manifest'], job['csir'], job['mapping'],
            str(candidate_dir / 'transfer-plan.json')
        )
        if not inspected.get('ready'):
            raise RuntimeError('Prepared source setup is not ready: ' +
                               '; '.join(inspected.get('blockers', [])[:8]))
        if animation_choice:
            import studio_character_execution
            character = studio_character_execution.preflight(
                unreal, job, decision, mapped, checked_plan, inspected,
                worker={'connected': True, 'project': _loaded_project(), 'level': _loaded_level(),
                        'editor_pid': os.getpid(),
                        'worker_version': WORKER_PROTOCOL, 'scene_inventory': _native_level_inventory()},
            )
    element6_guard.step(
        WORKSPACE, job, element6_claim, 'EDITOR_PREFLIGHT_COMPLETE',
    )
    element6_guard.step(
        WORKSPACE, job, element6_claim, 'DESTINATION_MUTATION_STARTED',
    )
    if character is not None:
        studio_character_execution.begin(job, checked_plan)
    job['execution_stage'] = 'PREPARING_DESTINATION_LEVEL'
    _ensure_target_level(job)
    if job.get('automatic_setup'):
        # Source verification runs before ANY editor mutation. If an asset import
        # fails, the immutable receipt reports partial changes; do not retry.
        import studio_auto_scene
        setup_receipt = candidate_dir / ('automatic-setup-receipt-' + job['job_id'] + '.json')
        job['setup_status'] = 'IMPORTING_AND_CREATING_SCENE'
        job['execution_stage'] = 'IMPORTING_ASSETS_AND_CREATING_ACTORS'
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
        if staged.get('status') == 'SETUP_SAVED_UNVERIFIED':
            job['assets_imported_count'] = len(staged.get('assets_imported') or [])
            job['actors_created_count'] = len(staged.get('actors_created') or [])
        if staged['status'] != 'SETUP_SAVED_UNVERIFIED':
            raise RuntimeError('Automatic setup not saved; sequence generation blocked.')
        if character is not None:
            job['execution_stage'] = 'VERIFYING_STAGED_CHARACTER_MOTION'
            studio_character_execution.validate_staged(unreal, job, checked_plan)
    element6_guard.step(
        WORKSPACE, job, element6_claim,
        'DESTINATION_SETUP_COMPLETE_OR_NOT_REQUIRED',
    )
    # Last-second check: an actor may have been removed after the UI approved
    # this job. Report a setup state, not a failed engine generation.
    job['execution_stage'] = 'CHECKING_DESTINATION_READINESS'
    _update_destination_readiness()
    latest = _load(WORKSPACE / 'destination-readiness.json')
    if latest.get('candidate_id') != job['candidate_id'] or not latest.get('ready'):
        job['status'] = ('SETUP_SAVED_BUT_NOT_READY' if job.get('setup_status') == 'SETUP_SAVED_UNVERIFIED'
                         else 'BLOCKED_SETUP')
        job['error'] = 'Destination setup not ready: ' + str(latest.get('next_action', 'Inspect target scene.'))
        job['generation_status'] = 'NOT_STARTED'
        return job
    job['execution_stage'] = 'GENERATING_EDITABLE_LEVEL_SEQUENCE'
    element6_guard.step(
        WORKSPACE, job, element6_claim, 'NATIVE_SEQUENCE_BUILDER_STARTED',
    )
    result = build_level_sequence.build_prepared_files(
        job['csir'], job['mapping'], str(candidate_dir / 'transfer-plan.json'),
        str(candidate_dir / 'coverage-report.json'),
        str(candidate_dir / 'evidence.json'), str(receipt),
        expected_project_path=job['expected_project'],
        expected_level_path=job['expected_level'],
    )
    element6_guard.step(
        WORKSPACE, job, element6_claim, 'NATIVE_SEQUENCE_BUILDER_RETURNED',
    )
    job['generation_status'] = 'GENERATED_UNVERIFIED'
    if element_dispatch is not None:
        # The canonical builder has already recompiled and dispatched the
        # exact native actions. Record that fact from its *real* runtime
        # receipt; individual action readback and fidelity remain pending.
        try:
            import studio_element_native_gate
            dispatch = studio_element_native_gate.record_job(
                WORKSPACE, job, _native_level_inventory(),
            )
            job['element_native_dispatch_receipt'] = str(
                candidate_dir / ('element-native-dispatch-' + job['job_id'] + '.json')
            )
            job['element_native_dispatch_status'] = (
                'REGISTERED_BUILDER_COMPLETED_INDIVIDUAL_READBACK_UNVERIFIED'
            )
            job['element_native_dispatched_action_count'] = dispatch['action_count']
        except Exception as exc:
            job['element_native_dispatch_status'] = (
                'DISPATCH_RECEIPT_UNAVAILABLE_REVIEW_REQUIRED'
            )
            job['element_native_dispatch_error'] = str(exc)[:350]
            unreal.log_warning(
                '[CutSceneAI Studio] Native element dispatch receipt incomplete: '
                + str(exc)
            )
    try:
        job['bindings_created_count'] = len(result.get_bindings())
    except Exception:
        job['bindings_created_count'] = None
    job['generated_sequence'] = result.get_path_name()
    if character is not None:
        proof = studio_character_execution.record(unreal, job, checked_plan, character, result)
        job['character_native_readback_status'] = proof['status']
        if proof['status'] != 'PASS':
            job['status'] = 'GENERATED_ANIMATION_VERIFICATION_FAILED_REVIEW_REQUIRED'
            job['generation_status'] = 'NATIVE_ANIMATION_READBACK_FAILED'
            job['error'] = 'Character asset or Sequencer timing readback did not pass. Preserve and inspect this candidate.'
            return job
    if job.get('automatic_setup'):
        # The builder may change camera poses, root alignment and attachments
        # after the initial staging save. Persist those scene changes too.
        job['execution_stage'] = 'SAVING_GENERATED_DESTINATION_LEVEL'
        try:
            import studio_auto_scene
            studio_auto_scene._save_level(unreal, job['expected_level'])
        except Exception as save_error:
            job['status'] = 'GENERATED_LEVEL_NOT_SAVED_REVIEW_REQUIRED'
            job['error'] = 'Sequence exists, but the updated level could not be saved: ' + str(save_error)
            job['fidelity_verified'] = False
            return job
    # Record the real editor OS process that generated this saved sequence.
    # Independent persistence needs the target reopened in another process;
    # a Python module reload in this same editor cannot spoof that evidence.
    job['execution_stage'] = 'POST_GENERATION_AUDITS'
    element6_guard.step(
        WORKSPACE, job, element6_claim,
        'POST_GENERATION_DIAGNOSTICS_STARTED',
    )
    job['generation_editor_pid'] = os.getpid()
    job['receipt_file'] = str(receipt)
    _save(WORKSPACE / 'jobs' / (job['job_id'] + '.json'), job)
    cine_report = None
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
        cine_report = report
        job['status'] = 'GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED'
    except Exception as exc:
        job['status'] = 'GENERATED_DIAGNOSTIC_INCOMPLETE'
        job['error'] = 'CineTwin analysis unavailable: ' + str(exc)
    # Read-only native visual audit and CineTwin feedback, without inventing a
    # rendered-frame PASS or modifying the generated sequence again.
    visual_report = None
    try:
        import studio_visual_audit
        visual_report = studio_visual_audit.audit_latest(WORKSPACE, api=unreal)
        job['visual_audit_status'] = visual_report['status']
    except Exception as exc:
        job['visual_audit_error'] = str(exc)
        unreal.log_warning('[CutSceneAI Studio] Automatic visual audit incomplete: ' + str(exc))
    # Attempt only a proven material-slot correction on newly staged actors.
    # Re-audit after each change and stop on no progress, a source mismatch,
    # or the hard two-round cap. Other domains are not safely auto-repairable.
    repairs = []
    if visual_report is not None and job.get('automatic_setup'):
        previous_fallback = int(visual_report.get('material_slots_engine_default', 0))
        for _ in range(2):
            if previous_fallback <= 0:
                break
            try:
                import studio_visual_repair
                repair = studio_visual_repair.attempt(job, staged, unreal)
                if repair.get('changed', 0) <= 0:
                    break
                import studio_auto_scene
                studio_auto_scene._save_level(unreal, job['expected_level'])
                repairs.append({'changed': repair['changed'], 'strategy': repair['status']})
                import studio_visual_audit
                refreshed = studio_visual_audit.audit_latest(WORKSPACE, api=unreal)
                visual_report = refreshed
                current_fallback = int(refreshed.get('material_slots_engine_default', 0))
                if current_fallback >= previous_fallback:
                    break
                previous_fallback = current_fallback
            except Exception as exc:
                job['repair_status'] = 'PARTIAL_REPAIR_MUST_INSPECT'
                job['repair_error'] = str(exc)
                unreal.log_warning('[CutSceneAI Studio] Source-backed visual repair stopped: ' + str(exc))
                break
    job['repair_iterations'] = len(repairs)
    job['repair_changes'] = sum(row['changed'] for row in repairs)
    if visual_report is not None:
        job['visual_audit_status'] = visual_report['status']
    try:
        import closed_loop_evaluation
        assessment = closed_loop_evaluation.evaluate(
            cine_report, visual_report, repair_iterations=len(repairs),
            coverage=_load(candidate_dir / 'coverage-report.json'),
        )
        assessment_path = candidate_dir / ('closed-loop-evaluation-' + job['job_id'] + '.json')
        closed_loop_evaluation.write_new(assessment_path, assessment)
        job['closed_loop_report_file'] = str(assessment_path)
        job['closed_loop_status'] = assessment['status']
    except Exception as exc:
        job['closed_loop_error'] = str(exc)
        unreal.log_warning('[CutSceneAI Studio] Post-transfer assessment incomplete: ' + str(exc))
    job['fidelity_verified'] = False
    # Read back saved native assets, bindings and hierarchy now, in the
    # generating editor. Only a separately launched editor may later prove
    # persistence across process restart.
    try:
        _save(WORKSPACE / 'jobs' / (job['job_id'] + '.json'), job)
        import studio_generation_readback
        proof = studio_generation_readback.capture(WORKSPACE, job, unreal_api=unreal)
        job['generation_readback_status'] = proof.get('native_structure', 'INCOMPLETE')
        job['generation_hierarchy_status'] = proof.get('source_hierarchy', 'INCOMPLETE')
        errors = [x for x in (proof.get('native_structure_error'),
                              proof.get('source_hierarchy_error')) if x]
        if errors:
            job['generation_readback_errors'] = errors
            unreal.log_warning('[CutSceneAI Studio] Native readback incomplete: ' +
                               '; '.join(errors))
    except Exception as exc:
        job['generation_readback_status'] = 'INCOMPLETE'
        job['generation_readback_error'] = str(exc)
        unreal.log_warning('[CutSceneAI Studio] Generation readback unavailable: ' +
                           str(exc))
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


def _running_native_job_exists():
    """Never refresh executable native code during an executing/orphaned job."""
    jobs = WORKSPACE / 'jobs'
    if not jobs.is_dir():
        return False
    paths = list(jobs.glob('*.json'))
    # Unbounded or unreadable native history must not grant reload authority.
    if len(paths) > 10000:
        return True
    for path in paths:
        if path.is_symlink():
            return True
        try:
            if _load(path).get('status') == 'RUNNING':
                return True
        except (OSError, ValueError, TypeError):
            return True
    return False


def _refresh_dependency_modules():
    """Refresh known source/target pipeline modules, never the native editor.

    The existing planner synchronization already checks canonical module paths,
    and protects against stale/shadowed versions before native mutation. The
    supplementary observer and generator imports are similarly origin-pinned.
    """
    import studio_planner_sync
    expected_sync = (ROOT / 'integrations/unreal/studio_planner_sync.py').resolve()
    if Path(getattr(studio_planner_sync, '__file__', '')).resolve() != expected_sync:
        raise RuntimeError('Reloaded Studio planner belongs to another checkout.')
    importlib.reload(studio_planner_sync)
    studio_planner_sync.synchronize()
    extras = (
        ('unreal_compat', 'integrations/unreal'),
        ('studio_agent_executor', 'integrations/unreal'),
        ('studio_auto_scene', 'integrations/unreal'),
        ('build_level_sequence', 'integrations/unreal'),
        ('cinetwin_target_evaluator', 'integrations/unreal'),
        ('cinetwin_tick_evaluator', 'integrations/unreal'),
        ('cinetwin_camera_cuts', 'integrations/unreal'),
        ('behavior_compare', 'packages/cinetwin'),
        ('camera_optics', 'packages/cinetwin'),
        ('camera_cut_timing', 'packages/cinetwin'),
        ('joint_motion_profile', 'packages/cinetwin'),
    )
    for name, relative in extras:
        module = sys.modules.get(name)
        if module is None:
            continue
        expected = (ROOT / relative / (name + '.py')).resolve()
        if Path(getattr(module, '__file__', '')).resolve() != expected:
            raise RuntimeError('A loaded Studio adapter comes from another checkout: ' + name)
        importlib.reload(module)


def _refresh_worker_python():
    """Refresh changed repo Python inside the same editor, only when idle.

    The existing Slate callback is a stable dispatcher into the live module.
    Updating the source therefore does not require unregistering/re-registering
    a callback on an active Unreal tick or restarting the Unreal Editor.
    """
    global LIVE_RELOAD_STATE, LIVE_RELOAD_ERROR
    global DEPENDENCY_SOURCE_SHA256, LAST_DEPENDENCY_CHECK
    path = Path(__file__).resolve()
    if Path(__file__).is_symlink():
        LIVE_RELOAD_STATE, LIVE_RELOAD_ERROR = 'BLOCKED', 'Worker source is a symlink.'
        return True
    try:
        source = path.read_bytes()
        current_sha = hashlib.sha256(source).hexdigest()
        if current_sha == WORKER_SOURCE_SHA256:
            if time.monotonic() - LAST_DEPENDENCY_CHECK < 3.0:
                return False
            LAST_DEPENDENCY_CHECK = time.monotonic()
            current_deps = _dependency_fingerprint()
            if current_deps == DEPENDENCY_SOURCE_SHA256:
                LIVE_RELOAD_STATE, LIVE_RELOAD_ERROR = 'CURRENT', ''
                return False
            if BUSY or _running_native_job_exists():
                LIVE_RELOAD_STATE, LIVE_RELOAD_ERROR = (
                    'DEFERRED_NATIVE_JOB', 'Adapter source changed while a native job is running.'
                )
                return True
            _refresh_dependency_modules()
            if _dependency_fingerprint() != current_deps:
                LIVE_RELOAD_STATE, LIVE_RELOAD_ERROR = 'BLOCKED', (
                    'Adapter source changed during the code refresh.'
                )
                return True
            DEPENDENCY_SOURCE_SHA256 = current_deps
            LIVE_RELOAD_STATE, LIVE_RELOAD_ERROR = 'AUTO_RELOADED', ''
            unreal.log('[CutSceneAI Studio] Updated Studio Python adapters in the open Unreal Editor.')
            return True
        if BUSY or _running_native_job_exists():
            LIVE_RELOAD_STATE, LIVE_RELOAD_ERROR = (
                'DEFERRED_NATIVE_JOB', 'Code changed during native execution; preserve the job for inspection.'
            )
            return True
        module = sys.modules.get(__name__)
        if module is None or Path(getattr(module, '__file__', '')).resolve() != path:
            LIVE_RELOAD_STATE, LIVE_RELOAD_ERROR = 'BLOCKED', 'Worker module origin cannot be verified.'
            return True
        # Compile the exact bytes read. A bad git pull never executes a queued
        # candidate or partially updates the module's callable state.
        compiled = compile(source, str(path), 'exec')
        if hashlib.sha256(path.read_bytes()).hexdigest() != current_sha:
            LIVE_RELOAD_STATE, LIVE_RELOAD_ERROR = 'BLOCKED', 'Worker changed while being inspected.'
            return True
        previous_handle, previous_workspace = HANDLE, WORKSPACE
        exec(compiled, module.__dict__)
        module.HANDLE = previous_handle
        module.WORKSPACE = previous_workspace
        module.LAST_TICK = time.monotonic()
        module.LIVE_RELOAD_STATE = 'AUTO_RELOADED'
        module.LIVE_RELOAD_ERROR = ''
        # The compiled source recalculates the adapter fingerprint and receives
        # the latest managed module functions on the next idle heartbeat.
        module.LAST_DEPENDENCY_CHECK = 0.0
        unreal.log('[CutSceneAI Studio] Updated Python companion in the running Unreal Editor; no restart.')
        return True
    except Exception as exc:
        # Any syntax/import failure leaves the editor open but blocks native
        # submission. Never execute a queued candidate through partial code.
        LIVE_RELOAD_STATE, LIVE_RELOAD_ERROR = 'BLOCKED', (
            'Python worker update is invalid: ' + str(exc)
        )[:500]
        unreal.log_error('[CutSceneAI Studio] Worker auto-refresh blocked: ' + LIVE_RELOAD_ERROR)
        return True


def _tick_dispatch(delta):
    """Stable callback uses the current module handler after a code refresh."""
    current = sys.modules.get(__name__)
    handler = getattr(current, '_tick', _tick) if current is not None else _tick
    return handler(delta)


def _tick(_delta):
    global LAST_TICK, BUSY
    if BUSY or time.monotonic() - LAST_TICK < 1.0:
        return
    LAST_TICK = time.monotonic()
    try:
        WORKSPACE.mkdir(parents=True, exist_ok=True)
        if _refresh_worker_python():
            # Always report the *currently executed* source SHA; the host will
            # refuse stale/invalid worker code and not queue a second native job.
            _save(WORKSPACE / 'unreal-worker.json', {
                'heartbeat': _now(), 'project': _loaded_project(),
                'level': _loaded_level(), 'worker': WORKER_PROTOCOL,
                'editor_pid': os.getpid(), 'checkout_root': str(ROOT.resolve()),
                'worker_source_sha256': WORKER_SOURCE_SHA256,
                'live_reload_state': LIVE_RELOAD_STATE,
                'live_reload_error': LIVE_RELOAD_ERROR,
            })
            return
        _save(WORKSPACE / 'unreal-worker.json', {
            'heartbeat': _now(), 'project': _loaded_project(),
            'level': _loaded_level(), 'worker': WORKER_PROTOCOL,
            'editor_pid': os.getpid(),
            'checkout_root': str(ROOT.resolve()),
            'worker_source_sha256': WORKER_SOURCE_SHA256,
            'live_reload_state': LIVE_RELOAD_STATE,
            'live_reload_error': LIVE_RELOAD_ERROR,
            'scene_inventory': _native_level_inventory(),
        })
        if (WORKSPACE / 'character-probe-request.json').is_file():
            try:
                import studio_character_probe
                studio_character_probe.service(WORKSPACE, unreal, project=_loaded_project(), level=_loaded_level(), save=_save)
            except (ValueError, RuntimeError, OSError) as probe_error:
                unreal.log_warning('[CutSceneAI Studio] Character probe unavailable: ' + str(probe_error))
        try:
            _update_destination_readiness()
        except Exception as readiness_error:
            try:
                _report_inspection_failure(readiness_error)
            except Exception as report_error:
                unreal.log_error('[CutSceneAI Studio] Unable to record readiness failure: ' + str(report_error))
            unreal.log_warning('[CutSceneAI Studio] Destination inspection unavailable: ' + str(readiness_error))
        # The standard deterministic transfer remains the default. The
        # editor companion executes only strict, candidate-bound agent actions.
        try:
            import studio_agent_executor
            studio_agent_executor.service_one(
                unreal, WORKSPACE, project=_loaded_project(),
                level=_loaded_level(), save=_save
            )
        except Exception as agent_error:
            unreal.log_warning('[CutSceneAI Studio] Agent request inspection blocked: ' + str(agent_error))
        jobs_folder = WORKSPACE / 'jobs'
        if not jobs_folder.is_dir():
            return
        if jobs_folder.is_symlink() or len(list(jobs_folder.glob('*.json'))) > 10000:
            raise RuntimeError('Native job queue is unsafe or unbounded.')
        for path in sorted(jobs_folder.glob('*.json')):
            if path.is_symlink() or not path.is_file():
                # A hostile queue entry must not become a native operation.
                continue
            job = _load(path)
            if job.get('status') != 'QUEUED':
                continue
            BUSY = True
            native_guard = None
            attempt = None
            other_claim_exists = False
            try:
                native_guard = _native_attempt_guard()
                # Durable write-ahead claim happens BEFORE RUNNING status,
                # import, level creation, actor changes or sequence generation.
                # Two editors racing the same queue cannot both create it.
                attempt = native_guard.claim(
                    WORKSPACE, job, editor_pid=os.getpid(),
                )
                job['element6_claim_sha256'] = attempt['claim_sha256']
                job['element6_guard_status'] = 'CLAIMED_NO_REPLAY'
                job['status'] = 'RUNNING'
                _save(path, job)
                job = _execute(job)
            except Exception as exc:
                # Another editor may have claimed the QUEUED job before it
                # changed the shared job file to RUNNING. Never let the losing
                # editor overwrite the owner's live status or native receipt.
                candidate_id = job.get('candidate_id')
                job_id = job.get('job_id')
                if (attempt is None and native_guard is not None
                        and isinstance(candidate_id, str)
                        and isinstance(job_id, str)
                        and native_guard.CANDIDATE.fullmatch(candidate_id)
                        and native_guard.JOB_ID.fullmatch(job_id)):
                    other_claim_exists = (
                        WORKSPACE / 'candidates' / candidate_id /
                        ('element6-native-claim-' + job_id + '.json')
                    ).is_file()
                if other_claim_exists:
                    unreal.log_warning(
                        '[CutSceneAI Studio] Existing native attempt owns this '
                        'queue item. Do not replay or overwrite its job status.'
                    )
                else:
                    job['failure_stage'] = job.get('execution_stage', 'UNKNOWN_NATIVE_STAGE')
                    job['status'] = ('PARTIAL_SETUP_MUST_INSPECT'
                                     if job.get('setup_status') == 'PARTIAL_SETUP_MUST_INSPECT'
                                     else 'BLOCKED_OR_FAILED')
                    job['error'] = str(exc)
                    job['traceback'] = traceback.format_exc()
                    job['fidelity_verified'] = False
                    if attempt is not None:
                        job['element6_guard_status'] = (
                            'INCOMPLETE_OR_FAILED_NO_AUTOMATIC_REPLAY'
                        )
                    candidate = Path(str(job.get('candidate_dir') or ''))
                    if (candidate / 'character-native-attempt.json').exists():
                        try:
                            import studio_character_execution
                            studio_character_execution.attempt_status(
                                job, 'FAILED_NO_REPLAY', reason=str(exc),
                            )
                        except Exception as attempt_error:
                            job['character_attempt_record_error'] = str(attempt_error)
                    unreal.log_error('[CutSceneAI Studio] Job stopped: ' + str(exc))
            finally:
                if attempt is not None and native_guard is not None:
                    try:
                        if (job.get('generation_status') == 'GENERATED_UNVERIFIED'
                                and job.get('status') not in
                                native_guard.FINAL_FAILURE_STATES):
                            native_guard.step(
                                WORKSPACE, job, attempt,
                                'TERMINAL_EVIDENCE_RECORDED',
                            )
                        proof = native_guard.terminal(WORKSPACE, job, attempt)
                        job['element6_guard_status'] = proof['status']
                        job['element6_runtime_receipt_sha256'] = proof[
                            'runtime_receipt_sha256'
                        ]
                        job['element6_receipt_sha256'] = proof['receipt_sha256']
                        job['element6_replay_allowed'] = False
                    except Exception as guard_error:
                        # Never mask a missing/tampered attempt receipt as an
                        # otherwise successful native transfer.
                        job['element6_guard_status'] = (
                            'RECEIPT_UNAVAILABLE_MANUAL_INSPECTION_REQUIRED'
                        )
                        job['element6_guard_error'] = type(guard_error).__name__
                        if job.get('generation_status') == 'GENERATED_UNVERIFIED':
                            job['status'] = (
                                'GENERATED_GUARD_EVIDENCE_INCOMPLETE_REVIEW_REQUIRED'
                            )
                        job['fidelity_verified'] = False
                if not other_claim_exists:
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
    HANDLE = unreal.register_slate_post_tick_callback(_tick_dispatch)
    unreal.log_warning('[CutSceneAI Studio] Local worker listening; idle Python updates refresh automatically without restarting Unreal.')


def stop():
    global HANDLE
    if HANDLE is None:
        return
    unreal.unregister_slate_post_tick_callback(HANDLE)
    HANDLE = None
