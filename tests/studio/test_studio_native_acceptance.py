"""Exercise wiring and evidence gates without claiming an actual editor run."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'integrations' / 'unreal'))
import studio_native_acceptance as acceptance


@pytest.mark.parametrize('reopened', [True, False])
def test_native_acceptance_requires_reopen_and_compares_the_exact_full_capture(tmp_path, monkeypatch, reopened):
    candidate = tmp_path / 'candidates' / 'candidate'
    candidate.mkdir(parents=True)
    job_id = '1' * 32
    manifest = tmp_path / 'jobs' / (job_id + '.json')
    manifest.parent.mkdir()
    csir, capture, mapping = [str(tmp_path / name) for name in ('source.json', 'capture.json', 'mapping.json')]
    Path(capture).write_text(json.dumps({'native_unity_samples': [0, 0.25, 0.5]}))
    sequence = '/Game/Stage/LS_Candidate'
    level = '/Game/Stage/L_Candidate'
    generation_pid = os.getpid() + int(reopened)
    manifest.write_text(json.dumps({
        'kind': 'cutsceneai.studio.local_unreal_job', 'job_id': job_id,
        'generation_editor_pid': generation_pid, 'candidate_dir': str(candidate),
        'candidate_id': candidate.name, 'expected_level': level,
        'csir': csir, 'capture': capture, 'mapping': mapping, 'sequence_path': sequence,
    }))
    if not reopened:
        with pytest.raises(ValueError, match='fresh Editor process'):
            acceptance.start(tmp_path, job_id=job_id)
        assert not list(candidate.iterdir())
        return

    def verify(path):
        assert path == candidate
        return {'source': {'csir_path': csir},
                'target': {'sequence_asset_path': sequence, 'mapping_path': mapping},
                'source_capture': {'path': capture, 'sha256': 'a' * 64}}

    def sampling_plan(path, output):
        assert path == csir
        plan = {'times': [0, 0.25, 0.5]}
        output.write_text(json.dumps(plan))
        return plan

    def audit(path, output):
        assert path == manifest
        result = {'status': 'STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS',
                  'native_structure_status': 'PASS', 'restart_verified': True}
        output.write_text(json.dumps(result))
        return result

    def compare(plan, source, target):
        assert plan['times'] == source['native_unity_samples'] == target['native_samples']
        return {'evaluation': {'status': 'NO_FLAGGED_DIFFERENCES', 'unmapped_entity_count': 0},
                'rig_motion_diagnostics': [{'joint_positions': {'status': 'PASS'}}]}

    def begin(plan_path, target_mapping, target_sequence, output, *, probe_times, on_complete):
        assert probe_times is None
        assert target_mapping == mapping and target_sequence == sequence
        target = {'target': {'editor_pid': os.getpid(), 'sequence_asset_path': sequence + '.LS_Candidate'},
                  'native_samples': json.loads(Path(plan_path).read_text())['times'],
                  'quality': {'status': 'OBSERVED_NOT_YET_PROVEN'}}
        Path(output).write_text(json.dumps(target))
        on_complete(target)
        return {'sample_count': 3}

    monkeypatch.setattr(acceptance.prepared_transfer, 'verify', verify)
    monkeypatch.setattr(acceptance, 'plan_file', sampling_plan)
    monkeypatch.setattr(acceptance, 'validate_capture', lambda *_: {'failures': []})
    monkeypatch.setattr(acceptance, 'compare', compare)
    monkeypatch.setattr(acceptance.persistence, 'audit', audit)
    monkeypatch.setattr(acceptance.persistence, '_loaded_level', lambda _: level)
    monkeypatch.setitem(sys.modules, 'unreal', SimpleNamespace(log=lambda _: None))
    monkeypatch.setitem(sys.modules, 'cinetwin_tick_evaluator', SimpleNamespace(start=begin))
    request = acceptance.start(tmp_path, job_id=job_id)
    folder = Path(request['evidence_folder'])
    comparison = json.loads((folder / 'comparison.json').read_text())
    assert comparison['acceptance_status'] == 'STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE'
    assert comparison['observation_editor_pid'] != comparison['generation_editor_pid']
    assert comparison['target_observation_sha256'] == acceptance.persistence._sha(folder / 'target-behavior.json')
