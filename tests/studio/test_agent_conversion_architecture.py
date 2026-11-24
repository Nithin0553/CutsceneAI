"""Generalizable conversion-agent contracts: unseen semantics, retrieval and safe tools."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "studio"))
sys.path.insert(0, str(ROOT / "tools"))

import ced_agent_knowledge as knowledge
import studio_conversion_graph as graph
import studio_model_provider as models
import studio_recovery_policy as recovery


def _evidence():
    return {
        "allowed_strategies": ["native_source", "source_materials"],
        "summary": {"safe_partial_visibility_adapter_available": False},
        "ced_knowledge": {
            "knowledge_sha256": "e" * 64,
            "no_native_write_permission": True,
        },
    }


def test_unseen_component_combinations_retrieve_without_benchmark_names():
    source = {
        "entities": [
            {"ced_type": "entity.character", "name": "UnseenCharacter"},
            {"ced_type": "camera.fov", "name": "CustomLens"},
            {"ced_type": "unknown.vendor.proprietary", "name": "NeverSeenPlugin"},
        ],
        "tracks": [
            {"ced_type": "camera.transform", "sections": [
                {"ced_type": "animation.section"}]},
            {"ced_type": "event.state", "sections": []},
        ],
    }
    result = knowledge.retrieve(
        source, target_capabilities={"camera.lens_model": True},
        source_version="6000.3", target_version="5.8",
    )
    seen = {row["ced"]: row for row in result["entries"]}
    assert seen["camera.fov"]["source_occurrences"] == 1
    assert "camera_fov" in seen["camera.fov"]["native_action_candidates"]
    assert any(rule["rule_id"] == "unity-unreal-camera-fov"
               for rule in seen["camera.fov"]["rules"])
    assert seen["unknown.vendor.proprietary"]["resolution_state"] == (
        "UNKNOWN_SEMANTIC_INVESTIGATE")
    assert seen["unknown.vendor.proprietary"]["native_action_candidates"] == []
    assert result["no_native_write_permission"] is True
    assert len(result["knowledge_sha256"]) == 64


def test_ced_rule_capability_gaps_are_exposed_not_fabricated():
    source = {"tracks": [{"ced_type": "camera.fov"}]}
    missing = knowledge.retrieve(source, target_capabilities={})
    full = knowledge.retrieve(
        source, target_capabilities={"camera.lens_model": True},
    )
    a = missing["entries"][0]["rules"][0]
    b = full["entries"][0]["rules"][0]
    assert "camera.lens_model" in a["capabilities_not_observed"]
    assert a["status"] == "CAPABILITY_EVIDENCE_MISSING"
    assert b["status"] == "RULE_CANDIDATE_REQUIRES_PREFLIGHT"
    assert missing["knowledge_sha256"] != full["knowledge_sha256"]


def test_langgraph_agent_retries_a_rejected_strategy_with_validator_feedback():
    observed = []
    def reasoner(evidence):
        observed.append(evidence.get("planning_feedback", ""))
        return ({"strategy": "invent_runtime_plugin", "reason": "Bad attempt"}
                if len(observed) == 1 else
                {"strategy": "source_materials", "reason": "Existing importer"})
    answer = graph.select(_evidence(), reasoner=reasoner)
    assert answer["strategy"] == "source_materials"
    assert len(observed) == 2
    assert observed[0] == ""
    assert "unregistered" in observed[1].lower()


def test_langgraph_agent_never_executes_arbitrary_native_code_or_endless_retry():
    calls = []
    def bad(_):
        calls.append(True)
        return {"strategy": "native_source", "reason": "",
                "python": "import unreal; unreal.EditorLevelLibrary.destroy_all()"}
    with pytest.raises(graph.ConversionAgentError, match="unregistered"):
        graph.select(_evidence(), reasoner=bad)
    assert len(calls) == graph.MAX_PLANNING_ATTEMPTS


def test_local_model_provider_structured_json_no_cloud_key(monkeypatch):
    monkeypatch.setenv("CUTSCENEAI_MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("CUTSCENEAI_AGENT_MODEL", "qwen2.5:7b-instruct")
    monkeypatch.setenv("CUTSCENEAI_OLLAMA_URL", "http://127.0.0.1:11434")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, length):
            assert length == models.MAX_RESPONSE_BYTES + 1
            return json.dumps({
                "message": {"content": json.dumps({
                    "strategy": "native_source", "reason": "Camera-only timeline",
                })},
            }).encode()

    def transport(req, timeout):
        assert timeout == 120
        assert req.full_url == "http://127.0.0.1:11434/api/chat"
        seen.update(json.loads(req.data))
        return Response()

    monkeypatch.setattr(models.request, "urlopen", transport)
    result = models.complete_json(
        task="cutsceneai_test",
        instructions="Choose a registered option from redacted evidence.",
        payload={"ced": ["camera.fov"], "target_capable": True},
        schema={"type": "object", "additionalProperties": False,
                "properties": {"strategy": {"type": "string"},
                               "reason": {"type": "string"}},
                "required": ["strategy", "reason"]},
    )
    assert result.provider == "OLLAMA_LOCAL"
    assert result.answer["strategy"] == "native_source"
    assert seen["stream"] is False
    assert seen["options"]["temperature"] == 0
    assert seen["messages"][1]["content"] == (
        '{"ced": ["camera.fov"], "target_capable": true}')
    assert len(result.response_sha256) == 64


def _ollama_test_request():
    return {
        "task": "cutsceneai_test",
        "instructions": "Choose the registered strategy only.",
        "payload": {"ced": ["camera.fov"]},
        "schema": {"type": "object"},
    }


def test_local_ollama_timeout_is_configurable_and_bounded(monkeypatch):
    monkeypatch.delenv("CUTSCENEAI_OLLAMA_TIMEOUT_SECONDS", raising=False)
    assert models._ollama_timeout_seconds() == 120
    monkeypatch.setenv("CUTSCENEAI_OLLAMA_TIMEOUT_SECONDS", "180")
    assert models._ollama_timeout_seconds() == 180
    for value in ("0", "9", "301", "inf", "20.5", ""):
        monkeypatch.setenv("CUTSCENEAI_OLLAMA_TIMEOUT_SECONDS", value)
        with pytest.raises(models.ModelProviderError, match="integer from 10 to 300"):
            models._ollama_timeout_seconds()


def test_local_ollama_timeout_is_not_misreported_as_offline(monkeypatch):
    monkeypatch.setenv("CUTSCENEAI_MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("CUTSCENEAI_OLLAMA_TIMEOUT_SECONDS", "120")

    def timed_out(_req, timeout):
        assert timeout == 120
        raise TimeoutError("timed out")

    monkeypatch.setattr(models.request, "urlopen", timed_out)
    with pytest.raises(models.ModelProviderError, match="timed out after 120") as caught:
        models.complete_json(**_ollama_test_request())
    result = recovery.classify(
        str(caught.value), phase="ANALYZING_PROJECTS", native_submitted=False
    )
    assert result["category"] == "MODEL_PROVIDER_TIMEOUT"
    assert result["safe_automatic_retry"] is False
    assert result["native_replay_authorized"] is False


def test_ollama_memory_http_error_is_not_misreported_as_offline(monkeypatch):
    monkeypatch.setenv("CUTSCENEAI_MODEL_PROVIDER", "ollama")

    def overloaded(req, timeout):
        raise models.error.HTTPError(
            req.full_url, 500, "Internal Server Error", {},
            io.BytesIO(b'{"error":"model requires more system memory (4.0 GiB)"}')
        )

    monkeypatch.setattr(models.request, "urlopen", overloaded)
    with pytest.raises(models.ModelProviderError, match="lacks enough memory") as caught:
        models.complete_json(**_ollama_test_request())
    result = recovery.classify(
        str(caught.value), phase="ANALYZING_PROJECTS", native_submitted=False
    )
    assert result["category"] == "MODEL_RESOURCE_EXHAUSTED"
    assert result["safe_automatic_retry"] is False


def test_missing_ollama_model_is_not_treated_as_service_disconnect(monkeypatch):
    monkeypatch.setenv("CUTSCENEAI_MODEL_PROVIDER", "ollama")

    def missing(req, timeout):
        raise models.error.HTTPError(req.full_url, 404, "Not Found", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(models.request, "urlopen", missing)
    with pytest.raises(models.ModelProviderError, match="model not found") as caught:
        models.complete_json(**_ollama_test_request())
    result = recovery.classify(
        str(caught.value), phase="ANALYZING_PROJECTS", native_submitted=False
    )
    assert result["category"] == "MODEL_NOT_INSTALLED"
    assert result["safe_automatic_retry"] is False


def test_offline_ollama_still_allows_pre_native_bounded_retry(monkeypatch):
    monkeypatch.setenv("CUTSCENEAI_MODEL_PROVIDER", "ollama")

    def disconnected(_req, timeout):
        raise models.error.URLError("connection refused")

    monkeypatch.setattr(models.request, "urlopen", disconnected)
    with pytest.raises(models.ModelProviderError, match="connection failed") as caught:
        models.complete_json(**_ollama_test_request())
    result = recovery.classify(
        str(caught.value), phase="ANALYZING_PROJECTS", native_submitted=False
    )
    assert result["category"] == "MODEL_PROVIDER_UNAVAILABLE"
    assert result["safe_automatic_retry"] is True


@pytest.mark.parametrize("invalid", [
    "https://remote.example:11434",
    "http://10.0.0.99:11434",
    "http://localhost:11434/elsewhere",
    "http://user:secret@localhost:11434",
])
def test_local_model_refuses_remote_or_unsafe_origins(monkeypatch, invalid):
    monkeypatch.setenv("CUTSCENEAI_MODEL_PROVIDER", "ollama")
    monkeypatch.setenv("CUTSCENEAI_OLLAMA_URL", invalid)
    with pytest.raises(models.ModelProviderError, match="loopback"):
        models.complete_json(
            task="cutsceneai_test", instructions="No secrets",
            payload={"ced": "camera.fov"}, schema={"type": "object"},
        )


def test_bounded_prompt_budget_rejects_source_data_dump():
    with pytest.raises(models.ModelProviderError, match="prompt budget"):
        models._payload_bytes({"source_file": "X" * 100000})
