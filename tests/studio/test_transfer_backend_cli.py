"""Production prepare/verify workflow must round-trip unchanged JSON artifacts."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _rt(seconds):
    return {"value": int(seconds * 1000000),
            "rate": {"numerator": 1000000, "denominator": 1}}


def test_cli_unchanged_preparation_verifies_and_tampered_plan_blocks(tmp_path):
    csir = {
        "schema_version": "0.1.0", "cutscene_id": "cli-test",
        "source": {"engine": "unity"},
        "timing": {
            "source_rate": {"numerator": 24, "denominator": 1},
            "duration_seconds": 1.0,
        },
        "entities": [{
            "entity_id": "camera-1", "name": "CAM",
            "ced_type": "entity.camera",
            "metadata": {"camera": {"field_of_view_degrees": 50.0, "aspect": 1.777}},
        }],
        "assets": [],
        "tracks": [{
            "ced_type": "camera.cut", "track_id": "cut:1",
            "binding_entity_id": "camera-1",
            "sections": [{"start": _rt(0), "end": _rt(1), "payload": {}}],
        }],
    }
    mapping = {
        "entities": {"CAM": {"actor_label": "CAMUE"}},
        "assets": {},
        "sequence_asset_path": "/Game/Studio/LS_Test",
        "overwrite_sequence": False,
    }
    csir_file = tmp_path / "source.json"
    mapping_file = tmp_path / "mapping.json"
    csir_file.write_text(json.dumps(csir), encoding="utf-8")
    mapping_file.write_text(json.dumps(mapping), encoding="utf-8")
    folder = tmp_path / "plan"
    cmd = [
        sys.executable, str(ROOT / "tools" / "transfer_backend.py"),
        "--csir", str(csir_file),
        "--mapping", str(mapping_file),
        "--out", str(folder),
    ]
    first = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr
    coverage = json.loads((folder / "coverage-report.json").read_text(encoding="utf-8"))
    evidence = json.loads((folder / "evidence.json").read_text(encoding="utf-8"))
    plan_before = json.loads((folder / "transfer-plan.json").read_text(encoding="utf-8"))
    assert "ced_preflight" in coverage
    assert coverage["ced_preflight_status"] == "REVIEW_REQUIRED"
    assert coverage["ced_preflight"]["active_alert_count"] >= 1
    assert evidence["ced_sha256"] == plan_before["ced_registry"]["sha256"]
    assert evidence["ced_adapter_capabilities_sha256"] == (
        plan_before["ced_registry"]["adapter_capabilities_sha256"]
    )
    original_bytes = {
        name: (folder / name).read_bytes()
        for name in ("transfer-plan.json", "coverage-report.json", "evidence.json")
    }
    verify = subprocess.run(cmd + ["--verify-existing"],
                            capture_output=True, text=True, check=False)
    assert verify.returncode == 0, verify.stderr
    assert "PREPARED FILES: VERIFIED" in verify.stdout
    assert all((folder / name).read_bytes() == body for name, body in original_bytes.items())
    plan = json.loads((folder / "transfer-plan.json").read_text(encoding="utf-8"))
    plan["duration_frames"] += 1
    (folder / "transfer-plan.json").write_text(json.dumps(plan), encoding="utf-8")
    invalid = subprocess.run(cmd + ["--verify-existing"],
                             capture_output=True, text=True, check=False)
    assert invalid.returncode == 2
    assert "duration_frames" in invalid.stderr



def test_strict_ced_cli_blocks_unknown_before_creating_a_plan_directory(tmp_path):
    csir = {
        "schema_version": "0.1.0", "cutscene_id": "strict-unknown",
        "source": {"engine": "unity"},
        "timing": {"source_rate": {"numerator": 24, "denominator": 1},
                   "duration_seconds": 1.0},
        "entities": [{"entity_id": "cam", "name": "Cam",
                      "ced_type": "entity.camera",
                      "metadata": {"camera": {
                          "field_of_view_degrees": 60, "aspect": 1.777,
                      }}}],
        "assets": [],
        "tracks": [
            {"ced_type": "camera.cut", "track_id": "cut",
             "binding_entity_id": "cam",
             "sections": [{"ced_type": "camera.cut",
                           "start": _rt(0), "end": _rt(1), "payload": {}}]},
            {"ced_type": "timeline.track", "track_id": "new-user-track",
             "metadata": {"native_type": "creator.CustomCameraImpulseTrack"},
             "sections": [{"ced_type": "timeline.clip", "section_id": "c2",
                           "native_payload": {"native_asset_type": "creator.Clip"},
                           "start": _rt(0), "end": _rt(1), "payload": {}}]},
        ],
    }
    target = {
        "entities": {"Cam": {"actor_label": "CamUE"}},
        "assets": {},
        "sequence_asset_path": "/Game/Studio/LS_Strict",
        "overwrite_sequence": False,
    }
    source_file = tmp_path / "source.json"
    mapping_file = tmp_path / "mapping.json"
    folder = tmp_path / "never_created"
    source_file.write_text(json.dumps(csir), encoding="utf-8")
    mapping_file.write_text(json.dumps(target), encoding="utf-8")
    cmd = [sys.executable, str(ROOT / "tools" / "transfer_backend.py"),
           "--csir", str(source_file), "--mapping", str(mapping_file),
           "--out", str(folder), "--strict-ced"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert "CED strict preflight blocked" in result.stderr
    assert not folder.exists()
    assert not (tmp_path / "runtime-receipt.json").exists()
