"""Exactly one source-authenticated animated CineCamera world-position key repair.

This adapter changes one existing MovieSceneScriptingDoubleKey.value, NEVER
inserts/deletes/re-times native keys or rewrites other cinematic channels.
All nine native transform channels are freshly inspected against the immutable
CineTwin-backed prepared source grid before mutation. Any API ambiguity,
other mismatch or save failure refuses/attempts compensating rollback.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[2]
for folder in (ROOT/"packages/studio",ROOT/"integrations/unreal"):
    if str(folder) not in sys.path:
        sys.path.insert(0,str(folder))

import studio_camera_key_evidence as evidence
import studio_camera_motion_contract as grid
import studio_camera_position_evidence as position


class AnimatedCameraNativeError(ValueError):
    """Native camera key owner, source sample or rollback is unverified."""


def _load(path: Path) -> dict:
    return evidence.readback._safe_json(path)[0]


def _frame(api: Any, key: Any) -> int:
    try:
        stamp=key.get_time(api.MovieSceneTimeUnit.DISPLAY_RATE)
        raw=getattr(stamp,"frame_number",stamp)
        value=getattr(raw,"value",raw)
        sub=float(getattr(stamp,"sub_frame",0.))
        if (type(value) is not int or not math.isfinite(sub)
                or abs(sub)>1e-7 or value<0 or value>100_000):
            raise AnimatedCameraNativeError(
                "Camera scripting key has subframe/invalid time."
            )
        return value
    except AnimatedCameraNativeError:
        raise
    except (AttributeError,TypeError,ValueError,RuntimeError) as exc:
        raise AnimatedCameraNativeError(
            "Native source key display-frame readback unavailable."
        ) from exc


def _read_channels(api: Any, section: Any, prepared: dict,
                   *,repair: dict) -> tuple[Any,float]:
    """Compare ALL existing native keys to immutable source action; one exception."""
    from unreal_compat import get_section_channels
    channels=list(get_section_channels(section))
    if len(channels)!=9:
        raise AnimatedCameraNativeError("Nine native camera transform channels required.")
    keys=prepared["keys"]
    if (prepared.get("source_behavior_strategy")!=grid.CAPTURE_STRATEGY
            or len(keys)>evidence._MAX_FRAMES
            or len(keys)<4
            or any(k.get("frame")!=i for i,k in enumerate(keys))):
        raise AnimatedCameraNativeError(
            "Original CineTwin evaluated camera frame grid invalid."
        )
    active_frame=repair["source_key_frame"]
    axis=repair["native_channel_index"]
    if (type(active_frame) is not int or type(axis) is not int
            or not 0<active_frame<len(keys)-1 or axis not in (0,1,2)):
        raise AnimatedCameraNativeError("Camera key does not belong to one XYZ axis.")
    rich=getattr(api,"RichCurveInterpMode",None)
    linear=getattr(rich,"RCIM_LINEAR",None)
    if linear is None:
        raise AnimatedCameraNativeError(
            "Native source camera linear key interpolation is not introspectable."
        )
    changed_key=None
    original_value=None
    for channel_index,channel in enumerate(channels):
        key_list=list(channel.get_keys())
        if channel_index>=6:
            if key_list:
                raise AnimatedCameraNativeError(
                    "Animated camera has explicit authored scale keys."
                )
            default_getter=getattr(channel,"get_default",None)
            has_default=getattr(channel,"has_default",None)
            if (not callable(default_getter)
                    or not callable(has_default)
                    or has_default() is not True):
                raise AnimatedCameraNativeError(
                    "Native source camera scale default cannot be inspected."
                )
            default=float(default_getter())
            if not math.isfinite(default) or abs(default-1.)>1e-6:
                raise AnimatedCameraNativeError(
                    "Animated camera native scale differs from original unit scale."
                )
            continue
        if len(key_list)!=len(keys):
            raise AnimatedCameraNativeError(
                "Native camera channel has extra/missing key times."
            )
        frames=[_frame(api,key) for key in key_list]
        if frames!=list(range(len(keys))):
            raise AnimatedCameraNativeError(
                "Native camera channel has subframe, duplicated or reordered source keys."
            )
        for index,key in enumerate(key_list):
            # A different cubic/constant tangent or extrapolation mode can
            # change camera motion BETWEEN the matching source frame samples.
            # Source-baked CineTwin transform keys must remain LINEAR.
            mode=getattr(key,"get_interpolation_mode",None)
            if not callable(mode) or mode()!=linear:
                raise AnimatedCameraNativeError(
                    "Native camera key interpolation differs from source linear grid."
                )
            expected=(
                list(keys[index]["location_cm"])
                + list(keys[index]["rotation_rpy_degrees"])
            )[channel_index]
            actual=float(key.get_value())
            if not math.isfinite(actual) or not math.isfinite(float(expected)):
                raise AnimatedCameraNativeError("Native camera key value nonfinite.")
            # For rotations, the precise native Euler trajectory from the
            # ORIGINAL prepared plan is authoritative. Equivalent but different
            # unwrapped angles can interpolate differently: fail closed.
            if channel_index==axis and index==active_frame:
                if (abs(actual-repair["native_key_value_before_cm"])>0.15
                        or abs(float(expected)-repair["source_key_value_cm"])>0.1
                        or not evidence.MIN_CM<=abs(actual-float(expected))<=evidence.MAX_CM
                        or not callable(getattr(key,"set_value",None))):
                    raise AnimatedCameraNativeError(
                        "Live native key no longer matches independently sampled discrepancy."
                    )
                changed_key=key
                original_value=actual
            elif abs(actual-float(expected))>(
                    0.05 if channel_index<3 else 0.02):
                raise AnimatedCameraNativeError(
                    "Another native transform channel/key differs from source."
                )
    if changed_key is None or original_value is None:
        raise AnimatedCameraNativeError(
            "Original source-owned camera key not found."
        )
    return changed_key,original_value


def _all_camera_keys_match_source(api: Any, section: Any, action: dict) -> None:
    """Independently reread all nine native transform channels after mutation."""
    from unreal_compat import get_section_channels
    channels = list(get_section_channels(section))
    keys = action["keys"]
    linear = getattr(getattr(api, "RichCurveInterpMode", None),
                     "RCIM_LINEAR", None)
    if len(channels) != 9 or linear is None:
        raise AnimatedCameraNativeError(
            "Post-write native nine-channel camera readback unavailable."
        )
    for channel_index, channel in enumerate(channels):
        actual_keys = list(channel.get_keys())
        if channel_index >= 6:
            has_default = getattr(channel, "has_default", None)
            get_default = getattr(channel, "get_default", None)
            if (actual_keys or not callable(has_default)
                    or has_default() is not True
                    or not callable(get_default)
                    or abs(float(get_default()) - 1.0) > 1e-6):
                raise AnimatedCameraNativeError(
                    "Camera scale changed after source-key edit."
                )
            continue
        if len(actual_keys) != len(keys):
            raise AnimatedCameraNativeError(
                "Native camera lost or gained animation keys after edit."
            )
        for frame, (original, observed) in enumerate(zip(keys, actual_keys)):
            interpolation = getattr(observed, "get_interpolation_mode", None)
            if (_frame(api, observed) != frame
                    or not callable(interpolation)
                    or interpolation() != linear):
                raise AnimatedCameraNativeError(
                    "Native camera key timing/interpolation changed after edit."
                )
            expected = (
                *original["location_cm"], *original["rotation_rpy_degrees"]
            )[channel_index]
            actual = float(observed.get_value())
            if (not math.isfinite(actual)
                    or abs(actual - float(expected)) > 0.02):
                raise AnimatedCameraNativeError(
                    "A native camera key differs from the immutable source plan."
                )


def _live_owner(api: Any, sequence: Any, setup: list, proof: dict,
                action: dict) -> Any:
    ext=getattr(api,"MovieSceneSequenceExtensions",None)
    get_bindings=getattr(ext,"get_bindings",None)
    locate=getattr(ext,"locate_bound_objects",None)
    get_tracks=getattr(ext,"get_tracks",None)
    editor_type=getattr(api,"UnrealEditorSubsystem",None)
    if (not all(callable(v) for v in (get_bindings,locate,get_tracks))
            or editor_type is None):
        raise AnimatedCameraNativeError(
            "Full native camera binding and master-track inventory unavailable."
        )
    root_tracks=list(get_tracks(sequence))
    if len(root_tracks)>1000 or any(
        str(track.get_class().get_name()) not in {
            "MovieSceneCameraCutTrack","MovieSceneAudioTrack",
        }
        for track in root_tracks
    ):
        raise AnimatedCameraNativeError(
            "Native shot/subsequence/timewarp master track may own time base."
        )
    staged=[row for row in setup if isinstance(row,dict)
            and row.get("kind")=="entity.camera"
            and row.get("name")==proof["source_camera_name"]
            and row.get("label")==proof["target_actor_label"]]
    if len(staged)!=1:
        raise AnimatedCameraNativeError("Exactly one source-staged camera is required.")
    native_path=staged[0].get("native_actor_path")
    if (not isinstance(native_path,str)
            or not native_path.startswith("/Game/")
            or len(native_path)>1024):
        raise AnimatedCameraNativeError("Exact staged CineCamera UObject path absent.")
    world=api.get_editor_subsystem(editor_type).get_editor_world()
    bindings=list(get_bindings(sequence))
    if len(bindings)>10000:
        raise AnimatedCameraNativeError("Unbounded Unreal binding inventory.")
    actor_track=None
    actor=None
    for binding in bindings:
        owners=list(locate(sequence,binding,world))
        if len(owners)>1:
            raise AnimatedCameraNativeError(
                "Unreal binding resolves to multiple native objects."
            )
        binding_tracks=list(binding.get_tracks())
        if len(binding_tracks)>1000:
            raise AnimatedCameraNativeError("Unbounded native component tracks.")
        for track in binding_tracks:
            name=str(track.get_class().get_name())
            if ("SubTrack" in name or "CinematicShot" in name
                    or "TimeWarp" in name or "TimeDilation" in name
                    or "ControlRig" in name):
                raise AnimatedCameraNativeError(
                    "A competing Sequencer owner can change camera motion."
                )
        if not owners:
            # A missing camera binding cannot be silently treated as a
            # correctly posed source-mapped CineCamera.
            if any(str(track.get_class().get_name())=="MovieScene3DTransformTrack"
                   for track in binding_tracks):
                raise AnimatedCameraNativeError(
                    "Unresolved Sequencer transform binding may own camera."
                )
            continue
        obj=owners[0]
        if str(obj.get_path_name())!=native_path:
            continue
        if (actor is not None or str(obj.get_actor_label())!=proof["target_actor_label"]
                or str(obj.get_class().get_name())!="CineCameraActor"):
            raise AnimatedCameraNativeError(
                "Source-staged camera bound UObject is ambiguous or wrong class."
            )
        actor=obj
        if (len(binding_tracks)!=1
                or str(binding_tracks[0].get_class().get_name())
                !="MovieScene3DTransformTrack"):
            raise AnimatedCameraNativeError(
                "Camera actor has an additional or missing property owner."
            )
        actor_track=binding_tracks[0]
    if actor is None or actor_track is None:
        raise AnimatedCameraNativeError("Source-staged camera not bound to Sequencer.")
    # No second native owner may animate the camera component's transform.
    # Lens tracks are separate camera optics; anything else is a competitor.
    get_component=getattr(actor,"get_cine_camera_component",None)
    if not callable(get_component) or get_component() is None:
        raise AnimatedCameraNativeError("Native CineCamera component is missing.")
    component=get_component()
    component_path=str(component.get_path_name())
    for binding in bindings:
        owners=list(locate(sequence,binding,world))
        if len(owners)>1:
            raise AnimatedCameraNativeError("Ambiguous native camera component binding.")
        if not owners or str(owners[0].get_path_name())!=component_path:
            continue
        for linked in binding.get_tracks():
            class_name=str(linked.get_class().get_name())
            if class_name!="MovieSceneFloatTrack":
                raise AnimatedCameraNativeError(
                    "Camera component has another animation/transform owner."
                )
            get_property=getattr(linked,"get_property_name",None)
            if (not callable(get_property)
                    or str(get_property()) not in {
                        "CurrentFocalLength","FieldOfView",
                    }):
                raise AnimatedCameraNativeError(
                    "Camera component has an unknown scalar property owner."
                )
    direct_name=getattr(actor_track,"get_display_name",None)
    ext_name=getattr(getattr(api,"MovieSceneTrackExtensions",None),
                     "get_display_name",None)
    if callable(direct_name):
        track_name=str(direct_name())
    elif callable(ext_name):
        track_name=str(ext_name(actor_track))
    else:
        raise AnimatedCameraNativeError(
            "Exact source-generated native camera track name unavailable."
        )
    if track_name!=action.get("track_name"):
        raise AnimatedCameraNativeError(
            "Native animated camera track name is not source-generated."
        )
    sections=list(actor_track.get_sections())
    if len(sections)!=1:
        raise AnimatedCameraNativeError(
            "Only one original complete camera animation section is editable."
        )
    section=sections[0]
    ext_section=getattr(api,"MovieSceneSectionExtensions",None)
    get_start=getattr(ext_section,"get_start_frame",None)
    get_end=getattr(ext_section,"get_end_frame",None)
    is_active=getattr(section,"is_active",None)
    get_blend=getattr(section,"get_blend_type",None)
    absolute=getattr(getattr(api,"MovieSceneBlendType",None),"ABSOLUTE",None)
    if (not all(callable(x) for x in (get_start,get_end,is_active,get_blend))
            or absolute is None):
        raise AnimatedCameraNativeError(
            "Native section timing/absolute ownership cannot be inspected."
        )
    first=get_start(section)
    last=get_end(section)
    first=getattr(first,"value",first)
    last=getattr(last,"value",last)
    native_blend=get_blend()
    if (native_blend is None
            or getattr(native_blend,"is_valid",None) is not True
            or getattr(native_blend,"blend_type",None)!=absolute):
        raise AnimatedCameraNativeError(
            "Native camera section has no verified absolute blend owner."
        )
    if (type(first) is not int or type(last) is not int
            or (first,last)!=(0,len(action["keys"]))
            or is_active() is not True):
        raise AnimatedCameraNativeError(
            "Original animated camera section is retimed, inactive or not absolute."
        )
    # The prepared plan is independently checked at execution, while all
    # native key indices must additionally belong to this original section.
    # Competing attachments/rigs must never be mistaken for actor world keys.
    if actor.get_attach_parent_actor() is not None:
        raise AnimatedCameraNativeError("Animated camera parent rig is unsupported.")
    scene=api.get_editor_subsystem(api.EditorActorSubsystem)
    actors=list(scene.get_all_level_actors())
    if len(actors)>10000 or any(
        other is not actor and other.get_attach_parent_actor() is actor
        for other in actors
    ):
        raise AnimatedCameraNativeError("Animated camera owns child attachments.")
    # Some real CineCamera components use nonidentity defaults, so component
    # relative transform cannot be silently assumed source-aligned. The
    # original world-space native CineTwin capture and original Sequencer
    # source action remain mandatory; exact component transform ownership is
    # independently constrained to no other bound transform/property track.
    return section


def attempt(api: Any,workspace: Path,job: dict,request: dict) -> dict:
    if request.get("strategy")!=evidence.STRATEGY:
        raise AnimatedCameraNativeError("Wrong animated camera key strategy.")
    candidate=Path(job["candidate_dir"]).resolve()
    fid=str(request.get("feedback_id") or "")
    if not re.fullmatch("[a-f0-9]{32}",fid):
        raise AnimatedCameraNativeError(
            "A current explicit camera keyframe correction request is required."
        )
    active=_load(candidate/("user-feedback-active-"+job["job_id"]+".json"))
    feedback=_load(candidate/("user-feedback-"+fid+".json"))
    if (active.get("feedback_id")!=fid
            or active.get("job_id")!=job["job_id"]
            or active.get("candidate_id")!=job["candidate_id"]
            or feedback.get("kind")!="cutsceneai.studio.user_feedback"
            or feedback.get("feedback_id")!=fid
            or feedback.get("job_id")!=job["job_id"]
            or feedback.get("candidate_id")!=job["candidate_id"]
            or not evidence.message_requests_key(feedback.get("message"))):
        raise AnimatedCameraNativeError("Stale/ambiguous camera-keyframe consent.")
    proof=evidence.build(workspace,job)
    if (request.get("animated_camera_key_repair_sha256")
            !=proof["animated_camera_key_repair_sha256"]
            or request.get("source_camera_occurrence_id")
            !=proof["source_camera_occurrence_id"]):
        raise AnimatedCameraNativeError(
            "Original source/native camera position-key proof is stale."
        )
    setup_path=Path(str(job.get("setup_receipt_file") or ""))
    if (setup_path.is_symlink() or not setup_path.is_file()
            or setup_path.resolve().parent!=candidate):
        raise AnimatedCameraNativeError(
            "Source-created CineCamera staging receipt is unavailable."
        )
    staged=_load(setup_path).get("actors_created")
    if not isinstance(staged,list):
        raise AnimatedCameraNativeError("Original camera actor staging inventory absent.")
    compiled,_=evidence.readback._safe_json(candidate/"transfer-plan.json")
    actions=[action for action in compiled.get("actions",[])
             if isinstance(action,dict) and action.get("entity_name")
             ==proof["source_camera_name"] and action.get("kind")=="transform"]
    if (len(actions)!=1 or actions[0].get("actor_label")
            !=proof["target_actor_label"]
            or position._hash(actions[0])!=proof["source_camera_action_sha256"]):
        raise AnimatedCameraNativeError("Original compiled camera animation changed.")
    action=actions[0]
    grid.validate_action(action,duration_frames=compiled["duration_frames"])
    sequence=api.load_asset(job["sequence_path"])
    if sequence is None:
        raise AnimatedCameraNativeError("Exact source-generated Level Sequence missing.")
    section=_live_owner(api,sequence,staged,proof,action)
    from unreal_compat import UnrealCompatibilityError
    try:
        key,old_value=_read_channels(api,section,action,repair=proof)
    except (UnrealCompatibilityError,AttributeError,TypeError,RuntimeError) as exc:
        raise AnimatedCameraNativeError(
            "Exact native nine-channel camera-key inventory unavailable."
        ) from exc
    # ALL original key contents and their ordering have been inspected:
    # alter ONLY the one previously measured outlier and compare all nine
    # channels again to the unchanged immutable source-baked action.
    target=float(action["keys"][proof["source_key_frame"]]["location_cm"][
        proof["native_channel_index"]
    ])
    mutated=False
    saved=False
    try:
        mutated=True
        key.set_value(target)
        # The entire source-bound native transform grid must match again,
        # including interpolation and scale defaults, before saving.
        _all_camera_keys_match_source(api, section, action)
        asset_lib=getattr(api,"EditorAssetLibrary",None)
        save=getattr(asset_lib,"save_loaded_asset",None)
        if not callable(save) or save(sequence) is not True:
            raise AnimatedCameraNativeError(
                "Native generated camera Level Sequence save was not confirmed."
            )
        saved=True
        return {
            "status":"ONE_ANIMATED_CAMERA_POSITION_KEY_SAVED_REOPENED_CINETWIN_PENDING",
            "animated_camera_key_repair_sha256":
                proof["animated_camera_key_repair_sha256"],
            "source_camera_occurrence_id":proof["source_camera_occurrence_id"],
            "source_key_frame":proof["source_key_frame"],
            "native_channel_index":proof["native_channel_index"],
            "changes":1,
            "native_key_difference_after_cm":abs(float(key.get_value())-target),
            "native_complete_transform_key_grid_readback_verified":True,
            "sequence_save_confirmed":True,
            "persistence_after_editor_restart_verified":False,
            "cinetwin_reopened_after_repair_verified":False,
            "rendered_camera_motion_verified":False,
            "full_cutscene_fidelity_verified":False,
        }
    finally:
        if mutated and not saved:
            try:
                key.set_value(old_value)
                if abs(float(key.get_value())-old_value)>0.02:
                    raise AnimatedCameraNativeError(
                        "Original native camera key rollback did not restore old value."
                    )
            except (AttributeError,TypeError,ValueError,RuntimeError) as exc:
                raise AnimatedCameraNativeError(
                    "Animated camera key rollback unverified; inspect editor manually."
                ) from exc
