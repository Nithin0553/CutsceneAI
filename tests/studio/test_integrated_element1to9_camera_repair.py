"""Consolidated Elements 1–9 and expanded guarded camera repair, software only.

All native camera objects below are deterministic stubs; actual Unity/Unreal
engine acceptance, saved/reopened CineTwin and rendering are still required.
"""
from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
for part in ("packages/studio", "packages/ced", "packages/cinetwin",
             "integrations/unreal", "tools", "tests/studio", "tests/cinetwin"):
    loc = str(ROOT / part)
    if loc not in sys.path:
        sys.path.insert(0, loc)

import agent_intent_router
import ced_agent_knowledge as knowledge
import studio_agent_executor
import studio_agent_feedback
import studio_agent_graph
import studio_camera_lens_evidence as lens_evidence
import studio_camera_lens_repair
import studio_element4_validation as element4
import studio_element5_plan as element5
import studio_element6_execution as element6
import studio_element7_readback as element7
import studio_element8_repair as element8
import studio_element9_outcome as element9
import studio_element_cinetwin
import studio_element_investigation
import studio_element_plan
import studio_element_schedule
import studio_element_strategy
from test_element7_native_readback import _put, _scenario


def _camera_mismatch(tmp_path, *, agents=True, automatic=True,
                     target_fov=52.0):
    workspace, job, folder = _scenario(
        tmp_path, with_element3=True, complete=True,
        ai_agents_enabled=agents, automatic_setup=automatic,
    )
    target_path = folder / "target-behavior.json"
    target = json.loads(target_path.read_text())
    for sample in target["samples"]:
        camera = next(x for x in sample["entities"]
                      if x["entity_id"] == "camera")
        native = camera["camera"]
        height = float(native["sensor_height_mm"])
        native["focal_length_mm"] = height / (
            2 * math.tan(math.radians(target_fov) / 2)
        )
        native["vertical_fov_degrees"] = float(target_fov)
    _put(target_path, target)
    # Reconstruct genuine measured CineTwin comparison fields from source
    # and target, never write a hand-authored synthetic PASS status.
    from behavior_compare import compare

    sampling = json.loads((folder / "sampling-plan.json").read_text())
    source = json.loads(Path(job["capture"]).read_text())
    comparator = compare(sampling, source, target)
    assert comparator["camera_optics"]["status"] == "FAIL"
    baseline = json.loads((folder / "comparison.json").read_text())
    baseline.update(comparator)
    baseline["target_observation_sha256"] = element7._safe_json(target_path)[1]
    baseline["acceptance_status"] = "DIFFERENCES_DETECTED"
    _put(folder / "comparison.json", baseline)
    _put(folder / "element7-readback.json",
         element7.build(workspace, job["job_id"], folder))
    return workspace, job, folder


def _authorize(workspace, job, message="Please fix the camera lens FOV."):
    candidate = Path(job["candidate_dir"])
    record = studio_agent_feedback.submit(workspace, job, message)
    return record["feedback_id"], candidate


class FakeComponent:
    def __init__(self, focal):
        self.focal = focal
        self.fail_set = False
        self.incorrect_set = False
        self.filmback = SimpleNamespace(
            get_editor_property=lambda prop: 24 if prop == "sensor_height" else None,
        )
        self.settings = SimpleNamespace(
            get_editor_property=lambda prop: {
                "min_focal_length": 8.0,
                "max_focal_length": 300.0,
            }[prop],
        )

    def get_editor_property(self, prop):
        return {
            "filmback": self.filmback,
            "lens_settings": self.settings,
            "current_focal_length": self.focal,
        }[prop]

    def set_editor_property(self, prop, value):
        assert prop == "current_focal_length"
        if self.fail_set:
            raise RuntimeError("Simulated native setter error")
        self.focal = value + (3 if self.incorrect_set else 0)
        self.incorrect_set = False


class FakeActor:
    def __init__(self, label, component):
        self.label = label
        self.component = component

    def get_actor_label(self):
        return self.label

    def get_attach_parent_actor(self):
        return None

    def get_cine_camera_component(self):
        return self.component


def _fake_api(label, before_focal, *, tracks=None):
    component = FakeComponent(before_focal)
    actor = FakeActor(label, component)
    track_objects = [
        SimpleNamespace(get_class=lambda name=name:
                        SimpleNamespace(get_name=lambda: name))
        for name in (tracks or [])
    ]
    binding = SimpleNamespace(get_tracks=lambda: track_objects)
    group = SimpleNamespace(get_all_level_actors=lambda: [actor])
    api = SimpleNamespace(
        EditorActorSubsystem=object(),
        EditorAssetLibrary=SimpleNamespace(
            does_asset_exist=lambda path: True,
        ),
        MovieSceneSequenceExtensions=SimpleNamespace(
            get_bindings=lambda seq: [binding],
        ),
        get_editor_subsystem=lambda kind: group,
        load_asset=lambda path: object(),
    )
    return api, component


def _request(workspace, job, folder, proof, feedback_id):
    candidate = Path(job["candidate_dir"])
    receipt = candidate / "setup-camera-test.json"
    _put(receipt, {
        "actors_created": [{
            "kind": "entity.camera",
            "name": proof["source_camera_name"],
            "label": proof["target_actor_label"],
        }],
    })
    job["setup_receipt_file"] = str(receipt)
    _put(workspace / "jobs" / (job["job_id"] + ".json"), job)
    return {
        "kind": "cutsceneai.studio.agent_repair_request",
        "schema_version": "1",
        "strategy": "restore_static_camera_lens",
        "job_id": job["job_id"],
        "candidate_id": job["candidate_id"],
        "expected_project": job["expected_project"],
        "expected_level": job["expected_level"],
        "sequence_path": job["sequence_path"],
        "feedback_id": feedback_id,
        "camera_repair_sha256": proof["camera_repair_sha256"],
        "source_camera_occurrence_id": proof["source_camera_occurrence_id"],
    }


def test_1to9_stacked_software_evidence_contract_is_complete(tmp_path):
    workspace, job, folder = _scenario(
        tmp_path, with_element3=True, complete=True,
    )
    candidate = Path(job["candidate_dir"])
    csir, _ = element7._safe_json(Path(job["csir"]))
    mapping, _ = element7._safe_json(Path(job["mapping"]))
    compiled, _ = element7._safe_json(candidate / "transfer-plan.json")
    workflow = element8._snapshot(candidate)
    assert csir["source"]["engine"] == "unity"
    caps = {
        "fbx_asset_import": False, "sequencer_visibility_track": False,
        "cine_camera_actor": True, "sequencer_skeletal_animation_track": True,
    }
    source_knowledge = knowledge.retrieve_all(csir, target_capabilities=caps)
    assert source_knowledge["knowledge_sha256"]
    plan = workflow["element_plan"]
    assert plan["source_occurrence_count"] > 0
    studio_element_plan.verify(plan, csir, source_knowledge, caps)
    scheduled = workflow["element_schedule"]
    studio_element_schedule.verify(scheduled, plan, csir)
    strategies = workflow["element_strategy"]
    studio_element_strategy.verify(
        strategies, plan, scheduled, source_knowledge, csir, caps,
    )
    investigated = studio_element_investigation.build(
        plan, scheduled, strategies, source_knowledge, csir, caps,
    )
    element4.verify(
        workflow["element4_baseline_validation"],
        plan, scheduled, strategies, investigated, source_knowledge,
        csir, caps, global_strategy="native_source",
        allowed_strategies=["native_source", "source_materials"],
    )
    element5.verify(
        workflow["element5_source_bound_plan"], csir, mapping, compiled,
        plan, workflow["element_schedule"], workflow["element_strategy"],
        workflow["element4_baseline_validation"],
    )
    native = element6.inspect(workspace, job)
    assert native["native_replay_allowed"] is False
    original = element7.build(workspace, job["job_id"], folder)
    assert original["native_attempt"]["native_builder_completed"]
    # Element 9 checks the original SAVED observer output, not just a report
    # recomputed in memory during the test.
    _put(folder / "element7-readback.json", original)
    triage = element8.build(workspace, job["job_id"], [folder])
    assert triage["source_occurrence_count"] == plan["source_occurrence_count"]
    attributed = studio_element_cinetwin.build(
        csir, plan, json.loads((folder / "sampling-plan.json").read_text()),
        json.loads(Path(job["capture"]).read_text()),
        json.loads((folder / "target-behavior.json").read_text()),
    )
    assert attributed["source_occurrence_count"] == plan["source_occurrence_count"]
    terminal = element9.build(workspace, job["job_id"], [folder])
    assert terminal["source_occurrence_count"] == (
        plan["source_occurrence_count"]
    )
    assert len(terminal["source_occurrences"]) == (
        plan["source_occurrence_count"]
    )
    assert terminal["element8_repair_plan_sha256"] == triage["repair_plan_sha256"]
    assert terminal["full_cutscene_fidelity_verified"] is False


def test_source_bound_static_cinecamera_review_derived_from_native_samples(tmp_path):
    workspace, job, _folder = _camera_mismatch(tmp_path)
    proof = lens_evidence.build(workspace, job)
    assert proof["eligible"] is True
    assert proof["source_camera_name"] == "Camera"
    assert proof["target_actor_label"] == "CameraUnreal"
    assert proof["source_camera_occurrence_id"].startswith("E")
    assert proof["sample_count"] == 5
    assert proof["target_source_fov_degrees"] == pytest.approx(40)
    assert proof["measured_native_fov_error_degrees"] == pytest.approx(12)
    assert proof["native_focal_after_mm"] == pytest.approx(
        24 / (2 * math.tan(math.radians(20)))
    )
    assert proof["full_cutscene_fidelity_verified"] is False
    assert proof["native_actor_or_sequencer_edited"] is False


def test_camera_lens_cannot_be_auto_repaired_without_explicit_user_request(tmp_path):
    workspace, job, _folder = _camera_mismatch(tmp_path)
    proof = lens_evidence.build(workspace, job)
    for message in (
        "The camera framing is wrong.",
        "Please fix the camera rotation.",
        "Don't fix the camera lens.",
    ):
        assert lens_evidence.message_requests_lens(message) is False
    assert lens_evidence.message_requests_lens("Please fix camera FOV.") is True
    assert agent_intent_router.route(
        "Please fix the camera lens FOV.",
        generation_complete=True, native_material_fallback_slots=0,
        source_albedo_provenance=False, completed_repairs=0,
        repair_budget=2, independent_issues=[],
        camera_lens_repair_evidence=proof,
    )["safe_strategies"] == ["report_only", "restore_static_camera_lens"]
    blocked = agent_intent_router.route(
        "Please fix the camera lens FOV and character position.",
        generation_complete=True, native_material_fallback_slots=0,
        source_albedo_provenance=False, completed_repairs=0,
        repair_budget=2, independent_issues=[],
        camera_lens_repair_evidence=proof,
    )
    assert blocked["safe_strategies"] == ["report_only"]


def test_guarded_native_camera_lens_repair_rolls_back_when_verified_scope_fails(
        tmp_path, monkeypatch):
    workspace, job, folder = _camera_mismatch(tmp_path)
    proof = lens_evidence.build(workspace, job)
    fid, _ = _authorize(workspace, job)
    request = _request(workspace, job, folder, proof, fid)
    api, component = _fake_api(
        proof["target_actor_label"], proof["native_focal_before_mm"],
    )
    saved = []
    monkeypatch.setitem(sys.modules, "studio_auto_scene",
                        SimpleNamespace(_save_level=lambda *args: saved.append(args)))
    result = studio_agent_executor.execute(
        api, workspace, job, request,
        project=job["expected_project"], level=job["expected_level"],
    )
    assert result["status"] == (
        "CAMERA_STATIC_LENS_PROPERTY_SAVED_REOPENED_CINETWIN_PENDING"
    )
    assert result["native_property_readback_verified"] is True
    assert result["cinetwin_reopened_time_grid_verified_after_repair"] is False
    assert result["full_cutscene_fidelity_verified"] is False
    assert component.focal == pytest.approx(proof["native_focal_after_mm"])
    assert len(saved) == 1
    for changed in ("focal", "approval"):
        api2, comp2 = _fake_api(
            proof["target_actor_label"], proof["native_focal_before_mm"],
        )
        if changed == "focal":
            comp2.incorrect_set = True
            with pytest.raises(studio_camera_lens_repair.CameraLensRepairError):
                studio_camera_lens_repair.attempt(
                    api2, workspace, job, request,
                )
            assert comp2.focal == pytest.approx(proof["native_focal_before_mm"])
        else:
            forged = dict(request, camera_repair_sha256="0" * 64)
            with pytest.raises(studio_camera_lens_repair.CameraLensRepairError):
                studio_camera_lens_repair.attempt(
                    api2, workspace, job, forged,
                )
    assert len(saved) == 1


def test_native_cinecamera_repair_refuses_animated_lens_tracks(tmp_path):
    workspace, job, folder = _camera_mismatch(tmp_path)
    proof = lens_evidence.build(workspace, job)
    fid, _ = _authorize(workspace, job)
    request = _request(workspace, job, folder, proof, fid)
    api, component = _fake_api(
        proof["target_actor_label"], proof["native_focal_before_mm"],
        tracks=["MovieSceneFloatTrack"],
    )
    with pytest.raises(studio_camera_lens_repair.CameraLensRepairError,
                       match="property controls"):
        studio_camera_lens_repair.attempt(api, workspace, job, request)
    assert component.focal == pytest.approx(proof["native_focal_before_mm"])


def test_camera_fov_without_element7_evidence_is_diagnosis_only(tmp_path):
    workspace, job, _folder = _scenario(
        tmp_path, with_element3=True, complete=True,
        ai_agents_enabled=True, automatic_setup=True,
    )
    review = lens_evidence
    assert review.message_requests_lens("Fix camera lens FOV.")
    with pytest.raises(lens_evidence.CameraLensEvidenceError):
        lens_evidence.build(workspace, job)
    assert agent_intent_router.route(
        "Fix camera lens FOV.",
        generation_complete=True, native_material_fallback_slots=0,
        source_albedo_provenance=False, completed_repairs=0,
        repair_budget=2, independent_issues=[],
        camera_lens_repair_evidence=None,
    )["safe_strategies"] == ["report_only"]


def test_expanded_repair_requires_single_known_source_camera_and_unmodified_plan(tmp_path):
    workspace, job, _folder = _camera_mismatch(tmp_path)
    source_path = Path(job["csir"])
    original = json.loads(source_path.read_text())
    extra = copy.deepcopy(original["entities"][1])
    extra["entity_id"] = "second-camera"
    extra["name"] = "SecondaryCamera"
    original["entities"].append(extra)
    _put(source_path, original)
    with pytest.raises(lens_evidence.CameraLensEvidenceError):
        lens_evidence.build(workspace, job)


def test_graph_repair_proposal_binds_camera_identity_not_model_numeric_value(tmp_path):
    workspace, job, _folder = _camera_mismatch(tmp_path)
    fid, candidate = _authorize(workspace, job)
    _put(candidate / ("closed-loop-evaluation-" + job["job_id"] + ".json"), {
        "kind": "cutsceneai.studio.closed_loop_evaluation",
        "issues": [{"category": "CAMERA_NATIVE_LENS_DIFFERENCE"}],
    })
    result = studio_agent_graph.run_once(
        workspace, job, lambda summary: {
            "strategy": "restore_static_camera_lens",
            "reason": "Use only the source-backed static camera lens adapter.",
        },
    )
    assert result["feedback_id"] == fid
    assert result["status"] == "WAITING_FOR_UNREAL_AGENT_REPAIR"
    assert result["intent_routing"]["safe_strategies"] == [
        "report_only", "restore_static_camera_lens",
    ]
    requests = list(candidate.glob("agent-request-*.json"))
    assert len(requests) == 1
    native = json.loads(requests[0].read_text())
    assert native["strategy"] == "restore_static_camera_lens"
    assert native["source_camera_occurrence_id"].startswith("E")
    assert "focal_length_mm" not in native
    assert "camera_repair_sha256" in native
    assert result["fidelity_verified"] is False
