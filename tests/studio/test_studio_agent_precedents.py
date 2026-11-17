"""The LLM sees reviewed CED precedents, never raw paths or executable payloads."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "studio"))
from studio_agent_graph import _approved_precedents


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
