"""The LLM sees reviewed CED precedents, never raw paths or executable payloads."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "studio"))
from studio_agent_graph import _approved_precedents
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "readiness"))
import ced_rulebook
from studio_agent_graph import _approved_ced_rulebook_precedents


def _case(source_project: str):
    data = {
        "case_version": "0.1.0",
        "status": "MAPPING_VERIFIED",
        "source": {"engine": "unity", "project_fingerprint": source_project},
        "target": {"engine": "unreal"},
        "features": ["entity:entity.prop"],
        "mapping_labels": [
            {"ced": "entity.prop", "resolver": "native_static_mesh",
             "outcome": "NATIVE_UNVERIFIED",
             "parameters": {"private_path": "C:/Never/Share/This/Asset.fbx"}},
            {"ced": "../../bad/path", "resolver": "unsafe", "outcome": "BLOCKED",
             "parameters": {"command": "rm -rf /"}},
        ],
    }
    digest = hashlib.sha256(json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()[:24]
    data["case_id"] = digest
    return data


def test_approved_precedents_are_redacted_and_non_executable(tmp_path):
    workspace = tmp_path / "runs"
    store = workspace / "learning" / "approved-cases"
    store.mkdir(parents=True)
    case = _case("other_project")
    (store / (case["case_id"] + ".json")).write_text(json.dumps(case))
    csir = tmp_path / "source.csir.json"
    csir.write_text(json.dumps({
        "source": {"engine": "unity", "project_fingerprint": "current_project"},
        "entities": [{"ced_type": "entity.prop"}], "tracks": [],
    }))
    result = _approved_precedents(workspace, {"csir": str(csir)})
    assert len(result) == 1
    assert result[0]["case_id"] == case["case_id"]
    assert result[0]["can_execute_tools"] is False
    assert result[0]["full_fidelity_verified"] is False
    assert len(result[0]["ced_mapping_labels"]) == 1
    assert "private_path" not in json.dumps(result)
    assert "Never" not in json.dumps(result)
    assert "rm -rf" not in json.dumps(result)


def test_same_project_case_cannot_leak_into_heldout_recommendation(tmp_path):
    workspace = tmp_path / "runs"
    store = workspace / "learning" / "approved-cases"
    store.mkdir(parents=True)
    case = _case("source_project")
    (store / (case["case_id"] + ".json")).write_text(json.dumps(case))
    csir = tmp_path / "source.csir.json"
    csir.write_text(json.dumps({
        "source": {"engine": "unity", "project_fingerprint": "source_project"},
        "entities": [{"ced_type": "entity.prop"}], "tracks": [],
    }))
    assert _approved_precedents(workspace, {"csir": str(csir)}) == []


def test_unapproved_or_tampered_record_never_reaches_model(tmp_path):
    workspace = tmp_path / "runs"
    store = workspace / "learning" / "approved-cases"
    store.mkdir(parents=True)
    case = _case("other_project")
    case["status"] = "CANDIDATE"
    (store / (case["case_id"] + ".json")).write_text(json.dumps(case))
    csir = tmp_path / "source.csir.json"
    csir.write_text(json.dumps({
        "source": {"engine": "unity", "project_fingerprint": "current_project"},
        "entities": [{"ced_type": "entity.prop"}], "tracks": [],
    }))
    assert _approved_precedents(workspace, {"csir": str(csir)}) == []


def test_agent_exposes_only_qa_approved_native_rule_id_without_private_params(tmp_path):
    workspace = tmp_path / "runs"
    workspace.mkdir()
    store = tmp_path / "ced-knowledge"
    baseline = json.loads(ced_rulebook.BASE_RULES.read_text())["rules"][0]
    rule = dict(baseline)
    rule["rule_id"] = "verified-rotated-pose-rule"
    rule["ced"] = "transform.quaternion"
    candidate_id = ced_rulebook.propose(
        store, rule, origin="USER", feature_sha256="b" * 64)
    source = tmp_path / "source.csir.json"
    source.write_text(json.dumps({
        "source": {"engine": "unity"},
        "entities": [{"ced_type": "transform.quaternion"}], "tracks": [],
    }))
    # Candidate is never shown as approved, even after persistence.
    assert _approved_ced_rulebook_precedents(workspace, {"csir": str(source)}) == []
    evidence = {
        "kind": "cinetwin.behavior_comparison",
        "acceptance_status": "STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE",
        "native_persistence_status": "STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS",
        "generation_editor_pid": 11, "observation_editor_pid": 22,
        "evaluation": {"status": "NO_FLAGGED_DIFFERENCES",
                       "overall_cutscene_fidelity": "NOT_ESTABLISHED"},
    }
    (store / "native_evidence" / "pass.json").write_text(json.dumps(evidence))
    ced_rulebook.promote(
        store, candidate_id, evidence_name="pass.json", reviewer="qa_user",
        held_out_passed=True, regression_passed=True)
    results = _approved_ced_rulebook_precedents(workspace, {"csir": str(source)})
    assert len(results) == 1
    assert results[0]["ced"] == "transform.quaternion"
    assert results[0]["no_automatic_native_permission"] is True
    assert "parameters" not in json.dumps(results)
    assert "native_evidence" not in json.dumps(results)
