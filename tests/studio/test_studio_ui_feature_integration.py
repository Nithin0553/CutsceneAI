"""Studio UI/API feature routing, scoped source evidence and saved-native audit integration."""
from __future__ import annotations

import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import studio_ui_features as feat
from test_studio_local_bridge import bridge, call, fixture_files


@pytest.fixture
def local_service(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("Studio UI")
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), bridge.create_handler(web, tmp_path / "work")
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:" + str(server.server_port), tmp_path
    server.shutdown()
    server.server_close()
    thread.join()


def _source_census(tmp_path):
    config = fixture_files(tmp_path)
    unity = tmp_path / "Unity"
    (unity / "Assets").mkdir(parents=True)
    export = unity / "CutSceneAI" / "Exports"
    export.mkdir(parents=True)
    src = json.loads(Path(config["csir"]).read_text())
    src["source"]["project_fingerprint"] = "right-project"
    src["source"]["engine_version"] = "2022.3.60f1"
    src["entities"][0]["entity_id"] = "camera-a"
    src["entities"][0]["metadata"] = {
        "scene_path": "Assets/Benchmark002.unity", "hierarchy_path": "Root/CAM_A"
    }
    Path(config["csir"]).write_text(json.dumps(src))
    census = export / "feature-surface-unity-match.json"
    census.write_text(json.dumps({
        "kind": "cutsceneai.engine.feature_surface",
        "schema_version": "0.2.0", "engine": "unity",
        "project_fingerprint": "right-project",
        "engine_version": "2022.3.60f1",
        "registered_types": [],
        "loaded_scene_components": [{
            "scene_path": "Assets/Benchmark002.unity",
            "object_path": "Root/CAM_A",
            "component_type": "UnityEngine.Camera",
            "component_global_id": "camera-a-1",
        }],
        "imported_assets": [],
    }))
    config.update({"unity_project": str(unity), "source_scope": "Assets"})
    return config, census


def test_capability_panel_uses_live_ced_and_builder_actions():
    stats = feat.capabilities()
    assert stats["catalog_version"] == "0.2.0"
    assert stats["feature_families"] == 39
    assert len(stats["families"]) == 39
    assert all(row["state"] == "CATALOGUED_NOT_TRANSFER_VERIFIED" for row in stats["families"])
    assert stats["semantic_elements"] >= 700
    assert "property_float" in stats["builder_actions"]
    assert "actor_visibility" in stats["builder_actions"]
    assert stats["full_conversion_verified"] is False


def test_source_census_scoped_to_same_connected_unity_project(tmp_path):
    config, census = _source_census(tmp_path)
    options = feat.source_surfaces(config)
    assert options["options"][0]["state"] == "MATCHED_COMPLETE"
    assert options["options"][0]["strict_ready"] is True
    approved = feat.validate_options(config, {
        "source_feature_surface_path": str(census),
        "require_complete_source_features": True,
        "enable_actor_visibility_fallback": True,
    })
    assert approved == {
        "source_feature_surface_path": str(census),
        "require_complete_source_features": True,
        "enable_actor_visibility_fallback": True,
    }
    outside = tmp_path / "random.json"
    outside.write_text(census.read_text())
    with pytest.raises(ValueError, match="connected Unity project"):
        feat.validate_options(config, {"source_feature_surface_path": str(outside)})
    with pytest.raises(ValueError, match="requires a matching"):
        feat.validate_options(config, {"require_complete_source_features": True})


def test_incomplete_census_may_be_reviewed_but_not_strictly_misrepresented(tmp_path):
    config, census = _source_census(tmp_path)
    saved = json.loads(census.read_text())
    saved["loaded_scene_components"].append({
        "scene_path": "Assets/Benchmark002.unity", "object_path": "Root/CAM_A",
        "component_type": "Vendor.CustomFX", "component_global_id": "vendor",
    })
    census.write_text(json.dumps(saved))
    opt = feat.source_surfaces(config)["options"][0]
    assert opt["state"] == "REVIEW_REQUIRED"
    assert opt["unresolved_components"] == 1
    assert opt["unresolved_findings"] == [{
        "native_type": "Vendor.CustomFX",
        "object_path": "Root/CAM_A",
        "scene_path": "Assets/Benchmark002.unity",
        "state": "NATIVE_COMPONENT_EXTRACTION_OR_ADAPTER_REQUIRED",
    }]
    with pytest.raises(ValueError, match="Strict source census"):
        feat.validate_options(config, {
            "source_feature_surface_path": str(census), "require_complete_source_features": True,
        })
    allowed = feat.validate_options(config, {
        "source_feature_surface_path": str(census),
        "require_complete_source_features": False,
    })
    assert allowed["require_complete_source_features"] is False


def test_capture_candidate_ui_options_apply_only_to_unique_mapping_copy(tmp_path, monkeypatch):
    config, census = _source_census(tmp_path)
    workspace = tmp_path / "runs"
    bridge.atomic_json(workspace / "connection.json", bridge.config_check(config))
    original = Path(config["mapping"]).read_bytes()

    def fake_prepare(csir, mapping, capture, seq, out, *,
                     skeletal_root_world_lock, hierarchy_transfer, transfer_options):
        assert transfer_options["source_feature_surface_path"] == str(census)
        assert transfer_options["enable_actor_visibility_fallback"] is True
        out.mkdir(parents=True)
        (out / "transfer-plan.json").write_text(json.dumps({
            "sequence_asset_path": seq, "actions": [],
        }))
        (out / "coverage-report.json").write_text(json.dumps({
            "feature_dispatch": {
                "catalog_semantic_count": 735, "catalog_family_count": 39,
                "source_occurrence_count": 2, "accounted_occurrence_count": 2,
                "missing_adapter_count": 1, "states": {"SOURCE_RECORDED_ADAPTER_MISSING": 1},
            },
            "source_feature_surface_state": "SOURCE_CENSUS_VERIFIED_NO_UNRESOLVED_COMPONENTS",
            "source_feature_surface": {"unresolved_component_count": 0},
        }))
        copied = out.with_suffix(".mapping.json")
        copied.write_text(json.dumps({**json.loads(Path(mapping).read_text()), **transfer_options}))
        return copied, {"track_coverage": {}, "ced_preflight": "REVIEW_REQUIRED"}

    monkeypatch.setitem(sys.modules, "studio_candidate", NS(prepare_candidate=fake_prepare))
    result = bridge.prepare(workspace, {
        "source_feature_surface_path": str(census),
        "require_complete_source_features": True,
        "enable_actor_visibility_fallback": True,
    })
    assert result["source_unresolved_components"] == 0
    assert result["feature_dispatch_summary"]["missing_adapters"] == 1
    assert result["feature_dispatch_summary"]["full_conversion_verified"] is False
    assert Path(config["mapping"]).read_bytes() == original
    assert result["prepared_options"]["source_feature_surface_path"] == str(census)


def test_source_only_candidate_ui_options_keep_original_mapping_unchanged(tmp_path, monkeypatch):
    config, census = _source_census(tmp_path)
    config["capture"] = ""
    workspace = tmp_path / "runs"
    bridge.atomic_json(workspace / "connection.json", bridge.config_check(config))
    baseline = Path(config["mapping"]).read_bytes()

    def fake_prepared(csir, mapping, out, *, target_project):
        copied = json.loads(Path(mapping).read_text())
        assert copied["source_feature_surface_path"] == str(census)
        assert copied["enable_actor_visibility_fallback"] is True
        assert copied["enable_cinetwin_hierarchy"] is True
        out.mkdir()
        (out / "transfer-plan.json").write_text('{"actions": []}')
        return {"track_coverage": {}, "ced_preflight": "REVIEW_REQUIRED"}

    monkeypatch.setitem(sys.modules, "prepared_transfer", NS(prepare=fake_prepared))
    result = bridge.prepare(workspace, {
        "source_feature_surface_path": str(census),
        "require_complete_source_features": True,
        "enable_actor_visibility_fallback": True,
    })
    assert result["engine_generation_executed"] is False
    assert Path(config["mapping"]).read_bytes() == baseline


def test_readonly_verification_reads_only_active_candidate_and_no_false_fidelity(tmp_path):
    workspace = tmp_path / "runs"
    jobid = "a" * 32
    candidate = workspace / "candidates" / "trial"
    candidate.mkdir(parents=True)
    (candidate / ("post-reopen-audit-" + jobid + ".json")).write_text(json.dumps({
        "kind": "cutsceneai.studio.persistence_audit",
        "status": "STRUCTURAL_READBACK_PASS_RESTART_UNVERIFIED",
        "native_structure_status": "PASS",
        "assets_class_and_disk_verified": 18, "asset_count": 18,
        "actors_unique_and_class_verified": 10, "actor_count": 10,
    }))
    (candidate / ("hierarchy-audit-" + jobid + "-01234567.json")).write_text(json.dumps({
        "kind": "cutsceneai.studio.hierarchy_persistence_audit",
        "status": "INCOMPLETE", "direct_parent_links_verified": 2,
        "direct_edges_verified": 2, "direct_edges_expected": 2,
        "unresolved_source_parents": [{}] * 8,
        "source_group_ancestors": ["Benchmark002", "CHARACTER_A", "CHARACTER_B"],
    }))
    result = feat.verification(workspace, {"job_id": jobid},
                               {"job_id": jobid, "candidate_dir": str(candidate)})
    assert result["persistence"]["assets"] == 18
    assert result["persistence"]["actors"] == 10
    assert result["hierarchy"]["parent_links"] == 2
    assert result["hierarchy"]["fully_checked"] == 2
    assert result["hierarchy"]["unresolved_source_parents"] == 8
    assert result["fidelity_verified"] is False


def test_new_readonly_localhost_endpoints_have_actual_ced_and_no_job(local_service):
    base, _tmp = local_service
    code, capabilities = call(base + "/api/capabilities")
    assert code == 200 and capabilities["semantic_elements"] >= 700
    code, sources = call(base + "/api/source-surfaces")
    assert code == 200 and not sources["available"]
    code, verification = call(base + "/api/verification")
    assert code == 200 and verification["persistence"] is None
    assert verification["hierarchy"] is None


def test_source_ui_static_wiring_and_benchmark_guidance():
    app = (ROOT / "apps" / "studio-web" / "app.js").read_text()
    assert "function featurePanel()" in app
    assert "function verificationPanel()" in app
    for part in ("api('capabilities')", "api('source-surfaces')", "api('verification')",
                 "enable_actor_visibility_fallback", "strict-source-census",
                 "source_feature_surface_path", "copy-audit-command",
                 "Benchmark002 regression", "2/2 direct",
                 "Inspect all", "Declared scalar property mappings",
                 "unresolved_findings", "exact source objects",
                 "Best-effort mode selected", "Strict mode will block"):
        assert part in app
