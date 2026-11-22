"""Two-shot Unreal section repair with synthetic editor and failure injection.

These mocks verify logic and rollback only. No real Unreal/Unity engine ran.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in ("packages/studio", "packages/cinetwin", "integrations/unreal",
               "tests/studio", "tools"):
    route = str(ROOT / folder)
    if route not in sys.path:
        sys.path.insert(0, route)

import studio_agent_executor
import studio_agent_feedback
import studio_agent_graph
import studio_two_shot_cut_evidence as evidence
import studio_two_shot_cut_repair as native
from test_two_shot_cut_evidence import scenario


class Actor:
    def __init__(self, label):
        self.label = label
        self.path = f"/Game/Stage/L_Switch.L_Switch:PersistentLevel.{label}"
        self.cls = "CineCameraActor"

    def get_actor_label(self):
        return self.label

    def get_class(self):
        return NS(get_name=lambda: self.cls)

    def get_path_name(self):
        return self.path


class Section:
    def __init__(self, first, last, binding, history):
        self.start = first
        self.end = last
        self.binding = binding
        self.history = history
        self.fail_once = False
        self.corrupt_once = False

    def get_camera_binding_id(self):
        return self.binding

    def set_range(self, first, last):
        self.start = first + (1 if self.corrupt_once else 0)
        self.end = last
        self.corrupt_once = False
        self.history.append((self.binding, first, last))
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("editor raised after mutating cut section")


class CameraCutTrack:
    def __init__(self, sections):
        self.sections = sections

    def get_sections(self):
        return self.sections

    def get_class(self):
        return NS(get_name=lambda: "MovieSceneCameraCutTrack")


class OtherTrack:
    def __init__(self, name):
        self.name = name

    def get_class(self):
        return NS(get_name=lambda: self.name)


class Binding:
    def __init__(self, key, tracks=()):
        self.key = key
        self.tracks = list(tracks)

    def get_tracks(self):
        return [OtherTrack(name) for name in self.tracks]


def native_editor(*, switch=22):
    history, saves = [], []
    actors = [Actor("CamLeftNative"), Actor("CamRightNative")]
    a = Section(0, switch, "left-guid", history)
    b = Section(switch, 40, "right-guid", history)
    sections = [a, b]
    track = CameraCutTrack(sections)
    seq = object()
    bindings = [Binding("left-guid"), Binding("right-guid")]
    ext = NS(
        get_tracks=lambda _: [track],
        get_bindings=lambda _: bindings,
        get_binding_id=lambda _, bind: bind.key,
        locate_bound_objects=lambda _, bind, world: [
            actors[0] if bind.key == "left-guid" else actors[1]
        ],
    )
    api = NS(
        MovieSceneCameraCutTrack=CameraCutTrack,
        MovieSceneSequenceExtensions=ext,
        MovieSceneSectionExtensions=NS(
            get_start_frame=lambda section: section.start,
            get_end_frame=lambda section: section.end,
        ),
        UnrealEditorSubsystem=type("EditorWorldType", (), {}),
        EditorActorSubsystem=type("ActorType", (), {}),
        EditorAssetLibrary=NS(
            does_asset_exist=lambda _: True,
            save_loaded_asset=lambda _: saves.append(seq) or True,
        ),
        get_editor_subsystem=lambda _: NS(
            get_editor_world=lambda: object(),
            get_all_level_actors=lambda: actors,
        ),
        load_asset=lambda _: seq,
    )
    return api, a, b, actors, history, saves


def prepared(monkeypatch, tmp_path, message="Please fix the camera cut timing."):
    workspace, job, state = scenario(monkeypatch, tmp_path)
    candidate = Path(job["candidate_dir"])
    candidate.mkdir(parents=True)
    fid = "f" * 32
    stage = candidate / "setup-two-shot.json"
    stage.write_text(json.dumps({
        "actors_created": [{
            "kind": "entity.camera",
            "name": name,
            "label": label,
            "native_actor_path":
                f"/Game/Stage/L_Switch.L_Switch:PersistentLevel.{label}",
        } for name, label in (
            ("CamLeft", "CamLeftNative"),
            ("CamRight", "CamRightNative"),
        )],
    }), encoding="utf-8")
    job["setup_receipt_file"] = str(stage)
    state["canonical"]["setup_receipt_file"] = str(stage)
    (candidate / ("user-feedback-active-" + job["job_id"] + ".json")).write_text(
        json.dumps({
            "feedback_id": fid, "job_id": job["job_id"],
            "candidate_id": job["candidate_id"],
        }), encoding="utf-8",
    )
    (candidate / ("user-feedback-" + fid + ".json")).write_text(json.dumps({
        "kind": "cutsceneai.studio.user_feedback", "feedback_id": fid,
        "job_id": job["job_id"], "candidate_id": job["candidate_id"],
        "message": message,
    }), encoding="utf-8")
    (workspace / "active-job.json").write_text(json.dumps({
        "job_id": job["job_id"],
    }), encoding="utf-8")
    proof = evidence.build(workspace, job)
    request = {
        "kind": "cutsceneai.studio.agent_repair_request",
        "schema_version": "1",
        "strategy": "restore_two_shot_camera_switch",
        "job_id": job["job_id"], "candidate_id": job["candidate_id"],
        "sequence_path": job["sequence_path"],
        "expected_project": job["expected_project"],
        "expected_level": job["expected_level"],
        "feedback_id": fid,
        "two_shot_cut_repair_sha256": proof["two_shot_cut_repair_sha256"],
    }
    monkeypatch.setattr(native, "_load", lambda path: json.loads(
        Path(path).read_text(encoding="utf-8"),
    ))
    return workspace, job, request, proof, state


def test_two_shot_native_moves_shared_boundary_without_overlap_and_without_render_claim(
        monkeypatch, tmp_path):
    workspace, job, request, proof, _ = prepared(monkeypatch, tmp_path)
    api, a, b, _actors, history, saves = native_editor()
    result = studio_agent_executor.execute(
        api, workspace, job, request,
        project=job["expected_project"], level=job["expected_level"],
    )
    assert (a.start, a.end, b.start, b.end) == (0, 20, 20, 40)
    assert history == [("left-guid", 0, 20), ("right-guid", 20, 40)]
    assert len(saves) == 1
    assert result["status"] == "TWO_SHOT_SWITCH_SAVED_REOPENED_CINETWIN_PENDING"
    assert result["two_shot_cut_repair_sha256"] == proof["two_shot_cut_repair_sha256"]
    assert result["native_section_binding_readback_verified"] is True
    assert result["native_shot_order_preserved"] is True
    assert result["cinetwin_reopened_time_grid_verified_after_repair"] is False
    assert result["rendered_camera_switching_verified"] is False
    assert result["full_cutscene_fidelity_verified"] is False
    assert "native_switch_frame_after" in result
    assert "native_switch_frame_after" not in request


def test_two_shot_later_switch_shrinks_second_section_first(
        monkeypatch, tmp_path):
    workspace, job, request, _, state = prepared(monkeypatch, tmp_path)
    native_rows = state["target"]["camera_cut_sections"]["sections"]
    native_rows[0]["end_frame"] = 18
    native_rows[1]["start_frame"] = 18
    old_proof = request["two_shot_cut_repair_sha256"]
    request["two_shot_cut_repair_sha256"] = evidence.build(
        workspace, job,
    )["two_shot_cut_repair_sha256"]
    assert old_proof != request["two_shot_cut_repair_sha256"]
    api, a, b, _, history, _ = native_editor(switch=18)
    native.attempt(api, workspace, job, request)
    assert (a.end, b.start) == (20, 20)
    assert history[:2] == [
        ("right-guid", 20, 40), ("left-guid", 0, 20),
    ]


@pytest.mark.parametrize("case", [
    "stale_feedback", "wrong_request_hash", "different_camera",
    "same_label_replacement", "foreign_binding_object",
    "wrong_camera_class",
    "changed_native_binding", "reversed_native_sections",
    "nested_shot", "subsequence", "time_warp", "root_master",
    "different_original_frame", "camera_added", "missing_camera_path",
])
def test_two_shot_rejects_foreign_bindings_tracks_and_identity_without_mutation(
        monkeypatch, tmp_path, case):
    workspace, job, request, _, _ = prepared(monkeypatch, tmp_path)
    api, a, b, actors, history, saves = native_editor()
    if case == "stale_feedback":
        candidate = Path(job["candidate_dir"])
        (candidate / ("user-feedback-active-" + job["job_id"] + ".json")).write_text(
            json.dumps({"feedback_id": "e" * 32, "job_id": job["job_id"],
                        "candidate_id": job["candidate_id"]}),
            encoding="utf-8",
        )
    elif case == "wrong_request_hash":
        request["two_shot_cut_repair_sha256"] = "0" * 64
    elif case == "different_camera":
        actors[1].label = "AnotherCamera"
    elif case == "same_label_replacement":
        actors[1].path = "/Game/Unrelated/OtherCamera"
    elif case == "foreign_binding_object":
        # The binding resolves a different UObject with the SAME label.
        # The old label-only CineTwin inspector would accept this falsely.
        ext = api.MovieSceneSequenceExtensions
        live = ext.locate_bound_objects
        foreign = Actor("CamRightNative")
        foreign.path = "/Game/Foreign/L_Altered.L_Altered:PersistentLevel.CamRightNative"
        ext.locate_bound_objects = (
            lambda seq, binding, world: [foreign]
            if binding.key == "right-guid" else live(seq, binding, world)
        )
    elif case == "wrong_camera_class":
        actors[1].cls = "Actor"
    elif case == "changed_native_binding":
        b.binding = "left-guid"
    elif case == "reversed_native_sections":
        a.start, a.end = 22, 40
        b.start, b.end = 0, 22
    elif case == "nested_shot":
        api.MovieSceneSequenceExtensions.get_bindings = (
            lambda _: [Binding("left-guid", ["MovieSceneCinematicShotTrack"]),
                       Binding("right-guid")]
        )
    elif case == "subsequence":
        api.MovieSceneSequenceExtensions.get_bindings = (
            lambda _: [Binding("left-guid", ["MovieSceneSubTrack"]),
                       Binding("right-guid")]
        )
    elif case == "time_warp":
        api.MovieSceneSequenceExtensions.get_bindings = (
            lambda _: [Binding("left-guid", ["MovieSceneTimeWarpTrack"]),
                       Binding("right-guid")]
        )
    elif case == "root_master":
        get_tracks = api.MovieSceneSequenceExtensions.get_tracks
        api.MovieSceneSequenceExtensions.get_tracks = (
            lambda seq: [*get_tracks(seq), OtherTrack("MovieSceneCinematicShotTrack")]
        )
    elif case == "different_original_frame":
        a.end = 21
    elif case == "camera_added":
        actors.append(Actor("CamRightNative"))
    else:
        stage = Path(job["setup_receipt_file"])
        record = json.loads(stage.read_text())
        record["actors_created"][1].pop("native_actor_path")
        stage.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises((native.TwoShotNativeRepairError, ValueError)):
        native.attempt(api, workspace, job, request)
    assert history == []
    assert saves == []


@pytest.mark.parametrize("case", [
    "setter_mutates_then_throws", "second_setter_throws",
    "bad_post_edit_readback", "save_returns_false", "save_throws",
])
def test_two_shot_reverts_both_sections_after_partial_write_or_save_error(
        monkeypatch, tmp_path, case):
    workspace, job, request, _, _ = prepared(monkeypatch, tmp_path)
    api, a, b, _, history, saves = native_editor()
    if case == "setter_mutates_then_throws":
        a.fail_once = True
    elif case == "second_setter_throws":
        b.fail_once = True
    elif case == "bad_post_edit_readback":
        a.corrupt_once = True
    elif case == "save_returns_false":
        api.EditorAssetLibrary.save_loaded_asset = lambda _: saves.append("failed") or False
    else:
        def broken(_):
            saves.append("raised")
            raise RuntimeError("save interrupted")
        api.EditorAssetLibrary.save_loaded_asset = broken
    with pytest.raises((native.TwoShotNativeRepairError, RuntimeError)):
        native.attempt(api, workspace, job, request)
    assert (a.start, a.end, b.start, b.end) == (0, 22, 22, 40)
    assert len(history) >= 3
    assert saves == [] if "save" not in case else len(saves) == 1


def test_langgraph_emits_hash_only_source_scoped_two_shot_native_request(
        monkeypatch, tmp_path):
    from test_langgraph_agent_integration import staged as agent_staged

    workspace, candidate, job, _ = agent_staged(tmp_path)
    saved_feedback = studio_agent_feedback.submit(
        workspace, job, "Please fix the camera cut timing.",
    )
    monkeypatch.setattr(evidence, "build", lambda *_: {
        "kind": evidence.KIND, "eligible": True,
        "camera_count": 2, "switch_count": 1,
        "maximum_frame_boundary_error": 2,
        "two_shot_cut_repair_sha256": "d" * 64,
        "native_edit_authorized": False,
    })
    snapshots = []
    state = studio_agent_graph.run_once(workspace, job, lambda summary: (
        snapshots.append(summary) or {
            "strategy": "restore_two_shot_camera_switch",
            "reason": "One source-confirmed two-camera boundary discrepancy.",
        }
    ))
    assert state["status"] == "WAITING_FOR_UNREAL_AGENT_REPAIR"
    assert state["feedback_id"] == saved_feedback["feedback_id"]
    assert state["intent_routing"]["disposition"] == (
        "GUARDED_TWO_SHOT_SWITCH_BOUNDARY_AVAILABLE"
    )
    assert snapshots[0]["verified_two_shot_cut_candidate"]["eligible"] is True
    assert snapshots[0]["verified_two_shot_cut_candidate"]["native_edit_authorized"] is False
    req_files = list(candidate.glob("agent-request-*.json"))
    assert len(req_files) == 1
    request = json.loads(req_files[0].read_text())
    assert request["strategy"] == "restore_two_shot_camera_switch"
    assert request["two_shot_cut_repair_sha256"] == "d" * 64
    assert request["feedback_id"] == saved_feedback["feedback_id"]
    assert not any(
        "frame" in key or "shot" in key and key != "two_shot_cut_repair_sha256"
        for key in request
    )
    assert state["fidelity_verified"] is False


def test_unsupported_multishot_proposal_never_reaches_native_editor(
        monkeypatch, tmp_path):
    from test_langgraph_agent_integration import staged as agent_staged

    workspace, candidate, job, _ = agent_staged(tmp_path)
    studio_agent_feedback.submit(workspace, job, "Fix all camera cuts everywhere.")
    monkeypatch.setattr(evidence, "build", lambda *_: pytest.fail(
        "Multi-shot unbounded feedback must not initiate two-shot proof."
    ))
    state = studio_agent_graph.run_once(workspace, job, lambda _: {
        "strategy": "restore_two_shot_camera_switch", "reason": "unsafe",
    })
    assert state["status"] == "REJECTED_UNSUPPORTED_STRATEGY"
    assert list(candidate.glob("agent-request-*.json")) == []



def test_two_shot_agent_claim_prevents_replay_after_interrupted_native_write(
        monkeypatch, tmp_path):
    from test_langgraph_agent_integration import staged as agent_staged

    workspace, candidate, job, _ = agent_staged(tmp_path)
    studio_agent_feedback.submit(
        workspace, job, "Please fix the camera cut timing."
    )
    monkeypatch.setattr(evidence, "build", lambda *_: {
        "kind": evidence.KIND,
        "eligible": True,
        "camera_count": 2, "switch_count": 1,
        "two_shot_cut_repair_sha256": "d" * 64,
        "native_edit_authorized": False,
    })
    state = studio_agent_graph.run_once(workspace, job, lambda _: {
        "strategy": "restore_two_shot_camera_switch",
        "reason": "One bounded two-shot camera switch mismatch.",
    })
    assert state["status"] == "WAITING_FOR_UNREAL_AGENT_REPAIR"
    claim = candidate / ("agent-claim-" + state["pending_request"] + ".json")
    claim.write_text(
        '{"status":"interrupted editor native mutation"}', encoding="utf-8"
    )
    monkeypatch.setattr(native, "attempt", lambda *_: pytest.fail(
        "Interrupted camera-cut section changes may never replay."
    ))
    api = NS(
        EditorAssetLibrary=NS(does_asset_exist=lambda _: True),
        log_warning=lambda _: None,
    )
    def save(path, document):
        path.write_text(json.dumps(document), encoding="utf-8")

    assert studio_agent_executor.service_one(
        api, workspace, project=job["expected_project"],
        level=job["expected_level"], save=save,
    ) is True
    result_path = candidate / (
        "agent-receipt-" + state["pending_request"] + ".json"
    )
    receipt = json.loads(result_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "REPAIR_FAILED_OR_BLOCKED"
    assert "no automatic replay" in receipt["error"]
    assert studio_agent_executor.service_one(
        api, workspace, project=job["expected_project"],
        level=job["expected_level"], save=save,
    ) is False
