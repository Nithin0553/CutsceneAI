"""Element 3 exact native action consent, dispatch receipts and worker guards.

All direct tests use synthetic plans and fake receipts. They DO NOT run Unreal.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "packages" / "studio"))
sys.path.insert(0, str(ROOT / "integrations" / "unreal"))
sys.path.insert(0, str(ROOT / "tests" / "studio"))

import studio_element_native_execution as native
import studio_element_native_gate as native_gate
import studio_element_workflow as workflow
from test_element_studio_workflow import _setup, _write


def _manifest(tmp_path, *, two_actions=False):
    work, worker, target = _setup(tmp_path)
    candidate = json.loads((work / "active-candidate.json").read_text())
    location = work / "candidates" / candidate["candidate_id"]
    actions = [
        {"kind": "camera_setup", "source_location": "entities[1]",
         "source_ced": "entity.camera", "entity_name": "Camera"}
    ]
    if two_actions:
        actions.append({"kind": "audio", "unattributed_legacy": True})
    _write(location / "transfer-plan.json", {
        "sequence_asset_path": "/Game/Demo/LS_Trial", "actions": actions,
    })
    report = workflow.prepare(work, worker)
    manifest = native.inventory(
        json.loads((location / "transfer-plan.json").read_text()),
        workflow._active(work)["element_plan"],
    )
    return work, worker, target, report, manifest


def test_explicit_registered_native_actions_are_bound_to_original_occurrences(tmp_path):
    work, _worker, _target, summary, manifest = _manifest(tmp_path)
    assert summary["native_actions"]["action_count"] == 1
    assert manifest["action_count"] == 1
    row, = manifest["actions"]
    source = summary["elements"][1]
    assert row["kind"] == "camera_setup"
    assert row["source_occurrence_ids"] == [source["occurrence_id"]]
    assert row["source_attribution"] == "EXPLICIT_REGISTERED_SOURCE_LOCATION"
    assert row["native_execution_verified"] is False
    assert summary["native_actions"]["approved_for_existing_native_preflight"] is False
    assert manifest["full_cutscene_fidelity_verified"] is False


def test_unregistered_or_foreign_source_native_actions_fail_closed(tmp_path):
    work, _worker, _target, _summary, _manifest_doc = _manifest(tmp_path)
    report = workflow._active(work)["element_plan"]
    for action, expected in [
        ({"kind": "execute_python"}, "builder"),
        ({"kind": "camera_setup", "source_location": "entities[999]"}, "foreign"),
        ({"kind": "audio", "source_location": "entities[1]"}, "registered"),
        ({"kind": "camera_setup", "source_location": "entities[1]",
          "source_ced": "Vendor.SecretProperty"}, "semantic"),
    ]:
        with pytest.raises(ValueError, match=expected):
            native.inventory({"sequence_asset_path": "/Game/Demo/LS_Trial",
                              "actions": [action]}, report)


def test_separate_native_approval_covers_exact_actions_and_legacy_unattributed(tmp_path):
    work, worker, _target, summary, manifest = _manifest(tmp_path, two_actions=True)
    assert manifest["unattributed_count"] == 1
    workflow.acknowledge(work, worker, summary["workflow_sha256"])
    with pytest.raises(native.ElementNativeExecutionError, match="separate explicit"):
        workflow.approve_native_actions(
            work, worker, workflow_sha256=summary["workflow_sha256"],
            inventory_sha256=native.digest(manifest),
            review_all=True, accept_legacy_unattributed=False,
        )
    granted = workflow.approve_native_actions(
        work, worker, workflow_sha256=summary["workflow_sha256"],
        inventory_sha256=native.digest(manifest),
        review_all=True, accept_legacy_unattributed=True,
    )
    assert granted["action_count"] == 2
    assert granted["unattributed_count"] == 1
    assert granted["native_builder_executed"] is False
    latest = workflow.current(work, worker)
    assert latest["native_actions"]["approved_for_existing_native_preflight"] is True
    assert latest["native_execution_authorized"] is False
    assert workflow.require_native_action_authorization(
        work, worker, latest["candidate_id"]
    ) == granted["native_action_authorization_sha256"]
    candidate = json.loads((work / "active-candidate.json").read_text())
    approval_path = (work / "candidates" / candidate["candidate_id"] /
                     "element-native-approval.json")
    permission = json.loads(approval_path.read_text())
    assert permission["full_cutscene_fidelity_verified"] is False
    assert permission["runtime_dispatched"] is False


def test_approved_all_actions_reject_omissions_duplicates_and_stale_plan_hash(tmp_path):
    _work, _worker, _target, summary, manifest = _manifest(tmp_path, two_actions=True)
    values = ["A00000", "A00001"]
    for ids in (values[:-1], values + values[:1], values[::-1], ["A00000", "A00000"]):
        with pytest.raises(native.ElementNativeExecutionError, match="entire immutable"):
            native.authorize(
                manifest, candidate_id=summary["candidate_id"],
                workflow_sha256=summary["workflow_sha256"],
                transfer_plan_sha256="b" * 64,
                approved_action_ids=ids, accept_legacy_unattributed=True,
            )
    consent = native.authorize(
        manifest, candidate_id=summary["candidate_id"],
        workflow_sha256=summary["workflow_sha256"],
        transfer_plan_sha256="b" * 64,
        approved_action_ids=values, accept_legacy_unattributed=True,
    )
    changed = copy.deepcopy(consent)
    changed["transfer_plan_sha256"] = "c" * 64
    changed["authorization_sha256"] = native.digest({
        k: v for k, v in changed.items() if k != "authorization_sha256"
    })
    with pytest.raises(native.ElementNativeExecutionError, match="stale"):
        native.verify_authorization(
            changed, manifest, candidate_id=summary["candidate_id"],
            workflow_sha256=summary["workflow_sha256"],
            transfer_plan_sha256="b" * 64,
        )


def test_exact_grant_is_checked_again_before_engine_mutation_and_receipted(tmp_path):
    work, worker, _target, summary, manifest = _manifest(tmp_path)
    with pytest.raises(workflow.ElementWorkflowError, match="acknowledged"):
        workflow.require_native_action_authorization(
            work, worker, summary["candidate_id"],
        )
    workflow.acknowledge(work, worker, summary["workflow_sha256"])
    with pytest.raises(workflow.ElementWorkflowError, match="Approve"):
        workflow.require_native_action_authorization(
            work, worker, summary["candidate_id"],
        )
    approved = workflow.approve_native_actions(
        work, worker, workflow_sha256=summary["workflow_sha256"],
        inventory_sha256=native.digest(manifest),
        review_all=True, accept_legacy_unattributed=False,
    )
    current = json.loads((work / "active-candidate.json").read_text())
    config = json.loads((work / "connection.json").read_text())
    location = work / "candidates" / current["candidate_id"]
    job_id = "a" * 32
    job = {
        "kind": "cutsceneai.studio.local_unreal_job",
        "job_id": job_id, "candidate_id": summary["candidate_id"],
        "candidate_dir": str(location),
        "csir": config["csir"],
        "mapping": current["mapping_copy"],
        "sequence_path": current["sequence_path"],
        "expected_project": config["target_project"],
        "element_native_authorization_sha256":
            approved["native_action_authorization_sha256"],
    }
    consent, manifest_again = workflow.verify_native_job(work, job)
    native_permission, native_manifest = native_gate.verify_job(
        work, job, worker["scene_inventory"]
    )
    assert native_permission == consent
    assert native_manifest == manifest
    changed_native = copy.deepcopy(worker["scene_inventory"])
    changed_native["native_capabilities"]["cine_camera_actor"] = False
    with pytest.raises(native_gate.NativeElementGateError, match="capability"):
        native_gate.verify_job(work, job, changed_native)
    assert consent["action_count"] == 1
    assert manifest_again == manifest
    receipt_file = location / ("unreal-runtime-receipt-" + job_id + ".json")
    _write(receipt_file, {
        "kind": "cutsceneai.unreal.best_effort_receipt",
        "status": "GENERATED_UNVERIFIED",
        "stage": "complete",
        "transfer_plan_sha256": summary["native_actions"] and
            workflow._active(work)["transfer_plan_sha256"],
    })
    recorded = workflow.record_native_job(work, job)
    assert native_gate.record_job(work, job, worker["scene_inventory"]) == recorded
    assert recorded["action_count"] == 1
    assert recorded["native_builder_completed"] is True
    assert recorded["individual_native_action_readbacks_verified"] is False
    assert recorded["full_cutscene_fidelity_verified"] is False
    assert workflow.record_native_job(work, job) == recorded
    changed = copy.deepcopy(job)
    changed["element_native_authorization_sha256"] = "f" * 64
    with pytest.raises(workflow.ElementWorkflowError, match="approved"):
        workflow.verify_native_job(work, changed)
    receipt_data = json.loads(receipt_file.read_text())
    receipt_data["status"] = "BLOCKED"
    _write(receipt_file, receipt_data)
    with pytest.raises(native.ElementNativeExecutionError, match="completed"):
        workflow.record_native_job(work, job)


def test_plan_or_capability_changed_after_consent_never_reaches_native_worker(tmp_path):
    work, worker, _target, summary, manifest = _manifest(tmp_path)
    workflow.acknowledge(work, worker, summary["workflow_sha256"])
    workflow.approve_native_actions(
        work, worker, workflow_sha256=summary["workflow_sha256"],
        inventory_sha256=native.digest(manifest),
        review_all=True, accept_legacy_unattributed=False,
    )
    location = work / "candidates" / summary["candidate_id"]
    doc = json.loads((location / "transfer-plan.json").read_text())
    doc["actions"][0]["kind"] = "transform"
    _write(location / "transfer-plan.json", doc)
    with pytest.raises(workflow.ElementWorkflowError, match="stale"):
        workflow.require_native_action_authorization(
            work, worker, summary["candidate_id"],
        )


def test_unobserved_editor_capabilities_cannot_grant_native_actions(tmp_path):
    work, worker, _target, _summary, manifest = _manifest(tmp_path)
    worker["connected"] = False
    report = workflow.prepare(work, worker)
    workflow.acknowledge(work, worker, report["workflow_sha256"])
    with pytest.raises(workflow.ElementWorkflowError, match="live native"):
        workflow.approve_native_actions(
            work, worker, workflow_sha256=report["workflow_sha256"],
            inventory_sha256=report["native_actions"]["action_inventory_sha256"],
            review_all=True, accept_legacy_unattributed=True,
        )


def test_worker_checks_action_grant_before_editor_mutation():
    worker = (ROOT / "integrations" / "unreal" /
              "studio_local_editor_worker.py").read_text(encoding="utf-8")
    assert worker.index("studio_element_native_gate.verify_job(") < (
        worker.index("_ensure_target_level(job)", worker.index("def _execute(job):"))
    )
    assert worker.index("studio_element_workflow.verify_native_job(WORKSPACE, job)") < (
        worker.index("studio_auto_scene.run(")
    )
    assert worker.index("studio_element_native_gate.record_job(") > (
        worker.index("build_level_sequence.build_prepared_files(")
    )


def test_engine_reopen_acceptance_recomputes_real_source_bound_occurrences():
    src = (ROOT / "integrations" / "unreal" /
           "studio_native_acceptance.py").read_text(encoding="utf-8")
    assert "target['target']['editor_pid'] != os.getpid()" in src
    assert "studio_element_native_gate.verify_job(" in src
    assert "element3_native_authorization_sha256" in src
    assert "element3_source_occurrence_count" in src
    assert "full_cutscene_fidelity_verified': False" in src
    host = (ROOT / "packages" / "studio" /
            "studio_release_gate.py").read_text(encoding="utf-8")
    assert "studio_element_cinetwin.build(" in host
    assert "element3_native_reopened_attribution" in host
