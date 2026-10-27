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
