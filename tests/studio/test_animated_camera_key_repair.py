"""Software-only tests for guarded ONE-source-key animated CineCamera repair."""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT=Path(__file__).resolve().parents[2]
for folder in ("packages/studio","integrations/unreal","packages/cinetwin"):
    path=str(ROOT/folder)
    if path not in sys.path:
        sys.path.insert(0,path)

import agent_intent_router as router
import csir_plan
import studio_camera_key_evidence as proof
import studio_camera_key_repair as native
import studio_camera_motion_contract as contract


def _scenario():
    camera={"entity_id":"cam:1","name":"CAM","ced_type":"entity.camera"}
    plan={"duration_frames":4,"display_rate":{"numerator":2,"denominator":1}}
    csir={"timing":{"source_rate":plan["display_rate"],
                    "playback_start":{"value":0,"rate":{
                        "numerator":1,"denominator":1,
                    }}}}
    keys=[]
    src=[]
    dst=[]
    for i in range(5):
        pos=[float(i*2),0.,0.]
        expected=csir_plan.canonical_position_to_unreal_cm(tuple(pos))
        keys.append({"frame":i,"location_cm":list(expected),
                     "rotation_rpy_degrees":[0.,0.,0.]})
        src.append({"time_seconds":i/2,"entities":[{
            "entity_id":"cam:1","world_transform":{
                "position_m":list(pos),
                "rotation_xyzw":[0.,0.,0.,1.],
                "scale_xyz":[1.,1.,1.],
            },
        }]})
        observed=list(pos)
        if i==2:
            observed[0]+=0.05
        dst.append({"time_seconds":i/2,"entities":[{
            "entity_id":"cam:1","actor_label":"CameraUE",
            "world_transform":{
                "position_m":observed,
                "rotation_xyzw":[0.,0.,0.,1.],
                "scale_xyz":[1.,1.,1.],
            },
        }]})
    action={
        "kind":"transform","entity_name":"CAM","actor_label":"CameraUE",
        "source_behavior_strategy":contract.CAPTURE_STRATEGY,
        "track_name":"CutSceneAI Evaluated Camera World Motion",
        "baked_source_curves":True,"keys":keys,
    }
    return (
        {"samples":src},{"samples":dst},camera,"CameraUE",action,plan,csir,
    )


def _review(*,mutate=None):
    source,target,cam,label,action,plan,csir=_scenario()
    if mutate:
        mutate(source,target,cam,label,action,plan,csir)
    return proof._analyze_grid(source,target,cam,label,action,plan,csir)


def test_evaluated_camera_source_one_position_axis_key_is_reviewable():
    report=_review()
    assert report["source_key_frame"]==2
    assert report["native_channel_index"]==1
    assert report["native_source_position_error_cm"]==pytest.approx(5)
    assert report["source_key_value_cm"]==400
    assert report["native_key_value_before_cm"]==405
    assert report["sample_count"]==5


@pytest.mark.parametrize("mutate,reason",[
    (lambda src,dst,*_:dst["samples"][3]["entities"][0]["world_transform"][
        "position_m"].__setitem__(0,6.08),"exactly one"),
    (lambda src,dst,*_:dst["samples"][2]["entities"][0]["world_transform"][
        "position_m"].__setitem__(1,0.04),"exactly one"),
    (lambda src,dst,*_:dst["samples"][2]["entities"][0]["world_transform"][
        "position_m"].__setitem__(0,4.50),"safe single-key"),
    (lambda src,dst,*_:dst["samples"][2]["entities"][0]["world_transform"][
        "rotation_xyzw"].__setitem__(2,0.2),"orientation"),
    (lambda src,dst,*_:dst["samples"][2]["entities"][0]["world_transform"][
        "scale_xyz"].__setitem__(1,2),"scale"),
    (lambda src,dst,*_:src["samples"][2]["entities"][0]["world_transform"][
        "position_m"].__setitem__(0,2),"compiled"),
    (lambda src,dst,*_:dst["samples"][2].update(time_seconds=1.25),
     "missing/duplicated"),
    (lambda src,dst,*_:dst["samples"].append(copy.deepcopy(
        dst["samples"][1])),"missing/duplicated"),
    (lambda src,dst,*_:dst["samples"][0]["entities"][0].update(
        actor_label="Different"),"not unique"),
])
def test_discrepancy_proof_fails_closed_on_competing_domains(mutate,reason):
    with pytest.raises(proof.AnimatedCameraKeyError,match=reason):
        _review(mutate=mutate)


@pytest.mark.parametrize("message,expected",[
    ("Fix animated camera position keyframe",True),
    ("Repair moving CineCamera location keyed frame",True),
    ("Fix camera position",False),
    ("Fix all animated camera position keyframes",False),
    ("Fix animated camera rotation keyframe",False),
    ("Fix animated camera position keyframe and lens",False),
    ("Never fix animated camera position keyframe",False),
    ("Fix animated camera position keyframe on rig",False),
    ("Fix animated camera position keyframe and shot",False),
])
def test_only_explicit_single_camera_xyz_key_language_is_eligible(message,expected):
    assert proof.message_requests_key(message) is expected


def test_intent_cannot_authorize_without_exact_proof_and_no_budget():
    shot=_review()
    eligible={
        "kind":proof.KIND,"eligible":True,"native_edit_authorized":False,
        "source_key_frame":shot["source_key_frame"],
        "native_channel_index":shot["native_channel_index"],
        "animated_camera_key_repair_sha256":"a"*64,
    }
    def route(msg,*,evidence=eligible,limit=0):
        return router.route(
            msg,generation_complete=True,
            native_material_fallback_slots=0,
            source_albedo_provenance=False,
            completed_repairs=limit,repair_budget=2,
            independent_issues=[],animated_camera_key_evidence=evidence,
        )
    allowed=route("Fix animated camera position keyframe")
    assert allowed["safe_strategies"]==[
        "report_only",proof.STRATEGY,
    ]
    assert route("Fix camera position keyframe")["safe_strategies"]==["report_only"]
    assert route("Fix animated camera position keyframe",limit=2)[
        "safe_strategies"]==["report_only"]
    invalid=dict(eligible,source_key_frame=2.5)
    assert route("Fix animated camera position keyframe",evidence=invalid)[
        "safe_strategies"]==["report_only"]


class FakeKey:
    def __init__(self,frame,value,*,fail_after=False):
        self.frame=frame
        self.value=float(value)
        self.fail_after=fail_after
    def get_time(self,unit):
        assert unit=="DISPLAY_RATE"
        return NS(frame_number=NS(value=self.frame),sub_frame=0.)
    def get_value(self):
        return self.value
    def get_interpolation_mode(self):
        return "RCIM_LINEAR"
    def set_value(self,new):
        self.value=float(new)
        if self.fail_after:
            raise RuntimeError("Setter mutated then threw.")


class FakeChannel:
    def __init__(self,keys=None,default=1):
        self.keys=list(keys or [])
        self.default=default
    def get_keys(self):
        return self.keys
    def get_default(self):
        return self.default
    def has_default(self):
        return True


class FakeSection:
    def __init__(self,action,*,diff=5):
        self.channels=[]
        for axis in range(6):
            expected=[
                (*row["location_cm"],*row["rotation_rpy_degrees"])[axis]
                for row in action["keys"]
            ]
            self.channels.append(FakeChannel([
                FakeKey(i,value+(diff if axis==1 and i==2 else 0))
                for i,value in enumerate(expected)
            ]))
        self.channels.extend(FakeChannel() for _ in range(3))
    def get_all_channels(self):
        return list(self.channels)
    def is_active(self):
        return True
    def get_blend_type(self):
        return NS(is_valid=True,blend_type="ABSOLUTE")


API=NS(MovieSceneTimeUnit=NS(DISPLAY_RATE="DISPLAY_RATE"),
       RichCurveInterpMode=NS(RCIM_LINEAR="RCIM_LINEAR"))


def _native():
    _,_,_,_,action,_,_=_scenario()
    section=FakeSection(action)
    report=_review()
    return action,section,report


def test_native_one_key_live_grid_all_other_tracks_unchanged():
    action,section,report=_native()
    key,previous=native._read_channels(API,section,action,repair=report)
    assert previous==pytest.approx(405)
    key.set_value(400)
    assert len(section.channels[1].get_keys())==5
    assert all(key.get_value()==pytest.approx(1)
               for c in section.channels[6:9]
               for key in c.get_keys())  # none, defaults inspected above


@pytest.mark.parametrize("tamper",[
    lambda s:s.channels[0].keys[3].set_value(15),
    lambda s:s.channels[3].keys[1].set_value(40),
    lambda s:s.channels[1].keys.append(FakeKey(5,123)),
    lambda s:s.channels[1].keys[2].__setattr__("frame",3),
    lambda s:s.channels[5].keys[0].__setattr__("frame",0.25),
    lambda s:s.channels[7].__setattr__("default",0),
    lambda s:s.channels[8].keys.append(FakeKey(1,1)),
    lambda s:s.channels.pop(),
    lambda s:s.channels[1].keys[2].set_value(900),
])
def test_native_preflight_refuses_modified_or_competing_keys(tamper):
    action,section,report=_native()
    tamper(section)
    with pytest.raises(native.AnimatedCameraNativeError):
        native._read_channels(API,section,action,repair=report)


def test_native_single_key_transaction_confirms_save_and_does_not_retry(monkeypatch,tmp_path):
    _,section,review=_native()
    _,_,_,_,action,_,_=_scenario()
    setup=tmp_path/"setup.json"
    setup.write_text('{"actors_created": []}',encoding="utf-8")
    (tmp_path/"transfer-plan.json").write_text(__import__("json").dumps({
        "duration_frames":4,"actions":[action],
    }),encoding="utf-8")
    jid="a"*32
    fid="b"*32
    job={
        "candidate_dir":str(tmp_path),"job_id":jid,
        "candidate_id":"20261122T000000Z_aaaaaaaa",
        "setup_receipt_file":str(setup),"sequence_path":"/Game/Scene",
    }
    expected_proof={
        **review,
        "source_camera_name":"CAM","target_actor_label":"CameraUE",
        "source_camera_occurrence_id":"occurrence:1",
        "source_camera_action_sha256":proof.position._hash(action),
        "animated_camera_key_repair_sha256":"f"*64,
    }
    request={
        "strategy":proof.STRATEGY,
        "feedback_id":fid,
        "animated_camera_key_repair_sha256":"f"*64,
        "source_camera_occurrence_id":"occurrence:1",
    }
    monkeypatch.setattr(native.evidence,"build",lambda *args:expected_proof)
    def read(path):
        path=str(path)
        if "active" in path:
            return {"feedback_id":fid,"job_id":jid,
                    "candidate_id":job["candidate_id"]}
        if fid in path:
            return {"kind":"cutsceneai.studio.user_feedback",
                    "feedback_id":fid,"job_id":jid,
                    "candidate_id":job["candidate_id"],
                    "message":"Fix animated camera position keyframe"}
        return {"actors_created":[]}
    monkeypatch.setattr(native,"_load",read)
    monkeypatch.setattr(native,"_live_owner",lambda *args:section)
    api=NS(load_asset=lambda s: NS(),MovieSceneTimeUnit=API.MovieSceneTimeUnit,
           RichCurveInterpMode=API.RichCurveInterpMode,
           EditorAssetLibrary=NS(save_loaded_asset=lambda s:True))
    old=section.channels[1].keys[2]
    result=native.attempt(api,tmp_path,job,request)
    assert result["status"]==(
        "ONE_ANIMATED_CAMERA_POSITION_KEY_SAVED_REOPENED_CINETWIN_PENDING"
    )
    assert result["native_key_difference_after_cm"]==0
    assert old.get_value()==400
    assert result["cinetwin_reopened_after_repair_verified"] is False
    assert result["rendered_camera_motion_verified"] is False
    # A failed native save rolls a mutated key back instead of claiming pass.
    _,failing_section,_=_native()
    monkeypatch.setattr(native,"_live_owner",lambda *args:failing_section)
    api.EditorAssetLibrary.save_loaded_asset=lambda s:False
    with pytest.raises(native.AnimatedCameraNativeError,match="save"):
        native.attempt(api,tmp_path,job,request)
    assert failing_section.channels[1].keys[2].get_value()==405


def test_mutate_then_throw_native_key_setter_rolls_back(monkeypatch,tmp_path):
    # A low-level setter can mutate an Unreal object and then raise. Test the
    # rollback boundary from a separate callback, not only normal return.
    _,section,review=_native()
    key=section.channels[1].keys[2]
    key.fail_after=True
    key.set_value=lambda val: setattr(key,"value",float(val)) or (
        (_ for _ in ()).throw(RuntimeError("native setter threw"))
        if float(val)!=405 else None
    )
    _,_,_,_,action,_,_=_scenario()
    setup=tmp_path/"setup.json"
    setup.write_text('{"actors_created": []}',encoding="utf-8")
    (tmp_path/"transfer-plan.json").write_text(__import__("json").dumps({
        "duration_frames":4,"actions":[action],
    }),encoding="utf-8")
    jid="a"*32;fid="b"*32
    job={"candidate_dir":str(tmp_path),"job_id":jid,
         "candidate_id":"20261122T000000Z_aaaaaaaa",
         "setup_receipt_file":str(setup),"sequence_path":"/Game/Scene"}
    expected={
        **review,"source_camera_name":"CAM","target_actor_label":"CameraUE",
        "source_camera_occurrence_id":"occurrence:1",
        "source_camera_action_sha256":proof.position._hash(action),
        "animated_camera_key_repair_sha256":"f"*64,
    }
    monkeypatch.setattr(native.evidence,"build",lambda *args:expected)
    monkeypatch.setattr(native,"_live_owner",lambda *args:section)
    monkeypatch.setattr(native,"_load",lambda path: (
        {"feedback_id":fid,"job_id":jid,"candidate_id":job["candidate_id"]}
        if "active" in str(path) else
        {"kind":"cutsceneai.studio.user_feedback","feedback_id":fid,
         "job_id":jid,"candidate_id":job["candidate_id"],
         "message":"Fix animated camera position keyframe"}
        if fid in str(path) else {"actors_created":[]}
    ))
    req={"strategy":proof.STRATEGY,"feedback_id":fid,
         "animated_camera_key_repair_sha256":"f"*64,
         "source_camera_occurrence_id":"occurrence:1"}
    with pytest.raises(RuntimeError,match="native setter"):
        native.attempt(NS(load_asset=lambda s:NS(),
                          MovieSceneTimeUnit=API.MovieSceneTimeUnit,
                          RichCurveInterpMode=API.RichCurveInterpMode,
                          EditorAssetLibrary=NS(save_loaded_asset=lambda s:True)),
                       tmp_path,job,req)
    assert key.get_value()==405



def test_native_camera_binding_must_be_original_staged_uobject_not_label_only():
    action,section,_=_native()
    path="/Game/Test.PersistentLevel.CineCameraActor_5"
    class FakeActor:
        def __init__(self):
            self.label="CameraUE"
            self.path=path
            self.parent=None
        def get_path_name(self):
            return self.path
        def get_actor_label(self):
            return self.label
        def get_class(self):
            return NS(get_name=lambda:"CineCameraActor")
        def get_attach_parent_actor(self):
            return self.parent
        def get_cine_camera_component(self):
            return NS(get_path_name=lambda:path+".CameraComponent")
    class FakeTrack:
        def __init__(self,name,section=None):
            self.name=name
            self.section=section
        def get_class(self):
            return NS(get_name=lambda:self.name)
        def get_display_name(self):
            return "CutSceneAI Evaluated Camera World Motion"
        def get_sections(self):
            return [self.section] if self.section is not None else []
    actor=FakeActor()
    track=FakeTrack("MovieScene3DTransformTrack",section)
    root=FakeTrack("MovieSceneCameraCutTrack")
    binding=NS(get_tracks=lambda:[track],owner=actor)
    native_world=NS(get_editor_world=lambda:NS())
    actor_scene=NS(get_all_level_actors=lambda:[actor])
    roots=[root]
    ext=NS(
        get_bindings=lambda seq:[binding],
        get_tracks=lambda seq:list(roots),
        locate_bound_objects=lambda seq,b,w:[b.owner],
    )
    sections=NS(get_start_frame=lambda sec:NS(value=0),
                get_end_frame=lambda sec:NS(value=5))
    api=NS(MovieSceneSequenceExtensions=ext,
           MovieSceneSectionExtensions=sections,
           MovieSceneBlendType=NS(ABSOLUTE="ABSOLUTE"),
           UnrealEditorSubsystem="world",
           EditorActorSubsystem="actor",
           get_editor_subsystem=lambda cls:native_world
               if cls=="world" else actor_scene)
    staged=[{
        "name":"CAM","kind":"entity.camera","label":"CameraUE",
        "native_actor_path":path,
    }]
    assert native._live_owner(api,NS(),staged,{
        "source_camera_name":"CAM","target_actor_label":"CameraUE",
    },action) is section
    actor.path="/Game/Wrong.PersistentLevel.CineCameraActor_5"
    with pytest.raises(native.AnimatedCameraNativeError,match="not bound"):
        native._live_owner(api,NS(),staged,{
            "source_camera_name":"CAM","target_actor_label":"CameraUE",
        },action)
    actor.path=path
    binding.get_tracks=lambda:[track,FakeTrack("MovieSceneFloatTrack")]
    with pytest.raises(native.AnimatedCameraNativeError,match="additional"):
        native._live_owner(api,NS(),staged,{
            "source_camera_name":"CAM","target_actor_label":"CameraUE",
        },action)
    binding.get_tracks=lambda:[track]
    roots.append(FakeTrack("MovieSceneCinematicShotTrack"))
    with pytest.raises(native.AnimatedCameraNativeError,match="master"):
        native._live_owner(api,NS(),staged,{
            "source_camera_name":"CAM","target_actor_label":"CameraUE",
        },action)
    roots.pop()
    actor.parent=FakeActor()
    with pytest.raises(native.AnimatedCameraNativeError,match="parent rig"):
        native._live_owner(api,NS(),staged,{
            "source_camera_name":"CAM","target_actor_label":"CameraUE",
        },action)
