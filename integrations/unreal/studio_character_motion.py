"""Guarded native actor trajectory adapter and independent channel readback.

No asset offsets, root stripping, pose fitting or inferred calibration. A raw
native clip containing a second root trajectory refuses before sequence build.
"""
from __future__ import annotations

import math

import character_motion as motion
import character_compatibility as compatibility

CHANNEL_NAMES = tuple(f"{group}.{axis}" for group in ("Location", "Rotation", "Scale") for axis in "XYZ")


def available(api):
    required = (
        ("AnimationLibrary", "extract_root_track_transform"),
        ("MovieSceneSequenceExtensions", "get_bindings"),
        ("MovieSceneSequenceExtensions", "locate_bound_objects"),
        ("MovieSceneSequenceExtensions", "get_display_rate"),
        ("MovieSceneSequenceExtensions", "get_tick_resolution"),
        ("MovieSceneSectionExtensions", "get_all_channels"),
        ("MovieSceneSectionExtensions", "get_start_frame"),
        ("MovieSceneSectionExtensions", "get_end_frame"),
        ("MovieSceneScriptingDoubleChannel", "get_keys"),
        ("MovieSceneScriptingDoubleChannel", "get_default"),
        ("MovieSceneScriptingDoubleChannel", "set_default"),
        ("MovieSceneScriptingDoubleKey", "get_time"),
        ("MovieSceneScriptingDoubleKey", "get_value"),
        ("MovieSceneScriptingDoubleKey", "get_interpolation_mode"),
        ("MovieSceneScriptingFloatChannel", "get_keys"),
        ("MovieSceneScriptingFloatChannel", "get_default"),
        ("MovieSceneScriptingFloatChannel", "set_default"),
        ("Actor", "get_attach_parent_actor"),
        ("Actor", "get_actor_scale3d"),
        ("PrimitiveComponent", "is_simulating_physics"),
        ("MovieSceneSection", "set_post_roll_frames"),
        ("MovieSceneSection", "get_post_roll_frames"),
        ("MovieSceneSection", "is_active"),
        ("MovieSceneSection", "set_is_active"),
        ("MovieSceneSection", "get_blend_type"),
        ("MovieSceneSection", "set_blend_type"),
    )
    return (all(callable(getattr(getattr(api, owner, None), name, None)) for owner, name in required)
            and hasattr(api, "MovieScene3DTransformTrack")
            and getattr(getattr(api, "MovieSceneBlendType", None), "ABSOLUTE", None) is not None
            and getattr(getattr(api, "MovieSceneKeyInterpolation", None), "LINEAR", None) is not None
            and getattr(getattr(api, "RichCurveInterpMode", None), "RCIM_LINEAR", None) is not None)


def transform_channels(api, section, *, initialize=False):
    """UE5 transform sections can also expose a float manual-weight channel.

    Resolve the nine double channels by semantic name, never mistake Weight
    or an optional constraint channel for scale/rotation.
    """
    channels = list(api.MovieSceneSectionExtensions.get_all_channels(section))
    doubles = [c for c in channels if isinstance(c, api.MovieSceneScriptingDoubleChannel)]
    named = {str(c.channel_name): c for c in doubles}
    if len(doubles) != 9 or set(named) != set(CHANNEL_NAMES):
        raise RuntimeError("Native actor trajectory requires nine uniquely named double transform channels.")
    extra = [c for c in channels if not isinstance(c, api.MovieSceneScriptingDoubleChannel)]
    if len(extra) > 1 or any(not isinstance(c, api.MovieSceneScriptingFloatChannel)
                             or str(c.channel_name) not in ("Weight", "ManualWeight") for c in extra):
        raise RuntimeError("Native transform contains unsupported constraint or override channels.")
    for weight in extra:
        if initialize:
            weight.set_default(1.0)
        if list(weight.get_keys()) or not math.isclose(float(weight.get_default()), 1, abs_tol=1e-7, rel_tol=0):
            raise RuntimeError("Native actor trajectory has a competing manual weight curve.")
    return [named[name] for name in CHANNEL_NAMES]


def action(plan):
    choice = plan.get("ai_character_animation") or {}
    if choice.get("action_id") != motion.ACTION:
        return None
    transforms = [a for a in plan["actions"] if a.get("source_entity_id") == choice["source_entity_id"]
                  and a["kind"] == "transform"]
    if len(transforms) != 1:
        raise RuntimeError("Moving character needs exactly one source-bound native actor trajectory.")
    return transforms[0]


def _root(api, clip, rate, expected_duration, used_times):
    if str(clip.get_class().get_name()) != "AnimSequence":
        raise RuntimeError("Moving character requires a native AnimSequence.")
    duration = float(clip.get_play_length())
    if (not math.isfinite(duration) or not math.isclose(duration, expected_duration, abs_tol=1 / rate, rel_tol=0)
            or not 0 < duration * rate < motion.MAX_FRAMES - 1):
        raise RuntimeError("Native animation duration or root sample budget differs from source evidence.")
    # Read raw animation, including motion that a root-extraction flag could hide.
    if any(not math.isfinite(t) or not -1e-8 <= t <= duration + 1e-8 for t in used_times):
        raise RuntimeError("Moving actor clip trim/speed samples exceed native media duration.")
    times = sorted({min(i / rate, duration) for i in range(math.ceil(duration * rate) + 1)}
                   | {min(max(t, 0), duration) for t in used_times} | {duration})
    rows = []
    for time in times:
        transform = api.AnimationLibrary.extract_root_track_transform(clip, time)
        p, q, s = transform.translation, transform.rotation, transform.scale3d
        row = [float(v) for v in (p.x, p.y, p.z, q.x, q.y, q.z, q.w, s.x, s.y, s.z)]
        if not all(math.isfinite(v) for v in row) or math.dist(row[7:], [1, 1, 1]) > 1e-5:
            raise RuntimeError("Native skeletal root is nonfinite or has unsupported scale.")
        motion.conjugate(row[3:7])
        rows.append(row)
    translation = max(math.dist(rows[0][:3], row[:3]) for row in rows)
    rotation = max(compatibility.angle_degrees(rows[0][3:7], row[3:7]) for row in rows)
    if translation > compatibility.STILL_CM or rotation > compatibility.STILL_DEGREES:
        raise RuntimeError(f"Native clip has competing skeletal-root motion ({translation:.6f} cm, {rotation:.6f} degrees).")
    return {"clip": str(clip.get_path_name()).split(".", 1)[0], "sample_count": len(rows),
            "maximum_translation_cm": translation, "maximum_rotation_degrees": rotation,
            "raw_root_samples_sha256": compatibility.digest([times, rows]), "status": "PASS"}


def validate_staged(api, plan):
    selected = action(plan)
    if selected is None:
        return None
    if not available(api):
        raise RuntimeError("Native moving-character root inspection or transform readback API unavailable.")
    related = [a for a in plan["actions"] if a.get("entity_name") == selected["entity_name"]]
    clips = [a for a in related if a["kind"] == "skeletal_animation"]
    if (len(clips) != 1 or any(a["kind"] == "skeletal_world_root_lock" or a.get("expected_root_delta_cm") is not None
                               for a in related)
            or len([a for a in related if a["kind"] == "transform"]) != 1):
        raise RuntimeError("Native moving-character plan has competing motion owners.")
    clip = api.load_asset(clips[0]["unreal_asset_path"])
    if clip is None:
        raise RuntimeError("Native animation is missing after staging.")
    rate = plan["display_rate"]
    times = [clips[0]["source_offset_seconds"] + key["frame"] * rate["denominator"] / rate["numerator"] * clips[0]["time_scale"]
             for key in selected["keys"]]
    actors = api.get_editor_subsystem(api.EditorActorSubsystem).get_all_level_actors()
    matches = [a for a in actors if str(a.get_actor_label()) == selected["actor_label"]]
    if len(matches) != 1:
        raise RuntimeError("Staged moving character has a missing or ambiguous native actor binding.")
    actor, = matches
    scale = actor.get_actor_scale3d()
    component = actor.get_editor_property("skeletal_mesh_component")
    if (actor.get_attach_parent_actor() is not None or not all(math.isfinite(v) for v in (scale.x, scale.y, scale.z))
            or math.dist([scale.x, scale.y, scale.z], [1, 1, 1]) > 1e-5
            or component.is_simulating_physics() is not False):
        raise RuntimeError("Native actor has a parent, non-unit scale or competing physics motion owner.")
    return {"status": "PASS", "motion_ownership": motion.OWNER,
            "roots": [_root(api, clip, selected["native_root_sample_rate"], selected["native_root_duration_seconds"], times)]}


def readback(api, sequence, actor, plan):
    selected = action(plan)
    if selected is None:
        return None
    roots = validate_staged(api, plan)
    extension = api.MovieSceneSequenceExtensions
    rate = extension.get_display_rate(sequence)
    if {"numerator": int(rate.numerator), "denominator": int(rate.denominator)} != plan["display_rate"]:
        raise RuntimeError("Native moving-character display rate differs from source.")
    world = api.get_editor_subsystem(api.UnrealEditorSubsystem).get_editor_world()
    bindings, tracks = [], []
    for binding in extension.get_bindings(sequence):
        owners = list(extension.locate_bound_objects(sequence, binding, world))
        if any(a.get_path_name() == actor.get_path_name() for a in owners):
            if len(owners) != 1:
                raise RuntimeError("Native actor trajectory has an ambiguous owning binding.")
            bindings.append(binding)
            tracks.extend(t for t in binding.get_tracks() if isinstance(t, api.MovieScene3DTransformTrack))
    if len(bindings) != 1 or len(tracks) != 1 or len(tracks[0].get_sections()) != 1:
        raise RuntimeError("Native actor trajectory track or owning binding is missing or duplicated.")
    section, = tracks[0].get_sections()
    blend = section.get_blend_type()
    if section.is_active() is not True or blend.is_valid is not True or blend.blend_type != api.MovieSceneBlendType.ABSOLUTE:
        raise RuntimeError("Native actor trajectory is inactive or has a non-absolute blend owner.")
    section_api = api.MovieSceneSectionExtensions
    if (int(section_api.get_start_frame(section)) != 0
            or int(section_api.get_end_frame(section)) != plan["duration_frames"] + 1):
        raise RuntimeError("Native actor trajectory section range changed.")
    channels = transform_channels(api, section)
    expected = selected["keys"]
    values = [[*key["location_cm"], *key["rotation_rpy_degrees"]] for key in expected]
    observed = []
    for index, channel in enumerate(channels[:6]):
        keys = list(channel.get_keys())
        rows = []
        for key in keys:
            time = key.get_time()  # Native default unit is DISPLAY_RATE.
            frame = int(time.frame_number.value)
            value = float(key.get_value())
            if (abs(float(time.sub_frame)) > 1e-7 or not math.isfinite(value)
                    or key.get_interpolation_mode() != api.RichCurveInterpMode.RCIM_LINEAR):
                raise RuntimeError("Native trajectory contains subframes, nonfinite values or nonlinear keys.")
            rows.append([frame, value])
        rows.sort()
        if (len(rows) != len(expected) or any(row[0] != key["frame"] or
                not math.isclose(row[1], value[index], abs_tol=1e-5, rel_tol=0)
                for row, key, value in zip(rows, expected, values))):
            raise RuntimeError(f"Native actor trajectory channel {index} differs from measured source keys.")
        observed.append(rows)
    if any(list(c.get_keys()) or not math.isclose(float(c.get_default()), 1, abs_tol=1e-7, rel_tol=0)
           for c in channels[6:]):
        raise RuntimeError("Native actor trajectory contains a second scale owner.")
    return {"status": "PASS", "motion_ownership": motion.OWNER, "actor_path": actor.get_path_name(),
            "owning_actor_binding_count": len(bindings), "transform_track_count": len(tracks),
            "section_start_frame": 0, "section_end_frame": plan["duration_frames"] + 1,
            "display_rate": plan["display_rate"], "frame_count": len(expected),
            "trajectory_sha256": plan["ai_character_motion_binding"]["trajectory_sha256"],
            "observed_channels_sha256": compatibility.digest(observed), "native_roots": roots,
            "fidelity_verified": False}
