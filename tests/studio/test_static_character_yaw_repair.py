"""Guarded static actor yaw: synthetic-only editor and rollback acceptance.

No real Unreal Editor or source/target rendered parity is claimed. Native
setter values come exclusively from recomputed approved source evidence.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in ("packages/studio", "packages/cinetwin", "packages/ced",
               "integrations/unreal", "tests/studio"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

import studio_agent_executor
import studio_auto_scene
import studio_static_character_yaw_evidence as evidence
import studio_static_character_yaw_repair as native
from test_static_character_yaw_evidence import fixture

ns = SimpleNamespace


class Mesh:
    def get_path_name(self):
        return "/Game/Characters/Guard.Guard"

    def get_editor_property(self, key):
        assert key == "post_process_anim_blueprint"


class Component:
    def __init__(self, actor):
        self.actor = actor
        self.mode = "AnimationMode.ANIMATION_CUSTOM_MODE"
        self.anim_instance = None
        self.postprocess = None
        self.anim_class = None
        self.single_node = None
        self.physics = False
        self.relative_angle = 0.
        self.world_error = 0.

    def get_skeletal_mesh_asset(self):
        return Mesh()

    def get_relative_transform(self):
        angle = math.radians(self.relative_angle) / 2
        return ns(
            translation=ns(x=0., y=0., z=0.),
            rotation=ns(x=0., y=0., z=math.sin(angle), w=math.cos(angle)),
            scale3d=ns(x=1., y=1., z=1.),
        )

    def get_world_transform(self):
        angle = math.radians(self.actor.yaw + self.world_error) / 2
        return ns(rotation=ns(
            x=0., y=0., z=math.sin(angle), w=math.cos(angle),
        ))

    def get_editor_property(self, key):
        if key == "animation_mode":
            return self.mode
        if key == "anim_class":
            return self.anim_class
        if key == "animation_data":
            return ns(anim_to_play=self.single_node)
        raise AttributeError(key)

    def get_animation_mode(self):
        return self.mode

    def get_anim_instance(self):
        return self.anim_instance

    def get_post_process_instance(self):
        return self.postprocess

    def is_simulating_physics(self):
        return self.physics


class Actor:
    def __init__(self):
        self.yaw = self.pitch = self.roll = 0.
        self.location = [0., 0., 0.]
        self.parent = None
        self.component = Component(self)
        self.return_false = False
        self.throw_after_set = False
        self.wrong_after_set = False
        self.translate_after_set = False
        self.writes = []

    def get_actor_label(self):
        return "GuardTarget"

    def get_path_name(self):
        return "/Game/Stage/L_Static.L_Static:PersistentLevel.GuardTarget"

    def get_class(self):
        return ns(get_name=lambda: "SkeletalMeshActor")

    def get_actor_location(self):
        return ns(x=self.location[0], y=self.location[1], z=self.location[2])

    def get_actor_rotation(self):
        return ns(roll=self.roll, pitch=self.pitch, yaw=self.yaw)

    def get_actor_scale3d(self):
        return ns(x=1, y=1, z=1)

    def get_attach_parent_actor(self):
        return self.parent

    def get_components_by_class(self, _):
        return [self.component]

    def set_actor_location(self, new, sweep, teleport):
        assert sweep is False and teleport is True
        self.location = [new.x, new.y, new.z]
        return True

    def set_actor_rotation(self, new, teleport):
        assert teleport is True
        self.writes.append((new.pitch, new.yaw, new.roll))
        self.pitch, self.yaw, self.roll = new.pitch, new.yaw, new.roll
        if self.translate_after_set:
            self.location[0] += 12
            self.translate_after_set = False
        if self.wrong_after_set:
            self.yaw += 10
            self.wrong_after_set = False
        if self.throw_after_set:
            self.throw_after_set = False
            raise RuntimeError("native editor raised after mutating actor")
        if self.return_false:
            self.return_false = False
            return False
        return True


class Track:
    def __init__(self, name):
        self.name = name

    def get_class(self):
        return ns(get_name=lambda: self.name)


class Binding:
    def __init__(self, kinds):
        self.kinds = kinds

    def get_tracks(self):
        return [Track(x) for x in self.kinds]


def editor(actor, *, tracks=(), roots=()):
    return ns(
        EditorAssetLibrary=ns(does_asset_exist=lambda _: True),
        EditorActorSubsystem=object(),
        SkeletalMeshComponent=object(),
        MovieSceneSequenceExtensions=ns(
            get_tracks=lambda _: [Track(k) for k in roots],
            get_bindings=lambda _: [Binding(tracks)],
        ),
        Rotator=lambda pitch, yaw, roll: ns(
            pitch=pitch, yaw=yaw, roll=roll,
        ),
        Vector=lambda x, y, z: ns(x=x, y=y, z=z),
        get_editor_subsystem=lambda _: ns(
            get_all_level_actors=lambda: [actor],
        ),
        load_asset=lambda _: object(),
    )


def staged(monkeypatch, tmp_path):
    workspace, job, docs, *_ = fixture(monkeypatch, tmp_path)
    candidate = Path(job["candidate_dir"])
    candidate.mkdir(parents=True, exist_ok=True)
    project = Path(job["expected_project"])
    project.write_text('{"FileVersion": 3}', encoding="utf-8")
    feedback_id = "b" * 32
    docs["user-feedback-active-" + job["job_id"] + ".json"] = {
        "feedback_id": feedback_id,
        "job_id": job["job_id"], "candidate_id": job["candidate_id"],
    }
    docs["user-feedback-" + feedback_id + ".json"] = {
        "kind": "cutsceneai.studio.user_feedback",
        "feedback_id": feedback_id, "job_id": job["job_id"],
        "candidate_id": job["candidate_id"],
        "message": "Please fix the character facing direction.",
    }
    receipt_path = Path(job["setup_receipt_file"])
    receipt_path.write_text('{"actors_created": []}', encoding="utf-8")
    docs[receipt_path.name] = {"actors_created": [{
        "kind": "entity.character", "name": "Guard", "label": "GuardTarget",
        "native_actor_path":
            "/Game/Stage/L_Static.L_Static:PersistentLevel.GuardTarget",
    }]}
    (workspace / "jobs").mkdir()
    (workspace / "jobs" / (job["job_id"]+".json")).write_text(
        json.dumps(job), encoding="utf-8",
    )
    (workspace / "active-job.json").write_text(json.dumps({
        "job_id": job["job_id"],
    }), encoding="utf-8")
    proof = evidence.build(workspace, job)
    request = {
        "kind": "cutsceneai.studio.agent_repair_request",
        "schema_version": "1",
        "strategy": "restore_static_character_actor_yaw",
        "job_id": job["job_id"], "candidate_id": job["candidate_id"],
        "expected_project": job["expected_project"],
        "expected_level": job["expected_level"],
        "sequence_path": job["sequence_path"],
        "feedback_id": feedback_id,
        "source_entity_id": proof["source_entity_id"],
        "character_yaw_repair_sha256": proof["character_yaw_repair_sha256"],
    }
    return workspace, job, request, proof, docs


def test_native_editor_static_yaw_one_edit_source_derived_and_pending_reopen(
        tmp_path, monkeypatch):
    workspace, job, request, proof, _ = staged(monkeypatch, tmp_path)
    actor = Actor()
    api = editor(actor)
    saves = []
    monkeypatch.setattr(studio_auto_scene, "_save_level",
                        lambda *_: saves.append("native-level-save"))
    result = studio_agent_executor.execute(
        api, workspace, job, request,
        project=job["expected_project"], level=job["expected_level"],
    )
    assert len(actor.writes) == 1
    assert actor.writes[0] == pytest.approx((0, proof["native_yaw_after_degrees"], 0))
    assert actor.yaw == pytest.approx(90)
    assert actor.location == [0, 0, 0]
    assert saves == ["native-level-save"]
    assert result["changes"] == 1
    assert result["status"] == "STATIC_CHARACTER_YAW_SAVED_REOPENED_CINETWIN_PENDING"
    assert result["native_actor_base_readback_verified"] is True
    assert result["native_mesh_world_basis_readback_verified"] is True
    assert result["cinetwin_reopened_time_grid_verified_after_repair"] is False
    assert result["rendered_character_facing_verified"] is False
    assert result["full_cutscene_fidelity_verified"] is False


@pytest.mark.parametrize("case", [
    "stale_proof", "stale_feedback", "unsafe_message", "wrong_staged_actor",
    "skeletal_track", "control_rig", "nested_shot", "imported_mesh_rotation",
    "animation_blueprint", "postprocess", "single_node",
    "single_mode", "physics", "stale_actor_rotation", "bad_world_basis",
])
def test_native_preflight_refuses_unsafe_root_or_retarget_owner(
        tmp_path, monkeypatch, case):
    workspace, job, request, _proof, docs = staged(monkeypatch, tmp_path)
    actor = Actor()
    api = editor(actor)
    if case == "stale_proof":
        request["character_yaw_repair_sha256"] = "c" * 64
    elif case == "stale_feedback":
        docs["user-feedback-active-" + job["job_id"] + ".json"]["feedback_id"] = "c" * 32
    elif case == "unsafe_message":
        docs["user-feedback-" + request["feedback_id"] + ".json"]["message"] = (
            "Please fix the moving character facing."
        )
    elif case == "wrong_staged_actor":
        docs[Path(job["setup_receipt_file"]).name]["actors_created"][0][
            "native_actor_path"
        ] = "/Game/Stage/L_Static.L_Static:PersistentLevel.DifferentActor"
    elif case == "skeletal_track":
        api = editor(actor, tracks=["MovieSceneSkeletalAnimationTrack"])
    elif case == "control_rig":
        api = editor(actor, roots=["MovieSceneControlRigParameterTrack"])
    elif case == "nested_shot":
        api = editor(actor, roots=["MovieSceneCinematicShotTrack"])
    elif case == "imported_mesh_rotation":
        actor.component.relative_angle = 90
    elif case == "animation_blueprint":
        actor.component.anim_instance = object()
    elif case == "postprocess":
        actor.component.postprocess = object()
    elif case == "single_node":
        actor.component.single_node = object()
    elif case == "single_mode":
        actor.component.mode = "AnimationMode.ANIMATION_SINGLE_NODE"
    elif case == "physics":
        actor.component.physics = True
    elif case == "stale_actor_rotation":
        actor.yaw = 30
    else:
        actor.component.world_error = 15
    with pytest.raises((native.StaticCharacterYawRepairError,
                        evidence.StaticCharacterYawError)):
        native.attempt(api, workspace, job, request)
    assert actor.writes == []
    assert actor.yaw == pytest.approx(30 if case == "stale_actor_rotation" else 0)


@pytest.mark.parametrize("failure", [
    "setter_returns_false", "setter_mutates_then_throws", "wrong_native_readback",
    "unexpected_translation", "save_fails",
])
def test_native_yaw_rollback_prevents_partial_editor_mutation(
        tmp_path, monkeypatch, failure):
    workspace, job, request, _, _ = staged(monkeypatch, tmp_path)
    actor = Actor()
    api = editor(actor)
    if failure == "setter_returns_false":
        actor.return_false = True
    elif failure == "setter_mutates_then_throws":
        actor.throw_after_set = True
    elif failure == "wrong_native_readback":
        actor.wrong_after_set = True
    elif failure == "unexpected_translation":
        actor.translate_after_set = True
    else:
        monkeypatch.setattr(studio_auto_scene, "_save_level",
                            lambda *_: (_ for _ in ()).throw(
                                RuntimeError("save interrupted")
                            ))
    with pytest.raises((native.StaticCharacterYawRepairError, RuntimeError)):
        native.attempt(api, workspace, job, request)
    assert actor.yaw == pytest.approx(0)
    assert actor.pitch == pytest.approx(0)
    assert actor.roll == pytest.approx(0)
    assert len(actor.writes) == 2
    assert actor.location == pytest.approx([0, 0, 0])


def test_native_yaw_agent_request_never_contains_model_authored_orientation(
        tmp_path, monkeypatch):
    _workspace, _job, request, proof, _docs = staged(monkeypatch, tmp_path)
    assert request["character_yaw_repair_sha256"] == proof["character_yaw_repair_sha256"]
    assert "native_yaw_after_degrees" not in request
    assert "derived_yaw_correction_degrees" not in request
    assert "actor_rotation" not in request
    assert "native_yaw_before_degrees" not in request


def test_native_executor_rejects_unauthorized_actor_write_before_dispatch(
        tmp_path, monkeypatch):
    workspace, job, request, _, _ = staged(monkeypatch, tmp_path)
    actor = Actor()
    api = editor(actor)
    request["expected_project"] = str(tmp_path / "Other.uproject")
    with pytest.raises(ValueError, match="not authorized"):
        studio_agent_executor.execute(
            api, workspace, job, request,
            project=job["expected_project"], level=job["expected_level"],
        )
    assert actor.writes == []


def test_langgraph_dispatch_and_editor_claim_are_source_id_only_no_replay(
        tmp_path, monkeypatch):
    import studio_agent_feedback
    import studio_agent_graph
    import studio_character_facing_review
    from test_langgraph_agent_integration import staged as graph_staged

    workspace, candidate, job, _ = graph_staged(tmp_path)
    studio_agent_feedback.submit(
        workspace, job, "Please fix the character facing direction."
    )
    proof = {
        "kind": evidence.KIND, "eligible": True,
        "source_entity_id": "guard",
        "source_character_name": "Guard",
        "target_actor_label": "GuardTarget",
        "character_yaw_repair_sha256": "c" * 64,
        "sample_count": 5,
        "native_edit_authorized": False,
    }
    monkeypatch.setattr(evidence, "build", lambda *_: proof)
    monkeypatch.setattr(studio_character_facing_review, "build", lambda *_: {
        "kind": studio_character_facing_review.KIND,
        "status": "REOPENED_CHARACTER_OWNER_DIAGNOSTIC_ONLY",
        "native_owner_observation_available": True,
        "native_edit_authorized": False,
        "model_command_authorized": False,
    })
    seen = []
    choice = lambda summary: (
        seen.append(summary) or {
            "strategy": "restore_static_character_actor_yaw",
            "reason": "Only one calibrated static actor and approved native owner.",
        }
    )
    state = studio_agent_graph.run_once(workspace, job, choice)
    assert state["status"] == "WAITING_FOR_UNREAL_AGENT_REPAIR"
    assert state["chosen_strategy"] == "restore_static_character_actor_yaw"
    assert state["intent_routing"]["safe_strategies"] == [
        "report_only", "restore_static_character_actor_yaw",
    ]
    assert seen[0]["verified_static_character_yaw_candidate"]["eligible"] is True
    assert seen[0]["verified_static_character_yaw_candidate"]["native_edit_authorized"] is False
    request_files = list(candidate.glob("agent-request-*.json"))
    assert len(request_files) == 1
    payload = json.loads(request_files[0].read_text())
    assert payload["character_yaw_repair_sha256"] == "c" * 64
    assert payload["source_entity_id"] == "guard"
    assert {key for key in payload if "yaw" in key} == {
        "character_yaw_repair_sha256",
    }
    assert not any("rotation" in key for key in payload)

    executed = []
    def once(api, root, original, requested):
        claim = candidate / ("agent-claim-" + requested["request_id"] + ".json")
        assert claim.is_file()
        executed.append(requested["request_id"])
        return {
            "status": "STATIC_CHARACTER_YAW_SAVED_REOPENED_CINETWIN_PENDING",
            "changes": 1, "full_cutscene_fidelity_verified": False,
            "cinetwin_reopened_time_grid_verified_after_repair": False,
        }

    monkeypatch.setattr(native, "attempt", once)
    api = ns(
        EditorAssetLibrary=ns(does_asset_exist=lambda _: True),
        log_warning=lambda _: None,
    )
    def writer(path, data):
        path.write_text(json.dumps(data), encoding="utf-8")
    assert studio_agent_executor.service_one(
        api, workspace, project=job["expected_project"],
        level=job["expected_level"], save=writer,
    ) is True
    assert executed == [payload["request_id"]]
    assert studio_agent_executor.service_one(
        api, workspace, project=job["expected_project"],
        level=job["expected_level"], save=writer,
    ) is False
    receipt = json.loads((candidate / (
        "agent-receipt-" + payload["request_id"] + ".json"
    )).read_text())
    assert receipt["full_cutscene_fidelity_verified"] is False
    assert receipt["status"] == "STATIC_CHARACTER_YAW_SAVED_REOPENED_CINETWIN_PENDING"


def test_stale_claim_stops_new_static_character_yaw_attempt(
        tmp_path, monkeypatch):
    import studio_agent_feedback
    import studio_agent_graph
    from test_langgraph_agent_integration import staged as graph_staged

    workspace, candidate, job, _ = graph_staged(tmp_path)
    studio_agent_feedback.submit(
        workspace, job, "Please fix the character facing direction."
    )
    monkeypatch.setattr(evidence, "build", lambda *_: {
        "kind": evidence.KIND, "eligible": True,
        "source_entity_id": "guard", "character_yaw_repair_sha256": "c" * 64,
        "native_edit_authorized": False,
    })
    result = studio_agent_graph.run_once(workspace, job, lambda _: {
        "strategy": "restore_static_character_actor_yaw",
        "reason": "Independent static character pose.",
    })
    assert result["status"] == "WAITING_FOR_UNREAL_AGENT_REPAIR"
    receipt_id = result["pending_request"]
    (candidate / ("agent-claim-" + receipt_id + ".json")).write_text(
        '{"status":"interrupted prior native write"}', encoding="utf-8",
    )
    monkeypatch.setattr(native, "attempt", lambda *_: pytest.fail(
        "Interrupted native actor yaw must never be replayed."
    ))
    def writer(path, data):
        path.write_text(json.dumps(data), encoding="utf-8")
    api = ns(
        EditorAssetLibrary=ns(does_asset_exist=lambda _: True),
        log_warning=lambda _: None,
    )
    assert studio_agent_executor.service_one(
        api, workspace, project=job["expected_project"],
        level=job["expected_level"], save=writer,
    ) is True
    persisted = json.loads((candidate / (
        "agent-receipt-" + receipt_id + ".json"
    )).read_text())
    assert persisted["status"] == "REPAIR_FAILED_OR_BLOCKED"
    assert "no automatic replay" in persisted["error"]
