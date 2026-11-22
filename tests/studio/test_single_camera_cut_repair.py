"""Source-grounded single camera cut native repair: fully synthetic test editor.

No actual Sequencer, Unity or Unreal editor was run. Live engine persistence
and rendered camera switching MUST be independently tested later.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
for directory in ("packages/studio", "packages/ced", "packages/cinetwin",
                  "integrations/unreal", "tools", "tests/studio"):
    location = str(ROOT / directory)
    if location not in sys.path:
        sys.path.insert(0, location)

import agent_intent_router
import studio_agent_executor
import studio_agent_feedback
import studio_agent_graph
import studio_camera_cut_evidence as cut
import studio_camera_cut_repair as native_cut
import studio_element7_readback as element7
import studio_element8_repair as element8
from behavior_compare import compare
from test_element7_native_readback import _put, _scenario


def _cut_scene(tmp_path):
    work, job, folder = _scenario(
        tmp_path, with_element3=True, complete=True, camera_cut=True,
        ai_agents_enabled=True, automatic_setup=True,
    )
    native_target = folder / "target-behavior.json"
    target = json.loads(native_target.read_text(encoding="utf-8"))
    target["camera_cut_sections"]["sections"][0]["end_frame"] = 3
    _put(native_target, target)
    sampling = json.loads((folder / "sampling-plan.json").read_text())
    source = json.loads(Path(job["capture"]).read_text())
    measured = compare(sampling, source, target)
    assert measured["camera_cut_timing"]["status"] == "FAIL"
    assert measured["camera_optics"]["status"] == "PASS"
    comparison_path = folder / "comparison.json"
    report = json.loads(comparison_path.read_text())
    report.update(measured)
    report["target_observation_sha256"] = element7._safe_json(native_target)[1]
    report["acceptance_status"] = "DIFFERENCES_DETECTED"
    _put(comparison_path, report)
    _put(folder / "element7-readback.json",
         element7.build(work, job["job_id"], folder))
    return work, job, folder


def _consent(workspace, job, text="Please fix the camera cut timing."):
    result = studio_agent_feedback.submit(workspace, job, text)
    candidate = Path(job["candidate_dir"])
    proof = cut.build(workspace, job)
    setup = candidate / "setup-cut-test.json"
    _put(setup, {
        "actors_created": [{
            "kind": "entity.camera",
            "name": proof["source_camera_name"],
            "label": proof["target_camera_actor_label"],
        }],
    })
    job["setup_receipt_file"] = str(setup)
    _put(workspace / "jobs" / (job["job_id"] + ".json"), job)
    request = {
        "kind": "cutsceneai.studio.agent_repair_request",
        "schema_version": "1",
        "strategy": "restore_single_camera_cut_timing",
        "job_id": job["job_id"],
        "candidate_id": job["candidate_id"],
        "expected_project": job["expected_project"],
        "expected_level": job["expected_level"],
        "sequence_path": job["sequence_path"],
        "feedback_id": result["feedback_id"],
        "camera_cut_repair_sha256": proof["camera_cut_repair_sha256"],
    }
    return request, proof


class Section:
    def __init__(self, start=0, end=3):
        self.start = start
        self.end = end
        self.corrupt_next = False

    def get_camera_binding_id(self):
        return "known-camera-binding"

    def set_range(self, start, end):
        self.start = start + (1 if self.corrupt_next else 0)
        self.end = end
        self.corrupt_next = False


class CameraCutTrack:
    def __init__(self, section):
        self.section = section

    def get_sections(self):
        return [self.section]

    def get_class(self):
        return SimpleNamespace(get_name=lambda: "MovieSceneCameraCutTrack")


def _native(label="CameraUnreal"):
    section = Section()
    track = CameraCutTrack(section)
    actor = SimpleNamespace(get_actor_label=lambda: label)
    binding = object()
    seq = object()
    saved = []
    api = SimpleNamespace(
        EditorAssetLibrary=SimpleNamespace(
            does_asset_exist=lambda _: True,
            save_loaded_asset=lambda item: saved.append(item) or True,
        ),
        MovieSceneSequenceExtensions=SimpleNamespace(
            get_tracks=lambda obj: [track],
            get_bindings=lambda obj: [binding],
            get_binding_id=lambda obj, binding: "known-camera-binding",
            locate_bound_objects=lambda obj, binding, world: [actor],
        ),
        MovieSceneSectionExtensions=SimpleNamespace(
            get_start_frame=lambda item: item.start,
            get_end_frame=lambda item: item.end,
        ),
        UnrealEditorSubsystem=object(),
        MovieSceneCameraCutTrack=CameraCutTrack,
        get_editor_subsystem=lambda kind: SimpleNamespace(
            get_editor_world=lambda: object(),
        ),
        load_asset=lambda path: seq,
    )
    return api, section, saved


def test_exact_single_source_camera_cut_can_be_proposed_not_auto_executed(tmp_path):
    workspace, job, _folder = _cut_scene(tmp_path)
    report = cut.build(workspace, job)
    assert report["eligible"] is True
    assert report["expected_start_frame"] == 0
    assert report["expected_end_frame"] == 4
    assert report["native_start_frame"] == 0
    assert report["native_end_frame"] == 3
    assert report["maximum_frame_boundary_error"] == 1
    assert report["native_edit_authorized"] is False
    assert report["full_cutscene_fidelity_verified"] is False
    review = element8.build(workspace, job["job_id"], [
        Path(job["candidate_dir"]) / "native-acceptance-synthetic",
    ])
    assert review["domain_findings"][1]["status"] == "FAIL"
    intent = agent_intent_router.route(
        "Please fix the camera cut timing.",
        generation_complete=True, native_material_fallback_slots=0,
        source_albedo_provenance=False, completed_repairs=0,
        repair_budget=2, independent_issues=[],
        camera_cut_repair_evidence=report,
    )
    assert intent["safe_strategies"] == [
        "report_only", "restore_single_camera_cut_timing",
    ]
    assert intent["model_can_authorize_native_commands"] is False
    assert not cut.message_requests_cut("Do not fix the camera cut timing.")
    assert not cut.message_requests_cut("Please fix the camera lens FOV.")
    assert not cut.message_requests_cut(
        "Please correct camera cut timing and zoom animation."
    )


def test_single_cut_native_editor_applies_bound_frame_pair_and_requires_reopen(tmp_path):
    workspace, job, _folder = _cut_scene(tmp_path)
    request, proof = _consent(workspace, job)
    api, section, saved = _native()
    outcome = studio_agent_executor.execute(
        api, workspace, job, request,
        project=job["expected_project"], level=job["expected_level"],
    )
    assert (section.start, section.end) == (0, 4)
    assert len(saved) == 1
    assert outcome["status"] == (
        "CAMERA_SINGLE_CUT_SECTION_SAVED_REOPENED_CINETWIN_PENDING"
    )
    assert outcome["camera_cut_repair_sha256"] == proof["camera_cut_repair_sha256"]
    assert outcome["native_section_binding_readback_verified"] is True
    assert outcome["rendered_camera_switching_verified"] is False
    assert outcome["cinetwin_reopened_time_grid_verified_after_repair"] is False
    assert outcome["full_cutscene_fidelity_verified"] is False


def test_native_cut_repair_rejects_wrong_binding_and_rolls_back_failed_readback(tmp_path):
    workspace, job, _folder = _cut_scene(tmp_path)
    request, proof = _consent(workspace, job)
    wrong_api, wrong_section, wrong_saves = _native(label="OtherCamera")
    with pytest.raises(native_cut.CameraCutRepairError):
        native_cut.attempt(wrong_api, workspace, job, request)
    assert (wrong_section.start, wrong_section.end) == (0, 3)
    assert wrong_saves == []
    api, section, saved = _native()
    section.corrupt_next = True
    with pytest.raises(native_cut.CameraCutRepairError, match="differs"):
        native_cut.attempt(api, workspace, job, request)
    assert (section.start, section.end) == (0, 3)
    assert saved == []
    compromised = dict(request, camera_cut_repair_sha256="f" * 64)
    with pytest.raises(native_cut.CameraCutRepairError):
        native_cut.attempt(api, workspace, job, compromised)
    assert saved == []
    assert proof["source_camera_name"] == "Camera"


def test_no_cut_observation_is_report_only_never_an_implicit_new_cut(tmp_path):
    workspace, job, _folder = _scenario(
        tmp_path, with_element3=True, complete=True, camera_cut=False,
        ai_agents_enabled=True, automatic_setup=True,
    )
    with pytest.raises(cut.CameraCutEvidenceError):
        cut.build(workspace, job)
    assert agent_intent_router.route(
        "Please fix the camera cut timing.",
        generation_complete=True, native_material_fallback_slots=0,
        source_albedo_provenance=False, completed_repairs=0,
        repair_budget=2, independent_issues=[],
        camera_cut_repair_evidence=None,
    )["safe_strategies"] == ["report_only"]


def test_cut_agent_dispatch_records_only_source_bound_proof_not_model_frames(tmp_path):
    workspace, job, _folder = _cut_scene(tmp_path)
    submitted = studio_agent_feedback.submit(
        workspace, job, "Please fix the camera cut timing.",
    )
    candidate = Path(job["candidate_dir"])
    _put(candidate / ("closed-loop-evaluation-" + job["job_id"] + ".json"), {
        "kind": "cutsceneai.studio.closed_loop_evaluation",
        "issues": [{"category": "CAMERA_CUT_TIMING_DIFFERENCE"}],
    })
    result = studio_agent_graph.run_once(
        workspace, job, lambda summary: {
            "strategy": "restore_single_camera_cut_timing",
            "reason": "Select only one approved source-bound shot boundary.",
        },
    )
    assert result["feedback_id"] == submitted["feedback_id"]
    assert result["status"] == "WAITING_FOR_UNREAL_AGENT_REPAIR"
    requests = list(candidate.glob("agent-request-*.json"))
    assert len(requests) == 1
    request = json.loads(requests[0].read_text())
    assert request["strategy"] == "restore_single_camera_cut_timing"
    assert "camera_cut_repair_sha256" in request
    assert "expected_start_frame" not in request
    assert "expected_end_frame" not in request
    assert result["fidelity_verified"] is False



def test_camera_cut_save_failure_restores_original_section_without_success(
        tmp_path):
    workspace, job, _folder = _cut_scene(tmp_path)
    request, _proof = _consent(workspace, job)
    api, section, saved = _native()
    api.EditorAssetLibrary.save_loaded_asset = (
        lambda seq: saved.append(seq) or False
    )
    with pytest.raises(native_cut.CameraCutRepairError, match="save"):
        native_cut.attempt(api, workspace, job, request)
    assert (section.start, section.end) == (0, 3)
    assert len(saved) == 1


def test_camera_cut_repair_does_not_modify_subsequence_or_nested_shots(
        tmp_path):
    workspace, job, _folder = _cut_scene(tmp_path)
    request, _proof = _consent(workspace, job)
    api, section, saved = _native()
    nested = SimpleNamespace(
        get_class=lambda: SimpleNamespace(
            get_name=lambda: "MovieSceneCinematicShotTrack",
        ),
    )
    get_tracks = api.MovieSceneSequenceExtensions.get_tracks
    api.MovieSceneSequenceExtensions.get_tracks = (
        lambda seq: [*get_tracks(seq), nested]
    )
    with pytest.raises(native_cut.CameraCutRepairError, match="Nested"):
        native_cut.attempt(api, workspace, job, request)
    assert (section.start, section.end) == (0, 3)
    assert saved == []
