"""Guarded multi-axis camera rotation-key recovery from measured CineTwin frames.

Allows *bounded existing-key* pitch/roll/yaw repair on one source-generated
absolute CineCamera transform section. No rig, weighted blend, key insertion,
arbitrary tangent rewriting, or independent rendered-fidelity claim.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import studio_camera_key_repair as native
import studio_camera_motion_contract as grid
import studio_camera_key_evidence as evidence
import csir_plan


class CameraCurveError(ValueError):
    pass


MAX_CHANGED_KEYS=1024
MAX_PITCH=80.0
MAX_DELTA_DEGREES=60.0


def _sha(document: Any) -> str:
    return hashlib.sha256(json.dumps(document,sort_keys=True,
                    separators=(",",":"),allow_nan=False).encode("utf-8")).hexdigest()


def compile_rotation_curve(action:dict, original:dict, observed:dict,
                           approval:dict, *, source_id:str,
                           target_label:str, duration_frames:int,
                           display_rate:dict) -> dict:
    """Recompute from the immutable source action and independent observations."""
    if (not isinstance(approval,dict)
            or approval.get("kind")!="cutsceneai.studio.approved_camera_3axis_curve"
            or approval.get("schema_version")!="1"
            or approval.get("reviewed_exclusive_camera_owner") is not True
            or approval.get("source_camera_action_sha256")!=_sha(action)
            or approval.get("original_source_capture_sha256")!=_sha(original)
            or approval.get("original_native_capture_sha256")!=_sha(observed)
            or approval.get("source_entity_id")!=source_id
            or approval.get("native_actor_label")!=target_label
            or not isinstance(display_rate,dict)):
        raise CameraCurveError("Explicit source/native capture-bound camera curve approval required.")
    if action.get("source_behavior_strategy")!=grid.CAPTURE_STRATEGY:
        raise CameraCurveError("Only independently evaluated source camera grid is repairable.")
    grid.validate_action(action,duration_frames=duration_frames)
    if (type(display_rate.get("numerator")) is not int
            or type(display_rate.get("denominator")) is not int
            or display_rate["numerator"]<=0 or display_rate["denominator"]<=0):
        raise CameraCurveError("Original camera display rate is invalid.")
    previous=None
    changes=[]
    for key in action["keys"]:
        frame=key["frame"]
        instant=frame*display_rate["denominator"]/display_rate["numerator"]
        try:
            source=evidence._unique_sample(original,source_id,None,instant)
            target=evidence._unique_sample(observed,source_id,target_label,instant)
            qs=evidence._vec(source,"rotation_xyzw",4)
            qt=evidence._vec(target,"rotation_xyzw",4)
            ps=evidence._vec(source,"position_m",3)
            pt=evidence._vec(target,"position_m",3)
            ss=evidence._vec(source,"scale_xyz",3)
            st=evidence._vec(target,"scale_xyz",3)
            source_rpy=tuple(float(x) for x in key["rotation_rpy_degrees"])
            native_source=csir_plan.canonical_quat_to_unreal_rotator(qs)
            native_target=csir_plan.canonical_quat_to_unreal_rotator(qt)
        except (evidence.AnimatedCameraKeyError,ValueError,KeyError,
                TypeError,OverflowError) as exc:
            raise CameraCurveError("Missing source/native evaluated camera frame.") from exc
        if (math.dist(ps,pt)*100>0.25
                or math.dist(csir_plan.canonical_position_to_unreal_cm(ps),
                             key["location_cm"])>0.2
                or any(abs(x-1)>0.001 for x in (*ss,*st))):
            raise CameraCurveError("Camera curve is not an isolated rotation-only difference.")
        if (grid._orientation_delta(source_rpy,native_source)>0.2
                or evidence._qangle(qs,qt)>MAX_DELTA_DEGREES
                or abs(native_source[1])>=MAX_PITCH
                or abs(native_target[1])>=MAX_PITCH
                or any(abs(x)>=170 for x in (*source_rpy,*native_target))):
            raise CameraCurveError("Native/source camera Euler basis is wrapped or near singular.")
        native_target=csir_plan.continuous_unreal_rotator(previous,native_target)
        previous=native_target
        for axis in range(3):
            wanted=source_rpy[axis]
            before=float(native_target[axis])
            if abs(before-wanted)>0.2:
                if abs(before-wanted)>MAX_DELTA_DEGREES:
                    raise CameraCurveError("Camera rotation key differs beyond bounded physical angle.")
                changes.append({
                    "frame":frame,"native_channel_index":axis+3,
                    "native_key_value_before_degrees":round(before,6),
                    "source_key_value_degrees":round(wanted,6),
                })
    if not 1<=len(changes)<=MAX_CHANGED_KEYS:
        raise CameraCurveError("One to 1024 source-measured camera rotation key differences required.")
    report={
        "kind":"cutsceneai.studio.approved_camera_rotation_curve_plan",
        "schema_version":"1",
        "source_camera_occurrence_id":source_id,
        "target_actor_label":target_label,
        "source_camera_action_sha256":_sha(action),
        "original_source_capture_sha256":_sha(original),
        "original_native_capture_sha256":_sha(observed),
        "changes":changes,
        "native_edit_authorized_only_by_separate_review":True,
        "source_display_frames":len(action["keys"]),
        "native_reopened_cinetwin_verified":False,
        "rendered_between_key_fidelity_verified":False,
    }
    report["canonical_curve_plan_sha256"]=_sha(report)
    return report


def realize(api:Any, section:Any, action:dict, plan:dict) -> dict:
    """Complete native nine-channel readback and rollback for *existing* keys.

    Caller must first resolve section using
    studio_camera_key_repair._live_owner against the exact newly staged
    source camera UObject and the original compiled sequence.
    """
    if (not isinstance(plan,dict)
            or plan.get("kind")!="cutsceneai.studio.approved_camera_rotation_curve_plan"
            or plan.get("source_camera_action_sha256")!=_sha(action)
            or plan.get("canonical_curve_plan_sha256")!=_sha({
                k:v for k,v in plan.items()
                if k!="canonical_curve_plan_sha256"
            })):
        raise CameraCurveError("Camera curve proof differs from original source action.")
    rows=plan["changes"]
    if not isinstance(rows,list) or not 1<=len(rows)<=MAX_CHANGED_KEYS:
        raise CameraCurveError("No bounded original measured camera keys.")
    from unreal_compat import get_section_channels
    channels=list(get_section_channels(section))
    if len(channels)!=9:
        raise CameraCurveError("CineCamera native nine-channel owner is missing.")
    linear=getattr(getattr(api,"RichCurveInterpMode",None),"RCIM_LINEAR",None)
    if linear is None:
        raise CameraCurveError("Native key interpolation readback unavailable.")
    exceptions={}
    for row in rows:
        frame,channel=row.get("frame"),row.get("native_channel_index")
        if (type(frame) is not int or type(channel) is not int
                or channel not in (3,4,5)
                or not 0<=frame<len(action["keys"])
                or (frame,channel) in exceptions):
            raise CameraCurveError("Ambiguous native camera rotation key exception.")
        exceptions[(frame,channel)]=row
    originals=[]
    selected=[]
    for idx,channel in enumerate(channels):
        keys=list(channel.get_keys())
        if idx>=6:
            has=getattr(channel,"has_default",None)
            get=getattr(channel,"get_default",None)
            if (keys or not callable(has) or has() is not True
                    or not callable(get) or abs(float(get())-1)>1e-7):
                raise CameraCurveError("Native camera scale has an unexpected owner.")
            continue
        if len(keys)!=len(action["keys"]):
            raise CameraCurveError("Native camera key count differs from source.")
        for frame,key in enumerate(keys):
            mode=getattr(key,"get_interpolation_mode",None)
            if (native._frame(api,key)!=frame or
                    not callable(mode) or mode()!=linear):
                raise CameraCurveError("Native key frame or interpolation differs from source.")
            expected=(*action["keys"][frame]["location_cm"],
                      *action["keys"][frame]["rotation_rpy_degrees"])[idx]
            current=float(key.get_value())
            if not math.isfinite(current):
                raise CameraCurveError("Camera native key nonfinite.")
            mismatch=exceptions.get((frame,idx))
            if mismatch is None:
                if abs(current-expected)>0.02:
                    raise CameraCurveError("Competing native camera key differs from original source.")
                continue
            if (abs(current-mismatch["native_key_value_before_degrees"])>0.15
                    or abs(float(expected)-mismatch["source_key_value_degrees"])>0.02
                    or not callable(getattr(key,"set_value",None))):
                raise CameraCurveError("Native camera key changed since independent capture.")
            selected.append((key,float(expected)))
            originals.append((key,current))
    if len(selected)!=len(rows):
        raise CameraCurveError("Not all original camera rotation exceptions exist.")
    changed=[]
    saved=False
    try:
        for (key,wanted),(original_key,original_value) in zip(selected,originals):
            changed.append((original_key,original_value))
            key.set_value(wanted)
        native._all_camera_keys_match_source(api,section,action)
        sequence=plan.get("_verified_runtime_sequence")
        save=getattr(getattr(api,"EditorAssetLibrary",None),"save_loaded_asset",None)
        if sequence is None or not callable(save) or save(sequence) is not True:
            raise CameraCurveError("Native source camera curve save not confirmed.")
        saved=True
        return {
            "status":"SAVED_CAMERA_3AXIS_ROTATION_CURVE_REOPENED_CINETWIN_PENDING",
            "canonical_curve_plan_sha256":plan["canonical_curve_plan_sha256"],
            "native_changed_keys":len(changed),
            "all_nine_native_transform_channels_readback":True,
            "native_save_confirmed":True,
            "editor_reopen_verified":False,
            "rendered_trajectory_verified":False,
        }
    finally:
        if changed and not saved:
            try:
                for key,old in reversed(changed):
                    key.set_value(old)
                if any(abs(float(k.get_value())-old)>0.02 for k,old in changed):
                    raise CameraCurveError("Native camera rotation rollback mismatch.")
            except (AttributeError,RuntimeError,TypeError,ValueError) as exc:
                raise CameraCurveError(
                    "Native camera rotation curve rollback unverified."
                ) from exc
