"""Studio transfer-handoff regression tests: no engine, no mutation, no false claims."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in ("packages/studio", "packages/learning", "packages/cinetwin", "integrations/unreal"):
    sys.path.insert(0, str(ROOT / folder))

import prepared_transfer


def fixture_files(tmp_path):
    rt = lambda sec: {"value": sec * 1000000,
                      "rate": {"numerator": 1000000, "denominator": 1}}
    source = {
        "schema_version": "0.1.0", "cutscene_id": "heldout-demo",
        "source": {"engine": "unity", "project_fingerprint": "project-x"},
        "timing": {"source_rate": {"numerator": 24, "denominator": 1},
                   "duration_seconds": 1.0},
        "entities": [{"entity_id": "cam", "name": "SourceCamera",
                      "ced_type": "entity.camera", "metadata": {"camera": {
                          "field_of_view_degrees": 60, "aspect": 1.777,
                      }}}],
        "assets": [],
        "tracks": [{"ced_type": "camera.cut", "track_id": "cut",
                    "binding_entity_id": "cam", "sections": [
                        {"ced_type": "camera.cut", "start": rt(0),
                         "end": rt(1), "payload": {}},
                    ]}],
    }
    mapping = {
        "entities": {"SourceCamera": {"actor_label": "TargetCamera"}},
        "assets": {}, "sequence_asset_path": "/Game/Studio/LS_New",
        "overwrite_sequence": False,
    }
    source_path = tmp_path / "source.json"
    mapping_path = tmp_path / "mapping.json"
    source_path.write_text(json.dumps(source), encoding="utf-8")
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
    return source_path, mapping_path


def test_end_to_end_pure_python_handoff_is_immutable_and_verifiable(tmp_path):
    source, mapping = fixture_files(tmp_path)
    before = (source.read_bytes(), mapping.read_bytes())
    out = tmp_path / "new"
    prepared = prepared_transfer.prepare(source, mapping, out)
    assert prepared["stage"] == "AWAITING_UNREAL_PREFLIGHT"
    assert prepared["engine_generation_executed"] is False
    assert prepared["asset_import_executed"] is False
    assert prepared["learning_applied"] is False
    assert prepared["target_readback_verified"] is False
    assert prepared["behavioral_fidelity_established"] is False
    assert prepared["track_coverage"]["NATIVE_UNVERIFIED"] == 1
    assert "ced_preflight" in json.loads((out / "coverage-report.json").read_text())
    assert prepared_transfer.verify(out) == prepared
    assert (source.read_bytes(), mapping.read_bytes()) == before
    with pytest.raises(prepared_transfer.PreparedTransferError, match="reuse"):
        prepared_transfer.prepare(source, mapping, out)


@pytest.mark.parametrize("filename", [
    "transfer-plan.json", "coverage-report.json", "evidence.json", "suggestions.json",
])
def test_tampered_artifacts_never_verify(tmp_path, filename):
    src, mapping = fixture_files(tmp_path)
    out = tmp_path / "fresh"
    prepared_transfer.prepare(src, mapping, out)
    (out / filename).write_text('{"tampered":true}', encoding="utf-8")
    with pytest.raises(prepared_transfer.PreparedTransferError, match="artifact"):
        prepared_transfer.verify(out)


def test_changed_source_and_mapping_are_rejected(tmp_path):
    for changed in ("source", "mapping"):
        root = tmp_path / changed
        root.mkdir()
        src, mapping = fixture_files(root)
        out = root / "fresh"
        prepared_transfer.prepare(src, mapping, out)
        path = src if changed == "source" else mapping
        path.write_text(path.read_text() + "\n", encoding="utf-8")
        with pytest.raises(prepared_transfer.PreparedTransferError, match="changed"):
            prepared_transfer.verify(out)


def test_unsafe_target_and_strict_ced_block_without_creating_folder(tmp_path):
    src, mapping = fixture_files(tmp_path)
    for bad in ("NotUnreal/Sequence", "/Game/../Bad"):
        document = json.loads(mapping.read_text())
        document["sequence_asset_path"] = bad
        mapping.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(prepared_transfer.PreparedTransferError, match="sequence"):
            prepared_transfer.prepare(src, mapping, tmp_path / "blocked")
        assert not (tmp_path / "blocked").exists()
    valid = json.loads(mapping.read_text())
    valid["sequence_asset_path"] = "/Game/Studio/LS_New"
    mapping.write_text(json.dumps(valid), encoding="utf-8")
    with pytest.raises(prepared_transfer.PreparedTransferError, match="strict transfer"):
        prepared_transfer.prepare(src, mapping, tmp_path / "strict", strict_ced=True)
    assert not (tmp_path / "strict").exists()


def test_prepared_summary_tampering_is_detected(tmp_path):
    src, mapping = fixture_files(tmp_path)
    out = tmp_path / "new"
    prepared_transfer.prepare(src, mapping, out)
    doc = json.loads((out / "session.json").read_text())
    doc["learning_applied"] = True
    (out / "session.json").write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(prepared_transfer.PreparedTransferError, match="cannot assert"):
        prepared_transfer.verify(out)
