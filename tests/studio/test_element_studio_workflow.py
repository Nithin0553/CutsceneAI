"""Candidate-scoped Element 3 workflow, native gate and persisted readback tests."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests" / "studio"))
sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))

import studio_element_workflow as workflow
from sampling_plan import build_plan
from test_element_cinetwin_attribution import _inputs


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _setup(tmp_path):
    csir, _conversion, _sampling, source, target = _inputs()
    work = tmp_path / "runs"
    work.mkdir()
    source_file = tmp_path / "source.csir.json"
    _write(source_file, csir)
    plan = build_plan(csir, csir_sha256=hashlib.sha256(
        source_file.read_bytes()).hexdigest())
    source["source"] = copy.deepcopy(plan["source"])
    target["source"] = copy.deepcopy(plan["source"])
    source_file_capture = tmp_path / "source.capture.json"
    _write(source_file_capture, source)
    candidate_id = "20261121T183000Z_deadbeef"
    candidate = work / "candidates" / candidate_id
    candidate.mkdir(parents=True)
    project = tmp_path / "Demo.uproject"
    project.write_text("{}", encoding="utf-8")
    original_mapping = tmp_path / "original-mapping.json"
    _write(original_mapping, {"sequence_asset_path": "/Game/Demo/LS_Original"})
    mapping = work / "candidates" / (candidate_id + ".mapping.json")
    _write(mapping, {"sequence_asset_path": "/Game/Demo/LS_Trial"})
    _write(candidate / "transfer-plan.json", {
        "sequence_asset_path": "/Game/Demo/LS_Trial",
        "actions": [],
    })
    _write(work / "connection.json", {
        "csir": str(source_file), "capture": str(source_file_capture),
        "mapping": str(original_mapping), "target_project": str(project),
        "level_path": "/Game/Demo/L_Stage",
        "auto_create_level": False,
    })
    _write(work / "active-candidate.json", {
        "candidate_id": candidate_id, "mapping_copy": str(mapping),
        "sequence_path": "/Game/Demo/LS_Trial",
    })
    worker = {
        "connected": True, "project": str(project), "level": "/Game/Demo/L_Stage",
        "scene_inventory": {
            "available": True,
            "native_capabilities": {
                "fbx_asset_import": True,
                "cine_camera_actor": True,
                "sequencer_skeletal_animation_track": True,
                "sequencer_visibility_track": True,
            },
        },
    }
    return work, worker, target


def _offset(target: dict, cm: float) -> dict:
    other = copy.deepcopy(target)
    for sample in other["samples"]:
        sample["entities"][0]["world_transform"]["position_m"][0] += cm / 100
    return other


def test_candidate_review_contains_all_five_phase_inputs_and_redacts_names(tmp_path):
    work, worker, _target = _setup(tmp_path)
    prepared = workflow.prepare(work, worker)
    assert prepared["available"] is True
    assert prepared["source_occurrence_count"] == 5
    assert prepared["review_acknowledged"] is False
    assert prepared["native_execution_authorized"] is False
    assert prepared["full_cutscene_fidelity_verified"] is False
    assert prepared["target_capabilities_observed"] is True
    assert prepared["target_capability_evidence_current"] is True
    assert len(prepared["elements"]) == prepared["source_occurrence_count"]
    assert all(x["native_verified"] is False for x in prepared["elements"])
    assert all(x["source_location"].startswith(("entities[", "tracks["))
               for x in prepared["elements"])
    candidate = work / "candidates" / prepared["candidate_id"]
    persisted = candidate / ("element-workflow-" + prepared["workflow_sha256"] + ".json")
    record = json.loads(persisted.read_text(encoding="utf-8"))
    assert record["element_plan"]["source_occurrence_count"] == 5
    assert record["element_schedule"]["native_execution_permitted"] is False
    assert record["element_strategy"]["native_execution_authorized"] is False
    assert record["element_investigation"]["native_execution_authorized"] is False
    assert workflow.current(work, worker) == prepared
    response = json.dumps(prepared)
    assert "Alice" not in response
    assert "CameraUnreal" not in response
    assert "Assets/timeline.playable" not in response
    assert "Demo.uproject" not in response


def test_new_element_review_pre_native_acknowledgment_is_exact_candidate_bound(tmp_path):
    work, worker, _target = _setup(tmp_path)
    prepared = workflow.prepare(work, worker)
    with pytest.raises(workflow.ElementWorkflowError, match="Review and acknowledge"):
        workflow.require_acknowledgment(work, worker, prepared["candidate_id"])
    with pytest.raises(workflow.ElementWorkflowError, match="changed"):
        workflow.acknowledge(work, worker, "0" * 64)
    assert workflow.acknowledge(work, worker, prepared["workflow_sha256"])[
        "native_execution_authorized"] is False
    workflow.require_acknowledgment(work, worker, prepared["candidate_id"])
    assert workflow.current(work, worker)["review_acknowledged"] is True
    invalid = copy.deepcopy(worker)
    invalid["scene_inventory"]["native_capabilities"]["cine_camera_actor"] = False
    with pytest.raises(workflow.ElementWorkflowError, match="acknowledge"):
        workflow.require_acknowledgment(work, invalid, prepared["candidate_id"])
    refreshed = workflow.prepare(work, invalid)
    assert refreshed["workflow_sha256"] != prepared["workflow_sha256"]
    assert refreshed["review_acknowledged"] is False
    with pytest.raises(workflow.ElementWorkflowError, match="acknowledge"):
        workflow.require_acknowledgment(work, invalid, refreshed["candidate_id"])


def test_existing_native_legacy_path_without_element_review_is_unchanged(tmp_path):
    work, worker, _target = _setup(tmp_path)
    active = json.loads((work / "active-candidate.json").read_text())
    workflow.require_acknowledgment(work, worker, active["candidate_id"])


def test_rehashed_source_bound_snapshot_is_reconstructed_not_trusted(tmp_path):
    work, worker, _target = _setup(tmp_path)
    prepared = workflow.prepare(work, worker)
    path = work / "candidates" / prepared["candidate_id"] / (
        "element-workflow-" + prepared["workflow_sha256"] + ".json")
    altered = json.loads(path.read_text())
    altered["element_plan"]["elements"][0]["state"] = "TRANSFER_VERIFIED"
    altered.pop("workflow_sha256")
    altered["workflow_sha256"] = workflow._digest(altered)
    _write(path, altered)
    with pytest.raises(workflow.ElementWorkflowError, match="checksum"):
        workflow.current(work, worker)


def test_changing_original_csir_or_prepared_mapping_refuses_stale_review(tmp_path):
    work, worker, _target = _setup(tmp_path)
    prepared = workflow.prepare(work, worker)
    mapping = Path(json.loads((work / "active-candidate.json").read_text())[
        "mapping_copy"])
    mapping.write_text(mapping.read_text() + " ", encoding="utf-8")
    with pytest.raises(workflow.ElementWorkflowError, match="stale"):
        workflow.current(work, worker)
    # A new immutable snapshot can be prepared and must be acknowledged anew.
    new = workflow.prepare(work, worker)
    assert new["workflow_sha256"] != prepared["workflow_sha256"]
    assert new["review_acknowledged"] is False


def test_source_bound_target_observations_are_persisted_and_measured_not_approved(tmp_path):
    work, worker, target = _setup(tmp_path)
    prepared = workflow.prepare(work, worker)
    before = tmp_path / "unreal-before.json"
    after = tmp_path / "unreal-after.json"
    _write(before, _offset(target, 7))
    _write(after, target)
    first = workflow.verify_target(work, worker, str(before))
    assert first["verification"]["observation_count"] == 1
    assert first["verification"]["native_repair_authorized"] is False
    assert first["verification"]["full_cutscene_fidelity_verified"] is False
    result = workflow.verify_target(work, worker, str(after))
    assert result["verification"]["observation_count"] == 2
    assert result["verification"]["remeasurement_attempts"] == 1
    assert result["verification"]["native_repair_authorized"] is False
    assert result["verification"]["full_cutscene_fidelity_verified"] is False
    assert workflow.current(work, worker)["verification"] == result["verification"]
    index_path = work / "candidates" / prepared["candidate_id"] / "element-readback-index.json"
    index = json.loads(index_path.read_text())
    assert len(index["observations"]) == 2
    assert index["observations"][0]["sha256"] == hashlib.sha256(
        before.read_bytes()).hexdigest()
    with pytest.raises(workflow.ElementWorkflowError, match="Duplicate"):
        workflow.verify_target(work, worker, str(before))


def test_source_target_comparison_refuses_foreign_sequence_and_changed_capture(tmp_path):
    work, worker, target = _setup(tmp_path)
    workflow.prepare(work, worker)
    foreign = tmp_path / "wrong-sequence.json"
    target["target"] = {"sequence_asset_path": "/Game/Foreign/LS_Wrong"}
    _write(foreign, target)
    with pytest.raises(workflow.ElementWorkflowError, match="sequence"):
        workflow.verify_target(work, worker, str(foreign))
    target["target"]["sequence_asset_path"] = "/Game/Demo/LS_Trial"
    _write(foreign, target)
    workflow.verify_target(work, worker, str(foreign))
    target["samples"][0]["entities"][0]["world_transform"]["position_m"][0] = 99
    _write(foreign, target)
    with pytest.raises(workflow.ElementWorkflowError, match="changed"):
        workflow.current(work, worker)


def test_readback_index_forgery_and_budget_refuse_unsafe_replays(tmp_path):
    work, worker, target = _setup(tmp_path)
    prepared = workflow.prepare(work, worker)
    for i in range(3):
        path = tmp_path / f"unreal-{i}.json"
        _write(path, _offset(target, float(i+1)))
        workflow.verify_target(work, worker, str(path))
    fourth = tmp_path / "unreal-fourth.json"
    _write(fourth, _offset(target, 10))
    with pytest.raises(workflow.ElementWorkflowError, match="budget"):
        workflow.verify_target(work, worker, str(fourth))
    index_path = work / "candidates" / prepared["candidate_id"] / "element-readback-index.json"
    index = json.loads(index_path.read_text())
    index["observations"][-1]["report_sha256"] = "f" * 64
    index["index_sha256"] = workflow._digest({
        k: v for k, v in index.items() if k != "index_sha256"
    })
    _write(index_path, index)
    with pytest.raises(workflow.ElementWorkflowError, match="does not match"):
        workflow.current(work, worker)


def test_paginated_element_preview_is_bounded_and_deterministic(tmp_path):
    work, worker, _target = _setup(tmp_path)
    summary = workflow.prepare(work, worker)
    page = workflow.current(work, worker, offset=1)
    assert page["elements"] == summary["elements"][1:]
    assert page["offset"] == 1
    with pytest.raises(workflow.ElementWorkflowError, match="offset"):
        workflow.current(work, worker, offset=-1)
    with pytest.raises(workflow.ElementWorkflowError, match="offset"):
        workflow.current(work, worker, offset=30001)


def test_http_element_review_requires_local_session_token_and_rejects_native_bypass(tmp_path):
    from test_studio_local_bridge import bridge
    work, worker, _target = _setup(tmp_path)
    _write(work / "unreal-worker.json", {
        "heartbeat": "2099-11-21T00:00:00Z",
        "project": worker["project"], "level": worker["level"],
        "scene_inventory": worker["scene_inventory"],
    })
    # The heartbeat is not live, so the API must not claim native capability observation.
    webroot = tmp_path / "web"
    webroot.mkdir()
    (webroot / "index.html").write_text("Studio", encoding="utf-8")
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), bridge.create_handler(webroot, work)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:" + str(server.server_port)

    def call(endpoint: str, payload: dict | None = None, token: str = ""):
        headers = {"Host": "127.0.0.1:" + str(server.server_port)}
        if payload is not None:
            headers.update({"Content-Type": "application/json",
                            "X-CSAI-Token": token})
        request = Request(base + endpoint, headers=headers,
                          data=json.dumps(payload).encode() if payload is not None else None)
        try:
            with urlopen(request, timeout=20) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())

    try:
        token = call("/api/status")[1]["token"]
        assert call("/api/elements")[1]["available"] is False
        assert call("/api/elements/prepare", {})[0] == 403
        code, summary = call("/api/elements/prepare", {}, token)
        assert code == 200, summary
        assert summary["target_capabilities_observed"] is False
        assert call("/api/elements?offset=bogus")[0] == 409
        assert call("/api/elements/acknowledge", {
            "workflow_sha256": summary["workflow_sha256"], "reviewed": False,
        }, token)[0] == 422
        code, ack = call("/api/elements/acknowledge", {
            "workflow_sha256": summary["workflow_sha256"], "reviewed": True,
        }, token)
        assert code == 200
        assert ack["native_execution_authorized"] is False
        assert call("/api/elements")[1]["review_acknowledged"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join()



def test_element4_studio_review_never_calls_inventory_a_validated_model_strategy(tmp_path):
    work, worker, _target = _setup(tmp_path)
    report = workflow.prepare(work, worker)
    assert report["element4_strategy_validation"]["status"] == (
        "NO_MODEL_STRATEGY_DECISION"
    )
    assert report["element4_strategy_validation"]["independently_recomputed"] is False
    assert report["element4_strategy_validation"]["native_execution_authorized"] is False

    location = work / "candidates" / report["candidate_id"]
    _write(location / "ai-conversion-decision.json", {
        "kind": "cutsceneai.studio.ai_conversion_decision",
        "element4_validation": {"validation_sha256": "a" * 64},
        "input_sha256": {},
    })
    changed = workflow.current(work, worker)
    assert changed["element4_strategy_validation"]["status"] == (
        "MODEL_STRATEGY_EVIDENCE_STALE_OR_UNVERIFIABLE"
    )
    assert changed["element4_strategy_validation"][
        "independently_recomputed"
    ] is False
    assert changed["native_execution_authorized"] is False
    assert changed["full_cutscene_fidelity_verified"] is False
