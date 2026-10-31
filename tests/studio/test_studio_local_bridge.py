"""End-to-end localhost API boundary tests, no Unity or Unreal runtime required."""
import importlib.util
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent / 'tools/studio_local_bridge.py').is_file())
MODULE = ROOT / 'tools/studio_local_bridge.py'
spec = importlib.util.spec_from_file_location('studio_local_bridge', MODULE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


@pytest.fixture
def service(tmp_path):
    web = tmp_path / 'web'
    web.mkdir()
    (web / 'index.html').write_text('studio test')
    server = ThreadingHTTPServer(('127.0.0.1', 0), bridge.create_handler(web, tmp_path / 'work'))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}', tmp_path
    server.shutdown()
    server.server_close()
    thread.join()


def call(url, payload=None, key=None, origin=None):
    headers = {}
    if payload is not None:
        headers['Content-Type'] = 'application/json'
        if key:
            headers['X-CSAI-Token'] = key
        if origin:
            headers['Origin'] = origin
    req = Request(url, headers=headers,
                  data=json.dumps(payload).encode() if payload is not None else None)
    try:
        with urlopen(req, timeout=5) as result:
            return result.status, json.loads(result.read())
    except HTTPError as err:
        return err.code, json.loads(err.read())


def fixture_files(tmp_path):
    csir = tmp_path / 'source.csir.json'
    csir.write_text(json.dumps({
        'schema_version': '0.1.0',
        'cutscene_id': 'known', 'source': {'engine': 'unity'},
        'tracks': [{}, {}], 'entities': [{}, {}, {}],
    }))
    capture = tmp_path / 'source.cinetwin.behavior.json'
    capture.write_text(json.dumps({'kind': 'cinetwin.behavior_capture', 'cutscene_id': 'known'}))
    mapping = tmp_path / 'target_mapping.json'
    mapping.write_text(json.dumps({
        'sequence_asset_path': '/Game/Trials/LS_BenchmarkV8',
        'overwrite_sequence': False,
    }))
    project = tmp_path / 'Game.uproject'
    project.write_text('{}')
    return {'csir': str(csir), 'capture': str(capture),
            'mapping': str(mapping), 'target_project': str(project),
            'level_path': '/Game/Level'}


def test_local_connection_and_source_listing(service):
    base, tmp = service
    status, initial = call(base + '/api/status')
    assert status == 200 and initial['connected'] is False
    config = fixture_files(tmp)
    status, blocked = call(base + '/api/connect', config)
    assert status == 403 and 'token' in blocked['error'].lower()
    status, result = call(base + '/api/connect', config, initial['token'])
    assert status == 200 and result['source_track_count'] == 2
    assert result['source_entity_count'] == 3
    assert result['skeletal_root_world_lock'] is False
    status, source = call(base + '/api/cutscenes')
    assert status == 200 and source['cutscenes'][0]['cutscene_id'] == 'known'
    status, current = call(base + '/api/status')
    assert status == 200 and current['connected'] is True


def test_rejects_cross_site_post_and_wrong_capture(service):
    base, tmp = service
    token = call(base + '/api/status')[1]['token']
    config = fixture_files(tmp)
    status, blocked = call(base + '/api/connect', config, token, origin='https://attacker.example')
    assert status == 403
    Path(config['capture']).write_text(json.dumps({'cutscene_id': 'another'}))
    status, blocked = call(base + '/api/connect', config, token)
    assert status == 422 and 'does not match' in blocked['error']
    assert not (tmp / 'work/connection.json').exists()


def test_no_target_overwrite_and_no_execution_without_worker(service):
    base, tmp = service
    token = call(base + '/api/status')[1]['token']
    config = fixture_files(tmp)
    Path(config['mapping']).write_text(json.dumps({
        'sequence_asset_path': '/Game/Level/Old', 'overwrite_sequence': True,
    }))
    status, res = call(base + '/api/connect', config, token)
    assert status == 422 and 'overwriting' in res['error']
    Path(config['mapping']).write_text(json.dumps({
        'sequence_asset_path': '/Game/Level/Old', 'overwrite_sequence': False,
    }))
    assert call(base + '/api/connect', config, token)[0] == 200
    status, res = call(base + '/api/execute', {'candidate_id': 'not_a_candidate'}, token)
    assert status == 422 and 'not found' in res['error'].lower()


def test_report_path_is_confined_to_candidates(tmp_path):
    work = tmp_path / 'work'
    jobs = work / 'jobs'
    jobs.mkdir(parents=True)
    job_id = 'a' * 32
    external = tmp_path / 'untrusted-report.json'
    external.write_text('{}')
    bridge.atomic_json(jobs / (job_id+'.json'), {'job_id': job_id, 'diagnostic_file': str(external)})
    with pytest.raises(ValueError, match='outside'):
        bridge.diagnostic_summary(job_id, work)


def test_prepare_calls_existing_candidate_backend_without_changing_original(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    config = fixture_files(tmp_path)
    work = tmp_path / 'runs'
    bridge.atomic_json(work / 'connection.json', bridge.config_check(config))
    original_mapping = Path(config['mapping']).read_bytes()

    def fake_prepare(csir, mapping, capture, sequence, out, *, skeletal_root_world_lock):
        assert Path(csir) == Path(config['csir'])
        assert Path(mapping) == Path(config['mapping'])
        assert Path(capture) == Path(config['capture'])
        assert sequence.startswith('/Game/Trials/LS_BenchmarkV8_STUDIO_')
        assert skeletal_root_world_lock is False
        out.mkdir(parents=True)
        (out / 'transfer-plan.json').write_text(json.dumps({'actions':[{'kind':'camera_cut'},{'kind':'transform'}]}))
        copy = out.with_suffix('.mapping.json')
        copy.write_text(json.dumps({'sequence_asset_path': sequence}))
        return copy, {'ced_preflight': 'REVIEW_REQUIRED',
                      'track_coverage': {'NATIVE_UNVERIFIED': 2}}

    monkeypatch.setitem(sys.modules, 'studio_candidate', SimpleNamespace(prepare_candidate=fake_prepare))
    result = bridge.prepare(work)
    assert result['engine_generation_executed'] is False
    assert result['behavioral_fidelity_established'] is False
    assert result['track_coverage'] == {'NATIVE_UNVERIFIED': 2}
    assert Path(config['mapping']).read_bytes() == original_mapping


def test_queue_requires_alive_editor_and_immutable_handoff(tmp_path, monkeypatch):
    import sys
    from datetime import datetime, timezone
    from types import SimpleNamespace

    config = fixture_files(tmp_path)
    work = tmp_path / 'runs'
    checked = bridge.config_check(config)
    bridge.atomic_json(work / 'connection.json', checked)
    candidate_id = '20261030T123456Z_deadbeef'
    folder = work / 'candidates' / candidate_id
    folder.mkdir(parents=True)
    (folder / 'session.json').write_text('{}')
    with pytest.raises(ValueError, match='not connected'):
        # No editor heartbeat => fail-closed even with a valid session.
        session = {'source': {'csir_path': config['csir']},
                   'source_capture': {'path': config['capture']},
                   'target': {'mapping_path': config['mapping'],
                              'sequence_asset_path': '/Game/Trials/LS_New'}}
        monkeypatch.setitem(sys.modules, 'prepared_transfer', SimpleNamespace(verify=lambda _: session))
        bridge.queue_trial(candidate_id, work)

    bridge.atomic_json(work / 'unreal-worker.json', {
        'heartbeat': datetime.now(timezone.utc).isoformat(), 'project': config['target_project'], 'level': config['level_path']
    })
    # With explicit editor heartbeat, a new job is queued but not claimed completed.
    result = bridge.queue_trial(candidate_id, work)
    assert result['status'] == 'QUEUED'
    job = bridge.job_status(result['job_id'], work)
    assert job['generation_status'] == 'NOT_STARTED'
    assert job['fidelity_verified'] is False


def test_source_capture_optional_during_connection(service):
    base, tmp = service
    token = call(base + '/api/status')[1]['token']
    config = fixture_files(tmp)
    config['capture'] = ''
    status, connected = call(base + '/api/connect', config, token)
    assert status == 200
    assert connected['capture'] == ''
    assert connected['source_capture_available'] is False
    assert connected['track_types'] == {'unknown': 2}


def test_worker_must_match_project_and_level(tmp_path, monkeypatch):
    import sys
    from datetime import datetime, timezone
    from types import SimpleNamespace
    config = fixture_files(tmp_path)
    work = tmp_path / 'runs'
    bridge.atomic_json(work / 'connection.json', bridge.config_check(config))
    candidate_id = '20261030T123456Z_deadbeef'
    candidate_dir = work / 'candidates' / candidate_id
    candidate_dir.mkdir(parents=True)
    (candidate_dir / 'session.json').write_text('{}')
    session = {'source': {'csir_path': config['csir']},
               'source_capture': {'path': config['capture']},
               'target': {'mapping_path': config['mapping'],
                          'sequence_asset_path': '/Game/Trials/LS_New'}}
    monkeypatch.setitem(sys.modules, 'prepared_transfer', SimpleNamespace(verify=lambda _: session))
    bridge.atomic_json(work / 'unreal-worker.json', {
        'heartbeat': datetime.now(timezone.utc).isoformat(),
        'project': config['target_project'], 'level': '/Game/Wrong'})
    with pytest.raises(ValueError, match='different project or level'):
        bridge.queue_trial(candidate_id, work)


def test_target_observation_source_identity(tmp_path):
    import hashlib
    cfg = fixture_files(tmp_path)
    cfg['capture'] = ''
    source = Path(cfg['csir'])
    obs = tmp_path / 'target_observation.json'
    obs.write_text(json.dumps({
        'kind': 'cinetwin.target_behavior_observation',
        'cutscene_id': 'known',
        'source': {'csir_sha256': hashlib.sha256(source.read_bytes()).hexdigest()},
        'target': {'sequence_asset_path': '/Game/Tests/LS_Candidate'},
        'coverage': {'sample_count': 2, 'full_temporal_coverage': True,
                     'mapped_entity_count': 1, 'source_entity_count': 3,
                     'skeletal_rig_count': 0, 'unmapped_source_entities': [{}, {}]},
        'samples': [{'time_seconds': 0, 'entities': [{'entity_id':'actor1','actor_label':'Hero','world_transform':{'position_m':[0,0,0]}}], 'skeletal_poses':[]}, {'time_seconds': 1, 'entities': [{'entity_id':'actor1','actor_label':'Hero','world_transform':{'position_m':[0,0,1]}}], 'skeletal_poses':[]}]
    }))
    checked = bridge.config_check(cfg)
    summary = bridge.observation_summary(str(obs), checked)
    assert summary['sample_count'] == 2
    assert summary['fidelity'] == 'NOT_ESTABLISHED'
    data = json.loads(obs.read_text())
    data['source']['csir_sha256'] = 'wrong'
    obs.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='hash'):
        bridge.observation_summary(str(obs), checked)


def test_no_execution_without_candidate_file(service):
    base, tmp = service
    token = call(base + '/api/status')[1]['token']
    config = fixture_files(tmp)
    assert call(base + '/api/connect', config, token)[0] == 200
    status, res = call(base + '/api/observation', {'path': str(tmp / 'missing.json')}, token)
    assert status == 422
    assert 'observation' in res['error'].lower()


def test_prepare_without_unity_behavior_capture(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    cfg = fixture_files(tmp_path)
    cfg['capture'] = ''
    work = tmp_path / 'runs'
    bridge.atomic_json(work / 'connection.json', bridge.config_check(cfg))
    original = Path(cfg['mapping']).read_bytes()
    def fake_prep(csir, mapping, output, *, target_project=None):
        assert str(csir) == cfg['csir']
        assert target_project == cfg['target_project']
        assert Path(mapping).is_file()
        assert load_file(mapping)['overwrite_sequence'] is False
        assert load_file(mapping)['sequence_asset_path'] != '/Game/Trials/LS_BenchmarkV8'
        Path(output).mkdir()
        (Path(output)/'transfer-plan.json').write_text(json.dumps({
            'actions':[{'kind':'camera_cut'}, {'kind':'camera_cut'}, {'kind':'skeletal_animation'}]}))
        return {'ced_preflight':'REVIEW_REQUIRED', 'track_coverage':{'NATIVE_UNVERIFIED':2,'SKIPPED':1}}
    def load_file(p):
        return json.loads(Path(p).read_text())
    monkeypatch.setitem(sys.modules,'studio_candidate',SimpleNamespace(prepare_candidate=lambda *a,**k: None))
    monkeypatch.setitem(sys.modules,'prepared_transfer',SimpleNamespace(prepare=fake_prep))
    result = bridge.prepare(work)
    assert result['action_total'] == 3
    assert result['action_counts'] == {'camera_cut':2,'skeletal_animation':1}
    assert result['source_capture_available'] is False
    assert Path(cfg['mapping']).read_bytes() == original
    assert (work/'active-candidate.json').is_file()


def test_review_flags_expose_cross_namespace_and_unverified_audio():
    cfg = {'base_sequence': '/Game/OldAssets/LS_Demo',
           'level_path': '/Game/Tests/L_Target'}
    flags = bridge.review_flags(cfg, {'audio': 2, 'transform': 5})
    assert len(flags) == 2
    assert flags[0].startswith('MAPPING_NAMESPACE_DIFFERENCE:')
    assert 'AUDIO_TARGETS_UNVERIFIED' in flags[1]
    assert bridge.review_flags({'base_sequence':'/Game/Tests/LS_Demo',
                                'level_path':'/Game/Tests/L_Target'},
                               {'audio':0}) == []
