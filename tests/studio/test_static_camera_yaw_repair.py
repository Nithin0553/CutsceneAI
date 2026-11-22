"""Static camera yaw repair regression: synthetic source, CineTwin and Unreal.

No actual engine was executed. Native editor persistence and rendered framing
require later independently reopened Unreal acceptance.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
for part in ("packages/studio", "packages/ced", "packages/cinetwin",
             "integrations/unreal", "tests/studio", "tools"):
    route = str(ROOT / part)
    if route not in sys.path:
        sys.path.insert(0, route)

import agent_intent_router
import readback_math
import studio_agent_executor
import studio_agent_feedback
import studio_agent_graph
import studio_camera_yaw_evidence as evidence
import studio_camera_yaw_repair as native
import studio_element7_readback as readback
from behavior_compare import compare
from test_element7_native_readback import _put, _scenario


def _yaw_camera(tmp_path, *, yaw=25.0):
    workspace, job, folder = _scenario(
        tmp_path, with_element3=True, complete=True,
        ai_agents_enabled=True, automatic_setup=True,
    )
    target_path = folder / "target-behavior.json"
    target = json.loads(target_path.read_text(encoding="utf-8"))
    quat = list(readback_math.unreal_rpy_to_canonical_quat(0., 0., yaw))
    for frame in target["samples"]:
        row, = [r for r in frame["entities"] if r["entity_id"] == "camera"]
        row["world_transform"]["rotation_xyzw"] = quat
    _put(target_path, target)
    source = json.loads(Path(job["capture"]).read_text())
    sampling = json.loads((folder / "sampling-plan.json").read_text())
    measured = compare(sampling, source, target)
    camera, = [r for r in measured["entities"] if r["entity_id"] == "camera"]
    assert camera["flags"] == ["WORLD_ROTATION_OUTSIDE_TOLERANCE"]
    assert measured["camera_optics"]["status"] == "PASS"
    comparison_path = folder / "comparison.json"
    comparison = json.loads(comparison_path.read_text())
    comparison.update(measured)
    comparison["target_observation_sha256"] = readback._safe_json(target_path)[1]
    comparison["acceptance_status"] = "DIFFERENCES_DETECTED"
    _put(comparison_path, comparison)
    _put(folder / "element7-readback.json",
         readback.build(workspace, job["job_id"], folder))
    return workspace, job, folder


class Camera:
    def __init__(self, label, before):
        self.label = label
        self.roll, self.pitch, self.yaw = before
        self.xyz = [0.,0.,0.]
        self.scale = [1.,1.,1.]
        self.parent = None
        self.native_path = (
            "/Game/Acceptance/L_Stage.L_Stage:PersistentLevel.CameraUnreal"
        )
        self.class_name = "CineCameraActor"
        self.comp = Component(self)
        self.writes = []
        self.mutate_then_raise = False
        self.incorrect = False
        self.translate = False
        self.refuse = False

    def get_actor_label(self):
        return self.label

    def get_path_name(self):
        return self.native_path

    def get_class(self):
        return NS(get_name=lambda: self.class_name)

    def get_attach_parent_actor(self):
        return self.parent

    def get_actor_location(self):
        return NS(x=self.xyz[0],y=self.xyz[1],z=self.xyz[2])

    def get_actor_scale3d(self):
        return NS(x=self.scale[0],y=self.scale[1],z=self.scale[2])

    def get_actor_rotation(self):
        return NS(roll=self.roll,pitch=self.pitch,yaw=self.yaw)

    def get_cine_camera_component(self):
        return self.comp

    def set_actor_rotation(self,rot,teleport):
        assert teleport is True
        self.roll,self.pitch,self.yaw = rot.roll,rot.pitch,rot.yaw
        self.writes.append((self.roll,self.pitch,self.yaw))
        if self.mutate_then_raise:
            self.mutate_then_raise=False
            raise RuntimeError("camera editor changed rotation then raised")
        if self.incorrect:
            self.incorrect=False
            self.yaw += 9
        if self.translate:
            self.translate=False
            self.xyz[0] += 12
        if self.refuse:
            self.refuse=False
            return False
        return True

    def set_actor_location(self,loc,sweep,teleport):
        assert sweep is False and teleport is True
        self.xyz=[loc.x,loc.y,loc.z]
        return True


class Component:
    def __init__(self,actor):
        self.actor=actor
        self.relative_angle=0.
        self.world_drift=0.

    def get_relative_transform(self):
        rad=math.radians(self.relative_angle)/2
        return NS(
            translation=NS(x=0.,y=0.,z=0.),
            scale3d=NS(x=1.,y=1.,z=1.),
            rotation=NS(x=0.,y=0.,z=math.sin(rad),w=math.cos(rad)),
        )

    def get_world_transform(self):
        roll,pitch,yaw=self.actor.roll,self.actor.pitch,self.actor.yaw+self.world_drift
        # Our approved fixture uses pure native yaw and zero roll/pitch.
        assert abs(roll)<0.0001 and abs(pitch)<0.0001
        rad=math.radians(yaw)/2
        return NS(rotation=NS(x=0.,y=0.,z=math.sin(rad),w=math.cos(rad)))


class Track:
    def __init__(self,kind):
        self.kind=kind

    def get_class(self):
        return NS(get_name=lambda:self.kind)


class Binding:
    def __init__(self, tracks=()):
        self.tracks=tracks

    def get_tracks(self):
        return [Track(s) for s in self.tracks]


def _editor(proof, *, roots=(), tracks=()):
    actor=Camera(proof["target_actor_label"],
                 proof["native_rotation_rpy_before_degrees"])
    actor.xyz=list(proof["native_position_before_cm"])
    saves=[]
    api=NS(
        EditorAssetLibrary=NS(does_asset_exist=lambda _: True),
        EditorActorSubsystem=object(),
        MovieSceneSequenceExtensions=NS(
            get_tracks=lambda _: [Track(t) for t in roots],
            get_bindings=lambda _: [Binding(tracks)],
        ),
        Rotator=lambda pitch,yaw,roll:NS(pitch=pitch,yaw=yaw,roll=roll),
        Vector=lambda x,y,z:NS(x=x,y=y,z=z),
        get_editor_subsystem=lambda _: NS(get_all_level_actors=lambda:[actor]),
        load_asset=lambda _: object(),
    )
    return api,actor,saves


def _approved(workspace, job, message="Please fix the camera rotation."):
    feedback=studio_agent_feedback.submit(workspace, job, message)
    proof=evidence.build(workspace, job)
    candidate=Path(job["candidate_dir"])
    receipt=candidate/"setup-camera-yaw-test.json"
    _put(receipt,{"actors_created":[{
        "kind":"entity.camera",
        "name":proof["source_camera_name"],
        "label":proof["target_actor_label"],
        "native_actor_path":
            "/Game/Acceptance/L_Stage.L_Stage:PersistentLevel.CameraUnreal",
    }]})
    job["setup_receipt_file"]=str(receipt)
    _put(workspace/"jobs"/(job["job_id"]+".json"),job)
    request={
        "kind":"cutsceneai.studio.agent_repair_request",
        "schema_version":"1",
        "strategy":"restore_static_camera_actor_yaw",
        "job_id":job["job_id"],
        "candidate_id":job["candidate_id"],
        "expected_project":job["expected_project"],
        "expected_level":job["expected_level"],
        "sequence_path":job["sequence_path"],
        "feedback_id":feedback["feedback_id"],
        "source_camera_occurrence_id":proof["source_camera_occurrence_id"],
        "camera_yaw_repair_sha256":proof["camera_yaw_repair_sha256"],
    }
    return request,proof


def test_source_bound_yaw_candidate_is_stable_and_never_authorizes_model_numbers(
        tmp_path):
    workspace,job,_=_yaw_camera(tmp_path)
    proof=evidence.build(workspace,job)
    assert proof["kind"]==evidence.KIND
    assert proof["eligible"] is True
    assert proof["sample_count"]==5
    assert proof["native_yaw_delta_degrees"]==pytest.approx(-25.)
    assert proof["source_aligned_rotation_rpy_degrees"]==pytest.approx([0.,0.,0.])
    assert proof["native_rotation_rpy_before_degrees"]==pytest.approx([0.,0.,25.])
    assert proof["native_edit_authorized"] is False
    assert proof["full_cutscene_fidelity_verified"] is False
    assert proof["camera_yaw_repair_sha256"]==evidence.position._hash({
        k:v for k,v in proof.items() if k!="camera_yaw_repair_sha256"
    })
    routing=agent_intent_router.route(
        "Please fix the camera rotation.",
        generation_complete=True,
        native_material_fallback_slots=0,
        source_albedo_provenance=False,
        completed_repairs=0,
        repair_budget=2,independent_issues=[],
        camera_yaw_repair_evidence=proof,
    )
    assert routing["disposition"]=="GUARDED_STATIC_CAMERA_YAW_AVAILABLE"
    assert routing["safe_strategies"]==[
        "report_only","restore_static_camera_actor_yaw",
    ]
    assert routing["requires_editor_receipt"] is True
    assert routing["model_can_authorize_native_commands"] is False


@pytest.mark.parametrize("message,accepted",[
    ("Please fix the camera rotation.",True),
    ("Correct the camera yaw.",True),
    ("Restore camera orientation.",True),
    ("Fix camera position and rotation.",False),
    ("Fix camera rotation and lens.",False),
    ("Fix camera animated rotation.",False),
    ("Fix camera pan.",False),
    ("Fix camera pitch.",False),
    ("Fix camera cut timing.",False),
    ("Do not fix the camera rotation.",False),
    ("Fix the character facing.",False),
    ("Fix camera rotation and all scenes.",False),
])
def test_static_camera_yaw_feedback_scope(message,accepted):
    assert evidence.message_requests_yaw(message) is accepted


def test_native_rotation_changes_only_actor_yaw_and_requires_reopened_cinetwin(
        tmp_path,monkeypatch):
    workspace,job,_=_yaw_camera(tmp_path)
    request,proof=_approved(workspace,job)
    api,actor,saves=_editor(proof)
    import studio_auto_scene
    monkeypatch.setattr(studio_auto_scene,"_save_level",
                        lambda *_:saves.append("native-level-saved"))
    result=studio_agent_executor.execute(
        api,workspace,job,request,
        project=job["expected_project"],level=job["expected_level"],
    )
    assert len(actor.writes)==1
    assert actor.writes[0]==pytest.approx((0,0,0))
    assert actor.xyz==pytest.approx(proof["native_position_before_cm"])
    assert saves==["native-level-saved"]
    assert result["changes"]==1
    assert result["native_base_and_component_rotation_readback_verified"] is True
    assert result["native_actor_yaw_error_after_degrees"]<=0.1
    assert result["status"]=="CAMERA_STATIC_YAW_SAVED_REOPENED_CINETWIN_PENDING"
    assert result["persistence_after_editor_restart_verified"] is False
    assert result["cinetwin_reopened_time_grid_verified_after_repair"] is False
    assert result["rendered_camera_facing_verified"] is False
    assert result["full_cutscene_fidelity_verified"] is False


@pytest.mark.parametrize("kind",[
    "stale_hash","stale_feedback","wrong_actor_path","wrong_actor_class",
    "attached_parent","attached_child","duplicate_label",
    "transform_track","nested_shot","timewarp","bad_relative_component",
    "bad_world_component","changed_yaw","changed_position","wrong_scale",
])
def test_native_camera_rotation_rejects_conflicting_owners_and_stale_proof(
        tmp_path,kind):
    workspace,job,_=_yaw_camera(tmp_path)
    request,proof=_approved(workspace,job)
    api,actor,_=_editor(proof)
    if kind=="stale_hash":
        request["camera_yaw_repair_sha256"]="f"*64
    elif kind=="stale_feedback":
        _put(Path(job["candidate_dir"])/
             ("user-feedback-active-"+job["job_id"]+".json"),{
                 "job_id":job["job_id"],"candidate_id":job["candidate_id"],
                 "feedback_id":"e"*32,
             })
    elif kind=="wrong_actor_path":
        actor.native_path="/Game/Foreign/OtherCamera"
    elif kind=="wrong_actor_class":
        actor.class_name="Actor"
    elif kind=="attached_parent":
        actor.parent=object()
    elif kind=="attached_child":
        child=Camera("Child",[0,0,0])
        child.parent=actor
        api.get_editor_subsystem=lambda _:NS(
            get_all_level_actors=lambda:[actor,child],
        )
    elif kind=="duplicate_label":
        another=Camera(actor.label,[0,0,0])
        api.get_editor_subsystem=lambda _:NS(
            get_all_level_actors=lambda:[actor,another],
        )
    elif kind=="transform_track":
        api.MovieSceneSequenceExtensions.get_bindings=lambda _:[
            Binding(["MovieScene3DTransformTrack"]),
        ]
    elif kind=="nested_shot":
        api.MovieSceneSequenceExtensions.get_tracks=lambda _:[
            Track("MovieSceneCinematicShotTrack"),
        ]
    elif kind=="timewarp":
        api.MovieSceneSequenceExtensions.get_tracks=lambda _:[
            Track("MovieSceneTimeWarpTrack"),
        ]
    elif kind=="bad_relative_component":
        actor.comp.relative_angle=12
    elif kind=="bad_world_component":
        actor.comp.world_drift=9
    elif kind=="changed_yaw":
        actor.yaw=28
    elif kind=="changed_position":
        actor.xyz[0]+=3
    else:
        actor.scale[0]=2
    with pytest.raises((native.StaticCameraYawRepairError,
                        evidence.StaticCameraYawError)):
        native.attempt(api,workspace,job,request)
    assert actor.writes==[]


@pytest.mark.parametrize("kind",[
    "setter_mutates_then_raises","setter_wrong_readback",
    "setter_refuses","setter_translates","native_save_fails",
])
def test_native_camera_rotation_partial_mutation_rolls_back_actor_transform(
        tmp_path,monkeypatch,kind):
    workspace,job,_=_yaw_camera(tmp_path)
    request,proof=_approved(workspace,job)
    api,actor,_=_editor(proof)
    if kind=="setter_mutates_then_raises":
        actor.mutate_then_raise=True
    elif kind=="setter_wrong_readback":
        actor.incorrect=True
    elif kind=="setter_refuses":
        actor.refuse=True
    elif kind=="setter_translates":
        actor.translate=True
    else:
        import studio_auto_scene
        monkeypatch.setattr(studio_auto_scene,"_save_level",
                            lambda *_: (_ for _ in ()).throw(
                                RuntimeError("native save interrupted"),
                            ))
    with pytest.raises((native.StaticCameraYawRepairError,RuntimeError)):
        native.attempt(api,workspace,job,request)
    assert actor.roll==pytest.approx(proof["native_rotation_rpy_before_degrees"][0])
    assert actor.pitch==pytest.approx(proof["native_rotation_rpy_before_degrees"][1])
    assert actor.yaw==pytest.approx(proof["native_rotation_rpy_before_degrees"][2])
    assert actor.xyz==pytest.approx(proof["native_position_before_cm"])
    assert len(actor.writes)==2


def test_langgraph_request_is_proof_hash_not_ai_authored_yaw(tmp_path):
    workspace,job,_=_yaw_camera(tmp_path)
    feedback=studio_agent_feedback.submit(
        workspace,job,"Please fix the camera rotation."
    )
    candidate=Path(job["candidate_dir"])
    _put(candidate/("closed-loop-evaluation-"+job["job_id"]+".json"),{
        "kind":"cutsceneai.studio.closed_loop_evaluation",
        "issues":[{"category":"CAMERA_WORLD_ROTATION_DIFFERENCE"}],
    })
    summaries=[]
    state=studio_agent_graph.run_once(
        workspace,job,lambda summary: summaries.append(summary) or {
            "strategy":"restore_static_camera_actor_yaw",
            "reason":"Source/native camera yaw is isolated and constant.",
        },
    )
    assert state["status"]=="WAITING_FOR_UNREAL_AGENT_REPAIR"
    assert state["feedback_id"]==feedback["feedback_id"]
    assert state["intent_routing"]["safe_strategies"]==[
        "report_only","restore_static_camera_actor_yaw",
    ]
    assert summaries[0]["verified_camera_yaw_candidate"]["eligible"] is True
    assert summaries[0]["verified_camera_yaw_candidate"]["native_edit_authorized"] is False
    req_files=list(candidate.glob("agent-request-*.json"))
    assert len(req_files)==1
    request=json.loads(req_files[0].read_text())
    assert request["strategy"]=="restore_static_camera_actor_yaw"
    assert "camera_yaw_repair_sha256" in request
    assert "native_yaw_delta_degrees" not in request
    assert "source_aligned_rotation_rpy_degrees" not in request
    assert "native_rotation_rpy_before_degrees" not in request
    assert state["fidelity_verified"] is False



@pytest.mark.parametrize("case",[
    "animated_source","animated_target","position_difference",
    "source_position_drift","target_position_drift",
    "target_roll","target_pitch","yaw_drift","small_yaw",
    "unbounded_yaw","wrong_scale","bad_time_grid",
    "missing_camera_sample",
])
def test_static_camera_source_grid_denies_animated_or_competing_discrepancy(
        tmp_path,monkeypatch,case):
    # This is an *eligibility policy unit test*, not a forged native pass:
    # original separately-verified Element 7/8 objects stay constant while
    # the sampled source/native fixture is deliberately varied to exercise
    # independent boundary predicates.
    workspace,job,folder=_yaw_camera(tmp_path)
    original_build=readback.build(workspace,job["job_id"],folder)
    review=evidence.repair.build(workspace,job["job_id"],[folder])
    source_path=Path(job["capture"])
    target_path=folder/"target-behavior.json"
    source=json.loads(source_path.read_text())
    target=json.loads(target_path.read_text())
    samples_a=source["samples"]
    samples_b=target["samples"]
    get_camera=lambda frame: next(
        row for row in frame["entities"] if row["entity_id"]=="camera"
    )["world_transform"]
    if case=="animated_source":
        get_camera(samples_a[2])["rotation_xyzw"]=list(
            readback_math.unreal_rpy_to_canonical_quat(0.,0.,4.)
        )
    elif case=="animated_target":
        get_camera(samples_b[2])["rotation_xyzw"]=list(
            readback_math.unreal_rpy_to_canonical_quat(0.,0.,31.)
        )
    elif case=="position_difference":
        get_camera(samples_b[0])["position_m"][0]+=0.07
    elif case=="source_position_drift":
        for frame in samples_a[1:]:
            get_camera(frame)["position_m"][0]+=0.002
    elif case=="target_position_drift":
        for frame in samples_b[1:]:
            get_camera(frame)["position_m"][0]+=0.002
    elif case=="target_roll":
        for frame in samples_b:
            get_camera(frame)["rotation_xyzw"]=list(
                readback_math.unreal_rpy_to_canonical_quat(5.,0.,25.)
            )
    elif case=="target_pitch":
        for frame in samples_b:
            get_camera(frame)["rotation_xyzw"]=list(
                readback_math.unreal_rpy_to_canonical_quat(0.,-15.,25.)
            )
    elif case=="yaw_drift":
        for frame in samples_b[1:]:
            get_camera(frame)["rotation_xyzw"]=list(
                readback_math.unreal_rpy_to_canonical_quat(0.,0.,40.)
            )
    elif case=="small_yaw":
        for frame in samples_b:
            get_camera(frame)["rotation_xyzw"]=list(
                readback_math.unreal_rpy_to_canonical_quat(0.,0.,0.3)
            )
    elif case=="unbounded_yaw":
        for frame in samples_b:
            get_camera(frame)["rotation_xyzw"]=list(
                readback_math.unreal_rpy_to_canonical_quat(0.,0.,120.)
            )
    elif case=="wrong_scale":
        get_camera(samples_b[0])["scale_xyz"][0]=1.3
    elif case=="bad_time_grid":
        samples_b[2]["time_seconds"]+=0.01
    else:
        samples_b[1]["entities"]=[
            row for row in samples_b[1]["entities"]
            if row["entity_id"]!="camera"
        ]
    original_read=evidence.readback._safe_json
    monkeypatch.setattr(evidence.readback,"build",lambda *_:original_build)
    monkeypatch.setattr(evidence.repair,"build",lambda *_:review)
    def synthetic_read(path):
        if Path(path)==source_path:
            return source,"fixture-source"
        if Path(path)==target_path:
            return target,"fixture-target"
        return original_read(path)
    monkeypatch.setattr(evidence.readback,"_safe_json",synthetic_read)
    with pytest.raises(evidence.StaticCameraYawError):
        evidence.build(workspace,job)


def test_camera_yaw_source_authored_camera_track_denied_before_native_edit(
        tmp_path,monkeypatch):
    workspace,job,_=_yaw_camera(tmp_path)
    original=evidence.outcome._context
    def source_track(*args):
        root,candidate,canonical,csir,mapping,compiled=original(*args)
        csir={
            **csir,
            "tracks":[*csir["tracks"],{
                "track_id":"camera-keyframes",
                "ced_type":"transform.track",
                "binding_entity_id":"camera",
            }],
        }
        return root,candidate,canonical,csir,mapping,compiled
    monkeypatch.setattr(evidence.outcome,"_context",source_track)
    with pytest.raises(evidence.StaticCameraYawError,match="animation"):
        evidence.build(workspace,job)


def test_camera_yaw_interrupted_editor_claim_refuses_native_replay(
        tmp_path,monkeypatch):
    from test_langgraph_agent_integration import staged as agent_staged

    workspace,candidate,job,_=agent_staged(tmp_path)
    studio_agent_feedback.submit(
        workspace,job,"Please fix the camera rotation."
    )
    monkeypatch.setattr(evidence,"build",lambda *_:{
        "kind":evidence.KIND,
        "eligible":True,
        "source_camera_occurrence_id":"occ-camera",
        "native_yaw_delta_degrees":-25.,
        "sample_count":5,
        "camera_yaw_repair_sha256":"d"*64,
        "native_edit_authorized":False,
    })
    state=studio_agent_graph.run_once(workspace,job,lambda _:{
        "strategy":"restore_static_camera_actor_yaw",
        "reason":"Only source-bound static camera world yaw.",
    })
    assert state["status"]=="WAITING_FOR_UNREAL_AGENT_REPAIR"
    rid=state["pending_request"]
    (candidate/("agent-claim-"+rid+".json")).write_text(
        '{"status":"interrupted native camera write"}',encoding="utf-8"
    )
    monkeypatch.setattr(native,"attempt",lambda *_:pytest.fail(
        "Native yaw edit must never replay an interrupted claim."
    ))
    api=NS(
        EditorAssetLibrary=NS(does_asset_exist=lambda _:True),
        log_warning=lambda _:None,
    )
    def writer(path,document):
        path.write_text(json.dumps(document),encoding="utf-8")
    assert studio_agent_executor.service_one(
        api,workspace,project=job["expected_project"],
        level=job["expected_level"],save=writer,
    ) is True
    receipt=json.loads((candidate/("agent-receipt-"+rid+".json")).read_text())
    assert receipt["status"]=="REPAIR_FAILED_OR_BLOCKED"
    assert "no automatic replay" in receipt["error"]
    assert studio_agent_executor.service_one(
        api,workspace,project=job["expected_project"],
        level=job["expected_level"],save=writer,
    ) is False
