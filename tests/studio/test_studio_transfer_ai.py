"""The AI participates in *candidate planning*, not arbitrary native execution."""
from __future__ import annotations

import copy
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
            "native_capabilities": {
                "fbx_asset_import": True,
                "sequencer_visibility_track": True,
                "sequencer_skeletal_animation_track": True,
                "cine_camera_actor": True,
            },
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
    assert summary["target_native_capabilities"]["fbx_asset_import"] is True
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


def test_ai_rejects_unreal_unsupported_native_conversion_options(scene):
    config, census, worker = scene
    disabled = dict(worker, scene_inventory={
        **worker["scene_inventory"],
        "native_capabilities": {
            **worker["scene_inventory"]["native_capabilities"],
            "sequencer_visibility_track": False,
        },
    })
    data = ai.inspect(config, census, disabled)
    assert "visual_activation_partial" not in data["allowed_strategies"]
    with pytest.raises(ai.TransferAIError, match="not supported"):
        ai.decide(config, census, disabled, reasoner=lambda _: {
            "strategy": "visual_activation_partial", "reason": "Unsupported"
        })
    no_importer = dict(worker, scene_inventory={
        **worker["scene_inventory"],
        "native_capabilities": {
            **worker["scene_inventory"]["native_capabilities"],
            "fbx_asset_import": False,
        },
    })
    with pytest.raises(ai.TransferAIError, match="FBX import capability"):
        ai.inspect(config, census, no_importer)


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
    monkeypatch.setenv("CUTSCENEAI_MODEL_PROVIDER", "openai")
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



def test_large_verified_cinetwin_capture_uses_same_limit_as_unity_bridge():
    """Regression: native source captures around 88 MiB previously failed AI."""
    class SimulatedEvidence:
        def __init__(self, size: int, *, symlink: bool = False):
            self.size = size
            self.symlink = symlink
            self.reads = 0

        def is_file(self):
            return True

        def is_symlink(self):
            return self.symlink

        def stat(self):
            return SimpleNamespace(st_size=self.size)

        def read_text(self, *, encoding):
            assert encoding == "utf-8-sig"
            self.reads += 1
            return '{"kind":"cinetwin.behavior_capture","samples":[]}'

    actual_size = int(88.28 * 1024 * 1024)
    capture = SimulatedEvidence(actual_size)
    assert ai._read(capture, kind="CineTwin capture")["kind"] == (
        "cinetwin.behavior_capture")
    assert capture.reads == 1
    with pytest.raises(ai.TransferAIError, match="project evidence.*64 MiB"):
        ai._read(SimulatedEvidence(actual_size))
    with pytest.raises(ai.TransferAIError, match="CineTwin capture exceeds the 128 MiB"):
        ai._read(SimulatedEvidence(129 * 1024 * 1024),
                 kind="CineTwin capture")
    with pytest.raises(ai.TransferAIError, match="missing or unsafe"):
        ai._read(SimulatedEvidence(actual_size, symlink=True),
                 kind="CineTwin capture")


def test_ai_inspection_passes_large_capture_only_to_bounded_capture_reader(
        scene, monkeypatch):
    config, census, worker = scene
    original = ai._read
    seen = []

    def checked_read(path, *, kind="project evidence"):
        seen.append((Path(path).name, kind))
        return original(path, kind=kind)

    monkeypatch.setattr(ai, "_read", checked_read)
    evidence = ai.inspect(config, census, worker)
    assert evidence["summary"]["source_capture_sample_count"] == 1
    assert ("unity.capture.json", "CineTwin capture") in seen
    assert ("unity.csir.json", "Unity CSIR") in seen
    assert ("unity.census.json", "Unity source census") in seen
    assert ("target.mapping.json", "Target mapping") in seen
    assert ("Target.uproject", "project evidence") in seen



def test_default_ai_decision_reviews_all_source_elements_before_native(scene, monkeypatch):
    config, census, worker = scene
    import studio_model_provider
    monkeypatch.setenv("CUTSCENEAI_ELEMENT_PLANNING", "model")

    monkeypatch.setattr(ai, "_model_choose", lambda _: {
        "strategy": "native_source", "reason": "Registered native source policy",
    })
    requests = []

    def review(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(answer={
            "choices": [
                {
                    "occurrence_id": item["occurrence_id"],
                    "action": (item["candidate_actions"][0]
                               if item["candidate_actions"] else "report_only"),
                }
                for item in kwargs["payload"]["elements"]
            ]
        }, response_sha256="a" * 64)

    monkeypatch.setattr(studio_model_provider, "complete_json", review)
    decision = ai.decide(config, census, worker)
    plan = decision["element_plan"]
    assert decision["element_decisions_advisory_only"] is True
    assert plan["source_occurrence_count"] == 3
    assert plan["model_reviewed_count"] == 3
    assert decision["element_model_reviewed_count"] == 3
    assert decision["element_model_response_sha256s"] == ["a" * 64]
    assert requests[0]["task"] == "cutsceneai_element_conversion_choices"
    assert config["csir"] not in json.dumps(requests[0]["payload"])
    assert config["target_project"] not in json.dumps(requests[0]["payload"])
    assert all(item["model_reviewed"] for item in plan["elements"])
    assert plan["native_conversion_executed"] is False
    assert ai.verify(decision, config, census, worker)[
        "enable_actor_visibility_fallback"] is False


def test_injected_global_reasoner_cannot_silently_claim_element_ai_selection(scene):
    config, census, worker = scene
    decision = ai.decide(config, census, worker, reasoner=lambda _: {
        "strategy": "native_source", "reason": "Unit test reasoner without element review"
    })
    assert decision["element_model_reviewed_count"] == 0
    assert decision["element_model_response_sha256s"] == []
    assert all(row["selected_action"] == "report_only"
               and row["model_reviewed"] is False
               for row in decision["element_plan"]["elements"])
    assert ai.verify(decision, config, census, worker)


def test_ai_rejects_unregistered_per_occurrence_action_before_conversion(
        scene, monkeypatch):
    config, census, worker = scene
    import studio_model_provider
    monkeypatch.setenv("CUTSCENEAI_ELEMENT_PLANNING", "model")
    monkeypatch.setattr(ai, "_model_choose", lambda _: {
        "strategy": "native_source", "reason": "Source strategy"
    })

    def inject(**kwargs):
        return SimpleNamespace(answer={
            "choices": [
                {"occurrence_id": row["occurrence_id"],
                 "action": "arbitrary_unreal_python"}
                for row in kwargs["payload"]["elements"]
            ]
        }, response_sha256="b" * 64)

    monkeypatch.setattr(studio_model_provider, "complete_json", inject)
    with pytest.raises(ai.TransferAIError, match="unregistered"):
        ai.decide(config, census, worker)


def test_per_occurrence_decision_tampering_blocks_stale_plan_verification(scene):
    config, census, worker = scene
    decision = ai.decide(config, census, worker, reasoner=lambda _: {
        "strategy": "native_source", "reason": "Source plan"
    })
    decision["element_plan"]["elements"].pop()
    with pytest.raises(ai.TransferAIError, match="tampered"):
        ai.verify(decision, config, census, worker)


def test_phase33_strategy_is_source_bound_and_reverified_before_native(scene):
    config, census, worker = scene
    decision = ai.decide(config, census, worker, reasoner=lambda _: {
        "strategy": "native_source", "reason": "Installed native policy."
    })
    comparison = decision["element_strategy"]
    assert decision["element_strategy_advisory_only"] is True
    assert decision["element_strategy_sha256"] == comparison["comparison_sha256"]
    assert comparison["native_execution_authorized"] is False
    assert comparison["full_cutscene_fidelity_verified"] is False
    assert len(comparison["comparisons"]) == decision["element_plan"][
        "source_occurrence_count"]
    assert ai.verify(decision, config, census, worker)

    tampered = copy.deepcopy(decision)
    tampered["element_strategy"]["comparisons"][0]["suggested_action"] = (
        "arbitrary_native_code"
    )
    import studio_element_plan
    tampered["element_strategy"].pop("comparison_sha256")
    tampered["element_strategy"]["comparison_sha256"] = (
        studio_element_plan._digest(tampered["element_strategy"])
    )
    tampered["element_strategy_sha256"] = tampered["element_strategy"][
        "comparison_sha256"]
    with pytest.raises(ai.TransferAIError, match="Adaptive element strategy"):
        ai.verify(tampered, config, census, worker)


def test_phase33_model_receives_strategy_options_without_native_bypass(scene, monkeypatch):
    config, census, worker = scene
    import studio_model_provider
    monkeypatch.setenv("CUTSCENEAI_ELEMENT_PLANNING", "model")
    monkeypatch.setattr(ai, "_model_choose", lambda _: {
        "strategy": "native_source", "reason": "Source policy"
    })
    requests = []

    def review(**kwargs):
        requests.append(kwargs["payload"])
        for element in kwargs["payload"]["elements"]:
            assert "adaptive_evidence" in element
            assert element["candidate_actions"] == [
                option["action"] for option in element["adaptive_evidence"][
                    "alternatives"]
            ]
        return SimpleNamespace(answer={"choices": [
            {"occurrence_id": element["occurrence_id"],
             "action": (element["candidate_actions"][0]
                        if element["candidate_actions"] else "report_only")}
            for element in kwargs["payload"]["elements"]
        ]}, response_sha256="d" * 64)

    monkeypatch.setattr(studio_model_provider, "complete_json", review)
    decision = ai.decide(config, census, worker)
    assert requests
    assert decision["element_planning_mode"] == "MODEL_REVIEWED"
    assert ai.verify(decision, config, census, worker)
