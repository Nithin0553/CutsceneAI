"""Approved 6-DoF skeletal-root alignment from *measured* source/native poses.

No invented IK, no automatic source-bone mapping. Produces an actor-owned
absolute world-space motion track; the independently measured target
AnimSequence root remains the only other motion carrier. Requires a single
retargeted clip and a reviewed source/target reference calibration.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

import csir_plan


class RootCalibrationError(ValueError):
    pass


STRATEGY="approved_measured_skeletal_root_6dof_actor_world_v1"
MAX_FRAMES=4000
_HASH=re.compile(r"[a-f0-9]{64}")


def _vec(value, n, field):
    if (not isinstance(value,(list,tuple)) or len(value)!=n
            or any(type(v) not in (int,float) or not math.isfinite(v)
                   for v in value)):
        raise RootCalibrationError("Invalid measured "+field)
    return tuple(float(v) for v in value)


def _quat(value):
    x,y,z,w=_vec(value,4,"root orientation")
    norm=math.hypot(x,y,z,w)
    if not math.isfinite(norm) or abs(norm-1.)>0.01:
        raise RootCalibrationError("Skeletal root quaternion is not a unit orientation.")
    return tuple(x/norm for x in (x,y,z,w))


def _mul(a,b):
    x,y,z,w=a
    u,v,t,s=b
    return (w*u+x*s+y*t-z*v,
            w*v-x*t+y*s+z*u,
            w*t+x*v-y*u+z*s,
            w*s-x*u-y*v-z*t)


def _inverse(q):
    return (-q[0],-q[1],-q[2],q[3])


def _rotate(q,p):
    v=(*p,0.)
    result=_mul(_mul(q,v),_inverse(q))
    return result[:3]


def _pose(transform, label):
    if not isinstance(transform,dict):
        raise RootCalibrationError("Missing "+label)
    scale=_vec(transform.get("scale_xyz"),3,label+" scale")
    if any(abs(v-1.)>1e-4 for v in scale):
        raise RootCalibrationError(
            "Nonunit skeletal root scale/shear needs separately calibrated rig adapter."
        )
    return (_vec(transform.get("position_m"),3,label+" position"),
            _quat(transform.get("rotation_xyzw")))


def _digest(value):
    return hashlib.sha256(json.dumps(
        value,allow_nan=False,sort_keys=True,separators=(",",":"),
    ).encode("utf-8")).hexdigest()


def compile_6dof_root_action(
    source_frames, target_root_local_frames, approval,
    *, source_sha256, native_skeleton_sha256, frame_rate, actor_name, actor_label,
):
    """Solve sourceRootWorld = targetActorWorld * nativeRootActorLocal.

    Both frame arrays must originate from full playback sampling at EXACT
    display times, not a model estimate or the first animated key used as rest.
    Independent skin/bone fidelity remains a separate CineTwin gate.
    """
    if (not isinstance(approval,dict)
            or approval.get("kind")!="cutsceneai.studio.approved_root_6dof"
            or approval.get("schema_version")!="1"
            or approval.get("source_sha256")!=source_sha256
            or approval.get("native_skeleton_sha256")!=native_skeleton_sha256
            or not _HASH.fullmatch(str(source_sha256))
            or not _HASH.fullmatch(str(native_skeleton_sha256))
            or approval.get("reviewed_independent_reference_bone_axes") is not True
            or approval.get("native_root_motion_isolated") is not True
            or approval.get("exclusive_actor_motion_owner") is not True
            or approval.get("native_parent_attachment_present") is not False
            or approval.get("skeletal_clip_count")!=1):
        raise RootCalibrationError(
            "Independent source/native skeleton rest axes, root isolation and one owner must be approved."
        )
    if (not isinstance(actor_name,str) or not actor_name
            or not isinstance(actor_label,str) or not actor_label
            or not isinstance(frame_rate,dict)
            or type(frame_rate.get("numerator")) is not int
            or type(frame_rate.get("denominator")) is not int
            or frame_rate["numerator"]<=0 or frame_rate["denominator"]<=0):
        raise RootCalibrationError("Root action needs one explicit actor and display rate.")
    if (not isinstance(source_frames,list)
            or not isinstance(target_root_local_frames,list)
            or not 2<=len(source_frames)<=MAX_FRAMES
            or len(source_frames)!=len(target_root_local_frames)):
        raise RootCalibrationError("Native and Unity skeletal roots need the same complete time grid.")
    fps=frame_rate["numerator"]/frame_rate["denominator"]
    previous=None
    keys=[]
    errors=[]
    for frame,(source,native) in enumerate(zip(source_frames,target_root_local_frames)):
        if not isinstance(source,dict) or not isinstance(native,dict):
            raise RootCalibrationError("Incomplete measured root frame.")
        if source.get("frame")!=frame or native.get("frame")!=frame:
            raise RootCalibrationError("Root frames are missing, extra or reordered.")
        try:
            a,b=float(source["time_seconds"]),float(native["time_seconds"])
        except (KeyError,TypeError,ValueError) as exc:
            raise RootCalibrationError("Root frame timestamp unavailable.") from exc
        if (not math.isfinite(a) or not math.isfinite(b)
                or abs(a-frame/fps)>1e-7 or abs(b-a)>1e-7):
            raise RootCalibrationError("Source/native root clocks differ from source display grid.")
        src_p,src_q=_pose(source.get("root_world"),"Unity evaluated root world")
        loc_p,loc_q=_pose(native.get("root_actor_local"),"Unreal sampled root actor-local")
        actor_q=_quat(_mul(src_q,_inverse(loc_q)))
        rotated=_rotate(actor_q,loc_p)
        actor_p=tuple(src_p[j]-rotated[j] for j in range(3))
        if any(abs(x)>100000 for x in actor_p):
            raise RootCalibrationError("Solved native actor world pose exceeds supported bounds.")
        if any(not math.isfinite(x) for x in (*actor_p,*actor_q)):
            raise RootCalibrationError("Solved native actor world pose is nonfinite.")
        computed=tuple(actor_p[j]+_rotate(actor_q,loc_p)[j] for j in range(3))
        errors.append(100*math.dist(computed,src_p))
        rot=csir_plan.canonical_quat_to_unreal_rotator(actor_q)
        rpy=csir_plan.continuous_unreal_rotator(previous,rot)
        previous=rpy
        keys.append({
            "frame":frame,
            "location_cm":list(csir_plan.canonical_position_to_unreal_cm(actor_p)),
            "rotation_rpy_degrees":list(rpy),
        })
    action={
        "kind":"transform",
        "entity_name":actor_name,
        "actor_label":actor_label,
        "track_name":"CutSceneAI Approved 6DoF Source Skeletal Root",
        "keys":keys,
        "baked_source_curves":True,
        "source_behavior_strategy":STRATEGY,
        "motion_ownership":"SINGLE_ACTOR_TRACK_WITH_NATIVE_MEASURED_LOCAL_SKELETAL_ROOT",
        "native_root_motion_fidelity_verified":False,
    }
    action["source_root_motion_evidence_sha256"]=_digest({
        "source":source_frames,"target_root_actor_local":target_root_local_frames,
        "approved":approval,
    })
    return {
        "kind":"cutsceneai.studio.approved_root_6dof_action",
        "action":action,
        "source_frame_count":len(keys),
        "solver_max_recomposition_cm":max(errors),
        "native_key_generation_executed":False,
        "target_reopened_source_root_comparison_verified":False,
        "skin_deformation_fidelity_verified":False,
    }


def attach_exclusive_action(plan: dict, artifact: dict) -> dict:
    """Attach only to a single native clip with NO other actor root owner."""
    if (not isinstance(plan,dict) or not isinstance(plan.get("actions"),list)
            or not isinstance(artifact,dict)
            or artifact.get("kind")!="cutsceneai.studio.approved_root_6dof_action"):
        raise RootCalibrationError("A full compiled source plan and approved root artifact are required.")
    action=artifact.get("action") or {}
    entity=action.get("entity_name")
    owned=[a for a in plan["actions"] if a.get("entity_name")==entity]
    clips=[a for a in owned if a.get("kind")=="skeletal_animation"]
    if (len(clips)!=1 or any(a.get("kind") in
            {"transform","skeletal_world_root_lock"} for a in owned)
            or any(a.get("root_motion_correction_samples") or
                   a.get("expected_root_delta_cm") is not None for a in clips)):
        raise RootCalibrationError(
            "6DoF skeletal root correction refuses another world/root trajectory owner."
        )
    if len(action.get("keys",[]))!=plan.get("duration_frames",-1)+1:
        raise RootCalibrationError("Approved native root pose does not cover the whole Timeline.")
    cloned={**plan,"actions":[*plan["actions"],action]}
    return cloned
