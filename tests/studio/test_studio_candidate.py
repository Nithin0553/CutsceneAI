"""Unique V9 trial preparation must never overwrite the original mapping or V8."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import studio_candidate


def test_candidate_copies_mapping_without_touching_original(tmp_path, monkeypatch):
    original = tmp_path / "original.json"
    original.write_text(json.dumps({
        "entities": {"CharacterA": {"actor_label": "CHARACTER_A"}},
        "assets": {}, "sequence_asset_path": "/Game/Test/LS_V8",
        "overwrite_sequence": False,
    }), encoding="utf-8")
    capture = tmp_path / "capture.json"
    capture.write_text("{}")
    csir = tmp_path / "source.json"
    csir.write_text("{}")
    original_contents = original.read_bytes()

    def fake_prepare(source, mapping, out, **kwargs):
        assert source == csir
        assert kwargs["capture_path"] == capture
        staged = json.loads(mapping.read_text())
        assert staged["sequence_asset_path"] == "/Game/Test/LS_V9"
        assert staged["overwrite_sequence"] is False
        assert staged["enable_cinetwin_skeletal_world_lock"] is True
        assert staged["entities"] == {"CharacterA": {"actor_label": "CHARACTER_A"}}
        out.mkdir()
        return {"track_coverage": {"NATIVE_PARTIAL": 1}}

    monkeypatch.setattr(studio_candidate.prepared_transfer, "prepare", fake_prepare)
    out = tmp_path / "V9_trial"
    mapping_copy, _session = studio_candidate.prepare_candidate(
        csir, original, capture, "/Game/Test/LS_V9", out,
        skeletal_root_world_lock=True,
    )
    assert mapping_copy.exists()
    assert original.read_bytes() == original_contents
    with pytest.raises(ValueError, match="reuse"):
        studio_candidate.prepare_candidate(
            csir, original, capture, "/Game/Test/LS_V9", out,
        )


def test_rejects_original_sequence_path_and_mapping_overwrite(tmp_path):
    original = tmp_path / "original.json"
    capture = tmp_path / "capture.json"
    capture.touch()
    original.write_text(json.dumps({
        "sequence_asset_path": "/Game/Level/Original",
        "overwrite_sequence": False,
    }))
    with pytest.raises(ValueError, match="original Level Sequence"):
        studio_candidate.prepare_candidate(
            tmp_path / "source", original, capture,
            "/Game/Level/Original", tmp_path / "trial",
        )
    original.write_text(json.dumps({
        "sequence_asset_path": "/Game/Level/Original",
        "overwrite_sequence": True,
    }))
    with pytest.raises(ValueError, match="overwrit"):
        studio_candidate.prepare_candidate(
            tmp_path / "source", original, capture,
            "/Game/Level/New", tmp_path / "trial",
        )
