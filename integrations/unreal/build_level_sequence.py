"""Realize a CutSceneAI CSIR reconstruction plan inside Unreal Engine 5.8.

Run from the Unreal Python environment, for example:

    import sys
    sys.path.append(r"B:/Research/CutSceneAI/CutsceneAI/integrations/unreal")
    import build_level_sequence
    build_level_sequence.build(
        r"D:/path/Benchmark001.csir.json",
        r"B:/Research/CutSceneAI/CutsceneAI/integrations/unreal/benchmark001_mapping.json",
    )

The script is intentionally conservative: it aborts instead of replacing an existing
Level Sequence unless ``overwrite_sequence`` is enabled in the mapping file.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

import unreal

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import csir_plan
import scene_prep

importlib.reload(csir_plan)
importlib.reload(scene_prep)


class UnrealBuildError(RuntimeError):
    pass


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
            unreal.Rotator(float(pitch), float(yaw), float(roll)),
            False,
        )
        actor.set_actor_scale3d(
            unreal.Vector(float(scale[0]), float(scale[1]), float(scale[2]))
        )
        unreal.log(
            f"[CutSceneAI] Prepared actor {operation['actor_label']} from {operation['source']}"
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
    channels = section.get_channels()
    if len(channels) < 6:
        raise UnrealBuildError("Unexpected Unreal transform channel layout; expected at least 6 channels.")

    # Sequencer 3D transform channel order: Location X/Y/Z, Rotation X/Y/Z, Scale X/Y/Z.
    for key in action["keys"]:
        frame = unreal.FrameNumber(int(key["frame"]))
        location = key["location_cm"]
        rotation = key["rotation_rpy_degrees"]
        channels[0].add_key(frame, float(location[0]))
        channels[1].add_key(frame, float(location[1]))
        channels[2].add_key(frame, float(location[2]))
        channels[3].add_key(frame, float(rotation[0]))
        channels[4].add_key(frame, float(rotation[1]))
        channels[5].add_key(frame, float(rotation[2]))


def _add_skeletal_animation(binding: Any, action: dict[str, Any]) -> None:
    animation = _load_asset(action["unreal_asset_path"])
    track = binding.add_track(unreal.MovieSceneSkeletalAnimationTrack)
    track.set_display_name(action.get("track_name", "CutSceneAI Animation"))
    section = track.add_section()
    section.set_range(int(action["start_frame"]), int(action["end_frame"]))
    params = section.get_editor_property("params")
    params.set_editor_property("animation", animation)
    play_rate = unreal.MovieSceneTimeWarpVariant()
    play_rate.set_fixed_play_rate(float(action.get("time_scale", 1.0)))
    params.set_editor_property("play_rate", play_rate)
    section.set_editor_property("params", params)


def _camera_component(actor: unreal.Actor) -> unreal.CameraComponent:
    if isinstance(actor, unreal.CameraActor):
        return actor.get_camera_component()
    components = actor.get_components_by_class(unreal.CameraComponent)
    if len(components) != 1:
        raise UnrealBuildError(
            f"Camera actor '{actor.get_actor_label()}' must expose exactly one CameraComponent."
        )
    return components[0]


def _add_camera_fov(sequence: unreal.LevelSequence, actor: unreal.Actor, action: dict[str, Any]) -> None:
    component = _camera_component(actor)
    component_binding = unreal.MovieSceneSequenceExtensions.add_possessable(sequence, component)
    track = component_binding.add_track(unreal.MovieSceneFloatTrack)
    track.set_display_name("CutSceneAI Field Of View")
    track.set_property_name_and_path("FieldOfView", "FieldOfView")
    section = track.add_section()
    section.set_range(0, sequence.get_playback_end())
    channels = section.get_channels()
    if len(channels) != 1:
        raise UnrealBuildError("Unexpected FOV channel layout; expected one float/double channel.")
    for key in action["keys"]:
        channels[0].add_key(unreal.FrameNumber(int(key["frame"])), float(key["value"]))


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


def _add_audio(sequence: unreal.LevelSequence, action: dict[str, Any]) -> None:
    sound = _load_asset(action["unreal_asset_path"])
    track = unreal.MovieSceneSequenceExtensions.add_track(sequence, unreal.MovieSceneAudioTrack)
    track.set_display_name("CutSceneAI Audio")
    section = track.add_section()
    section.set_range(int(action["start_frame"]), int(action["end_frame"]))
    section.set_sound(sound)
    section.set_looping(bool(action.get("loop", False)))


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
    plan = csir_plan.build_plan(csir, mapping)

    _apply_scene_prep(csir, mapping)
    sequence = _create_sequence(plan)
    bindings = _binding_cache(sequence, plan)

    camera_cuts: list[dict[str, Any]] = []
    for action in plan["actions"]:
        kind = action["kind"]
        if kind == "transform":
            _add_transform(sequence, bindings[action["entity_name"]]["binding"], action)
        elif kind == "skeletal_animation":
            _add_skeletal_animation(bindings[action["entity_name"]]["binding"], action)
        elif kind == "camera_fov":
            _add_camera_fov(sequence, bindings[action["entity_name"]]["actor"], action)
        elif kind == "camera_cut":
            camera_cuts.append(action)
        elif kind == "audio":
            _add_audio(sequence, action)
        elif kind == "marker":
            _add_marker(sequence, action)
        else:
            raise UnrealBuildError(f"Unsupported reconstruction action: {kind}")

    _add_camera_cuts(sequence, camera_cuts, bindings)
    unreal.EditorAssetLibrary.save_loaded_asset(sequence)
    unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(sequence)
    unreal.LevelSequenceEditorBlueprintLibrary.refresh_current_level_sequence()
    unreal.log(f"[CutSceneAI] Generated Level Sequence: {plan['sequence_asset_path']}")
    return sequence


if __name__ == "__main__":
    csir_path = os.environ.get("CUTSCENEAI_CSIR")
    mapping_path = os.environ.get("CUTSCENEAI_UNREAL_MAPPING")
    if not csir_path or not mapping_path:
        raise UnrealBuildError(
            "Set CUTSCENEAI_CSIR and CUTSCENEAI_UNREAL_MAPPING, or import this module and call build()."
        )
    build(csir_path, mapping_path)
