"""Element 7 readback and CineTwin: all engine operations are synthetic.

The validator is production code. Test fixtures are independently constructed
CSIR, original Unity capture, target observation, native persistence/receipts.
No fake observation is presented as real Unity/Unreal acceptance.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for section in ("packages/studio", "packages/ced", "packages/cinetwin",
                "integrations/unreal", "tests/studio", "tests/cinetwin"):
    sys.path.insert(0, str(ROOT / section))

import ced_agent_knowledge as ced
import studio_element4_validation as gate4
import studio_element5_plan as gate5
import studio_element6_execution as execution
import studio_element7_readback as readback
import studio_element_investigation as investigation
import studio_element_native_execution as native_actions
import studio_element_plan as element_plan
import studio_element_schedule as schedule_tool
import studio_element_strategy as strategy_tool
import studio_release_gate as release_gate
from behavior_compare import compare
from sampling_plan import build_plan
from test_element_cinetwin_attribution import _inputs


def _put(path: Path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")


def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scenario(tmp_path, *, attempt=True, complete=False, with_element3=False):
    csir, _conversion, _sampling, source, target = _inputs()
    work = tmp_path / "runs"
    original = tmp_path / "source.csir.json"
    source_capture = tmp_path / "unity-capture.json"
    mapping_file = tmp_path / "mapping.json"
    project = tmp_path / "NativeTest.uproject"
    project.write_text('{"ProjectID": "synthetic-only"}', encoding="utf-8")
    _put(original, csir)
    sampling = build_plan(csir, csir_sha256=_sha(original))
    source["source"] = copy.deepcopy(sampling["source"])
    target["source"] = copy.deepcopy(sampling["source"])
    target["skeletal_bone_maps"] = {"character": {"hips": "pelvis"}}
    target["coverage"]["source_entity_count"] = len(sampling["entities"])
    target["coverage"]["mapped_entity_count"] = 2 + int(complete)
    target["target"] = {
        "engine": "unreal", "engine_version": "5.8",
        "sequence_asset_path": "/Game/Acceptance/LS_Test.LS_Test",
        "editor_pid": 2222,
        "project_file_sha256": _sha(project),
        "project_identity_sha256": hashlib.sha256(
            str(project.resolve()).encode("utf-8") + b"\0"
            + project.read_bytes()
        ).hexdigest(),
    }
    target["quality"] = {
        "method": "slate_post_tick_between_sequencer_seeks",
        "status": "OBSERVED_NOT_YET_PROVEN",
        "ticks_per_sample": 3,
    }
    if complete:
        target["coverage"]["unmapped_source_entities"] = []
        target["coverage"]["sample_count"] = len(sampling["samples"])
        focal = 24 / (2 * math.tan(math.radians(40) / 2))
        for src_sample, dst_sample in zip(source["samples"], target["samples"]):
            dst_sample["entities"].append({
                "entity_id": "audio", "actor_label": "NativeAudioActor",
                "world_transform": copy.deepcopy(
                    src_sample["entities"][2]["world_transform"]
                ),
            })
            camera = next(x for x in dst_sample["entities"]
                          if x["entity_id"] == "camera")
            camera["camera"] = {
                "status": "OBSERVED",
                "lens_basis":
                    "UNREAL_CINE_CAMERA_SENSOR_HEIGHT_AND_FOCAL_LENGTH",
                "sensor_height_mm": 24,
                "focal_length_mm": focal,
                "vertical_fov_degrees": 40,
            }
    _put(source_capture, source)
    seq = "/Game/Acceptance/LS_Test"
    mapping = {
        "sequence_asset_path": seq,
        "overwrite_sequence": False,
        "entities": {
            "Alice": {"actor_label": "AliceUnreal"},
            "Camera": {"actor_label": "CameraUnreal"},
            **({"Sound": {"actor_label": "NativeAudioActor"}}
               if complete else {}),
        },
        "skeletal_bone_maps": {"character": {"hips": "pelvis"}},
    }
    _put(mapping_file, mapping)
    candidate_id = "20261121T183000Z_deadbeef"
    candidate = work / "candidates" / candidate_id
    _put(candidate / "transfer-plan.json", {
        "sequence_asset_path": seq, "actions": [],
    })
    _put(candidate / "session.json", {
        "kind": "cutsceneai.studio.prepared_transfer",
        "source": {
            "csir_path": str(original), "sha256": _sha(original),
        },
        "source_capture": {
            "path": str(source_capture), "sha256": _sha(source_capture),
        },
        "target": {
            "mapping_path": str(mapping_file), "sequence_asset_path": seq,
            "project_path": str(project),
        },
        "artifact_sha256": {
            "transfer-plan.json": _sha(candidate / "transfer-plan.json"),
        },
    })
    native_folder = candidate / "native-acceptance-synthetic"
    workflow = None
    native_permission = ""
    if with_element3:
        caps = {
            "fbx_asset_import": False, "sequencer_visibility_track": False,
            "cine_camera_actor": True,
            "sequencer_skeletal_animation_track": True,
        }
        knowledge = ced.retrieve_all(csir, target_capabilities=caps)
        conversion = element_plan.prepare(csir, knowledge, caps)
        scheduled = schedule_tool.build(conversion, csir)
        strategies = strategy_tool.build(
            conversion, scheduled, knowledge, csir, caps,
        )
        investigated = investigation.build(
            conversion, scheduled, strategies, knowledge, csir, caps,
        )
        validated = gate4.build(
            conversion, scheduled, strategies, investigated, knowledge,
            csir, caps, global_strategy="native_source",
            allowed_strategies=["native_source", "source_materials"],
        )
        transfer = json.loads(
            (candidate / "transfer-plan.json").read_text(encoding="utf-8")
        )
        source_bound = gate5.build(
            csir, mapping, transfer, conversion,
            scheduled, strategies, validated,
        )
        snapshot = {
            "kind": "cutsceneai.studio.element_workflow",
            "schema_version": "1", "candidate_id": candidate_id,
            "source_file_sha256": _sha(original),
            "source_csir_sha256": conversion["source_csir_sha256"],
            "candidate_mapping_sha256": _sha(mapping_file),
            "transfer_plan_sha256": _sha(candidate / "transfer-plan.json"),
            "target_project_identity_sha256": hashlib.sha256(
                str(project.resolve()).encode("utf-8")
            ).hexdigest(),
            "element_plan": conversion,
            "element_schedule": scheduled,
            "element_strategy": strategies,
            "element4_baseline_validation": validated,
            "element5_source_bound_plan": source_bound,
            "native_execution_authorized": False,
            "full_cutscene_fidelity_verified": False,
        }
        workflow = readback._hash(snapshot)
        snapshot["workflow_sha256"] = workflow
        _put(candidate / "element-workflow-active.json", {
            "candidate_id": candidate_id, "workflow_sha256": workflow,
        })
        _put(candidate / ("element-workflow-" + workflow + ".json"), snapshot)
        inventory = native_actions.inventory(transfer, conversion, strategies)
        permission = native_actions.authorize(
            inventory, candidate_id=candidate_id,
            workflow_sha256=workflow,
            transfer_plan_sha256=_sha(candidate / "transfer-plan.json"),
            approved_action_ids=[
                action["action_id"] for action in inventory["actions"]
            ], accept_legacy_unattributed=False,
        )
        native_permission = permission["authorization_sha256"]
        _put(candidate / "element-native-approval.json", permission)
    job_id = "a" * 32
    job = {
        "kind": "cutsceneai.studio.local_unreal_job",
        "schema_version": "0.1.0",
        "job_id": job_id,
        "candidate_id": candidate_id,
        "candidate_dir": str(candidate),
        "expected_project": str(project),
        "expected_level": "/Game/Acceptance/L_Stage",
        "sequence_path": seq, "csir": str(original),
        "capture": str(source_capture),
        "mapping": str(mapping_file),
        "status": "QUEUED", "generation_status": "NOT_STARTED",
        "generation_editor_pid": 1111,
        "ai_agents_enabled": False,
        "ai_conversion_decision_sha256": "",
        "element_native_authorization_sha256": native_permission,
    }
    _put(work / "jobs" / (job_id + ".json"), job)
    _put(work / "active-job.json", {"job_id": job_id})
    _put(work / "active-candidate.json", {
        "candidate_id": candidate_id,
        "sequence_path": seq, "mapping_copy": str(mapping_file),
    })
    if attempt:
        claim = execution.claim(work, job, editor_pid=1111)
        for stage in execution.STAGES[1:]:
            execution.step(work, job, claim, stage)
        _put(candidate / ("unreal-runtime-receipt-" + job_id + ".json"), {
            "kind": "cutsceneai.unreal.best_effort_receipt",
            "status": "GENERATED_UNVERIFIED", "stage": "complete",
            "transfer_plan_sha256": _sha(candidate / "transfer-plan.json"),
        })
        job["status"] = "GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED"
        job["generation_status"] = "GENERATED_UNVERIFIED"
        _put(work / "jobs" / (job_id + ".json"), job)
        receipt = execution.terminal(work, job, claim)
        assert receipt["native_builder_completed"] is True
    else:
        job["status"] = "GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED"
        job["generation_status"] = "GENERATED_UNVERIFIED"
        _put(work / "jobs" / (job_id + ".json"), job)
    _put(native_folder / "sampling-plan.json", sampling)
    _put(native_folder / "target-behavior.json", target)
    _put(native_folder / "persistence.json", {
        "kind": "cutsceneai.studio.persistence_audit",
        "job_id": job_id, "candidate_id": candidate_id,
        "expected_project": str(project),
        "expected_level": job["expected_level"],
        "status": "STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS",
        "native_structure_status": "PASS",
        "restart_verified": True,
        "provenance_status": "COMPLETE",
    })
    result = compare(sampling, source, target)
    expected_status = ("STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE"
                       if complete else "INCOMPLETE_MEASURED_SCOPE")
    assert result["evaluation"]["status"] == "NO_FLAGGED_DIFFERENCES"
    assert result["camera_optics"]["status"] == (
        "PASS" if complete else "INCOMPLETE"
    )
    _put(native_folder / "comparison.json", {
        **result,
        "job_id": job_id, "acceptance_status": expected_status,
        "generation_editor_pid": 1111,
        "observation_editor_pid": 2222,
        "source_capture_sha256": _sha(source_capture),
        "target_observation_sha256": _sha(native_folder / "target-behavior.json"),
        "persistence_sha256": _sha(native_folder / "persistence.json"),
        "sampling_plan_sha256": _sha(native_folder / "sampling-plan.json"),
        "native_persistence_status":
            "STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS",
        "element3_workflow_sha256": workflow,
        "element3_native_authorization_sha256": (
            native_permission or None
        ),
        "element3_source_occurrence_count": (
            conversion["source_occurrence_count"] if workflow else None
        ),
        "full_cutscene_fidelity_verified": False,
    })
    return work, job, native_folder


def test_element7_measured_scope_is_reconstructed_but_never_full_fidelity(tmp_path):
    work, job, folder = _scenario(tmp_path)
    report = readback.build(work, job["job_id"], folder)
    assert report["kind"] == readback.KIND
    assert report["native_attempt"]["status"] == (
        "SOURCE_BOUND_NATIVE_BUILDER_COMPLETED"
    )
    assert report["distinct_reopened_editor_observed"] is True
    assert report["target_tick_sampling_status"] == (
        "TICK_SYNCHRONIZED_FULL_GRID_CLAIMED"
    )
    assert report["source_target_mapping_status"] == (
        "EXACT_PREPARED_MAPPING_OBSERVED"
    )
    assert report["measured_scope_status"] == "NATIVE_MEASURED_SCOPE_INCOMPLETE"
    assert report["sampling_count"] == 5
    assert report["unmapped_entity_count"] == 1
    assert report["camera_lens_status"] == "INCOMPLETE"
    assert "audio_output" in report["unverified_domains"]
    assert "rendered_frame" in report["unverified_domains"]
    assert report["full_cutscene_fidelity_verified"] is False
    assert report["independent_engine_attestation_verified"] is False
    assert report["native_retry_authorized"] is False
    assert report["native_repair_authorized"] is False
    assert "AliceUnreal" not in json.dumps(report)
    assert "/Game/Acceptance" not in json.dumps(report)
    readback.verify(report, work, job["job_id"], folder)


def test_full_measured_grid_can_pass_without_whole_cinematic_fidelity(tmp_path):
    work, job, folder = _scenario(tmp_path, complete=True)
    report = readback.build(work, job["job_id"], folder)
    assert report["measured_scope_status"] == "MEASURED_NATIVE_SCOPE_WITHIN_TOLERANCE"
    assert report["unmapped_entity_count"] == 0
    assert report["camera_lens_status"] == "PASS"
    assert report["native_attempt"]["native_builder_completed"] is True
    assert report["full_cutscene_fidelity_verified"] is False
    assert "event_execution" in report["unverified_domains"]
    assert "rendered_frame" in report["unverified_domains"]


def test_real_source_occurrence_inventory_is_anonymous_and_complete(tmp_path):
    work, job, folder = _scenario(tmp_path, with_element3=True)
    report = readback.build(work, job["job_id"], folder)
    attributed = report["element_occurrence_attribution"]
    assert attributed is not None
    assert attributed["source_occurrence_count"] == len(attributed["per_occurrence"])
    assert attributed["source_occurrence_count"] > 3
    assert attributed["per_occurrence"][0]["occurrence_id"] == "E00000"
    assert all(not row.get("native_verified", False)
               for row in attributed["per_occurrence"])
    assert "Alice" not in json.dumps(report)
    assert "Assets/timeline" not in json.dumps(report)
    readback.verify(report, work, job["job_id"], folder)


def test_legacy_native_builder_without_element6_cannot_gain_provenance(tmp_path):
    work, job, folder = _scenario(tmp_path, attempt=False, complete=True)
    report = readback.build(work, job["job_id"], folder)
    assert report["native_attempt"]["status"] == (
        "LEGACY_NATIVE_ATTEMPT_UNVERIFIED"
    )
    assert report["measured_scope_status"] == "NATIVE_MEASURED_SCOPE_INCOMPLETE"
    assert not report["native_attempt"]["native_builder_completed"]
    assert report["native_attempt"]["native_execution_replay_allowed"] is False


def test_7cm_native_actor_error_is_not_hidden_by_clean_runtime_receipt(tmp_path):
    work, job, folder = _scenario(tmp_path)
    target_path = folder / "target-behavior.json"
    target = json.loads(target_path.read_text())
    for frame in target["samples"]:
        frame["entities"][0]["world_transform"]["position_m"][0] += 0.07
    _put(target_path, target)
    with pytest.raises(readback.Element7ReadbackError, match="disagrees"):
        readback.build(work, job["job_id"], folder)


def test_tampered_self_rehashed_element7_report_is_rejected(tmp_path):
    work, job, folder = _scenario(tmp_path, with_element3=True)
    report = readback.build(work, job["job_id"], folder)
    altered = copy.deepcopy(report)
    altered["measured_scope_status"] = "FULL_FIDELITY_PROVEN"
    altered["full_cutscene_fidelity_verified"] = True
    altered.pop("readback_sha256")
    altered["readback_sha256"] = readback._hash(altered)
    with pytest.raises(readback.Element7ReadbackError, match="modified"):
        readback.verify(altered, work, job["job_id"], folder)


@pytest.mark.parametrize("name", [
    "source_capture", "csir", "mapping", "transfer", "sampling", "persistence",
    "target", "comparison", "uproject",
])
def test_changed_original_native_evidence_never_remains_accepted(tmp_path, name):
    work, job, folder = _scenario(tmp_path)
    paths = {
        "source_capture": Path(job["capture"]),
        "csir": Path(job["csir"]),
        "mapping": Path(job["mapping"]),
        "transfer": folder.parent / "transfer-plan.json",
        "sampling": folder / "sampling-plan.json",
        "persistence": folder / "persistence.json",
        "target": folder / "target-behavior.json",
        "comparison": folder / "comparison.json",
        "uproject": Path(job["expected_project"]),
    }
    report = readback.build(work, job["job_id"], folder)
    path = paths[name]
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises((readback.Element7ReadbackError, ValueError)):
        readback.verify(report, work, job["job_id"], folder)


@pytest.mark.parametrize("field,value", [
    ("generation_editor_pid", 2222),
    ("sequence_path", "/Game/Acceptance/LS_Foreign"),
    ("candidate_id", "20261121T183000Z_11111111"),
])
def test_cross_editor_or_foreign_target_job_is_not_attested(tmp_path, field, value):
    work, job, folder = _scenario(tmp_path)
    job[field] = value
    _put(work / "jobs" / (job["job_id"] + ".json"), job)
    with pytest.raises(readback.Element7ReadbackError):
        readback.build(work, job["job_id"], folder)


def test_comparison_pass_label_is_not_trusted_without_measured_camera_coverage(tmp_path):
    work, job, folder = _scenario(tmp_path)
    comparison_path = folder / "comparison.json"
    comparison = json.loads(comparison_path.read_text())
    comparison["acceptance_status"] = (
        "STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE"
    )
    _put(comparison_path, comparison)
    with pytest.raises(readback.Element7ReadbackError, match="status differs"):
        readback.build(work, job["job_id"], folder)


def test_incomplete_element6_receipt_is_never_promoted_to_builder_completion(tmp_path):
    work, job, folder = _scenario(tmp_path, complete=True)
    receipt_path = folder.parent / (
        "element6-native-receipt-" + job["job_id"] + ".json"
    )
    receipt_path.unlink()
    report = readback.build(work, job["job_id"], folder)
    assert report["native_attempt"]["status"] == "INCOMPLETE_NATIVE_EXECUTION_RECEIPT"
    assert report["measured_scope_status"] == "NATIVE_MEASURED_SCOPE_INCOMPLETE"
    assert report["native_retry_authorized"] is False


def test_reopened_native_record_pins_the_generation_editor_and_receipt(tmp_path):
    work, job, folder = _scenario(tmp_path)
    claim_path = folder.parent / (
        "element6-native-claim-" + job["job_id"] + ".json"
    )
    claim = json.loads(claim_path.read_text())
    claim["editor_pid"] += 1
    claim.pop("claim_sha256")
    claim["claim_sha256"] = readback._hash(claim)
    _put(claim_path, claim)
    with pytest.raises(readback.Element7ReadbackError):
        readback.build(work, job["job_id"], folder)


def test_symlinked_external_native_evidence_is_never_loaded(tmp_path):
    work, job, folder = _scenario(tmp_path)
    unsafe = folder / "target-behavior.json"
    outside = tmp_path / "outside.json"
    outside.write_bytes(unsafe.read_bytes())
    unsafe.unlink()
    unsafe.symlink_to(outside)
    with pytest.raises(readback.Element7ReadbackError, match="unsafe"):
        readback.build(work, job["job_id"], folder)


def test_release_gate_exposes_measured_scope_not_full_cinematic_release(tmp_path):
    work, job, folder = _scenario(tmp_path, complete=True)
    report = readback.build(work, job["job_id"], folder)
    _put(folder / "element7-readback.json", report)
    status = release_gate.assess(work, job["job_id"])
    assert status["checks"]["element7_native_execution_chain"]["status"] == "PASS"
    assert status["checks"]["element7_cinetwin_recomputation"]["status"] == "PASS"
    assert status["checks"]["element7_cinetwin_recomputation"][
        "readback_sha256"
    ] == report["readback_sha256"]
    assert status["release_ready"] is False
    assert status["checks"]["rendered_frame_parity"]["status"] == "INCOMPLETE"
    assert status["fidelity_verified"] is False
    forged = copy.deepcopy(report)
    forged["native_attempt"]["status"] = "ENGINE_FIDELITY_VERIFIED"
    forged["readback_sha256"] = readback._hash({
        k: v for k, v in forged.items() if k != "readback_sha256"
    })
    _put(folder / "element7-readback.json", forged)
    tampered = release_gate.assess(work, job["job_id"])
    assert tampered["checks"]["element7_cinetwin_recomputation"]["status"] == "FAIL"
    assert tampered["release_ready"] is False


def test_native_acceptance_writer_uses_actual_reopened_raw_evidence():
    source = (ROOT / "integrations/unreal" /
              "studio_native_acceptance.py").read_text()
    # The readback is constructed inside the observer's on_complete
    # callback; the callback is defined earlier in source than start().
    assert source.index("def finish(target):") < source.index(
        "studio_element7_readback.build("
    ) < source.index("cinetwin_tick_evaluator.start(")
    assert "on_complete=finish" in source
    assert "plan.get('kind') == 'cinetwin.sampling_plan'" in source
    assert "element7-readback.json" in source
    assert "rig-calibration.json" in source
    assert "mesh-forward-approval.json" in source



def test_recomputed_clean_actor_labels_cannot_override_prepared_mapping(tmp_path):
    """Even a fully recomputed CineTwin report is not authority to remap actors."""
    work, job, folder = _scenario(tmp_path, complete=True)
    target_path = folder / "target-behavior.json"
    target = json.loads(target_path.read_text(encoding="utf-8"))
    for frame in target["samples"]:
        for entity in frame["entities"]:
            if entity["entity_id"] == "camera":
                entity["actor_label"] = "ForeignCamera"
    _put(target_path, target)
    comparison_path = folder / "comparison.json"
    recorded = json.loads(comparison_path.read_text(encoding="utf-8"))
    source = json.loads(Path(job["capture"]).read_text(encoding="utf-8"))
    sampling = json.loads((folder / "sampling-plan.json").read_text(
        encoding="utf-8"
    ))
    recomputed = compare(sampling, source, target)
    assert recomputed["evaluation"]["status"] == "NO_FLAGGED_DIFFERENCES"
    recorded.update(recomputed)
    recorded["target_observation_sha256"] = _sha(target_path)
    _put(comparison_path, recorded)
    with pytest.raises(readback.Element7ReadbackError, match="prepared target mapping"):
        readback.build(work, job["job_id"], folder)


def test_forged_workflow_hash_and_invalid_native_grant_not_accepted(tmp_path):
    work, job, folder = _scenario(tmp_path, with_element3=True)
    baseline = readback.build(work, job["job_id"], folder)
    assert baseline["element_occurrence_attribution"] is not None
    candidate = folder.parent
    pointer = json.loads((candidate / "element-workflow-active.json").read_text())
    snapshot_path = candidate / (
        "element-workflow-" + pointer["workflow_sha256"] + ".json"
    )
    snapshot = json.loads(snapshot_path.read_text())
    snapshot["source_file_sha256"] = "c" * 64
    snapshot["workflow_sha256"] = readback._hash({
        k: v for k, v in snapshot.items() if k != "workflow_sha256"
    })
    _put(snapshot_path, snapshot)
    with pytest.raises(readback.Element7ReadbackError, match="unapproved|foreign"):
        readback.build(work, job["job_id"], folder)
    # A real source record cannot be substituted by an otherwise plausible
    # model/native authorization digest in a different candidate.
    isolated = tmp_path / "separate"
    isolated.mkdir()
    work, job, folder = _scenario(isolated, with_element3=True)
    approval_path = folder.parent / "element-native-approval.json"
    approval = json.loads(approval_path.read_text())
    approval["approved_action_ids"] = ["A99999"]
    approval["authorization_sha256"] = native_actions.digest({
        k: v for k, v in approval.items() if k != "authorization_sha256"
    })
    _put(approval_path, approval)
    with pytest.raises(readback.Element7ReadbackError):
        readback.build(work, job["job_id"], folder)



def test_open_unreal_editor_refreshes_canonical_element7_code_without_restart():
    import studio_planner_sync

    modules = [name for name, _relative in studio_planner_sync.MODULES]
    assert modules.index("studio_element6_execution") < (
        modules.index("studio_element_cinetwin")
    )
    assert modules.index("studio_element_cinetwin") < (
        modules.index("studio_element7_readback")
    )
    assert modules.index("studio_element7_readback") < (
        modules.index("studio_element_native_gate")
    )
