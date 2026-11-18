"""The AI participates in *candidate planning*, not arbitrary native execution."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import studio_transfer_ai as ai


@pytest.fixture
def scene(tmp_path):
    source = tmp_path / "unity.csir.json"
    capture = tmp_path / "unity.capture.json"
    mapping = tmp_path / "target.mapping.json"
    census = tmp_path / "unity.census.json"
    project = tmp_path / "Target.uproject"
    source.write_text(json.dumps({
        "schema_version": "0.1.0", "cutscene_id": "exact-identity",
        "source": {"engine": "unity", "engine_version": "6000.3"},
        "timing": {
            "display_rate": {"numerator": 24, "denominator": 1},
            "playback_start": {"value": 0, "rate": {"numerator": 24, "denominator": 1}},
            "playback_end": {"value": 48, "rate": {"numerator": 24, "denominator": 1}},
        },
        "entities": [{
            "entity_id": "character-001", "name": "Character",
            "metadata": {
                "source_model_assets": [{"asset_path": "Assets/Characters/ch.fbx"}],
                "source_material_assets": [{"asset_path": "Assets/Mats/ch.mat"}],
            },
        }],
        "tracks": [{
            "ced_type": "event.state", "name": "Activation",
            "binding_entity_id": "character-001",
            "sections": [{
                "section_id": "clip-1",
                "start": {"value": 0, "rate": {"numerator": 24, "denominator": 1}},
                "end": {"value": 24, "rate": {"numerator": 24, "denominator": 1}},
                "payload": {"activation": {
                    "active": True, "post_playback_state": "Revert"
                }},
            }],
        }],
    }), encoding="utf-8")
    capture.write_text(json.dumps({
        "kind": "cinetwin.behavior_capture", "cutscene_id": "exact-identity",
        "samples": [{"frame": 0}],
    }), encoding="utf-8")
    mapping.write_text(json.dumps({
        "entities": {"Character": {"actor_label": "CSAI_Character"}},
        "sequence_asset_path": "/Game/CutSceneAI/Sequence",
        "overwrite_sequence": False,
    }), encoding="utf-8")
    census.write_text(json.dumps({"state": "MATCHED_COMPLETE"}), encoding="utf-8")
    project.write_text(json.dumps({
        "EngineAssociation": "5.8",
        "Plugins": [{"Name": "PythonScriptPlugin", "Enabled": True}],
    }), encoding="utf-8")
    config = {
        "csir": str(source), "capture": str(capture),
        "mapping": str(mapping), "target_project": str(project),
        "level_path": "/Game/AI_Test02", "auto_create_level": False,
    }
    worker = {
        "connected": True, "project": str(project),
        "level": "/Game/AI_Test02", "worker_version": "studio-editor-v0.6",
        "scene_inventory": {
            "available": True, "actor_count": 6,
            "class_counts": {"CineCameraActor": 2, "SkeletalMeshActor": 2,
                             "DirectionalLight": 2},
            "truncated": False,
        },
    }
    return config, str(census), worker


def test_ai_analyzes_both_projects_and_gates_partial_native_adapter(scene):
    config, census, worker = scene
    evidence = ai.inspect(config, census, worker)
    summary = evidence["summary"]
    assert summary["source_track_types"]["event.state"] == 1
    assert summary["source_capture_sample_count"] == 1
    assert summary["target_project_metadata"]["engine_association"] == "5.8"
    assert summary["target_connected"] is True
    assert summary["target_level_actor_count"] == 6
    assert summary["target_level_actor_class_counts"]["CineCameraActor"] == 2
    assert summary["safe_partial_visibility_adapter_available"] is True
    assert "visual_activation_partial" in evidence["allowed_strategies"]
    decision = ai.decide(config, census, worker, reasoner=lambda _: {
        "strategy": "visual_activation_partial",
        "reason": "Source ActivationTrack may use a visual-only partial adapter.",
    })
    opts = ai.verify(decision, config, census, worker)
    assert opts == {
        "enable_fbx_embedded_material_import": True,
        "enable_actor_visibility_fallback": True,
    }
    assert decision["activation_semantics_partial"] is True
    assert decision["source_and_target_fidelity_verified"] is False
    assert decision["native_conversion_executed"] is False
    assert "uproject" in decision["input_sha256"]


def test_ai_cannot_invent_strategy_or_bypass_source_provenance(scene):
    config, census, worker = scene
    with pytest.raises(ai.TransferAIError, match="unregistered"):
        ai.decide(config, census, worker, reasoner=lambda _: {
            "strategy": "arbitrary_native_python", "reason": "Invent this"
        })
    chosen = ai.decide(config, census, worker, reasoner=lambda _: {
        "strategy": "native_source", "reason": "Native conservative plan"
    })
    # Source material provenance is a deterministic floor regardless of model.
    assert chosen["conversion_options"]["enable_fbx_embedded_material_import"] is True
    assert chosen["conversion_options"]["enable_actor_visibility_fallback"] is False
    source_path = Path(config["csir"])
    mutated = json.loads(source_path.read_text(encoding="utf-8"))
    mutated["source"]["engine_version"] = "modified-with-same-source-id"
    source_path.write_text(json.dumps(mutated), encoding="utf-8")
    with pytest.raises(ai.TransferAIError, match="stale"):
        ai.verify(chosen, config, census, worker)


def test_real_target_identity_is_required_without_name_only_guessing(scene, tmp_path):
    config, census, worker = scene
    wrong = dict(worker, project=str(tmp_path / "Another" / "Target.uproject"))
    with pytest.raises(ai.TransferAIError, match="selected target"):
        ai.inspect(config, census, wrong)
    wrong_level = dict(worker, level="/Game/Unrelated")
    with pytest.raises(ai.TransferAIError, match="selected target"):
        ai.inspect(config, census, wrong_level)
    disconnected = dict(worker, connected=False)
    with pytest.raises(ai.TransferAIError, match="selected target"):
        ai.inspect(config, census, disconnected)
    missing_inventory = dict(worker, scene_inventory=None)
    with pytest.raises(ai.TransferAIError, match="level inventory"):
        ai.inspect(config, census, missing_inventory)


def test_partial_adapter_requires_actually_valid_activation_clips(scene):
    config, census, worker = scene
    csir_path = Path(config["csir"])
    document = json.loads(csir_path.read_text())
    document["tracks"][0]["sections"][0]["payload"]["activation"]["active"] = False
    csir_path.write_text(json.dumps(document), encoding="utf-8")
    evidence = ai.inspect(config, census, worker)
    assert "visual_activation_partial" not in evidence["allowed_strategies"]
    with pytest.raises(ai.TransferAIError, match="not supported"):
        ai.decide(config, census, worker, reasoner=lambda _: {
            "strategy": "visual_activation_partial", "reason": "Ignore eligibility"
        })


def test_source_only_redacted_summary_passed_to_llm(scene, monkeypatch):
    config, census, worker = scene
    evidence = ai.inspect(config, census, worker)
    received = {}
    def call(**kwargs):
        received.update(kwargs)
        return SimpleNamespace(output_text=json.dumps({
            "strategy": "source_materials", "reason": "Source renderer material references",
        }))
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-only")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(
        OpenAI=lambda **kwargs: SimpleNamespace(
            responses=SimpleNamespace(create=call))
    ))
    result = ai._model_choose(evidence)
    assert result["strategy"] == "source_materials"
    assert received["text"]["format"]["strict"] is True
    assert set(received["text"]["format"]["schema"]["properties"]) == {"strategy", "reason"}
    assert config["csir"] not in received["input"]
    assert config["target_project"] not in received["input"]
    assert "unit-test-only" not in received["input"]


def test_missing_api_key_blocks_ai_pretransfer_not_silent_native_fallback(scene, monkeypatch):
    config, census, worker = scene
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ai.TransferAIError, match="OPENAI_API_KEY"):
        ai.decide(config, census, worker)


def test_project_config_changes_invalidate_prepared_ai_decision(scene):
    config, census, worker = scene
    decision = ai.decide(config, census, worker, reasoner=lambda _: {
        "strategy": "native_source", "reason": "Use installed source-backed handlers"
    })
    assert ai.verify(decision, config, census, worker)[
        "enable_actor_visibility_fallback"] is False
    project = Path(config["target_project"])
    project.write_text('{"EngineAssociation": "5.9"}', encoding="utf-8")
    with pytest.raises(ai.TransferAIError, match="stale"):
        ai.verify(decision, config, census, worker)
