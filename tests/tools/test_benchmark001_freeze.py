import hashlib
import json
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import benchmark001_freeze


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_freeze_manifest_requires_pass_and_hashes_artifacts(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source = tmp_path / "Benchmark001.csir.json"
    mapping = tmp_path / "mapping.json"
    target = tmp_path / "LS_Benchmark001.uasset"
    validation_dir = tmp_path / "validation"
    validation_dir.mkdir()
    expected = validation_dir / "Benchmark001.expected.json"
    readback = validation_dir / "Benchmark001.unreal.readback.json"
    report = validation_dir / "Benchmark001.validation.json"
    output = validation_dir / "Benchmark001.target-freeze.json"

    source.write_text('{"source":"test"}', encoding="utf-8")
    mapping.write_text('{"entities":{}}', encoding="utf-8")
    target.write_bytes(b"uasset")
    expected.write_text(
        '{"sequence_asset_path":"/Game/CutSceneAI/Benchmark001/LS_Benchmark001"}',
        encoding="utf-8",
    )
    readback.write_text(
        json.dumps(
            {
                "engine": {"name": "unreal", "version": "5.8.3"},
                "sequence_asset_path": "/Game/CutSceneAI/Benchmark001/LS_Benchmark001",
                "display_rate": {"numerator": 60, "denominator": 1},
                "playback": {"start_frame": 0, "end_frame": 600},
            }
        ),
        encoding="utf-8",
    )
    report.write_text(
        json.dumps(
            {
                "status": "PASS",
                "summary": {"passed": 54, "failed": 0, "incomplete": 0},
            }
        ),
        encoding="utf-8",
    )

    benchmark001_freeze.EXPECTED_SOURCE_SHA256 = _sha(source)

    manifest = benchmark001_freeze.create_manifest(
        repo_root=repo_root,
        source_csir=source,
        mapping=mapping,
        target_uasset=target,
        validation_dir=validation_dir,
        output_path=output,
    )

    assert manifest["status"] == "FROZEN_AUTOMATED_PASS"
    assert manifest["validation"]["summary"]["passed"] == 54
    assert manifest["target"]["sha256"] == _sha(target)
    assert output.is_file()


def test_freeze_refuses_nonpassing_validation(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source = tmp_path / "Benchmark001.csir.json"
    mapping = tmp_path / "mapping.json"
    target = tmp_path / "LS_Benchmark001.uasset"
    validation_dir = tmp_path / "validation"
    validation_dir.mkdir()

    source.write_text("source", encoding="utf-8")
    mapping.write_text("{}", encoding="utf-8")
    target.write_bytes(b"uasset")
    (validation_dir / "Benchmark001.expected.json").write_text("{}", encoding="utf-8")
    (validation_dir / "Benchmark001.unreal.readback.json").write_text("{}", encoding="utf-8")
    (validation_dir / "Benchmark001.validation.json").write_text(
        json.dumps(
            {
                "status": "FAIL",
                "summary": {"passed": 53, "failed": 1, "incomplete": 0},
            }
        ),
        encoding="utf-8",
    )

    benchmark001_freeze.EXPECTED_SOURCE_SHA256 = _sha(source)

    try:
        benchmark001_freeze.create_manifest(
            repo_root=repo_root,
            source_csir=source,
            mapping=mapping,
            target_uasset=target,
            validation_dir=validation_dir,
            output_path=validation_dir / "freeze.json",
        )
    except benchmark001_freeze.FreezeError as exc:
        assert "requires validation PASS" in str(exc)
    else:
        raise AssertionError("Expected FreezeError")
