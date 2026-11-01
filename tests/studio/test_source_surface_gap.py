"""Real source component gap detection tests: no missing script silently converted."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "studio"))
import source_surface_gap


def _fixtures():
    csir = {
        "source": {"engine": "unity"}, "cutscene_id": "C",
        "entities": [
            {"entity_id": "scene.cam", "name": "CAM", "ced_type": "entity.camera",
             "metadata": {
                 "scene_path": "Assets/Scenes/S.unity",
                 "hierarchy_path": "S/Camera"}},
        ],
        "assets": [{"asset_id": "img", "name": "Texture",
                    "metadata": {"asset_path": "Assets/Texture.png"}}],
    }
    census = {
        "kind": "cutsceneai.engine.feature_surface", "engine": "unity",
        "schema_version": "0.2.0", "engine_version": "2022.3.62f1",
        "registered_types": [
            {"full_name": "UnityEngine.Transform"},
            {"full_name": "MyGame.CustomFX"},
        ],
        "loaded_scene_components": [
            {"scene_path": "Assets/Scenes/S.unity", "object_path": "S/Camera",
             "component_global_id": "transform-a", "component_type": "UnityEngine.Transform"},
            {"scene_path": "Assets/Scenes/S.unity", "object_path": "S/Camera",
             "component_global_id": "camera-a", "component_type": "UnityEngine.Camera"},
            {"scene_path": "Assets/Scenes/S.unity", "object_path": "S/Camera",
             "component_global_id": "script-a", "component_type": "MyGame.CustomFX"},
            {"scene_path": "Assets/Scenes/S.unity", "object_path": "S/Unrelated",
             "component_global_id": "u-a", "component_type": "MyGame.Unrelated"},
        ],
        "imported_assets": [
            {"asset_path": "Assets/Texture.png", "native_type": "UnityEngine.Texture2D"},
            {"asset_path": "Assets/Unused.fbx", "native_type": "UnityEngine.Mesh"},
        ],
    }
    return csir, census


def test_loaded_project_custom_component_is_reported_as_source_gap():
    csir, surface = _fixtures()
    result = source_surface_gap.audit(csir, surface)
    assert result["indexed_cutscene_entities"] == 1
    assert result["scoped_component_occurrences"] == 3
    assert result["unresolved_component_count"] == 1
    assert result["component_counts"]["SOURCE_OBJECT_TRANSFORM_IDENTIFIED"] == 1
    assert result["component_counts"]["SOURCE_COMPONENT_SEMANTIC_REQUIRES_TARGET_EVIDENCE"] == 1
    assert result["component_counts"]["NATIVE_COMPONENT_EXTRACTION_OR_ADAPTER_REQUIRED"] == 1
    assert result["source_assets_matched_by_path"] == 1
    assert result["other_project_asset_type_counts"] == {"UnityEngine.Mesh": 1}
    assert result["cutscene_completeness_verified"] is False


def test_missing_script_and_nested_components_are_never_hidden():
    csir, surface = _fixtures()
    surface["loaded_scene_components"].append({
        "scene_path": "Assets/Scenes/S.unity", "object_path": "S/Camera/Child",
        "component_global_id": "", "component_type": "MISSING_MONOBEHAVIOUR_SCRIPT",
        "missing_script": True,
    })
    result = source_surface_gap.audit(csir, surface)
    assert result["unresolved_component_count"] == 2
    assert result["component_counts"]["MISSING_SOURCE_SCRIPT"] == 1


def test_unrelated_scene_and_asset_classes_do_not_falsely_block():
    csir, surface = _fixtures()
    surface["loaded_scene_components"] = [
        {"scene_path": "Assets/Other.unity", "object_path": "Elsewhere",
         "component_type": "Another.Plugin"},
    ]
    result = source_surface_gap.audit(csir, surface)
    assert result["unresolved_component_count"] == 0
    assert result["component_counts"]["OTHER_LOADED_SCENE_COMPONENT"] == 1


def test_invalid_or_wrong_engine_census_is_rejected():
    csir, surface = _fixtures()
    surface["engine"] = "unreal"
    try:
        source_surface_gap.audit(csir, surface)
    except source_surface_gap.SourceSurfaceGapError as exc:
        assert "non-Unity" in str(exc)
    else:
        raise AssertionError("Non-Unity feature surface was accepted.")


def test_cli_strict_blocks_custom_script_without_editing_source(tmp_path):
    csir, surface = _fixtures()
    source_path, census_path, report_path = (
        tmp_path / "source.json", tmp_path / "surface.json", tmp_path / "report.json"
    )
    source_path.write_text(json.dumps(csir), encoding="utf-8")
    census_path.write_text(json.dumps(surface), encoding="utf-8")
    initial = source_path.read_bytes()
    command = [
        sys.executable, str(ROOT / "tools" / "studio_source_surface_gap.py"),
        "--csir", str(source_path), "--source-surface", str(census_path),
        "--out", str(report_path), "--strict",
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    assert first.returncode == 2
    assert "Strict source extraction: BLOCKED" in first.stderr
    assert source_path.read_bytes() == initial
    assert report_path.is_file()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert len(payload["source_csir_sha256"]) == 64
    assert len(payload["source_surface_sha256"]) == 64
    again = subprocess.run(command, capture_output=True, text=True, check=False)
    assert again.returncode != 0
    assert "Refusing to overwrite" in again.stderr
