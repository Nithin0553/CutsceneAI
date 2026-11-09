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
    assert result["unresolved_component_count"] == 1
    assert result["component_counts"]["OTHER_LOADED_SCENE_COMPONENT"] == 1
    assert result["source_scope_matched"] is False
    assert result["component_counts"]["SOURCE_OBJECT_TRANSFORM_NOT_VERIFIED"] == 1
    assert result["missing_cutscene_objects"][0]["hierarchy_path"] == "S/Camera"


def test_partial_census_cannot_claim_all_cutscene_objects_were_scanned():
    csir, census = _fixtures()
    csir["entities"].append({
        "entity_id": "scene.sibling", "name": "Sibling",
        "metadata": {"scene_path": "Assets/Scenes/S.unity",
                     "hierarchy_path": "S/Sibling"},
    })
    census["loaded_scene_components"] = [
        row for row in census["loaded_scene_components"]
        if row["component_type"] != "MyGame.CustomFX"
    ]
    report = source_surface_gap.audit(csir, census)
    assert report["verified_cutscene_objects"] == 1
    assert report["source_scope_matched"] is False
    assert report["unresolved_component_count"] == 1
    assert report["missing_cutscene_objects"] == [{
        "scene_path": "Assets/Scenes/S.unity", "hierarchy_path": "S/Sibling",
        "source_entity_id": "scene.sibling",
        "state": "SOURCE_OBJECT_TRANSFORM_NOT_VERIFIED",
    }]


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


def test_project_fingerprint_mismatch_is_blocked_before_preparation():
    csir, census = _fixtures()
    csir["source"]["project_fingerprint"] = "unity-project-original"
    census["project_fingerprint"] = "unity-project-different"
    try:
        source_surface_gap.audit(csir, census)
    except source_surface_gap.SourceSurfaceGapError as exc:
        assert "different source project" in str(exc)
    else:
        raise AssertionError("The source census was accepted for a wrong Unity project.")


def test_matching_source_project_is_explicit_evidence_not_parity():
    csir, census = _fixtures()
    csir["source"]["project_fingerprint"] = "unity-project-abc"
    census["project_fingerprint"] = "unity-project-abc"
    result = source_surface_gap.audit(csir, census)
    assert result["project_identity_proven"] is True
    assert result["source_scope_matched"] is True
    assert result["parity_verified"] is False


def test_source_engine_version_mismatch_blocks_census():
    csir, census = _fixtures()
    csir["source"]["engine_version"] = "6000.0"
    with __import__("pytest").raises(
        source_surface_gap.SourceSurfaceGapError, match="version differs"
    ):
        source_surface_gap.audit(csir, census)


def test_same_hierarchy_path_with_different_unity_object_id_blocks_strict_census():
    csir, census = _fixtures()
    csir['source']['project_fingerprint'] = 'same-project'
    census['project_fingerprint'] = 'same-project'
    csir['entities'][0]['native_ref'] = 'GlobalObjectId_V1-1-REAL'
    for component in census['loaded_scene_components'][:3]:
        component['global_object_id'] = 'GlobalObjectId_V1-1-REPLACEMENT'
    report = source_surface_gap.audit(csir, census)
    assert report['source_scope_matched'] is False
    assert report['unresolved_component_count'] >= 3
    assert report['component_counts']['SOURCE_OBJECT_IDENTITY_MISMATCH'] == 3


def test_cli_strict_rejects_missing_project_provenance_even_if_components_known(tmp_path):
    csir, surface = _fixtures()
    surface["loaded_scene_components"] = [
        row for row in surface["loaded_scene_components"]
        if row["component_type"] in {"UnityEngine.Transform", "UnityEngine.Camera"}
    ]
    csir_path = tmp_path / "src.json"
    surface_path = tmp_path / "census.json"
    output = tmp_path / "report.json"
    csir_path.write_text(json.dumps(csir))
    surface_path.write_text(json.dumps(surface))
    result = subprocess.run([
        sys.executable,
        str(ROOT / "tools" / "studio_source_surface_gap.py"),
        "--csir", str(csir_path),
        "--source-surface", str(surface_path),
        "--out", str(output),
        "--strict",
    ], capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert "provenance incomplete" in result.stderr
    record = json.loads(output.read_text())
    assert record["unresolved_component_count"] == 0
    assert record["project_identity_proven"] is False



def _benchmark002_partial_component_rows():
    """Mirrors source-side CaptureComponent contracts for the reported 7 types."""
    base = {
        "scene_path": "Assets/Scenes/S.unity",
        "object_path": "S/Camera",
        "global_object_id": "object-one",
    }
    vector = {"x": 0.0, "y": 0.0, "z": 0.0}
    quaternion = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
    snapshots = [
        ("UnityEngine.SphereCollider", {
            "extraction": "STATIC_COLLIDER_WORLD_SHAPE_CANDIDATE",
            "shape": "sphere", "has_geometry": True,
            "enabled": True, "is_trigger": False,
            "world_center_m": vector, "world_rotation_xyzw": quaternion,
            "world_radius_m": 0.5,
            "collider_scale_policy": "UNITY_SPHERE_MAX_AXIS_LOSSY_SCALE",
        }),
        ("UnityEngine.BoxCollider", {
            "extraction": "STATIC_COLLIDER_WORLD_SHAPE_CANDIDATE",
            "shape": "box", "has_geometry": True,
            "enabled": True, "is_trigger": False,
            "world_center_m": vector, "world_rotation_xyzw": quaternion,
            "world_size_m": {"x": 2.0, "y": 1.0, "z": 1.0},
            "collider_scale_policy": "LOSSY_SCALE_NO_SHEAR_PROOF",
        }),
        *[("UnityEngine.Rendering.Universal.UniversalAdditionalCameraData", {
            "extraction": "URP_CAMERA_PROPERTIES_PARTIAL",
            "has_render_post_processing": True, "render_post_processing": True,
            "native_properties": [{"path": "m_RenderPostProcessing",
                                   "native_type": "bool", "bool_value": True}],
        }) for _ in range(3)],
        ("UnityEngine.Rendering.Universal.UniversalAdditionalLightData", {
            "extraction": "URP_LIGHT_PROPERTIES_PARTIAL",
            "has_use_pipeline_settings": True,
            "use_pipeline_settings": True,
        }),
        ("UnityEngine.Timeline.SignalReceiver", {
            "extraction": "SIGNAL_REACTIONS_INSPECTED_NO_TARGET_EVENT_BINDING",
            "signal_reaction_count": 1,
            "signal_reactions": ["GlobalObjectId_V1-1-EXACT:OnSignal"],
        }),
    ]
    return [
        {**base, "component_type": native_type,
         "component_global_id": "source-component-" + str(index),
         "feature": {**feature, "native_properties_truncated": False}}
        for index, (native_type, feature) in enumerate(snapshots)
    ]


def test_benchmark002_seven_captured_component_types_are_not_unextracted():
    csir, census = _fixtures()
    census["loaded_scene_components"] = [
        row for row in census["loaded_scene_components"]
        if row["component_type"] in {"UnityEngine.Transform", "UnityEngine.Camera"}
    ] + _benchmark002_partial_component_rows()
    result = source_surface_gap.audit(csir, census)
    assert result["source_scope_matched"] is True
    assert result["unresolved_component_count"] == 0
    assert result["source_snapshot_partial_count"] == 7
    assert result["component_counts"][
        "SOURCE_COMPONENT_SNAPSHOT_PARTIAL_TARGET_UNVERIFIED"
    ] == 7
    assert all(row["target_native_verified"] is False
               and row["behavior_verified"] is False
               for row in result["source_snapshot_partial_findings"])
    assert result["parity_verified"] is False
    assert result["cutscene_completeness_verified"] is False


def test_partial_source_capture_must_have_correct_type_and_untruncated_evidence():
    import copy

    csir, census = _fixtures()
    census["loaded_scene_components"] = [
        row for row in census["loaded_scene_components"]
        if row["component_type"] in {"UnityEngine.Transform", "UnityEngine.Camera"}
    ]
    original = _benchmark002_partial_component_rows()[0]
    invalids = [
        {**original, "feature": {}},
        {**original, "component_global_id": ""},
        {**original, "feature": {
            **original["feature"], "native_properties_truncated": True,
        }},
        {**original, "feature": {
            **original["feature"], "native_properties_truncated": None,
        }},
        {**original, "feature": {
            **original["feature"], "shape": "unknown",
        }},
        {**original, "feature": {
            **original["feature"], "world_radius_m": float("nan"),
        }},
        {**original, "feature": {
            **original["feature"], "world_center_m": {"x": "bad", "y": 0, "z": 0},
        }},
        {**original, "component_type": "Vendor.CustomCollider"},
    ]
    for row in invalids:
        invalid_census = copy.deepcopy(census)
        invalid_census["loaded_scene_components"].append(row)
        result = source_surface_gap.audit(csir, invalid_census)
        assert result["unresolved_component_count"] == 1
        assert result["source_snapshot_partial_count"] == 0
        assert result["component_counts"][
            "NATIVE_COMPONENT_EXTRACTION_OR_ADAPTER_REQUIRED"
        ] == 1


def test_malformed_signal_and_empty_urp_evidence_do_not_get_source_credit():
    csir, census = _fixtures()
    census["loaded_scene_components"] = [
        row for row in census["loaded_scene_components"]
        if row["component_type"] in {"UnityEngine.Transform", "UnityEngine.Camera"}
    ]
    for native_type, feature in [
        ("UnityEngine.Timeline.SignalReceiver", {
            "extraction": "SIGNAL_REACTIONS_INSPECTED_NO_TARGET_EVENT_BINDING",
            "signal_reaction_count": 3,
            "signal_reactions": ["only-one"],
        }),
        ("UnityEngine.Rendering.Universal.UniversalAdditionalCameraData", {
            "extraction": "URP_CAMERA_PROPERTIES_PARTIAL",
        }),
        ("UnityEngine.Rendering.Universal.UniversalAdditionalLightData", {
            "extraction": "URP_LIGHT_PROPERTIES_PARTIAL",
        }),
    ]:
        surface = dict(census)
        surface["loaded_scene_components"] = census["loaded_scene_components"] + [{
            "scene_path": "Assets/Scenes/S.unity", "object_path": "S/Camera",
            "component_type": native_type,
            "component_global_id": "component-1",
            "feature": {**feature, "native_properties_truncated": False},
        }]
        result = source_surface_gap.audit(csir, surface)
        assert result["unresolved_component_count"] == 1
        assert result["source_snapshot_partial_count"] == 0
