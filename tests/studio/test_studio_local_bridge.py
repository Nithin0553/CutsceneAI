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

    def fake_prepare(csir, mapping, capture, sequence, out, *, skeletal_root_world_lock,
                     hierarchy_transfer):
        assert Path(csir) == Path(config['csir'])
        assert Path(mapping) == Path(config['mapping'])
        assert Path(capture) == Path(config['capture'])
        assert sequence.startswith('/Game/Trials/LS_BenchmarkV8_STUDIO_')
        assert skeletal_root_world_lock is False
        assert hierarchy_transfer is False
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
    from datetime import UTC, datetime
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
        'heartbeat': datetime.now(UTC).isoformat(), 'project': config['target_project'], 'level': config['level_path']
    })
    # Valid editor heartbeat is insufficient when its scene is missing actors.
    with pytest.raises(ValueError, match='Destination not ready'):
        bridge.queue_trial(candidate_id, work)
    import hashlib
    bridge.atomic_json(work / 'active-candidate.json', {
        'candidate_id': candidate_id, 'sequence_path': '/Game/Trials/LS_New'
    })
    (folder / 'transfer-plan.json').write_text('{}')
    bridge.atomic_json(work / 'destination-readiness.json', {
        'kind': 'cutsceneai.studio.destination_readiness',
        'checked_at': datetime.now(UTC).isoformat(),
        'candidate_id': candidate_id, 'sequence_path': '/Game/Trials/LS_New',
        'plan_sha256': hashlib.sha256((folder / 'transfer-plan.json').read_bytes()).hexdigest(),
        'expected_project': config['target_project'], 'observed_project': config['target_project'],
        'expected_level': config['level_path'], 'observed_level': config['level_path'],
        'status': 'SCENE_SETUP_REQUIRED', 'ready': False, 'missing_actors': [{'actor_label':'CSAI_Test_CAM_A'}],
        'next_action': 'Create the required actors.'
    })
    with pytest.raises(ValueError, match='missing actors'):
        bridge.queue_trial(candidate_id, work)
    valid = bridge.load_json(work / 'destination-readiness.json')
    valid['status'] = 'READY'
    valid['ready'] = True
    valid['missing_actors'] = []
    valid['next_action'] = 'Ready.'
    bridge.atomic_json(work / 'destination-readiness.json', valid)
    assert bridge.destination_readiness(work)['ready'] is True
    # With a verified ready-scene report, a new job can now be queued.
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
    from datetime import UTC, datetime
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
        'heartbeat': datetime.now(UTC).isoformat(),
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


def test_readiness_refuses_stale_or_different_candidate(tmp_path):
    import hashlib
    from datetime import UTC, datetime, timedelta
    cfg = fixture_files(tmp_path)
    work = tmp_path / 'runs'
    work.mkdir(parents=True)
    bridge.atomic_json(work / 'connection.json', bridge.config_check(cfg))
    cid = '20261031T123456Z_aaaabbbb'
    folder = work / 'candidates' / cid
    folder.mkdir(parents=True)
    plan = folder / 'transfer-plan.json'
    plan.write_text('{"actions":[]}', encoding='utf-8')
    bridge.atomic_json(work / 'active-candidate.json', {'candidate_id':cid, 'sequence_path':'/Game/New'})
    bridge.atomic_json(work / 'unreal-worker.json', {'heartbeat':datetime.now(UTC).isoformat(),
                                                  'project':cfg['target_project'],'level':cfg['level_path']})
    report = {'kind':'cutsceneai.studio.destination_readiness',
              'candidate_id':cid, 'sequence_path':'/Game/New',
              'plan_sha256':hashlib.sha256(plan.read_bytes()).hexdigest(),
              'expected_project':cfg['target_project'], 'observed_project':cfg['target_project'],
              'expected_level':cfg['level_path'], 'observed_level':cfg['level_path'],
              'checked_at':datetime.now(UTC).isoformat(), 'ready':True,'status':'READY'}
    bridge.atomic_json(work / 'destination-readiness.json', report)
    assert bridge.destination_readiness(work)['ready'] is True
    report['candidate_id'] = 'different'
    bridge.atomic_json(work / 'destination-readiness.json', report)
    assert bridge.destination_readiness(work)['status'] == 'INSPECTION_UNAVAILABLE'
    report['candidate_id'] = cid
    report['checked_at'] = (datetime.now(UTC)-timedelta(minutes=1)).isoformat()
    bridge.atomic_json(work / 'destination-readiness.json', report)
    assert bridge.destination_readiness(work)['status'] == 'INSPECTION_UNAVAILABLE'
    report['checked_at'] = datetime.now(UTC).isoformat()
    bridge.atomic_json(work / 'destination-readiness.json', report)
    plan.write_text('{"actions":["tampered"]}', encoding='utf-8')
    assert bridge.destination_readiness(work)['status'] == 'INSPECTION_UNAVAILABLE'


def test_status_exposes_readiness_before_generate(service):
    base, tmp = service
    cfg = fixture_files(tmp)
    token=call(base+'/api/status')[1]['token']
    assert call(base+'/api/connect',cfg,token)[0]==200
    status, data=call(base+'/api/status')
    assert status==200 and data['destination_readiness']['ready'] is False
    assert data['destination_readiness']['status']=='WAITING_FOR_PLAN'


def test_live_editor_without_report_is_not_endless_checking(tmp_path):
    """Connected and heartbeating worker cannot leave UI in checking forever."""
    from datetime import UTC, datetime
    cfg = fixture_files(tmp_path)
    work = tmp_path / 'runs'
    bridge.atomic_json(work / 'connection.json', bridge.config_check(cfg))
    cid = '20261101T012000Z_aaaabbbb'
    path = work / 'candidates' / cid / 'transfer-plan.json'
    path.parent.mkdir(parents=True)
    path.write_text('{"actions":[]}', encoding='utf-8')
    bridge.atomic_json(work / 'active-candidate.json', {
        'candidate_id': cid, 'sequence_path': '/Game/Tests/LS_New',
    })
    bridge.atomic_json(work / 'unreal-worker.json', {
        'heartbeat': datetime.now(UTC).isoformat(),
        'project': cfg['target_project'], 'level': cfg['level_path'],
        'worker': 'studio-editor-v0.5',
    })
    report = bridge.destination_readiness(work)
    assert report['status'] == 'INSPECTION_UNAVAILABLE'
    assert report['ready'] is False
    assert 'Python log' in report['next_action']


def test_connected_old_companion_explains_restart(tmp_path):
    from datetime import UTC, datetime
    cfg = fixture_files(tmp_path)
    work = tmp_path / 'runs'
    connected = bridge.config_check(cfg)
    connected['unity_project'] = str(tmp_path)
    bridge.atomic_json(work / 'connection.json', connected)
    bridge.atomic_json(work / 'active-candidate.json', {
        'candidate_id': '20261101T012000Z_aaaabbbb', 'sequence_path': '/Game/New',
    })
    bridge.atomic_json(work / 'unreal-worker.json', {
        'heartbeat': datetime.now(UTC).isoformat(),
        'project': cfg['target_project'], 'level': cfg['level_path'],
        'worker': 'studio-editor-v0.3',
    })
    report = bridge.destination_readiness(work)
    assert report['status'] == 'UPGRADE_COMPANION'
    assert 'restart unreal' in report['next_action'].lower()


def test_automatic_studio_preparation_requests_safe_hierarchy_reconstruction(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    config = fixture_files(tmp_path)
    unity = tmp_path / "Unity"
    (unity / "Assets").mkdir(parents=True)
    config["unity_project"] = str(unity)
    config["source_scope"] = "Assets"
    work = tmp_path / "runs"
    bridge.atomic_json(work / "connection.json", bridge.config_check(config))
    original = Path(config["mapping"]).read_bytes()

    def fake_prepare(csir, mapping, capture, sequence, out, *,
                     skeletal_root_world_lock, hierarchy_transfer):
        assert hierarchy_transfer is True
        assert skeletal_root_world_lock is False
        out.mkdir(parents=True)
        (out / "transfer-plan.json").write_text(json.dumps({
            "sequence_asset_path": sequence, "actions": [], "bindings": {}
        }))
        copied = out.with_suffix(".mapping.json")
        copied.write_text(json.dumps({"sequence_asset_path": sequence,
                                      "enable_cinetwin_hierarchy": True}))
        return copied, {"ced_preflight": "REVIEW_REQUIRED",
                        "track_coverage": {"NATIVE_UNVERIFIED": 1}}

    monkeypatch.setitem(sys.modules, "studio_candidate",
                        SimpleNamespace(prepare_candidate=fake_prepare))
    result = bridge.prepare(work)
    assert result["engine_generation_executed"] is False
    assert Path(config["mapping"]).read_bytes() == original


def test_source_only_studio_candidate_uses_hierarchy_enabled_mapping_copy(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    config = fixture_files(tmp_path)
    config.pop("capture")
    unity = tmp_path / "Unity"
    (unity / "Assets").mkdir(parents=True)
    config["unity_project"] = str(unity)
    config["source_scope"] = "Assets"
    work = tmp_path / "runs"
    bridge.atomic_json(work / "connection.json", bridge.config_check(config))
    original = Path(config["mapping"]).read_bytes()
    observed = {}

    def fake_prepared(csir, copied_mapping, output, *, target_project):
        mapping = json.loads(Path(copied_mapping).read_text(encoding="utf-8"))
        observed["hierarchy"] = mapping.get("enable_cinetwin_hierarchy")
        assert mapping["overwrite_sequence"] is False
        assert mapping["sequence_asset_path"].startswith("/Game/Trials/LS_BenchmarkV8_STUDIO_")
        output.mkdir(parents=True)
        (output / "transfer-plan.json").write_text(json.dumps({
            "sequence_asset_path": mapping["sequence_asset_path"],
            "bindings": {}, "actions": [],
        }))
        return {"ced_preflight": "REVIEW_REQUIRED",
                "track_coverage": {"NATIVE_UNVERIFIED": 1}}

    monkeypatch.setitem(sys.modules, "prepared_transfer",
                        SimpleNamespace(prepare=fake_prepared))
    result = bridge.prepare(work)
    assert observed["hierarchy"] is True
    assert result["engine_generation_executed"] is False
    assert Path(config["mapping"]).read_bytes() == original



def test_failed_job_exposes_native_stage_and_exact_safe_setup_receipt(tmp_path):
    work = tmp_path / "work"
    candidate = work / "candidates" / "candidate_001"
    candidate.mkdir(parents=True)
    job_id = "d" * 32
    receipt = candidate / ("automatic-setup-receipt-" + job_id + ".json")
    receipt.write_text(json.dumps({
        "kind": "cutsceneai.studio.automatic_setup_receipt",
        "status": "PARTIAL_SETUP_MUST_INSPECT",
        "failed_step": {"phase": "asset_import", "path": "/Game/Studio/CharacterA"},
        "recovery": "Do not rerun; inspect imported assets.",
        "error": {"type": "AutomaticSetupError", "message": "FBX import failed"},
    }))
    job = {
        "job_id": job_id, "candidate_id": "candidate_001",
        "candidate_dir": str(candidate), "created_at": "2026-11-09T17:00:00Z",
        "status": "PARTIAL_SETUP_MUST_INSPECT",
        "generation_status": "NOT_STARTED",
        "failure_stage": "IMPORTING_ASSETS_AND_CREATING_ACTORS",
        "error": "FBX import failed",
        "setup_receipt_file": str(receipt),
        "setup_status": "PARTIAL_SETUP_MUST_INSPECT",
    }
    bridge.atomic_json(work / "jobs" / (job_id + ".json"), job)
    result = bridge.job_status(job_id, work)
    assert result["error"] == "FBX import failed"
    assert result["failure_stage"] == "IMPORTING_ASSETS_AND_CREATING_ACTORS"
    assert result["created_at"] == "2026-11-09T17:00:00Z"
    assert result["candidate_id"] == "candidate_001"
    assert result["setup_failed_step"]["phase"] == "asset_import"
    assert result["setup_recovery"].startswith("Do not rerun")
    assert result["setup_error"] == "FBX import failed"
    assert "traceback" not in result

    # A forged receipt path cannot read arbitrary files outside the candidate.
    external = tmp_path / "outside.json"
    external.write_text(receipt.read_text())
    job["setup_receipt_file"] = str(external)
    bridge.atomic_json(work / "jobs" / (job_id + ".json"), job)
    blocked = bridge.job_status(job_id, work)
    assert blocked["error"] == "FBX import failed"
    assert "setup_failed_step" not in blocked
    assert "setup_recovery" not in blocked


def test_old_failed_job_keeps_original_error_without_new_stage(tmp_path):
    work = tmp_path / "work"
    job_id = "e" * 32
    bridge.atomic_json(work / "jobs" / (job_id + ".json"), {
        "job_id": job_id,
        "status": "BLOCKED_OR_FAILED",
        "generation_status": "NOT_STARTED",
        "error": "Target already exists; refusing to overwrite or rerun.",
    })
    report = bridge.job_status(job_id, work)
    assert report["error"].startswith("Target already exists")
    assert report["failure_stage"] is None
    assert "setup_failed_step" not in report



def _current_editor_heartbeat(config):
    import hashlib
    from datetime import UTC, datetime

    worker_file = (bridge.ROOT / 'integrations/unreal' /
                   'studio_local_editor_worker.py')
    return {
        'heartbeat': datetime.now(UTC).isoformat(),
        'project': config['target_project'],
        'level': config['level_path'],
        'worker': bridge.REQUIRED_WORKER_PROTOCOL,
        'checkout_root': str(bridge.ROOT.resolve()),
        'worker_source_sha256': hashlib.sha256(worker_file.read_bytes()).hexdigest(),
    }


def test_unreal_companion_handshake_rejects_old_cached_or_foreign_worker(tmp_path):
    config = fixture_files(tmp_path)
    good = _current_editor_heartbeat(config)
    result = bridge.worker_code_mismatch({
        'worker_version': good['worker'],
        'checkout_root': good['checkout_root'],
        'worker_source_sha256': good['worker_source_sha256'],
    })
    assert result is None
    for changed, expected in [
        ({'worker_version': 'studio-editor-v0.5'}, 'requires'),
        ({'worker_source_sha256': '0' * 64}, 'cached an outdated'),
        ({'checkout_root': str(tmp_path / 'OtherCheckout')}, 'different'),
        ({'worker_source_sha256': None}, 'cached an outdated'),
        ({'checkout_root': None}, 'valid'),
        ({'checkout_root': '.'}, 'absolute'),
    ]:
        worker = {
            'worker_version': good['worker'],
            'checkout_root': good['checkout_root'],
            'worker_source_sha256': good['worker_source_sha256'],
        }
        worker.update(changed)
        assert expected in bridge.worker_code_mismatch(worker)


def test_destination_readiness_blocks_older_editor_for_source_studio(tmp_path):
    config = fixture_files(tmp_path)
    config = bridge.config_check(config)
    # A source-project Studio connection is subject to the stronger
    # module-origin handshake; target-only legacy trials are unaffected.
    config['unity_project'] = str(tmp_path / 'Unity')
    work = tmp_path / 'runs'
    bridge.atomic_json(work / 'connection.json', config)
    bridge.atomic_json(work / 'active-candidate.json', {
        'candidate_id': 'candidate_new', 'sequence_path': '/Game/Fresh',
    })
    old = _current_editor_heartbeat(config)
    old['worker'] = 'studio-editor-v0.5'
    bridge.atomic_json(work / 'unreal-worker.json', old)
    report = bridge.destination_readiness(work)
    assert report['status'] == 'UPGRADE_COMPANION'
    assert report['ready'] is False
    assert 'completely close Unreal Editor' in report['next_action']
    assert 'new transfer candidate' in report['next_action']
    current = _current_editor_heartbeat(config)
    bridge.atomic_json(work / 'unreal-worker.json', current)
    followup = bridge.destination_readiness(work)
    assert followup['status'] != 'UPGRADE_COMPANION'


def test_queue_refuses_stale_worker_before_job_or_asset_mutation(tmp_path, monkeypatch):
    import sys
    from datetime import UTC, datetime
    from types import SimpleNamespace

    cfg = bridge.config_check(fixture_files(tmp_path))
    cfg['unity_project'] = str(tmp_path / 'Unity')
    work = tmp_path / 'runs'
    bridge.atomic_json(work / 'connection.json', cfg)
    candidate = 'candidate_no_stale_worker'
    path = work / 'candidates' / candidate
    path.mkdir(parents=True)
    (path / 'session.json').write_text('{}')
    session = {
        'source': {'csir_path': cfg['csir']},
        'source_capture': {'path': cfg['capture']},
        'target': {'mapping_path': cfg['mapping'],
                   'sequence_asset_path': '/Game/CutSceneAI/New'},
    }
    monkeypatch.setitem(sys.modules, 'prepared_transfer',
                        SimpleNamespace(verify=lambda _: session))
    monkeypatch.setattr(bridge, 'config_check', lambda current: current)
    heartbeat = _current_editor_heartbeat(cfg)
    heartbeat['worker'] = 'studio-editor-v0.5'
    bridge.atomic_json(work / 'unreal-worker.json', heartbeat)
    with pytest.raises(ValueError, match='Unreal companion update required'):
        bridge.queue_trial(candidate, work)
    assert not (work / 'jobs').exists() or not list((work / 'jobs').glob('*.json'))
    assert not (work / 'active-job.json').exists()

    # A new-protocol worker that reports an old imported code hash also blocks.
    heartbeat['worker'] = bridge.REQUIRED_WORKER_PROTOCOL
    heartbeat['worker_source_sha256'] = 'f' * 64
    bridge.atomic_json(work / 'unreal-worker.json', heartbeat)
    with pytest.raises(ValueError, match='cached an outdated Python worker'):
        bridge.queue_trial(candidate, work)
    assert not (work / 'active-job.json').exists()
