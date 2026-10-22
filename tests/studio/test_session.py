"""Studio sessions never assume a successful in-engine conversion."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for directory in (
    ROOT / "packages" / "studio", ROOT / "packages" / "learning",
    ROOT / "packages" / "cinetwin", ROOT / "integrations" / "unreal",
):
    sys.path.insert(0, str(directory))

import session


def source(*, unsupported=False):
    tracks = []
    if unsupported:
        tracks.append({
            "track_id": "custom", "ced_type": "shader.custom",
            "binding_entity_id": "unknown", "sections": [
                {"section_id": "shader", "ced_type": "shader", "payload": {}}
            ],
        })
    return {
        "cutscene_id": "arbitrary-demo",
        "source": {"engine": "unity", "project_fingerprint": "source-1"},
        "timing": {"source_rate": {"numerator": 24, "denominator": 1},
                   "duration_seconds": 5.0},
        "entities": [],
        "assets": [],
        "tracks": tracks,
    }


def mapping(*, overwrite=False):
    return {
        "entities": {}, "assets": {},
        "sequence_asset_path": "/Game/Staging/GeneratedCutscene",
        "overwrite_sequence": overwrite,
    }


def files(tmp_path, *, unsupported=False, overwrite=False):
    src, target = tmp_path / "source.json", tmp_path / "mapping.json"
    src.write_text(json.dumps(source(unsupported=unsupported)), encoding="utf-8")
    target.write_text(json.dumps(mapping(overwrite=overwrite)), encoding="utf-8")
    return src, target


def test_studio_session_prepares_read_only_plan_without_engine(tmp_path):
    src, target = files(tmp_path)
    original_csir = src.read_bytes()
    report = session.prepare(src, target, tmp_path / "out")
    assert report["stage"] == "AWAITING_REAL_ENGINE_PREFLIGHT"
    assert report["engine_generation_executed"] is False
    assert report["behavioral_fidelity_established"] is False
    assert report["training_example_approved"] is False
    assert (tmp_path / "out" / "transfer-plan.json").is_file()
    assert src.read_bytes() == original_csir
    assert report == session.prepare(src, target, tmp_path / "out")


def test_unsupported_shader_blocks_before_engine_invocation(tmp_path):
    src, target = files(tmp_path, unsupported=True)
    report = session.prepare(src, target, tmp_path / "out")
    assert report["stage"] == "BLOCKED_SOURCE_COVERAGE"
    assert not (tmp_path / "out" / "transfer-plan.json").exists()
    readiness = json.loads((tmp_path / "out" / "readiness.json").read_text())
    assert readiness["counts"]["BLOCKED"] == 1


def test_overwrite_mapping_refused_for_staging(tmp_path):
    src, target = files(tmp_path, overwrite=True)
    with pytest.raises(session.StudioError, match="overwrite_sequence"):
        session.prepare(src, target, tmp_path / "out")
    assert not (tmp_path / "out" / "session.json").exists()


def test_reusing_session_directory_with_different_source_fails(tmp_path):
    src, target = files(tmp_path)
    session.prepare(src, target, tmp_path / "out")
    src.write_text(json.dumps(source() | {"cutscene_id": "changed"}), encoding="utf-8")
    with pytest.raises(session.StudioError, match="conflicting"):
        session.prepare(src, target, tmp_path / "out")


def test_mapping_proposals_only_never_auto_apply(tmp_path):
    src, target = files(tmp_path)
    case = {
        "case_id": "verified-1",
        "status": "MAPPING_VERIFIED",
        "source": {"engine": "unity"},
        "target": {"engine": "unreal"},
        "features": ["entity:entity.prop"],
        "mapping_labels": [{"ced": "transform.position",
                            "resolver": "verified-map",
                            "outcome": "CONVERTED", "parameters": {}}],
    }
    doc = source()
    doc["entities"] = [{"entity_id": "prop", "name": "Prop",
                        "ced_type": "entity.prop"}]
    src.write_text(json.dumps(doc), encoding="utf-8")
    report = session.prepare(src, target, tmp_path / "out", verified_cases=[case])
    proposals = json.loads((tmp_path / "out" / "suggestions.json").read_text())
    assert report["proposed_mapping_cases"] == 1
    assert proposals["auto_applied"] is False
    assert proposals["suggestions"][0]["proposal_only"] is True
