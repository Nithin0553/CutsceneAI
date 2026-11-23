"""Source-authenticated multi-axis (roll/pitch/yaw) camera native-key regressions."""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT=Path(__file__).resolve().parents[2]
for directory in ("packages/studio","integrations/unreal","tests/studio"):
    sys.path.insert(0,str(ROOT/directory))

import studio_camera_rotation_curve as curve
from test_animated_camera_key_repair import (
    API,
    FakeSection,
    _yaw_scenario,
)


def _fixture():
    original,target,_cam,label,action,plan,_=_yaw_scenario()
    # The independent target captured a separate physical roll deviation.
    theta=math.radians(9)/2
    dq=(math.sin(theta),0.,0.,math.cos(theta))
    q=target["samples"][1]["entities"][0]["world_transform"]["rotation_xyzw"]
    # Quaternion composition, not direct Euler channel tampering.
    x,y,z,w=q
    u,v,t,s=dq
    target["samples"][1]["entities"][0]["world_transform"]["rotation_xyzw"]=[
        w*u+x*s+y*t-z*v,w*v-x*t+y*s+z*u,
        w*t+x*v-y*u+z*s,w*s-x*u-y*v-z*t,
    ]
    approval={
        "kind":"cutsceneai.studio.approved_camera_3axis_curve",
        "schema_version":"1",
        "reviewed_exclusive_camera_owner":True,
        "source_camera_action_sha256":curve._sha(action),
        "original_source_capture_sha256":curve._sha(original),
        "original_native_capture_sha256":curve._sha(target),
        "source_entity_id":"cam:1",
        "native_actor_label":label,
        "target_sequence_path":"/Game/Scene",
    }
    return original,target,action,approval,plan


def _compile(source,target,action,approved,plan):
    return curve.compile_rotation_curve(
        action,source,target,approved,source_id="cam:1",
        target_label="CameraUE",duration_frames=plan["duration_frames"],
        display_rate=plan["display_rate"],
    )


def _native_scene(action,report,*,save=True):
    section=FakeSection(action,diff=0)
    for row in report["changes"]:
        section.channels[row["native_channel_index"]].keys[
            row["frame"]].set_value(row["native_key_value_before_degrees"])
    sequence=NS(get_path_name=lambda:"/Game/Scene.Scene")
    api=NS(MovieSceneTimeUnit=API.MovieSceneTimeUnit,
           RichCurveInterpMode=API.RichCurveInterpMode,
           EditorAssetLibrary=NS(save_loaded_asset=lambda obj:save))
    return api,sequence,section


def test_roll_and_yaw_are_source_measured_then_written_to_exact_native_keys():
    source,target,action,approved,scope=_fixture()
    plan=_compile(source,target,action,approved,scope)
    assert plan["kind"]=="cutsceneai.studio.approved_camera_rotation_curve_plan"
    assert len(plan["changes"])>=2
    assert all(row["native_channel_index"] in (3,4,5)
               for row in plan["changes"])
    api,sequence,section=_native_scene(action,plan)
    receipt=curve.realize(api,sequence,section,action,plan)
    assert receipt["status"]=="SAVED_CAMERA_3AXIS_ROTATION_CURVE_REOPENED_CINETWIN_PENDING"
    assert receipt["native_changed_keys"]==len(plan["changes"])
    assert receipt["all_nine_native_transform_channels_readback"] is True
    assert receipt["editor_reopen_verified"] is False


def test_saving_failed_camera_rotation_restores_all_native_original_keys():
    source,target,action,approved,scope=_fixture()
    plan=_compile(source,target,action,approved,scope)
    api,sequence,section=_native_scene(action,plan,save=False)
    before=[[k.get_value() for k in channel.get_keys()]
            for channel in section.channels]
    with pytest.raises(curve.CameraCurveError,match="save"):
        curve.realize(api,sequence,section,action,plan)
    after=[[k.get_value() for k in channel.get_keys()]
           for channel in section.channels]
    assert before==after


def test_native_curve_refuses_other_axes_and_stale_approval():
    source,target,action,approved,scope=_fixture()
    plan=_compile(source,target,action,approved,scope)
    api,seq,section=_native_scene(action,plan)
    section.channels[0].keys[0].set_value(200.)
    with pytest.raises(curve.CameraCurveError,match="Competing"):
        curve.realize(api,seq,section,action,plan)
    stale=copy.deepcopy(plan)
    stale["changes"][0]["source_key_value_degrees"]+=1
    with pytest.raises(curve.CameraCurveError,match="differs"):
        curve.realize(api,seq,_native_scene(action,plan)[2],action,stale)
    approval=copy.deepcopy(approved)
    approval["original_native_capture_sha256"]="0"*64
    with pytest.raises(curve.CameraCurveError,match="approval"):
        _compile(source,target,action,approval,scope)


def test_camera_rig_scale_position_and_pitch_pole_refuse_source_curve_approval():
    source,target,action,approved,scope=_fixture()
    new_target=copy.deepcopy(target)
    new_target["samples"][0]["entities"][0]["world_transform"][
        "position_m"][0]+=0.1
    approval=copy.deepcopy(approved)
    approval["original_native_capture_sha256"]=curve._sha(new_target)
    with pytest.raises(curve.CameraCurveError,match="rotation-only"):
        _compile(source,new_target,action,approval,scope)


def test_safe_entrypoint_requires_exact_live_owner_and_original_captures(monkeypatch):
    source,target,action,approval,scope=_fixture()
    report=_compile(source,target,action,approval,scope)
    api,sequence,section=_native_scene(action,report)
    staged=[{"kind":"entity.camera","name":"CAM","label":"CameraUE",
             "native_actor_path":"/Game/Stage.CineCam"}]
    calls=[]
    def owner(api,sequence,actors,identity,source_action):
        calls.append((actors,identity,source_action))
        return section
    monkeypatch.setattr(curve.native,"_live_owner",owner)
    receipt=curve.realize_from_original(
        api,sequence,staged,source,target,action,approval,
        source_entity_id="cam:1",source_camera_name="CAM",
        target_actor_label="CameraUE",duration_frames=scope["duration_frames"],
        display_rate=scope["display_rate"],
    )
    assert receipt["native_changed_keys"]==len(report["changes"])
    assert calls and calls[0][1]=={
        "source_camera_name":"CAM","target_actor_label":"CameraUE",
    }
    altered=copy.deepcopy(target)
    altered["samples"][1]["entities"][0]["world_transform"][
        "position_m"][0]+=0.1
    calls.clear()
    with pytest.raises(curve.CameraCurveError,match="approval"):
        curve.realize_from_original(
            api,sequence,staged,source,altered,action,approval,
            source_entity_id="cam:1",source_camera_name="CAM",
            target_actor_label="CameraUE",duration_frames=scope["duration_frames"],
            display_rate=scope["display_rate"],
        )
    assert not calls


def test_safe_entrypoint_refuses_unknown_cinecamera_binding(monkeypatch):
    source,target,action,approval,scope=_fixture()
    report=_compile(source,target,action,approval,scope)
    api,sequence,_section=_native_scene(action,report)
    def refuse(*args):
        raise curve.native.AnimatedCameraNativeError("camera is attached to unknown rig")
    monkeypatch.setattr(curve.native,"_live_owner",refuse)
    with pytest.raises(curve.CameraCurveError,match="not original"):
        curve.realize_from_original(
            api,sequence,[],source,target,action,approval,
            source_entity_id="cam:1",source_camera_name="CAM",
            target_actor_label="CameraUE",duration_frames=scope["duration_frames"],
            display_rate=scope["display_rate"],
        )
