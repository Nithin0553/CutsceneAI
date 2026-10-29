"""Realize a CutSceneAI CSIR reconstruction plan inside supported Unreal Editor runtimes.

Run from the Unreal Python environment, for example:

    import sys
    sys.path.append(r"B:/Research/CutSceneAI/CutsceneAI/integrations/unreal")
    import build_level_sequence
    build_level_sequence.build(
        r"D:/path/Benchmark001.csir.json",
        r"B:/Research/CutSceneAI/CutsceneAI/integrations/unreal/benchmark001_mapping.json",
    )

The script is intentionally conservative and capability-driven: it probes the current
Unreal runtime before target mutation and aborts instead of guessing when a required
engine feature cannot be resolved. It also refuses to replace an existing Level Sequence
unless ``overwrite_sequence`` is enabled in the mapping file.
"""

from __future__ import annotations

import importlib
import math
import os
import sys
from pathlib import Path
from typing import Any

import unreal

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
CINETWIN_DIR = SCRIPT_DIR.parents[1] / "packages" / "cinetwin"
if str(CINETWIN_DIR) not in sys.path:
    sys.path.insert(0, str(CINETWIN_DIR))

import cinetwin_hierarchy_runtime
import hierarchy_realization
import transfer_readiness
import csir_plan
import scene_prep
import unreal_compat

importlib.reload(csir_plan)
importlib.reload(scene_prep)
importlib.reload(unreal_compat)
importlib.reload(cinetwin_hierarchy_runtime)
importlib.reload(hierarchy_realization)


class UnrealBuildError(RuntimeError):
    pass


ROOT_MOTION_TRAJECTORY_CORRECTION_MIN_HORIZONTAL_CM = 10.0
ROOT_MOTION_TRAJECTORY_CORRECTION_EPSILON_CM = 0.05
ROOT_MOTION_CORRECTION_TRACK_PREFIX = "CutSceneAI Root Motion Correction"


def _split_asset_path(asset_path: str) -> tuple[str, str]:
    normalized = asset_path.rstrip("/")
    if not normalized.startswith("/Game/"):
        raise UnrealBuildError(f"Level Sequence path must be under /Game: {asset_path}")
    package_path, name = normalized.rsplit("/", 1)
    return package_path, name


def _find_actor(label: str) -> unreal.Actor:
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    matches = [actor for actor in subsystem.get_all_level_actors() if actor.get_actor_label() == label]
    if len(matches) != 1:
        raise UnrealBuildError(
            f"Expected exactly one level actor labelled '{label}', found {len(matches)}."
        )
    return matches[0]


def _load_asset(asset_path: str) -> unreal.Object:
    asset = unreal.load_asset(asset_path)
    if asset is None:
        raise UnrealBuildError(f"Unreal asset not found: {asset_path}")
    return asset


def _preflight(plan: dict[str, Any]) -> None:
    """Probe target capabilities and mappings before mutating actors or creating assets."""
    required_actions = {str(action["kind"]) for action in plan.get("actions", [])}
    try:
        unreal_compat.validate_runtime_capabilities(required_actions)
    except unreal_compat.UnrealCompatibilityError as exc:
        raise UnrealBuildError(str(exc)) from exc

    # Fail on malformed easing before moving actors or creating a Level
    # Sequence. In particular, never pass Unity's -1 "no blend" sentinel to
    # Sequencer; new plans must normalize it in csir_plan first.
    easing_fields = {
        "skeletal_animation": ("blend_in_seconds", "blend_out_seconds"),
        "audio": ("fade_in_seconds", "fade_out_seconds"),
    }
    for action in plan.get("actions", []):
        for field in easing_fields.get(str(action.get("kind", "")), ()):
            try:
                seconds = float(action.get(field, 0.0))
            except (TypeError, ValueError) as exc:
                raise UnrealBuildError(
                    f"Invalid {field} in prepared action; no scene changes made."
                ) from exc
            if not math.isfinite(seconds) or seconds < 0:
                raise UnrealBuildError(
                    f"Invalid {field}={seconds} in prepared action; "
                    "no scene changes made. Re-prepare an immutable new plan."
                )

    # New cinematic features are preflighted BEFORE changing any level actor.
    needs_easing = any(
        a.get("kind") == "skeletal_animation"
        and (float(a.get("blend_in_seconds", 0.0)) > 0
             or float(a.get("blend_out_seconds", 0.0)) > 0)
        or a.get("kind") == "audio"
        and (float(a.get("fade_in_seconds", 0.0)) > 0
             or float(a.get("fade_out_seconds", 0.0)) > 0)
        for a in plan.get("actions", [])
    )
    needs_linear_keys = any(
        a.get("kind") == "light_intensity"
        or bool(a.get("baked_source_curves"))
        for a in plan.get("actions", [])
    )
    if needs_easing:
        easing = getattr(unreal, "MovieSceneSectionEasingExtensions", None)
        if any(not callable(getattr(easing, name, None))
               for name in ("set_ease_in_duration", "set_ease_out_duration")):
            raise UnrealBuildError("Sequencer section easing extension missing; no level changes made.")
    if needs_linear_keys:
        interp = getattr(unreal, "MovieSceneKeyInterpolation", None)
        if getattr(interp, "LINEAR", None) is None:
            raise UnrealBuildError("Sequencer linear interpolation unavailable; no level changes made.")
    if any(a.get("kind") == "skeletal_animation"
           and float(a.get("source_offset_seconds", 0.0)) > 0
           for a in plan.get("actions", [])):
        seq_ext = getattr(unreal, "MovieSceneSequenceExtensions", None)
        if not callable(getattr(seq_ext, "get_tick_resolution", None)):
            raise UnrealBuildError("Sequencer tick resolution accessor missing; no level changes made.")

    profile = unreal_compat.runtime_profile()
    unreal.log(
        "[CutSceneAI] Runtime capability profile: "
        + ", ".join(f"{key}={value}" for key, value in profile.items())
    )

    asset_path = str(plan["sequence_asset_path"])
    existing = unreal.load_asset(asset_path)
    if existing is not None and not plan.get("overwrite_sequence", False):
        raise UnrealBuildError(
            f"Level Sequence already exists: {asset_path}. "
            "Set overwrite_sequence=true only when intentionally replacing it."
        )

    actor_cache: dict[str, unreal.Actor] = {}
    for entity_name, actor_label in plan.get("bindings", {}).items():
        actor_cache[entity_name] = _find_actor(str(actor_label))

    for action in plan.get("actions", []):
        kind = str(action["kind"])
        if kind == "skeletal_animation":
            animation = _load_asset(str(action["unreal_asset_path"]))
            expected = action.get("expected_root_delta_cm")
            if expected is not None:
                try:
                    target_delta, root_strategy = unreal_compat.extract_animation_root_delta_cm(
                        animation,
                        float(action.get("source_start_seconds", 0.0)),
                        float(action.get("source_end_seconds", 0.0)),
                    )
                except unreal_compat.UnrealCompatibilityError as exc:
                    raise UnrealBuildError(str(exc)) from exc
                base_yaw = float(action.get("base_actor_yaw_degrees", 0.0))
                target_world_delta = csir_plan.rotate_unreal_delta_yaw(
                    target_delta,
                    base_yaw,
                )
                yaw = csir_plan.root_motion_yaw_alignment_degrees(
                    tuple(float(value) for value in expected),
                    target_world_delta,
                )
                action["resolved_root_yaw_degrees"] = yaw
                action["root_motion_sampling_strategy"] = root_strategy
                action["target_root_delta_after_base_cm"] = [
                    float(value) for value in target_world_delta
                ]

                source_profile = action.get("root_motion_source_profile", {})
                source_horizontal = float(
                    source_profile.get("horizontal_end_distance_cm", 0.0)
                    if isinstance(source_profile, dict)
                    else 0.0
                )
                source_samples = action.get("root_motion_source_samples", [])
                if (
                    source_horizontal >= ROOT_MOTION_TRAJECTORY_CORRECTION_MIN_HORIZONTAL_CM
                    and isinstance(source_samples, list)
                    and source_samples
                ):
                    final_yaw = base_yaw + (float(yaw) if yaw is not None else 0.0)
                    rate = plan["display_rate"]
                    fps_n = int(rate["numerator"])
                    fps_d = int(rate["denominator"])
                    correction_by_frame: dict[int, dict[str, Any]] = {}
                    for sample in source_samples:
                        source_time = float(sample["source_time_seconds"])
                        timeline_time = float(sample["timeline_time_seconds"])
                        try:
                            sampled_target_delta, _sample_strategy = (
                                unreal_compat.extract_animation_root_delta_cm(
                                    animation,
                                    float(action.get("source_start_seconds", 0.0)),
                                    source_time,
                                )
                            )
                        except unreal_compat.UnrealCompatibilityError as exc:
                            raise UnrealBuildError(str(exc)) from exc
                        sampled_target_world = csir_plan.rotate_unreal_delta_yaw(
                            sampled_target_delta,
                            final_yaw,
                        )
                        sampled_source_world = tuple(
                            float(value) for value in sample["delta_cm"]
                        )
                        correction = tuple(
                            sampled_source_world[index]
                            - float(sampled_target_world[index])
                            for index in range(3)
                        )
                        frame = csir_plan.seconds_to_frame(
                            timeline_time, fps_n, fps_d
                        )
                        correction_by_frame[frame] = {
                            "frame": int(frame),
                            "correction_delta_cm": [
                                float(value) for value in correction
                            ],
                            "source_delta_cm": [
                                float(value) for value in sampled_source_world
                            ],
                            "target_delta_cm": [
                                float(value) for value in sampled_target_world
                            ],
                        }

                    correction_samples = [
                        correction_by_frame[frame]
                        for frame in sorted(correction_by_frame)
                    ]
                    max_horizontal_correction = max(
                        math.hypot(
                            float(sample["correction_delta_cm"][0]),
                            float(sample["correction_delta_cm"][1]),
                        )
                        for sample in correction_samples
                    )
                    if (
                        max_horizontal_correction
                        > ROOT_MOTION_TRAJECTORY_CORRECTION_EPSILON_CM
                    ):
                        action["root_motion_correction_samples"] = correction_samples
                        action["root_motion_correction_strategy"] = (
                            "actor_world_sampled_translation"
                        )
                        unreal.log(
                            "[CutSceneAI] Preflight root trajectory correction "
                            f"{action['entity_name']}: samples={len(correction_samples)}, "
                            f"max_horizontal_cm={max_horizontal_correction:.3f}, "
                            f"endpoint_cm={tuple(round(float(v), 3) for v in correction_samples[-1]['correction_delta_cm'])}"
                        )

                unreal.log(
                    "[CutSceneAI] Preflight root motion "
                    f"{action['entity_name']}: sampler={root_strategy}, "
                    f"expected_world_cm={tuple(round(float(v), 3) for v in expected)}, "
                    f"target_import_cm={tuple(round(float(v), 3) for v in target_delta)}, "
                    f"base_actor_yaw={round(base_yaw, 3)}, "
                    f"target_base_world_cm={tuple(round(float(v), 3) for v in target_world_delta)}, "
                    f"world_yaw_correction={None if yaw is None else round(yaw, 3)}"
                )
        elif kind == "audio":
            _load_asset(str(action["unreal_asset_path"]))
        elif kind == "camera_setup":
            actor = actor_cache[action["entity_name"]]
            component, resolution_strategy = _camera_component(actor)
            try:
                setup_spec = unreal_compat.validate_camera_setup(
                    component,
                    field_of_view_degrees=float(action["field_of_view_degrees"]),
                    source_axis=str(action.get("source_fov_axis", "vertical")),
                    target_aspect=action.get("target_output_aspect"),
                    projection=str(action.get("projection", "perspective")),
                )
            except unreal_compat.UnrealCompatibilityError as exc:
                raise UnrealBuildError(str(exc)) from exc
            unreal.log(
                "[CutSceneAI] Preflight camera setup "
                f"{actor.get_actor_label()}: component={resolution_strategy}, "
                f"realization={setup_spec['strategy']}"
            )
        elif kind == "camera_fov":
            actor = actor_cache[action["entity_name"]]
            component, resolution_strategy = _camera_component(actor)
            try:
                fov_spec = unreal_compat.prepare_camera_fov_track(
                    component,
                    action["keys"],
                    str(action.get("source_fov_axis", "vertical")),
                    action.get("target_output_aspect"),
                )
            except unreal_compat.UnrealCompatibilityError as exc:
                raise UnrealBuildError(str(exc)) from exc
            unreal.log(
                "[CutSceneAI] Preflight camera "
                f"{actor.get_actor_label()}: component={resolution_strategy}, "
                f"lens={fov_spec['strategy']}"
            )

    # World-space correction tracks for overlapping clips cannot be combined
    # safely until a weighted root trajectory model is available.
    corrected_by_actor: dict[str, int] = {}
    for action in plan.get("actions", []):
        if action.get("root_motion_correction_samples"):
            label = str(action["actor_label"])
            corrected_by_actor[label] = corrected_by_actor.get(label, 0) + 1
    for label, count in corrected_by_actor.items():
        if count > 1:
            raise UnrealBuildError(
                "Multiple sampled root-motion corrections are not yet composable: "
                f"{label}. Rejecting before actor mutation."
            )

    unreal.log("[CutSceneAI] Runtime preflight PASS")


def _apply_scene_prep(csir: dict[str, Any], mapping: dict[str, Any]) -> None:
    for operation in scene_prep.build_scene_prep(csir, mapping):
        actor = _find_actor(str(operation["actor_label"]))
        location = operation["location_cm"]
        pitch, yaw, roll = operation["rotation_pitch_yaw_roll_degrees"]
        scale = operation["scale_xyz"]

        actor.set_actor_location(
            unreal.Vector(float(location[0]), float(location[1]), float(location[2])),
            False,
            False,
        )
        actor.set_actor_rotation(
            unreal_compat.make_rotator_semantic(
                roll=float(roll),
                pitch=float(pitch),
                yaw=float(yaw),
            ),
            False,
        )
        actor.set_actor_scale3d(
            unreal.Vector(float(scale[0]), float(scale[1]), float(scale[2]))
        )
        unreal.log(
            f"[CutSceneAI] Prepared actor {operation['actor_label']} from {operation['source']}"
        )


def _apply_root_motion_alignment(plan: dict[str, Any]) -> None:
    """Apply one measured trajectory calibration per actor before Sequencer build."""
    selected = csir_plan.select_actor_root_motion_alignments(plan.get("actions", []))
    for action in selected:
        yaw = action.get("resolved_root_yaw_degrees")
        if yaw is None or abs(float(yaw)) <= 0.05:
            continue
        actor = _find_actor(str(action["actor_label"]))
        expected = action.get("expected_root_delta_cm", (0.0, 0.0, 0.0))
        horizontal_cm = math.hypot(float(expected[0]), float(expected[1]))
        try:
            strategy = unreal_compat.apply_actor_world_yaw_alignment(actor, float(yaw))
        except unreal_compat.UnrealCompatibilityError as exc:
            raise UnrealBuildError(str(exc)) from exc
        resolved_rotation = actor.get_actor_rotation()
        unreal.log(
            "[CutSceneAI] Root motion aligned "
            f"{action['entity_name']}: space=actor_world, strategy={strategy}, "
            f"calibration_horizontal_cm={horizontal_cm:.3f}, "
            f"yaw_correction={float(yaw):.3f} deg, "
            f"actor_rpy=({float(resolved_rotation.roll):.3f}, "
            f"{float(resolved_rotation.pitch):.3f}, "
            f"{float(resolved_rotation.yaw):.3f})"
        )


def _create_sequence(plan: dict[str, Any]) -> unreal.LevelSequence:
    asset_path = str(plan["sequence_asset_path"])
    existing = unreal.load_asset(asset_path)
    if existing is not None:
        if not plan.get("overwrite_sequence", False):
            raise UnrealBuildError(
                f"Level Sequence already exists: {asset_path}. Set overwrite_sequence=true only "
                "when you intentionally want to replace the generated benchmark sequence."
            )
        unreal.EditorAssetLibrary.delete_asset(asset_path)

    package_path, name = _split_asset_path(asset_path)
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    sequence = asset_tools.create_asset(name, package_path, unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
    if sequence is None:
        raise UnrealBuildError(f"Failed to create Level Sequence: {asset_path}")

    rate = plan["display_rate"]
    sequence.set_display_rate(unreal.FrameRate(int(rate["numerator"]), int(rate["denominator"])))
    sequence.set_playback_start(0)
    sequence.set_playback_end(int(plan["duration_frames"]))
    return sequence


def _add_possessable(sequence: unreal.LevelSequence, actor: unreal.Actor):
    return unreal.MovieSceneSequenceExtensions.add_possessable(sequence, actor)


def _binding_cache(sequence: unreal.LevelSequence, plan: dict[str, Any]) -> dict[str, Any]:
    cache: dict[str, Any] = {}
    for entity_name, actor_label in plan.get("bindings", {}).items():
        actor = _find_actor(str(actor_label))
        cache[entity_name] = {
            "actor": actor,
            "binding": _add_possessable(sequence, actor),
        }
    return cache


def _add_transform(sequence: unreal.LevelSequence, binding: Any, action: dict[str, Any]) -> None:
    track = binding.add_track(unreal.MovieScene3DTransformTrack)
    track.set_display_name(action.get("track_name", "CutSceneAI Transform"))
    section = track.add_section()
    section.set_range(0, sequence.get_playback_end())
    channels = unreal_compat.get_section_channels(section)
    if len(channels) < 6:
        raise UnrealBuildError("Unexpected Unreal transform channel layout; expected at least 6 channels.")

    # Sequencer 3D transform channel order: Location X/Y/Z, Rotation X/Y/Z, Scale X/Y/Z.
    for key in action["keys"]:
        frame = unreal.FrameNumber(int(key["frame"]))
        location = key["location_cm"]
        rotation = key["rotation_rpy_degrees"]
        values = (*location, *rotation)
        for channel, value in zip(channels[:6], values):
            if action.get("baked_source_curves"):
                unreal_compat.add_linear_channel_key(channel, int(key["frame"]), float(value))
            else:
                channel.add_key(frame, float(value))
    # Frame-baked curves must not be smoothed by Unreal auto tangents.
    # AddKey's explicit interpolation argument is MovieSceneKeyInterpolation.


def _add_skeletal_animation(
    sequence: unreal.LevelSequence, binding: Any, action: dict[str, Any],
    existing_track: Any | None = None,
) -> Any:
    animation = _load_asset(action["unreal_asset_path"])
    # Sections from the SAME Unity animation track must share one Unreal track.
    # A separate Unreal track per overlapping clip can override the intended
    # crossfade and produces incorrect weighting at the transition.
    track = existing_track
    if track is None:
        track = binding.add_track(unreal.MovieSceneSkeletalAnimationTrack)
        track.set_display_name(action.get("track_name", "CutSceneAI Animation"))
    section = track.add_section()
    section.set_range(int(action["start_frame"]), int(action["end_frame"]))
    params = section.get_editor_property("params")
    params.set_editor_property("animation", animation)
    # Unity clipIn refers to source media time, not the Sequencer section start.
    # Unreal uses frame offsets into the imported animation; fail rather than
    # silently sampling a different pose when the adapter cannot represent it.
    source_offset = float(action.get("source_offset_seconds", 0.0))
    if source_offset > 1e-9:
        tick_rate = unreal.MovieSceneSequenceExtensions.get_tick_resolution(sequence)
        ticks_per_second = float(tick_rate.numerator) / float(tick_rate.denominator)
        offset_ticks = int(round(source_offset * ticks_per_second))
        try:
            params.set_editor_property("start_frame_offset", unreal.FrameNumber(offset_ticks))
        except Exception as exc:
            raise UnrealBuildError(
                "Unreal does not expose a supported skeletal source trim offset."
            ) from exc
    play_rate = unreal_compat.make_fixed_play_rate(float(action.get("time_scale", 1.0)))
    params.set_editor_property("play_rate", play_rate)
    section.set_editor_property("params", params)
    # Unlike a hard cut, the Unity source explicitly crossfades overlapping
    # clips. Unreal section easing controls how these sections combine.
    fps = sequence.get_display_rate()
    frames_per_second = float(fps.numerator) / float(fps.denominator)
    blend_in_frames = round(float(action.get("blend_in_seconds", 0.0)) * frames_per_second)
    blend_out_frames = round(float(action.get("blend_out_seconds", 0.0)) * frames_per_second)
    try:
        unreal_compat.set_section_easing_frames(
            section, ease_in=int(blend_in_frames), ease_out=int(blend_out_frames)
        )
    except unreal_compat.UnrealCompatibilityError as exc:
        raise UnrealBuildError(str(exc)) from exc

    hold_end_frame = int(action.get("hold_end_frame", action["end_frame"]))
    post_roll_frames = max(0, hold_end_frame - int(action["end_frame"]))
    if post_roll_frames:
        try:
            hold_strategy = unreal_compat.set_section_post_roll_frames(
                section, post_roll_frames
            )
        except unreal_compat.UnrealCompatibilityError as exc:
            raise UnrealBuildError(str(exc)) from exc
        unreal.log(
            "[CutSceneAI] Animation final-pose hold "
            f"{action['entity_name']}: post_roll_frames={post_roll_frames}, "
            f"strategy={hold_strategy}"
        )

    completion = str(action.get("completion_mode", "project_default"))
    try:
        completion_strategy = unreal_compat.set_section_completion_mode(section, completion)
    except unreal_compat.UnrealCompatibilityError as exc:
        raise UnrealBuildError(str(exc)) from exc
    unreal.log(
        "[CutSceneAI] Animation completion "
        f"{action['entity_name']}: mode={completion}, strategy={completion_strategy}"
    )
    return track


def _add_root_motion_correction(
    sequence: unreal.LevelSequence,
    binding: Any,
    actor: unreal.Actor,
    action: dict[str, Any],
) -> None:
    """Apply sampled world-translation compensation without changing animation timing."""
    samples = action.get("root_motion_correction_samples", [])
    if not isinstance(samples, list) or not samples:
        return

    track = binding.add_track(unreal.MovieScene3DTransformTrack)
    track.set_display_name(
        f"{ROOT_MOTION_CORRECTION_TRACK_PREFIX}|"
        f"{int(action['start_frame'])}|{int(action['end_frame'])}"
    )
    section = track.add_section()
    section.set_range(0, sequence.get_playback_end())
    channels = unreal_compat.get_section_channels(section)
    if len(channels) < 6:
        raise UnrealBuildError(
            "Unexpected Unreal transform channel layout for root-motion correction; "
            "expected at least 6 channels."
        )

    base_location = actor.get_actor_location()
    base_rotation = actor.get_actor_rotation()
    base_scale = actor.get_actor_scale3d()

    emitted: dict[int, list[float]] = {}
    for sample in samples:
        frame_number = int(sample["frame"])
        correction = [float(value) for value in sample["correction_delta_cm"]]
        emitted[frame_number] = correction

    last_frame = max(emitted)
    hold_frame = int(sequence.get_playback_end())
    if hold_frame > last_frame:
        emitted[hold_frame] = list(emitted[last_frame])

    for frame_number in sorted(emitted):
        correction = emitted[frame_number]
        frame = unreal.FrameNumber(frame_number)
        channels[0].add_key(frame, float(base_location.x) + correction[0])
        channels[1].add_key(frame, float(base_location.y) + correction[1])
        channels[2].add_key(frame, float(base_location.z) + correction[2])
        channels[3].add_key(frame, float(base_rotation.roll))
        channels[4].add_key(frame, float(base_rotation.pitch))
        channels[5].add_key(frame, float(base_rotation.yaw))
        if len(channels) >= 9:
            channels[6].add_key(frame, float(base_scale.x))
            channels[7].add_key(frame, float(base_scale.y))
            channels[8].add_key(frame, float(base_scale.z))

    unreal.log(
        "[CutSceneAI] Root trajectory correction "
        f"{action['entity_name']}: strategy={action.get('root_motion_correction_strategy')}, "
        f"samples={len(samples)}, hold_end_frame={hold_frame}"
    )


def _camera_component(actor: unreal.Actor) -> tuple[Any, str]:
    try:
        return unreal_compat.resolve_camera_component(actor)
    except unreal_compat.UnrealCompatibilityError as exc:
        raise UnrealBuildError(str(exc)) from exc


def _apply_camera_setup(actor: unreal.Actor, action: dict[str, Any]) -> None:
    component, resolution_strategy = _camera_component(actor)
    try:
        setup_spec = unreal_compat.apply_camera_setup(
            component,
            field_of_view_degrees=float(action["field_of_view_degrees"]),
            source_axis=str(action.get("source_fov_axis", "vertical")),
            target_aspect=action.get("target_output_aspect"),
            projection=str(action.get("projection", "perspective")),
        )
    except unreal_compat.UnrealCompatibilityError as exc:
        raise UnrealBuildError(str(exc)) from exc

    unreal.log(
        "[CutSceneAI] Camera setup "
        f"{actor.get_actor_label()}: component={resolution_strategy}, "
        f"realization={setup_spec['strategy']}, "
        f"target_aspect={setup_spec['target_aspect']}"
    )


def _add_camera_fov(sequence: unreal.LevelSequence, actor: unreal.Actor, action: dict[str, Any]) -> None:
    component, resolution_strategy = _camera_component(actor)
    try:
        fov_spec = unreal_compat.prepare_camera_fov_track(
            component,
            action["keys"],
            str(action.get("source_fov_axis", "vertical")),
            action.get("target_output_aspect"),
        )
    except unreal_compat.UnrealCompatibilityError as exc:
        raise UnrealBuildError(str(exc)) from exc

    component_binding = unreal.MovieSceneSequenceExtensions.add_possessable(sequence, component)
    track = component_binding.add_track(unreal.MovieSceneFloatTrack)
    track.set_display_name("CutSceneAI Camera Lens")
    track.set_property_name_and_path(
        str(fov_spec["property_name"]),
        str(fov_spec["property_path"]),
    )
    section = track.add_section()
    section.set_range(0, sequence.get_playback_end())
    channels = unreal_compat.get_section_channels(section)
    if len(channels) != 1:
        raise UnrealBuildError("Unexpected camera lens channel layout; expected one float/double channel.")
    for key in fov_spec["keys"]:
        if action.get("baked_source_curves"):
            unreal_compat.add_linear_channel_key(channels[0], int(key["frame"]), float(key["value"]))
        else:
            channels[0].add_key(unreal.FrameNumber(int(key["frame"])), float(key["value"]))

    unreal.log(
        "[CutSceneAI] Camera lens adapter "
        f"{actor.get_actor_label()}: component={resolution_strategy}, "
        f"realization={fov_spec['strategy']}"
    )


def _add_camera_cuts(sequence: unreal.LevelSequence, actions: list[dict[str, Any]], bindings: dict[str, Any]) -> None:
    if not actions:
        return
    track = unreal.MovieSceneSequenceExtensions.add_track(sequence, unreal.MovieSceneCameraCutTrack)
    track.set_display_name("CutSceneAI Camera Cuts")
    for action in sorted(actions, key=lambda item: item["start_frame"]):
        section = track.add_section()
        section.set_range(int(action["start_frame"]), int(action["end_frame"]))
        binding = bindings[action["entity_name"]]["binding"]
        binding_id = unreal.MovieSceneSequenceExtensions.get_binding_id(sequence, binding)
        section.set_camera_binding_id(binding_id)


def _add_light_intensity(sequence: unreal.LevelSequence, actor: unreal.Actor, action: dict[str, Any]) -> None:
    """Create a native intensity track bound to the existing light component."""
    cls = getattr(unreal, "LightComponentBase", None)
    if cls is None:
        raise UnrealBuildError("Unreal runtime lacks LightComponentBase.")
    components = actor.get_components_by_class(cls)
    if len(components) != 1:
        raise UnrealBuildError(
            f"Expected one light component on {actor.get_actor_label()}, found {len(components)}.")
    component = components[0]
    binding = unreal.MovieSceneSequenceExtensions.add_possessable(sequence, component)
    track = binding.add_track(unreal.MovieSceneFloatTrack)
    track.set_display_name("CutSceneAI Light Intensity")
    track.set_property_name_and_path("Intensity", "Intensity")
    section = track.add_section()
    section.set_range(0, sequence.get_playback_end())
    channels = unreal_compat.get_section_channels(section)
    if len(channels) != 1:
        raise UnrealBuildError("Light intensity requires exactly one float channel.")
    for key in action["keys"]:
        unreal_compat.add_linear_channel_key(channels[0], int(key["frame"]), float(key["value"]))


def _add_audio(sequence: unreal.LevelSequence, action: dict[str, Any]) -> None:
    sound = _load_asset(action["unreal_asset_path"])
    track = unreal.MovieSceneSequenceExtensions.add_track(sequence, unreal.MovieSceneAudioTrack)
    track.set_display_name("CutSceneAI Audio")
    section = track.add_section()
    section.set_range(int(action["start_frame"]), int(action["end_frame"]))
    section.set_sound(sound)
    section.set_looping(bool(action.get("loop", False)))
    # Audio fades are source Timeline easing semantics. Require native section
    # easing instead of silently discarding authored envelopes.
    rate = sequence.get_display_rate()
    fps = float(rate.numerator) / float(rate.denominator)
    try:
        unreal_compat.set_section_easing_frames(
            section,
            ease_in=int(round(float(action.get("fade_in_seconds", 0.0)) * fps)),
            ease_out=int(round(float(action.get("fade_out_seconds", 0.0)) * fps)),
        )
    except unreal_compat.UnrealCompatibilityError as exc:
        raise UnrealBuildError(str(exc)) from exc


def _add_marker(sequence: unreal.LevelSequence, action: dict[str, Any]) -> None:
    marked = unreal.MovieSceneMarkedFrame()
    marked.set_editor_property("frame_number", unreal.FrameNumber(int(action["frame"])))
    marked.set_editor_property("label", str(action["label"]))
    try:
        unreal.MovieSceneSequenceExtensions.add_marked_frame_to_sequence(
            sequence, marked, unreal.MovieSceneTimeUnit.DISPLAY_RATE
        )
    except AttributeError:
        # ScriptMethod fallback for builds where the extension is exposed directly on the asset.
        sequence.add_marked_frame(marked)


def build(csir_path: str | os.PathLike[str], mapping_path: str | os.PathLike[str]) -> unreal.LevelSequence:
    csir = csir_plan.load_json(csir_path)
    mapping = csir_plan.load_json(mapping_path)
    # Do not silently construct a partial target when the source requires
    # unsupported tracks or a mapped clip is missing.
    readiness = transfer_readiness.audit(csir, mapping)
    if readiness["generation"] == "BLOCKED":
        failures = [
            f"{entry['track_name'] or entry['track_id']}: {'; '.join(entry['reasons'])}"
            for entry in readiness["tracks"] if entry["state"] == "BLOCKED"
        ]
        if readiness.get("plan_error"):
            failures.append(str(readiness["plan_error"]))
        raise UnrealBuildError(
            "Source readiness BLOCKED before level mutation: " +
            " | ".join(failures) +
            ". Run tools/transfer_readiness.py for a complete source-track ledger."
        )
    if readiness["unverified_behavior_count"]:
        unreal.log_warning(
            "[CutSceneAI] Transfer coverage PARTIAL for "
            f"{readiness['unverified_behavior_count']} source tracks. "
            "Generation is not cinematic fidelity acceptance."
        )
    plan = csir_plan.build_plan(csir, mapping)

    return _build_prepared_plan(csir, mapping, plan)


def _build_prepared_plan(
    csir: dict[str, Any], mapping: dict[str, Any], plan: dict[str, Any]
) -> unreal.LevelSequence:
    """Shared realization of strict or independently audited partial transfer plans."""
    # Hierarchy realization remains opt-in until a staging target project and
    # evaluated child-motion verification have been proven in the user's engine.
    # Compute all constraints BEFORE making any level actor changes.
    hierarchy_operations = None
    if bool(mapping.get("enable_cinetwin_hierarchy", False)):
        hierarchy_operations = hierarchy_realization.build_attachment_operations(
            csir, mapping, plan["actions"]
        )
        unreal.log(
            "[CineTwin] Preflight actor hierarchy: "
            f"attachments={len(hierarchy_operations['attachments'])}, "
            f"unresolved_source_parents="
            f"{len(hierarchy_operations['unresolved_source_parents'])}."
        )

    _preflight(plan)
    # Level actors are shared scene state. Restore their world poses if any
    # construction step fails; do not leave partly placed cameras/characters.
    previous_poses = {
        str(label): (_find_actor(str(label)), _find_actor(str(label)).get_actor_transform())
        for label in plan.get("bindings", {}).values()
    }
    attachment_changes: list[dict[str, Any]] = []
    sequence: unreal.LevelSequence | None = None
    try:
        _apply_scene_prep(csir, mapping)
        _apply_root_motion_alignment(plan)
        if hierarchy_operations is not None:
            attachment_changes = cinetwin_hierarchy_runtime.apply_hierarchy(
                hierarchy_operations
            )
        sequence = _create_sequence(plan)
        bindings = _binding_cache(sequence, plan)

        camera_cuts: list[dict[str, Any]] = []
        root_corrections: list[dict[str, Any]] = []
        skeletal_tracks: dict[tuple[str, str], Any] = {}
        for action in plan["actions"]:
            kind = action["kind"]
            if kind == "transform":
                _add_transform(sequence, bindings[action["entity_name"]]["binding"], action)
            elif kind == "skeletal_animation":
                cache_key = (str(action["entity_name"]), str(action.get("track_name", "")))
                skeletal_tracks[cache_key] = _add_skeletal_animation(
                    sequence,
                    bindings[action["entity_name"]]["binding"],
                    action,
                    existing_track=skeletal_tracks.get(cache_key),
                )
                if action.get("root_motion_correction_samples"):
                    root_corrections.append(action)
            elif kind == "camera_setup":
                _apply_camera_setup(bindings[action["entity_name"]]["actor"], action)
            elif kind == "camera_fov":
                _add_camera_fov(sequence, bindings[action["entity_name"]]["actor"], action)
            elif kind == "camera_cut":
                camera_cuts.append(action)
            elif kind == "light_intensity":
                _add_light_intensity(sequence, bindings[action["entity_name"]]["actor"], action)
            elif kind == "audio":
                _add_audio(sequence, action)
            elif kind == "marker":
                _add_marker(sequence, action)
            else:
                raise UnrealBuildError(f"Unsupported reconstruction action: {kind}")

        corrections_by_actor: dict[str, list[dict[str, Any]]] = {}
        for action in root_corrections:
            corrections_by_actor.setdefault(str(action["actor_label"]), []).append(action)
        for actor_label, actions in corrections_by_actor.items():
            if len(actions) > 1:
                raise UnrealBuildError(
                    "Multiple sampled root-motion corrections for one actor are not "
                    f"yet safely composable: {actor_label}. Refusing to guess."
                )
            action = actions[0]
            binding_record = bindings[action["entity_name"]]
            _add_root_motion_correction(
                sequence,
                binding_record["binding"],
                binding_record["actor"],
                action,
            )

        _add_camera_cuts(sequence, camera_cuts, bindings)
        unreal.EditorAssetLibrary.save_loaded_asset(sequence)
        unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(sequence)
        unreal.LevelSequenceEditorBlueprintLibrary.refresh_current_level_sequence()
        unreal.log(f"[CutSceneAI] Generated Level Sequence: {plan['sequence_asset_path']}")
        return sequence
    except Exception:
        # Do NOT call EditorAssetLibrary.delete_asset() here: it force-deletes
        # a newly allocated package while native Sequencer bindings/sections
        # may still reference it. Unreal can then report a potentially corrupt
        # package. Preserve the original traceback, restore actor state where
        # possible, and require a fresh editor session/target for the retry.
        if sequence is not None:
            unreal.log_error(
                "[CutSceneAI] INCOMPLETE_UNSAVED_SEQUENCE: "
                + str(plan["sequence_asset_path"])
                + ". Do not save this asset or the modified level. "
                "Close the editor without saving, inspect a backed-up project "
                "after restart, then retry with a NEW target path."
            )
        if attachment_changes:
            try:
                cinetwin_hierarchy_runtime.rollback_hierarchy(attachment_changes)
                unreal.log_warning(
                    "[CineTwin] Restored newly created actor attachments "
                    "after generation failure (persistence not verified)."
                )
            except Exception as restore_error:
                unreal.log_error(
                    "[CineTwin] Failed to restore actor attachments: "
                    + str(restore_error)
                )
        for label, (actor, transform) in previous_poses.items():
            try:
                actor.set_actor_transform(transform, False, True)
            except Exception as restore_error:
                unreal.log_error(
                    f"[CutSceneAI] Unable to restore actor {label}: {restore_error}"
                )
        raise



def build_prepared_files(
    csir_path: str | os.PathLike[str],
    mapping_path: str | os.PathLike[str],
    plan_path: str | os.PathLike[str],
    report_path: str | os.PathLike[str],
    evidence_path: str | os.PathLike[str],
    runtime_receipt_path: str | os.PathLike[str],
    *,
    expected_project_path: str,
    expected_level_path: str,
) -> unreal.LevelSequence:
    """Execute a deterministic best-effort plan after independently checking inputs.

    The engine does not trust a client-supplied action plan: it recomputes
    generation from source/mapping/verified capture and compares the result
    before calling any code that changes actors or assets.
    """
    import hashlib
    import json
    import traceback

    STUDIO_DIR = SCRIPT_DIR.parents[1] / "packages" / "studio"
    if str(STUDIO_DIR) not in sys.path:
        sys.path.insert(0, str(STUDIO_DIR))
    import transfer_backend

    receipt = {
        "kind": "cutsceneai.unreal.best_effort_receipt",
        "schema_version": "0.1.0",
        "stage": "source_verification",
        "status": "BLOCKED",
        "scene_modified": False,
        "target_fidelity_established": False,
    }
    output = Path(runtime_receipt_path)
    if output.exists():
        raise UnrealBuildError(f"Refusing to overwrite existing runtime receipt: {output}")
    if not output.parent.is_dir():
        raise UnrealBuildError("Receipt parent directory does not exist.")
    try:
        # This is staging code: bind the run to a known Unreal project/level.
        # Never modify an unrelated editor window by accident.
        if not expected_project_path or not expected_level_path:
            raise UnrealBuildError("Expected project and level must be specified.")
        project = str(unreal.Paths.get_project_file_path())
        if os.path.normcase(os.path.abspath(project)) != os.path.normcase(
            os.path.abspath(expected_project_path)
        ):
            raise UnrealBuildError(
                f"Wrong Unreal project loaded: {project}; expected {expected_project_path}"
            )
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        level = str(world.get_path_name()).split(".")[0]
        if level != expected_level_path:
            raise UnrealBuildError(
                f"Wrong Unreal level loaded: {level}; expected {expected_level_path}"
            )
        receipt["verified_project"] = project
        receipt["verified_level"] = level
        evidence = csir_plan.load_json(evidence_path)
        actual_source_hash = hashlib.sha256(Path(csir_path).read_bytes()).hexdigest()
        actual_mapping_hash = hashlib.sha256(Path(mapping_path).read_bytes()).hexdigest()
        if (evidence.get("csir_sha256") != actual_source_hash
                or evidence.get("mapping_sha256") != actual_mapping_hash):
            raise UnrealBuildError("Prepared plan is stale: source/mapping file changed.")
        capture_path = evidence.get("source_capture_path")
        if capture_path and (
            hashlib.sha256(Path(capture_path).read_bytes()).hexdigest()
            != evidence.get("source_capture_sha256")
        ):
            raise UnrealBuildError("Source CineTwin capture has changed since planning.")

        original_csir = csir_plan.load_json(csir_path)
        original_mapping = csir_plan.load_json(mapping_path)
        expected_plan, expected_report, expected_evidence = transfer_backend.compose_files(
            csir_path, mapping_path, capture_path=capture_path
        )
        submitted_plan = csir_plan.load_json(plan_path)
        submitted_report = csir_plan.load_json(report_path)
        # Compare to the JSON encoding that wrote the prepared files.
        # Native planner vectors may be tuples; JSON round-trips into lists.
        # Never weaken exact value/provenance checking just to accommodate
        # representational differences.
        try:
            transfer_backend.verify_prepared_artifacts(
                submitted_plan,
                submitted_report,
                evidence,
                expected_plan,
                expected_report,
                expected_evidence,
            )
        except transfer_backend.TransferBackendError as exc:
            raise UnrealBuildError(str(exc)) from exc
        if (submitted_report.get("mode") != "BEST_EFFORT"
                or submitted_report.get("source_track_count")
                != len(original_csir.get("tracks", []))):
            raise UnrealBuildError("Missing source feature-accountability evidence.")
        if original_mapping.get("overwrite_sequence", False):
            raise UnrealBuildError("Best-effort runs cannot overwrite a target sequence.")
        receipt["source_track_count"] = submitted_report["source_track_count"]
        receipt["track_outcomes"] = submitted_report["outcomes"]
        receipt["planned_actions"] = submitted_report["actions"]
        receipt["stage"] = "unreal_capability_and_generation"
        # Once the Unreal builder begins, modifications are possible even
        # when actor rollback subsequently succeeds. Never claim otherwise.
        receipt["scene_modified"] = "POSSIBLE_MUST_INSPECT"
        # This call checks actual assets/actors/engine features before mutation.
        sequence = _build_prepared_plan(original_csir, original_mapping, submitted_plan)
        receipt["status"] = "GENERATED_UNVERIFIED"
        receipt["stage"] = "complete"
        receipt["scene_modified"] = True
        receipt["generated_sequence"] = sequence.get_path_name()
        unreal.log_warning(
            "[CutSceneAI] Best-effort generation finished with losses disclosed. "
            "No saved target behavior or fidelity comparison has passed yet."
        )
        return sequence
    except Exception as exc:
        receipt["exception"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        unreal.log_error(
            f"[CutSceneAI] Best-effort transfer stopped at {receipt['stage']}: {exc}"
        )
        raise
    finally:
        output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")


if __name__ == "__main__":
    csir_path = os.environ.get("CUTSCENEAI_CSIR")
    mapping_path = os.environ.get("CUTSCENEAI_UNREAL_MAPPING")
    if not csir_path or not mapping_path:
        raise UnrealBuildError(
            "Set CUTSCENEAI_CSIR and CUTSCENEAI_UNREAL_MAPPING, or import this module and call build()."
        )
    build(csir_path, mapping_path)
