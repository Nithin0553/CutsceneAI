"""Synthetic six-dimensional source/native root alignment tests (no editor)."""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]
for directory in (ROOT/"packages"/"studio",ROOT/"integrations"/"unreal"):
    sys.path.insert(0,str(directory))
import root_motion_calibration_6dof as root

RATE={"numerator":30,"denominator":1}


def _pose(p,angle=0):
    half=math.radians(angle)/2
    return {"position_m":p,
            "rotation_xyzw":[0,0,math.sin(half),math.cos(half)],
            "scale_xyz":[1,1,1]}


def _fixture():
    src=[]
    dst=[]
    for i in range(4):
        src.append({"frame":i,"time_seconds":i/30.,
                    "root_world":_pose([0.,float(i)*2.,0.],i*30.)})
        dst.append({"frame":i,"time_seconds":i/30.,
                    "root_actor_local":_pose([1.,0.,0.],0.)})
    approval={
        "kind":"cutsceneai.studio.approved_root_6dof",
        "schema_version":"1","source_sha256":"a"*64,
        "native_skeleton_sha256":"b"*64,
        "reviewed_independent_reference_bone_axes":True,
        "native_root_motion_isolated":True,
        "exclusive_actor_motion_owner":True,
        "native_parent_attachment_present":False,
        "skeletal_clip_count":1,
    }
    return src,dst,approval


def _compile(src,dst,approved):
    return root.compile_6dof_root_action(
        src,dst,approved,source_sha256="a"*64,
        native_skeleton_sha256="b"*64,frame_rate=RATE,
        actor_name="Hero",actor_label="HeroUE",
    )


def test_rotating_world_root_solved_from_local_animated_root_at_all_frames():
    src,dst,approved=_fixture()
    result=_compile(src,dst,approved)
    assert result["source_frame_count"]==4
    assert result["solver_max_recomposition_cm"]<1e-7
    keys=result["action"]["keys"]
    assert keys[0]["location_cm"]==pytest.approx([0,-100,0])
    assert keys[3]["location_cm"]==pytest.approx([0,0,500])
    assert len(set(tuple(k["rotation_rpy_degrees"]) for k in keys))==4
    assert result["native_key_generation_executed"] is False
    assert result["target_reopened_source_root_comparison_verified"] is False


@pytest.mark.parametrize("change,match",[
    (lambda s,t,a: t.pop(),"same complete"),
    (lambda s,t,a: t[1].__setitem__("frame",2),"missing, extra or reordered"),
    (lambda s,t,a: t[1].__setitem__("time_seconds",0.7),"clocks"),
    (lambda s,t,a: t[1]["root_actor_local"].__setitem__(
        "scale_xyz",[1.,0.,1.]),"scale/shear"),
    (lambda s,t,a: s[1]["root_world"].__setitem__(
        "rotation_xyzw",[0,0,0,0]),"unit orientation"),
    (lambda s,t,a: a.__setitem__(
        "native_root_motion_isolated",False),"approved"),
    (lambda s,t,a: a.__setitem__(
        "native_parent_attachment_present",True),"approved"),
    (lambda s,t,a: a.__setitem__(
        "skeletal_clip_count",2),"approved"),
])
def test_unapproved_or_malformed_source_native_root_frame_refused(change,match):
    source,target,approval=_fixture()
    change(source,target,approval)
    with pytest.raises(root.RootCalibrationError,match=match):
        _compile(source,target,approval)


def test_root_attacher_refuses_competing_transform_and_two_clips():
    src,dst,approved=_fixture()
    artifact=_compile(src,dst,approved)
    plan={"duration_frames":3,"actions":[
        {"kind":"skeletal_animation","entity_name":"Hero","unreal_asset_path":
         "/Game/Char/Anim"},
    ]}
    out=root.attach_exclusive_action(plan,artifact)
    assert len(out["actions"])==2 and len(plan["actions"])==1
    assert out["actions"][-1]["source_behavior_strategy"]==root.STRATEGY
    for competitor in (
        {"kind":"transform","entity_name":"Hero"},
        {"kind":"skeletal_world_root_lock","entity_name":"Hero"},
        {"kind":"skeletal_animation","entity_name":"Hero"},
    ):
        bad=copy.deepcopy(plan)
        bad["actions"].append(competitor)
        with pytest.raises(root.RootCalibrationError,match="another"):
            root.attach_exclusive_action(bad,artifact)
    bad=copy.deepcopy(plan)
    bad["actions"][0]["root_motion_correction_samples"]=[{"frame":1}]
    with pytest.raises(root.RootCalibrationError,match="another"):
        root.attach_exclusive_action(bad,artifact)
