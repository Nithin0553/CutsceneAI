"""Static camera placement repair uses source/native synthetic fixtures only.

Real Unreal editor save, reopen, CineTwin time-grid and rendered framing are
still separate engine acceptance tasks.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in ("packages/studio", "packages/ced", "packages/cinetwin",
               "integrations/unreal", "tools", "tests/studio"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

import agent_intent_router
import studio_agent_executor
import studio_agent_feedback
import studio_agent_graph
import studio_camera_position_evidence as evidence
import studio_camera_position_repair as native
import studio_element7_readback as readback
from behavior_compare import compare
from test_element7_native_readback import _put, _scenario


def _offset_camera(tmp_path):
    workspace, job, folder = _scenario(
        tmp_path, with_element3=True, complete=True, ai_agents_enabled=True,
        automatic_setup=True,
    )
    target_path = folder / "target-behavior.json"
    target = json.loads(target_path.read_text())
    for frame in target["samples"]:
        camera = next(row for row in frame["entities"]
                      if row["entity_id"] == "camera")
        camera["world_transform"]["position_m"][0] += 0.3
    _put(target_path, target)
    sampling = json.loads((folder / "sampling-plan.json").read_text())
    source = json.loads(Path(job["capture"]).read_text())
    measured = compare(sampling, source, target)
    camera_row = next(x for x in measured["entities"]
                      if x["entity_id"] == "camera")
    assert camera_row["flags"] == ["WORLD_POSITION_OUTSIDE_TOLERANCE"]
    comparison_path = folder / "comparison.json"
    original = json.loads(comparison_path.read_text())
    original.update(measured)
    original["target_observation_sha256"] = readback._safe_json(target_path)[1]
    original["acceptance_status"] = "DIFFERENCES_DETECTED"
    _put(comparison_path, original)
    _put(folder / "element7-readback.json",
         readback.build(workspace, job["job_id"], folder))
    return workspace, job, folder


def _approved(workspace, job, text="Please fix the camera position."):
    feedback = studio_agent_feedback.submit(workspace, job, text)
    proof = evidence.build(workspace, job)
    candidate = Path(job["candidate_dir"])
    setup = candidate / "setup-camera-position-test.json"
    _put(setup, {"actors_created": [{
        "kind": "entity.camera",
        "name": proof["source_camera_name"],
        "label": proof["target_actor_label"],
    }]})
    job["setup_receipt_file"] = str(setup)
    _put(workspace / "jobs" / (job["job_id"] + ".json"), job)
    request = {
        "kind": "cutsceneai.studio.agent_repair_request",
        "schema_version": "1",
        "strategy": "restore_static_camera_position",
        "job_id": job["job_id"],
        "candidate_id": job["candidate_id"],
        "expected_project": job["expected_project"],
        "expected_level": job["expected_level"],
        "sequence_path": job["sequence_path"],
        "feedback_id": feedback["feedback_id"],
        "source_camera_occurrence_id": proof["source_camera_occurrence_id"],
        "camera_position_repair_sha256": proof["camera_position_repair_sha256"],
    }
    return request, proof


class CameraActor:
    def __init__(self, label, coords):
        self.label = label
        self.coords = list(coords)
        self.fail_after_set = False
        self.incorrect_set = False

    def get_actor_label(self):
        return self.label

    def get_attach_parent_actor(self):
        return None

    def get_cine_camera_component(self):
        return object()

    def get_actor_location(self):
        return SimpleNamespace(x=self.coords[0], y=self.coords[1], z=self.coords[2])

    def set_actor_location(self, point, sweep, teleport):
        corrupt = self.incorrect_set
        fail = self.fail_after_set
        self.incorrect_set = False
        self.fail_after_set = False
        self.coords = [point.x + (1 if corrupt else 0), point.y, point.z]
        if fail:
            raise RuntimeError("native setter failed after mutation")


class Track:
    def __init__(self, name):
        self.name = name

    def get_class(self):
        return SimpleNamespace(get_name=lambda: self.name)


class Binding:
    def __init__(self, tracks=()):
        self.tracks = tracks

    def get_tracks(self):
        return [Track(name) for name in self.tracks]


def _editor(proof, *, tracks=(), roots=()):
    actor = CameraActor(proof["target_actor_label"], proof["native_world_before_cm"])
    saved = []
    seq = object()
    api = SimpleNamespace(
        EditorAssetLibrary=SimpleNamespace(does_asset_exist=lambda _: True),
        EditorActorSubsystem=object(),
        MovieSceneSequenceExtensions=SimpleNamespace(
            get_tracks=lambda obj: [Track(name) for name in roots],
            get_bindings=lambda obj: [Binding(tracks)],
        ),
        Vector=lambda x, y, z: SimpleNamespace(x=x, y=y, z=z),
        get_editor_subsystem=lambda _: SimpleNamespace(get_all_level_actors=lambda: [actor]),
        load_asset=lambda _: seq,
    )
    return api, actor, saved


def test_source_position_review_requires_constant_exact_camera_and_user_intent(tmp_path):
    workspace, job, folder = _offset_camera(tmp_path)
    proof = evidence.build(workspace, job)
    assert proof["eligible"] is True
    assert proof["max_world_offset_cm"] == pytest.approx(30)
    assert proof["native_edit_authorized"] is False
    assert evidence.message_requests_position("Please fix camera position.")
    for message in ("Don't fix camera position.", "Fix camera position and lens.",
                    "Fix moving camera position.", "Fix the character position.",
                    "Fix camera rotation.", "Move camera cut timing."):
        assert not evidence.message_requests_position(message)
    route = agent_intent_router.route(
        "Please fix camera position.",
        generation_complete=True, native_material_fallback_slots=0,
        source_albedo_provenance=False, completed_repairs=0,
        repair_budget=2, independent_issues=[],
        camera_position_repair_evidence=proof,
    )
    assert route["safe_strategies"] == [
        "report_only", "restore_static_camera_position",
    ]
    assert route["model_can_authorize_native_commands"] is False
    # Mixed semantic request is not allowed even with the same native proof.
    route = agent_intent_router.route(
        "Fix the camera position and rotation.",
        generation_complete=True, native_material_fallback_slots=0,
        source_albedo_provenance=False, completed_repairs=0,
        repair_budget=2, independent_issues=[],
        camera_position_repair_evidence=None,
    )
    assert route["safe_strategies"] == ["report_only"]


def test_native_static_camera_placement_requires_reopened_fidelity_later(
        tmp_path, monkeypatch):
    workspace, job, _folder = _offset_camera(tmp_path)
    request, proof = _approved(workspace, job)
    api, actor, saved = _editor(proof)
    import studio_auto_scene
    monkeypatch.setattr(studio_auto_scene, "_save_level",
                        lambda *args: saved.append(args))
    result = studio_agent_executor.execute(
        api, workspace, job, request,
        project=job["expected_project"], level=job["expected_level"],
    )
    expected = [a+b for a, b in zip(
        proof["native_world_before_cm"], proof["unreal_offset_cm"],
    )]
    assert actor.coords == pytest.approx(expected)
    assert len(saved) == 1
    assert result["native_base_property_readback_verified"] is True
    assert result["native_base_position_error_after_cm"] <= 0.1
    assert result["cinetwin_reopened_time_grid_verified_after_repair"] is False
    assert result["full_cutscene_fidelity_verified"] is False


def test_camera_placement_rejects_native_transform_owner_and_stale_consent(
        tmp_path):
    workspace, job, _folder = _offset_camera(tmp_path)
    request, proof = _approved(workspace, job)
    api, actor, saved = _editor(proof, tracks=["MovieScene3DTransformTrack"])
    with pytest.raises(native.StaticCameraNativeRepairError, match="ownership"):
        native.attempt(api, workspace, job, request)
    assert actor.coords == pytest.approx(proof["native_world_before_cm"])
    forged = dict(request, camera_position_repair_sha256="f"*64)
    api, actor, saved = _editor(proof)
    with pytest.raises(native.StaticCameraNativeRepairError, match="proof"):
        native.attempt(api, workspace, job, forged)
    assert actor.coords == pytest.approx(proof["native_world_before_cm"])


def test_camera_placement_mutation_failure_rolls_back(tmp_path):
    workspace, job, _folder = _offset_camera(tmp_path)
    request, proof = _approved(workspace, job)
    api, actor, saved = _editor(proof)
    actor.incorrect_set = True
    with pytest.raises(native.StaticCameraNativeRepairError, match="did not reach"):
        native.attempt(api, workspace, job, request)
    assert actor.coords == pytest.approx(proof["native_world_before_cm"])
    api, actor, saved = _editor(proof)
    actor.fail_after_set = True
    with pytest.raises(RuntimeError, match="setter failed"):
        native.attempt(api, workspace, job, request)
    assert actor.coords == pytest.approx(proof["native_world_before_cm"])


def test_agent_dispatch_omits_model_camera_coordinates(tmp_path):
    workspace, job, _folder = _offset_camera(tmp_path)
    feedback = studio_agent_feedback.submit(
        workspace, job, "Please fix the camera position.",
    )
    candidate = Path(job["candidate_dir"])
    _put(candidate / ("closed-loop-evaluation-" + job["job_id"] + ".json"), {
        "kind": "cutsceneai.studio.closed_loop_evaluation",
        "issues": [{"category": "CAMERA_WORLD_POSITION_DIFFERENCE"}],
    })
    state = studio_agent_graph.run_once(
        workspace, job, lambda summary: {
            "strategy": "restore_static_camera_position",
            "reason": "Source/native placement is constant.",
        },
    )
    assert state["status"] == "WAITING_FOR_UNREAL_AGENT_REPAIR"
    assert state["feedback_id"] == feedback["feedback_id"]
    assert state["intent_routing"]["safe_strategies"] == [
        "report_only", "restore_static_camera_position",
    ]
    requests = list(candidate.glob("agent-request-*.json"))
    assert len(requests) == 1
    native_request = json.loads(requests[0].read_text())
    assert native_request["strategy"] == "restore_static_camera_position"
    assert "unreal_offset_cm" not in native_request
    assert "native_world_before_cm" not in native_request
    assert "camera_position_repair_sha256" in native_request
