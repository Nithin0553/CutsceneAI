"""CutSceneAI Studio local-only API for immutable Unity -> Unreal trial handoffs.

No fake engine connection, no remote exposure and no filesystem writes to source.
This service uses the existing repository's studio_candidate.prepare_candidate.
Actual Unreal work runs separately in the Unreal editor bridge worker.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = Path.home() / '.cutsceneai-studio' / 'runs'
MAX_BODY = 64 * 1024
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.RLock()


def load_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(obj, dict):
        raise ValueError('Expected a JSON object: ' + str(path))
    return obj


def atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(temp, path)


def config_check(payload: dict[str, Any]) -> dict[str, Any]:
    keys = ('csir', 'mapping', 'target_project', 'level_path')
    for key in keys:
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError('Missing required ' + key)
    csir, mapping, target = (
        Path(payload[key]).expanduser().resolve() for key in keys[:3]
    )
    capture_text = str(payload.get('capture') or '').strip()
    capture = Path(capture_text).expanduser().resolve() if capture_text else None
    for title, path in [('Unity CSIR', csir), ('Target mapping', mapping),
                        ('Unreal .uproject', target)]:
        if not path.is_file():
            raise ValueError(f'{title} not found: {path}')
    if target.suffix.lower() != '.uproject':
        raise ValueError('Target must be a real Unreal .uproject file.')
    if payload.get('skeletal_root_world_lock') and capture is None:
        raise ValueError('Experimental skeletal root correction requires Unity CineTwin capture.')
    level = payload['level_path'].strip()
    if not level.startswith('/Game/') or '..' in level.split('/') or level.endswith('/'):
        raise ValueError('Target level must be a valid /Game/... asset path.')
    source_data = load_json(csir)
    if source_data.get('schema_version') != '0.1.0' or source_data.get('source', {}).get('engine') != 'unity':
        raise ValueError('Select a Unity CSIR v0.1.0 file.')
    if capture is not None:
        if not capture.is_file():
            raise ValueError('CineTwin capture not found: ' + str(capture))
        capture_data = load_json(capture)
        if capture_data.get('kind') != 'cinetwin.behavior_capture' or capture_data.get('cutscene_id') != source_data.get('cutscene_id'):
            raise ValueError('CineTwin capture does not match this Unity cutscene.')
    def seconds(value):
        if not isinstance(value, dict):
            return None
        rate = value.get('rate') or {}
        denominator = float(rate.get('numerator', 0))
        multiplier = float(rate.get('denominator', 1))
        if denominator <= 0:
            return None
        return float(value.get('value', 0)) * multiplier / denominator

    timing = source_data.get('timing') or {}
    start_sec, end_sec = seconds(timing.get('playback_start')), seconds(timing.get('playback_end'))
    duration = end_sec - start_sec if start_sec is not None and end_sec is not None else None
    display_rate = timing.get('display_rate') or timing.get('source_rate') or {}
    fps = (round(float(display_rate.get('numerator', 0)) / float(display_rate.get('denominator', 1)), 3)
           if isinstance(display_rate, dict) and float(display_rate.get('denominator', 1)) > 0 else None)
    mapping_data = load_json(mapping)
    sequence = mapping_data.get('sequence_asset_path')
    if not isinstance(sequence, str) or not sequence.startswith('/Game/'):
        raise ValueError('Target mapping is missing its /Game/... sequence path.')
    if mapping_data.get('overwrite_sequence') is True:
        raise ValueError('The target mapping requests sequence overwriting.')
    track_types = {}
    for track in source_data.get('tracks', []):
        category = str(track.get('ced_type') or 'unknown')
        track_types[category] = track_types.get(category, 0) + 1
    return {'csir': str(csir), 'capture': str(capture) if capture else '', 'mapping': str(mapping),
            'target_project': str(target), 'level_path': level,
            'skeletal_root_world_lock': bool(payload.get('skeletal_root_world_lock', False)),
            'cutscene_id': str(source_data['cutscene_id']),
            'scene_name': source_data.get('name') or source_data.get('title') or csir.stem,
            'source_track_count': len(source_data.get('tracks', [])),
            'source_entity_count': len(source_data.get('entities', [])),
            'source_fps': fps, 'source_duration_seconds': duration,
            'base_sequence': sequence, 'source_engine_version': str(source_data.get('source', {}).get('engine_version') or 'Unknown'),
            'track_types': track_types, 'source_capture_available': capture is not None}


def worker_connected(folder: Path = WORKSPACE) -> dict[str, Any]:
    marker = folder / 'unreal-worker.json'
    if not marker.is_file():
        return {'connected': False}
    try:
        data = load_json(marker)
        tick = datetime.fromisoformat(str(data['heartbeat']).replace('Z', '+00:00'))
        age = (datetime.now(timezone.utc) - tick).total_seconds()
        return {'connected': 0 <= age < 8, 'project': data.get('project'), 'level': data.get('level'), 'age_seconds': round(age, 1)}
    except (ValueError, KeyError, OSError):
        return {'connected': False}



def review_flags(config: dict[str, Any], action_counts: dict[str, int]) -> list[str]:
    """Flag risky transfer scope without assuming different folders are always invalid."""
    flags = []
    seq_dir = str(config.get('base_sequence') or '').rsplit('/', 1)[0]
    level_dir = str(config.get('level_path') or '').rsplit('/', 1)[0]
    if seq_dir and level_dir and seq_dir != level_dir:
        flags.append(
            'MAPPING_NAMESPACE_DIFFERENCE: Mapping sequence folder ' + seq_dir +
            ' differs from loaded target level folder ' + level_dir +
            '. Confirm this mapping belongs to the selected Unreal project.')
    if int(action_counts.get('audio', 0)) > 0:
        flags.append(
            'AUDIO_TARGETS_UNVERIFIED: Audio tracks are planned, but this UI has not '
            'verified their SoundWave assets in the selected Unreal project.')
    return flags


def prepare(folder: Path = WORKSPACE) -> dict[str, Any]:
    """Call the existing, source-authenticated transfer backend; never overwrite."""
    config = load_json(folder / 'connection.json')
    config_check(config)  # Recheck input files, target existence and source identity.
    active_job = folder / 'active-job.json'
    if active_job.is_file():
        prior = job_status(load_json(active_job)['job_id'], folder)
        if prior['status'] in {'QUEUED', 'RUNNING'}:
            raise ValueError('An Unreal job is still queued or running; wait for a terminal result.')
    tools_dir = ROOT / 'tools'
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from studio_candidate import prepare_candidate

    candidate_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8]
    candidate_dir = folder / 'candidates' / candidate_id
    old_sequence = config['base_sequence']
    new_sequence = old_sequence + '_STUDIO_' + candidate_id[-8:].upper()
    if config.get('capture'):
        mapping_copy, session = prepare_candidate(
            Path(config['csir']), Path(config['mapping']), Path(config['capture']),
            new_sequence, candidate_dir,
            skeletal_root_world_lock=config['skeletal_root_world_lock'],
        )
    else:
        # The existing immutable backend supports source-only preparation.
        # CineTwin parity remains unavailable until a real source capture is supplied.
        for part in ('packages/studio', 'packages/learning', 'packages/cinetwin', 'integrations/unreal'):
            entry = str(ROOT / part)
            if entry not in sys.path:
                sys.path.insert(0, entry)
        import prepared_transfer
        mapping_copy = candidate_dir.with_suffix('.mapping.json')
        original = load_json(Path(config['mapping']))
        original['sequence_asset_path'] = new_sequence
        original['overwrite_sequence'] = False
        if config['skeletal_root_world_lock']:
            raise ValueError('Experimental skeletal root world lock requires source CineTwin evidence.')
        mapping_copy.parent.mkdir(parents=True, exist_ok=True)
        with mapping_copy.open('x', encoding='utf-8') as handle:
            json.dump(original, handle, indent=2)
        session = prepared_transfer.prepare(
            config['csir'], mapping_copy, candidate_dir,
            target_project=config['target_project'],
        )
    plan = load_json(candidate_dir / 'transfer-plan.json')
    actions = plan.get('actions', [])
    action_counts = {}
    for action in actions:
        label = str(action.get('kind') or 'unknown')
        action_counts[label] = action_counts.get(label, 0) + 1
    flags = review_flags(config, action_counts)
    info = {'candidate_id': candidate_id, 'candidate_dir': str(candidate_dir),
            'review_flags': flags, 'source_mapping_path': config['mapping'],
            'source_base_sequence': config['base_sequence'],
            'mapping_copy': str(mapping_copy), 'sequence_path': new_sequence,
            'ced_preflight': session.get('ced_preflight'),
            'track_coverage': session.get('track_coverage'),
            'engine_generation_executed': False,
            'behavioral_fidelity_established': False, 'source_capture_available': bool(config.get('capture')),
            'action_counts': action_counts, 'action_total': len(actions)}
    atomic_json(folder / 'active-candidate.json', info)
    (folder / 'active-job.json').unlink(missing_ok=True)
    return info


def queue_trial(candidate_id: str, folder: Path = WORKSPACE) -> dict[str, Any]:
    if not candidate_id.isascii() or not candidate_id.replace('_', '').isalnum():
        raise ValueError('Invalid candidate identity.')
    candidate_dir = (folder / 'candidates' / candidate_id)
    session_path = candidate_dir / 'session.json'
    if not session_path.is_file():
        raise ValueError('Candidate not found.')
    # Reverify complete immutable evidence at submission time.
    for p in (ROOT / 'packages/studio', ROOT / 'packages/learning', ROOT / 'packages/cinetwin', ROOT / 'integrations/unreal'):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import prepared_transfer
    session = prepared_transfer.verify(candidate_dir)
    config = load_json(folder / 'connection.json')
    config_check(config)
    if session['source']['csir_path'] != config['csir']:
        raise ValueError('Session source differs from active connection.')
    session_capture = session.get('source_capture')
    if (session_capture['path'] if session_capture else '') != (config.get('capture') or ''):
        raise ValueError('Session capture differs from active connection.')
    if session['target']['sequence_asset_path'] == config['base_sequence']:
        raise ValueError('Original Level Sequence path cannot be reused.')
    heartbeat = worker_connected(folder)
    if not heartbeat['connected']:
        raise ValueError('Unreal bridge not connected: open staging project and start the editor companion.')
    if (os.path.normcase(str(heartbeat.get('project') or '')) != os.path.normcase(config['target_project'])
        or heartbeat.get('level') != config['level_path']):
        raise ValueError('Unreal worker is connected to a different project or level.')
    for old_job in (folder / 'jobs').glob('*.json') if (folder / 'jobs').is_dir() else []:
        if load_json(old_job).get('candidate_id') == candidate_id:
            raise ValueError('This candidate was already submitted; inspect its job instead of replaying it.')
    job_id = uuid.uuid4().hex
    job = {'kind': 'cutsceneai.studio.local_unreal_job', 'schema_version': '0.1.0',
           'job_id': job_id, 'status': 'QUEUED', 'candidate_id': candidate_id,
           'csir': config['csir'], 'capture': config['capture'],
           'mapping': session['target']['mapping_path'],
           'candidate_dir': str(candidate_dir),
           'sequence_path': session['target']['sequence_asset_path'],
           'expected_project': config['target_project'],
           'expected_level': config['level_path'],
           'created_at': datetime.now(timezone.utc).isoformat(),
           'generation_status': 'NOT_STARTED', 'fidelity_verified': False}
    atomic_json(folder / 'jobs' / (job_id + '.json'), job)
    atomic_json(folder / 'active-job.json', {'job_id': job_id})
    return {'job_id': job_id, 'status': 'QUEUED',
            'message': 'Unreal Editor will execute the prepared trial; fidelity remains unverified.'}


def job_status(job_id: str, folder: Path = WORKSPACE) -> dict[str, Any]:
    if len(job_id) != 32 or not all(c in '0123456789abcdef' for c in job_id):
        raise ValueError('Invalid job id.')
    job_path = folder / 'jobs' / (job_id + '.json')
    if not job_path.is_file():
        raise ValueError('Job not found.')
    job = load_json(job_path)
    return {key: job.get(key) for key in (
        'job_id', 'status', 'generation_status', 'sequence_path', 'diagnostic_file',
        'receipt_file', 'error', 'fidelity_verified', 'generated_sequence')}


def diagnostic_summary(job_id: str, folder: Path = WORKSPACE) -> dict[str, Any]:
    job = job_status(job_id, folder)
    path_str = job.get('diagnostic_file')
    if not path_str:
        raise ValueError('No independent CineTwin diagnostic for this job.')
    path = Path(path_str).resolve()
    if not path.is_relative_to((folder / 'candidates').resolve()) or not path.is_file():
        raise ValueError('Diagnostic path outside the prepared workspace.')
    data = load_json(path)
    if data.get('kind') != 'cutsceneai.cinetwin.unreal_world_pose_diagnostic':
        raise ValueError('Unexpected diagnostic report format.')
    return {'source': data.get('source'), 'target': {'sequence_path': data.get('target', {}).get('sequence_path')},
            'status': data.get('status'), 'entities': {
                name: {'actor_max_cm': row.get('actor_world', {}).get('max_absolute_error_cm'),
                       'root_max_cm': row.get('skeletal_root_world', {}).get('max_absolute_error_cm'),
                       'status': row.get('status')}
                for name, row in data.get('entities', {}).items()},
            'limitations': data.get('limitations', [])}


def observation_summary(path_string: str, config: dict[str, Any]) -> dict[str, Any]:
    """Read a user-selected existing CineTwin target capture; never call it parity."""
    source = load_json(Path(config['csir']))
    path = Path(path_string).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != '.json':
        raise ValueError('Choose an existing CineTwin target observation JSON.')
    if path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError('Observation file is too large (128 MB limit).')
    report = load_json(path)
    if report.get('kind') != 'cinetwin.target_behavior_observation':
        raise ValueError('Not a CineTwin target behavior observation.')
    if report.get('cutscene_id') != source.get('cutscene_id'):
        raise ValueError('Target observation belongs to a different Unity cutscene.')
    import hashlib
    digest = hashlib.sha256(Path(config['csir']).read_bytes()).hexdigest()
    if report.get('source', {}).get('csir_sha256') != digest:
        raise ValueError('Target observation source hash differs from connected CSIR.')
    cov = report.get('coverage') or {}
    samples = report.get('samples') or []
    if not samples or len(samples) != cov.get('sample_count') or not cov.get('full_temporal_coverage'):
        raise ValueError('Target observation sample coverage is incomplete.')
    if cov.get('source_entity_count') != len(source.get('entities') or []):
        raise ValueError('Observation entity scope differs from connected CSIR.')
    import math
    past = -math.inf
    for i, sample in enumerate(samples):
        time = float(sample.get('time_seconds', float('nan')))
        if not math.isfinite(time) or time <= past:
            raise ValueError('Observation times are missing or not increasing.')
        past = time
        if len(sample.get('entities') or []) != cov.get('mapped_entity_count'):
            raise ValueError(f'Observation actor count mismatch at sample {i}.')
        if len(sample.get('skeletal_poses') or []) != cov.get('skeletal_rig_count'):
            raise ValueError(f'Observation skeletal rig count mismatch at sample {i}.')
    # Target motion diagnostics are relative to the first observation, NOT Unity parity.
    first_actor = {e['entity_id']: e['world_transform']['position_m'] for e in samples[0]['entities']}
    first_bones = {(rig['entity_id'], b['bone_name']): b['world_position_m']
                   for rig in samples[0]['skeletal_poses'] for b in rig['bones']}
    actor_motion = {e['actor_label']: 0.0 for e in samples[0]['entities']}
    bone_motion = {rig['entity_id']: 0.0 for rig in samples[0]['skeletal_poses']}
    for sample in samples:
        for e in sample['entities']:
            start = first_actor[e['entity_id']]
            point = e['world_transform']['position_m']
            actor_motion[e['actor_label']] = max(actor_motion[e['actor_label']], math.dist(start, point) * 100)
        for rig in sample['skeletal_poses']:
            rid = rig['entity_id']
            for bone in rig['bones']:
                start = first_bones[(rid, bone['bone_name'])]
                bone_motion[rid] = max(bone_motion[rid], math.dist(start, bone['world_position_m']) * 100)
    actor_motion = {k:round(v,3) for k,v in actor_motion.items()}
    bone_motion = {k:round(v,3) for k,v in bone_motion.items()}
    # Summaries do not infer equivalence with Unity, camera optics or bone retargeting.
    return {'kind': report['kind'], 'cutscene_id': report['cutscene_id'],
            'sequence': report.get('target', {}).get('sequence_asset_path'),
            'sample_count': len(samples),
            'mapped_actor_count': cov.get('mapped_entity_count'),
            'source_entity_count': cov.get('source_entity_count'),
            'skeletal_rig_count': cov.get('skeletal_rig_count'),
            'unmapped_count': len(cov.get('unmapped_source_entities') or []),
            'actor_motion_cm': actor_motion, 'skeletal_bone_motion_cm': bone_motion,
            'fidelity': 'NOT_ESTABLISHED', 'comparison': 'TARGET_ONLY'}


def create_handler(webroot: Path, folder: Path = WORKSPACE):
    class StudioHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(webroot), **kwargs)

        def end_headers(self):
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            super().end_headers()

        def reply(self, status, obj):
            body = json.dumps(obj, allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def permitted(self):
            host = self.headers.get('Host', '').split(':')[0]
            origin = self.headers.get('Origin', '')
            return host in {'localhost', '127.0.0.1'} and (
                not origin or origin in {f'http://localhost:{self.server.server_port}', f'http://127.0.0.1:{self.server.server_port}'})

        def do_GET(self):
            if not self.permitted():
                return self.reply(403, {'error': 'Local origin required.'})
            path = urlparse(self.path).path
            if path == '/api/status':
                cfg = folder / 'connection.json'
                return self.reply(200, {'service': 'CutSceneAI Studio Local Companion',
                                        'repo_root': str(ROOT), 'token': TOKEN, 'connected': cfg.is_file(),
                                        'connection': load_json(cfg) if cfg.is_file() else None,
                                        'unreal_worker': worker_connected(folder),
                                        'candidate': load_json(folder / 'active-candidate.json') if (folder / 'active-candidate.json').is_file() else None,
                                        'active_job': load_json(folder / 'active-job.json').get('job_id') if (folder / 'active-job.json').is_file() else None,
                                        'observation': load_json(folder / 'attached-observation.json') if (folder / 'attached-observation.json').is_file() else None,
                                        'fidelity_verified': False})
            if path.startswith('/api/jobs/'):
                try:
                    return self.reply(200, job_status(path.rsplit('/', 1)[-1], folder))
                except ValueError as e:
                    return self.reply(404, {'error': str(e)})
            if path.startswith('/api/diagnostic/'):
                try:
                    return self.reply(200, diagnostic_summary(path.rsplit('/', 1)[-1], folder))
                except ValueError as e:
                    return self.reply(404, {'error': str(e)})
            if path == '/api/cutscenes':
                cfg = folder / 'connection.json'
                if not cfg.is_file():
                    return self.reply(409, {'error': 'Connect real inputs first.'})
                data = load_json(Path(load_json(cfg)['csir']))
                return self.reply(200, {'cutscenes': [{
                    'name': data.get('name') or data.get('title') or Path(load_json(cfg)['csir']).stem,
                    'cutscene_id': data.get('cutscene_id'),
                    'tracks': len(data.get('tracks', [])),
                    'entities': len(data.get('entities', [])),
                    'source': 'EXPORTED_CSIR'}]})
            return super().do_GET()

        def do_POST(self):
            if not self.permitted() or self.headers.get('X-CSAI-Token') != TOKEN:
                return self.reply(403, {'error': 'Local session token required.'})
            size_str = self.headers.get('Content-Length', '0')
            if not size_str.isdigit() or int(size_str) > MAX_BODY:
                return self.reply(413, {'error': 'Request too large.'})
            try:
                data = json.loads(self.rfile.read(int(size_str)))
                if not isinstance(data, dict):
                    raise ValueError('Expected JSON request object.')
                route = urlparse(self.path).path
                with LOCK:
                    if route == '/api/connect':
                        active_job_file = folder / 'active-job.json'
                        if active_job_file.is_file():
                            prior = job_status(load_json(active_job_file)['job_id'], folder)
                            if prior['status'] in {'QUEUED', 'RUNNING'}:
                                raise ValueError('Cannot change connections while an Unreal job is queued or running.')
                        result = config_check(data)
                        atomic_json(folder / 'connection.json', result)
                        for name in ('active-candidate.json', 'active-job.json', 'attached-observation.json'):
                            (folder / name).unlink(missing_ok=True)
                    elif route == '/api/prepare':
                        result = prepare(folder)
                    elif route == '/api/execute':
                        result = queue_trial(str(data.get('candidate_id', '')), folder)
                    elif route == '/api/observation':
                        cfg = folder / 'connection.json'
                        if not cfg.is_file():
                            raise ValueError('Connect a source cutscene first.')
                        summary = observation_summary(str(data.get('path', '')), load_json(cfg))
                        atomic_json(folder / 'attached-observation.json', summary)
                        result = summary
                    else:
                        return self.reply(404, {'error': 'Unknown route.'})
                return self.reply(200, result)
            except (ValueError, KeyError, OSError, RuntimeError, ImportError) as e:
                return self.reply(422, {'error': str(e)})

    return StudioHandler


def main(argv=None) -> int:
    global ROOT, WORKSPACE
    parser = argparse.ArgumentParser(description='CutSceneAI Studio localhost-only editor companion API')
    parser.add_argument('--repo', type=Path, default=ROOT, help='Repository root containing tools/studio_candidate.py')
    parser.add_argument('--web', type=Path, default=ROOT / 'apps/studio-web')
    parser.add_argument('--workspace', type=Path, default=WORKSPACE)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args(argv)
    ROOT = args.repo.resolve()
    WORKSPACE = args.workspace.resolve()
    if not (ROOT / 'tools/studio_candidate.py').is_file():
        parser.error('Repository must contain tools/studio_candidate.py.')
    if not (args.web / 'index.html').is_file():
        parser.error('Web UI directory is missing index.html.')
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    handler = create_handler(args.web.resolve(), WORKSPACE)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler)
    print(f'CutSceneAI Studio: http://127.0.0.1:{args.port}')
    print('Only localhost is accessible. Close with Ctrl+C.')
    try:
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
