"""Fresh-target source asset preparation, no native Unreal runtime required."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import studio_fresh_target_assets as stage


def fixture(tmp_path):
    source = tmp_path / "Unity"
    scope = source / "Assets" / "CutSceneAI" / "Scene42"
    (scope / "Characters" / "Textures").mkdir(parents=True)
    (scope / "Characters" / "Ch31.fbm").mkdir()
    (scope / "Animations").mkdir()
    (scope / "Audio").mkdir()
    (scope / "Characters" / "Ch31.fbx").write_bytes(b"pretend-fbx-character")
    (scope / "Animations" / "Walking.fbx").write_bytes(b"pretend-fbx-anim")
    png_bytes = stage.PNG_SIGNATURE + b"test-data"
    (scope / "Characters" / "Textures" / "Ch31_Diffuse.png").write_bytes(png_bytes)
    (scope / "Characters" / "Ch31.fbm" / "Ch31_Diffuse.png").write_bytes(png_bytes)
    (scope / "Audio" / "Cue.mp3").write_bytes(b"pretend-mp3")
    csir = tmp_path / "source.csir.json"
    csir.write_text(json.dumps({"schema_version": "0.1.0", "source": {"engine": "unity"},
                                "entities": [{"ced_type": "entity.character", "name": "Ch31"}]}))
    project = tmp_path / "NewTarget.uproject"
    project.write_text("{}")
    opts = {"csir": csir, "source_project": source,
            "scope": "Assets/CutSceneAI/Scene42", "target_project": project,
            "target_folder": "/Game/CutSceneAI/TestRun_001"}
    return opts, scope


def test_composes_import_candidates_dedupes_texture_and_defers_animation(tmp_path):
    opts, _ = fixture(tmp_path)
    obj = stage.compose(**opts)
    statuses = obj["status_counts"]
    assert statuses == {
        "CANDIDATE_SKELETAL_MODEL_UNVERIFIED": 1,
        "CANDIDATE_TEXTURE_UNVERIFIED": 1,
        "DEFERRED_MP3_TO_WAV": 1,
        "DEFERRED_SKELETON_COMPATIBILITY": 1,
        "DUPLICATE_CONTENT": 1,
    }
    assert not obj["engine_import_executed"]
    candidates = [x for x in obj["files"] if x["target_asset_path"]]
    assert len(candidates) == 2
    assert len(set(x["target_asset_path"] for x in candidates)) == 2


def test_manifest_is_byte_stable_and_source_tamper_fails(tmp_path):
    opts, scope = fixture(tmp_path)
    out = tmp_path / "plan.json"
    out.write_text(stage._canonical_json(stage.compose(**opts)))
    assert stage.verify(out) == stage.compose(**opts)
    (scope / "Characters" / "Ch31.fbx").write_bytes(b"changed")
    with pytest.raises(stage.FreshTargetError, match="changed"):
        stage.verify(out)


def test_blocks_unsafe_scope_bad_target_and_plan_overwrite(tmp_path):
    opts, _ = fixture(tmp_path)
    with pytest.raises(stage.FreshTargetError, match="Scope"):
        stage.compose(**{**opts, "scope": "../outside"})
    with pytest.raises(stage.FreshTargetError, match="Destination"):
        stage.compose(**{**opts, "target_folder": "/Game/../unsafe"})
    out = tmp_path / "done.json"
    out.write_text("do not replace")
    rc = stage.main(["plan", "--csir", str(opts["csir"]),
                     "--source-project", str(opts["source_project"]),
                     "--scope", opts["scope"],
                     "--target-project", str(opts["target_project"]),
                     "--target-folder", opts["target_folder"],
                     "--out", str(out)])
    assert rc == 2
    assert out.read_text() == "do not replace"
