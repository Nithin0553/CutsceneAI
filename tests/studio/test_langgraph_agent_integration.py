"""Evidence-driven LangGraph orchestration contracts; no Unity/Unreal editor needed."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in ("packages/studio", "tools", "integrations/unreal"):
    sys.path.insert(0, str(ROOT / folder))
import studio_agent_coordinator as coordinator
import studio_agent_executor as executor
import studio_agent_graph as graph


def write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def staged(tmp_path, *, enabled=True, fallback=2, issues=True):
    workspace = tmp_path / "runs"
    candidate = workspace / "candidates" / "candidate0001"
    candidate.mkdir(parents=True)
    job_id = "a" * 32
    job = {
        "job_id": job_id, "candidate_id": "candidate0001",
        "candidate_dir": str(candidate),
        "status": "GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED",
        "generation_status": "GENERATED_UNVERIFIED",
        "ai_agents_enabled": enabled, "automatic_setup": True,
        "expected_project": str(tmp_path / "Fake.uproject"),
        "expected_level": "/Game/L_Stage",
        "sequence_path": "/Game/CSAI/LS_Generated",
        "automatic_setup_manifest": str(candidate / "automatic-setup.json"),
    }
    write(workspace / "active-job.json", {"job_id": job_id})
    write(workspace / "jobs" / (job_id + ".json"), job)
    write(candidate / "automatic-setup.json",
          {"source_albedo_material_candidates": [{"slot_name": "Body"}]})
    write(candidate / ("closed-loop-evaluation-" + job_id + ".json"), {
        "kind": "cutsceneai.studio.closed_loop_evaluation",
        "issues": ([{"category": "VISUAL_NATIVE_READBACK",
                     "code": "RENDER_MATERIALS_MISSING_OR_ENGINE_DEFAULT"}]
                   if issues else []),
    })
    visual_file = candidate / ("visual-audit-" + job_id + "-0001.json")
    write(visual_file, {"kind": "cutsceneai.studio.visual_readback_audit",
                        "character_material_slots_engine_default": fallback})
    return workspace, candidate, job, visual_file


def test_agent_graph_is_compiled_real_langgraph(tmp_path):
    workspace, _candidate, job, _ = staged(tmp_path)
    compiled = graph.build_graph(workspace, job, lambda _: {
        "strategy": "report_only", "reason": "No safe adapter available"
    })
    assert hasattr(compiled, "invoke")
    names = set(compiled.get_graph().nodes)
    assert {"inspect", "reason", "dispatch", "observe"}.issubset(names)


def test_disabled_never_calls_reasoner_or_writes_requests(tmp_path):
    workspace, candidate, job, _ = staged(tmp_path, enabled=False)
    called = []
    result = graph.run_once(workspace, job, lambda summary: called.append(summary))
    assert result["status"] == "DISABLED"
    assert called == []
    assert list(candidate.glob("agent-request-*.json")) == []


def test_lifecycle_repair_request_receipt_verify_and_terminate(tmp_path):
    workspace, candidate, job, _visual_file = staged(tmp_path)
    decisions = []
    def select(summary):
        decisions.append(summary)
        return {"strategy": "restore_source_albedo",
                "reason": "Exact-source albedo and fallback slots verified"}
    initial = graph.run_once(workspace, job, select)
    assert initial["status"] == "WAITING_FOR_UNREAL_AGENT_REPAIR"
    assert initial["iterations"] == 0
    requests = list(candidate.glob("agent-request-*.json"))
    assert len(requests) == 1
    request = json.loads(requests[0].read_text())
    assert request["strategy"] == "restore_source_albedo"
    assert request["expected_level"] == "/Game/L_Stage"
    waiting = graph.run_once(workspace, job, select)
    assert waiting["status"] == "WAITING_FOR_UNREAL_AGENT_REPAIR"
    assert len(list(candidate.glob("agent-request-*.json"))) == 1
    write(candidate / ("agent-receipt-" + request["request_id"] + ".json"), {
        "kind": "cutsceneai.studio.agent_repair_receipt",
        "request_id": request["request_id"], "candidate_id": job["candidate_id"],
        "job_id": job["job_id"], "status": "REPAIR_SAVED_AND_REAUDITED",
        "fallback_after": 0, "changes": 2,
    })
    completed = graph.run_once(workspace, job, select)
    assert completed["status"] == "MATERIAL_FALLBACK_RESOLVED_OTHER_DOMAINS_UNVERIFIED"
    assert completed["iterations"] == 1
    assert completed["fidelity_verified"] is False
    assert len(decisions) == 1
    assert graph.run_once(workspace, job, select) == completed


def test_no_progress_stops_without_second_agent_request(tmp_path):
    workspace, candidate, job, _ = staged(tmp_path)
    reasoning = lambda _: {"strategy": "restore_source_albedo", "reason": "Repair candidate"}
    started = graph.run_once(workspace, job, reasoning)
    req_id = started["pending_request"]
    write(candidate / ("agent-receipt-" + req_id + ".json"), {
        "kind": "cutsceneai.studio.agent_repair_receipt",
        "request_id": req_id, "candidate_id": job["candidate_id"],
        "job_id": job["job_id"], "status": "REPAIR_SAVED_AND_REAUDITED",
        "fallback_after": 2, "changes": 0,
    })
    final = graph.run_once(workspace, job, reasoning)
    assert final["status"] == "STOPPED_NO_MEASURABLE_PROGRESS"
    assert final["iterations"] == 1
    assert len(list(candidate.glob("agent-request-*.json"))) == 1


def test_agent_can_report_only_with_no_unsafe_repair(tmp_path):
    workspace, candidate, job, _ = staged(tmp_path)
    result = graph.run_once(workspace, job, lambda _: {
        "strategy": "report_only", "reason": "Need custom shader translation"
    })
    assert result["status"] == "UNRESOLVED_NO_SAFE_STRATEGY"
    assert result["reasoning"] == "Need custom shader translation"
    assert list(candidate.glob("agent-request-*.json")) == []


def test_graph_no_issues_finishes_without_model_or_perfection(tmp_path):
    workspace, _candidate, job, _ = staged(tmp_path, issues=False)
    result = graph.run_once(workspace, job, lambda _: pytest.fail("Model must not run"))
    assert result["status"] == "NO_DETECTED_GAPS_FIDELITY_UNVERIFIED"
    assert not result["fidelity_verified"]


def test_missing_or_invalid_receipt_stops_without_executing(tmp_path):
    workspace, candidate, job, _ = staged(tmp_path)
    start = graph.run_once(workspace, job, lambda _: {
        "strategy": "restore_source_albedo", "reason": "Provenance"
    })
    write(candidate / ("agent-receipt-" + start["pending_request"] + ".json"), {
        "kind": "cutsceneai.studio.agent_repair_receipt",
        "request_id": start["pending_request"], "job_id": "b" * 32,
        "candidate_id": job["candidate_id"], "fallback_after": 0,
    })
    final = graph.run_once(workspace, job)
    assert final["status"] == "EVIDENCE_UNAVAILABLE"
    assert "mismatched" in final["failure"]


def test_coordinator_never_runs_without_candidate_consent(tmp_path):
    workspace, _candidate, job, _ = staged(tmp_path, enabled=False)
    assert coordinator.advance(workspace)["status"] == "DISABLED"
    assert coordinator.status(workspace)["enabled"] is False
    job["ai_agents_enabled"] = True
    write(workspace / "jobs" / (job["job_id"] + ".json"), job)
    assert coordinator.advance(workspace, reasoner=lambda _: {
        "strategy": "report_only", "reason": "Unverified"
    })["enabled"] is True


def test_unreal_executor_denies_unapproved_llm_action_before_mutation(tmp_path):
    workspace, _candidate, job, _ = staged(tmp_path, enabled=False)
    req = {"kind": "cutsceneai.studio.agent_repair_request", "schema_version": "1",
           "job_id": job["job_id"], "candidate_id": job["candidate_id"],
           "strategy": "arbitrary_python", "sequence_path": job["sequence_path"],
           "expected_project": job["expected_project"],
           "expected_level": job["expected_level"]}
    with pytest.raises(ValueError, match="not authorized"):
        executor.execute(object(), workspace, job, req, project=job["expected_project"],
                         level=job["expected_level"])


def test_missing_model_configuration_is_reported(tmp_path, monkeypatch):
    workspace, candidate, job, _ = staged(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = graph.run_once(workspace, job)
    assert result["status"] == "AGENT_REASONING_UNAVAILABLE"
    assert "OPENAI_API_KEY" in result["failure"]
    assert list(candidate.glob("agent-request-*.json")) == []



def test_bridge_persists_agent_consent_per_candidate_and_rejects_text_booleans(tmp_path):
    import studio_local_bridge as bridge
    workspace, candidate, job, _ = staged(tmp_path, enabled=False)
    (workspace / "active-job.json").unlink()
    write(workspace / "active-candidate.json", {"candidate_id": job["candidate_id"]})
    write(workspace / "connection.json", {
        "csir": "source.csir.json",
        "target_project": job["expected_project"],
        "level_path": job["expected_level"],
        "source_rights_confirmed": True,
    })
    approved = bridge.approve_one_click(job["candidate_id"], workspace, enable_ai_agents=True)
    assert approved["approved"] is True
    record = json.loads((workspace / "one-click-approval.json").read_text())
    assert record["enable_ai_agents"] is True
    with pytest.raises(ValueError, match="Boolean"):
        bridge.approve_one_click(job["candidate_id"], workspace, enable_ai_agents="false")
    bridge.approve_one_click(job["candidate_id"], workspace)
    record = json.loads((workspace / "one-click-approval.json").read_text())
    assert record["enable_ai_agents"] is False
    assert list(candidate.glob("agent-request-*.json")) == []


def test_agent_diagnoses_unsupported_domain_but_cannot_execute_it(tmp_path):
    workspace, candidate, job, _ = staged(tmp_path, fallback=0)
    result = graph.run_once(workspace, job, lambda summary: {
        "strategy": "report_only", "reason": "Missing semantic camera adapter"
    })
    assert result["status"] == "UNRESOLVED_NO_SAFE_STRATEGY"
    assert result["reasoning"] == "Missing semantic camera adapter"
    assert list(candidate.glob("agent-request-*.json")) == []


def test_native_failure_is_only_diagnosed_never_replayed(tmp_path):
    workspace, candidate, job, _ = staged(tmp_path)
    job.update({"generation_status": "NOT_STARTED",
                "status": "BLOCKED_OR_FAILED", "automatic_setup": False})
    (candidate / ("closed-loop-evaluation-" + job["job_id"] + ".json")).unlink()
    result = graph.run_once(workspace, job, lambda summary: {
        "strategy": "report_only", "reason": "Source asset mapping is unresolved"
    })
    assert result["status"] == "UNRESOLVED_NO_SAFE_STRATEGY"
    assert list(candidate.glob("agent-request-*.json")) == []
    assert result["issues"][0]["category"] == "NATIVE_TRANSFER_FAILED_NO_PARITY"
