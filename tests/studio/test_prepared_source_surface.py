"""Require source-identity-confirmed Unity component census during actual planning."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for prefix in ("integrations/unreal", "packages/cinetwin", "packages/studio"):
    sys.path.insert(0, str(ROOT / prefix))

import transfer_backend
from test_transfer_backend import mapping, source


def evidence_files(tmp_path):
    csir = source()
    csir["source"]["engine_version"] = "6000.1"
    csir["entities"][0]["metadata"] = {
        "scene_path": "Assets/Scenes/MyScene.unity", "hierarchy_path": "Scene/Prop",
        "world_transform": {
            "position": {"x": 0, "y": 0, "z": 0},
            "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
            "scale": {"x": 1, "y": 1, "z": 1},
        },
    }
    catalog = {
        "kind": "cutsceneai.engine.feature_surface", "schema_version": "0.2.0",
        "engine": "unity", "engine_version": "6000.1",
        "project_fingerprint": "proj-any",
        "registered_types": [{"full_name": "UnityEngine.Transform"}],
        "loaded_scene_components": [
            {"scene_path": "Assets/Scenes/MyScene.unity",
             "object_path": "Scene/Prop", "component_type": "UnityEngine.Transform",
             "component_global_id": "global-tr"},
        ],
        "imported_assets": [],
    }
    original = mapping()
    csir_path = tmp_path / "source.csir.json"
    census_path = tmp_path / "feature-surface.json"
    mapping_path = tmp_path / "mapping.json"
    csir_path.write_text(json.dumps(csir), encoding="utf-8")
    census_path.write_text(json.dumps(catalog), encoding="utf-8")
    original["source_feature_surface_path"] = "feature-surface.json"
    mapping_path.write_text(json.dumps(original), encoding="utf-8")
    return csir_path, mapping_path, census_path, csir, catalog, original


def test_source_census_is_reconciled_with_immutable_transfer_evidence(tmp_path):
    csir_path, map_path, surface_path, _csir, _surface, mapping_data = evidence_files(tmp_path)
    before = {file: file.read_bytes() for file in (csir_path, map_path, surface_path)}
    plan, report, evidence = transfer_backend.compose_files(csir_path, map_path)
    assert plan["actions"]
    assert report["source_feature_surface_state"] == (
        "SOURCE_CENSUS_VERIFIED_NO_UNRESOLVED_COMPONENTS"
    )
    assert report["source_feature_surface"]["project_identity_proven"] is True
    assert report["source_feature_surface"]["unresolved_component_count"] == 0
    assert evidence["source_feature_surface_sha256"] == hashlib.sha256(
        surface_path.read_bytes()).hexdigest()
    assert evidence["source_feature_surface_path"] == str(surface_path.resolve())
    assert mapping_data["source_feature_surface_path"] == "feature-surface.json"
    assert all(file.read_bytes() == data for file, data in before.items())


def test_custom_source_component_blocks_actual_transfer_before_unreal(tmp_path):
    src, target, surface, _csir, catalog, _mapping = evidence_files(tmp_path)
    catalog["loaded_scene_components"].append({
        "scene_path": "Assets/Scenes/MyScene.unity",
        "object_path": "Scene/Prop",
        "component_type": "MyCompany.SuperCameraShader",
        "component_global_id": "custom-shader",
    })
    surface.write_text(json.dumps(catalog))
    with pytest.raises(transfer_backend.TransferBackendError, match="census is incomplete"):
        transfer_backend.compose_files(src, target)


def test_feature_surface_wrong_source_project_blocks_actual_transfer(tmp_path):
    src, target, surface, _csir, catalog, _mapping = evidence_files(tmp_path)
    catalog["project_fingerprint"] = "wrong-unity-project"
    surface.write_text(json.dumps(catalog))
    with pytest.raises(transfer_backend.TransferBackendError, match="different source project"):
        transfer_backend.compose_files(src, target)


def test_missing_source_census_scene_scope_is_unsafe(tmp_path):
    src, target, surface, _csir, catalog, _mapping = evidence_files(tmp_path)
    catalog["loaded_scene_components"] = []
    surface.write_text(json.dumps(catalog))
    with pytest.raises(transfer_backend.TransferBackendError, match="census is incomplete"):
        transfer_backend.compose_files(src, target)


def test_explicit_best_effort_source_gap_preserves_unverified_report(tmp_path):
    src, target, surface, _csir, catalog, mapping_data = evidence_files(tmp_path)
    catalog["loaded_scene_components"].append({
        "scene_path": "Assets/Scenes/MyScene.unity",
        "object_path": "Scene/Prop",
        "component_type": "MyCompany.CustomCinematic",
        "component_global_id": "plugin-1",
    })
    mapping_data["require_complete_source_features"] = False
    target.write_text(json.dumps(mapping_data))
    surface.write_text(json.dumps(catalog))
    plan, report, evidence = transfer_backend.compose_files(src, target)
    assert plan["actions"]
    assert report["source_feature_surface_state"] == (
        "SOURCE_CENSUS_PARTIAL_EXPLICIT_REVIEW_REQUIRED"
    )
    assert report["source_feature_surface"]["unresolved_component_count"] == 1
    assert report["source_feature_surface"]["cutscene_completeness_verified"] is False
    assert evidence["source_feature_surface_sha256"]
    assert report["no_full_fidelity_claim"] is True


def test_changed_census_stale_plan_cannot_be_promoted_to_verification(tmp_path):
    src, target, surface, _csir, catalog, _mapping = evidence_files(tmp_path)
    plan, report, evidence = transfer_backend.compose_files(src, target)
    initial = copy.deepcopy(evidence)
    catalog["imported_assets"].append({
        "asset_path": "Assets/Unrelated.mat", "native_type": "UnityEngine.Material",
    })
    surface.write_text(json.dumps(catalog))
    recomputed = transfer_backend.compose_files(src, target)
    with pytest.raises(transfer_backend.TransferBackendError, match="provenance mismatch"):
        transfer_backend.verify_prepared_artifacts(
            plan, report, initial, *recomputed
        )


def test_unreal_builder_rechecks_census_hash_before_scene_mutation():
    code = (ROOT / "integrations" / "unreal" / "build_level_sequence.py"
            ).read_text(encoding="utf-8")
    assert 'surface_path = evidence.get("source_feature_surface_path")' in code
    assert '"Unity source component/feature census changed since preparation."' in code
